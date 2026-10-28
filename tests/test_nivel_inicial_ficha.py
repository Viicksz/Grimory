import unittest

from comandos.ficha import (
    NIVEL_INICIAL_MAXIMO,
    NIVEL_INICIAL_MINIMO,
    pontos_criacao_por_nivel,
    pv_ph_criacao_por_nivel,
)


class NivelInicialFichaTests(unittest.TestCase):
    def test_niveis_de_um_a_dez_sao_aceitos(self) -> None:
        self.assertEqual(NIVEL_INICIAL_MINIMO, 1)
        self.assertEqual(NIVEL_INICIAL_MAXIMO, 10)
        self.assertEqual(pontos_criacao_por_nivel(1), 14)
        self.assertEqual(pontos_criacao_por_nivel(7), 26)
        self.assertEqual(pontos_criacao_por_nivel(10), 32)

    def test_nivel_fora_do_intervalo_e_rejeitado(self) -> None:
        with self.assertRaises(ValueError):
            pontos_criacao_por_nivel(0)
        with self.assertRaises(ValueError):
            pontos_criacao_por_nivel(11)

    def test_nivel_sete_do_jonatha_resulta_em_82_pv(self) -> None:
        pv, ph = pv_ph_criacao_por_nivel(
            nivel=7,
            constituicao=18,
            sabedoria=12,
        )
        self.assertEqual(pv, 82)
        self.assertEqual(ph, 24)


if __name__ == "__main__":
    unittest.main()
