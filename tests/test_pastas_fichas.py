import unittest
from unittest.mock import patch

from comandos.combate import SelecionarOrigemCombateView
from comandos.ficha import (
    ConsultaCategoriaFichaView,
    MenuPastaFichaView,
    SessaoFicha,
    TitularPlayerView,
    ficha_da_sessao,
)
from comandos.inventario import PastaInventarioView
from utils.fichas import EMOJIS_PASTAS_FICHA, GRUPOS_FICHA, ORDEM_PASTAS_FICHA


class PastasFichaIdentificacaoTests(unittest.TestCase):
    def test_player_exige_seletor_e_preserva_titular_escolhido(self) -> None:
        sessao = SessaoFicha(
            usuario_id=10,
            titular_id=467140579260891147,
            nome="Player Teste",
            grupo="Players",
        )
        view = TitularPlayerView(sessao)
        self.assertEqual(len(view.children), 1)
        self.assertEqual(view.children[0].placeholder, "Selecione o titular da ficha")
        self.assertEqual(ficha_da_sessao(sessao).titular_id, 467140579260891147)

    def test_ordem_e_emojis_oficiais_das_pastas(self) -> None:
        self.assertEqual(
            ORDEM_PASTAS_FICHA,
            (
                "Players",
                "NPCs",
                "Grifinória",
                "Sonserina",
                "Lufa-Lufa",
                "Corvinal",
                "Criaturas",
                "Figuras de Autoridade",
            ),
        )
        self.assertEqual(
            EMOJIS_PASTAS_FICHA,
            {
                "Players": "👤",
                "NPCs": "👥",
                "Grifinória": "❤️",
                "Sonserina": "💚",
                "Lufa-Lufa": "💛",
                "Corvinal": "💙",
                "Criaturas": "🦇",
                "Figuras de Autoridade": "📋",
            },
        )
        self.assertEqual(
            GRUPOS_FICHA,
            tuple(pasta for pasta in ORDEM_PASTAS_FICHA if pasta != "Criaturas"),
        )

    def test_fluxos_de_pastas_preservam_ordem_e_emojis(self) -> None:
        with patch("comandos.inventario.listar_fichas", return_value=[]):
            inventario = PastaInventarioView(1, False, "guardar")
        with patch("comandos.ficha.listar_fichas", return_value=[]):
            consulta = ConsultaCategoriaFichaView(1)
        menu = MenuPastaFichaView(1, "consultar")
        with patch("comandos.combate._referencias_da_origem", return_value=[]):
            combate = SelecionarOrigemCombateView(None, 1, "teste", "Aliados")

        for view, ordem in (
            (inventario, GRUPOS_FICHA),
            (consulta, GRUPOS_FICHA),
            (menu, ORDEM_PASTAS_FICHA),
            (combate, ORDEM_PASTAS_FICHA),
        ):
            seletor = view.children[0]
            self.assertEqual([opcao.label for opcao in seletor.options], list(ordem))
            self.assertEqual(
                [opcao.emoji.name for opcao in seletor.options],
                [EMOJIS_PASTAS_FICHA[pasta] for pasta in ordem],
            )


if __name__ == "__main__":
    unittest.main()
