import unittest

from pathlib import Path

from comandos.ficha_criaturas import (
    GRUPOS_ALFABETICOS_CRIATURAS,
    paginas_criaturas_alfabeticas,
)
from utils.fichas_criaturas import ReferenciaCriatura
from utils.fichas import (
    ATRIBUTOS_POR_PERICIA,
    GRUPOS_ALFABETICOS_FICHAS,
    PERICIAS,
    ReferenciaFicha,
    paginas_fichas_alfabeticas,
    paginas_pericias,
)


class PaginacaoFichasTests(unittest.TestCase):
    def test_fichas_usam_as_doze_faixas_alfabeticas_fixas(self):
        itens = [
            ReferenciaFicha("Arthur", "NPCs", Path("Arthur.md")),
            ReferenciaFicha("Minerva", "NPCs", Path("Minerva.md")),
            ReferenciaFicha("Zelda", "NPCs", Path("Zelda.md")),
        ]
        paginas = paginas_fichas_alfabeticas(itens)
        self.assertEqual(
            [rotulo for rotulo, _ in paginas],
            list(GRUPOS_ALFABETICOS_FICHAS),
        )
        self.assertEqual([item.nome for item in paginas[0][1]], ["Arthur"])
        self.assertEqual([item.nome for item in paginas[6][1]], ["Minerva"])
        self.assertEqual([item.nome for item in paginas[-1][1]], ["Zelda"])

    def test_faixa_de_fichas_com_mais_de_25_cria_subpaginas(self):
        itens = [
            ReferenciaFicha(
                f"Autoridade {indice:02d}",
                "Figuras de Autoridade",
                Path(f"{indice}.md"),
            )
            for indice in range(26)
        ]
        paginas = paginas_fichas_alfabeticas(itens)
        self.assertEqual(paginas[0][0], "AB — 1/2")
        self.assertEqual(paginas[1][0], "AB — 2/2")
        self.assertEqual(len(paginas[0][1]), 25)
        self.assertEqual(len(paginas[1][1]), 1)

    def test_pericias_sao_separadas_pelos_tres_pares_de_atributos(self):
        paginas = paginas_pericias()
        self.assertEqual(
            [rotulo for rotulo, _ in paginas],
            [
                "Força e Destreza",
                "Inteligência e Sabedoria",
                "Carisma e Constituição",
            ],
        )
        agrupadas = [pericia for _, pericias in paginas for pericia in pericias]
        self.assertEqual(agrupadas, list(PERICIAS))
        self.assertEqual(len(agrupadas), len(set(agrupadas)))

    def test_cada_pericia_pertence_aos_atributos_da_pagina(self):
        atributos_por_rotulo = {
            "Força e Destreza": {"Força", "Destreza"},
            "Inteligência e Sabedoria": {"Inteligência", "Sabedoria"},
            "Carisma e Constituição": {"Carisma", "Constituição"},
        }
        for rotulo, pericias in paginas_pericias():
            for pericia in pericias:
                self.assertTrue(
                    atributos_por_rotulo[rotulo].intersection(ATRIBUTOS_POR_PERICIA[pericia])
                )

    def test_paginas_de_criaturas_mantem_nove_grupos_fixos(self):
        itens = [
            ReferenciaCriatura("Acromântula", "XXX", "Fera", Path("A.md")),
            ReferenciaCriatura("Dragão", "XXXXX", "Fera", Path("D.md")),
            ReferenciaCriatura("Pixie", "X", "Fera", Path("P.md")),
        ]
        paginas = paginas_criaturas_alfabeticas(itens)
        self.assertEqual([rotulo for rotulo, _ in paginas], list(GRUPOS_ALFABETICOS_CRIATURAS))
        self.assertEqual([item.nome for item in paginas[0][1]], ["Acromântula"])
        self.assertEqual([item.nome for item in paginas[1][1]], ["Dragão"])
        self.assertEqual([item.nome for item in paginas[7][1]], ["Pixie"])
        self.assertEqual(paginas[-1][1], [])

    def test_grupo_alfabetico_com_mais_de_25_itens_cria_subpaginas(self):
        itens = [
            ReferenciaCriatura(f"Animal {indice:02d}", "X", "Fera", Path(f"{indice}.md"))
            for indice in range(26)
        ]
        paginas = paginas_criaturas_alfabeticas(itens)
        self.assertEqual(paginas[0][0], "AB — 1/2")
        self.assertEqual(paginas[1][0], "AB — 2/2")
        self.assertEqual(len(paginas[0][1]), 25)
        self.assertEqual(len(paginas[1][1]), 1)


if __name__ == "__main__":
    unittest.main()
