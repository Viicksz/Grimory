import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import discord

from comandos.habilidades import listar_habilidades
from utils.fichas import FichaPersonagem
from utils.fichas_criaturas import FichaCriatura
from utils.publicacao_fichas import (
    cabecalho_criatura,
    cabecalho_personagem,
    cabecalho_personagem_parte_2,
    destino_criatura,
    destino_personagem,
    publicar_ou_atualizar_ficha,
)
from comandos.ficha import (
    _adicionar_campo_efeito,
    _fragmentar_embed_de_ficha,
    dividir_embeds_publicacao_personagem,
    montar_embeds_ficha,
    publicar_personagem_em_partes,
)


class MensagemFalsa:
    def __init__(self, identificador: int):
        self.id = identificador
        self.edicoes = []
        self.excluida = False

    async def edit(self, **dados):
        self.edicoes.append(dados)

    async def delete(self):
        self.excluida = True


class CanalFalso:
    def __init__(self):
        self.mensagens = {}
        self.envios = []

    async def fetch_message(self, identificador: int):
        return self.mensagens[identificador]

    async def send(self, **dados):
        mensagem = MensagemFalsa(9001 + len(self.envios))
        self.mensagens[mensagem.id] = mensagem
        self.envios.append(dados)
        return mensagem


class ClienteFalso:
    def __init__(self, canal):
        self.canal = canal

    def get_channel(self, identificador):
        return self.canal


class PublicacaoFichasTests(unittest.IsolatedAsyncioTestCase):
    def test_destinos_por_grupo(self):
        self.assertEqual(destino_personagem("Corvinal"), 1289388383210307645)
        self.assertEqual(destino_personagem("Lufa-Lufa"), 1289388326473830460)
        self.assertEqual(destino_personagem("Grifinória"), 1289388242730487890)
        self.assertEqual(destino_personagem("Sonserina"), 1289388434284347392)
        self.assertEqual(destino_personagem("NPCs"), 1289388691114164319)
        self.assertEqual(destino_personagem("Players"), 1532236479999508480)
        self.assertEqual(destino_criatura(), 1532236686078119986)

    def test_cabecalhos_identificam_tipo_e_categoria(self):
        personagem = cabecalho_personagem("Ollie White", "Corvinal")
        criatura = cabecalho_criatura("Pixie", "XXXX")
        self.assertIn("## Ollie White", personagem)
        self.assertIn("_Ficha de Personagem • Corvinal_", personagem)
        self.assertIn("## Pixie", criatura)
        self.assertIn("_Ficha de Criatura • XXXX_", criatura)
        self.assertEqual(cabecalho_personagem_parte_2("Ollie White"), "")

    def test_markdown_preserva_id_da_publicacao(self):
        personagem = FichaPersonagem("Teste", "Players", "--", "Meio-Sangue", "Penas de Fênix")
        personagem.mensagem_discord_id = 123456789012345678
        personagem.mensagem_discord_parte_2_id = 223456789012345678
        personagem.mensagem_narrativa_discord_id = 323456789012345678
        personagem.mensagem_time_discord_id = 423456789012345678
        criatura = FichaCriatura("Fera", "Fera", "X", "1 m", "De 1 m a 2 m")
        criatura.mensagem_discord_id = 223456789012345678
        with tempfile.TemporaryDirectory() as pasta:
            caminho_personagem = Path(pasta) / "Personagem.md"
            caminho_criatura = Path(pasta) / "X" / "Criatura.md"
            caminho_criatura.parent.mkdir()
            caminho_personagem.write_text(personagem.markdown(), encoding="utf-8")
            caminho_criatura.write_text(criatura.markdown(), encoding="utf-8")
            self.assertEqual(FichaPersonagem.carregar(caminho_personagem).mensagem_discord_id, 123456789012345678)
            self.assertEqual(
                FichaPersonagem.carregar(caminho_personagem).mensagem_discord_parte_2_id,
                223456789012345678,
            )
            self.assertEqual(FichaPersonagem.carregar(caminho_personagem).mensagem_narrativa_discord_id, 323456789012345678)
            self.assertEqual(FichaPersonagem.carregar(caminho_personagem).mensagem_time_discord_id, 423456789012345678)
            self.assertEqual(FichaCriatura.carregar(caminho_criatura).mensagem_discord_id, 223456789012345678)

    async def test_publica_uma_vez_e_depois_edita_a_mesma_mensagem(self):
        canal = CanalFalso()
        cliente = ClienteFalso(canal)
        embeds = [discord.Embed(title="Ficha")]
        criada = await publicar_ou_atualizar_ficha(cliente, 1, embeds, conteudo="Cabeçalho")
        atualizada = await publicar_ou_atualizar_ficha(cliente, 1, embeds, criada.id, "Cabeçalho novo")
        self.assertIs(criada, atualizada)
        self.assertEqual(len(canal.envios), 1)
        self.assertEqual(len(criada.edicoes), 1)
        self.assertEqual(canal.envios[0]["content"], "Cabeçalho")
        self.assertEqual(criada.edicoes[0]["content"], "Cabeçalho novo")

    def test_ficha_longa_mantem_identidade_informacoes_e_itens_juntos(self):
        ficha = FichaPersonagem("Ollie", "Corvinal", "Corvinal", "Meio-Sangue", "Penas de Fênix")
        embeds = [
            discord.Embed(title="Identidade", description="A" * 3500),
            discord.Embed(title="🎒 Itens", description="I" * 900),
            discord.Embed(title="💡 Habilidades", description="B" * 900),
            discord.Embed(title="🪄 Feitiços", description="C" * 900),
        ]
        with patch("comandos.ficha.montar_embeds_ficha", return_value=embeds):
            principal, parte_2, parte_3 = dividir_embeds_publicacao_personagem(ficha)
        self.assertEqual(
            [embed.title for embed in principal],
            ["Identidade", "🎒 Itens"],
        )
        self.assertEqual(
            [embed.title for embed in parte_2],
            ["💡 Habilidades", "🪄 Feitiços"],
        )
        self.assertEqual(parte_3, [])

    async def test_publica_parte_2_logo_apos_a_principal(self):
        canal = CanalFalso()
        cliente = ClienteFalso(canal)
        ficha = FichaPersonagem("Ollie", "Corvinal", "Corvinal", "Meio-Sangue", "Penas de Fênix")
        partes = (
            [discord.Embed(title="Identidade")],
            [discord.Embed(title="💡 Habilidades")],
            [],
        )
        with patch("comandos.ficha.dividir_embeds_publicacao_personagem", return_value=partes):
            principal, parte_2, parte_3 = await publicar_personagem_em_partes(cliente, ficha)
        self.assertEqual(principal.id, 9001)
        self.assertEqual(parte_2.id, 9002)
        self.assertIsNone(parte_3)
        self.assertEqual(canal.envios[1]["content"], "")

    def test_bloco_inferior_grande_quebra_no_ponto_mais_equilibrado(self):
        ficha = FichaPersonagem("Ollie", "Corvinal", "Corvinal", "Meio-Sangue", "Penas de Fênix")
        embeds = [
            discord.Embed(title="Identidade", description="A" * 1000),
            discord.Embed(title="🎒 Itens", description="I" * 900),
            discord.Embed(title="💡 Habilidades", description="B" * 3500),
            discord.Embed(title="🪄 Feitiços", description="C" * 3800),
        ]
        with patch("comandos.ficha.montar_embeds_ficha", return_value=embeds):
            principal, parte_2, parte_3 = dividir_embeds_publicacao_personagem(ficha)
        self.assertEqual(
            [embed.title for embed in principal],
            ["Identidade", "🎒 Itens", "💡 Habilidades"],
        )
        self.assertEqual([embed.title for embed in parte_2], ["🪄 Feitiços"])
        self.assertEqual(parte_3, [])

    def test_quebras_priorizam_os_quatro_blocos_naturais(self):
        ficha = FichaPersonagem("Ollie", "Corvinal", "Corvinal", "Meio-Sangue", "Penas de Fênix")
        embeds = [
            discord.Embed(description="I" * 2200),
            discord.Embed(title="📋 Informações", description="I" * 900),
            discord.Embed(title="🎒 Itens", description="I" * 900),
            discord.Embed(title="📊 Estatísticas", description="E" * 1300),
            discord.Embed(title="📌 Atributos", description="A" * 1300),
            discord.Embed(title="📌 Perícias", description="P" * 1300),
            discord.Embed(title="📖 Aptidões", description="A" * 700),
            discord.Embed(title="💡 Habilidades", description="H" * 2300),
            discord.Embed(title="🪄 Feitiços", description="F" * 2500),
        ]
        with patch("comandos.ficha.montar_embeds_ficha", return_value=embeds):
            principal, parte_2, parte_3 = dividir_embeds_publicacao_personagem(ficha)
        self.assertEqual(
            [embed.title for embed in principal],
            [None, "📋 Informações", "🎒 Itens"],
        )
        self.assertEqual(
            [embed.title for embed in parte_2],
            ["📊 Estatísticas", "📌 Atributos", "📌 Perícias"],
        )
        self.assertEqual(
            [embed.title for embed in parte_3],
            ["📖 Aptidões", "💡 Habilidades", "🪄 Feitiços"],
        )

    def test_feiticos_e_itens_grandes_sao_fragmentados_sem_continuacao(self):
        for titulo in ("🪄 Feitiços", "🎒 Itens"):
            embed = discord.Embed(title=titulo)
            for indice in range(8):
                embed.add_field(
                    name=f"Item {indice}",
                    value="X" * 900,
                    inline=False,
                )
            partes = _fragmentar_embed_de_ficha(embed)
            self.assertGreater(len(partes), 1)
            self.assertTrue(all(parte.title == titulo for parte in partes))
            self.assertTrue(all("continuação" not in (parte.title or "") for parte in partes))
            self.assertTrue(all(len(parte) <= 5900 for parte in partes))

    def test_habilidade_longa_repete_titulo_sem_continuacao(self):
        embed = discord.Embed(title="💡 Habilidades")
        _adicionar_campo_efeito(embed, "✨ Fitometria", "Texto " * 300)
        self.assertGreater(len(embed.fields), 1)
        self.assertEqual(
            {campo.name for campo in embed.fields},
            {"✨ Fitometria"},
        )
        self.assertTrue(
            all(campo.value.startswith("> ") for campo in embed.fields)
        )
        self.assertTrue(all(len(campo.value) <= 1024 for campo in embed.fields))

    def test_descricao_multilinha_da_habilidade_cita_todas_as_linhas(self):
        embed = discord.Embed(title="💡 Habilidades")
        _adicionar_campo_efeito(
            embed,
            "✨ Fitometria",
            "Passivo: primeira linha.\n2ph: segunda linha.",
        )
        self.assertEqual(
            embed.fields[0].value,
            "> Passivo: primeira linha.\n> 2ph: segunda linha.",
        )

    def test_descricao_de_habilidade_nao_cria_citacao_soltas(self):
        embed = discord.Embed(title="💡 Habilidades")
        _adicionar_campo_efeito(
            embed,
            "✨ Clarividência — Clareza — 2ph",
            "Primeiro parágrafo.\n\nSegundo parágrafo.",
        )
        self.assertEqual(
            embed.fields[0].value,
            "> Primeiro parágrafo.\n> Segundo parágrafo.",
        )
        self.assertNotIn(">\n", embed.fields[0].value)

    def test_origem_magica_separa_subhabilidades_e_custos_com_travessao(self):
        ficha = FichaPersonagem(
            "Fitometria Teste",
            "Players",
            "Corvinal",
            "Meio-Sangue",
            "Penas de Fênix",
            origens_magicas=["Fitometria"],
        )
        habilidades = next(
            embed
            for embed in montar_embeds_ficha(ficha)
            if embed.title == "💡 Habilidades"
        )
        campos = {campo.name: campo.value for campo in habilidades.fields}
        self.assertIn("✨ Fitometria — Passivo", campos)
        self.assertIn("✨ Fitometria — Detecção Sensorial — 2ph", campos)
        self.assertIn(
            "✨ Fitometria — Memória Compartilhada — Estágio Inicial — 4ph",
            campos,
        )
        self.assertIn(
            "✨ Fitometria — Memória Compartilhada — Estágio Avançado — 6ph",
            campos,
        )
        self.assertTrue(all(valor.startswith("> ") for valor in campos.values()))
        self.assertNotIn("//", "\n".join(campos))

    def test_todas_as_origens_magicas_usam_fields_sem_citacoes_soltas(self):
        for origem in listar_habilidades("origem_magica", limite=None):
            ficha = FichaPersonagem(
                f"Teste {origem}",
                "Players",
                "Corvinal",
                "Meio-Sangue",
                "Penas de Fênix",
                origens_magicas=[origem],
            )
            campos = [
                campo
                for embed in montar_embeds_ficha(ficha)
                if embed.title == "💡 Habilidades"
                for campo in embed.fields
                if campo.name.startswith(f"✨ {origem} —")
            ]
            self.assertTrue(campos, origem)
            self.assertTrue(all("//" not in campo.name for campo in campos), origem)
            self.assertTrue(
                all(
                    all(linha.strip() != ">" for linha in campo.value.splitlines())
                    for campo in campos
                ),
                origem,
            )

    def test_descricoes_de_habilidade_comecam_com_maiuscula(self):
        embed = discord.Embed(title="💡 Habilidades")
        _adicionar_campo_efeito(
            embed,
            "🧬 Meio-Sangue — Primeira Evolução — Passivo",
            "ganha 2 XP.\ntem custo reduzido.\n2ph: mantém o custo minúsculo.",
        )
        self.assertEqual(
            embed.fields[0].value,
            "> Ganha 2 XP.\n> Tem custo reduzido.\n> 2ph: mantém o custo minúsculo.",
        )

    async def test_remove_parte_2_quando_ficha_volta_a_caber_em_uma_mensagem(self):
        canal = CanalFalso()
        cliente = ClienteFalso(canal)
        ficha = FichaPersonagem("Ollie", "Corvinal", "Corvinal", "Meio-Sangue", "Penas de Fênix")
        ficha.mensagem_discord_id = 7001
        ficha.mensagem_discord_parte_2_id = 7002
        canal.mensagens[7001] = MensagemFalsa(7001)
        canal.mensagens[7002] = MensagemFalsa(7002)
        partes = ([discord.Embed(title="Identidade")], [], [])
        with patch("comandos.ficha.dividir_embeds_publicacao_personagem", return_value=partes):
            _, parte_2, parte_3 = await publicar_personagem_em_partes(cliente, ficha)
        self.assertIsNone(parte_2)
        self.assertIsNone(parte_3)
        self.assertTrue(canal.mensagens[7002].excluida)


if __name__ == "__main__":
    unittest.main()
