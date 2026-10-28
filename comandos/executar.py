import re
from collections import defaultdict
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

from utils.biblioteca import (
    BibliotecaCategoria,
    EntradaBiblioteca,
    interpretar_markdown,
    normalizar_rotulo,
)
from utils.feiticos_combate import descricao_publica
from utils.publicacao_fichas import ErroPublicacaoFicha, carregar_destinos_fichas


feiticos = BibliotecaCategoria("feiti\u00e7os")
runas = BibliotecaCategoria("runas")
bindrunes = BibliotecaCategoria("bindrunes")
COR_EMBED_FEITICO = 14721000
COR_EMBED_RUNA = 14462035
LIMITE_AUTOCOMPLETE = 25
CORES_FEITICOS = {
    "defesa contra arte das trevas": 7922638,
    "transfiguracao": 7689136,
    "encantamentos": 14721000,
    "duelos": 2192040,
    "arte das trevas": 2097409,
    "trato de criaturas magicas": 3284747,
}
ROTULOS_FEITICO = {
    "categoria": ("Categoria:", True),
    "vertente": ("Vertente:", True),
    "ano de desbloqueio": ("Desbloqueio:", True),
    "grau de dificuldade": ("Grau de Dificuldade:", True),
    "corrupcao de alma": ("Corrup\u00e7\u00e3o de Alma:", False),
    "dificuldade por ano": ("Dificuldade por ano:", False),
    "modificador de barganha": ("Modificador de Barganha:", False),
}
ROTULOS_RUNA = {
    "palavras-chave": ("Palavras-chave:", True),
    "categoria": ("Categoria:", True),
    "ætt": ("Ætt:", True),
    "equivalente": ("Equivalente:", True),
    "grau de dificuldade": ("Grau de Dificuldade:", True),
    "capacidades magicas": ("Capacidades Mágicas:", False),
    "tipo de uso": ("Tipo de uso:", True),
    "preparacao": ("Preparação:", False),
    "ativacao": ("Ativação:", False),
    "materiais": ("Materiais:", False),
    "alcance": ("Alcance:", True),
    "area": ("Área:", True),
    "duracao": ("Duração:", True),
    "resistencia": ("Resistência:", False),
    "rompimento": ("Rompimento:", False),
    "falha": ("Falha:", False),
}
ROTULOS_BINDRUNA = {
    "runas utilizadas": ("Runas Utilizadas:", False),
    "categoria": ("Categoria:", True),
    "grau de dificuldade": ("Grau de Dificuldade:", True),
}
SEPARADOR_EMBEDS = "---"
ALIASES_INDICE = {
    "dcat": "defesa contra arte das trevas",
    "defesa contra as artes das trevas": "defesa contra arte das trevas",
    "trevas": "arte das trevas",
    "runas antigas": "runas",
    "bindruna": "bindrunes",
}
ORDEM_AETTS = {
    "primeiro aett": 1,
    "segundo aett": 2,
    "terceiro aett": 3,
}
ORDEM_CATEGORIAS_BINDRUNA = {
    "sobreposta": 1,
    "haste": 2,
    "radial": 3,
}
VERTENTES_TREVAS = (
    "Maldições",
    "Necromancia",
    "Magia Ritualística",
    "Alquimia Sombria",
    "Magia de Controle",
    "Magia de Destruição",
    "Magia de Ilusão",
)
ORDEM_VERTENTES_TREVAS = {
    "maldicoes": 1,
    "necromancia": 2,
    "magia ritualistica": 3,
    "alquimia sombria": 4,
    "magia de controle": 5,
    "magia de destruicao": 6,
    "magia de ilusao": 7,
}
ORDEM_RITUAIS = {
    "comunhao": 1,
    "invocacao": 2,
    "evocacao": 3,
    "pactos": 4,
    "consagracao profana": 5,
    "apoteose": 6,
}
VERTENTES_MALDICOES = {
    "maldicoes imperdoaveis",
    "maldicoes de sangue",
}


@dataclass(frozen=True)
class ItemIndice:
    nome: str
    entrada: EntradaBiblioteca
    tipo: str


@dataclass(frozen=True)
class GrupoIndice:
    titulo: str
    itens: list[ItemIndice]


@dataclass(frozen=True)
class LoteIndice:
    rotulo: str
    embeds: list[discord.Embed]


def escolher_cor_embed(campos: dict[str, str]) -> int:
    categoria = campos.get("categoria", "")
    return CORES_FEITICOS.get(normalizar_rotulo(categoria), COR_EMBED_FEITICO)


def dividir_descricao_em_embeds(descricao: str) -> list[str]:
    partes = []

    for parte in descricao.split(f"\n{SEPARADOR_EMBEDS}\n"):
        parte = parte.strip()

        if parte:
            partes.append(parte)

    return partes or [""]


def campos_normalizados(entrada: EntradaBiblioteca) -> dict[str, str]:
    return {
        normalizar_rotulo(rotulo): valor
        for rotulo, valor in entrada.campos.items()
    }


def carregar_todos_feiticos() -> list[ItemIndice]:
    itens = []

    for arquivo in feiticos.listar_arquivos():
        entrada = interpretar_markdown(arquivo.read_text(encoding="utf-8"))
        itens.append(ItemIndice(arquivo.stem, entrada, "feitico"))

    return itens


def carregar_todas_runas() -> list[ItemIndice]:
    itens = []

    for arquivo in runas.listar_arquivos():
        entrada = interpretar_markdown(arquivo.read_text(encoding="utf-8"))
        aett = extrair_aett(entrada.descricao)

        if aett:
            itens.append(ItemIndice(arquivo.stem, entrada, "runa"))

    return itens


def carregar_todas_bindrunes() -> list[ItemIndice]:
    itens = []

    for arquivo in bindrunes.listar_arquivos():
        entrada = interpretar_markdown(arquivo.read_text(encoding="utf-8"))
        itens.append(ItemIndice(arquivo.stem, entrada, "bindruna"))

    return itens


def listar_artes_magicas() -> dict[str, str]:
    artes = {}

    for item in carregar_todos_feiticos():
        categoria = campos_normalizados(item.entrada).get("categoria", "").strip()

        if categoria:
            artes.setdefault(normalizar_rotulo(categoria), categoria)

    return artes


def nomes_indices() -> list[str]:
    nomes = list(listar_artes_magicas().values())
    nomes.extend(("Runas Antigas", "Bindrunes"))
    return sorted(nomes, key=str.casefold)


def buscar_nomes_execucao(termo: str = "") -> list[str]:
    termo_normalizado = termo.casefold().strip()
    nomes_por_chave: dict[str, str] = {}

    for nome in nomes_indices():
        if termo_normalizado and termo_normalizado not in nome.casefold():
            continue

        nomes_por_chave.setdefault(nome.casefold(), nome)

    for biblioteca in (bindrunes, runas, feiticos):
        for nome in biblioteca.listar_nomes():
            if termo_normalizado and termo_normalizado not in nome.casefold():
                continue

            nomes_por_chave.setdefault(nome.casefold(), nome)

    return sorted(
        nomes_por_chave.values(),
        key=str.casefold,
    )[:LIMITE_AUTOCOMPLETE]


def carregar_entrada_execucao(nome: str):
    entrada_bindruna = bindrunes.carregar_entrada(nome)

    if entrada_bindruna is not None:
        return entrada_bindruna, "bindruna"

    entrada_runa = runas.carregar_entrada(nome)

    if entrada_runa is not None:
        return entrada_runa, "runa"

    entrada_feitico = feiticos.carregar_entrada(nome)

    if entrada_feitico is not None:
        return entrada_feitico, "feitico"

    return None, None


def descricao_contem_titulo(descricao: str, titulo: str) -> bool:
    return f"**{titulo}**".casefold() in descricao[:500].casefold()


def criar_embeds_entrada(
    entrada: EntradaBiblioteca,
    tipo_entrada: str,
    nome: str,
) -> list[discord.Embed]:
    campos_por_rotulo = campos_normalizados(entrada)
    eh_bindruna = tipo_entrada == "bindruna"
    eh_runa = tipo_entrada == "runa"
    cor = (
        COR_EMBED_RUNA
        if eh_runa or eh_bindruna
        else escolher_cor_embed(campos_por_rotulo)
    )

    if eh_bindruna:
        embed = discord.Embed(
            title=entrada.titulo or nome,
            color=cor,
        )

        for rotulo, (nome_campo, inline) in ROTULOS_BINDRUNA.items():
            valor = campos_por_rotulo.get(rotulo)

            if valor:
                embed.add_field(name=nome_campo, value=valor, inline=inline)

        if entrada.descricao:
            embed.add_field(
                name="Descrição:",
                value=entrada.descricao,
                inline=False,
            )

        capacidades = campos_por_rotulo.get("capacidades magicas")

        if capacidades:
            embed.add_field(
                name="Capacidades Mágicas:",
                value=capacidades,
                inline=False,
            )

        return [embed]

    descricao_renderizada = (
        descricao_publica(entrada.descricao, entrada.perfil_combate)
        if not eh_runa and not eh_bindruna
        else entrada.descricao
    )
    descricoes = dividir_descricao_em_embeds(descricao_renderizada)
    titulo_primeiro_embed = entrada.titulo or nome

    if eh_runa and descricao_contem_titulo(entrada.descricao, titulo_primeiro_embed):
        titulo_primeiro_embed = None

    embeds = [
        discord.Embed(
            title=titulo_primeiro_embed if indice == 0 else None,
            description=descricao,
            color=cor,
        )
        for indice, descricao in enumerate(descricoes)
    ]

    rotulos_visiveis = ROTULOS_RUNA if eh_runa else ROTULOS_FEITICO
    eh_ritualistica = (
        normalizar_rotulo(campos_por_rotulo.get("vertente", ""))
        == "magia ritualistica"
    )
    embed_campos = embeds[0]

    if eh_ritualistica:
        embed_campos = discord.Embed(color=cor)
        embeds.append(embed_campos)

    for rotulo, (nome_campo, inline) in rotulos_visiveis.items():
        valor = campos_por_rotulo.get(rotulo)

        if valor:
            if eh_ritualistica and rotulo in {
                "dificuldade por ano",
                "modificador de barganha",
            }:
                inline = True

            embed_campos.add_field(name=nome_campo, value=valor, inline=inline)

    return embeds


def normalizar_ano(ano: str) -> str:
    correspondencia = re.search(r"\b([1-7])\s*[º°o]?\s*ano\b", ano, re.IGNORECASE)

    if correspondencia:
        return f"{correspondencia.group(1)}º Ano"

    return ano.strip() or "Sem ano de desbloqueio"


def extrair_aett(descricao: str) -> str | None:
    correspondencia = re.search(
        r"Runa do ((?:Primeiro|Segundo|Terceiro) Ætt de [^*_\r\n]+)",
        descricao,
        re.IGNORECASE,
    )

    if correspondencia:
        return correspondencia.group(1).strip()

    return None


def chave_ordenacao_grupo(titulo: str) -> tuple[int, str]:
    if normalizar_rotulo(titulo) == "transfiguracao":
        return 0, titulo.casefold()

    ano = re.match(r"([1-7])º Ano$", titulo)

    if ano:
        return int(ano.group(1)), titulo.casefold()

    titulo_normalizado = normalizar_rotulo(titulo).replace("æ", "ae")

    if titulo_normalizado in ORDEM_CATEGORIAS_BINDRUNA:
        return ORDEM_CATEGORIAS_BINDRUNA[titulo_normalizado], titulo.casefold()

    if titulo_normalizado in ORDEM_VERTENTES_TREVAS:
        return ORDEM_VERTENTES_TREVAS[titulo_normalizado], titulo.casefold()

    for prefixo, ordem in ORDEM_AETTS.items():
        if titulo_normalizado.startswith(prefixo):
            return ordem, titulo.casefold()

    return 99, titulo.casefold()


def chave_ordenacao_item(grupo: str, item: ItemIndice) -> tuple[int, str]:
    if normalizar_rotulo(grupo) == "magia ritualistica":
        ordem = ORDEM_RITUAIS.get(normalizar_rotulo(item.nome), 99)
        return ordem, item.nome.casefold()

    return 99, item.nome.casefold()


def criar_grupos_indice(nome: str) -> tuple[str, list[GrupoIndice], int] | None:
    nome_normalizado = normalizar_rotulo(nome)
    nome_normalizado = ALIASES_INDICE.get(nome_normalizado, nome_normalizado)
    grupos: dict[str, list[ItemIndice]] = defaultdict(list)

    if nome_normalizado == "runas":
        for item in carregar_todas_runas():
            aett = extrair_aett(item.entrada.descricao)

            if aett:
                grupos[aett].append(item)

        titulo_indice = "Runas Antigas"
        cor = COR_EMBED_RUNA
    elif nome_normalizado == "bindrunes":
        for item in carregar_todas_bindrunes():
            campos = campos_normalizados(item.entrada)
            categoria = campos.get("categoria", "").strip() or "Sem categoria"
            grupos[categoria].append(item)

        titulo_indice = "Bindrunes"
        cor = COR_EMBED_RUNA
    else:
        artes = listar_artes_magicas()

        if nome_normalizado not in artes:
            return None

        titulo_indice = artes[nome_normalizado]

        if nome_normalizado == "arte das trevas":
            for vertente in VERTENTES_TREVAS:
                grupos[vertente]

        for item in carregar_todos_feiticos():
            campos = campos_normalizados(item.entrada)

            if normalizar_rotulo(campos.get("categoria", "")) != nome_normalizado:
                continue

            if nome_normalizado == "arte das trevas":
                grupo = campos.get("vertente", "").strip() or "Sem vertente"

                if normalizar_rotulo(grupo) in VERTENTES_MALDICOES:
                    grupo = "Maldições"
            else:
                ano_desbloqueio = campos.get("ano de desbloqueio", "")

                if (
                    nome_normalizado == "transfiguracao"
                    and normalizar_rotulo(ano_desbloqueio) == "aulas de transfiguracao"
                ):
                    grupo = titulo_indice
                else:
                    grupo = normalizar_ano(ano_desbloqueio)

            grupos[grupo].append(item)

        cor = CORES_FEITICOS.get(nome_normalizado, COR_EMBED_FEITICO)

    grupos_ordenados = [
        GrupoIndice(
            titulo=grupo,
            itens=sorted(
                itens,
                key=lambda item: chave_ordenacao_item(grupo, item),
            ),
        )
        for grupo, itens in sorted(
            grupos.items(),
            key=lambda par: chave_ordenacao_grupo(par[0]),
        )
    ]
    return titulo_indice, grupos_ordenados, cor


def criar_embeds_indice(
    titulo_indice: str,
    grupos: list[GrupoIndice],
    cor: int,
    links: dict[tuple[str, str], str] | None = None,
) -> list[discord.Embed]:
    links = links or {}
    embeds = []
    for grupo in grupos:
        chave_grupo = normalizar_rotulo(grupo.titulo)
        nomes = (
            "\n".join(
                (
                    f"• [{item.nome.replace('[', r'\[').replace(']', r'\]')}]"
                    f"({links[(chave_grupo, normalizar_rotulo(item.nome))]})"
                    if (chave_grupo, normalizar_rotulo(item.nome)) in links
                    else f"• {item.nome}"
                )
                for item in grupo.itens
            )
            or "Nenhum feitiço disponível."
        )
        titulo_embed = (
            titulo_indice
            if normalizar_rotulo(grupo.titulo) == normalizar_rotulo(titulo_indice)
            else f"{titulo_indice} — {grupo.titulo}"
        )
        embeds.append(
            discord.Embed(
                title=titulo_embed,
                description=nomes,
                color=cor,
            )
        )

    return embeds


def agrupar_embeds_indice(embeds: list[discord.Embed]) -> list[list[discord.Embed]]:
    lotes: list[list[discord.Embed]] = []
    atual: list[discord.Embed] = []
    tamanho_atual = 0
    for embed in embeds:
        tamanho = len(embed)
        if tamanho > 6000:
            raise ValueError("Uma das páginas do índice ultrapassou o limite do Discord.")
        if atual and (len(atual) >= 10 or tamanho_atual + tamanho > 6000):
            lotes.append(atual)
            atual = []
            tamanho_atual = 0
        atual.append(embed)
        tamanho_atual += tamanho
    if atual:
        lotes.append(atual)
    if (
        len(lotes) > 1
        and len(lotes[-1]) == 1
        and len(lotes[-2]) > 1
        and sum(len(embed) for embed in lotes[-1]) + len(lotes[-2][-1]) <= 6000
    ):
        lotes[-1].insert(0, lotes[-2].pop())
    return lotes


def faixa_progressao(grupo: GrupoIndice) -> tuple[int, str] | None:
    correspondencia = re.match(
        r"^\s*([1-7])\s*[º°o]?\s*Ano\s*$",
        grupo.titulo,
        re.IGNORECASE,
    )
    if not correspondencia:
        return None
    ano = int(correspondencia.group(1))
    if ano <= 2:
        return 1, "Básico — 1º e 2º Ano"
    if ano <= 5:
        return 2, "Intermediário — 3º ao 5º Ano"
    return 3, "Avançado — 6º e 7º Ano"


def organizar_lotes_indice(
    titulo_indice: str,
    grupos: list[GrupoIndice],
    embeds: list[discord.Embed],
) -> list[LoteIndice]:
    pares = list(zip(grupos, embeds))
    tem_progressao = any(faixa_progressao(grupo) is not None for grupo, _ in pares)
    if not tem_progressao:
        lotes = agrupar_embeds_indice(embeds)
        return [
            LoteIndice(
                titulo_indice if len(lotes) == 1 else f"{titulo_indice} — {indice}/{len(lotes)}",
                lote,
            )
            for indice, lote in enumerate(lotes, 1)
        ]

    faixas: dict[tuple[int, str], list[discord.Embed]] = defaultdict(list)
    extras: list[discord.Embed] = []
    for grupo, embed in pares:
        faixa = faixa_progressao(grupo)
        if faixa is None:
            extras.append(embed)
        else:
            faixas[faixa].append(embed)

    resultado: list[LoteIndice] = []
    if extras:
        lotes_extras = agrupar_embeds_indice(extras)
        resultado.extend(
            LoteIndice(
                "Mecânicas próprias"
                if len(lotes_extras) == 1
                else f"Mecânicas próprias — {indice}/{len(lotes_extras)}",
                lote,
            )
            for indice, lote in enumerate(lotes_extras, 1)
        )
    for ordem, rotulo in sorted(faixas):
        lotes_faixa = agrupar_embeds_indice(faixas[(ordem, rotulo)])
        resultado.extend(
            LoteIndice(
                rotulo if len(lotes_faixa) == 1 else f"{rotulo} — {indice}/{len(lotes_faixa)}",
                lote,
            )
            for indice, lote in enumerate(lotes_faixa, 1)
        )
    return resultado


def destino_grupo_indice(
    titulo_indice: str,
    grupo: GrupoIndice,
    destinos: dict[tuple[str, str], int],
) -> int | None:
    titulo_normalizado = normalizar_rotulo(titulo_indice)
    if titulo_normalizado == "bindrunes":
        secao = "Runas Antigas"
        chave = "Bindrunes"
    else:
        secao = titulo_indice
        chave = grupo.titulo
    return destinos.get((normalizar_rotulo(secao), normalizar_rotulo(chave)))


def titulos_publicados(mensagem: discord.Message) -> set[str]:
    titulos = {
        normalizar_rotulo(embed.title)
        for embed in mensagem.embeds
        if embed.title
    }
    for linha in mensagem.content.splitlines():
        correspondencia = re.match(r"^#{1,6}\s+(.+?)\s*$", linha.strip())
        if correspondencia:
            titulo = correspondencia.group(1).strip().strip("*_")
            titulo = re.sub(r"^[^\wÀ-ÿ]+", "", titulo).strip()
            if titulo:
                titulos.add(normalizar_rotulo(titulo))
    return titulos


async def localizar_links_oficiais(
    bot: commands.Bot,
    titulo_indice: str,
    grupos: list[GrupoIndice],
) -> dict[tuple[str, str], str]:
    try:
        destinos = carregar_destinos_fichas()
    except ErroPublicacaoFicha:
        return {}

    esperados_por_thread: dict[int, dict[str, list[tuple[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for grupo in grupos:
        thread_id = destino_grupo_indice(titulo_indice, grupo, destinos)
        if thread_id is None:
            continue
        chave_grupo = normalizar_rotulo(grupo.titulo)
        for item in grupo.itens:
            chave_item = (chave_grupo, normalizar_rotulo(item.nome))
            nomes = {normalizar_rotulo(item.nome)}
            if item.entrada.titulo:
                nomes.add(normalizar_rotulo(item.entrada.titulo))
            for nome in nomes:
                esperados_por_thread[thread_id][nome].append(chave_item)

    links: dict[tuple[str, str], str] = {}
    for thread_id, esperados in esperados_por_thread.items():
        canal = bot.get_channel(thread_id)
        if canal is None:
            try:
                canal = await bot.fetch_channel(thread_id)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                continue
        if not hasattr(canal, "history"):
            continue
        try:
            async for mensagem in canal.history(limit=None):
                for titulo in titulos_publicados(mensagem):
                    correspondencias = esperados.get(titulo, [])
                    if len(correspondencias) == 1:
                        links.setdefault(correspondencias[0], mensagem.jump_url)
        except (discord.Forbidden, discord.HTTPException):
            continue
    return links


class Executar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def autocomplete_feiticos(
        self,
        interaction: discord.Interaction,
        atual: str,
    ) -> list[app_commands.Choice[str]]:
        nomes = buscar_nomes_execucao(atual)
        return [app_commands.Choice(name=nome, value=nome) for nome in nomes]

    @app_commands.command(
        name="executar",
        description="Auxilia na execução de um feitiço, runa ou bindruna.",
    )
    @app_commands.describe(nome="Nome da arte mágica, feitiço, runa ou bindruna")
    @app_commands.autocomplete(nome=autocomplete_feiticos)
    async def feitico(self, interaction: discord.Interaction, nome: str):
        entrada, tipo_entrada = carregar_entrada_execucao(nome)

        if entrada is not None:
            embeds = criar_embeds_entrada(entrada, tipo_entrada, nome)
            await interaction.response.send_message(embeds=embeds)
            return

        indice = criar_grupos_indice(nome)

        if indice is None:
            await interaction.response.send_message(
                f"**{nome}** não foi encontrado na biblioteca.",
                ephemeral=True,
            )
            return

        titulo_indice, grupos, cor = indice
        if not any(grupo.itens for grupo in grupos):
            await interaction.response.send_message(
                f"Não há entradas disponíveis em **{titulo_indice}**.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)
        links = await localizar_links_oficiais(self.bot, titulo_indice, grupos)
        embeds = criar_embeds_indice(titulo_indice, grupos, cor, links)
        lotes = organizar_lotes_indice(titulo_indice, grupos, embeds)
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
