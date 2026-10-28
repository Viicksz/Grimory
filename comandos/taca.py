from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from utils.taca import (
    CANAL_PROFETA_DIARIO_ID,
    CASAS,
    CARGOS_CASAS,
    CORACOES_CASAS,
    AcontecimentoTaca,
    EstadoTaca,
    aplicar_acontecimento,
    carregar_estado_taca,
    carregar_autoridades,
    listar_personagens_por_casa,
    salvar_estado_taca,
    sortear_acontecimento,
    texto_acontecimento,
)


COR_TACA = 0xD4AF37


def cabecalho_taca(titulo: str) -> str:
    return (
        "## ══════◄••🏆••►══════\n"
        f"## {titulo}\n"
        "## ══════◄••🏆••►══════"
    )


def mencao_casa(casa: str) -> str:
    return f"{CORACOES_CASAS[casa]} <@&{CARGOS_CASAS[casa]}>"


def resumo_movimentacao(item: AcontecimentoTaca) -> str:
    sinal = "+" if item.pontos > 0 else "−"
    return (
        f"{mencao_casa(item.casa)} **{sinal}{abs(item.pontos)} pontos** — "
        f"{item.personagem}, por {item.autoridade}"
    )


def embed_taca(estado: EstadoTaca) -> discord.Embed:
    classificacao = sorted(
        CASAS,
        key=lambda casa: (-estado.pontuacoes.get(casa, 0), CASAS.index(casa)),
    )
    maior = estado.pontuacoes.get(classificacao[0], 0)
    lideres = [casa for casa in classificacao if estado.pontuacoes.get(casa, 0) == maior]
    if len(lideres) == 1:
        lideranca = f"{mencao_casa(lideres[0])} lidera com **{maior} pontos**."
    else:
        nomes = ", ".join(mencao_casa(casa) for casa in lideres)
        lideranca = f"Empate na liderança entre {nomes}, com **{maior} pontos**."

    linhas = []
    medalhas = ("🥇", "🥈", "🥉", "💩")
    for indice, casa in enumerate(classificacao):
        linhas.append(
            f"{medalhas[indice]} {mencao_casa(casa)} — "
            f"{estado.pontuacoes.get(casa, 0)} pontos"
        )

    recentes = estado.historico[-5:]
    embed = discord.Embed(
        title="Taça das Casas",
        description=lideranca,
        color=COR_TACA,
    )
    embed.add_field(name="Classificação", value="\n".join(linhas), inline=False)
    embed.add_field(
        name="Movimentações recentes",
        value=(
            "\n".join(resumo_movimentacao(item) for item in reversed(recentes))
            if recentes
            else "*Ainda não houve movimentações.*"
        ),
        inline=False,
    )

    personagens = listar_personagens_por_casa()
    disponiveis = [casa for casa in CASAS if personagens[casa]]
    if len(disponiveis) == 4:
        embed.set_footer(text="Sorteio equilibrado: 25% de chance para cada casa.")
    elif disponiveis:
        embed.set_footer(text="Teste limitado às casas que já possuem fichas elegíveis.")
    else:
        embed.set_footer(text="Nenhuma casa possui fichas elegíveis para o sorteio.")
    return embed


def embeds_acontecimentos(
    acontecimentos: list[AcontecimentoTaca],
) -> list[discord.Embed]:
    return [
        discord.Embed(
            description=texto_acontecimento(acontecimento),
            color=0x57F287 if acontecimento.pontos > 0 else 0xED4245,
        )
        for acontecimento in acontecimentos
    ]


class TacaDasCasasView(discord.ui.View):
    def __init__(self, cog: TacaDasCasas):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Gerar 5 acontecimentos",
        style=discord.ButtonStyle.primary,
        emoji="🎲",
        custom_id="taca-das-casas:acontecimento",
    )
    async def gerar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        membro = interaction.user
        if not isinstance(membro, discord.Member) or not membro.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Somente moderadores com **Gerenciar servidor** podem gerar acontecimentos.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            estado, acontecimentos = await self.cog.gerar_acontecimentos(membro.id)
        except (OSError, ValueError) as erro:
            await interaction.edit_original_response(content=f"Não foi possível realizar o sorteio: {erro}")
            return

        painel_atualizado = [
            embed_taca(estado),
            *embeds_acontecimentos(acontecimentos),
        ]
        try:
            if interaction.message is not None:
                await interaction.message.edit(
                    embeds=painel_atualizado,
                    view=self,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            if interaction.channel_id != CANAL_PROFETA_DIARIO_ID:
                canal = await self.cog.obter_profeta_diario()
                await canal.send(
                    embeds=painel_atualizado,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except (discord.HTTPException, ValueError) as erro:
            await interaction.edit_original_response(
                content=(
                    "A pontuação foi registrada, mas houve uma falha ao publicar "
                    f"uma das atualizações: {erro}"
                )
            )
            return
        await interaction.edit_original_response(
            content="Cinco acontecimentos foram gerados e o placar foi atualizado."
        )


class TacaDasCasas(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bloqueio = asyncio.Lock()

    async def cog_load(self) -> None:
        self.bot.add_view(TacaDasCasasView(self))

    async def obter_profeta_diario(self):
        canal = self.bot.get_channel(CANAL_PROFETA_DIARIO_ID)
        if canal is None:
            canal = await self.bot.fetch_channel(CANAL_PROFETA_DIARIO_ID)
        if not hasattr(canal, "send"):
            raise ValueError("O canal configurado para o Profeta-diário não aceita mensagens.")
        return canal

    async def gerar_acontecimentos(
        self,
        moderador_id: int,
        quantidade: int = 5,
    ) -> tuple[EstadoTaca, list[AcontecimentoTaca]]:
        async with self.bloqueio:
            autoridades = carregar_autoridades()
            personagens = listar_personagens_por_casa()
            acontecimentos = [
                sortear_acontecimento(
                    moderador_id=moderador_id,
                    autoridades=autoridades,
                    personagens=personagens,
                )
                for _ in range(quantidade)
            ]
            estado = carregar_estado_taca()
            for acontecimento in acontecimentos:
                aplicar_acontecimento(estado, acontecimento)
            salvar_estado_taca(estado)
            return estado, acontecimentos

    @app_commands.command(
        name="taca-das-casas",
        description="Mostra a liderança e a pontuação atual da Taça das Casas.",
    )
    @app_commands.guild_only()
    async def taca_das_casas(self, interaction: discord.Interaction) -> None:
        estado = carregar_estado_taca()
        await interaction.response.send_message(
            content=cabecalho_taca("Taça das Casas"),
            embed=embed_taca(estado),
            view=TacaDasCasasView(self),
            allowed_mentions=discord.AllowedMentions.none(),
        )
