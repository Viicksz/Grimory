import unittest

from comandos.ajuda import CATEGORIAS_AJUDA, embed_categoria, embed_inicial


class AjudaTests(unittest.TestCase):
    def test_categorias_e_comandos_esperados(self):
        categorias = {categoria.chave: categoria for categoria in CATEGORIAS_AJUDA}
        self.assertEqual(
            set(categorias),
            {"consultas", "dados", "fichas", "xp", "inventario", "combate", "quadribol", "taca", "narrativa", "biblioteca"},
        )

        usos = {
            comando.uso
            for categoria in CATEGORIAS_AJUDA
            for comando in categoria.comandos
        }
        self.assertEqual(len(usos), 28)
        self.assertIn("/xp", usos)
        self.assertIn("/gringots", usos)
        self.assertIn("/ficha", usos)
        self.assertNotIn("/ficha criatura criar", usos)
        self.assertIn("/quadribol", usos)
        self.assertIn("/manobras", usos)
        self.assertIn("/combate", usos)
        self.assertIn("/guardar", usos)
        self.assertIn("/bolcetinha", usos)
        self.assertIn("/loot origem:", usos)
        self.assertIn("/executar nome:", usos)
        self.assertIn("/passagem-de-ano", usos)
        self.assertIn("/revisar-feiticos", usos)
        revisar = next(
            comando
            for comando in categorias["biblioteca"].comandos
            if comando.uso == "/revisar-feiticos"
        )
        self.assertTrue(revisar.administrativo)
        self.assertEqual(
            [comando.uso for comando in categorias["consultas"].comandos],
            [
                "/habilidade categoria: nome:",
                "/interagir criatura:",
                "/preparar nome:",
                "/executar nome:",
            ],
        )
        self.assertEqual(
            [comando.uso for comando in categorias["dados"].comandos],
            ["/rolar dado:"],
        )

    def test_uma_embed_valida_por_categoria(self):
        for categoria in CATEGORIAS_AJUDA:
            embed = embed_categoria(categoria)
            self.assertEqual(len(embed.fields), len(categoria.comandos))
            self.assertLessEqual(len(embed), 6000)
            self.assertIn(categoria.nome, embed.title)

    def test_painel_inicial_lista_todas_as_categorias(self):
        embed = embed_inicial()
        self.assertEqual(len(embed.fields), len(CATEGORIAS_AJUDA))
        for campo, categoria in zip(embed.fields, CATEGORIAS_AJUDA):
            self.assertIn(categoria.nome, campo.name)
            self.assertEqual(campo.value, f"*{categoria.resumo}*")
        self.assertLessEqual(len(embed), 6000)


if __name__ == "__main__":
    unittest.main()
