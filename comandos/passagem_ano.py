from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from comandos.ficha import publicar_personagem_em_partes
from utils.fichas import FichaPersonagem, salvar_ficha
from utils.passagem_ano import PreviaPassagemAno, executar_passagem_ano, preparar_passagem_ano
from utils.publicacao_narrativa import (
    destino_narrativo_grupo,
    destino_time,
    montar_entradas_ficha,
)
from utils.publicacao_fichas import (
    ErroPublicacaoFicha,
    destino_personagem,
    excluir_publicacao_ficha,
    publicar_ou_atualizar_ficha,
)
from utils.quadribol import POSICOES, obter_informacao
from utils.taca import CANAL_PROFETA_DIARIO_ID, CASAS, CORACOES_CASAS


COR_PASSAGEM = 0x4F8A5B
COR_QUADRIBOL = 0x7A5C1E


def embed_vagas_quadribol(previa: PreviaPassagemAno) -> discord.Embed | None:
    vagas: dict[str, dict[tuple[str, str], list[str]]] = {}
    for mudanca in previa.concluintes:
        ficha = FichaPersonagem.carregar(mudanca.caminho_atual)
        casa = mudanca.grupo if mudanca.grupo in CASAS else ficha.casa
        posicao = mudanca.posicao_quadribol or obter_informacao(
            ficha, "Jogador de Quadribol"
        )
        if casa not in CASAS or posicao not in POSICOES:
            continue
        situacao = (
            mudanca.situacao_time
            or obter_informacao(ficha, "Situação no time")
            or "Titular"
        )
        vagas.setdefault(casa, {}).setdefault((posicao, situacao), []).append(
            ficha.nome
        )
    if not vagas:
        return None

    embed = discord.Embed(
        title="🏏 NOVAS VAGAS PARA JOGADORES DE QUADRIBOL",
        description=(
            "Com a conclusão do ano letivo, novas posições ficaram disponíveis "
            "nas equipes de Quadribol de Hogwarts."
        ),
        color=COR_QUADRIBOL,
    )
    ordem_posicoes = {posicao: indice for indice, posicao in enumerate(POSICOES)}
    ordem_situacoes = {"Titular": 0, "Reserva": 1}
    for casa in CASAS:
        vagas_casa = vagas.get(casa)
        if not vagas_casa:
            continue
        linhas: list[str] = []
        for (posicao, situacao), nomes in sorted(
            vagas_casa.items(),
            key=lambda item: (
                ordem_posicoes.get(item[0][0], len(POSICOES)),
                ordem_situacoes.get(item[0][1], 2),
            ),
        ):
            quantidade = len(nomes)
            rotulo_vaga = "1 vaga" if quantidade == 1 else f"{quantidade} vagas"
            linhas.append(f"» **{posicao} — {situacao}** — {rotulo_vaga}")
            formandos = ", ".join(f"**{nome}**" for nome in nomes)
            linhas.append(f"Vaga liberada após a formatura de {formandos}.")
        embed.add_field(
            name=f"{CORACOES_CASAS[casa]} {casa}",
            value="\n".join(linhas),
            inline=False,
        )
    embed.set_footer(text="Profeta Diário • Esportes")
    return embed


def embed_previa_passagem(previa: PreviaPassagemAno) -> discord.Embed:
    pontuacao = "\n".join(
        f"> **{casa}:** {pontos} pontos → 0"
        for casa, pontos in previa.pontuacoes_taca.items()
    )
    concluintes = ", ".join(item.nome for item in previa.concluintes) or "Nenhum"
    embed = discord.Embed(
        title="Prévia — Passagem de Ano",
        description=(
            "Esta operação altera todas as fichas de personagem e reinicia a Taça das Casas. "
            "Uma cópia de segurança será criada antes da confirmação."
        ),
        color=COR_PASSAGEM,
    )
    embed.add_field(
        name="Progressão acadêmica",
        value=(
            f"**{len(previa.alunos)} alunos** receberão +1 ano de idade e avançarão em Cursando.\n"
            f"**Conclusão do 7º Ano:** {concluintes}\n"
            "Concluintes serão marcados como **Ensino Completo** e movidos para as publicações de NPCs."
        ),
        inline=False,
    )
    embed.add_field(
        name="Progressão mecânica",
        value=(
            f"**{len(previa.mudancas)} fichas:** Nível +1, +2 pontos de atributo pendentes "
            "e ganho de PV/PH conforme Constituição e Sabedoria atuais."
        ),
        inline=False,
    )
    embed.add_field(name="Taça das Casas", value=pontuacao, inline=False)
    embed.add_field(
        name="Histórico da Taça",
        value=f"{previa.historico_taca} movimentação(ões) serão arquivadas no backup e removidas da temporada ativa.",
        inline=False,
    )
    embed.set_footer(text="A confirmação é definitiva no Discord, mas os arquivos poderão ser restaurados pelo backup.")
    return embed


class ConfirmarPassagemAnoView(discord.ui.View):
    def __init__(self, cog: "PassagemAno", usuario_id: int, previa: PreviaPassagemAno):
        super().__init__(timeout=300)
        self.cog = cog
        self.usuario_id = usuario_id
        self.previa = previa
        self.concluida = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message("Somente quem abriu esta prévia pode confirmá-la.", ephemeral=True)
        return False

    @discord.ui.button(label="Confirmar passagem", emoji="✅", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.concluida:
            await interaction.response.send_message("Esta passagem de ano já foi encerrada.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with self.cog.bloqueio:
            try:
                backup = executar_passagem_ano(self.previa)
            except (OSError, ValueError) as erro:
                await interaction.edit_original_response(content=f"Não foi possível concluir: {erro}")
                return
            self.concluida = True
            self.stop()
            falhas = await self.cog.sincronizar_mensagens(self.previa)
            try:
                await self.cog.publicar_vagas_quadribol(self.previa)
            except (discord.DiscordException, OSError, ValueError) as erro:
                falhas.append(f"Profeta Diário (vagas de Quadribol): {erro}")
        texto = (
            f"✅ Passagem concluída: **{len(self.previa.mudancas)} fichas** subiram de nível, "
            f"**{len(self.previa.alunos)} alunos** avançaram e a Taça foi reiniciada.\n"
            f"Backup: `{backup.relative_to(backup.parents[2]).as_posix()}`"
        )
        if falhas:
            texto += "\n\n⚠️ Fichas salvas, mas algumas mensagens não foram atualizadas: " + "; ".join(falhas)
        await interaction.edit_original_response(content=texto, embed=None, view=None)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.concluida = True
        self.stop()
        await interaction.response.edit_message(content="Passagem de ano cancelada.", embed=None, view=None)


class PassagemAno(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bloqueio = asyncio.Lock()

    async def publicar_vagas_quadribol(
        self,
        previa: PreviaPassagemAno,
    ) -> discord.Message | None:
        embed = embed_vagas_quadribol(previa)
        if embed is None:
            return None
        canal = self.bot.get_channel(CANAL_PROFETA_DIARIO_ID)
        if canal is None:
            canal = await self.bot.fetch_channel(CANAL_PROFETA_DIARIO_ID)
        if not hasattr(canal, "send"):
            raise ValueError(
                "O canal configurado para o Profeta Diário não aceita mensagens."
            )
        return await canal.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def sincronizar_mensagens(self, previa: PreviaPassagemAno) -> list[str]:
        falhas: list[str] = []
        for mudanca in previa.mudancas:
            ficha = FichaPersonagem.carregar(mudanca.caminho_atual)
            alterada = False
            tinha_ficha_publicada = bool(ficha.mensagem_discord_id)
            tinha_narrativa_publicada = bool(ficha.mensagem_narrativa_discord_id)
            if mudanca.concluiu:
                try:
                    destino_ficha_anterior = destino_personagem(mudanca.grupo)
                    for mensagem_id in (
                        ficha.mensagem_discord_id,
                        ficha.mensagem_discord_parte_2_id,
                        ficha.mensagem_discord_parte_3_id,
                    ):
                        await excluir_publicacao_ficha(
                            self.bot,
                            destino_ficha_anterior,
                            mensagem_id,
                        )
                    destino_narrativo_anterior = destino_narrativo_grupo(
                        mudanca.grupo,
                        ficha.casa,
                    )
                    if ficha.mensagem_narrativa_discord_id:
                        if destino_narrativo_anterior is None:
                            raise ValueError(
                                "A thread narrativa anterior não está configurada."
                            )
                        await excluir_publicacao_ficha(
                            self.bot,
                            destino_narrativo_anterior,
                            ficha.mensagem_narrativa_discord_id,
                        )
                    if ficha.mensagem_time_discord_id:
                        destino_time_anterior = destino_time(ficha.casa)
                        if destino_time_anterior is None:
                            raise ValueError(
                                "A thread anterior do time não está configurada."
                            )
                        await excluir_publicacao_ficha(
                            self.bot,
                            destino_time_anterior,
                            ficha.mensagem_time_discord_id,
                        )
                except (ErroPublicacaoFicha, OSError, ValueError) as erro:
                    falhas.append(f"{ficha.nome} (migração): {erro}")
                    continue
                ficha.mensagem_discord_id = 0
                ficha.mensagem_discord_parte_2_id = 0
                ficha.mensagem_discord_parte_3_id = 0
                ficha.mensagem_narrativa_discord_id = 0
                ficha.mensagem_time_discord_id = 0
                alterada = True

            if ficha.mensagem_discord_id or (
                mudanca.concluiu and tinha_ficha_publicada
            ):
                try:
                    mensagem, mensagem_parte_2, mensagem_parte_3 = (
                        await publicar_personagem_em_partes(self.bot, ficha)
                    )
                    parte_2_id = mensagem_parte_2.id if mensagem_parte_2 else 0
                    parte_3_id = mensagem_parte_3.id if mensagem_parte_3 else 0
                    if ficha.mensagem_discord_id != mensagem.id:
                        ficha.mensagem_discord_id = mensagem.id
                        alterada = True
                    if ficha.mensagem_discord_parte_2_id != parte_2_id:
                        ficha.mensagem_discord_parte_2_id = parte_2_id
                        alterada = True
                    if ficha.mensagem_discord_parte_3_id != parte_3_id:
                        ficha.mensagem_discord_parte_3_id = parte_3_id
                        alterada = True
                except (ErroPublicacaoFicha, OSError, ValueError) as erro:
                    falhas.append(f"{ficha.nome} (ficha): {erro}")
            for entrada in montar_entradas_ficha(ficha, mudanca.caminho_atual):
                mensagem_id = (
                    ficha.mensagem_time_discord_id
                    if entrada.tipo == "time"
                    else ficha.mensagem_narrativa_discord_id
                )
                deve_recriar_narrativa = (
                    mudanca.concluiu
                    and entrada.tipo == "npc"
                    and tinha_narrativa_publicada
                )
                if (not mensagem_id and not deve_recriar_narrativa) or not entrada.pronta:
                    continue
                try:
                    mensagem = await publicar_ou_atualizar_ficha(
                        self.bot,
                        entrada.destino_id or 0,
                        entrada.embeds,
                        mensagem_id,
                        entrada.conteudo,
                        anexos=entrada.anexos,
                    )
                    if entrada.tipo == "time" and ficha.mensagem_time_discord_id != mensagem.id:
                        ficha.mensagem_time_discord_id = mensagem.id
                        alterada = True
                    elif entrada.tipo != "time" and ficha.mensagem_narrativa_discord_id != mensagem.id:
                        ficha.mensagem_narrativa_discord_id = mensagem.id
                        alterada = True
                except (ErroPublicacaoFicha, OSError, ValueError) as erro:
                    falhas.append(f"{ficha.nome} ({entrada.tipo}): {erro}")
            if alterada:
                salvar_ficha(ficha, mudanca.caminho_atual)
        return falhas

    @app_commands.command(
        name="passagem-de-ano",
        description="Avança o ano letivo, sobe o nível das fichas e reinicia a Taça das Casas.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def passagem_de_ano(self, interaction: discord.Interaction) -> None:
        membro = interaction.user
        if not isinstance(membro, discord.Member) or not membro.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Somente moderadores com **Gerenciar servidor** podem realizar a passagem de ano.",
                ephemeral=True,
            )
            return
        try:
            previa = preparar_passagem_ano()
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(f"Não foi possível preparar a prévia: {erro}", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=embed_previa_passagem(previa),
            view=ConfirmarPassagemAnoView(self, interaction.user.id, previa),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PassagemAno(bot))
