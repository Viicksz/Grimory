import tempfile
import unittest
from pathlib import Path

from comandos.editar import (
    CATEGORIAS_EDITAVEIS,
    SessaoEdicao,
    campos_descricao_narrativa,
    categorias_feiticos,
    definir_campo_narrativo,
    divisoes_itens,
    itens_da_categoria,
    itens_filtrados_edicao,
    ler_documento,
    listar_itens_biblioteca,
    opcoes_campo_registro,
    propagar_edicao_fichas,
    propagar_edicao_fichas_criaturas,
    registros_da_secao,
    renderizar_documento,
    resolver_item_biblioteca,
    serializar_registros,
)
from comandos.remover import ItemRemovivel
from utils.biblioteca import interpretar_markdown, normalizar_rotulo
from utils.fichas import FichaPersonagem, ReferenciaFicha, salvar_ficha
from utils.fichas_criaturas import (
    FichaCriatura,
    ReferenciaFichaCriatura,
    salvar_ficha_criatura,
)


class EditarTests(unittest.TestCase):
    def test_documento_preserva_semantica_do_markdown(self):
        categorias = {
            "encantamentos",
            "arte das trevas",
            "runas antigas",
            "bindrunes",
            "pocoes",
            "criaturas",
            "heranca sanguinea",
            "origem magica",
            "especializacao",
        }
        encontrados = {}
        for item in listar_itens_biblioteca():
            chave = normalizar_rotulo(item.categoria)
            if chave in categorias and chave not in encontrados:
                encontrados[chave] = item

        self.assertEqual(set(encontrados), categorias)
        for item in encontrados.values():
            original = item.arquivo.read_text(encoding="utf-8-sig")
            reconstruido = ler_documento(original, item.nome).markdown()
            antes = interpretar_markdown(original)
            depois = interpretar_markdown(reconstruido)
            self.assertEqual(
                (antes.titulo, antes.descricao, antes.campos),
                (depois.titulo, depois.descricao, depois.campos),
            )

    def test_cada_categoria_usa_renderizador_valido(self):
        esperadas = {
            "encantamentos",
            "arte das trevas",
            "runas antigas",
            "bindrunes",
            "pocoes",
            "criaturas",
            "heranca sanguinea",
            "origem magica",
            "especializacao",
        }
        renderizadas = set()
        for item in listar_itens_biblioteca():
            chave = normalizar_rotulo(item.categoria)
            if chave not in esperadas or chave in renderizadas:
                continue
            conteudo = item.arquivo.read_text(encoding="utf-8-sig")
            sessao = SessaoEdicao(
                1,
                item,
                ler_documento(conteudo, item.nome),
                conteudo,
                None,
                None,
            )
            _, embeds = renderizar_documento(sessao)
            self.assertTrue(embeds)
            renderizadas.add(chave)
        self.assertEqual(renderizadas, esperadas)

    def test_catalogo_do_edit_nao_inclui_fichas(self):
        itens = listar_itens_biblioteca()
        self.assertTrue(itens)
        ficha, ambiguos = resolver_item_biblioteca("fichas/Corvinal/Ollie White.md")
        self.assertIsNone(ficha)
        self.assertFalse(ambiguos)
        self.assertTrue(all(not item.identificador.startswith("fichas/") for item in itens))

    def test_itens_sao_filtrados_pela_categoria_escolhida(self):
        self.assertNotIn("Fichas de Personagem", CATEGORIAS_EDITAVEIS)
        self.assertNotIn("Fichas de Criatura", CATEGORIAS_EDITAVEIS)
        self.assertFalse(itens_da_categoria("Fichas de Personagem"))
        self.assertFalse(itens_da_categoria("Fichas de Criatura"))

    def test_navegacao_principal_usa_os_cinco_tipos_solicitados(self):
        self.assertEqual(
            CATEGORIAS_EDITAVEIS,
            (
                "Feitiços",
                "Poções",
                "Criaturas",
                "Habilidades",
                "Descrição de Personagens",
            ),
        )

    def test_feiticos_sao_divididos_por_categoria_e_ano(self):
        self.assertIn("Encantamentos", categorias_feiticos())
        self.assertIn("1º Ano", divisoes_itens("Feitiços", "Encantamentos"))
        itens = itens_filtrados_edicao("Feitiços", "Encantamentos", "1º Ano")
        self.assertTrue(itens)
        self.assertTrue(all(item.categoria == "Encantamentos" for item in itens))

    def test_arte_das_trevas_usa_vertentes_no_lugar_de_ano(self):
        divisoes = divisoes_itens("Feitiços", "Arte das Trevas")
        self.assertIn("Maldições", divisoes)
        self.assertNotIn("1º Ano", divisoes)

    def test_campos_narrativos_respeitam_o_tipo_de_personagem(self):
        autoridade = FichaPersonagem(
            "Teste", "Figuras de Autoridade", "--", "Humano", "--",
            informacoes=[
                {"titulo": "Cargo", "descricao": "Professor"},
                {"titulo": "Valores", "descricao": "Coragem"},
                {"titulo": "Personalidade", "descricao": "Calmo"},
            ],
            sobre_narrativo="História.",
        )
        self.assertEqual(
            [titulo for titulo, _ in campos_descricao_narrativa(autoridade)],
            ["Cargo", "Valores", "Personalidade", "Sobre"],
        )
        definir_campo_narrativo(autoridade, "Sobre", "Nova história.")
        self.assertEqual(autoridade.sobre_narrativo, "Nova história.")

    def test_registros_de_criatura_sao_editados_sem_expor_json(self):
        valor = '- {"nome":"Emboscada","tipo de ação":"Ação completa","descrição":"Surpresa."}'
        registros = registros_da_secao(valor)
        self.assertEqual(registros[0]["nome"], "Emboscada")
        registros[0]["descrição"] = "Ataque realizado de surpresa."
        self.assertEqual(registros_da_secao(serializar_registros(registros)), registros)

    def test_campos_estruturados_oferecem_opcoes_com_descricao(self):
        acoes = opcoes_campo_registro("Ataques não mágicos", "Tipo de ação")
        fraquezas = opcoes_campo_registro("Fraquezas", "Tipo")
        resistencias = opcoes_campo_registro("Resistências", "Tipo")
        self.assertIn("Completa", acoes)
        self.assertIn("Aumento de Dano Sofrido", fraquezas)
        self.assertIn("Redução de Dano Sofrido", resistencias)
        self.assertTrue(all(acoes.values()))

    def test_edicao_de_habilidade_propaga_nome_para_ficha_relacionada(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Teste.md"
            ficha = FichaPersonagem(
                "Teste",
                "NPCs",
                "--",
                "Humano",
                "--",
                origens_magicas=["Fitometria"],
            )
            salvar_ficha(ficha, caminho, nova=True)
            item = ItemRemovivel(
                Path(pasta) / "Fitometria.md",
                "Habilidades/Origem Mágica/Fitometria.md",
                "Fitometria",
                "Fitometria",
                "Origem Mágica",
                "Habilidades",
                "Origem Mágica",
            )

            afetadas = propagar_edicao_fichas(
                item,
                "Fitometria Renovada",
                "# Fitometria Renovada\n\nDescrição atualizada.\n\nCusto de aquisição em XP:\n40 XP\n",
                [ReferenciaFicha("Teste", "NPCs", caminho)],
            )

            self.assertEqual(afetadas, [caminho])
            self.assertEqual(
                FichaPersonagem.carregar(caminho).origens_magicas,
                ["Fitometria Renovada"],
            )

    def test_renomear_criatura_atualiza_origem_sem_sobrescrever_mecanicas(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "X" / "Teste.md"
            ficha = FichaCriatura(
                "Teste",
                "Fera",
                "X",
                "1 m",
                "De 1 m a 2 m",
                origem_biblioteca="Pelúcio",
                ataques=[{"nome": "Ataque próprio", "descrição": "Mantido."}],
            )
            salvar_ficha_criatura(ficha, caminho, nova=True)
            item = ItemRemovivel(
                Path(pasta) / "Pelúcio.md",
                "criaturas/X/Pelúcio.md",
                "Pelúcio",
                "Pelúcio",
                "Criaturas",
                "Trato de Criaturas Mágicas",
                "X",
            )

            afetadas = propagar_edicao_fichas_criaturas(
                item,
                "Pelúcio Dourado",
                [ReferenciaFichaCriatura("Teste", "X", caminho)],
            )

            atual = FichaCriatura.carregar(caminho)
            self.assertEqual(afetadas, [caminho])
            self.assertEqual(atual.origem_biblioteca, "Pelúcio Dourado")
            self.assertEqual(atual.ataques[0]["nome"], "Ataque próprio")


if __name__ == "__main__":
    unittest.main()
