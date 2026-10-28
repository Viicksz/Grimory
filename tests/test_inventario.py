import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import discord

from comandos.inventario import (
    AnoPocaoInventarioView,
    ArmaInventarioView,
    BolsaView,
    CategoriaIngredienteInventarioView,
    IngredienteInventarioView,
    ImagemItemModal,
    ImagemItemView,
    Inventario,
    ORIGENS_LOOT,
    RegistrarLootView,
    ItemModal,
    QuantidadeItemModal,
    QuantidadeItemView,
    PocaoInventarioView,
    RascunhoItem,
    TipoAlimentoView,
    TipoArmaInventarioView,
    TipoItemView,
    grupo_indice_pocoes,
    interpretar_quantidade,
    preparar_resultado_loot,
    rascunho_categoria_loot,
    rolar_loot,
)
from utils.fichas import FichaPersonagem
from utils.inventario import (
    CATEGORIAS_ITENS,
    TIPOS_ALIMENTO,
    consumir_item,
    formatar_item,
    ingredientes_oficiais_por_grupo,
    montar_embed_itens,
    remover_item,
    somar_item,
    unidade_ingrediente_oficial,
)
from utils.quadribol import Vassoura


def ficha_teste() -> FichaPersonagem:
    return FichaPersonagem(
        "Teste",
        "Players",
        "Corvinal",
        "Meio-Sangue",
        "Penas de Fênix",
        galeoes=10,
    )


class InventarioTests(unittest.TestCase):
    @patch("comandos.inventario.FichaPersonagem.carregar")
    def test_bolsa_permite_modificar_e_remover_itens(self, carregar):
        ficha = ficha_teste()
        ficha.itens = [
            {"categoria": "Variados", "nome": "Corda", "quantidade": "2"}
        ]
        carregar.return_value = ficha
        view = BolsaView(1, Path("Teste.md"))
        self.assertEqual(
            [botao.label for botao in view.children],
            ["Modificar item", "Remover item", "Voltar à ficha"],
        )

    def test_foto_opcional_aparece_em_todo_item_e_pode_ser_editada(self):
        url = "https://exemplo.com/item.png"
        item = {
            "categoria": "Ingredientes",
            "nome": "Muco",
            "quantidade": "2",
            "unidade": "ml",
            "imagem": url,
        }
        self.assertIn(f"[📷 Ver imagem]({url})", formatar_item(item))
        item["imagem"] = "biblioteca/fichas/imagens/itens/teste/item.png"
        self.assertIn("📷 Foto cadastrada", formatar_item(item))

        novo = ImagemItemView(
            1,
            Path("Teste.md"),
            RascunhoItem("Variados", "Corda"),
        )
        self.assertEqual(
            [botao.label for botao in novo.children],
            ["Adicionar foto", "Continuar sem foto"],
        )

        existente = RascunhoItem(
            "Variados",
            "Corda",
            {"imagem": url, "_quantidade_atual": "2"},
            0,
        )
        view = ImagemItemView(1, Path("Teste.md"), existente)
        self.assertEqual(
            [botao.label for botao in view.children],
            ["Alterar foto", "Manter foto", "Remover foto"],
        )
        modal = ImagemItemModal(1, Path("Teste.md"), existente)
        self.assertIsInstance(modal.arquivo_imagem, discord.ui.FileUpload)
        self.assertTrue(modal.arquivo_imagem.required)

    def test_ingredientes_usam_categoria_biblioteca_e_unidade_automatica(self):
        categorias = CategoriaIngredienteInventarioView(1, Path("Teste.md"))
        opcoes = categorias.children[0].options
        self.assertIn("Partes de Criaturas Mágicas", [opcao.label for opcao in opcoes])
        self.assertEqual(
            next(
                opcao.emoji.name
                for opcao in opcoes
                if opcao.label == "Partes de Criaturas Mágicas"
            ),
            "🐉",
        )

        grupo = "Partes de Criaturas Mágicas"
        ingredientes = ingredientes_oficiais_por_grupo()[grupo]
        view = IngredienteInventarioView(
            1,
            Path("Teste.md"),
            grupo,
            ingredientes,
            0,
        )
        self.assertIn("Veneno de Acromântula", ingredientes)
        pagina_do_veneno = ingredientes.index("Veneno de Acromântula") // 25
        view = view.nova(pagina_do_veneno)
        opcao = next(
            item for item in view.children[0].options
            if item.label == "Veneno de Acromântula"
        )
        self.assertEqual(opcao.description, "Quantidade medida em ml.")

    def test_pocoes_usam_ano_indice_clicavel_e_menu_da_biblioteca(self):
        anos = AnoPocaoInventarioView(1, Path("Teste.md"))
        self.assertEqual(
            [opcao.label for opcao in anos.children[0].options],
            [f"{ano}º Ano" for ano in range(1, 8)],
        )

        from comandos.ficha import listar_pocoes_ficha
        from utils.biblioteca import normalizar_rotulo

        referencias = listar_pocoes_ficha("1º Ano")
        self.assertTrue(referencias)
        primeira = referencias[0]
        url = "https://discord.com/channels/1/2/3"
        view = PocaoInventarioView(
            1,
            Path("Teste.md"),
            "1º Ano",
            referencias,
            {normalizar_rotulo(primeira.nome): url},
            0,
        )
        self.assertEqual(view.children[0].options[0].label, primeira.nome)
        self.assertIn(f"[{primeira.nome}]({url})", view.embed_indice().description)
        self.assertEqual(grupo_indice_pocoes("1º Ano", [primeira]).titulo, "1º Ano")

        modal = QuantidadeItemModal(
            1,
            Path("Teste.md"),
            RascunhoItem("Poções", primeira.nome),
        )
        self.assertEqual(modal.quantidade.label, "Quantidade em frascos")

    def test_quantidade_livre_e_definida_por_modal(self):
        rascunho = RascunhoItem(
            "Dinheiro",
            "Galeão(ões)",
            {"tipo": "Galeão(ões)", "_quantidade_atual": "37"},
        )
        view = QuantidadeItemView(1, Path("Teste.md"), rascunho)
        self.assertEqual(view.children[0].label, "Alterar quantidade atual: 37")
        modal = QuantidadeItemModal(1, Path("Teste.md"), rascunho, "37")
        self.assertEqual(modal.quantidade.label, "Quantidade em Galeão(ões)")
        self.assertEqual(modal.quantidade.default, "37")
        self.assertEqual(interpretar_quantidade("284"), 284)
        with self.assertRaisesRegex(ValueError, "número inteiro"):
            interpretar_quantidade("dois")
        with self.assertRaisesRegex(ValueError, "maior que zero"):
            interpretar_quantidade("0")

    @patch("utils.quadribol.encontrar_vassoura")
    def test_vassoura_exibe_dados_atualizados_do_catalogo(self, encontrar):
        encontrar.return_value = Vassoura(
            nome="Nimbus 2000",
            bonus_voo=2,
            vida_maxima=3,
            velocidade="10m/s",
            bonus_reflexo=1,
            bonus_fortitude=0,
            bonus_pontaria=1,
            uso_bonus_pontaria="perseguições",
            especificacoes=("Curvas fechadas sem perda de velocidade.",),
        )
        texto = formatar_item(
            {
                "categoria": "Variados",
                "nome": "Nimbus 2000",
                "quantidade": "1",
                "tipo": "Vassoura",
                "equipada": "Sim",
            }
        )
        self.assertIn("» **Nimbus 2000** — 1x • *Equipada*", texto)
        self.assertIn("> **PV:** 3", texto)
        self.assertIn("> **Velocidade:** 10m/s", texto)
        self.assertIn("Vôo +2 • Reflexo +1 • Fortitude +0", texto)
        self.assertIn("Pontaria +1 em perseguições", texto)
        self.assertIn("> **Especificações:**", texto)
        self.assertIn("> » Curvas fechadas sem perda de velocidade.", texto)

    def test_embed_respeita_ordem_e_formatos_das_categorias(self):
        ficha = ficha_teste()
        ficha.itens = [
            {"categoria": "Ingredientes", "nome": "Muco", "quantidade": "250", "unidade": "ml"},
            {"categoria": "Poções", "nome": "Murtisco", "quantidade": "2"},
            {"categoria": "Alimentos", "nome": "Torta", "tipo": "Doces", "quantidade": "3"},
            {"categoria": "Armas", "nome": "Espada Longa", "quantidade": "1", "tipo": "Cortante", "dano": "1d8+des", "critico": "19"},
            {"categoria": "Variados", "nome": "Corda", "descricao": "Uma corda resistente.", "quantidade": "4"},
        ]
        embed = montar_embed_itens(ficha)
        self.assertEqual(embed.title, "🎒 Itens")
        self.assertEqual(
            [campo.name.split(" ", 1)[1] for campo in embed.fields],
            list(CATEGORIAS_ITENS),
        )
        valores = "\n".join(campo.value for campo in embed.fields)
        self.assertIn("» **10** Galeões", valores)
        self.assertIn("» **Muco** — 250 ml", valores)
        self.assertIn("» **Murtisco** — 2x", valores)
        self.assertIn("» **Torta** *Doces* — 3x", valores)
        self.assertIn("> Uma corda resistente.", valores)
        self.assertIn("» **Espada Longa** *Cortante* `1d8+des` `crit. 19`", valores)

    def test_itens_iguais_somam_quantidade_e_galeoes_usam_campo_existente(self):
        ficha = ficha_teste()
        somar_item(ficha, {"categoria": "Variados", "nome": "Corda", "quantidade": "2"})
        somar_item(ficha, {"categoria": "Variados", "nome": "Corda", "quantidade": "3"})
        somar_item(ficha, {"categoria": "Dinheiro", "nome": "Galeão(ões)", "tipo": "Galeão(ões)", "quantidade": "5"})
        self.assertEqual(ficha.itens[0]["quantidade"], "5")
        self.assertEqual(ficha.galeoes, 15)

        somar_item(
            ficha,
            {
                "categoria": "Dinheiro",
                "nome": "Galeão(ões)",
                "tipo": "Galeão(ões)",
                "quantidade": "1",
                "imagem": "https://exemplo.com/galeao.png",
            },
        )
        self.assertEqual(ficha.galeoes, 16)
        self.assertIn(
            "[📷 Ver imagem](https://exemplo.com/galeao.png)",
            montar_embed_itens(ficha).fields[0].value,
        )

    def test_remover_galeoes_nao_remove_outros_itens(self):
        ficha = ficha_teste()
        ficha.itens = [{"categoria": "Variados", "nome": "Corda", "quantidade": "1"}]
        remover_item(ficha, "galeoes")
        self.assertEqual(ficha.galeoes, 0)
        self.assertEqual(len(ficha.itens), 1)

    def test_consumir_item_reduz_quantidade_e_remove_no_ultimo_uso(self):
        ficha = ficha_teste()
        ficha.itens = [{"categoria": "Poções", "nome": "Wiggenweld", "quantidade": "2"}]
        self.assertEqual(consumir_item(ficha, "Poções", "wiggenweld"), 1)
        self.assertEqual(ficha.itens[0]["quantidade"], "1")
        self.assertEqual(consumir_item(ficha, "Poções", "Wiggenweld"), 0)
        self.assertEqual(ficha.itens, [])

    def test_loot_e_formulario_usam_origens_e_categorias_definidas(self):
        self.assertEqual(
            ORIGENS_LOOT,
            ("Furto", "Criatura", "Ambiente Urbano", "Ambiente Selvagem"),
        )
        parametro_origem = Inventario.loot.parameters[0]
        self.assertEqual(
            [escolha.name for escolha in parametro_origem.choices],
            list(ORIGENS_LOOT),
        )
        view = TipoItemView(1, Path("Teste.md"))
        seletor = view.children[0]
        self.assertEqual([opcao.label for opcao in seletor.options], list(CATEGORIAS_ITENS))

        alimentos = TipoAlimentoView(1, Path("Teste.md"), RascunhoItem("Alimentos"))
        self.assertEqual(
            [opcao.label for opcao in alimentos.children[0].options],
            list(TIPOS_ALIMENTO),
        )

        variados = ItemModal(1, Path("Teste.md"), RascunhoItem("Variados"))
        self.assertEqual([campo.label for campo in variados.children], ["Título", "Descrição"])
        self.assertFalse(variados.descricao.required)

        registrar = RegistrarLootView(1, Path("Teste.md"), "Alimentos — Refeições")
        self.assertEqual(registrar.children[0].label, "Registrar item")
        self.assertEqual(registrar.children[1].label, "Descartar")
        self.assertEqual(registrar.children[1].emoji.name, "🗑️")
        interaction = AsyncMock()
        asyncio.run(registrar.descartar(interaction))
        interaction.response.defer.assert_awaited_once()
        interaction.delete_original_response.assert_awaited_once()
        alimento = rascunho_categoria_loot("Alimentos — Refeições")
        self.assertIsNotNone(alimento)
        assert alimento is not None
        self.assertEqual(alimento.categoria, "Alimentos")
        self.assertEqual(alimento.dados["tipo"], "Refeições")
        self.assertIsNone(rascunho_categoria_loot(""))

        grupos = ingredientes_oficiais_por_grupo()
        self.assertIn("Partes de Criaturas Mágicas", grupos)
        self.assertIn("Veneno de Acromântula", grupos["Partes de Criaturas Mágicas"])
        self.assertEqual(
            unidade_ingrediente_oficial(
                "Veneno de Acromântula", "Partes de Criaturas Mágicas"
            ),
            ("Líquido", "ml"),
        )

    def test_armas_sao_escolhidas_por_tipo_com_opcao_personalizada(self):
        rascunho = RascunhoItem("Armas")
        tipos = TipoArmaInventarioView(1, Path("Teste.md"), rascunho)
        self.assertEqual(
            [opcao.label for opcao in tipos.children[0].options],
            [
                "Armas Naturais",
                "Armas Simples",
                "Armas Marciais",
                "Armas Exóticas",
                "Armas de Fogo",
            ],
        )
        marciais = ArmaInventarioView(
            1, Path("Teste.md"), rascunho, "Armas Marciais"
        )
        opcoes = marciais.children[0].options
        self.assertIn("Espada Longa", [opcao.label for opcao in opcoes])
        self.assertEqual(opcoes[-1].label, "Personalizada")
        espada = next(opcao for opcao in opcoes if opcao.label == "Espada Longa")
        self.assertIn("Cortante", espada.description)
        self.assertIn("1d8+Destreza", espada.description)
        self.assertEqual(rascunho.registro(1)["quantidade"], "1")

    def test_modal_de_arma_preserva_quantidade_atual_apenas_em_edicao(self):
        nova = RascunhoItem("Armas")
        modal_novo = ItemModal(1, Path("Teste.md"), nova)
        self.assertNotIn("_quantidade_atual", modal_novo.rascunho.dados)

        existente = RascunhoItem(
            "Armas",
            "Adaga",
            {"tipo": "Perfurante", "_quantidade_atual": "3"},
            0,
        )
        modal_existente = ItemModal(
            1,
            Path("Teste.md"),
            existente,
            {"nome": "Adaga", "tipo": "Perfurante"},
        )
        self.assertEqual(modal_existente.rascunho.dados["_quantidade_atual"], "3")

    @patch("comandos.inventario.secrets.choice", return_value="Veneno de Acromântula")
    @patch("comandos.inventario.secrets.randbelow", side_effect=[3, 17, 1])
    def test_criatura_domesticada_rola_com_vantagem(self, _randbelow, _choice):
        ficha = ficha_teste()
        ficha.aptidoes["Trato de Criaturas Mágicas"] = 2
        embed = rolar_loot(ficha, "Criatura", "Domesticada")
        campos = {campo.name: campo.value for campo in embed.fields}
        self.assertEqual(campos["Teste"], "Trato de Criaturas Mágicas")
        self.assertIn("vantagem: 4, 18", campos["Rolagem"])
        self.assertIn("**20**", campos["Rolagem"])
        self.assertEqual(campos["Categoria encontrada"], "Ingredientes — Partes de criatura")
        self.assertEqual(
            campos["Item encontrado"],
            "» **Veneno de Acromântula** — 2 ml",
        )

    @patch("comandos.inventario.secrets.randbelow", return_value=19)
    def test_resultado_acima_de_vinte_fica_a_decisao_do_mestre(self, _randbelow):
        ficha = ficha_teste()
        ficha.pericias["Crime"] = 2
        embed = rolar_loot(ficha, "Furto")
        campos = {campo.name: campo.value for campo in embed.fields}
        self.assertIn("Resultado acima de 20", campos)
        self.assertIn("decidido pelo mestre", campos["Resultado acima de 20"])

    @patch("comandos.inventario.secrets.randbelow", return_value=19)
    def test_resultado_acima_de_vinte_abre_todos_os_tipos_para_registro(self, _randbelow):
        ficha = ficha_teste()
        ficha.pericias["Crime"] = 2
        embed, categoria, item = preparar_resultado_loot(ficha, "Furto")
        self.assertEqual(categoria, "")
        self.assertIsNone(item)
        self.assertIn("Registrar item", embed.description)


if __name__ == "__main__":
    unittest.main()
