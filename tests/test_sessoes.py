from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from comandos.narrativa import (
    Narrativa,
    cabecalho_narrativo,
    criar_embed_participante,
    evento_mais_proximo,
    inteiro_recurso,
    posicao_calendario,
)
from utils.fichas import FichaPersonagem, salvar_ficha
from utils.sessoes import (
    RespostaEncerramento,
    encerramento_ativo,
    novo_encerramento,
    salvar_encerramento,
    ultimo_encerramento_concluido,
)


class CalendarioNarrativoTests(unittest.TestCase):
    def test_cabecalho_narrativo_usa_padrao_ornamental_do_grimory(self) -> None:
        cabecalho = cabecalho_narrativo("Última Sessão")
        self.assertEqual(
            cabecalho,
            "## ══════◄••📖••►══════\n"
            "## Última Sessão\n"
            "## ══════◄••📖••►══════",
        )

    def test_posicao_respeita_estacoes_semanas_e_dias(self) -> None:
        self.assertEqual(posicao_calendario("outono", 1, "segunda"), 0)
        self.assertEqual(posicao_calendario("inverno", 2, "quarta"), 37)
        self.assertEqual(posicao_calendario("verao", 4, "quinta"), 122)

    def test_evento_do_mesmo_dia(self) -> None:
        evento, mesmo_dia = evento_mais_proximo("outono", 4, "domingo")
        self.assertTrue(mesmo_dia)
        self.assertEqual(evento.nome, "Halloween")

    def test_empate_prefere_evento_futuro(self) -> None:
        evento, mesmo_dia = evento_mais_proximo("outono", 1, "quinta")
        self.assertFalse(mesmo_dia)
        self.assertEqual(evento.nome, "Festa de boas-vindas das snakes")


class PersistenciaEncerramentoTests(unittest.TestCase):
    def test_salva_recarrega_e_localiza_ultima_sessao(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            with patch("utils.sessoes.PASTA_SESSOES", pasta):
                encerramento = novo_encerramento(10, 20, 30, [(40, "Luna Lovegood")])
                resposta = RespostaEncerramento(
                    estacao="primavera",
                    semana=4,
                    dia="domingo",
                    hora=9,
                    minuto=35,
                    periodo="PM",
                    local="Torre de Astronomia",
                    acao="Observava as estrelas.",
                    objetivo="Investigar um presságio.",
                    atualizado_por=40,
                    atualizado_em="2026-07-30T12:00:00+00:00",
                    pv=18,
                    ph=4,
                    ficha="Corvinal/Luna Lovegood.md",
                )
                encerramento.participantes[40].resposta = resposta
                salvar_encerramento(encerramento)

                ativo = encerramento_ativo(10)
                self.assertIsNotNone(ativo)
                self.assertEqual(ativo.participantes[40].nome, "Luna Lovegood")
                self.assertEqual(ativo.participantes[40].resposta.local, "Torre de Astronomia")
                self.assertEqual(ativo.participantes[40].resposta.pv, 18)
                self.assertEqual(ativo.participantes[40].resposta.ph, 4)
                self.assertEqual(ativo.participantes[40].resposta.ficha, "Corvinal/Luna Lovegood.md")

                encerramento.concluido = True
                encerramento.concluido_em = "2026-07-30T12:05:00+00:00"
                salvar_encerramento(encerramento)
                self.assertIsNone(encerramento_ativo(10))
                self.assertEqual(ultimo_encerramento_concluido(10).identificador, encerramento.identificador)

    def test_carrega_encerramento_antigo_sem_pv_e_ph(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            with patch("utils.sessoes.PASTA_SESSOES", pasta):
                encerramento = novo_encerramento(10, 20, 30, [(40, "Luna Lovegood")])
                resposta = RespostaEncerramento(
                    estacao="outono",
                    semana=1,
                    dia="segunda",
                    hora=8,
                    minuto=0,
                    periodo="AM",
                    local="Salão Principal",
                    acao="Tomava café.",
                    objetivo="Ir para a aula.",
                    atualizado_por=40,
                    atualizado_em="2026-08-08T12:00:00+00:00",
                )
                encerramento.participantes[40].resposta = resposta
                caminho = salvar_encerramento(encerramento)
                carregado = type(encerramento).carregar(caminho)
                self.assertIsNone(carregado.participantes[40].resposta.pv)
                self.assertIsNone(carregado.participantes[40].resposta.ph)
                self.assertEqual(carregado.participantes[40].resposta.ficha, "")

    def test_embed_mostra_pv_e_ph_quando_informados(self) -> None:
        encerramento = novo_encerramento(10, 20, 30, [(40, "Luna Lovegood")])
        encerramento.participantes[40].resposta = RespostaEncerramento(
            estacao="outono",
            semana=1,
            dia="segunda",
            hora=8,
            minuto=0,
            periodo="AM",
            local="Salão Principal",
            acao="Tomava café.",
            objetivo="Ir para a aula.",
            atualizado_por=40,
            atualizado_em="2026-08-08T12:00:00+00:00",
            pv=18,
            ph=4,
        )
        embed = criar_embed_participante(encerramento, 40)
        campos = {campo.name: campo.value for campo in embed.fields}
        self.assertEqual(campos["❤️ PV"], "18")
        self.assertEqual(campos["✨ PH"], "4")

    def test_pv_aceita_negativo_e_ph_nao(self) -> None:
        self.assertEqual(inteiro_recurso("0", "PV"), 0)
        self.assertEqual(inteiro_recurso(" 12 ", "PH"), 12)
        self.assertIsNone(inteiro_recurso("", "PV"))
        self.assertEqual(inteiro_recurso("-4", "PV", permitir_negativo=True), -4)
        with self.assertRaisesRegex(ValueError, "PH"):
            inteiro_recurso("-1", "PH")
        with self.assertRaisesRegex(ValueError, "PH"):
            inteiro_recurso("dois", "PH")

    def test_pv_negativo_marca_personagem_como_morrendo(self) -> None:
        encerramento = novo_encerramento(10, 20, 30, [(40, "Luna Lovegood")])
        encerramento.participantes[40].resposta = RespostaEncerramento(
            estacao="outono",
            semana=1,
            dia="segunda",
            hora=8,
            minuto=0,
            periodo="AM",
            local="Enfermaria",
            acao="Recebia atendimento.",
            objetivo="Sobreviver.",
            atualizado_por=40,
            atualizado_em="2026-08-08T12:00:00+00:00",
            pv=-3,
            ph=0,
        )
        embed = criar_embed_participante(encerramento, 40)
        self.assertEqual(embed.title, "(morrendo) Luna Lovegood — Última Sessão")


class AtualizacaoRecursosEncerramentoTests(unittest.IsolatedAsyncioTestCase):
    async def test_salvar_resposta_atualiza_pv_ph_da_ficha_vinculada(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            pasta_fichas = raiz / "fichas"
            pasta_sessoes = raiz / "sessoes"
            caminho_ficha = pasta_fichas / "Corvinal" / "Luna Lovegood.md"
            ficha = FichaPersonagem(
                nome="Luna Lovegood",
                grupo="Corvinal",
                casa="Corvinal",
                heranca="Meio-Sangue",
                nucleo="Pena de Fênix",
                titular_id=40,
                pv=30,
                ph=10,
            )
            with (
                patch("utils.fichas.PASTA_FICHAS", pasta_fichas),
                patch("comandos.narrativa.PASTA_FICHAS", pasta_fichas),
                patch("utils.sessoes.PASTA_SESSOES", pasta_sessoes),
            ):
                salvar_ficha(ficha, caminho_ficha, nova=True)
                encerramento = novo_encerramento(10, 20, 30, [(40, "Luna Lovegood")])
                salvar_encerramento(encerramento)
                resposta = RespostaEncerramento(
                    estacao="outono",
                    semana=1,
                    dia="segunda",
                    hora=8,
                    minuto=0,
                    periodo="AM",
                    local="Salão Principal",
                    acao="Tomava café.",
                    objetivo="Ir para a aula.",
                    atualizado_por=40,
                    atualizado_em="2026-08-08T12:00:00+00:00",
                    pv=17,
                    ph=3,
                )
                cog = Narrativa(SimpleNamespace())
                cog.atualizar_mensagens = AsyncMock()
                interaction = SimpleNamespace(
                    user=SimpleNamespace(id=40),
                    permissions=SimpleNamespace(manage_guild=False),
                    client=SimpleNamespace(),
                )
                with patch(
                    "comandos.ficha.sincronizar_publicacao_personagem",
                    new=AsyncMock(),
                ) as sincronizar:
                    atualizada = await cog.salvar_resposta(
                        encerramento.identificador,
                        40,
                        interaction,
                        resposta,
                    )

                self.assertTrue(atualizada)
                carregada = FichaPersonagem.carregar(caminho_ficha)
                self.assertEqual((carregada.pv, carregada.ph), (17, 3))
                self.assertEqual(resposta.ficha, "Corvinal/Luna Lovegood.md")
                sincronizar.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
