import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import discord
from discord import app_commands
from discord.ext import commands

from comandos.executar import (
    CORES_FEITICOS,
    COR_EMBED_FEITICO,
    COR_EMBED_RUNA,
    criar_embeds_entrada,
    normalizar_ano,
)
from comandos.interagir import COR_EMBED_TCM, montar_embeds_criatura
from comandos.habilidades import (
    CATEGORIAS_HABILIDADE,
    formatar_cabecalho_habilidade,
    formatar_lista,
    formatar_requisitos,
    formatar_subtitulos,
    montar_embeds_habilidade,
    normalizar_ph,
)
from comandos.preparar import COR_EMBED_POCAO, interpretar_pocao, montar_embeds_pocao
from utils.biblioteca import interpretar_markdown, normalizar_rotulo
from utils.inventario import GRUPOS_INGREDIENTES_APRESENTACAO, emoji_grupo_ingredientes


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_BIBLIOTECA = RAIZ_PROJETO / "biblioteca"
ARQUIVO_THREADS = PASTA_BIBLIOTECA / "modelos" / "threads-categorias.md"
TEMPO_FLUXO = 15 * 60
NOMES_RESERVADOS_WINDOWS = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{numero}" for numero in range(1, 10)),
    *(f"LPT{numero}" for numero in range(1, 10)),
}

CATEGORIAS_FEITICO = {
    "encantamentos": ("Encantamentos", "Encantamentos"),
    "transfiguracao": ("Transfiguração", "Transfiguração"),
    "duelos": ("Duelos", "Duelos"),
    "dcat": ("DCAT", "Defesa contra arte das trevas"),
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
CORRUPCAO_POR_GRAU_TREVAS = {
    "Intermediário III": "Sucesso: 2 | Falha: 4",
    "Intermediário IV": "Sucesso: 3 | Falha: 6",
    "Intermediário V": "Sucesso: 4 | Falha: 8",
    "Avançado VI": "Sucesso: 5 | Falha: 10",
    "Avançado VII": "Sucesso: 6 | Falha: 12",
}
CATEGORIAS_BINDRUNA = {
    "Sobreposta": ("Básico", 10),
    "Haste": ("Intermediário", 13),
    "Radial": ("Avançado", 16),
}
MAXIMO_RUNAS_BINDRUNA = 6
ANOS = tuple(f"{numero}º Ano" for numero in range(1, 8))
GRAUS_FEITICO_POR_ANO = {
    "1º Ano": "Básico Ⅰ",
    "2º Ano": "Básico Ⅱ",
    "3º Ano": "Intermediário Ⅲ",
    "4º Ano": "Intermediário Ⅳ",
    "5º Ano": "Intermediário Ⅴ",
    "6º Ano": "Avançado Ⅵ",
    "7º Ano": "Avançado Ⅶ",
}
DIFICULDADES_POCAO_POR_ANO = {
    "1º Ano": "1º Ano: 12+\n2º Ano: 10+\n3º Ano: 10+\n4º Ano: 8+\n5º Ano: 8+\n6º Ano: 6+\n7º Ano: 6+\n+18y: 6+",
    "2º Ano": "1º Ano: 14+\n2º Ano: 12+\n3º Ano: 12+\n4º Ano: 10+\n5º Ano: 10+\n6º Ano: 8+\n7º Ano: 8+\n+18y: 8+",
    "3º Ano": "1º Ano: 16+\n2º Ano: 16+\n3º Ano: 14+\n4º Ano: 14+\n5º Ano: 12+\n6º Ano: 12+\n7º Ano: 10+\n+18y: 10+",
    "4º Ano": "1º Ano: 18+\n2º Ano: 18+\n3º Ano: 16+\n4º Ano: 16+\n5º Ano: 14+\n6º Ano: 14+\n7º Ano: 12+\n+18y: 12+",
    "5º Ano": "1º Ano: 20+\n2º Ano: 20+\n3º Ano: 18+\n4º Ano: 18+\n5º Ano: 16+\n6º Ano: 16+\n7º Ano: 14+\n+18y: 14+",
    "6º Ano": "1º Ano: 25+\n2º Ano: 25+\n3º Ano: 25+\n4º Ano: 20+\n5º Ano: 20+\n6º Ano: 20+\n7º Ano: 18+\n+18y: 18+",
    "7º Ano": "1º Ano: 30+\n2º Ano: 30+\n3º Ano: 30+\n4º Ano: 25+\n5º Ano: 25+\n6º Ano: 22+\n7º Ano: 20+\n+18y: 20+",
}
DIFICULDADES_TREVAS_POR_GRAU = {
    "Intermediário III": DIFICULDADES_POCAO_POR_ANO["3º Ano"],
    "Intermediário IV": DIFICULDADES_POCAO_POR_ANO["4º Ano"],
    "Intermediário V": DIFICULDADES_POCAO_POR_ANO["5º Ano"],
    "Avançado VI": DIFICULDADES_POCAO_POR_ANO["6º Ano"],
    "Avançado VII": "1º Ano: 30+\n2º Ano: 30+\n3º Ano: 30+\n4º Ano: 25+\n5º Ano: 25+\n6º Ano: 25+\n7º Ano: 20+\n+18y: 20+",
}
PERICULOSIDADES = ("X", "XX", "XXX", "XXXX", "XXXXX")
class ErroConteudo(ValueError):
    pass


@dataclass(frozen=True)
class CampoFormulario:
    chave: str
    rotulo: str
    estilo: discord.TextStyle = discord.TextStyle.short
    obrigatorio: bool = True
    maximo: int = 1024
    placeholder: Optional[str] = None


@dataclass
class SessaoAdicionar:
    usuario_id: int
    tipo: str = ""
    opcao: str = ""
    valores: dict[str, str] = field(default_factory=dict)
    preparado: Optional["ConteudoPreparado"] = None


@dataclass
class ConteudoPreparado:
    nome: str
    markdown: str
    destino_markdown: Path
    embeds: list[discord.Embed]
    secao_thread: str
    chave_thread: str
    conteudo_publicacao: Optional[str] = None


def bloco(rotulo: str, valor: str) -> str:
    return f"{rotulo}:\n{valor.strip()}"


def montar_markdown(titulo: str, campos: list[tuple[str, str]]) -> str:
    partes = [f"# {titulo.strip()}"]
    partes.extend(bloco(rotulo, valor) for rotulo, valor in campos)
    return "\n\n".join(partes).rstrip() + "\n"


def validar_nome(nome: str) -> str:
    nome = nome.strip()

    if not nome:
        raise ErroConteudo("Informe o nome do conteúdo.")

    if len(nome) > 100:
        raise ErroConteudo("O nome pode ter no máximo 100 caracteres.")

    if any(caractere in nome for caractere in '<>:"/\\|?*\r\n'):
        raise ErroConteudo("O nome contém um caractere que não pode ser usado em arquivo.")

    if nome.endswith((".", " ")):
        raise ErroConteudo("O nome não pode terminar com ponto ou espaço.")

    if nome.upper() in NOMES_RESERVADOS_WINDOWS:
        raise ErroConteudo("Esse nome é reservado pelo Windows.")

    return nome


def caminho_seguro(pasta: Path, nome: str) -> Path:
    raiz = PASTA_BIBLIOTECA.resolve()
    destino = (pasta / f"{nome}.md").resolve()

    try:
        destino.relative_to(raiz)
    except ValueError as erro:
        raise ErroConteudo("O destino calculado ficou fora da biblioteca.") from erro

    return destino


def encontrar_colisao(destino: Path) -> Optional[Path]:
    if not destino.parent.exists():
        return None

    chave = destino.name.casefold()
    return next(
        (arquivo for arquivo in destino.parent.iterdir() if arquivo.name.casefold() == chave),
        None,
    )


def validar_embeds(embeds: list[discord.Embed]) -> None:
    if not embeds or len(embeds) > 10:
        raise ErroConteudo("A prévia precisa ter entre 1 e 10 embeds.")

    total = 0

    for embed in embeds:
        if len(embed.title or "") > 256:
            raise ErroConteudo("O título excede 256 caracteres.")
        if len(embed.description or "") > 4096:
            raise ErroConteudo("Uma descrição excede 4.096 caracteres.")
        if len(embed.fields) > 25:
            raise ErroConteudo("Uma embed excede 25 campos.")

        total += len(embed.title or "") + len(embed.description or "")

        for campo in embed.fields:
            if len(campo.name) > 256:
                raise ErroConteudo("O nome de um campo excede 256 caracteres.")
            if len(campo.value) > 1024:
                raise ErroConteudo(
                    f"O campo **{campo.name}** excede 1.024 caracteres."
                )
            total += len(campo.name) + len(campo.value)

    if total > 6000:
        raise ErroConteudo(
            f"A ficha soma {total} caracteres nas embeds; o limite é 6.000."
        )


def campos_formulario(sessao: SessaoAdicionar) -> list[list[CampoFormulario]]:
    if sessao.tipo == "feitico":
        return [[
            CampoFormulario("nome", "Nome", maximo=100),
            CampoFormulario(
                "descricao",
                "Descrição",
                discord.TextStyle.paragraph,
                maximo=4000,
            ),
        ]]

    if sessao.tipo == "trevas":
        paginas = [[
            CampoFormulario("nome", "Nome", maximo=100),
            CampoFormulario(
                "descricao",
                "Descrição",
                discord.TextStyle.paragraph,
                maximo=4000,
            ),
        ]]
        if sessao.opcao == "Magia Ritualística":
            paginas.append([
                CampoFormulario(
                    "barganha",
                    "Modificador de Barganha",
                    discord.TextStyle.paragraph,
                    maximo=1024,
                )
            ])
        return paginas

    if sessao.tipo == "bindruna":
        return [[
            CampoFormulario("nome", "Nome", maximo=100),
            CampoFormulario(
                "descricao",
                "Descrição",
                discord.TextStyle.paragraph,
                maximo=1024,
            ),
            CampoFormulario(
                "capacidades",
                "Capacidades Mágicas",
                discord.TextStyle.paragraph,
                maximo=1024,
            ),
        ]]

    if sessao.tipo == "pocao":
        return [
            [
                CampoFormulario("nome", "Nome", maximo=100),
                CampoFormulario("descricao", "Descrição", discord.TextStyle.paragraph, maximo=2000),
                CampoFormulario("efeito", "Efeito", discord.TextStyle.paragraph, maximo=1024),
                CampoFormulario("aparencia", "Aparência", discord.TextStyle.paragraph, maximo=1024),
                CampoFormulario("consumo", "Consumo", discord.TextStyle.paragraph, maximo=1024),
            ],
            [
                CampoFormulario("tempo", "Tempo de preparo", maximo=100),
                CampoFormulario("rendimento", "Rendimento", maximo=100),
                CampoFormulario("duracao", "Duração", maximo=200, obrigatorio=False),
                CampoFormulario("preparo", "Modo de Preparo", discord.TextStyle.paragraph, maximo=2000),
            ],
            [
                CampoFormulario("colaterais", "Efeitos colaterais gerais", discord.TextStyle.paragraph, maximo=1500),
                CampoFormulario("defeituosa", "Poção defeituosa", discord.TextStyle.paragraph, maximo=1500),
            ],
        ]

    if sessao.tipo == "criatura":
        return [
            [
                CampoFormulario("nome", "Nome", maximo=100),
            ],
            [
                CampoFormulario("descricao", "Descrição", discord.TextStyle.paragraph, maximo=3000),
                CampoFormulario("aparencia", "Aparência", discord.TextStyle.paragraph, maximo=3000),
                CampoFormulario("habitat", "Habitat e Distribuição", discord.TextStyle.paragraph, maximo=3000),
                CampoFormulario("alimentacao", "Alimentação", discord.TextStyle.paragraph, maximo=3000),
                CampoFormulario("comportamento", "Comportamento", discord.TextStyle.paragraph, maximo=3000),
            ],
            [
                CampoFormulario("ciclo", "Ciclo de Vida", discord.TextStyle.paragraph, maximo=3000),
                CampoFormulario("manejo", "Interação e Manejo", discord.TextStyle.paragraph, maximo=3000),
                CampoFormulario("defesas", "Defesas e Riscos", discord.TextStyle.paragraph, maximo=3000),
            ],
            [
                CampoFormulario("aptidoes", "Aptidões", discord.TextStyle.paragraph, maximo=3000),
                CampoFormulario("utilidades", "Utilidades", discord.TextStyle.paragraph, maximo=3000),
                CampoFormulario("rastros", "Rastros e Sinais", discord.TextStyle.paragraph, maximo=3000),
                CampoFormulario(
                    "imagem_url",
                    "Link da imagem",
                    maximo=2048,
                    placeholder="https://...",
                ),
            ],
        ]

    if sessao.tipo == "habilidade":
        if sessao.opcao == "heranca_sanguinea":
            return [
                [
                    CampoFormulario("nome", "Nome", maximo=100),
                    CampoFormulario("descricao", "Descrição", discord.TextStyle.paragraph, maximo=3000),
                    CampoFormulario(
                        "observacoes_desvantagens",
                        "Observações e Desvantagens",
                        discord.TextStyle.paragraph,
                        obrigatorio=False,
                        maximo=2000,
                    ),
                    CampoFormulario("custo_xp", "Custo por evolução em XP", maximo=30, placeholder="Ex.: 60 XP"),
                ],
                [
                    CampoFormulario(
                        "habilidade_inicial_descricao",
                        "Habilidade Inicial — descrição",
                        discord.TextStyle.paragraph,
                        maximo=2000,
                    ),
                ],
                *[
                    [
                        CampoFormulario(
                            f"evolucao_{indice}_custo",
                            f"{nome_evolucao} — custo/mecânica",
                            maximo=200,
                            placeholder="Custo em PH, XP ou mecânica própria",
                        ),
                        CampoFormulario(
                            f"evolucao_{indice}_descricao",
                            f"{nome_evolucao} — descrição",
                            discord.TextStyle.paragraph,
                            maximo=2000,
                        ),
                    ]
                    for indice, nome_evolucao in enumerate(
                        ("Primeira Evolução", "Segunda Evolução", "Terceira Evolução", "Quarta Evolução", "Última Evolução"),
                        start=1,
                    )
                ],
            ]
        if sessao.opcao == "origem_magica":
            paginas = [[
                CampoFormulario("nome", "Nome", maximo=100),
                CampoFormulario("custo_xp", "Custo de aquisição em XP", maximo=30, placeholder="Ex.: 80 XP ou Variável"),
                CampoFormulario("descricao", "Descrição", discord.TextStyle.paragraph, maximo=3000),
                CampoFormulario("observacoes", "Observações", discord.TextStyle.paragraph, obrigatorio=False, maximo=2000),
            ]]
            try:
                quantidade = int(sessao.valores.get("quantidade_habilidades", "0"))
            except ValueError:
                quantidade = 0
            if quantidade not in range(1, 5):
                return paginas
            paginas.extend([
                [
                    CampoFormulario(f"habilidade_{indice}_nome", f"Habilidade {indice} — nome", maximo=100),
                    CampoFormulario(
                        f"habilidade_{indice}_custo",
                        f"Habilidade {indice} — custo/mecânica",
                        maximo=200,
                        placeholder="Custo em PH, XP ou mecânica própria",
                    ),
                    CampoFormulario(
                        f"habilidade_{indice}_descricao",
                        f"Habilidade {indice} — descrição",
                        discord.TextStyle.paragraph,
                        maximo=2000,
                    ),
                ]
                for indice in range(1, quantidade + 1)
            ])
            return paginas
        if sessao.opcao == "especializacao":
            return [
                [
                    CampoFormulario("nome", "Nome", maximo=100),
                    CampoFormulario("custo_xp", "Custo de aquisição em XP", maximo=30, placeholder="Ex.: 20 XP"),
                    CampoFormulario("custo_ph", "Custo de PH", obrigatorio=False, maximo=30, placeholder="Ex.: 2ph ou Passivo"),
                    CampoFormulario("descricao", "Descrição", discord.TextStyle.paragraph, maximo=3000),
                ],
                [
                    CampoFormulario("requisitos", "Requisitos de aquisição", discord.TextStyle.paragraph, maximo=3000),
                ],
            ]
        raise ErroConteudo("Categoria de habilidade desconhecida.")

    raise ErroConteudo("Tipo de conteúdo desconhecido.")


def catalogo_runas() -> dict[str, tuple[str, dict[str, str]]]:
    catalogo = {}
    pasta = PASTA_BIBLIOTECA / "runas"

    for arquivo in pasta.glob("*.md"):
        entrada = interpretar_markdown(arquivo.read_text(encoding="utf-8-sig"))
        palavras = {}

        for rotulo, valor in entrada.campos.items():
            if normalizar_rotulo(rotulo) == "palavras-chave":
                for palavra in valor.splitlines():
                    palavra = palavra.strip().lstrip("- ").strip()
                    if palavra:
                        palavras[normalizar_rotulo(palavra)] = palavra

        catalogo[normalizar_rotulo(arquivo.stem)] = (
            entrada.titulo or arquivo.stem,
            palavras,
        )

    return catalogo


def opcoes_runas_bindruna() -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=titulo,
            value=chave,
            description=", ".join(palavras.values())[:100],
        )
        for chave, (titulo, palavras) in sorted(catalogo_runas().items())
    ]


def dados_runa_bindruna(
    sessao: SessaoAdicionar,
) -> tuple[list[str], int, str, str, dict[str, str]]:
    chaves = [
        chave
        for chave in sessao.valores.get("runas_selecionadas", "").splitlines()
        if chave
    ]
    try:
        indice = int(sessao.valores.get("indice_runa", "0"))
        chave = chaves[indice]
        titulo, palavras = catalogo_runas()[chave]
    except (KeyError, IndexError, ValueError) as erro:
        raise ErroConteudo("A seleção de runas ficou inválida. Recomece o `/add`.") from erro

    return chaves, indice, chave, titulo, palavras


def view_palavras_bindruna(sessao: SessaoAdicionar) -> "OpcoesView":
    _, _, _, titulo, palavras = dados_runa_bindruna(sessao)
    return OpcoesView(
        sessao,
        f"Escolha 1 ou 2 palavras de {titulo}",
        [
            discord.SelectOption(label=palavra, value=chave)
            for chave, palavra in palavras.items()
        ],
        finalidade="palavras_bindruna",
        minimo=1,
        maximo=min(2, len(palavras)),
    )


def formatar_runas_utilizadas(texto: str) -> tuple[str, int]:
    catalogo = catalogo_runas()
    linhas_formatadas = []
    runas_vistas = set()

    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue

        linha = linha.removeprefix("- ").strip()
        correspondencia = re.match(
            r"^(?:\*\*)?(?P<runa>.+?):(?:\*\*)?\s*(?P<palavras>.+)$",
            linha,
        )
        if correspondencia is None:
            raise ErroConteudo(
                "Escreva cada runa como `Isaz: Imobilidade`, uma por linha."
            )

        rotulo_runa = correspondencia.group("runa").strip().strip("*")
        chave_encontrada = next(
            (
                chave
                for chave in catalogo
                if normalizar_rotulo(rotulo_runa).endswith(chave)
            ),
            None,
        )
        if chave_encontrada is None:
            raise ErroConteudo(f"A runa **{rotulo_runa}** não existe na biblioteca.")
        if chave_encontrada in runas_vistas:
            raise ErroConteudo(f"A runa **{rotulo_runa}** foi informada mais de uma vez.")

        titulo_oficial, palavras_oficiais = catalogo[chave_encontrada]
        palavras_escolhidas = re.split(
            r"\s+e\s+",
            correspondencia.group("palavras").strip(),
            flags=re.IGNORECASE,
        )
        palavras_formatadas = []

        for palavra in palavras_escolhidas:
            chave_palavra = normalizar_rotulo(palavra)
            palavra_oficial = palavras_oficiais.get(chave_palavra)
            if palavra_oficial is None:
                raise ErroConteudo(
                    f"**{palavra.strip()}** não é uma palavra-chave oficial de "
                    f"**{titulo_oficial}**."
                )
            palavras_formatadas.append(palavra_oficial)

        linhas_formatadas.append(
            f"- **{titulo_oficial}:** {' e '.join(palavras_formatadas)}"
        )
        runas_vistas.add(chave_encontrada)

    if len(linhas_formatadas) < 2:
        raise ErroConteudo("Uma bindruna precisa utilizar pelo menos duas runas.")
    if len(linhas_formatadas) > MAXIMO_RUNAS_BINDRUNA:
        raise ErroConteudo(
            f"Uma bindruna pode utilizar no máximo {MAXIMO_RUNAS_BINDRUNA} runas."
        )

    return "\n".join(linhas_formatadas), len(linhas_formatadas)


def nomes_ingredientes_oficiais() -> dict[str, str]:
    arquivo = PASTA_BIBLIOTECA / "ingredientes" / "Ingredientes de Poções.md"
    nomes = {}

    for linha in arquivo.read_text(encoding="utf-8-sig").splitlines():
        if linha.startswith("- "):
            nome = linha.removeprefix("- ").strip()
            nomes[normalizar_rotulo(nome)] = nome

    return nomes


def paginas_ingredientes_oficiais() -> list[tuple[str, list[str]]]:
    arquivo = PASTA_BIBLIOTECA / "ingredientes" / "Ingredientes de Poções.md"
    grupos: list[tuple[str, list[str]]] = []
    grupo_atual = "Outros ingredientes"
    ingredientes_atuais: list[str] = []

    def guardar_grupo() -> None:
        if not ingredientes_atuais:
            return
        total = len(ingredientes_atuais)
        for inicio in range(0, total, 25):
            lote = ingredientes_atuais[inicio : inicio + 25]
            if total > 25:
                numero = inicio // 25 + 1
                quantidade = (total + 24) // 25
                rotulo = f"{grupo_atual} — {numero}/{quantidade}"
            else:
                rotulo = grupo_atual
            grupos.append((rotulo, lote.copy()))

    for linha in arquivo.read_text(encoding="utf-8-sig").splitlines():
        if linha.startswith("## "):
            guardar_grupo()
            grupo_atual = linha.removeprefix("## ").strip()
            ingredientes_atuais = []
            continue
        if not linha.startswith("- "):
            continue
        ingrediente = linha.removeprefix("- ").strip()
        ingredientes_atuais.append(ingrediente)

    guardar_grupo()
    return sorted(
        grupos,
        key=lambda grupo: next(
            (
                indice
                for indice, (rotulo, _) in enumerate(
                    GRUPOS_INGREDIENTES_APRESENTACAO
                )
                if grupo[0].startswith(rotulo)
            ),
            len(GRUPOS_INGREDIENTES_APRESENTACAO),
        ),
    )


def rotulo_grupo_ingredientes(rotulo: str) -> str:
    emoji = emoji_grupo_ingredientes(rotulo)
    return f"{emoji} {rotulo}"


def opcoes_grupos_ingredientes() -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=rotulo[:100],
            value=str(indice),
            emoji=emoji_grupo_ingredientes(rotulo),
            description=(
                "Pode servir como base"
                if rotulo.startswith("Líquidos, Essências e Extratos")
                else f"{len(ingredientes)} ingrediente(s)"
            ),
        )
        for indice, (rotulo, ingredientes) in enumerate(
            paginas_ingredientes_oficiais()
        )
    ]


def ingredientes_selecionados(sessao: SessaoAdicionar) -> list[str]:
    return [
        ingrediente
        for ingrediente in sessao.valores.get(
            "ingredientes_selecionados", ""
        ).splitlines()
        if ingrediente
    ]


def resumo_ingredientes(sessao: SessaoAdicionar) -> str:
    ingredientes = ingredientes_selecionados(sessao)
    if not ingredientes:
        return "Nenhum ingrediente selecionado."
    linhas = "\n".join(f"• {ingrediente}" for ingrediente in ingredientes)
    resumo = f"**Ingredientes selecionados ({len(ingredientes)}):**\n{linhas}"
    if len(resumo) > 1800:
        resumo = resumo[:1797].rstrip() + "..."
    return resumo


def orientacao_ingredientes_pocao(sessao: SessaoAdicionar) -> str:
    grau = GRAUS_FEITICO_POR_ANO.get(sessao.opcao, "")
    if grau.startswith("Básico"):
        composicao = "1 base + 2 ingredientes"
    elif grau.startswith("Intermediário"):
        composicao = "1 base + 3 ou 4 ingredientes"
    elif grau.startswith("Avançado"):
        composicao = "1 base + 4 ou mais ingredientes, incluindo 1 catalisador raro"
    else:
        composicao = "escolha uma base e os componentes necessários"
    return f"**Sugestão de composição:** {composicao}."


def placeholder_quantidade_ingrediente(ingrediente: str) -> str:
    chave = normalizar_rotulo(ingrediente)
    for rotulo, ingredientes in paginas_ingredientes_oficiais():
        if not rotulo.startswith("Líquidos, Essências e Extratos"):
            continue
        if any(normalizar_rotulo(nome) == chave for nome in ingredientes):
            return "Gotas, mL (mililitros) ou L (litros)"

    termos_liquidos = (
        "agua",
        "sangue",
        "seiva",
        "muco",
        "veneno",
        "urina",
        "meleca",
        "lagrima",
        "suco",
        "mercurio",
        "vinagre",
        "oleo",
        "essencia",
        "infusao",
        "orvalho",
    )
    if any(re.search(rf"\b{termo}\b", chave) for termo in termos_liquidos):
        return "Gotas, mL (mililitros) ou L (litros)"

    return "Unid (unidades), g (gramas) ou Kg (quilogramas)"


def montar_lista_ingredientes(sessao: SessaoAdicionar) -> str:
    linhas = []
    for indice, ingrediente in enumerate(ingredientes_selecionados(sessao)):
        quantidade = sessao.valores.get(f"quantidade_ingrediente_{indice}", "").strip()
        if not quantidade:
            raise ErroConteudo(f"Informe a quantidade de **{ingrediente}**.")
        linhas.append(f"- {ingrediente} — {quantidade}")
    if not linhas:
        raise ErroConteudo("Escolha pelo menos um ingrediente para a poção.")
    return "\n".join(linhas)


def limpar_quantidades_ingredientes(sessao: SessaoAdicionar) -> None:
    for chave in list(sessao.valores):
        if chave.startswith("quantidade_ingrediente_"):
            sessao.valores.pop(chave, None)
    sessao.valores.pop("ingredientes", None)


def cor_embed_fluxo(sessao: SessaoAdicionar) -> Optional[int]:
    if sessao.tipo == "habilidade":
        return None
    if sessao.tipo == "pocao":
        return COR_EMBED_POCAO
    if sessao.tipo == "bindruna":
        return COR_EMBED_RUNA
    if sessao.tipo == "criatura":
        return COR_EMBED_TCM
    if sessao.tipo == "trevas":
        return CORES_FEITICOS["arte das trevas"]
    if sessao.tipo == "feitico" and sessao.opcao in CATEGORIAS_FEITICO:
        _, categoria = CATEGORIAS_FEITICO[sessao.opcao]
        return CORES_FEITICOS.get(normalizar_rotulo(categoria), COR_EMBED_FEITICO)
    return COR_EMBED_FEITICO


def embed_fluxo(
    sessao: SessaoAdicionar,
    titulo: str,
    descricao: str,
    *,
    emoji_titulo: str = "💬",
) -> discord.Embed:
    return discord.Embed(
        title=f"{emoji_titulo} {titulo}",
        description=descricao,
        color=cor_embed_fluxo(sessao),
    )


def painel_ingredientes_pocao(
    sessao: SessaoAdicionar,
    mensagem: str,
    *,
    mostrar_resumo: bool = False,
) -> discord.Embed:
    partes = [orientacao_ingredientes_pocao(sessao)]
    if mostrar_resumo:
        partes.append(resumo_ingredientes(sessao))
    partes.append(mensagem)
    return embed_fluxo(sessao, "Ingredientes", "\n\n".join(partes))


def validar_ingredientes(texto: str) -> None:
    oficiais = nomes_ingredientes_oficiais()
    desconhecidos = []
    sem_quantidade = []

    for linha in texto.splitlines():
        linha = linha.strip().removeprefix("- ").strip()
        if not linha:
            continue

        partes = re.split(r"\s+[—–-](?:\s+|$)|:\s*", linha, maxsplit=1)
        nome = partes[0]
        nome = nome.rstrip(".").strip()
        if normalizar_rotulo(nome) not in oficiais:
            desconhecidos.append(nome)
        if len(partes) < 2 or not partes[1].strip():
            sem_quantidade.append(nome)

    if desconhecidos:
        lista = ", ".join(f"**{nome}**" for nome in desconhecidos[:5])
        raise ErroConteudo(
            f"Ingrediente(s) fora da biblioteca oficial: {lista}."
        )
    if sem_quantidade:
        lista = ", ".join(f"**{nome}**" for nome in sem_quantidade[:5])
        raise ErroConteudo(f"Informe a quantidade de: {lista}.")


def opcoes_campo_criatura(rotulo_procurado: str) -> list[discord.SelectOption]:
    valores: set[str] = set()
    chave_procurada = normalizar_rotulo(rotulo_procurado)

    for arquivo in (PASTA_BIBLIOTECA / "criaturas").rglob("*.md"):
        entrada = interpretar_markdown(arquivo.read_text(encoding="utf-8-sig"))
        campos = {
            normalizar_rotulo(rotulo): valor.strip()
            for rotulo, valor in entrada.campos.items()
        }
        valor = campos.get(chave_procurada, "")
        if not valor:
            continue

        if chave_procurada == normalizar_rotulo("Tipo de Aula"):
            valores.update(
                parte.strip()
                for parte in re.split(r"(?:\r?\n|,\s*|\s+e\s+)", valor)
                if parte.strip()
            )
        else:
            valores.add(valor)

    ordens = {
        normalizar_rotulo("Origem"): (
            "Oficial",
            "Autoral",
            "Adaptação",
        ),
        normalizar_rotulo("Classificação"): (
            "Fera",
            "Ser",
            "Ser semi-humano",
            "Espírito",
        ),
        normalizar_rotulo("Tipo de Aula"): (
            "Teórica",
            "Demonstrativa",
            "Prática",
            "Prática Supervisionada",
        ),
    }
    ordem = {
        normalizar_rotulo(valor): indice
        for indice, valor in enumerate(ordens.get(chave_procurada, ()))
    }
    organizados = sorted(
        valores,
        key=lambda valor: (
            ordem.get(normalizar_rotulo(valor), len(ordem)),
            normalizar_rotulo(valor),
        ),
    )
    if not organizados:
        raise ErroConteudo(
            f"Nenhuma opção oficial foi encontrada para **{rotulo_procurado}**."
        )
    return [discord.SelectOption(label=valor, value=valor) for valor in organizados]


def formatar_selecao_multipla(valores: list[str]) -> str:
    if len(valores) == 1:
        return valores[0]
    return f"{', '.join(valores[:-1])} e {valores[-1]}"


def formatar_anos_estudo(valores: list[str]) -> str:
    if len(valores) == 1:
        return valores[0]
    anos = [valor.removesuffix(" Ano") for valor in valores]
    return f"{', '.join(anos[:-1])} e {anos[-1]} Anos"


def progressao_feitico(categoria: str, ano: str) -> tuple[str, str]:
    pasta_nome, _ = CATEGORIAS_FEITICO[categoria]
    dificuldades = Counter()

    for arquivo in (PASTA_BIBLIOTECA / "feitiços" / pasta_nome).glob("*.md"):
        entrada = interpretar_markdown(arquivo.read_text(encoding="utf-8-sig"))
        campos = {
            normalizar_rotulo(rotulo): valor.strip()
            for rotulo, valor in entrada.campos.items()
        }
        if normalizar_ano(campos.get("ano de desbloqueio", "")) != ano:
            continue

        dificuldade = campos.get("dificuldade por ano", "")
        if dificuldade:
            dificuldades[dificuldade] += 1

    grau = GRAUS_FEITICO_POR_ANO.get(ano)
    if grau is None:
        raise ErroConteudo(f"Ano de desbloqueio inválido: **{ano}**.")

    if not dificuldades:
        raise ErroConteudo(
            f"A biblioteca não possui uma progressão de referência para **{ano}**."
        )

    mais_comum = dificuldades.most_common()
    if len(mais_comum) > 1 and mais_comum[0][1] == mais_comum[1][1]:
        raise ErroConteudo(
            f"A biblioteca possui dificuldades conflitantes para **{ano}** nessa categoria."
        )

    return grau, mais_comum[0][0]


def preparar_feitico(sessao: SessaoAdicionar) -> ConteudoPreparado:
    nome = validar_nome(sessao.valores["nome"])
    pasta_nome, categoria = CATEGORIAS_FEITICO[sessao.opcao]
    ano = sessao.valores["ano"]
    grau, dificuldade_ano = progressao_feitico(sessao.opcao, ano)
    campos = [
        ("Categoria", categoria),
        ("Ano de desbloqueio", ano),
        ("Grau de dificuldade", grau),
        ("Descrição", sessao.valores["descricao"]),
        ("Dificuldade por ano", dificuldade_ano),
    ]
    campos = [(rotulo, normalizar_ph(valor)) for rotulo, valor in campos]
    markdown = montar_markdown(nome, campos)
    entrada = interpretar_markdown(markdown)
    embeds = criar_embeds_entrada(entrada, "feitico", nome)
    validar_embeds(embeds)
    return ConteudoPreparado(
        nome,
        markdown,
        caminho_seguro(PASTA_BIBLIOTECA / "feitiços" / pasta_nome, nome),
        embeds,
        "Defesa Contra Arte das Trevas" if sessao.opcao == "dcat" else pasta_nome,
        ano,
    )


def preparar_trevas(sessao: SessaoAdicionar) -> ConteudoPreparado:
    nome = validar_nome(sessao.valores["nome"])
    grau = sessao.valores["grau"]
    corrupcao = CORRUPCAO_POR_GRAU_TREVAS.get(grau)
    dificuldade_ano = DIFICULDADES_TREVAS_POR_GRAU.get(grau)
    if corrupcao is None or dificuldade_ano is None:
        raise ErroConteudo(f"Grau de dificuldade inválido: **{grau}**.")
    campos = [
        ("Categoria", "Arte das Trevas"),
        ("Vertente", sessao.opcao),
        ("Grau de dificuldade", grau),
        ("Corrupção de Alma", corrupcao),
        ("Descrição", sessao.valores["descricao"]),
    ]
    if sessao.valores.get("barganha", "").strip():
        campos.append(("Modificador de Barganha", sessao.valores["barganha"]))
    campos.append(("Dificuldade por ano", dificuldade_ano))
    markdown = montar_markdown(nome, campos)
    embeds = criar_embeds_entrada(interpretar_markdown(markdown), "feitico", nome)
    validar_embeds(embeds)
    cabecalho = None
    if sessao.opcao == "Magia Ritualística":
        cabecalho = (
            "## ══════◄••💀••►══════\n"
            f"## {nome}\n"
            f"**Arte das Trevas • {grau}**\n"
            "## ══════◄••💀••►══════"
        )

    return ConteudoPreparado(
        nome,
        markdown,
        caminho_seguro(PASTA_BIBLIOTECA / "feitiços" / "Trevas" / sessao.opcao, nome),
        embeds,
        "Arte das Trevas",
        sessao.opcao,
        conteudo_publicacao=cabecalho,
    )


def preparar_bindruna(sessao: SessaoAdicionar) -> ConteudoPreparado:
    nome = validar_nome(sessao.valores["nome"])
    runas, quantidade = formatar_runas_utilizadas(sessao.valores["runas"])
    grau, cd_base = CATEGORIAS_BINDRUNA[sessao.opcao]
    cd = cd_base + max(0, quantidade - 2) * 2
    markdown = montar_markdown(nome, [
        ("Runas Utilizadas", runas),
        ("Categoria", sessao.opcao),
        ("Grau de Dificuldade", f"{grau} — CD {cd}"),
        ("Descrição", sessao.valores["descricao"]),
        ("Capacidades Mágicas", sessao.valores["capacidades"]),
    ])
    embeds = criar_embeds_entrada(interpretar_markdown(markdown), "bindruna", nome)
    validar_embeds(embeds)
    return ConteudoPreparado(
        nome,
        markdown,
        caminho_seguro(PASTA_BIBLIOTECA / "bindrunes", nome),
        embeds,
        "Runas Antigas",
        "Bindrunes",
    )


def preparar_pocao(sessao: SessaoAdicionar) -> ConteudoPreparado:
    nome = validar_nome(sessao.valores["nome"])
    validar_ingredientes(sessao.valores["ingredientes"])
    grau = GRAUS_FEITICO_POR_ANO.get(sessao.opcao)
    dificuldade_ano = DIFICULDADES_POCAO_POR_ANO.get(sessao.opcao)
    if grau is None or dificuldade_ano is None:
        raise ErroConteudo(f"Ano de desbloqueio inválido: **{sessao.opcao}**.")
    markdown = montar_markdown(nome, [
        ("Descrição", sessao.valores["descricao"]),
        ("Efeito", sessao.valores["efeito"]),
        ("Aparência", sessao.valores["aparencia"]),
        ("Consumo", sessao.valores["consumo"]),
        ("Tempo de preparo", sessao.valores["tempo"]),
        ("Rendimento", sessao.valores["rendimento"]),
        ("Duração", sessao.valores.get("duracao", "")),
        ("Efeitos colaterais gerais", sessao.valores["colaterais"]),
        ("Poção defeituosa", sessao.valores["defeituosa"]),
        ("Ingredientes", sessao.valores["ingredientes"]),
        ("Modo de Preparo", sessao.valores["preparo"]),
        ("Ano de desbloqueio", sessao.opcao),
        ("Grau de dificuldade", grau),
        ("Dificuldade por ano", dificuldade_ano),
    ])
    entrada, tempo, rendimento = interpretar_pocao(markdown)
    embeds = montar_embeds_pocao(entrada, nome, tempo, rendimento)
    validar_embeds(embeds)
    cabecalho = (
        "## ══════◄••🧪••►══════\n"
        f"## {nome}\n"
        f"**{sessao.opcao} • {grau}**\n"
        "## ══════◄••🧪••►══════"
    )
    return ConteudoPreparado(
        nome,
        markdown,
        caminho_seguro(PASTA_BIBLIOTECA / "poções" / sessao.opcao, nome),
        embeds,
        "Poções",
        sessao.opcao,
        conteudo_publicacao=cabecalho,
    )


def preparar_criatura(sessao: SessaoAdicionar) -> ConteudoPreparado:
    nome = validar_nome(sessao.valores["nome"])
    imagem_url = sessao.valores["imagem_url"].strip()
    url = urlsplit(imagem_url)
    if url.scheme.casefold() != "https" or not url.netloc:
        raise ErroConteudo("Informe um link completo de imagem começando com `https://`.")

    markdown = montar_markdown(nome, [
        ("Imagem", imagem_url),
        ("Origem", sessao.valores["origem"]),
        ("Classificação", sessao.valores["classificacao"]),
        ("Periculosidade", sessao.opcao),
        ("Ano de Estudo", sessao.valores["ano_estudo"]),
        ("Tipo de Aula", sessao.valores["tipo_aula"]),
        ("Descrição", sessao.valores["descricao"]),
        ("Aparência", sessao.valores["aparencia"]),
        ("Habitat e Distribuição", sessao.valores["habitat"]),
        ("Alimentação", sessao.valores["alimentacao"]),
        ("Comportamento", sessao.valores["comportamento"]),
        ("Ciclo de Vida", sessao.valores["ciclo"]),
        ("Interação e Manejo", sessao.valores["manejo"]),
        ("Defesas e Riscos", sessao.valores["defesas"]),
        ("Aptidões", sessao.valores["aptidoes"]),
        ("Utilidades", sessao.valores["utilidades"]),
        ("Rastros e Sinais", sessao.valores["rastros"]),
    ])
    embeds = montar_embeds_criatura(
        interpretar_markdown(markdown),
        nome,
        imagem_url,
    )


def validar_custo_habilidade(valor: str) -> str:
    valor = valor.strip()
    if any(caractere.isdigit() for caractere in valor):
        return valor
    if normalizar_rotulo(valor) in {"variavel", "custo variavel"}:
        return "Variável"
    raise ErroConteudo("Informe um custo de XP numérico ou **Variável**.")


def preparar_habilidade(sessao: SessaoAdicionar) -> ConteudoPreparado:
    nome = validar_nome(sessao.valores["nome"])
    dados = CATEGORIAS_HABILIDADE.get(sessao.opcao)
    if dados is None:
        raise ErroConteudo("Categoria de habilidade desconhecida.")

    categoria = str(dados["nome"])
    custo = validar_custo_habilidade(sessao.valores["custo_xp"])
    if sessao.opcao == "heranca_sanguinea":
        descricao_inicial = sessao.valores["habilidade_inicial_descricao"].strip()
        if not descricao_inicial:
            raise ErroConteudo("Informe a descrição da Habilidade Inicial passiva.")

        nomes_evolucoes = (
            "Primeira Evolução",
            "Segunda Evolução",
            "Terceira Evolução",
            "Quarta Evolução",
            "Última Evolução",
        )
        blocos_evolucoes: list[str] = []
        for indice, nome_evolucao in enumerate(nomes_evolucoes, start=1):
            custo_evolucao = normalizar_ph(sessao.valores[f"evolucao_{indice}_custo"].strip())
            descricao_evolucao = sessao.valores[f"evolucao_{indice}_descricao"].strip()
            if not custo_evolucao or not descricao_evolucao:
                raise ErroConteudo(
                    f"Informe o custo/mecânica e a descrição da {nome_evolucao}."
                )
            blocos_evolucoes.append(
                f"**{nome_evolucao} - {custo_evolucao}:** {descricao_evolucao}"
            )

        campos = [
            ("Categoria", categoria),
            ("Descrição", sessao.valores["descricao"]),
            ("Habilidade Inicial", descricao_inicial),
            ("Custo por evolução", custo),
            ("Evoluções", "\n\n".join(blocos_evolucoes)),
        ]
        observacoes = sessao.valores.get("observacoes_desvantagens", "").strip()
        if observacoes:
            campos.append(("Observações e Desvantagens", observacoes))
    elif sessao.opcao == "origem_magica":
        try:
            quantidade_habilidades = int(sessao.valores["quantidade_habilidades"])
        except (KeyError, ValueError) as erro:
            raise ErroConteudo("Escolha uma quantidade de habilidades entre 1 e 4.") from erro
        if quantidade_habilidades not in range(1, 5):
            raise ErroConteudo("Escolha uma quantidade de habilidades entre 1 e 4.")

        blocos_habilidades: list[str] = []
        for indice in range(1, quantidade_habilidades + 1):
            nome_habilidade = sessao.valores[f"habilidade_{indice}_nome"].strip()
            custo_habilidade = normalizar_ph(sessao.valores[f"habilidade_{indice}_custo"].strip())
            descricao_habilidade = sessao.valores[f"habilidade_{indice}_descricao"].strip()
            if not nome_habilidade or not custo_habilidade or not descricao_habilidade:
                raise ErroConteudo(
                    f"Preencha nome, custo/mecânica e descrição da Habilidade {indice}."
                )
            blocos_habilidades.append(
                f"**{nome_habilidade} // {custo_habilidade}:** {descricao_habilidade}"
            )
        habilidades = "\n\n".join(blocos_habilidades)
        habilidades_renderizadas = formatar_lista(formatar_subtitulos(habilidades))
        if len(habilidades_renderizadas) > 4096:
            raise ErroConteudo(
                "As habilidades somam mais de 4.096 caracteres. Reduza as descrições para mantê-las em uma única embed."
            )

        campos = [
            ("Categoria", categoria),
            ("Custo de aquisição", custo),
            ("Descrição", sessao.valores["descricao"]),
        ]
        if sessao.valores.get("observacoes", "").strip():
            campos.append(("Observações", sessao.valores["observacoes"]))
        campos.append(("Habilidades", habilidades))
    else:
        campos = [
            ("Categoria", categoria),
            ("Custo de aquisição", custo),
        ]
        if sessao.valores.get("custo_ph", "").strip():
            campos.append(("Custo de PH", sessao.valores["custo_ph"]))
        campos.extend([
            ("Descrição", sessao.valores["descricao"]),
            ("Requisitos de Aquisição", formatar_requisitos(sessao.valores["requisitos"])),
        ])

    markdown = montar_markdown(nome, campos)
    embeds = montar_embeds_habilidade(interpretar_markdown(markdown), sessao.opcao)
    validar_embeds(embeds)
    return ConteudoPreparado(
        nome,
        markdown,
        caminho_seguro(
            PASTA_BIBLIOTECA / "Habilidades" / str(dados["pasta"]),
            nome,
        ),
        embeds,
        "Habilidades",
        categoria,
        formatar_cabecalho_habilidade(nome, sessao.opcao),
    )
    validar_embeds(embeds)
    return ConteudoPreparado(
        nome,
        markdown,
        caminho_seguro(PASTA_BIBLIOTECA / "criaturas" / sessao.opcao, nome),
        embeds,
        "Trato de Criaturas Mágicas",
        sessao.opcao,
    )


async def preparar_conteudo(sessao: SessaoAdicionar) -> ConteudoPreparado:
    if sessao.tipo == "criatura":
        preparado = preparar_criatura(sessao)
    elif sessao.tipo == "feitico":
        preparado = preparar_feitico(sessao)
    elif sessao.tipo == "trevas":
        preparado = preparar_trevas(sessao)
    elif sessao.tipo == "bindruna":
        preparado = preparar_bindruna(sessao)
    elif sessao.tipo == "pocao":
        preparado = preparar_pocao(sessao)
    elif sessao.tipo == "habilidade":
        preparado = preparar_habilidade(sessao)
    else:
        raise ErroConteudo("Tipo de conteúdo desconhecido.")

    colisao = encontrar_colisao(preparado.destino_markdown)
    if colisao is not None:
        raise ErroConteudo(
            f"Já existe uma ficha chamada **{colisao.stem}** nessa categoria."
        )

    return preparado


def carregar_threads() -> dict[tuple[str, str], int]:
    if not ARQUIVO_THREADS.is_file():
        raise ErroConteudo("O cadastro de threads não foi encontrado.")

    secao = ""
    threads = {}

    for linha in ARQUIVO_THREADS.read_text(encoding="utf-8-sig").splitlines():
        if linha.startswith("## "):
            secao = linha.removeprefix("## ").strip()
            continue

        correspondencia = re.match(r"^-\s+(.+?):\s*(\d{15,22})\s*$", linha.strip())
        if secao and correspondencia:
            chave, identificador = correspondencia.groups()
            threads[(normalizar_rotulo(secao), normalizar_rotulo(chave))] = int(identificador)

    return threads


def encontrar_thread(conteudo: ConteudoPreparado) -> Optional[int]:
    threads = carregar_threads()
    secao = normalizar_rotulo(conteudo.secao_thread)
    chave = normalizar_rotulo(conteudo.chave_thread)
    encontrado = threads.get((secao, chave)) or threads.get((secao, "criaturas"))

    if encontrado is None and secao == normalizar_rotulo("Trato de Criaturas Mágicas"):
        secao_criaturas = normalizar_rotulo("Criaturas")
        encontrado = (
            threads.get((secao_criaturas, chave))
            or threads.get((secao_criaturas, "criaturas"))
        )

    return encontrado


def existe_thread_criaturas() -> bool:
    try:
        threads = carregar_threads()
    except ErroConteudo:
        return False

    secoes = {
        normalizar_rotulo("Trato de Criaturas Mágicas"),
        normalizar_rotulo("Criaturas"),
    }
    return any(secao in secoes for secao, _ in threads)


class ViewDoAutor(discord.ui.View):
    def __init__(self, sessao: SessaoAdicionar):
        super().__init__(timeout=TEMPO_FLUXO)
        self.sessao = sessao

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.sessao.usuario_id:
            return True

        await interaction.response.send_message(
            embed=embed_fluxo(
                self.sessao,
                "Controle indisponível",
                "Somente quem iniciou este `/add` pode usar estes controles.",
            ),
            ephemeral=True,
        )
        return False


class FormularioModal(discord.ui.Modal):
    def __init__(self, sessao: SessaoAdicionar, pagina: int):
        paginas = campos_formulario(sessao)
        super().__init__(
            title=f"💬 Adicionar conteúdo — {pagina + 1}/{len(paginas)}"
        )
        self.sessao = sessao
        self.pagina = pagina
        self.especificacoes = paginas[pagina]
        self.entradas: dict[str, discord.ui.TextInput] = {}

        for especificacao in self.especificacoes:
            entrada = discord.ui.TextInput(
                label=especificacao.rotulo,
                style=especificacao.estilo,
                required=especificacao.obrigatorio,
                max_length=especificacao.maximo,
                placeholder=especificacao.placeholder,
                default=sessao.valores.get(especificacao.chave) or None,
            )
            self.entradas[especificacao.chave] = entrada
            self.add_item(entrada)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        for chave, entrada in self.entradas.items():
            self.sessao.valores[chave] = str(entrada.value).strip()

        if self.sessao.tipo == "criatura" and self.pagina == 0:
            opcoes = opcoes_campo_criatura("Origem")
            await interaction.response.edit_message(
                content=None,
                embed=embed_fluxo(
                    self.sessao,
                    "Origem",
                    "Escolha a origem da criatura.",
                ),
                attachments=[],
                view=OpcoesView(
                    self.sessao,
                    "Escolha a origem",
                    opcoes,
                    finalidade="origem_criatura",
                ),
            )
            return

        if (
            self.sessao.tipo == "habilidade"
            and self.sessao.opcao == "origem_magica"
            and self.pagina == 0
        ):
            quantidade_atual = self.sessao.valores.get("quantidade_habilidades", "")
            await interaction.response.edit_message(
                content=None,
                embed=embed_fluxo(
                    self.sessao,
                    "Quantidade de habilidades",
                    "Escolha quantas habilidades esta Origem Mágica possui, de 1 a 4.",
                ),
                attachments=[],
                view=OpcoesView(
                    self.sessao,
                    "Escolha de 1 a 4 habilidades",
                    [
                        discord.SelectOption(
                            label=f"{quantidade} habilidade" if quantidade == 1 else f"{quantidade} habilidades",
                            value=str(quantidade),
                            default=quantidade_atual == str(quantidade),
                        )
                        for quantidade in range(1, 5)
                    ],
                    finalidade="quantidade_habilidades_origem",
                ),
            )
            return

        paginas = campos_formulario(self.sessao)
        proxima = self.pagina + 1

        if proxima < len(paginas):
            await interaction.response.edit_message(
                content=None,
                embed=embed_fluxo(
                    self.sessao,
                    "Formulário em andamento",
                    f"Etapa {self.pagina + 1}/{len(paginas)} concluída. "
                    "Continue para preencher os próximos campos.",
                ),
                attachments=[],
                view=ContinuarView(self.sessao, proxima),
            )
            return

        try:
            preparado = await preparar_conteudo(self.sessao)
        except ErroConteudo as erro:
            await interaction.response.edit_message(
                content=None,
                embed=embed_fluxo(
                    self.sessao,
                    "Revise as informações",
                    f"Não consegui montar a prévia: {erro}",
                ),
                attachments=[],
                view=ContinuarView(self.sessao, 0, "Revisar os formulários"),
            )
            return

        self.sessao.preparado = preparado
        embeds_previa = [
            discord.Embed.from_dict(embed.to_dict()) for embed in preparado.embeds
        ]
        embeds_previa[0].set_author(
            name="💬 Prévia para aprovação • Confira tudo antes de aprovar"
        )
        if embeds_previa[0].title:
            embeds_previa[0].title = f"💬 {embeds_previa[0].title}"

        await interaction.response.edit_message(
            content=None,
            embeds=embeds_previa,
            attachments=[],
            view=AprovacaoView(self.sessao),
        )


class ContinuarView(ViewDoAutor):
    def __init__(
        self,
        sessao: SessaoAdicionar,
        pagina: int,
        rotulo: str = "Continuar preenchimento",
    ):
        super().__init__(sessao)
        self.pagina = pagina
        botao = discord.ui.Button(label=rotulo, style=discord.ButtonStyle.primary)
        botao.callback = self.abrir_modal
        self.add_item(botao)

    async def abrir_modal(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(FormularioModal(self.sessao, self.pagina))


class OpcoesView(ViewDoAutor):
    def __init__(
        self,
        sessao: SessaoAdicionar,
        titulo: str,
        opcoes: list[discord.SelectOption],
        finalidade: str = "formulario",
        minimo: int = 1,
        maximo: int = 1,
    ):
        super().__init__(sessao)
        seletor = discord.ui.Select(
            placeholder=titulo,
            options=opcoes,
            min_values=minimo,
            max_values=maximo,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.finalidade = finalidade
        self.add_item(seletor)
        if finalidade == "ingredientes_pocao":
            confirmar = discord.ui.Button(
                label="Confirmar",
                style=discord.ButtonStyle.success,
                disabled=True,
                row=1,
            )
            confirmar.callback = self.confirmar_ingredientes_pocao
            self.confirmar_ingredientes = confirmar
            self.add_item(confirmar)
            voltar = discord.ui.Button(
                label="Voltar",
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            voltar.callback = self.voltar_grupos_ingredientes
            self.add_item(voltar)
        elif finalidade in {"ano_estudo_criatura", "tipo_aula_criatura"}:
            confirmar = discord.ui.Button(
                label="Confirmar",
                style=discord.ButtonStyle.success,
                disabled=True,
                row=1,
            )
            confirmar.callback = self.confirmar_selecao_multipla_criatura
            self.confirmar_multipla = confirmar
            self.add_item(confirmar)

            anular = discord.ui.Button(
                label="Anular",
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            anular.callback = self.anular_selecao_multipla_criatura
            self.add_item(anular)

    async def confirmar_selecao_multipla_criatura(
        self,
        interaction: discord.Interaction,
    ) -> None:
        chave_pendentes = f"{self.finalidade}_pendentes"
        pendentes = [
            valor
            for valor in self.sessao.valores.get(chave_pendentes, "").splitlines()
            if valor
        ]
        if not pendentes:
            await interaction.response.send_message(
                embed=embed_fluxo(
                    self.sessao,
                    "Escolha uma opção",
                    "Marque pelo menos uma opção antes de confirmar.",
                ),
                ephemeral=True,
            )
            return

        self.sessao.valores.pop(chave_pendentes, None)
        if self.finalidade == "ano_estudo_criatura":
            pendentes.sort(key=ANOS.index)
            self.sessao.valores["ano_estudo"] = formatar_anos_estudo(pendentes)
            opcoes = opcoes_campo_criatura("Classificação")
            await interaction.response.edit_message(
                content=None,
                embed=embed_fluxo(
                    self.sessao,
                    "Classificação",
                    "Escolha a classificação da criatura.",
                ),
                view=OpcoesView(
                    self.sessao,
                    "Escolha a classificação",
                    opcoes,
                    finalidade="classificacao_criatura",
                ),
            )
            return

        ordem = {opcao.value: indice for indice, opcao in enumerate(self.seletor.options)}
        pendentes.sort(key=lambda valor: ordem.get(valor, len(ordem)))
        self.sessao.valores["tipo_aula"] = formatar_selecao_multipla(pendentes)
        await interaction.response.send_modal(FormularioModal(self.sessao, 1))

    async def anular_selecao_multipla_criatura(
        self,
        interaction: discord.Interaction,
    ) -> None:
        self.sessao.valores.pop(f"{self.finalidade}_pendentes", None)
        for opcao in self.seletor.options:
            opcao.default = False
        self.confirmar_multipla.disabled = True
        await interaction.response.edit_message(view=self)

    async def voltar_grupos_ingredientes(
        self,
        interaction: discord.Interaction,
    ) -> None:
        self.sessao.valores.pop("ingredientes_pendentes", None)
        await interaction.response.edit_message(
            content=None,
            embed=painel_ingredientes_pocao(
                self.sessao,
                "Escolha um grupo de ingredientes.",
                mostrar_resumo=True,
            ),
            view=OpcoesView(
                self.sessao,
                "Escolha um grupo de ingredientes",
                opcoes_grupos_ingredientes(),
                finalidade="grupo_ingredientes_pocao",
            ),
        )

    async def confirmar_ingredientes_pocao(
        self,
        interaction: discord.Interaction,
    ) -> None:
        pendentes = [
            ingrediente
            for ingrediente in self.sessao.valores.get(
                "ingredientes_pendentes", ""
            ).splitlines()
            if ingrediente
        ]
        if not pendentes:
            await interaction.response.send_message(
                embed=embed_fluxo(
                    self.sessao,
                    "Escolha um ingrediente",
                    "Marque pelo menos um ingrediente antes de confirmar.",
                ),
                ephemeral=True,
            )
            return

        selecionados = ingredientes_selecionados(self.sessao)
        chaves = {normalizar_rotulo(ingrediente) for ingrediente in selecionados}
        for ingrediente in pendentes:
            chave = normalizar_rotulo(ingrediente)
            if chave not in chaves:
                selecionados.append(ingrediente)
                chaves.add(chave)
        self.sessao.valores["ingredientes_selecionados"] = "\n".join(
            selecionados
        )
        self.sessao.valores.pop("ingredientes_pendentes", None)
        await interaction.response.edit_message(
            content=None,
            embed=painel_ingredientes_pocao(
                self.sessao,
                "Adicione outros ingredientes ou informe as quantidades.",
                mostrar_resumo=True,
            ),
            view=IngredientesPocaoView(self.sessao),
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        valor = self.seletor.values[0]

        if self.finalidade == "origem_criatura":
            self.sessao.valores["origem"] = valor
            await interaction.response.edit_message(
                content=None,
                embed=embed_fluxo(
                    self.sessao,
                    "Ano de Estudo",
                    "Escolha um ou mais anos em que a criatura será estudada.",
                ),
                view=OpcoesView(
                    self.sessao,
                    "Escolha um ou mais anos",
                    [discord.SelectOption(label=ano, value=ano) for ano in ANOS],
                    finalidade="ano_estudo_criatura",
                    minimo=1,
                    maximo=len(ANOS),
                ),
            )
            return

        if self.finalidade in {"ano_estudo_criatura", "tipo_aula_criatura"}:
            pendentes = list(self.seletor.values)
            self.sessao.valores[f"{self.finalidade}_pendentes"] = "\n".join(
                pendentes
            )
            chaves = {normalizar_rotulo(item) for item in pendentes}
            for opcao in self.seletor.options:
                opcao.default = normalizar_rotulo(opcao.value) in chaves
            self.confirmar_multipla.disabled = False
            await interaction.response.edit_message(view=self)
            return

        if self.finalidade == "classificacao_criatura":
            self.sessao.valores["classificacao"] = valor
            opcoes = opcoes_campo_criatura("Tipo de Aula")
            await interaction.response.edit_message(
                content=None,
                embed=embed_fluxo(
                    self.sessao,
                    "Tipo de Aula",
                    "Escolha um ou mais tipos de aula.",
                ),
                view=OpcoesView(
                    self.sessao,
                    "Escolha um ou mais tipos de aula",
                    opcoes,
                    finalidade="tipo_aula_criatura",
                    minimo=1,
                    maximo=len(opcoes),
                ),
            )
            return

        if self.finalidade == "categoria_feitico":
            self.sessao.opcao = valor
            await interaction.response.edit_message(
                content=None,
                embed=embed_fluxo(
                    self.sessao,
                    "Adicionar feitiço",
                    "Agora escolha o **Ano de desbloqueio**.",
                ),
                view=OpcoesView(
                    self.sessao,
                    "Escolha o ano de desbloqueio",
                    [discord.SelectOption(label=ano, value=ano) for ano in ANOS],
                    finalidade="ano_feitico",
                ),
            )
            return

        if self.finalidade == "quantidade_habilidades_origem":
            quantidade = int(valor)
            self.sessao.valores["quantidade_habilidades"] = valor
            for indice in range(quantidade + 1, 5):
                self.sessao.valores.pop(f"habilidade_{indice}_nome", None)
                self.sessao.valores.pop(f"habilidade_{indice}_custo", None)
                self.sessao.valores.pop(f"habilidade_{indice}_descricao", None)
            await interaction.response.send_modal(FormularioModal(self.sessao, 1))
            return

        if self.finalidade == "vertente_trevas":
            self.sessao.opcao = valor
            await interaction.response.edit_message(
                content=None,
                embed=embed_fluxo(
                    self.sessao,
                    "Adicionar Arte das Trevas",
                    "Agora escolha o **Grau de dificuldade**.",
                ),
                view=OpcoesView(
                    self.sessao,
                    "Escolha o grau de dificuldade",
                    [
                        discord.SelectOption(
                            label=grau,
                            value=grau,
                            description=f"Corrupção: {corrupcao}",
                        )
                        for grau, corrupcao in CORRUPCAO_POR_GRAU_TREVAS.items()
                    ],
                    finalidade="grau_trevas",
                ),
            )
            return

        if self.finalidade == "categoria_bindruna":
            self.sessao.opcao = valor
            opcoes = opcoes_runas_bindruna()
            await interaction.response.edit_message(
                content=None,
                embed=embed_fluxo(
                    self.sessao,
                    "Adicionar Bindrune",
                    "Agora escolha **de duas a seis runas** para a Bindrune.",
                ),
                view=OpcoesView(
                    self.sessao,
                    "Escolha de duas a seis runas",
                    opcoes,
                    finalidade="runas_bindruna",
                    minimo=2,
                    maximo=min(MAXIMO_RUNAS_BINDRUNA, len(opcoes)),
                ),
            )
            return

        if self.finalidade == "runas_bindruna":
            self.sessao.valores["runas_selecionadas"] = "\n".join(
                self.seletor.values
            )
            self.sessao.valores["indice_runa"] = "0"
            self.sessao.valores["runas"] = ""
            _, _, _, titulo, _ = dados_runa_bindruna(self.sessao)
            await interaction.response.edit_message(
                content=None,
                embed=embed_fluxo(
                    self.sessao,
                    "Palavras-chave da Bindrune",
                    f"Escolha a palavra-chave invocada de **{titulo}**.",
                ),
                view=view_palavras_bindruna(self.sessao),
            )
            return

        if self.finalidade == "palavras_bindruna":
            chaves, indice, _, titulo, palavras = dados_runa_bindruna(self.sessao)
            escolhidas = [palavras[chave] for chave in self.seletor.values]
            linha = f"{titulo}: {' e '.join(escolhidas)}"
            anteriores = self.sessao.valores.get("runas", "")
            self.sessao.valores["runas"] = "\n".join(
                parte for parte in (anteriores, linha) if parte
            )
            indice += 1
            self.sessao.valores["indice_runa"] = str(indice)

            if indice < len(chaves):
                _, _, _, proximo_titulo, _ = dados_runa_bindruna(self.sessao)
                await interaction.response.edit_message(
                    content=None,
                    embed=embed_fluxo(
                        self.sessao,
                        "Palavras-chave da Bindrune",
                        "Escolha a palavra-chave invocada de "
                        f"**{proximo_titulo}**.",
                    ),
                    view=view_palavras_bindruna(self.sessao),
                )
            else:
                await interaction.response.send_modal(
                    FormularioModal(self.sessao, 0)
                )
            return

        if self.finalidade == "ano_pocao":
            self.sessao.opcao = valor
            self.sessao.valores["ingredientes_selecionados"] = ""
            limpar_quantidades_ingredientes(self.sessao)
            await interaction.response.edit_message(
                content=None,
                embed=painel_ingredientes_pocao(
                    self.sessao,
                    "Agora escolha o **grupo dos ingredientes**. "
                    "Você poderá adicionar ingredientes de outros grupos depois.",
                ),
                view=OpcoesView(
                    self.sessao,
                    "Escolha um grupo de ingredientes",
                    opcoes_grupos_ingredientes(),
                    finalidade="grupo_ingredientes_pocao",
                ),
            )
            return

        if self.finalidade == "grupo_ingredientes_pocao":
            try:
                rotulo, ingredientes = paginas_ingredientes_oficiais()[int(valor)]
            except (IndexError, ValueError) as erro:
                raise ErroConteudo("O grupo de ingredientes selecionado é inválido.") from erro
            self.sessao.valores.pop("ingredientes_pendentes", None)
            await interaction.response.edit_message(
                content=None,
                embed=painel_ingredientes_pocao(
                    self.sessao,
                    "Escolha os ingredientes de "
                    f"**{rotulo_grupo_ingredientes(rotulo)}**.",
                    mostrar_resumo=True,
                ),
                view=OpcoesView(
                    self.sessao,
                    "Escolha um ou mais ingredientes",
                    [
                        discord.SelectOption(label=ingrediente, value=ingrediente)
                        for ingrediente in ingredientes
                    ],
                    finalidade="ingredientes_pocao",
                    minimo=1,
                    maximo=len(ingredientes),
                ),
            )
            return

        if self.finalidade == "ingredientes_pocao":
            pendentes = list(self.seletor.values)
            self.sessao.valores["ingredientes_pendentes"] = "\n".join(pendentes)
            chaves_pendentes = {
                normalizar_rotulo(ingrediente) for ingrediente in pendentes
            }
            for opcao in self.seletor.options:
                opcao.default = normalizar_rotulo(opcao.value) in chaves_pendentes
            self.confirmar_ingredientes.disabled = False
            await interaction.response.edit_message(
                content=None,
                embed=painel_ingredientes_pocao(
                    self.sessao,
                    "**Marcados neste grupo:**\n"
                    + "\n".join(f"• {ingrediente}" for ingrediente in pendentes)
                    + "\n\nUse **Confirmar** para adicioná-los "
                    "ou **Voltar** para descartar esta marcação.",
                    mostrar_resumo=True,
                ),
                view=self,
            )
            return

        if self.finalidade == "ano_feitico":
            self.sessao.valores["ano"] = valor
        elif self.finalidade == "grau_trevas":
            self.sessao.valores["grau"] = valor
        else:
            self.sessao.opcao = valor

        await interaction.response.send_modal(FormularioModal(self.sessao, 0))


class IngredientesPocaoView(ViewDoAutor):
    @discord.ui.button(
        label="Adicionar mais ingredientes",
        style=discord.ButtonStyle.primary,
    )
    async def adicionar_mais(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=painel_ingredientes_pocao(
                self.sessao,
                "Escolha outro grupo para adicionar mais ingredientes.",
                mostrar_resumo=True,
            ),
            view=OpcoesView(
                self.sessao,
                "Escolha um grupo de ingredientes",
                opcoes_grupos_ingredientes(),
                finalidade="grupo_ingredientes_pocao",
            ),
        )

    @discord.ui.button(
        label="Informar quantidades",
        style=discord.ButtonStyle.success,
    )
    async def informar_quantidades(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        selecionados = ingredientes_selecionados(self.sessao)
        if not selecionados:
            await interaction.response.send_message(
                embed=embed_fluxo(
                    self.sessao,
                    "Escolha um ingrediente",
                    "Escolha pelo menos um ingrediente antes de continuar.",
                ),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            QuantidadesIngredientesModal(self.sessao, 0)
        )

    @discord.ui.button(
        label="Limpar seleção",
        style=discord.ButtonStyle.secondary,
    )
    async def limpar_selecao(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        self.sessao.valores["ingredientes_selecionados"] = ""
        limpar_quantidades_ingredientes(self.sessao)
        await interaction.response.edit_message(
            content=None,
            embed=painel_ingredientes_pocao(
                self.sessao,
                "Seleção limpa. Escolha novamente o grupo dos ingredientes.",
            ),
            view=OpcoesView(
                self.sessao,
                "Escolha um grupo de ingredientes",
                opcoes_grupos_ingredientes(),
                finalidade="grupo_ingredientes_pocao",
            ),
        )


class QuantidadesIngredientesModal(discord.ui.Modal):
    TAMANHO_PAGINA = 5

    def __init__(self, sessao: SessaoAdicionar, pagina: int):
        selecionados = ingredientes_selecionados(sessao)
        total_paginas = max(
            1,
            (len(selecionados) + self.TAMANHO_PAGINA - 1) // self.TAMANHO_PAGINA,
        )
        super().__init__(title=f"💬 Ingredientes — {pagina + 1}/{total_paginas}")
        self.sessao = sessao
        self.pagina = pagina
        self.total_paginas = total_paginas
        inicio = pagina * self.TAMANHO_PAGINA
        self.entradas: list[tuple[int, discord.ui.TextInput]] = []

        for indice, ingrediente in enumerate(
            selecionados[inicio : inicio + self.TAMANHO_PAGINA],
            start=inicio,
        ):
            entrada = discord.ui.TextInput(
                label=ingrediente[:45],
                placeholder=placeholder_quantidade_ingrediente(ingrediente),
                required=True,
                max_length=100,
                default=(
                    sessao.valores.get(f"quantidade_ingrediente_{indice}") or None
                ),
            )
            self.entradas.append((indice, entrada))
            self.add_item(entrada)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        for indice, entrada in self.entradas:
            self.sessao.valores[f"quantidade_ingrediente_{indice}"] = (
                str(entrada.value).strip()
            )

        proxima = self.pagina + 1
        if proxima < self.total_paginas:
            await interaction.response.edit_message(
                content=None,
                embed=painel_ingredientes_pocao(
                    self.sessao,
                    f"Quantidades {self.pagina + 1}/{self.total_paginas} salvas. "
                    "Continue para preencher os próximos ingredientes.",
                    mostrar_resumo=True,
                ),
                view=ContinuarQuantidadesIngredientesView(self.sessao, proxima),
            )
            return

        try:
            self.sessao.valores["ingredientes"] = montar_lista_ingredientes(
                self.sessao
            )
        except ErroConteudo as erro:
            await interaction.response.edit_message(
                content=None,
                embed=embed_fluxo(
                    self.sessao,
                    "Revise as quantidades",
                    f"Não consegui salvar as quantidades: {erro}",
                ),
                view=ContinuarQuantidadesIngredientesView(self.sessao, self.pagina),
            )
            return

        await interaction.response.edit_message(
            content=None,
            embed=painel_ingredientes_pocao(
                self.sessao,
                "Quantidades confirmadas. Continue para preencher os dados da poção.",
                mostrar_resumo=True,
            ),
            view=ContinuarView(self.sessao, 0, "Continuar formulário da poção"),
        )


class ContinuarQuantidadesIngredientesView(ViewDoAutor):
    def __init__(self, sessao: SessaoAdicionar, pagina: int):
        super().__init__(sessao)
        self.pagina = pagina

        continuar = discord.ui.Button(
            label="Continuar quantidades",
            style=discord.ButtonStyle.success,
        )
        continuar.callback = self.continuar
        self.add_item(continuar)

        voltar = discord.ui.Button(
            label="Voltar aos ingredientes",
            style=discord.ButtonStyle.secondary,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def continuar(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            QuantidadesIngredientesModal(self.sessao, self.pagina)
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=painel_ingredientes_pocao(
                self.sessao,
                "Adicione outros ingredientes ou informe novamente as quantidades.",
                mostrar_resumo=True,
            ),
            view=IngredientesPocaoView(self.sessao),
        )


def opcoes_do_tipo(tipo: str) -> tuple[str, list[discord.SelectOption]]:
    if tipo == "feitico":
        return (
            "Escolha a categoria do feitiço",
            [
                discord.SelectOption(label=rotulo, value=chave)
                for chave, (rotulo, _) in CATEGORIAS_FEITICO.items()
            ],
        )

    if tipo == "trevas":
        return (
            "Escolha a vertente",
            [discord.SelectOption(label=nome, value=nome) for nome in VERTENTES_TREVAS],
        )

    if tipo == "bindruna":
        return (
            "Escolha a categoria da Bindrune",
            [
                discord.SelectOption(
                    label=nome,
                    value=nome,
                    description=f"{grau} — CD {cd} com duas runas",
                )
                for nome, (grau, cd) in CATEGORIAS_BINDRUNA.items()
            ],
        )

    if tipo == "pocao":
        return (
            "Escolha o ano da poção",
            [discord.SelectOption(label=ano, value=ano) for ano in ANOS],
        )

    if tipo == "criatura":
        return (
            "Escolha a periculosidade",
            [
                discord.SelectOption(label=perigo, value=perigo)
                for perigo in PERICULOSIDADES
            ],
        )

    if tipo == "habilidade":
        return (
            "Escolha a categoria da habilidade",
            [
                discord.SelectOption(label=str(dados["nome"]), value=chave)
                for chave, dados in CATEGORIAS_HABILIDADE.items()
            ],
        )

    raise ErroConteudo("Tipo de conteúdo desconhecido.")


class AprovacaoView(ViewDoAutor):
    def __init__(self, sessao: SessaoAdicionar):
        super().__init__(sessao)
        self.concluido = False

    @discord.ui.button(label="Aprovar", style=discord.ButtonStyle.success, emoji="✅")
    async def aprovar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        if self.concluido or self.sessao.preparado is None:
            await interaction.response.send_message(
                embed=embed_fluxo(
                    self.sessao,
                    "Envio encerrado",
                    "Este envio já foi encerrado.",
                ),
                ephemeral=True,
            )
            return

        preparado = self.sessao.preparado
        colisao = encontrar_colisao(preparado.destino_markdown)
        if colisao is not None:
            await interaction.response.send_message(
                embed=embed_fluxo(
                    self.sessao,
                    "Ficha já existente",
                    f"Já existe uma ficha chamada **{colisao.stem}** nessa categoria.",
                ),
                ephemeral=True,
            )
            return
        try:
            thread_id = encontrar_thread(preparado)
        except ErroConteudo as erro:
            await interaction.response.send_message(
                embed=embed_fluxo(self.sessao, "Thread não encontrada", str(erro)),
                ephemeral=True,
            )
            return

        if thread_id is None:
            await interaction.response.send_message(
                embed=embed_fluxo(
                    self.sessao,
                    "Thread não configurada",
                    "Não há uma thread configurada para "
                    f"**{preparado.secao_thread} — {preparado.chave_thread}**. "
                    "Nada foi salvo ou publicado.",
                ),
                ephemeral=True,
            )
            return

        self.concluido = True
        await interaction.response.defer(ephemeral=True)
        canal = interaction.client.get_channel(thread_id)
        if canal is None:
            try:
                canal = await interaction.client.fetch_channel(thread_id)
            except discord.HTTPException as erro:
                self.concluido = False
                await interaction.followup.send(
                    embed=embed_fluxo(
                        self.sessao,
                        "Falha ao acessar a thread",
                        f"Não consegui acessar a thread configurada: {erro}",
                    ),
                    ephemeral=True,
                )
                return

        if not hasattr(canal, "send"):
            self.concluido = False
            await interaction.followup.send(
                embed=embed_fluxo(
                    self.sessao,
                    "Canal inválido",
                    "O ID configurado não aponta para um canal publicável.",
                ),
                ephemeral=True,
            )
            return

        criados = []
        try:
            preparado.destino_markdown.parent.mkdir(parents=True, exist_ok=True)
            with preparado.destino_markdown.open(
                "x", encoding="utf-8", newline="\n"
            ) as arquivo:
                arquivo.write(preparado.markdown)
            criados.append(preparado.destino_markdown)

            mensagem = await canal.send(
                content=preparado.conteudo_publicacao,
                embeds=preparado.embeds,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (OSError, discord.HTTPException) as erro:
            for caminho in reversed(criados):
                try:
                    caminho.unlink(missing_ok=True)
                except OSError:
                    pass
            self.concluido = False
            await interaction.followup.send(
                embed=embed_fluxo(
                    self.sessao,
                    "Falha no envio",
                    f"O envio falhou e os novos arquivos foram revertidos: {erro}",
                ),
                ephemeral=True,
            )
            return

        self.stop()
        await interaction.edit_original_response(
            content=None,
            embed=embed_fluxo(
                self.sessao,
                "Conteúdo publicado",
                f"✅ **{preparado.nome}** foi salvo na biblioteca e publicado "
                f"na [thread correta]({mensagem.jump_url}).",
                emoji_titulo="✅",
            ),
            attachments=[],
            view=None,
        )

    @discord.ui.button(label="Descartar", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def descartar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        self.concluido = True
        self.stop()
        await interaction.response.edit_message(
            content=None,
            embed=embed_fluxo(
                self.sessao,
                "Conteúdo descartado",
                "Nada foi salvo ou publicado.",
                emoji_titulo="🗑️",
            ),
            attachments=[],
            view=None,
        )


class Adicionar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="add",
        description="Adiciona conteúdo à biblioteca do Grimory com aprovação.",
    )
    @app_commands.describe(
        categoria="Tipo de conteúdo que será adicionado"
    )
    @app_commands.choices(categoria=[
        app_commands.Choice(name="Feitiços", value="feitico"),
        app_commands.Choice(name="Arte das Trevas", value="trevas"),
        app_commands.Choice(name="Bindrune", value="bindruna"),
        app_commands.Choice(name="Poção", value="pocao"),
        app_commands.Choice(name="Criatura", value="criatura"),
        app_commands.Choice(name="Habilidade", value="habilidade"),
    ])
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def adicionar(
        self,
        interaction: discord.Interaction,
        categoria: app_commands.Choice[str],
    ):
        membro = interaction.user
        if not isinstance(membro, discord.Member) or not membro.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="💬 Permissão necessária",
                    description=(
                        "Você precisa da permissão **Gerenciar servidor** "
                        "para usar `/add`."
                    ),
                    color=COR_EMBED_FEITICO,
                ),
                ephemeral=True,
            )
            return

        tipo = categoria.value
        sessao = SessaoAdicionar(
            usuario_id=membro.id,
            tipo=tipo,
        )

        if tipo == "criatura" and not existe_thread_criaturas():
            await interaction.response.send_message(
                embed=embed_fluxo(
                    sessao,
                    "Categoria indisponível",
                    "A criação de criaturas ficará disponível quando a thread de "
                    "**Trato de Criaturas Mágicas** for cadastrada em "
                    "`threads-categorias.md`.",
                ),
                ephemeral=True,
            )
            return

        titulo, opcoes = opcoes_do_tipo(tipo)
        if tipo == "feitico":
            finalidade = "categoria_feitico"
        elif tipo == "trevas":
            finalidade = "vertente_trevas"
        elif tipo == "bindruna":
            finalidade = "categoria_bindruna"
        elif tipo == "pocao":
            finalidade = "ano_pocao"
        elif tipo == "habilidade":
            finalidade = "categoria_habilidade"
        else:
            finalidade = "formulario"
        await interaction.response.send_message(
            embed=embed_fluxo(
                sessao,
                f"Adicionar {categoria.name}",
                f"Tipo escolhido: **{categoria.name}**. {titulo}.",
            ),
            view=OpcoesView(sessao, titulo, opcoes, finalidade=finalidade),
            ephemeral=True,
        )
