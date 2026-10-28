import unittest

from comandos.ficha import (
    DescricaoFeiticoFichaModal,
    exemplo_descricao_feitico,
    listar_categorias_feiticos_ficha,
    listar_feiticos_ficha,
)


class FeiticosDaFichaTests(unittest.TestCase):
    def test_seletor_inclui_runas_e_bindrunes(self):
        categorias = listar_categorias_feiticos_ficha()
        self.assertIn("Runas Antigas", categorias)
        self.assertIn("Bindrunes", categorias)

    def test_runas_e_bindrunes_sao_lidas_das_bibliotecas_corretas(self):
        runas = listar_feiticos_ficha("Runas Antigas")
        bindrunes = listar_feiticos_ficha("Bindrunes")
        self.assertTrue(runas)
        self.assertTrue(bindrunes)
        self.assertTrue(all(item.categoria == "Runas Antigas" for item in runas))
        self.assertTrue(all(item.categoria == "Bindrunes" for item in bindrunes))
        self.assertTrue(all("runas" in item.caminho.parts for item in runas))
        self.assertTrue(all("bindrunes" in item.caminho.parts for item in bindrunes))

    def test_descricao_guia_usa_descricao_do_feitico_e_capacidade_da_runa(self):
        feitico = listar_feiticos_ficha("Defesa contra arte das trevas")[0]
        runa = next(
            item
            for item in listar_feiticos_ficha("Runas Antigas")
            if item.nome == "ᛉ Algiz"
        )

        self.assertNotEqual(exemplo_descricao_feitico(feitico), feitico.nome)
        self.assertIn("permite", exemplo_descricao_feitico(runa).casefold())
        modal = DescricaoFeiticoFichaModal(1, runa.caminho, runa, "")
        self.assertEqual(modal.descricao.default, exemplo_descricao_feitico(runa))
        self.assertEqual(modal.descricao.max_length, 1024)


if __name__ == "__main__":
    unittest.main()
