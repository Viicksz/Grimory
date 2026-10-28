from pathlib import Path
from unicodedata import combining, normalize

from utils.feiticos_combate import extrair_perfil, remover_bloco


PASTA_BIBLIOTECA = Path("biblioteca")
LIMITE_MENSAGEM_DISCORD = 1900
LIMITE_AUTOCOMPLETE_DISCORD = 25
ROTULO_DESCRICAO = "descricao"


class EntradaBiblioteca:
    def __init__(self, titulo: str, descricao: str, campos: dict[str, str], perfil_combate=None):
        self.titulo = titulo
        self.descricao = descricao
        self.campos = campos
        self.perfil_combate = perfil_combate


class BibliotecaCategoria:
    def __init__(self, nome_categoria: str):
        self.nome_categoria = nome_categoria
        self.pasta = PASTA_BIBLIOTECA / nome_categoria

    def listar_arquivos(self) -> list[Path]:
        if not self.pasta.exists():
            return []

        return sorted(
            self.pasta.rglob("*.md"),
            key=lambda arquivo: arquivo.stem.casefold(),
        )

    def listar_nomes(self) -> list[str]:
        return [arquivo.stem for arquivo in self.listar_arquivos()]

    def buscar_nomes(self, termo: str = "") -> list[str]:
        termo_normalizado = termo.casefold().strip()
        nomes = self.listar_nomes()

        if termo_normalizado:
            nomes = [
                nome
                for nome in nomes
                if termo_normalizado in nome.casefold()
            ]

        return nomes[:LIMITE_AUTOCOMPLETE_DISCORD]

    def encontrar_arquivo(self, nome: str) -> Path | None:
        nome_normalizado = nome.casefold().strip()

        for arquivo in self.listar_arquivos():
            if arquivo.stem.casefold() == nome_normalizado:
                return arquivo

        return None

    def ler_entrada(self, nome: str) -> str | None:
        arquivo = self.encontrar_arquivo(nome)

        if arquivo is None:
            return None

        return arquivo.read_text(encoding="utf-8").strip()

    def carregar_entrada(self, nome: str) -> EntradaBiblioteca | None:
        conteudo = self.ler_entrada(nome)

        if conteudo is None:
            return None

        return interpretar_markdown(conteudo)


def normalizar_rotulo(rotulo: str) -> str:
    sem_acentos = normalize("NFD", rotulo.casefold())
    texto = "".join(letra for letra in sem_acentos if not combining(letra))
    return texto.strip().rstrip(":")


def interpretar_markdown(conteudo: str) -> EntradaBiblioteca:
    perfil_combate = extrair_perfil(conteudo)
    conteudo = remover_bloco(conteudo)
    linhas = conteudo.splitlines()
    titulo = ""
    campos: dict[str, str] = {}
    rotulo_atual: str | None = None
    valores: list[str] = []

    for linha in linhas:
        linha_limpa = linha.strip()

        if linha_limpa.startswith("# "):
            titulo = linha_limpa.removeprefix("# ").strip()
            continue

        if not linha_limpa:
            if rotulo_atual is not None and valores:
                valores.append("")

            continue

        if linha_limpa.endswith(":"):
            if rotulo_atual is not None:
                campos[rotulo_atual] = "\n".join(valores).strip()

            rotulo_atual = linha_limpa.rstrip(":").strip()
            valores = []
            continue

        if rotulo_atual is not None:
            valores.append(linha_limpa)

    if rotulo_atual is not None:
        campos[rotulo_atual] = "\n".join(valores).strip()

    descricao = ""
    campos_embed = {}

    for rotulo, valor in campos.items():
        if normalizar_rotulo(rotulo) == ROTULO_DESCRICAO:
            descricao = valor
        else:
            campos_embed[rotulo] = valor

    return EntradaBiblioteca(
        titulo=titulo,
        descricao=descricao,
        campos=campos_embed,
        perfil_combate=perfil_combate,
    )


def dividir_para_discord(texto: str) -> list[str]:
    if len(texto) <= LIMITE_MENSAGEM_DISCORD:
        return [texto]

    partes = []
    restante = texto

    while len(restante) > LIMITE_MENSAGEM_DISCORD:
        corte = restante.rfind("\n\n", 0, LIMITE_MENSAGEM_DISCORD)

        if corte == -1:
            corte = restante.rfind("\n", 0, LIMITE_MENSAGEM_DISCORD)

        if corte == -1:
            corte = LIMITE_MENSAGEM_DISCORD

        partes.append(restante[:corte].strip())
        restante = restante[corte:].strip()

    if restante:
        partes.append(restante)

    return partes
