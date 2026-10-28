from pathlib import Path
from urllib.parse import urlsplit

import discord
from discord import app_commands
from discord.ext import commands

from utils.biblioteca import BibliotecaCategoria, EntradaBiblioteca, normalizar_rotulo


criaturas = BibliotecaCategoria("criaturas")
COR_EMBED_TCM = 0x321F0B
LIMITE_CAMPO_EMBED = 1024
LIMITE_TOTAL_EMBEDS = 6000
MAXIMO_CAMPOS_POR_EMBED = 4
MAXIMO_EMBEDS_POR_MENSAGEM = 10
EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".webp"}
ROTULOS_IDENTIDADE = {
    "origem": "Origem",
    "classificacao": "Classificação",
    "periculosidade": "Periculosidade",
    "ano de estudo": "Ano de Estudo",
    "tipo de aula": "Tipo de Aula",
}
ROTULOS_OCULTOS = {"imagem", *ROTULOS_IDENTIDADE}
GRUPOS_CAMPOS = [
    [
        ("aparencia", "Aparência", False),
        ("habitat e distribuicao", "Habitat e Distribuição", True),
        ("alimentacao", "Alimentação", True),
        ("comportamento", "Comportamento", False),
    ],
    [
        (
            "acasalamento e homoafetividade",
            "Acasalamento e Homoafetividade",
            False,
        ),
        (
            "sociedade e escravidao",
            "Sociedade e Escravidão",
            False,
        ),
        ("ciclo de vida", "Ciclo de Vida", False),
        ("interacao e manejo", "Interação e Manejo", True),
        ("defesas e riscos", "Defesas e Riscos", True),
        ("aptidoes", "Aptidões", False),
    ],
    [
        ("utilidades", "Utilidades", True),
        ("rastros e sinais", "Rastros e Sinais", True),
    ],
]
ROTULOS_ORGANIZADOS = {
    rotulo
    for grupo in GRUPOS_CAMPOS
    for rotulo, _, _ in grupo
}
PERICULOSIDADE_VISUAL = {
    "X": ("Ⅹ", "Entediante"),
    "XX": ("ⅩⅩ", "Inofensivo / pode ser domesticado"),
    "XXX": ("ⅩⅩⅩ", "Bruxo competente pode enfrentar"),
    "XXXX": (
        "ⅩⅩⅩⅩ",
        "Perigoso / necessita de conhecimento especializado",
    ),
    "XXXXX": (
        "ⅩⅩⅩⅩⅩ",
        "Matador de bruxos / impossível de treinar ou domesticar",
    ),
}


def campos_normalizados(entrada: EntradaBiblioteca) -> dict[str, str]:
    return {
        normalizar_rotulo(rotulo): valor.strip()
        for rotulo, valor in entrada.campos.items()
    }


def buscar_nomes_criaturas(termo: str = "") -> list[str]:
    termo_normalizado = normalizar_rotulo(termo)

    return [
        nome
        for nome in criaturas.listar_nomes()
        if not termo_normalizado
        or termo_normalizado in normalizar_rotulo(nome)
    ][:25]


def encontrar_imagem(entrada: EntradaBiblioteca) -> Path | str | None:
    campos = campos_normalizados(entrada)
    valor_imagem = campos.get("imagem", "")

    if not valor_imagem:
        return None

    url = urlsplit(valor_imagem)
    if (
        url.scheme.casefold() in {"http", "https"}
        and url.netloc
        and len(valor_imagem) <= 2048
    ):
        return valor_imagem

    caminho_relativo = Path(valor_imagem)

    if caminho_relativo.is_absolute():
        return None

    raiz_criaturas = criaturas.pasta.resolve()
    caminho_imagem = (raiz_criaturas / caminho_relativo).resolve()

    try:
        caminho_imagem.relative_to(raiz_criaturas)
    except ValueError:
        return None

    if (
        not caminho_imagem.is_file()
        or caminho_imagem.suffix.casefold() not in EXTENSOES_IMAGEM
    ):
        return None

    return caminho_imagem


def dividir_texto_campo(texto: str) -> list[str]:
    restante = texto.strip()
    partes: list[str] = []

    while len(restante) > LIMITE_CAMPO_EMBED:
        corte = restante.rfind("\n\n", 0, LIMITE_CAMPO_EMBED + 1)

        if corte == -1:
            corte = restante.rfind("\n", 0, LIMITE_CAMPO_EMBED + 1)

        if corte == -1:
            corte = restante.rfind(" ", 0, LIMITE_CAMPO_EMBED + 1)

        if corte <= 0:
            corte = LIMITE_CAMPO_EMBED

        partes.append(restante[:corte].strip())
        restante = restante[corte:].strip()

    if restante:
        partes.append(restante)

    return partes


def formatar_como_citacao(texto: str) -> str:
    return "\n".join(
        f"> {linha}"
        for linha in texto.strip().splitlines()
        if linha.strip()
    )


def formatar_cabecalho(nome: str) -> str:
    return f"**{nome}**"


def formatar_cabecalho_thread(nome: str, periculosidade: str) -> str:
    valor_normalizado = periculosidade.strip().upper().replace(" ", "")
    simbolo, descricao = PERICULOSIDADE_VISUAL.get(
        valor_normalizado,
        (periculosidade, "Classificação não catalogada"),
    )

    return (
        "## ══════◄••:feet:••►══════\n"
        f"## {nome}  \n"
        f"**Classificação {simbolo}** • *{descricao}*\n"
        "## ══════◄••:feet:••►══════"
    )


def tamanho_embed(embed: discord.Embed) -> int:
    total = len(embed.title or "") + len(embed.description or "")
    total += len(embed.footer.text or "")

    for campo in embed.fields:
        total += len(campo.name) + len(campo.value)

    return total


def tamanho_total_embeds(embeds: list[discord.Embed]) -> int:
    return sum(tamanho_embed(embed) for embed in embeds)


def montar_embeds_criatura(
    entrada: EntradaBiblioteca,
    nome: str,
    url_imagem: str,
) -> list[discord.Embed]:
    campos = campos_normalizados(entrada)
    titulo = entrada.titulo or nome
    cabecalho = discord.Embed(
        description=formatar_cabecalho(titulo),
        color=COR_EMBED_TCM,
    )
    cabecalho.set_image(url=url_imagem)
    identidade = discord.Embed(
        description=entrada.descricao or None,
        color=COR_EMBED_TCM,
    )

    for rotulo, nome_visivel in ROTULOS_IDENTIDADE.items():
        valor = campos.get(rotulo)

        if valor:
            identidade.add_field(name=nome_visivel, value=valor, inline=True)

    embeds = [cabecalho, identidade]

    for grupo in GRUPOS_CAMPOS:
        embed_grupo = discord.Embed(color=COR_EMBED_TCM)

        for rotulo, nome_visivel, inline in grupo:
            valor = campos.get(rotulo)

            if not valor:
                continue

            valor_formatado = formatar_como_citacao(valor)
            partes = dividir_texto_campo(valor_formatado)

            for parte in partes:
                embed_grupo.add_field(
                    name=nome_visivel,
                    value=parte,
                    inline=inline if len(partes) == 1 else False,
                )

        if embed_grupo.fields:
            embeds.append(embed_grupo)

    campos_extras = [
        (rotulo_original, valor)
        for rotulo_original, valor in entrada.campos.items()
        if normalizar_rotulo(rotulo_original)
        not in ROTULOS_OCULTOS | ROTULOS_ORGANIZADOS
        and valor.strip()
    ]

    if campos_extras:
        embed_extras = discord.Embed(color=COR_EMBED_TCM)

        for rotulo_original, valor in campos_extras:
            partes = dividir_texto_campo(formatar_como_citacao(valor))

            for parte in partes:
                if len(embed_extras.fields) >= MAXIMO_CAMPOS_POR_EMBED:
                    embeds.append(embed_extras)
                    embed_extras = discord.Embed(color=COR_EMBED_TCM)

                embed_extras.add_field(
                    name=rotulo_original,
                    value=parte,
                    inline=False,
                )

        if embed_extras.fields:
            embeds.append(embed_extras)

    return embeds


def agrupar_embeds(embeds: list[discord.Embed]) -> list[list[discord.Embed]]:
    lotes: list[list[discord.Embed]] = []
    lote_atual: list[discord.Embed] = []
    tamanho_atual = 0

    for embed in embeds:
        tamanho = tamanho_embed(embed)

        if lote_atual and (
            tamanho_atual + tamanho > LIMITE_TOTAL_EMBEDS
            or len(lote_atual) >= MAXIMO_EMBEDS_POR_MENSAGEM
        ):
            lotes.append(lote_atual)
            lote_atual = []
            tamanho_atual = 0

        lote_atual.append(embed)
        tamanho_atual += tamanho

    if lote_atual:
        lotes.append(lote_atual)

    return lotes


class Interagir(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def autocomplete_criaturas(
        self,
        interaction: discord.Interaction,
        atual: str,
    ) -> list[app_commands.Choice[str]]:
        nomes = buscar_nomes_criaturas(atual)
        return [app_commands.Choice(name=nome, value=nome) for nome in nomes]

    @app_commands.command(
        name="interagir",
        description="Abre a ficha de uma criatura mágica.",
    )
    @app_commands.describe(criatura="Nome da criatura mágica")
    @app_commands.autocomplete(criatura=autocomplete_criaturas)
    async def interagir(self, interaction: discord.Interaction, criatura: str):
        entrada = criaturas.carregar_entrada(criatura)

        if entrada is None:
            await interaction.response.send_message(
                f"**{criatura}** não foi encontrada na biblioteca de criaturas.",
                ephemeral=True,
            )
            return

        imagem = encontrar_imagem(entrada)

        if imagem is None:
            await interaction.response.send_message(
                f"A ficha de **{criatura}** foi encontrada, mas sua imagem não está disponível.",
                ephemeral=True,
            )
            return

        arquivo = None
        if isinstance(imagem, Path):
            nome_anexo = f"criatura{imagem.suffix.casefold()}"
            url_imagem = f"attachment://{nome_anexo}"
            arquivo = discord.File(imagem, filename=nome_anexo)
        else:
            url_imagem = imagem

        embeds = montar_embeds_criatura(entrada, criatura, url_imagem)

        if tamanho_total_embeds(embeds) > LIMITE_TOTAL_EMBEDS:
            await interaction.response.send_message(
                f"A ficha de **{criatura}** excede o limite de exibição e precisa ser revisada.",
                ephemeral=True,
            )
            return

        lotes = agrupar_embeds(embeds)
        await interaction.response.send_message(
            embeds=lotes[0],
            file=arquivo,
        )

        for lote in lotes[1:]:
            await interaction.followup.send(embeds=lote)
