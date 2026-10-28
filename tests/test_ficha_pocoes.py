import tempfile
import unittest
import json
from pathlib import Path

from comandos.ficha import (
    DescricaoPocaoFichaModal,
    FichaAtualView,
    exemplo_descricao_pocao,
    listar_categorias_pocoes_ficha,
    listar_pocoes_ficha,
    montar_embeds_ficha,
    dividir_embeds_publicacao_personagem,
)
from utils.fichas import FichaPersonagem


def ficha_teste(**alteracoes) -> FichaPersonagem:
    dados = {
        "nome": "Teste",
        "grupo": "Players",
        "casa": "Sonserina",
        "heranca": "Meio-Sangue",
        "nucleo": "Coração de Dragão",
    }
    dados.update(alteracoes)
    return FichaPersonagem(**dados)


class PocoesDaFichaTests(unittest.TestCase):
    def test_catalogo_usa_as_42_pocoes_e_os_sete_anos_da_biblioteca(self):
        self.assertEqual(len(listar_pocoes_ficha()), 42)
        self.assertEqual(
            listar_categorias_pocoes_ficha(),
            [f"{ano}º Ano" for ano in range(1, 8)],
        )

    def test_descricao_guia_da_pocao_usa_o_efeito_da_biblioteca(self):
        pocao = next(
            item
            for item in listar_pocoes_ficha("1º Ano")
            if item.nome == "Essência de Murtisco"
        )
        guia = exemplo_descricao_pocao(pocao)
        self.assertIn("Medicina de cura", guia)
        modal = DescricaoPocaoFichaModal(1, pocao.caminho, pocao, "")
        self.assertEqual(modal.descricao.default, guia)
        self.assertEqual(modal.descricao.max_length, 1024)

    def test_pocoes_ficam_no_inventario_e_fichas_antigas_sao_migradas(self):
        ficha = ficha_teste(
            itens=[
                {
                    "categoria": "Poções",
                    "nome": "Essência de Murtisco",
                    "quantidade": "2",
                    "unidade": "frasco",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Teste.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            carregada = FichaPersonagem.carregar(caminho)
            self.assertEqual(carregada.itens, ficha.itens)

            legado = Path(pasta) / "Legado.md"
            legado.write_text(
                ficha_teste().markdown()
                + "\nPoções favoritas:\n- "
                + json.dumps(
                    {
                        "nome": "Essência de Murtisco",
                        "categoria": "1º Ano",
                        "descricao": "Usada para tratar ferimentos.",
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            antiga = FichaPersonagem.carregar(legado)
        self.assertEqual(antiga.pocoes_favoritas, [])
        self.assertEqual(antiga.itens[0]["categoria"], "Poções")
        self.assertEqual(antiga.itens[0]["quantidade"], "1")

    def test_pocoes_aparecem_em_itens_e_botoes_foram_substituidos(self):
        ficha = ficha_teste(
            itens=[
                {
                    "categoria": "Poções",
                    "nome": "Essência de Murtisco",
                    "quantidade": "2",
                    "unidade": "frasco",
                }
            ]
        )
        embeds = montar_embeds_ficha(ficha)
        itens = next(embed for embed in embeds if embed.title == "🎒 Itens")
        self.assertEqual(itens.fields[1].name, "🧪 Poções")
        self.assertIn("Essência de Murtisco", itens.fields[1].value)
        self.assertIn("2x", itens.fields[1].value)

        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Teste.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            view = FichaAtualView(1, caminho)
            linhas = {
                item.label: item.row
                for item in view.children
            }
            primeira_linha = [
                item.label for item in view.children if item.row == 1
            ]
            rotulos = set(linhas)
        self.assertIn("Item", rotulos)
        self.assertIn("Modificar Item", rotulos)
        self.assertNotIn("Poção", rotulos)
        self.assertNotIn("Modificar Poção", rotulos)
        self.assertEqual(linhas["Mercado de XP"], 0)
        self.assertEqual(linhas["Info"], 1)
        self.assertEqual(linhas["Modificar Info"], 1)
        self.assertEqual(linhas["Item"], 2)
        self.assertEqual(linhas["Modificar Item"], 2)
        self.assertEqual(linhas["Feitiço"], 3)
        self.assertEqual(linhas["Modificar Feitiço"], 3)
        self.assertEqual(linhas["Imagem"], 1)
        self.assertEqual(
            primeira_linha,
            ["Imagem", "Info", "Modificar Info"],
        )

    def test_autoridade_separa_inventario_sem_ultrapassar_limite_por_mensagem(self):
        ficha = ficha_teste(
            grupo="Figuras de Autoridade",
            feiticos_favoritos=[
                {"nome": "Bombarda", "categoria": "Duelos", "descricao": "Explosão."}
            ],
            itens=[
                {
                    "categoria": "Poções",
                    "nome": "Essência de Murtisco",
                    "quantidade": "1",
                    "unidade": "frasco",
                }
            ],
        )
        principal, parte_2, parte_3 = dividir_embeds_publicacao_personagem(ficha)
        self.assertTrue(all(len(parte) <= 10 for parte in (principal, parte_2, parte_3)))
        todos = principal + parte_2 + parte_3
        self.assertIn("🎒 Itens", [embed.title for embed in todos])
        grimorio = next(embed for embed in todos if embed.title == "📚 Grimório Pessoal")
        self.assertEqual(len(grimorio.fields), 1)


if __name__ == "__main__":
    unittest.main()
