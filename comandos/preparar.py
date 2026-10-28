import re

import discord
from discord import app_commands
from discord.ext import commands

from comandos.executar import (
    GrupoIndice,
    ItemIndice,
    criar_embeds_indice,
    localizar_links_oficiais,
    organizar_lotes_indice,
)
from utils.biblioteca import BibliotecaCategoria, EntradaBiblioteca, normalizar_rotulo


pocoes = BibliotecaCategoria("poções")
COR_EMBED_POCAO = 0x66F060
PADRAO_CAMPO = re.compile(r"^\*\*(.+?):\*\*$")
PADRAO_CAMPO_LIMPO = re.compile(r"^([^:]+):$")
PADRAO_PREPARO = re.compile(r"^`(.+?)\s*//\s*(.+?)`$")
LIMITE_TOTAL_EMBEDS = 6000
LIMITE_AUTOCOMPLETE = 25
NOME_INDICE_POCOES = "Poções"


def interpretar_pocao(conteudo: str) -> tuple[EntradaBiblioteca, str, str]:
    titulo = ""
    tempo = ""
    rendimento = ""
    campos: dict[str, str] = {}
    rotulo_atual: str | None = None
    valores: list[str] = []

    def guardar_campo() -> None:
        if rotulo_atual is not None:
            campos[rotulo_atual] = "\n".join(valores).strip()

    for linha in conteudo.splitlines():
        linha_limpa = linha.strip()

        if not linha_limpa or linha_limpa.startswith("══════"):
            continue

        if linha_limpa.startswith("# "):
            titulo = linha_limpa.removeprefix("# ").strip()
            continue

        preparo = PADRAO_PREPARO.fullmatch(linha_limpa)
        if preparo:
            tempo, rendimento = preparo.groups()
            continue

        campo = PADRAO_CAMPO.fullmatch(linha_limpa)
        if campo is None:
            campo = PADRAO_CAMPO_LIMPO.fullmatch(linha_limpa)

        if campo:
            guardar_campo()
            rotulo_atual = normalizar_rotulo(campo.group(1))
            valores = []
            continue

        if rotulo_atual is not None:
            valores.append(linha_limpa.removeprefix("> ").removeprefix(">"))

    guardar_campo()
    descricao = campos.pop("descricao", "")
    tempo = tempo or campos.pop("tempo de preparo", "")
    rendimento = rendimento or campos.pop("rendimento", "")

    return (
        EntradaBiblioteca(titulo=titulo, descricao=descricao, campos=campos),
        tempo.strip(),
        rendimento.strip(),
    )


def juntar_secoes(secoes: list[tuple[str, str]]) -> str:
    return "\n\n".join(
        f"**{titulo}**\n{conteudo}"
        for titulo, conteudo in secoes
        if conteudo
    )


def tamanho_embed(embed: discord.Embed) -> int:
    total = len(embed.title or "") + len(embed.description or "")

    for campo in embed.fields:
        total += len(campo.name) + len(campo.value)

    return total


def agrupar_embeds(embeds: list[discord.Embed]) -> list[list[discord.Embed]]:
    lotes: list[list[discord.Embed]] = []
    lote_atual: list[discord.Embed] = []
    tamanho_atual = 0

    for embed in embeds:
        tamanho = tamanho_embed(embed)

        if lote_atual and tamanho_atual + tamanho > LIMITE_TOTAL_EMBEDS:
            lotes.append(lote_atual)
            lote_atual = []
            tamanho_atual = 0

        lote_atual.append(embed)
        tamanho_atual += tamanho

    if lote_atual:
        lotes.append(lote_atual)

    return lotes


def normalizar_ano(ano: str) -> str:
    correspondencia = re.search(r"\b([1-7])\s*[º°o]?\s*ano\b", ano, re.IGNORECASE)

    if correspondencia:
        return f"{correspondencia.group(1)}º Ano"

    return ano.strip() or "Sem ano de desbloqueio"


def buscar_nomes_preparo(termo: str = "") -> list[str]:
    termo_normalizado = normalizar_rotulo(termo)
    nomes = []

    if not termo_normalizado or termo_normalizado in normalizar_rotulo(NOME_INDICE_POCOES):
        nomes.append(NOME_INDICE_POCOES)

    nomes.extend(
        nome
        for nome in pocoes.listar_nomes()
        if not termo_normalizado or termo_normalizado in normalizar_rotulo(nome)
    )
    return nomes[:LIMITE_AUTOCOMPLETE]


def criar_grupos_indice_pocoes() -> list[GrupoIndice]:
    itens_por_ano: dict[str, list[ItemIndice]] = {}

    for arquivo in pocoes.listar_arquivos():
        entrada, _, _ = interpretar_pocao(arquivo.read_text(encoding="utf-8"))
        ano = normalizar_ano(
            entrada.campos.get("ano de desbloqueio", "") or arquivo.parent.name
        )
        itens_por_ano.setdefault(ano, []).append(
            ItemIndice(
                nome=entrada.titulo or arquivo.stem,
                entrada=entrada,
                tipo="pocao",
            )
        )

    return [
        GrupoIndice(
            titulo=ano,
            itens=sorted(itens, key=lambda item: normalizar_rotulo(item.nome)),
        )
        for ano, itens in sorted(
            itens_por_ano.items(),
            key=lambda par: (
                int(par[0][0]) if re.match(r"[1-7]º Ano$", par[0]) else 99,
                par[0].casefold(),
            ),
        )
    ]


def montar_embeds_indice_pocoes(
    links: dict[tuple[str, str], str] | None = None,
) -> list[discord.Embed]:
    return criar_embeds_indice(
        NOME_INDICE_POCOES,
        criar_grupos_indice_pocoes(),
        COR_EMBED_POCAO,
        links,
    )


def montar_embeds_pocao(
    entrada: EntradaBiblioteca,
    nome: str,
    tempo: str,
    rendimento: str,
) -> list[discord.Embed]:
    campos = entrada.campos
    identidade = discord.Embed(
        title=entrada.titulo or nome,
        description=entrada.descricao,
        color=COR_EMBED_POCAO,
    )

    consumo = campos.get("consumo", "")
    aparencia = campos.get("aparencia", "")
    efeito = campos.get("efeito", "")

    if consumo:
        identidade.add_field(name="Consumo", value=consumo, inline=True)

    if aparencia:
        identidade.add_field(name="Aparência", value=aparencia, inline=True)

    if efeito:
        identidade.add_field(name="Efeito", value=efeito, inline=False)

    if tempo:
        identidade.add_field(name="Tempo de preparo:", value=tempo, inline=True)

    if rendimento:
        identidade.add_field(name="Rendimento:", value=rendimento, inline=True)

    duracao = campos.get("duracao", "")

    if duracao:
        identidade.add_field(name="Duração:", value=duracao, inline=True)

    receita = discord.Embed(
        description=juntar_secoes([
            ("Ingredientes", campos.get("ingredientes", "")),
            ("Modo de preparo", campos.get("modo de preparo", "") or campos.get("preparo", "")),
        ]),
        color=COR_EMBED_POCAO,
    )
    riscos = discord.Embed(
        description=juntar_secoes([
            (
                "Efeitos colaterais gerais",
                campos.get("efeitos colaterais gerais", "")
                or campos.get("efeitos colaterais", ""),
            ),
            ("Poção defeituosa", campos.get("pocao defeituosa", "")),
        ]),
        color=COR_EMBED_POCAO,
    )
    progressao = discord.Embed(color=COR_EMBED_POCAO)

    desbloqueio = campos.get("ano de desbloqueio", "")
    grau = campos.get("grau de dificuldade", "")
    dificuldade = campos.get("dificuldade por ano", "")

    if desbloqueio:
        progressao.add_field(name="Desbloqueio:", value=desbloqueio, inline=True)

    if grau:
        progressao.add_field(name="Grau de Dificuldade:", value=grau, inline=True)

    if dificuldade:
        progressao.add_field(
            name="Dificuldade por ano:",
            value=dificuldade,
            inline=False,
        )

    return [identidade, receita, riscos, progressao]


class Preparar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def autocomplete_pocoes(
        self,
        interaction: discord.Interaction,
        atual: str,
    ) -> list[app_commands.Choice[str]]:
        nomes = buscar_nomes_preparo(atual)
        return [app_commands.Choice(name=nome, value=nome) for nome in nomes]

    @app_commands.command(
        name="preparar",
        description="Mostra como preparar uma poção da biblioteca.",
    )
    @app_commands.describe(nome="Nome da arte mágica ou da poção")
    @app_commands.autocomplete(nome=autocomplete_pocoes)
    async def preparar(self, interaction: discord.Interaction, nome: str):
        conteudo = pocoes.ler_entrada(nome)

        if conteudo is not None:
            entrada, tempo, rendimento = interpretar_pocao(conteudo)
            embeds = montar_embeds_pocao(entrada, nome, tempo, rendimento)
            lotes = agrupar_embeds(embeds)

            await interaction.response.send_message(embeds=lotes[0])

            for lote in lotes[1:]:
                await interaction.followup.send(embeds=lote)

            return

        if normalizar_rotulo(nome) != normalizar_rotulo(NOME_INDICE_POCOES):
            await interaction.response.send_message(
                f"**{nome}** não foi encontrada na biblioteca de Poções.",
                ephemeral=True,
            )
            return

        grupos = criar_grupos_indice_pocoes()

        if not grupos or not any(grupo.itens for grupo in grupos):
            await interaction.response.send_message(
                "Não há poções disponíveis na biblioteca.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)
        links = await localizar_links_oficiais(
            self.bot,
            NOME_INDICE_POCOES,
            grupos,
        )
        embeds = criar_embeds_indice(
            NOME_INDICE_POCOES,
            grupos,
            COR_EMBED_POCAO,
            links,
        )
        lotes = organizar_lotes_indice(NOME_INDICE_POCOES, grupos, embeds)
        await interaction.edit_original_response(
            content=(
                f"### {lotes[0].rotulo}\n"
                "Clique no nome desejado para abrir sua mensagem oficial na biblioteca."
            ),
            embeds=lotes[0].embeds,
        )

        for lote in lotes[1:]:
            await interaction.followup.send(
                content=f"### {lote.rotulo}",
                embeds=lote.embeds,
            )
