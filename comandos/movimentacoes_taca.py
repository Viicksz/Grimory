from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from comandos.taca import COR_TACA
from utils.taca import (
    CANAL_PROFETA_DIARIO_ID,
    CARGOS_CASAS,
    CATEGORIAS_GRATIFICACAO,
    CASAS,
    AcontecimentoTaca,
    FiguraAutoridade,
    PresetTaca,
    aplicar_acontecimento,
    carregar_autoridades,
    carregar_estado_taca,
    salvar_estado_taca,
)


COR_GRATIFICACAO = 0x57F287
COR_PENALIDADE = 0xED4245
PONTOS_OCORRENCIAS = {
    "leve": {1: 10, 2: 15, 3: 20},
    "grave": {1: 20, 2: 25, 3: 30},
}
PUNICOES_SEM_VARINHA = (
    "Limpar os banheiros",
    "Limpar o corujal",
    "Limpar a cozinha",
    "Lavar a louça do jantar",
    "Limpar o salão comunal",
    "Organizar a biblioteca",
    "Raspar chiclete das mesas",
    "Polir as armaduras de um corredor",
    "Envernizar os quadros de determinada área",
    "Lavar os uniformes do time de quadribol",
    "Passar um dia trabalhando na lavanderia",
)
CATEGORIAS_DESLIZE = (
    "Atraso",
    "Desorganização",
    "Atividade não entregue",
    "Material esquecido",
    "Conversa ou interrupção da aula",
    "Descuido com o espaço escolar",
)
@dataclass
class SessaoMovimentacao:
    tipo: str
    moderador_id: int
    usuario_id: int
    nome_personagem: str
    autoridade: FiguraAutoridade | None = None
    casa: str = ""
    categoria: str = ""
    dimensao: str = ""
    pontos: int = 0
    detalhes: str = ""
    severidade: str = ""
    ocorrencia: int = 0
    finalizada: bool = False


def rotulo_opcao(texto: str) -> str:
    texto = texto.strip()
    return (texto[:97] + "...") if len(texto) > 100 else texto


def mencao_casa_sem_emoji(casa: str) -> str:
    return f"<@&{CARGOS_CASAS[casa]}>"


def motivo_publicacao(sessao: SessaoMovimentacao) -> str:
    motivos_padrao = {
        "Nota 10": "tirar nota 10 ou acima em uma aula",
        "Execução Perfeita": (
            "obter um resultado excepcionalmente alto na execução de um "
            "feitiço, uma poção ou um trato em sua presença"
        ),
    }
    if sessao.autoridade is not None:
        motivos_padrao["Nota 10"] = (
            sessao.autoridade.nota_10 or motivos_padrao["Nota 10"]
        )
        motivos_padrao["Execução Perfeita"] = (
            sessao.autoridade.execucao_perfeita
            or motivos_padrao["Execução Perfeita"]
        )
    if sessao.categoria in {"Personalizada", "Outra ocorrência"}:
        motivo = sessao.detalhes
    else:
        motivo = motivos_padrao.get(sessao.categoria, sessao.categoria)
        if sessao.detalhes:
            motivo = f"{motivo}: {sessao.detalhes}"
    return motivo.strip().rstrip(".")


def embed_catalogo_gratificacao(sessao: SessaoMovimentacao) -> discord.Embed:
    linhas = [
        "**Gratificações padrão**",
        "`Nota 10` — **+5 pontos** — tirar nota 10 ou acima em uma aula.",
        (
            "`Execução Perfeita` — **+15 pontos** — obter um resultado "
            "excepcionalmente alto em um feitiço, uma poção ou um trato na "
            "presença da Figura de Autoridade."
        ),
        "",
        "**Categorias de acontecimentos**",
        "A categoria escolhida determina a pontuação.",
        "",
    ]
    linhas.extend(
        f"`{nome}` — **+{pontos} pontos**"
        for _, nome, pontos in CATEGORIAS_GRATIFICACAO
    )
    return discord.Embed(
        title="Categoria da gratificação",
        description="\n".join(linhas),
        color=COR_TACA,
    )


def exemplos_gratificacao(sessao: SessaoMovimentacao) -> list[PresetTaca]:
    return [
        preset
        for preset in sessao.autoridade.gratificacoes
        if preset.pontos == sessao.pontos
    ]


def embed_exemplos_gratificacao(
    sessao: SessaoMovimentacao,
    exemplos: list[PresetTaca],
) -> discord.Embed:
    linhas = [
        f"**{sessao.dimensao} — +{sessao.pontos} pontos**",
        f"Aos olhos de **{sessao.autoridade.nome}**:",
        "",
    ]
    linhas.extend(
        f"`Exemplo {indice}` — {preset.motivo}."
        for indice, preset in enumerate(exemplos, start=1)
    )
    linhas.extend(
        [
            "",
            "`Personalizada` — escreva outra situação desta mesma categoria.",
        ]
    )
    return discord.Embed(
        title="Exemplos da gratificação",
        description="\n".join(linhas),
        color=COR_TACA,
    )


def embed_catalogo_penalidade(
    sessao: SessaoMovimentacao,
    especificas: list,
) -> discord.Embed:
    linhas = []
    if sessao.severidade == "deslize":
        linhas.extend(
            [
                "**Deslizes disciplinares — −5 pontos**",
                *(f"`{categoria}`" for categoria in CATEGORIAS_DESLIZE),
                "",
            ]
        )
    linhas.append(f"**Situações de {sessao.autoridade.nome}**")
    linhas.extend(
        f"`Situação {indice}` — {preset.motivo}."
        for indice, preset in enumerate(especificas, start=1)
    )
    linhas.extend(["", "`Outra ocorrência` — motivo descrito pelo moderador."])
    return discord.Embed(
        title="Categoria da penalidade",
        description="\n".join(linhas),
        color=COR_TACA,
    )


def embed_previa(sessao: SessaoMovimentacao) -> discord.Embed:
    expulsao = sessao.tipo == "expulsao"
    gratificacao = sessao.tipo == "gratificacao"
    titulo = "Prévia — Expulsão" if expulsao else (
        "Prévia — Gratificação" if gratificacao else "Prévia — Penalidade"
    )
    cor = COR_GRATIFICACAO if gratificacao else COR_PENALIDADE
    embed = discord.Embed(title=titulo, color=cor)
    embed.add_field(name="Figura de Autoridade", value=sessao.autoridade.nome, inline=False)
    embed.add_field(
        name="Estudante",
        value=f"<@{sessao.usuario_id}>",
        inline=False,
    )
    embed.add_field(name="Casa", value=mencao_casa_sem_emoji(sessao.casa), inline=True)
    if expulsao:
        embed.add_field(name="Efeito", value="Apenas encenação — sem alteração de pontos.", inline=True)
    else:
        sinal = "+" if sessao.pontos > 0 else "−"
        embed.add_field(name="Pontos", value=f"**{sinal}{abs(sessao.pontos)}**", inline=True)
    if gratificacao and sessao.dimensao:
        embed.add_field(name="Categoria", value=sessao.dimensao, inline=False)
        embed.add_field(name="Acontecimento", value=sessao.categoria, inline=False)
    else:
        embed.add_field(name="Categoria", value=sessao.categoria, inline=False)
    if sessao.detalhes:
        embed.add_field(name="Detalhes", value=sessao.detalhes, inline=False)
    if sessao.severidade in {"leve", "grave"}:
        embed.add_field(
            name="Ocorrência",
            value=f"{sessao.ocorrencia}ª ocorrência — punição sorteada após a confirmação",
            inline=False,
        )
    return embed


def embed_publicacao(sessao: SessaoMovimentacao, punicao: str = "") -> discord.Embed:
    gratificacao = sessao.tipo == "gratificacao"
    cor = COR_GRATIFICACAO if gratificacao else COR_PENALIDADE
    motivo = motivo_publicacao(sessao)
    if gratificacao:
        texto = (
            f"**{sessao.autoridade.nome}** concedeu a <@{sessao.usuario_id}> "
            f"*{abs(sessao.pontos)} pontos* para a "
            f"{mencao_casa_sem_emoji(sessao.casa)} por {motivo}."
        )
    else:
        texto = (
            f"**{sessao.autoridade.nome}** retirou de <@{sessao.usuario_id}> "
            f"*{abs(sessao.pontos)} pontos* da "
            f"{mencao_casa_sem_emoji(sessao.casa)} por {motivo}."
        )
    if punicao:
        texto += f"\n\nComo punição, deverá **{punicao.lower()}**, sem uso de varinha."
    return discord.Embed(description=texto, color=cor)


def embed_expulsao(sessao: SessaoMovimentacao) -> discord.Embed:
    motivo = sessao.detalhes.strip().rstrip(".")
    return discord.Embed(
        description=(
            f"**{sessao.autoridade.nome}** determinou que <@{sessao.usuario_id}>, "
            f"da {mencao_casa_sem_emoji(sessao.casa)}, "
            f"compareça imediatamente à Diretoria de Hogwarts por {motivo}."
        ),
        color=COR_PENALIDADE,
    )


def nome_curto(texto: str, limite: int = 18) -> str:
    return texto if len(texto) <= limite else f"{texto[: limite - 1]}…"


def placeholder_contexto(sessao: SessaoMovimentacao) -> str:
    autoridade = nome_curto(sessao.autoridade.nome, 22)
    estudante = nome_curto(sessao.nome_personagem)
    if sessao.tipo == "gratificacao":
        return (
            f"{autoridade} concedeu a @{estudante} {abs(sessao.pontos)} pontos "
            f"para a @{sessao.casa} por [...]"
        )
    if sessao.tipo == "penalidade":
        return (
            f"{autoridade} retirou de @{estudante} {abs(sessao.pontos)} pontos "
            f"da @{sessao.casa} por [...]"
        )
    return f"{autoridade} convocou @{estudante} à Diretoria por [...]"


async def enviar_previa(
    interaction: discord.Interaction,
    cog: MovimentacoesTaca,
    sessao: SessaoMovimentacao,
) -> None:
    embed_final = (
        embed_expulsao(sessao)
        if sessao.tipo == "expulsao"
        else embed_publicacao(sessao)
    )
    await interaction.response.send_message(
        embeds=[embed_previa(sessao), embed_final],
        view=ConfirmacaoMovimentacaoView(cog, sessao),
        ephemeral=True,
    )


class ViewDaSessao(discord.ui.View):
    def __init__(self, cog: MovimentacoesTaca, sessao: SessaoMovimentacao, *, timeout: float = 600):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.sessao = sessao

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.sessao.moderador_id:
            return True
        await interaction.response.send_message("Este formulário não pertence a você.", ephemeral=True)
        return False


class SelecaoInicialView(ViewDaSessao):
    def __init__(self, cog: MovimentacoesTaca, sessao: SessaoMovimentacao):
        super().__init__(cog, sessao)
        autoridades = carregar_autoridades()
        seletor_autoridade = discord.ui.Select(
            placeholder="Figura de Autoridade",
            options=[
                discord.SelectOption(
                    label=autoridade.nome,
                    value=str(indice),
                    description=rotulo_opcao(autoridade.ocupacao),
                )
                for indice, autoridade in enumerate(autoridades)
            ],
            row=0,
        )
        seletor_casa = discord.ui.Select(
            placeholder="Casa do estudante",
            options=[discord.SelectOption(label=casa, value=casa) for casa in CASAS],
            row=1,
        )

        async def selecionar_autoridade(interaction: discord.Interaction) -> None:
            self.sessao.autoridade = autoridades[int(seletor_autoridade.values[0])]
            await interaction.response.defer()

        async def selecionar_casa(interaction: discord.Interaction) -> None:
            self.sessao.casa = seletor_casa.values[0]
            await interaction.response.defer()

        seletor_autoridade.callback = selecionar_autoridade
        seletor_casa.callback = selecionar_casa
        self.add_item(seletor_autoridade)
        self.add_item(seletor_casa)

    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.primary, row=2)
    async def continuar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.sessao.autoridade is None or not self.sessao.casa:
            await interaction.response.send_message(
                "Selecione a Figura de Autoridade e a casa.", ephemeral=True
            )
            return
        if self.sessao.tipo == "gratificacao":
            proxima = CategoriaGratificacaoView(self.cog, self.sessao)
            proximo_embed = embed_catalogo_gratificacao(self.sessao)
        else:
            proxima = SeveridadeView(self.cog, self.sessao)
            proximo_embed = discord.Embed(title="Penalidade — Intensidade", color=COR_TACA)
        await interaction.response.edit_message(
            embed=proximo_embed,
            view=proxima,
        )


class CategoriaGratificacaoView(ViewDaSessao):
    def __init__(self, cog: MovimentacoesTaca, sessao: SessaoMovimentacao):
        super().__init__(cog, sessao)
        self.escolha = ""
        opcoes = [
            discord.SelectOption(
                label="Nota 10",
                value="padrao:nota_10",
                description="+5 pontos",
            ),
            discord.SelectOption(
                label="Execução Perfeita",
                value="padrao:execucao_perfeita",
                description="+15 pontos",
            ),
            *[
                discord.SelectOption(
                    label=nome,
                    value=identificador,
                    description=f"+{pontos} pontos",
                )
                for identificador, nome, pontos in CATEGORIAS_GRATIFICACAO
            ],
        ]
        seletor = discord.ui.Select(placeholder="Categoria da gratificação", options=opcoes)

        async def selecionar(interaction: discord.Interaction) -> None:
            self.escolha = seletor.values[0]
            await interaction.response.defer()

        seletor.callback = selecionar
        self.add_item(seletor)

    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.primary, row=1)
    async def continuar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.escolha:
            await interaction.response.send_message("Escolha uma categoria.", ephemeral=True)
            return
        if self.escolha == "padrao:nota_10":
            self.sessao.dimensao = ""
            self.sessao.categoria = "Nota 10"
            self.sessao.pontos = 5
            await enviar_previa(interaction, self.cog, self.sessao)
            return
        if self.escolha == "padrao:execucao_perfeita":
            self.sessao.dimensao = ""
            self.sessao.categoria = "Execução Perfeita"
            self.sessao.pontos = 15
            await enviar_previa(interaction, self.cog, self.sessao)
            return
        _, nome, pontos = next(
            categoria
            for categoria in CATEGORIAS_GRATIFICACAO
            if categoria[0] == self.escolha
        )
        self.sessao.dimensao = nome
        self.sessao.pontos = pontos
        proxima = ExemplosGratificacaoView(self.cog, self.sessao)
        await interaction.response.edit_message(
            embed=proxima.embed_catalogo(),
            view=proxima,
        )


class ExemplosGratificacaoView(ViewDaSessao):
    def __init__(self, cog: MovimentacoesTaca, sessao: SessaoMovimentacao):
        super().__init__(cog, sessao)
        self.escolha = ""
        self.exemplos = exemplos_gratificacao(sessao)
        seletor = discord.ui.Select(
            placeholder="Acontecimento da gratificação",
            options=(
                [
                    discord.SelectOption(
                        label=f"Exemplo {indice}",
                        value=f"exemplo:{indice - 1}",
                        description=f"{sessao.dimensao} • +{sessao.pontos} pontos",
                    )
                    for indice, _ in enumerate(self.exemplos, start=1)
                ]
                + [
                    discord.SelectOption(
                        label="Personalizada",
                        value="personalizada",
                        description="Outra situação desta mesma categoria",
                    )
                ]
            ),
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            self.escolha = seletor.values[0]
            await interaction.response.defer()

        seletor.callback = selecionar
        self.add_item(seletor)

    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.primary, row=1)
    async def continuar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.escolha:
            await interaction.response.send_message("Escolha um acontecimento.", ephemeral=True)
            return
        if self.escolha == "personalizada":
            self.sessao.categoria = "Personalizada"
            await interaction.response.send_modal(
                ContextoModal(self.cog, self.sessao, obrigatorio=True)
            )
            return
        indice = int(self.escolha.split(":", 1)[1])
        self.sessao.categoria = self.exemplos[indice].motivo
        await enviar_previa(interaction, self.cog, self.sessao)

    def embed_catalogo(self) -> discord.Embed:
        return embed_exemplos_gratificacao(self.sessao, self.exemplos)


class SeveridadeView(ViewDaSessao):
    def __init__(self, cog: MovimentacoesTaca, sessao: SessaoMovimentacao):
        super().__init__(cog, sessao)
        seletor = discord.ui.Select(
            placeholder="Intensidade da penalidade",
            options=[
                discord.SelectOption(
                    label="Deslize Disciplinar", value="deslize", description="−5 pontos, sem tarefa"
                ),
                discord.SelectOption(
                    label="Infração Leve", value="leve", description="−10, −15 ou −20 pontos"
                ),
                discord.SelectOption(
                    label="Infração Grave", value="grave", description="−20, −25 ou −30 pontos"
                ),
                discord.SelectOption(
                    label="Expulsão", value="expulsao", description="Apenas para dar medo"
                ),
            ],
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            self.sessao.severidade = seletor.values[0]
            await interaction.response.defer()

        seletor.callback = selecionar
        self.add_item(seletor)

    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.primary, row=1)
    async def continuar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.sessao.severidade:
            await interaction.response.send_message("Escolha a intensidade.", ephemeral=True)
            return
        if self.sessao.severidade == "expulsao":
            self.sessao.tipo = "expulsao"
            self.sessao.categoria = "Expulsão"
            await interaction.response.send_modal(ContextoModal(self.cog, self.sessao, obrigatorio=True))
            return
        if self.sessao.severidade == "deslize":
            self.sessao.pontos = -5
            proxima = CategoriaPenalidadeView(self.cog, self.sessao)
            await interaction.response.edit_message(
                embed=proxima.embed_catalogo(),
                view=proxima,
            )
            return
        await interaction.response.edit_message(
            embed=discord.Embed(title="Penalidade — Ocorrência", color=COR_TACA),
            view=OcorrenciaView(self.cog, self.sessao),
        )


class OcorrenciaView(ViewDaSessao):
    def __init__(self, cog: MovimentacoesTaca, sessao: SessaoMovimentacao):
        super().__init__(cog, sessao)
        seletor = discord.ui.Select(
            placeholder="Nível de ocorrência",
            options=[
                discord.SelectOption(
                    label=f"{numero}ª ocorrência",
                    value=str(numero),
                    description=(
                        f"−{PONTOS_OCORRENCIAS[sessao.severidade][numero]} pontos"
                    ),
                )
                for numero in (1, 2, 3)
            ],
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            self.sessao.ocorrencia = int(seletor.values[0])
            await interaction.response.defer()

        seletor.callback = selecionar
        self.add_item(seletor)

    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.primary, row=1)
    async def continuar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.sessao.ocorrencia:
            await interaction.response.send_message("Escolha a ocorrência.", ephemeral=True)
            return
        self.sessao.pontos = -PONTOS_OCORRENCIAS[self.sessao.severidade][self.sessao.ocorrencia]
        proxima = CategoriaPenalidadeView(self.cog, self.sessao)
        await interaction.response.edit_message(
            embed=proxima.embed_catalogo(),
            view=proxima,
        )


class CategoriaPenalidadeView(ViewDaSessao):
    def __init__(self, cog: MovimentacoesTaca, sessao: SessaoMovimentacao):
        super().__init__(cog, sessao)
        self.escolha = ""
        opcoes: list[discord.SelectOption] = []
        if sessao.severidade == "deslize":
            opcoes.extend(
                discord.SelectOption(label=categoria, value=f"comum:{indice}")
                for indice, categoria in enumerate(CATEGORIAS_DESLIZE)
            )
            alvo_preset = 5
        else:
            alvo_preset = min(abs(sessao.pontos), 25)
        especificas = [
            preset for preset in sessao.autoridade.penalidades if preset.pontos == alvo_preset
        ]
        opcoes.extend(
            discord.SelectOption(
                label=f"Situação {indice + 1}",
                value=f"preset:{indice}",
                description=f"−{abs(sessao.pontos)} pontos",
            )
            for indice, preset in enumerate(especificas)
        )
        opcoes.append(
            discord.SelectOption(
                label="Outra ocorrência",
                value="personalizada",
                description="Motivo descrito pelo moderador",
            )
        )
        self.especificas = especificas
        seletor = discord.ui.Select(placeholder="Categoria da penalidade", options=opcoes)

        async def selecionar(interaction: discord.Interaction) -> None:
            self.escolha = seletor.values[0]
            await interaction.response.defer()

        seletor.callback = selecionar
        self.add_item(seletor)

    def embed_catalogo(self) -> discord.Embed:
        return embed_catalogo_penalidade(self.sessao, self.especificas)

    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.primary, row=1)
    async def continuar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.escolha:
            await interaction.response.send_message("Escolha uma categoria.", ephemeral=True)
            return
        if self.escolha.startswith("comum:"):
            self.sessao.categoria = CATEGORIAS_DESLIZE[int(self.escolha.split(":")[1])]
        elif self.escolha.startswith("preset:"):
            self.sessao.categoria = self.especificas[int(self.escolha.split(":")[1])].motivo
        else:
            self.sessao.categoria = "Outra ocorrência"
            await interaction.response.send_modal(
                ContextoModal(self.cog, self.sessao, obrigatorio=True)
            )
            return
        await enviar_previa(interaction, self.cog, self.sessao)


class ContextoModal(discord.ui.Modal):
    def __init__(self, cog: MovimentacoesTaca, sessao: SessaoMovimentacao, *, obrigatorio: bool):
        super().__init__(title="Detalhes da movimentação")
        self.cog = cog
        self.sessao = sessao
        self.contexto = discord.ui.TextInput(
            label="Complete o trecho entre colchetes",
            placeholder=placeholder_contexto(sessao),
            style=discord.TextStyle.paragraph,
            required=obrigatorio,
            max_length=700,
        )
        self.add_item(self.contexto)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.sessao.detalhes = str(self.contexto.value).strip()
        await enviar_previa(interaction, self.cog, self.sessao)


class ConfirmacaoMovimentacaoView(ViewDaSessao):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, emoji="✅")
    async def confirmar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.sessao.finalizada:
            await interaction.response.send_message("Esta operação já foi concluída.", ephemeral=True)
            return
        self.sessao.finalizada = True
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            punicao = await self.cog.aplicar_e_publicar(self.sessao)
        except (OSError, ValueError, discord.HTTPException) as erro:
            self.sessao.finalizada = False
            await interaction.edit_original_response(content=f"Não foi possível concluir: {erro}")
            return
        self.stop()
        if self.sessao.tipo == "expulsao":
            texto = "A expulsão cenográfica foi publicada. Nenhum ponto ou punição real foi aplicado."
        else:
            texto = "Movimentação registrada e publicada no Profeta-diário."
            if punicao:
                texto += f" Punição sorteada: **{punicao}**."
        await interaction.edit_original_response(content=texto, embed=None, view=None)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.sessao.finalizada = True
        self.stop()
        await interaction.response.edit_message(content="Operação cancelada.", embed=None, view=None)


class MovimentacoesTaca(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bloqueio = asyncio.Lock()
        self.sorteio = random.SystemRandom()

    async def obter_profeta_diario(self):
        canal = self.bot.get_channel(CANAL_PROFETA_DIARIO_ID)
        if canal is None:
            canal = await self.bot.fetch_channel(CANAL_PROFETA_DIARIO_ID)
        if not hasattr(canal, "send"):
            raise ValueError("O canal configurado para o Profeta-diário não aceita mensagens.")
        return canal

    async def aplicar_e_publicar(self, sessao: SessaoMovimentacao) -> str:
        canal = await self.obter_profeta_diario()
        if sessao.tipo == "expulsao":
            await canal.send(
                embed=embed_expulsao(sessao),
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, users=True, roles=True, replied_user=False
                ),
            )
            return ""

        punicao = ""
        if sessao.tipo == "penalidade" and sessao.severidade in {"leve", "grave"}:
            punicao = self.sorteio.choice(PUNICOES_SEM_VARINHA)
        agora = datetime.now(timezone.utc)
        acontecimento = AcontecimentoTaca(
            identificador=f"{agora:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}",
            tipo=f"{sessao.tipo}_manual",
            autoridade=sessao.autoridade.nome,
            personagem=sessao.nome_personagem,
            casa=sessao.casa,
            pontos=sessao.pontos,
            motivo=sessao.categoria,
            moderador_id=sessao.moderador_id,
            criado_em=agora.isoformat(timespec="seconds"),
            usuario_id=sessao.usuario_id,
            categoria=sessao.dimensao or sessao.categoria,
            detalhes=sessao.detalhes,
            punicao=punicao,
        )
        async with self.bloqueio:
            estado = carregar_estado_taca()
            aplicar_acontecimento(estado, acontecimento)
            salvar_estado_taca(estado)
        await canal.send(
            embed=embed_publicacao(sessao, punicao),
            allowed_mentions=discord.AllowedMentions(
                everyone=False, users=True, roles=True, replied_user=False
            ),
        )
        return punicao

    async def iniciar(self, interaction: discord.Interaction, usuario: discord.Member, tipo: str) -> None:
        membro = interaction.user
        if not isinstance(membro, discord.Member) or not membro.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Você precisa da permissão **Gerenciar servidor** para usar este comando.",
                ephemeral=True,
            )
            return
        sessao = SessaoMovimentacao(
            tipo=tipo,
            moderador_id=membro.id,
            usuario_id=usuario.id,
            nome_personagem=usuario.display_name,
        )
        await interaction.response.send_message(
            embed=discord.Embed(
                title=("Nova Gratificação" if tipo == "gratificacao" else "Nova Penalidade"),
                description=(
                    f"Estudante selecionado: <@{usuario.id}>\n"
                    "Escolha a Figura de Autoridade e a casa."
                ),
                color=(COR_GRATIFICACAO if tipo == "gratificacao" else COR_PENALIDADE),
            ),
            view=SelecaoInicialView(self, sessao),
            ephemeral=True,
        )

    @app_commands.command(
        name="gratificação",
        description="Concede pontos manuais à casa de um estudante.",
    )
    @app_commands.describe(usuario="Estudante que receberá a gratificação")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def gratificacao(self, interaction: discord.Interaction, usuario: discord.Member) -> None:
        await self.iniciar(interaction, usuario, "gratificacao")

    @app_commands.command(
        name="penalidade",
        description="Registra uma penalidade para a casa de um estudante.",
    )
    @app_commands.describe(usuario="Estudante que receberá a penalidade")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def penalidade(self, interaction: discord.Interaction, usuario: discord.Member) -> None:
        await self.iniciar(interaction, usuario, "penalidade")
