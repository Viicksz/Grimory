import asyncio
import unittest

from comandos.ficha_criaturas import (
    ACOES,
    ATAQUES,
    DESCRICOES_ATAQUES,
    ROLAGENS_ATAQUE,
    AtaqueModal,
    ConfiguracaoAtaqueView,
    item_ataque_preset,
)
from utils.fichas_criaturas import FichaCriatura


class FluxoAtaqueCriaturaTests(unittest.TestCase):
    def setUp(self):
        self.ficha = FichaCriatura(
            "Criatura de teste",
            "Fera",
            "X",
            "1,5 m",
            "De 1 m a 2 m",
        )

    def ficha_preset(self):
        ficha = FichaCriatura(
            "Criatura de preset",
            "Fera",
            "XXX",
            "5 m",
            "De 4 m a 5 m",
        )
        ficha.atributos["Força"] = 16
        ficha.atributos["Destreza"] = 14
        return ficha

    def test_acao_e_rolagem_sao_menus_separados(self):
        async def validar():
            view = ConfiguracaoAtaqueView(1, self.ficha, "Derrubar")
            self.assertEqual(
                [opcao.value for opcao in view.acao_select.options],
                list(ACOES),
            )
            self.assertEqual(
                [opcao.value for opcao in view.rolagem_select.options],
                list(ROLAGENS_ATAQUE),
            )

        asyncio.run(validar())

    def test_modal_contem_apenas_detalhes_textuais(self):
        async def validar():
            modal = AtaqueModal(
                1,
                self.ficha,
                "Derrubar",
                "Padrão",
                "Atletismo",
            )
            self.assertEqual(len(modal.children), 3)
            self.assertEqual(
                [campo.label for campo in modal.children],
                ["Nome", "Dano ou efeito", "Descrição mecânica"],
            )

        asyncio.run(validar())

    def test_ordem_e_descricoes_dos_presets(self):
        self.assertEqual(
            ATAQUES,
            (
                "Emboscada", "Bote", "Investida", "Derrubar", "Arremesso",
                "Pisotear", "Varredura", "Coice", "Agarrão", "Constrição",
                "Ataques Múltiplos", "Ataque Venenoso", "Ataque Ácido", "Personalizado",
            ),
        )
        self.assertTrue(all(DESCRICOES_ATAQUES[nome] for nome in ATAQUES))

    def test_presets_usam_campos_na_ordem_aprovada(self):
        item = item_ataque_preset(self.ficha_preset(), "Derrubar")
        self.assertEqual(
            list(item),
            [
                "nome", "descrição", "tipo de ação", "rolagem de ataque",
                "dano ou efeito", "teste de resistência", "duração", "recarga",
            ],
        )

    def test_calculos_dos_presets(self):
        ficha = self.ficha_preset()
        natural = {"nome": "Garras", "categoria": "Armas Naturais", "dano": "1d12+Força"}
        marcial = {"nome": "Espada Longa", "categoria": "Armas Marciais", "dano": "1d8+Destreza"}

        self.assertIn("+ 6 de dano bônus", item_ataque_preset(ficha, "Bote", arma=marcial)["dano ou efeito"])
        self.assertIn("+ 1d10 de dano bônus", item_ataque_preset(ficha, "Investida", arma=marcial)["dano ou efeito"])

        derrubar = item_ataque_preset(ficha, "Derrubar")
        self.assertEqual(derrubar["tipo de ação"], "Completa")
        self.assertEqual(derrubar["teste de resistência"], "Fortitude contra CD 14.")
        self.assertEqual(derrubar["duração"], "1 rodada")

        self.assertTrue(item_ataque_preset(ficha, "Arremesso")["dano ou efeito"].startswith("8 de dano concussivo"))
        self.assertTrue(item_ataque_preset(ficha, "Pisotear", patas=4)["dano ou efeito"].startswith("4d8+3"))
        self.assertEqual(item_ataque_preset(ficha, "Varredura", arma=natural)["dano ou efeito"], "1d12+3 (Força)")
        self.assertEqual(item_ataque_preset(ficha, "Coice")["dano ou efeito"], "2d12+6 (Força ×2)")

        agarrar = item_ataque_preset(ficha, "Agarrão")
        self.assertIn("Ação de Movimento", agarrar["dano ou efeito"])
        self.assertEqual(agarrar["duração"], "Até escapar")
        self.assertTrue(item_ataque_preset(ficha, "Constrição")["dano ou efeito"].startswith("9 de dano"))

        multiplos = item_ataque_preset(ficha, "Ataques Múltiplos", arma=natural)
        self.assertIn("Até 4 golpes", multiplos["dano ou efeito"])
        self.assertIn("separadas", multiplos["dano ou efeito"])

        venenoso = item_ataque_preset(ficha, "Ataque Venenoso", arma=natural, rolagem_variavel="Luta")
        self.assertIn("+ 6 de dano venenoso", venenoso["dano ou efeito"])
        self.assertIn("+3 de dano venenoso por turno", venenoso["dano ou efeito"])
        self.assertIn("sem acumular", venenoso["dano ou efeito"])
        self.assertEqual(venenoso["duração"], "2 turnos")
        self.assertEqual(venenoso["recarga"], "3 rodada(s)")


if __name__ == "__main__":
    unittest.main()
