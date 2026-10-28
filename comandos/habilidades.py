import re
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from utils.biblioteca import EntradaBiblioteca, interpretar_markdown, normalizar_rotulo


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_HABILIDADES = RAIZ_PROJETO / "biblioteca" / "Habilidades"
LIMITE_AUTOCOMPLETE = 25
LIMITE_CAMPO = 1024
LIMITE_TOTAL_MENSAGEM = 6000

CATEGORIAS_HABILIDADE = {
    "heranca_sanguinea": {
        "nome": "Herança Sanguínea",
        "pasta": "Herança Sanguínea",
        "emoji": "🧬",
    },
    "origem_magica": {
        "nome": "Origem Mágica",
        "pasta": "Origem Mágica",
        "emoji": "✨",
    },
    "especializacao": {
        "nome": "Especialização",
        "pasta": "Especialização",
        "emoji": "🎓",
    },
}

ORDEM_HABILIDADES = {
    "heranca_sanguinea": (
        "Maledictus", "Meio-Banshee", "Parte-Vampiro", "Sangue de Gigante",
        "Sangue Veela", "Nascido-Trouxa", "Meio-Sangue", "Sangue Puro",
    ),
    "origem_magica": (
        "Animago", "Clarividência", "Experiência Alquímica", "Faunancião",
        "Fitometria", "Legilimência", "Licantropia", "Maestro", "Magia Ancestral",
        "Magia por Contato Visual", "Metamorfomagia", "Oclumência", "Ofidioglossia",
        "Oneiro", "Pseudo-síndrome do Desaparecimento", "Sacrifício à Mimir",
        "Sensorial", "Troca Peles",
    ),
    "especializacao": (
        "Mestria em (Nome do Feitiço)", "Pistoleiro", "Mestre Espadachim",
        "Aparência Inofensiva", "Presença Marcante", "Hábil e Experiente",
        "Estereótipo da Popularidade", "Sangue nos Olhos // Combo", "Tecnomagia",
        "Levitação", "Aparatação // Desaparatação", "Projetar Magias Defletidas",
        "Magia Manual", "Magia Não-Verbal", "Patrono Mágico", "Expecto Patronum",
        "A Arte da Arquemagia", "Guardião", "Feiticeiro", "Magizoologista Nato",
        "Gênio Alquímico", "Medibruxaria Sensorial", "Prodígio do Quadribol",
        "Curandeiro(a) e/ou Medibruxo(a)", "Rei", "Poeta // Artista", "Soldado",
        "Duelista Exímio", "Detetive", "Devorador de Livros", "Bom de Briga",
        "Brutamontes", "Valente", "Sedutor", "Charlatão", "Sortudo",
    ),
}

EMOJIS_HABILIDADES = {
    "heranca_sanguinea": {
        "Maledictus": "🐱💛",
        "Meio-Banshee": "👻☠️",
        "Parte-Vampiro": "🩸🦇",
        "Sangue de Gigante": "💥💪",
        "Sangue Veela": "💖🔥",
        "Nascido-Trouxa": "🩸🧬",
        "Meio-Sangue": "<:Halfblood:992497097997820067>🧬",
        "Sangue Puro": "<:BlueBlood:992497074421645382>🧬",
    },
    "origem_magica": {
        "Animago": "🐰", "Clarividência": "🔮", "Experiência Alquímica": "🧪",
        "Faunancião": "🗣️", "Fitometria": "🌿", "Legilimência": "💭",
        "Licantropia": "🐺", "Maestro": "🎻", "Magia Ancestral": "🕯️",
        "Magia por Contato Visual": "👁️‍🗨️", "Metamorfomagia": "💄",
        "Oclumência": "🚫", "Ofidioglossia": "🐍", "Oneiro": "🌙",
        "Pseudo-síndrome do Desaparecimento": "🫥", "Sacrifício à Mimir": "👁️",
        "Sensorial": "🪬", "Troca Peles": "🦋",
    },
    "especializacao": {
        "Mestria em (Nome do Feitiço)": "⚡",
        "Pistoleiro": "<:pistol:1281255645529505898>",
        "Mestre Espadachim": "🤺", "Aparência Inofensiva": "🐨",
        "Presença Marcante": "😎", "Hábil e Experiente": "🔁",
        "Estereótipo da Popularidade": "🫦", "Sangue nos Olhos // Combo": "🧨",
        "Tecnomagia": "💻", "Levitação": "🍃", "Aparatação // Desaparatação": "💨",
        "Projetar Magias Defletidas": "🏓", "Magia Manual": "🫵",
        "Magia Não-Verbal": "🙊", "Patrono Mágico": "🦄", "Expecto Patronum": "💫",
        "A Arte da Arquemagia": "💡", "Guardião": "🛡️", "Feiticeiro": "🪄",
        "Magizoologista Nato": "🐾", "Gênio Alquímico": "💎",
        "Medibruxaria Sensorial": "🪔", "Prodígio do Quadribol": "🏏",
        "Curandeiro(a) e/ou Medibruxo(a)": "🌿", "Rei": "👑",
        "Poeta // Artista": "❤️‍🩹", "Soldado": "🗡️", "Duelista Exímio": "⚔️",
        "Detetive": "🔎", "Devorador de Livros": "📚", "Bom de Briga": "👊",
        "Brutamontes": "💪", "Valente": "🤬", "Sedutor": "❤️‍🔥",
        "Charlatão": "🥸", "Sortudo": "🍀",
    },
}

ROTULOS_THREAD_HABILIDADE = {
    "heranca_sanguinea": "Linhagem Sanguínea",
    "origem_magica": "Origem Mágica",
    "especializacao": "Especialização",
}


def chave_categoria_habilidade(valor: str) -> str:
    alvo = normalizar_rotulo(valor)
    for chave, dados in CATEGORIAS_HABILIDADE.items():
        candidatos = {normalizar_rotulo(chave), normalizar_rotulo(str(dados["nome"])), normalizar_rotulo(str(dados["pasta"]))}
        if chave == "heranca_sanguinea":
            candidatos.add(normalizar_rotulo("Linhagem Sanguínea"))
        if alvo in candidatos:
            return chave
    raise ValueError("Categoria de habilidade inválida.")


def emoji_habilidade(categoria: str, nome: str) -> str:
    chave = chave_categoria_habilidade(categoria)
    return EMOJIS_HABILIDADES.get(chave, {}).get(nome, str(CATEGORIAS_HABILIDADE[chave]["emoji"]))


def formatar_cabecalho_habilidade(nome: str, categoria: str) -> str:
    chave = chave_categoria_habilidade(categoria)
    emoji_item = emoji_habilidade(chave, nome)
    emoji_categoria = str(CATEGORIAS_HABILIDADE[chave]["emoji"])
    rotulo = ROTULOS_THREAD_HABILIDADE[chave]
    return (
        f"## ══════◄••{emoji_categoria}••►══════\n"
        f"## {emoji_item} {nome}\n"
        f"_{rotulo}_\n"
        f"## ══════◄••{emoji_categoria}••►══════"
    )


def ordenar_nomes_habilidades(chave: str, nomes: list[str]) -> list[str]:
    ordem = {normalizar_rotulo(nome): indice for indice, nome in enumerate(ORDEM_HABILIDADES.get(chave, ())) }
    limite = len(ordem)
    return sorted(nomes, key=lambda nome: (ordem.get(normalizar_rotulo(nome), limite), nome.casefold()))


def dados_categoria(chave: str) -> dict[str, object]:
    dados = CATEGORIAS_HABILIDADE.get(chave)
    if dados is None:
        raise ValueError("Categoria de habilidade inválida.")
    return dados


def pasta_categoria(chave: str) -> Path:
    return PASTA_HABILIDADES / str(dados_categoria(chave)["pasta"])


def listar_habilidades(
    chave: str,
    termo: str = "",
    limite: int | None = LIMITE_AUTOCOMPLETE,
) -> list[str]:
    pasta = pasta_categoria(chave)
    if not pasta.is_dir():
        return []

    termo_normalizado = normalizar_rotulo(termo)
    nomes = []
    for arquivo in pasta.glob("*.md"):
        entrada = interpretar_markdown(arquivo.read_text(encoding="utf-8-sig"))
        nomes.append(entrada.titulo or arquivo.stem)
    nomes = ordenar_nomes_habilidades(chave, nomes)
    encontrados = [
        nome
        for nome in nomes
        if not termo_normalizado or termo_normalizado in normalizar_rotulo(nome)
    ]
    return encontrados[:limite] if limite is not None else encontrados


def encontrar_habilidade(chave: str, nome: str) -> Path | None:
    nome_normalizado = normalizar_rotulo(nome)
    for arquivo in pasta_categoria(chave).glob("*.md"):
        entrada = interpretar_markdown(arquivo.read_text(encoding="utf-8-sig"))
        if (
            normalizar_rotulo(arquivo.stem) == nome_normalizado
            or normalizar_rotulo(entrada.titulo) == nome_normalizado
        ):
            return arquivo
    return None


def carregar_habilidade(chave: str, nome: str) -> EntradaBiblioteca | None:
    arquivo = encontrar_habilidade(chave, nome)
    if arquivo is None:
        return None
    return interpretar_markdown(arquivo.read_text(encoding="utf-8-sig"))


def campos_normalizados(entrada: EntradaBiblioteca) -> dict[str, str]:
    return {
        normalizar_rotulo(rotulo): valor.strip()
        for rotulo, valor in entrada.campos.items()
    }


def custo_xp_habilidade(entrada: EntradaBiblioteca) -> int | None:
    campos = campos_normalizados(entrada)
    for rotulo in ("custo de aquisicao", "custo por evolucao", "custo de xp"):
        valor = campos.get(rotulo, "")
        numeros = "".join(caractere for caractere in valor if caractere.isdigit())
        if numeros:
            return int(numeros)
    return None


def dividir_texto(texto: str) -> list[str]:
    restante = texto.strip()
    partes: list[str] = []
    while len(restante) > LIMITE_CAMPO:
        corte = restante.rfind("\n\n", 0, LIMITE_CAMPO + 1)
        if corte <= 0:
            corte = restante.rfind("\n", 0, LIMITE_CAMPO + 1)
        if corte <= 0:
            corte = restante.rfind(" ", 0, LIMITE_CAMPO + 1)
        if corte <= 0:
            corte = LIMITE_CAMPO
        partes.append(restante[:corte].strip())
        restante = restante[corte:].strip()
    if restante:
        partes.append(restante)
    return partes


def formatar_requisitos(texto: str) -> str:
    partes = [
        parte.strip().strip(";")
        for parte in re.split(r"\s*[●•]\s*", texto.strip())
        if parte.strip().strip(";")
    ]
    if len(partes) > 1:
        return "\n".join(f"• {parte}" for parte in partes)

    linhas = [
        linha.strip().removeprefix("- ").strip()
        for linha in texto.splitlines()
        if linha.strip()
    ]
    return "\n".join(f"• {linha}" for linha in linhas)


def formatar_subtitulos(texto: str) -> str:
    """Destaca títulos internos sem competir com o título da seção."""
    formatado = re.sub(
        r"(?m)^\*\*(.+?):\*\*\s*",
        lambda correspondencia: f"### {correspondencia.group(1).strip()}\n",
        texto.strip(),
    )
    return re.sub(r"\n{2,}(?=### )", "\n", formatado)


def formatar_rotulos_inline(texto: str) -> str:
    linhas: list[str] = []
    padrao = re.compile(r"^(?P<inicio>\s*(?:•\s*)?)(?P<rotulo>[^:\n]{1,60}):\s+(?P<texto>.+)$")
    for linha in texto.splitlines():
        correspondencia = padrao.match(linha)
        if not correspondencia or "**" in correspondencia.group("rotulo"):
            linhas.append(linha)
            continue
        rotulo = correspondencia.group("rotulo").strip()
        if any(sinal in rotulo for sinal in ".!?;"):
            linhas.append(linha)
            continue
        explicacao = maiuscula_inicial(correspondencia.group("texto").strip())
        linhas.append(
            f'{correspondencia.group("inicio")}**{rotulo}:** {explicacao}'
        )
    return "\n".join(linhas)


def formatar_lista(texto: str) -> str:
    partes = re.split(r"\s*[●•]\s*", texto.strip())
    if len(partes) == 1:
        texto = normalizar_ph(texto.strip())
        return capitalizar_inicio_das_linhas(formatar_rotulos_inline(texto))

    prefixo = partes[0].strip()
    itens = [parte.strip() for parte in partes[1:] if parte.strip()]
    linhas = ([prefixo] if prefixo else []) + [f"• {item}" for item in itens]
    texto = normalizar_ph("\n".join(linhas))
    return capitalizar_inicio_das_linhas(formatar_rotulos_inline(texto))


def maiuscula_inicial(texto: str) -> str:
    for indice, caractere in enumerate(texto):
        if caractere.isalpha():
            return texto[:indice] + caractere.upper() + texto[indice + 1 :]
    return texto


def capitalizar_inicio_das_linhas(texto: str) -> str:
    linhas: list[str] = []
    for linha in texto.splitlines():
        conteudo = linha.lstrip()
        inicio_textual = conteudo.removeprefix("•").lstrip()
        if (
            not conteudo
            or conteudo.startswith(("#", "**"))
            or inicio_textual.startswith("**")
            or (inicio_textual and inicio_textual[0].isdigit())
        ):
            linhas.append(linha)
            continue
        linhas.append(maiuscula_inicial(linha))
    return "\n".join(linhas)


def normalizar_ph(texto: str) -> str:
    return re.sub(
        r"\b(\d+)\s*PH\b",
        lambda correspondencia: f"{correspondencia.group(1)}ph",
        texto,
        flags=re.IGNORECASE,
    )


def formatar_habilidade_inicial_heranca(texto: str) -> str:
    def substituir_titulo(correspondencia: re.Match[str]) -> str:
        titulo = normalizar_ph(correspondencia.group(1).strip())
        if re.fullmatch(r"\d+ph", titulo):
            return f"**{titulo}**\n"
        return f"**{titulo}:**\n"

    texto = re.sub(r"(?i)^Passiv[oa]\.\s*", "", texto.strip())
    texto = re.sub(r"(?mi)^\*\*Passiv[oa]:\*\*\s*", "", texto)
    texto = re.sub(r"(?m)^\*\*(.+?):\*\*\s*", substituir_titulo, texto)
    texto = re.sub(r"\n{2,}", "\n", texto)
    return formatar_lista(texto)


def separar_blocos_titulados(texto: str) -> list[tuple[str, str]]:
    padrao = re.compile(
        r"(?ms)^\*\*(?P<titulo>.+?):\*\*\s*(?P<conteudo>.*?)(?=^\*\*.+?:\*\*|\Z)"
    )
    return [
        (correspondencia.group("titulo").strip(), correspondencia.group("conteudo").strip())
        for correspondencia in padrao.finditer(texto.strip())
    ]


def dividir_descricao(texto: str, limite: int = 3900) -> list[str]:
    if len(texto) <= limite:
        return [texto]

    partes: list[str] = []
    restante = texto
    while len(restante) > limite:
        corte = restante.rfind("\n", 0, limite + 1)
        if corte <= 0:
            corte = restante.rfind(" ", 0, limite + 1)
        if corte <= 0:
            corte = limite
        partes.append(restante[:corte].rstrip())
        restante = restante[corte:].lstrip()
    if restante:
        partes.append(restante)
    return partes


def tamanho_embed(embed: discord.Embed) -> int:
    total = len(embed.title or "") + len(embed.description or "")
    return total + sum(len(campo.name) + len(campo.value) for campo in embed.fields)


def montar_embeds_habilidade(
    entrada: EntradaBiblioteca,
    categoria: str,
) -> list[discord.Embed]:
    dados = dados_categoria(categoria)
    emoji = str(dados["emoji"])
    nome_categoria = str(dados["nome"])
    campos = campos_normalizados(entrada)

    cabecalho = f"## {emoji} {entrada.titulo}"
    descricao_principal = (
        formatar_lista(formatar_subtitulos(entrada.descricao)) if entrada.descricao else ""
    )
    principal = discord.Embed(description=f"{cabecalho}\n{descricao_principal}".strip())
    principal.add_field(name="Categoria", value=nome_categoria, inline=True)

    rotulos_inline = {
        "custo de aquisicao": "Custo de aquisição",
        "custo por evolucao": "Custo por evolução",
        "custo de xp": "Custo de XP",
        "custo de ph": "Custo de PH",
    }
    usados = {"categoria", "descricao"}
    for chave, rotulo in rotulos_inline.items():
        valor = campos.get(chave)
        if valor:
            principal.add_field(name=rotulo, value=normalizar_ph(valor), inline=True)
            usados.add(chave)

    embeds = [principal]
    if categoria == "heranca_sanguinea":
        campos_heranca = {
            normalizar_rotulo(rotulo): (rotulo, valor)
            for rotulo, valor in entrada.campos.items()
            if valor.strip()
        }
        usados_heranca = set(usados)

        for chave in (
            "vantagens",
            "desvantagens",
            "observacoes",
            "observacoes e desvantagens",
            "consequencias",
        ):
            campo = campos_heranca.get(chave)
            if not campo:
                continue
            rotulo_original, valor = campo
            rotulo = "Desvantagens" if chave == "consequencias" else rotulo_original
            valor = formatar_lista(valor)
            for parte in dividir_descricao(valor):
                embeds.append(discord.Embed(description=f"## {rotulo}\n{parte}"))
            usados_heranca.add(chave)

        habilidade_inicial = campos_heranca.get("habilidade inicial")
        if habilidade_inicial:
            _, valor = habilidade_inicial
            valor = formatar_habilidade_inicial_heranca(valor)
            for parte in dividir_descricao(valor):
                embeds.append(discord.Embed(description=f"### Habilidade Inicial — Passivo\n{parte}"))
            usados_heranca.add("habilidade inicial")

        evolucoes = campos_heranca.get("evolucoes")
        if evolucoes:
            _, valor = evolucoes
            for titulo, conteudo in separar_blocos_titulados(valor):
                titulo = normalizar_ph(titulo)
                conteudo = formatar_lista(maiuscula_inicial(conteudo))
                for parte in dividir_descricao(conteudo):
                    embeds.append(discord.Embed(description=f"### {titulo}\n{parte}"))
            usados_heranca.add("evolucoes")

        for rotulo_original, valor in entrada.campos.items():
            chave = normalizar_rotulo(rotulo_original)
            if chave in usados_heranca or not valor.strip():
                continue
            valor = formatar_lista(formatar_subtitulos(valor))
            for parte in dividir_descricao(valor):
                embeds.append(discord.Embed(description=f"## {rotulo_original}\n{parte}"))
        return embeds

    secoes_finais: list[tuple[str, str]] = []
    for rotulo_original, valor in entrada.campos.items():
        chave = normalizar_rotulo(rotulo_original)
        if chave in usados or not valor.strip():
            continue
        if chave in {"consequencias", "desvantagens"}:
            secoes_finais.append((rotulo_original, valor))
            continue
        if chave == "requisitos de aquisicao":
            valor = normalizar_ph(formatar_requisitos(valor))
        else:
            valor = formatar_lista(formatar_subtitulos(valor))
        partes = dividir_descricao(valor)
        for parte in partes:
            if categoria == "origem_magica" and chave == "habilidades":
                embeds.append(discord.Embed(description=parte))
                continue
            embeds.append(discord.Embed(description=f"## {rotulo_original}\n{parte}"))

    for rotulo_original, valor in secoes_finais:
        valor = formatar_lista(formatar_subtitulos(valor))
        for parte in dividir_descricao(valor):
            embeds.append(discord.Embed(description=f"## {rotulo_original}\n{parte}"))
    return embeds


def agrupar_embeds(embeds: list[discord.Embed]) -> list[list[discord.Embed]]:
    grupos: list[list[discord.Embed]] = []
    atual: list[discord.Embed] = []
    total = 0
    for embed in embeds:
        tamanho = tamanho_embed(embed)
        if atual and (total + tamanho > LIMITE_TOTAL_MENSAGEM or len(atual) >= 10):
            grupos.append(atual)
            atual = []
            total = 0
        atual.append(embed)
        total += tamanho
    if atual:
        grupos.append(atual)
    return grupos


class Habilidades(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def autocomplete_nome(
        self,
        interaction: discord.Interaction,
        atual: str,
    ) -> list[app_commands.Choice[str]]:
        categoria = getattr(interaction.namespace, "categoria", "")
        if categoria not in CATEGORIAS_HABILIDADE:
            return []
        return [
            app_commands.Choice(name=nome, value=nome)
            for nome in listar_habilidades(categoria, atual)
        ]

    @app_commands.command(
        name="habilidade",
        description="Consulta uma habilidade oficial da biblioteca do Grimory.",
    )
    @app_commands.describe(
        categoria="Categoria da habilidade",
        nome="Nome da habilidade",
    )
    @app_commands.choices(categoria=[
        app_commands.Choice(name=str(dados["nome"]), value=chave)
        for chave, dados in CATEGORIAS_HABILIDADE.items()
    ])
    @app_commands.autocomplete(nome=autocomplete_nome)
    async def habilidade(
        self,
        interaction: discord.Interaction,
        categoria: app_commands.Choice[str],
        nome: str,
    ) -> None:
        entrada = carregar_habilidade(categoria.value, nome)
        if entrada is None:
            await interaction.response.send_message(
                f"**{nome}** não foi encontrada em **{categoria.name}**.",
                ephemeral=True,
            )
            return

        grupos = agrupar_embeds(montar_embeds_habilidade(entrada, categoria.value))
        await interaction.response.send_message(embeds=grupos[0])
        for grupo in grupos[1:]:
            await interaction.followup.send(embeds=grupo)
