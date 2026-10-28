from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from comandos.passagem_ano import PassagemAno, embed_vagas_quadribol
from utils.fichas import FichaPersonagem, salvar_ficha
from utils.passagem_ano import (
    MudancaFicha,
    PreviaPassagemAno,
    aplicar_passagem_ficha,
    avancar_ano,
    executar_passagem_ano,
    preparar_passagem_ano,
)
from utils.taca import AcontecimentoTaca, EstadoTaca, carregar_estado_taca, salvar_estado_taca


def aluno(nome: str, grupo: str = "Grifinória", ano: str = "4°Ano") -> FichaPersonagem:
    return FichaPersonagem(
        nome=nome,
        grupo=grupo,
        casa="Grifinória",
        heranca="Humano",
        nucleo="Pena de Fênix",
        nivel=4,
        pv=30,
        ph=10,
        atributos={
            "Força": 10,
            "Destreza": 10,
            "Constituição": 14,
            "Inteligência": 10,
            "Sabedoria": 12,
            "Carisma": 10,
        },
        informacoes=[
            {"titulo": "Cursando", "descricao": ano},
            {"titulo": "Altura e Idade", "descricao": "1,70 com 15 Anos"},
        ],
    )


class PassagemAnoTests(unittest.TestCase):
    def test_avanca_anos_e_conclui_o_setimo(self) -> None:
        self.assertEqual(avancar_ano("4°Ano"), "5°Ano")
        self.assertEqual(avancar_ano("7º Ano"), "Ensino Completo")
        self.assertEqual(avancar_ano("Completo"), "Ensino Completo")
        self.assertEqual(avancar_ano("Ensino Completo"), "Ensino Completo")

    def test_aluno_envelhece_e_recebe_progressao_mecanica(self) -> None:
        ficha = aluno("Amber")
        mudanca = aplicar_passagem_ficha(ficha)
        self.assertEqual((mudanca.ano_anterior, mudanca.ano_novo), ("4°Ano", "5°Ano"))
        self.assertEqual(mudanca.idade_nova, "1,70 com 16 Anos")
        self.assertEqual(ficha.nivel, 5)
        self.assertEqual(ficha.pontos_atributo_disponiveis, 2)
        self.assertEqual(ficha.pv, 37)
        self.assertEqual(ficha.ph, 13)

    def test_formatura_remove_vinculo_com_time_mas_preserva_vassoura(self) -> None:
        ficha = aluno("Apanhadora", grupo="Lufa-Lufa", ano="7°Ano")
        ficha.informacoes.extend(
            [
                {"titulo": "Jogador de Quadribol", "descricao": "Apanhador"},
                {"titulo": "Situação no time", "descricao": "Titular"},
            ]
        )
        ficha.itens.append(
            {
                "categoria": "Variados",
                "nome": "Nimbus 2000",
                "quantidade": "1",
                "tipo": "Vassoura",
                "equipada": "Sim",
            }
        )

        mudanca = aplicar_passagem_ficha(ficha)

        self.assertEqual(mudanca.posicao_quadribol, "Apanhador")
        self.assertEqual(mudanca.situacao_time, "Titular")
        self.assertFalse(
            any(
                item["titulo"] in {"Jogador de Quadribol", "Situação no time"}
                for item in ficha.informacoes
            )
        )
        self.assertEqual(ficha.itens[0]["nome"], "Nimbus 2000")
        self.assertEqual(ficha.itens[0]["equipada"], "Sim")

    def test_autoridade_sobe_nivel_sem_progressao_academica(self) -> None:
        ficha = aluno("Minerva", grupo="Figuras de Autoridade")
        ficha.informacoes = []
        mudanca = aplicar_passagem_ficha(ficha)
        self.assertFalse(mudanca.aluno)
        self.assertEqual(ficha.nivel, 5)
        self.assertEqual(ficha.informacoes, [])

    def test_execucao_salva_backup_e_reinicia_taca(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            ficha_1 = raiz / "Amber.md"
            ficha_2 = raiz / "Jonatha.md"
            salvar_ficha(aluno("Amber"), ficha_1, nova=True)
            salvar_ficha(aluno("Jonatha", grupo="Lufa-Lufa", ano="7°Ano"), ficha_2, nova=True)
            taca = raiz / "Taca.md"
            salvar_estado_taca(
                EstadoTaca(
                    pontuacoes={"Grifinória": 30, "Sonserina": 140, "Lufa-Lufa": 102, "Corvinal": 145},
                    historico=[
                        AcontecimentoTaca("id", "gratificacao", "Minerva", "Amber", "Grifinória", 5, "teste", 1, "agora")
                    ],
                ),
                taca,
            )
            previa = preparar_passagem_ano([ficha_1, ficha_2], taca)
            backup = executar_passagem_ano(previa, caminho_taca=taca, pasta_backups=raiz / "backups")
            self.assertTrue((backup / "resumo.json").is_file())
            self.assertEqual(FichaPersonagem.carregar(ficha_1).nivel, 5)
            concluinte = FichaPersonagem.carregar(ficha_2)
            self.assertEqual(concluinte.informacoes[0]["descricao"], "Ensino Completo")
            self.assertEqual(concluinte.ano, "Ensino Completo")
            self.assertEqual(concluinte.grupo, "NPCs")
            estado = carregar_estado_taca(taca)
            self.assertEqual(set(estado.pontuacoes.values()), {0})
            self.assertEqual(estado.historico, [])


class MigracaoDiscordConcluinteTests(unittest.IsolatedAsyncioTestCase):
    async def test_move_ficha_e_narrativa_para_npcs_e_remove_time(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "NPCs" / "Concluinte.md"
            ficha = aluno("Concluinte", grupo="Lufa-Lufa", ano="7°Ano")
            ficha.casa = "Lufa-Lufa"
            aplicar_passagem_ficha(ficha)
            ficha.mensagem_discord_id = 7001
            ficha.mensagem_discord_parte_2_id = 7002
            ficha.mensagem_narrativa_discord_id = 7003
            ficha.mensagem_time_discord_id = 7004
            salvar_ficha(ficha, caminho, nova=True)
            mudanca = MudancaFicha(
                caminho=Path(pasta) / "Lufa-Lufa" / "Concluinte.md",
                caminho_novo=caminho,
                nome="Concluinte",
                grupo="Lufa-Lufa",
                grupo_novo="NPCs",
                nivel_anterior=4,
                nivel_novo=5,
                idade_anterior="1,70 com 15 Anos",
                idade_nova="1,70 com 16 Anos",
                ano_anterior="7°Ano",
                ano_novo="Ensino Completo",
            )
            previa = PreviaPassagemAno("token", (mudanca,), {}, 0)
            entrada_npc = SimpleNamespace(
                tipo="npc",
                pronta=True,
                destino_id=1533249207165648916,
                embeds=[],
                conteudo="NPC",
                anexos=[],
            )
            exclusao = AsyncMock()
            publicar_ficha = AsyncMock(
                return_value=(SimpleNamespace(id=9001), None, None)
            )
            publicar_narrativa = AsyncMock(return_value=SimpleNamespace(id=9002))
            with (
                patch("comandos.passagem_ano.excluir_publicacao_ficha", exclusao),
                patch(
                    "comandos.passagem_ano.publicar_personagem_em_partes",
                    publicar_ficha,
                ),
                patch(
                    "comandos.passagem_ano.montar_entradas_ficha",
                    return_value=[entrada_npc],
                ),
                patch(
                    "comandos.passagem_ano.publicar_ou_atualizar_ficha",
                    publicar_narrativa,
                ),
            ):
                falhas = await PassagemAno(SimpleNamespace()).sincronizar_mensagens(
                    previa
                )

            self.assertEqual(falhas, [])
            destinos_excluidos = {
                (chamada.args[1], chamada.args[2])
                for chamada in exclusao.await_args_list
                if chamada.args[2]
            }
            self.assertIn((1289388326473830460, 7001), destinos_excluidos)
            self.assertIn((1289388326473830460, 7002), destinos_excluidos)
            self.assertIn((1124928017374908438, 7003), destinos_excluidos)
            self.assertIn((1124946495301496982, 7004), destinos_excluidos)
            atual = FichaPersonagem.carregar(caminho)
            self.assertEqual(atual.grupo, "NPCs")
            self.assertEqual(atual.mensagem_discord_id, 9001)
            self.assertEqual(atual.mensagem_narrativa_discord_id, 9002)
            self.assertEqual(atual.mensagem_time_discord_id, 0)

    def test_token_impede_confirmar_previa_desatualizada(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            caminho = raiz / "Amber.md"
            salvar_ficha(aluno("Amber"), caminho, nova=True)
            taca = raiz / "Taca.md"
            salvar_estado_taca(EstadoTaca(), taca)
            previa = preparar_passagem_ano([caminho], taca)
            ficha = FichaPersonagem.carregar(caminho)
            ficha.xp += 1
            salvar_ficha(ficha, caminho)
            with self.assertRaisesRegex(ValueError, "mudaram depois da prévia"):
                executar_passagem_ano(previa, caminho_taca=taca, pasta_backups=raiz / "backups")

    def test_concluinte_e_movido_da_casa_para_pasta_de_npcs(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            pasta_fichas = raiz / "fichas"
            origem = pasta_fichas / "Lufa-Lufa" / "Concluinte.md"
            origem.parent.mkdir(parents=True)
            salvar_ficha(
                aluno("Concluinte", grupo="Lufa-Lufa", ano="7°Ano"),
                origem,
                nova=True,
            )
            taca = raiz / "Taca.md"
            salvar_estado_taca(EstadoTaca(), taca)

            previa = preparar_passagem_ano(
                [origem],
                taca,
                pasta_fichas=pasta_fichas,
            )
            destino = pasta_fichas / "NPCs" / "Concluinte.md"
            self.assertEqual(previa.concluintes[0].caminho_novo, destino)

            executar_passagem_ano(
                previa,
                caminho_taca=taca,
                pasta_backups=raiz / "backups",
            )

            self.assertFalse(origem.exists())
            self.assertTrue(destino.is_file())
            concluinte = FichaPersonagem.carregar(destino)
            self.assertEqual(concluinte.grupo, "NPCs")
            self.assertEqual(concluinte.ano, "Ensino Completo")

    def test_anuncio_agrupa_vagas_por_casa_posicao_e_situacao(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            mudancas: list[MudancaFicha] = []
            for indice, nome in enumerate(("Formando A", "Formando B")):
                caminho = raiz / f"{nome}.md"
                ficha = aluno(nome, grupo="Grifinória", ano="7°Ano")
                ficha.informacoes.extend(
                    [
                        {
                            "titulo": "Jogador de Quadribol",
                            "descricao": "Apanhador",
                        },
                        {"titulo": "Situação no time", "descricao": "Titular"},
                    ]
                )
                aplicar_passagem_ficha(ficha)
                salvar_ficha(ficha, caminho, nova=True)
                mudancas.append(
                    MudancaFicha(
                        caminho=raiz / "Grifinória" / f"{nome}.md",
                        caminho_novo=caminho,
                        nome=nome,
                        grupo="Grifinória",
                        grupo_novo="NPCs",
                        nivel_anterior=4,
                        nivel_novo=5,
                        ano_anterior="7°Ano",
                        ano_novo="Ensino Completo",
                        posicao_quadribol="Apanhador",
                        situacao_time="Titular",
                    )
                )

            embed = embed_vagas_quadribol(
                PreviaPassagemAno("token", tuple(mudancas), {}, 0)
            )

            self.assertIsNotNone(embed)
            assert embed is not None
            self.assertEqual(embed.title, "🏏 NOVAS VAGAS PARA JOGADORES DE QUADRIBOL")
            self.assertEqual(len(embed.fields), 1)
            self.assertEqual(embed.fields[0].name, "❤️ Grifinória")
            self.assertIn("**Apanhador — Titular** — 2 vagas", embed.fields[0].value)
            self.assertIn("**Formando A**", embed.fields[0].value)
            self.assertIn("**Formando B**", embed.fields[0].value)


if __name__ == "__main__":
    unittest.main()
