from __future__ import annotations

import tempfile
import unittest
import inspect
from pathlib import Path
from unittest.mock import patch

from comandos.xp import (
    CATEGORIAS_LIVRES,
    CategoriasXPView,
    DestinoXP,
    OpcoesHerancaXPView,
    OpcoesDestinoXPView,
    PastasFichaXPView,
    XP,
    destino_pertence_ao_usuario,
    paginas_destinos_xp,
    custo_catalisador,
    reduzir_cd_em_um_nivel,
    validar_valor_variavel,
)
from utils.fichas import FichaPersonagem
from utils.xp import (
    ContaXP,
    caminho_nova_conta_xp,
    encontrar_conta_do_titular,
    encontrar_conta_xp,
    listar_contas_xp,
    salvar_conta_xp,
)


class ContaXPTests(unittest.TestCase):
    def test_salva_carrega_e_localiza_conta(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            with patch("utils.xp.PASTA_CONTAS_XP", pasta):
                caminho = caminho_nova_conta_xp("Reserva de Luna")
                salvar_conta_xp(ContaXP("Reserva de Luna", 123, 25), caminho, nova=True)

                carregada = ContaXP.carregar(caminho)
                self.assertEqual(carregada, ContaXP("Reserva de Luna", 123, 25))
                self.assertEqual(encontrar_conta_xp("reserva de luna").caminho, caminho)
                self.assertEqual(encontrar_conta_do_titular(123).nome, "Reserva de Luna")
                self.assertEqual(len(listar_contas_xp("Luna")), 1)

    def test_rejeita_nome_de_arquivo_invalido(self) -> None:
        with self.assertRaises(ValueError):
            caminho_nova_conta_xp("Conta/Insegura")

    def test_ficha_preserva_titular_do_discord(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "Luna.md"
            ficha = FichaPersonagem(
                nome="Luna",
                grupo="Players",
                casa="Corvinal",
                heranca="Sangue Puro",
                nucleo="Penas de Fênix",
                titular_id=456,
            )
            caminho.write_text(ficha.markdown(), encoding="utf-8")

            self.assertEqual(FichaPersonagem.carregar(caminho).titular_id, 456)
            destino = DestinoXP("Ficha", "Luna", caminho)
            self.assertTrue(destino_pertence_ao_usuario(destino, 456))
            self.assertFalse(destino_pertence_ao_usuario(destino, 999))


class ValorXPTests(unittest.TestCase):
    def test_comando_xp_abre_menu_sem_parametros_no_slash(self) -> None:
        parametros = inspect.signature(XP.xp.callback).parameters
        self.assertEqual(list(parametros), ["self", "interaction"])

    def test_menu_de_xp_move_critico_para_heranca(self) -> None:
        view = CategoriasXPView(XP(None), 123, False)
        valores = [opcao.value for opcao in view.seletor.options]
        self.assertEqual(valores, ["heranca", "aula_treino"])
        self.assertNotIn("critico", valores)

    def test_opcoes_de_destino_antecedem_a_navegacao(self) -> None:
        with patch("comandos.xp.listar_destinos_xp", return_value=[]):
            view = OpcoesDestinoXPView(XP(None), 123, "critico", False)
        self.assertEqual(view.seletor.placeholder, "Opções de Destino")
        self.assertEqual(
            [opcao.label for opcao in view.seletor.options],
            ["Fichas", "Banco de XP"],
        )

    def test_fichas_sao_separadas_pelas_pastas_da_biblioteca(self) -> None:
        with patch("comandos.xp.listar_destinos_xp", return_value=[]):
            view = PastasFichaXPView(XP(None), 123, "critico", False)
        self.assertEqual(view.seletor.placeholder, "Pastas de Fichas")
        self.assertEqual(
            [opcao.label for opcao in view.seletor.options],
            [
                "Players",
                "NPCs",
                "Grifinória",
                "Sonserina",
                "Lufa-Lufa",
                "Corvinal",
                "Figuras de Autoridade",
            ],
        )
        self.assertTrue(all(opcao.emoji is not None for opcao in view.seletor.options))

    def test_destinos_usam_faixas_alfabeticas_fixas(self) -> None:
        destinos = [
            DestinoXP("Ficha", "Arthur", Path("Arthur.md")),
            DestinoXP("Banco de XP", "Zelda", Path("Zelda.md")),
        ]
        paginas = paginas_destinos_xp(destinos)
        self.assertEqual(
            [rotulo for rotulo, _ in paginas],
            ["AB", "CD", "EF", "GH", "IJ", "KL", "MN", "OP", "QR", "ST", "UV", "WXYZ"],
        )
        self.assertEqual([item.nome for item in paginas[0][1]], ["Arthur"])
        self.assertEqual([item.nome for item in paginas[-1][1]], ["Zelda"])

    def test_categorias_livres_para_jogadores(self) -> None:
        self.assertEqual(CATEGORIAS_LIVRES, {"heranca", "aula_treino"})

    def test_catalisador_custa_cinco_ou_dez_e_reduz_cd(self) -> None:
        self.assertEqual(custo_catalisador("Intermediário IV"), 5)
        self.assertEqual(custo_catalisador("Avançado VI"), 10)
        with self.assertRaisesRegex(ValueError, "Básicos"):
            custo_catalisador("Básico II")
        self.assertEqual(reduzir_cd_em_um_nivel(20), 18)
        self.assertEqual(reduzir_cd_em_um_nivel(13), 12)

    def test_banco_de_xp_desbloqueia_todas_as_opcoes_de_heranca(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "Reserva.md"
            salvar_conta_xp(ContaXP("Reserva", 123, 50), caminho, nova=True)
            destino = DestinoXP("Banco de XP", "Reserva", caminho)
            view = OpcoesHerancaXPView(XP(None), 123, destino, False)
        self.assertEqual(
            [opcao.value for opcao in view.seletor.options],
            [
                "evento_critico",
                "evento_maestria",
                "evento_trouxa",
                "atributo",
                "reducao_dificuldade",
                "catalisador_temporario",
                "especializacao",
            ],
        )

    def test_cada_ficha_recebe_a_ultima_evolucao_da_propria_linhagem(self) -> None:
        esperados = {
            "Meio-Sangue": "catalisador_temporario",
            "Sangue Puro": "reducao_dificuldade",
            "Nascido-Trouxa": "especializacao",
        }
        with tempfile.TemporaryDirectory() as temporario:
            for heranca, esperado in esperados.items():
                caminho = Path(temporario) / f"{heranca}.md"
                caminho.write_text(
                    FichaPersonagem(
                        nome=heranca,
                        grupo="Players",
                        casa="Corvinal",
                        heranca=heranca,
                        nucleo="Penas de Fênix",
                        titular_id=123,
                        evolucao_heranca=5,
                    ).markdown(),
                    encoding="utf-8",
                )
                view = OpcoesHerancaXPView(
                    XP(None),
                    123,
                    DestinoXP("Ficha", heranca, caminho),
                    False,
                )
                valores = [opcao.value for opcao in view.seletor.options]
                self.assertIn(esperado, valores)
                self.assertEqual(
                    [valor for valor in valores if valor in esperados.values()],
                    [esperado],
                )

    def test_minimos(self) -> None:
        self.assertEqual(validar_valor_variavel("side_quest", "20"), 20)
        self.assertEqual(validar_valor_variavel("arco_campanha", "100"), 100)
        self.assertEqual(validar_valor_variavel("credito", "1"), 1)
        self.assertEqual(validar_valor_variavel("debito", "15"), 15)

    def test_rejeita_valor_abaixo_do_minimo(self) -> None:
        for categoria, valor in (("side_quest", "19"), ("arco_campanha", "99"), ("debito", "0")):
            with self.subTest(categoria=categoria), self.assertRaises(ValueError):
                validar_valor_variavel(categoria, valor)

    def test_debito_nao_aceita_simbolo(self) -> None:
        for valor in ("-10", "+10", "10 XP", "1,5"):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                validar_valor_variavel("debito", valor)



if __name__ == "__main__":
    unittest.main()
