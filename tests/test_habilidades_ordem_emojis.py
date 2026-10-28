import unittest

from comandos.habilidades import (
    EMOJIS_HABILIDADES,
    ORDEM_HABILIDADES,
    formatar_cabecalho_habilidade,
    listar_habilidades,
)


class HabilidadesOrdemEmojisTests(unittest.TestCase):
    def test_biblioteca_respeita_ordem_configurada(self):
        for categoria, ordem in ORDEM_HABILIDADES.items():
            self.assertEqual(listar_habilidades(categoria, limite=None), list(ordem))

    def test_todas_as_habilidades_possuem_emoji(self):
        for categoria, ordem in ORDEM_HABILIDADES.items():
            self.assertEqual(set(EMOJIS_HABILIDADES[categoria]), set(ordem))

    def test_blocos_que_devem_permanecer_juntos(self):
        self.assertEqual(
            ORDEM_HABILIDADES["heranca_sanguinea"][-3:],
            ("Nascido-Trouxa", "Meio-Sangue", "Sangue Puro"),
        )
        especializacoes = ORDEM_HABILIDADES["especializacao"]
        indice_rei = especializacoes.index("Rei")
        self.assertEqual(
            especializacoes[indice_rei:indice_rei + 3],
            ("Rei", "Poeta // Artista", "Soldado"),
        )

    def test_cabecalho_usa_emoji_individual_e_sem_espaco_no_separador(self):
        cabecalho = formatar_cabecalho_habilidade("Meio-Sangue", "heranca_sanguinea")
        self.assertIn("## <:Halfblood:992497097997820067>🧬 Meio-Sangue", cabecalho)
        self.assertTrue(cabecalho.startswith("## ══════◄••🧬••►══════"))
        self.assertIn("_Linhagem Sanguínea_", cabecalho)


if __name__ == "__main__":
    unittest.main()
