from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from shutil import copy2
from unittest.mock import patch

from comandos.ficha import (
    AdicionarImagemFichaModal,
    AtributosMercadoView,
    CategoriaPresetAutoridadeView,
    EditarPresetsAutoridadeModal,
    FichaAtualView,
    ImagemFichaView,
    PresetsAutoridadeView,
    RemoverImagemFichaView,
    SessaoFicha,
    ficha_da_sessao,
    limite_temporario_de_edicoes,
    montar_embeds_ficha,
    validar_url_imagem_ficha,
)
from utils.fichas import (
    FichaPersonagem,
    GRUPOS_FICHA,
    informacao_obrigatoria,
    listar_fichas,
    salvar_ficha,
)
from utils.taca import carregar_autoridades


class FigurasAutoridadeTests(unittest.TestCase):
    def test_limite_de_edicoes_antigas_e_reconhecido(self) -> None:
        erro_discord = RuntimeError("Maximum number of edits to messages older than 1 hour reached")
        erro_discord.code = 30046
        erro_publicacao = RuntimeError("Não consegui atualizar a publicação")
        erro_publicacao.__cause__ = erro_discord

        self.assertTrue(limite_temporario_de_edicoes(erro_publicacao))
        self.assertFalse(limite_temporario_de_edicoes(RuntimeError("Outro erro")))

    def test_categoria_e_as_vinte_e_uma_fichas_estao_disponiveis(self) -> None:
        self.assertIn("Figuras de Autoridade", GRUPOS_FICHA)
        fichas = [
            referencia
            for referencia in listar_fichas()
            if referencia.grupo == "Figuras de Autoridade"
        ]
        self.assertEqual(len(fichas), 21)

    def test_fichas_preservam_perfil_e_presets_da_taca(self) -> None:
        autoridades = carregar_autoridades()
        self.assertEqual(len(autoridades), 21)
        minerva = autoridades[0]
        self.assertEqual(minerva.nome, "Minerva McGonagall")
        self.assertIn("diretora", minerva.ocupacao)
        self.assertEqual(len(minerva.gratificacoes), 10)
        self.assertEqual(len(minerva.penalidades), 10)

    def test_publicacao_nao_exibe_presets_de_autoridade(self) -> None:
        referencia = next(
            item for item in listar_fichas()
            if item.nome == "Minerva McGonagall"
            and item.grupo == "Figuras de Autoridade"
        )
        embeds = montar_embeds_ficha(FichaPersonagem.carregar(referencia.caminho))
        self.assertEqual(embeds[1].title, "📋 Informações")
        self.assertEqual(embeds[2].title, "🎒 Itens")
        self.assertNotIn("🏆 Gratificações", [embed.title for embed in embeds])
        self.assertNotIn("⚠️ Penalidades", [embed.title for embed in embeds])

    def test_painel_de_presets_exibe_catalogo_antes_de_modificar(self) -> None:
        referencia = next(
            item for item in listar_fichas()
            if item.nome == "Minerva McGonagall"
            and item.grupo == "Figuras de Autoridade"
        )
        painel = PresetsAutoridadeView(1, referencia.caminho, "gratificacoes")
        self.assertEqual(
            [item.label for item in painel.children],
            ["Modificar", "Voltar à ficha"],
        )

    def test_consulta_oferece_editores_exclusivos_da_autoridade(self) -> None:
        referencia = next(
            item for item in listar_fichas()
            if item.nome == "Minerva McGonagall"
            and item.grupo == "Figuras de Autoridade"
        )
        view = FichaAtualView(1, referencia.caminho)
        rotulos = {item.label for item in view.children}
        self.assertIn("Gratificações", rotulos)
        self.assertIn("Penalidades", rotulos)
        self.assertIn("Imagem", rotulos)

        outra = next(
            item for item in listar_fichas()
            if item.grupo != "Figuras de Autoridade"
        )
        view_comum = FichaAtualView(1, outra.caminho)
        rotulos_comuns = {item.label for item in view_comum.children}
        self.assertNotIn("Gratificações", rotulos_comuns)
        self.assertNotIn("Penalidades", rotulos_comuns)
        self.assertIn("Imagem", rotulos_comuns)

    def test_imagem_possui_upload_obrigatorio_e_titulo_opcional(self) -> None:
        referencia = next(
            item for item in listar_fichas()
            if item.grupo == "Figuras de Autoridade"
        )
        modal = AdicionarImagemFichaModal(1, referencia.caminho)
        self.assertFalse(modal.titulo_imagem.required)
        self.assertTrue(modal.arquivo_imagem.required)

        arquivo = "biblioteca/fichas/imagens/teste/personagem.png"
        remover = RemoverImagemFichaView(
            1,
            referencia.caminho,
            [{"titulo": "", "arquivo": arquivo}],
        )
        self.assertEqual(remover.seletor.options[0].label, arquivo)

    def test_imagem_e_preservada_e_exibida_na_ficha(self) -> None:
        ficha = FichaPersonagem(
            "Imagem Teste",
            "Players",
            "Corvinal",
            "Meio-Sangue",
            "Penas de Fênix",
            imagens=[
                {
                    "titulo": "Retrato",
                    "url": "https://exemplo.com/retrato.png",
                },
                {
                    "titulo": "",
                    "url": "https://exemplo.com/sem-titulo.png",
                },
            ],
        )
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "Imagem Teste.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            recarregada = FichaPersonagem.carregar(caminho)
        self.assertEqual(recarregada.imagens, ficha.imagens)
        embeds = montar_embeds_ficha(recarregada)
        identidade = embeds[0]
        self.assertEqual(
            identidade.image.url,
            "https://exemplo.com/retrato.png",
        )
        campo = next(item for item in identidade.fields if item.name == "Aparência")
        self.assertEqual(
            campo.value,
            "[Retrato](https://exemplo.com/retrato.png)\n"
            "[Aparência 2](https://exemplo.com/sem-titulo.png)",
        )
        identidade_publica = montar_embeds_ficha(
            recarregada,
            apenas_aparencia_atual=True,
        )[0]
        campo_publico = next(
            item for item in identidade_publica.fields if item.name == "Aparência"
        )
        self.assertEqual(
            campo_publico.value,
            "[Retrato](https://exemplo.com/retrato.png)\n"
            "[Aparência 2](https://exemplo.com/sem-titulo.png)",
        )
        self.assertIn("https://", campo_publico.value)
        self.assertIsNone(embeds[1].image.url)

    def test_link_de_imagem_precisa_ser_http(self) -> None:
        self.assertEqual(
            validar_url_imagem_ficha("https://exemplo.com/a.png"),
            "https://exemplo.com/a.png",
        )
        with self.assertRaises(ValueError):
            validar_url_imagem_ficha("arquivo-local.png")

    def test_menu_de_imagem_permite_visualizar_aparencias_secundarias(self) -> None:
        view = ImagemFichaView(1, Path("Arthur Carter.md"))
        seletor = view.children[0]
        self.assertEqual(
            [opcao.value for opcao in seletor.options],
            ["visualizar", "adicionar", "remover"],
        )

    def test_editor_escolhe_categoria_e_modal_possui_dois_acontecimentos(self) -> None:
        referencia = next(
            item for item in listar_fichas()
            if item.nome == "Minerva McGonagall"
            and item.grupo == "Figuras de Autoridade"
        )
        seletor = CategoriaPresetAutoridadeView(
            1,
            referencia.caminho,
            "gratificacoes",
        )
        self.assertEqual(len(seletor.seletor.options), 5)
        self.assertEqual(seletor.seletor.options[0].label, "Evolução pessoal")

        modal = EditarPresetsAutoridadeModal(
            1,
            referencia.caminho,
            "gratificacoes",
            "Evolução pessoal",
            5,
            "+5 pontos",
            ["Primeira", "Segunda"],
        )
        self.assertEqual(
            [item.label for item in modal.children],
            ["Primeiro acontecimento", "Segundo acontecimento"],
        )

    def test_roundtrip_nao_apaga_dados_de_autoridade(self) -> None:
        referencia = next(
            item for item in listar_fichas()
            if item.nome == "Minerva McGonagall"
            and item.grupo == "Figuras de Autoridade"
        )
        ficha = FichaPersonagem.carregar(referencia.caminho)
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "Minerva.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            recarregada = FichaPersonagem.carregar(caminho)
        self.assertEqual(recarregada.ordem_autoridade, 1)
        self.assertEqual(
            recarregada.gratificacoes_autoridade,
            ficha.gratificacoes_autoridade,
        )
        self.assertEqual(
            recarregada.penalidades_autoridade,
            ficha.penalidades_autoridade,
        )

    def test_distribuicao_inicial_pode_reduzir_atributos_ate_confirmar(self) -> None:
        referencia = next(
            item for item in listar_fichas()
            if item.nome == "Minerva McGonagall"
            and item.grupo == "Figuras de Autoridade"
        )
        ficha = FichaPersonagem.carregar(referencia.caminho)
        ficha.atributos = {nome: 10 for nome in ficha.atributos}
        ficha.pontos_atributo_disponiveis = 52
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "Minerva.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            view = AtributosMercadoView(1, caminho, ficha)
            self.assertTrue(view.configuracao_inicial_autoridade)
            botoes_menos = [
                item for item in view.children
                if getattr(item, "delta", 0) == -1
            ]
            self.assertTrue(botoes_menos)
            self.assertTrue(all(not item.disabled for item in botoes_menos))

    def test_niveis_e_pontos_iniciais_seguem_a_hierarquia(self) -> None:
        fichas = {
            item.nome: FichaPersonagem.carregar(item.caminho)
            for item in listar_fichas()
            if item.grupo == "Figuras de Autoridade"
        }
        self.assertEqual(fichas["Minerva McGonagall"].nivel, 20)
        minerva = fichas["Minerva McGonagall"]
        self.assertEqual(
            minerva.pontos_atributo_disponiveis
            + sum(valor - 10 for valor in minerva.atributos.values()),
            52,
        )
        representantes = {
            "Rhysand Velaris",
            "Arthur Carter",
            "Kin Yamazaki",
            "Alessa Belshoff",
        }
        for nome, ficha in fichas.items():
            if nome == "Minerva McGonagall":
                continue
            nivel_esperado = 10 if nome in representantes else 8
            pontos_esperados = 32 if nome in representantes else 28
            self.assertEqual(ficha.nivel, nivel_esperado, nome)
            if ficha.pontos_atributo_disponiveis == 0:
                self.assertEqual(
                    sum(valor - 10 for valor in ficha.atributos.values()),
                    pontos_esperados,
                    nome,
                )
                continue
            self.assertEqual(
                ficha.pontos_atributo_disponiveis,
                pontos_esperados,
                nome,
            )

    def test_pasta_vazia_nao_recupera_catalogo_antigo(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            with patch("utils.taca.PASTA_AUTORIDADES", Path(temporario)):
                with self.assertRaisesRegex(
                    ValueError,
                    "Nenhuma ficha de Figura de Autoridade",
                ):
                    carregar_autoridades()

    def test_nova_autoridade_incompleta_nao_bloqueia_a_taca(self) -> None:
        minerva = next(
            item for item in listar_fichas()
            if item.nome == "Minerva McGonagall"
            and item.grupo == "Figuras de Autoridade"
        )
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            copy2(minerva.caminho, pasta / minerva.caminho.name)
            incompleta = FichaPersonagem(
                "Nova Autoridade",
                "Figuras de Autoridade",
                "--",
                "--",
                "--",
                ordem_autoridade=99,
            )
            salvar_ficha(incompleta, pasta / "Nova Autoridade.md", nova=True)
            with patch("utils.taca.PASTA_AUTORIDADES", pasta):
                autoridades = carregar_autoridades()
        self.assertEqual([item.nome for item in autoridades], ["Minerva McGonagall"])

    def test_criacao_prepara_campos_sem_ativar_a_taca(self) -> None:
        sessao = SessaoFicha(
            usuario_id=1,
            nome="Nova Professora",
            grupo="Figuras de Autoridade",
            nivel=8,
            heranca="--",
            casa="Corvinal",
            nucleo="--",
            classe_social="Média",
            galeoes=10,
        )
        ficha = ficha_da_sessao(sessao)
        self.assertGreater(ficha.ordem_autoridade, 21)
        self.assertEqual(
            [item["titulo"] for item in ficha.informacoes],
            ["Altura e Idade", "Cargo", "Valores", "Personalidade", "Familiar", "Patrono"],
        )
        self.assertFalse(ficha.gratificacoes_autoridade)
        self.assertFalse(ficha.penalidades_autoridade)

    def test_npc_nao_bruxo_nao_exige_familiar_nem_patrono(self) -> None:
        sessao = SessaoFicha(
            usuario_id=1,
            nome="Humano",
            grupo="NPCs",
            tipo_npc="Humano/Trouxa",
            nivel=2,
        )
        ficha = ficha_da_sessao(sessao)
        titulos = [item["titulo"] for item in ficha.informacoes]
        self.assertEqual(titulos, ["Altura e Idade", "Sobre"])
        self.assertTrue(informacao_obrigatoria(ficha, "Altura e Idade"))
        self.assertFalse(informacao_obrigatoria(ficha, "Familiar"))
        self.assertFalse(informacao_obrigatoria(ficha, "Patrono"))

    def test_cursando_e_obrigatorio_somente_nas_quatro_casas(self) -> None:
        casa = FichaPersonagem(
            "Aluna", "Corvinal", "Corvinal", "Meio-Sangue", "Penas de Fênix"
        )
        player = FichaPersonagem(
            "Player", "Players", "--", "Meio-Sangue", "Penas de Fênix"
        )
        self.assertTrue(informacao_obrigatoria(casa, "Cursando"))
        self.assertFalse(informacao_obrigatoria(player, "Cursando"))

    def test_perfis_disponiveis_foram_preenchidos_sem_citacoes(self) -> None:
        sem_base_suficiente: set[str] = set()
        referencias = [
            item for item in listar_fichas() if item.grupo == "Figuras de Autoridade"
        ]
        self.assertEqual(len(referencias), 21)
        for referencia in referencias:
            ficha = FichaPersonagem.carregar(referencia.caminho)
            informacoes = {item["titulo"]: item["descricao"] for item in ficha.informacoes}
            with self.subTest(autoridade=ficha.nome):
                titulos_esperados = {
                    "Cargo",
                    "Valores",
                    "Personalidade",
                    "Familiar",
                    "Patrono",
                }
                self.assertEqual(
                    set(informacoes),
                    titulos_esperados | {"Altura e Idade"},
                )
                if ficha.nome in sem_base_suficiente:
                    self.assertEqual(informacoes["Valores"], "--")
                    self.assertEqual(informacoes["Personalidade"], "--")
                else:
                    self.assertNotEqual(informacoes["Valores"], "--")
                    self.assertNotEqual(informacoes["Personalidade"], "--")


if __name__ == "__main__":
    unittest.main()
