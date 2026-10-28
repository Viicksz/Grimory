import unittest

from comandos.ficha import ATRIBUTO_MINIMO_PERSONAGEM, PONTOS_ATRIBUTO_INICIAIS
from utils.fichas import modificador


class AtributosPersonagemTests(unittest.TestCase):
    def test_personagem_pode_ter_atributo_abaixo_de_dez(self):
        self.assertEqual(ATRIBUTO_MINIMO_PERSONAGEM, 4)
        self.assertEqual(modificador(9), -1)
        self.assertEqual(modificador(4), -3)

    def test_distribuicao_inicial_continua_com_quatorze_pontos(self):
        self.assertEqual(PONTOS_ATRIBUTO_INICIAIS, 14)


if __name__ == "__main__":
    unittest.main()
