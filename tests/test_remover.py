import inspect
import unittest
from pathlib import Path

from comandos.remover import (
    EMOJIS_CATEGORIAS_REMOVER,
    PASTA_BIBLIOTECA,
    CategoriasRemocaoView,
    ItemRemovivel,
    PASTAS_FICHAS_REMOVIVEIS,
    PastasFichaRemocaoView,
    Remover,
    classificar_item,
    listar_itens_removiveis,
    paginas_itens_removiveis,
)


class RemoverUnificadoTests(unittest.TestCase):
    def test_emojis_de_feiticos_e_runas(self):
        for categoria in (
            "Encantamentos",
            "Transfiguração",
            "Duelos",
            "Defesa Contra Arte das Trevas",
            "Arte das Trevas",
        ):
            self.assertEqual(EMOJIS_CATEGORIAS_REMOVER[categoria], "🪄")
        self.assertEqual(EMOJIS_CATEGORIAS_REMOVER["Runas Antigas"], "📜")
        self.assertEqual(EMOJIS_CATEGORIAS_REMOVER["Bindrunes"], "📜")

    def test_comando_remove_nao_exige_item_no_slash(self):
        parametros = inspect.signature(Remover.remover.callback).parameters
        self.assertEqual(list(parametros), ["self", "interaction"])

    def test_fluxo_comeca_pelas_categorias_da_biblioteca(self):
        view = CategoriasRemocaoView(Remover(None), 1)
        self.assertEqual(view.seletor.placeholder, "Categoria da Biblioteca")
        self.assertEqual(view.seletor.options[0].label, "Lixeira")
        self.assertIn("Fichas", [opcao.label for opcao in view.seletor.options])
        self.assertTrue(all(opcao.emoji is not None for opcao in view.seletor.options))

    def test_fichas_sao_separadas_pelas_pastas(self):
        view = PastasFichaRemocaoView(Remover(None), 1)
        self.assertEqual(view.seletor.placeholder, "Pastas de Fichas")
        self.assertEqual(
            [opcao.label for opcao in view.seletor.options],
            list(PASTAS_FICHAS_REMOVIVEIS),
        )
        self.assertIn("Criaturas", PASTAS_FICHAS_REMOVIVEIS)
        self.assertTrue(all(opcao.emoji is not None for opcao in view.seletor.options))

    def test_itens_usam_faixas_alfabeticas_fixas(self):
        def item(nome: str) -> ItemRemovivel:
            return ItemRemovivel(
                Path(f"{nome}.md"),
                f"feitiços/Duelos/{nome}.md",
                nome,
                nome,
                "Duelos",
                "Duelos",
                "1º Ano",
            )

        paginas = paginas_itens_removiveis([item("Arthur"), item("Zelda")])
        self.assertEqual(
            [rotulo for rotulo, _ in paginas],
            ["AB", "CD", "EF", "GH", "IJ", "KL", "MN", "OP", "QR", "ST", "UV", "WXYZ"],
        )
        self.assertEqual([registro.nome for registro in paginas[0][1]], ["Arthur"])
        self.assertEqual([registro.nome for registro in paginas[-1][1]], ["Zelda"])

    def test_classifica_ficha_de_personagem(self):
        item = classificar_item(PASTA_BIBLIOTECA / "fichas" / "Corvinal" / "Ollie White.md")
        self.assertEqual(item.categoria, "Fichas")
        self.assertEqual(item.identificador, "fichas/Corvinal/Ollie White.md")

    def test_classifica_habilidade(self):
        item = classificar_item(
            PASTA_BIBLIOTECA / "Habilidades" / "Herança Sanguínea" / "Meio-Sangue.md"
        )
        self.assertEqual(item.categoria, "Herança Sanguínea")
        self.assertEqual(item.secao_thread, "Habilidades")

    def test_nao_oferece_configuracoes_de_ficha(self):
        identificadores = [item.identificador for item in listar_itens_removiveis()]
        self.assertFalse(any(valor.startswith("fichas/configurações/") for valor in identificadores))


if __name__ == "__main__":
    unittest.main()
