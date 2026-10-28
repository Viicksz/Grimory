from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import discord

from comandos.ficha import (
    FichaAtualView,
    GerenciarCombateNPCView,
    HabilidadeNPCWizardView,
    RECARGAS_HABILIDADE_NPC,
    SessaoFicha,
    aplicar_modo_custo_habilidade_npc,
    atualizar_efeito_habilidade_npc,
    bonus_escolha_habilidade_npc,
    ficha_da_sessao,
    gravar_registro_combate_npc,
    montar_embeds_ficha,
)
from utils.fichas import ATRIBUTOS, FichaPersonagem
from utils.combate import EQUIPE_ALIADOS, ReferenciaCombatente, participante_da_referencia


class FichasNPCsTests(unittest.TestCase):
    def sessao(self, tipo: str) -> SessaoFicha:
        return SessaoFicha(
            usuario_id=123,
            nome="NPC de teste",
            grupo="NPCs",
            tipo_npc=tipo,
            nivel=3,
            tamanho_npc="1,78 m",
            faixa_tamanho_npc="De 1 m a 2 m",
            anos_pos_vida=12,
            atributos={
                "Força": 14,
                "Destreza": 16,
                "Constituição": 12,
                "Inteligência": 10,
                "Sabedoria": 14,
                "Carisma": 8,
            },
            pericias_livres=["Reflexo", "Vontade"],
        )

    def test_humano_usa_progressao_por_nivel_e_ph_normal(self) -> None:
        ficha = ficha_da_sessao(self.sessao("Humano/Trouxa"))

        self.assertEqual(ficha.pv, 34)
        self.assertEqual(ficha.ph, 15)
        self.assertEqual(ficha.alma, 100)
        self.assertEqual(ficha.pericias["Reflexo"], 2)
        self.assertTrue(all(valor == 0 for valor in ficha.aptidoes.values()))

    def test_espirito_mantem_todos_os_atributos_e_usa_alma(self) -> None:
        ficha = ficha_da_sessao(self.sessao("Espírito"))

        self.assertEqual(tuple(ficha.atributos), ATRIBUTOS)
        self.assertEqual(ficha.atributos["Força"], 14)
        self.assertEqual(ficha.atributos["Destreza"], 16)
        self.assertEqual(ficha.atributos["Constituição"], 12)
        self.assertEqual(ficha.pv, 0)
        self.assertEqual(ficha.alma, 100)
        self.assertEqual(ficha.ph, 15)
        self.assertEqual(ficha.manifestacao_paranormal, 12)
        self.assertEqual(
            [item["nome"] for item in ficha.habilidades_npc],
            ["Intangibilidade — Passivo", "Manifestação Paranormal — Passivo"],
        )

    def test_dados_de_espirito_sobrevivem_ao_markdown_e_aparecem_na_consulta(self) -> None:
        ficha = ficha_da_sessao(self.sessao("Espírito"))
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Espirito.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            recarregada = FichaPersonagem.carregar(caminho)

        self.assertEqual(recarregada.tipo_npc, "Espírito")
        self.assertEqual(recarregada.anos_pos_vida, 12)
        self.assertEqual(recarregada.manifestacao_paranormal, 12)
        self.assertEqual(len(recarregada.habilidades_npc), 2)
        embeds = montar_embeds_ficha(recarregada)
        titulos = [embed.title for embed in embeds]
        self.assertIn("📊 Estatísticas", titulos)
        self.assertIn("💡 Habilidades", titulos)
        self.assertNotIn("📖 Aptidões", titulos)
        estatisticas = next(embed for embed in embeds if embed.title == "📊 Estatísticas")
        self.assertEqual([campo.name for campo in estatisticas.fields], ["Pontos de Habilidade", "Alma"])

    def test_espirito_entra_em_combate_com_alma_como_recurso_de_vida(self) -> None:
        ficha = ficha_da_sessao(self.sessao("Espírito"))
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Espirito.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            referencia = ReferenciaCombatente("NPC de teste", "personagem", "NPCs", caminho)
            participante = participante_da_referencia(referencia, EQUIPE_ALIADOS, 0)

        self.assertEqual(participante.recurso_vida, "Alma")
        self.assertEqual(participante.pv_maximo, 100)
        self.assertEqual(participante.ph_maximo, 15)

    def test_botao_de_habilidades_fica_na_segunda_linha(self) -> None:
        ficha = ficha_da_sessao(self.sessao("Humano/Trouxa"))
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Humano.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            view = FichaAtualView(123, caminho)

        botao = next(
            item
            for item in view.children
            if isinstance(item, discord.ui.Button) and item.label == "Habilidades"
        )
        self.assertEqual(botao.row, 1)
        self.assertEqual(str(botao.emoji), "✨")
        botoes_terceira_linha = {
            item.label
            for item in view.children
            if isinstance(item, discord.ui.Button) and item.row == 2
        }
        self.assertEqual(
            botoes_terceira_linha,
            {"Imagem", "Info", "Modificar Info"},
        )
        linhas_renderizadas = [
            [componente.get("label") for componente in linha["components"]]
            for linha in view.to_components()
        ]
        self.assertEqual(
            linhas_renderizadas,
            [
                ["Mercado de XP"],
                ["Armas", "Ataques", "Habilidades"],
                ["Imagem", "Info", "Modificar Info"],
                ["Item", "Modificar Item"],
            ],
        )

    def test_npc_alternativo_gerencia_armas_e_ataques(self) -> None:
        ficha = ficha_da_sessao(self.sessao("Semi-Humano"))
        ficha.armas_npc.append({"nome": "Garras"})
        ficha.ataques_npc.append({"nome": "Bote"})
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Semi-humano.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            armas = GerenciarCombateNPCView(123, caminho, "arma")
            ataques = GerenciarCombateNPCView(123, caminho, "ataque")

        for view in (armas, ataques):
            self.assertEqual(
                [item.label for item in view.children],
                ["Adicionar", "Modificar", "Remover", "Voltar à ficha"],
            )
            self.assertFalse(view.children[1].disabled)
            self.assertFalse(view.children[2].disabled)

    def test_registros_de_combate_npc_persistem_e_podem_ser_substituidos(self) -> None:
        ficha = ficha_da_sessao(self.sessao("Humano/Trouxa"))
        ficha.armas_npc.append({"nome": "Cajado", "dano": "1d6"})
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Humano.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            original = dict(ficha.armas_npc[0])
            atualizada = asyncio.run(
                gravar_registro_combate_npc(
                    caminho,
                    "arma",
                    {"nome": "Cajado", "dano": "1d8"},
                    0,
                    original,
                )
            )

        self.assertEqual(len(atualizada.armas_npc), 1)
        self.assertEqual(atualizada.armas_npc[0]["dano"], "1d8")

    def test_criador_npc_usa_recarga_sem_periculosidade_e_dez_dados(self) -> None:
        ficha = ficha_da_sessao(self.sessao("Semi-Humano"))
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Semi-humano.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            alcance = HabilidadeNPCWizardView(123, caminho, {}, etapa=1)
            efeito = HabilidadeNPCWizardView(123, caminho, {}, etapa=5)

        self.assertEqual(
            [opcao.value for opcao in alcance.seletores_etapa["recarga"].options],
            list(RECARGAS_HABILIDADE_NPC),
        )
        self.assertEqual([opcao.value for opcao in efeito.numero.options], [str(n) for n in range(1, 11)])

    def test_criador_npc_pede_modo_antes_do_valor_em_ph(self) -> None:
        ficha = ficha_da_sessao(self.sessao("Humano/Trouxa"))
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Humano.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            inicial = HabilidadeNPCWizardView(123, caminho, {}, etapa=2)
            cobrada = HabilidadeNPCWizardView(
                123,
                caminho,
                {"modo de custo": "Ativação", "custo de PH": "4"},
                etapa=2,
            )
            gratuita = HabilidadeNPCWizardView(
                123,
                caminho,
                {"modo de custo": "Sem Custo", "custo de PH": "0"},
                etapa=2,
            )

        self.assertEqual(inicial.children[0].placeholder, "Modo de Custo")
        self.assertIsNone(inicial.custo)
        self.assertEqual(cobrada.children[0].placeholder, "Modo de Custo")
        self.assertEqual(cobrada.children[1].placeholder, "Custo de PH")
        self.assertIsNone(gratuita.custo)

    def test_sem_custo_npc_define_zero_ph_automaticamente(self) -> None:
        item = {"modo de custo": "Sem Custo", "custo de PH": "10"}
        aplicar_modo_custo_habilidade_npc(item)
        self.assertEqual(item["custo de PH"], "0")
        self.assertEqual(item["mecânica de custo"], "Sem custo de PH.")

    def test_efeito_direto_usa_nivel_e_bonus_escolhido(self) -> None:
        ficha = ficha_da_sessao(self.sessao("Humano/Trouxa"))
        item = {
            "rolagem de reação": "Efeito Direto",
            "dado de efeito": "d8",
            "número de dados": "2",
        }

        atualizar_efeito_habilidade_npc(ficha, item, "Carisma")

        self.assertEqual(bonus_escolha_habilidade_npc(ficha, "Carisma"), -1)
        self.assertEqual(item["efeito calculado"], "2d8-1 (Carisma)")
        self.assertEqual(item["CD do efeito"], "10")


if __name__ == "__main__":
    unittest.main()
