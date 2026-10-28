"""Catálogo de regras gerais para o futuro comando de consulta de sistemas.

Os textos continuam em Markdown para que possam ser revisados sem alterar o
código. Este módulo apenas localiza sistemas e suas seções, preservando o
conteúdo original para a camada de apresentação.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_SISTEMAS = RAIZ_PROJETO / "biblioteca" / "sistemas"


@dataclass(frozen=True)
class Sistema:
    nome: str
    caminho: Path
    descricao: str


@dataclass(frozen=True)
class SecaoSistema:
    titulo: str
    conteudo: str


def listar_sistemas() -> list[Sistema]:
    """Retorna os sistemas publicados, em ordem alfabética."""
    if not PASTA_SISTEMAS.exists():
        return []
    sistemas: list[Sistema] = []
    for caminho in sorted(PASTA_SISTEMAS.glob("*.md"), key=lambda item: item.name.casefold()):
        if caminho.name.casefold() == "indice.md":
            continue
        texto = caminho.read_text(encoding="utf-8")
        linhas = texto.splitlines()
        titulo = next((linha[2:].strip() for linha in linhas if linha.startswith("# ")), caminho.stem)
        descricao = next((linha.strip() for linha in linhas if linha.strip() and not linha.startswith("#")), "")
        sistemas.append(Sistema(titulo, caminho, descricao))
    return sistemas


def ler_sistema(nome: str) -> str:
    """Lê um sistema pelo título ou pelo nome do arquivo."""
    procurado = nome.strip().casefold()
    for sistema in listar_sistemas():
        if sistema.nome.casefold() == procurado or sistema.caminho.stem.casefold() == procurado:
            return sistema.caminho.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Sistema não encontrado: {nome}")


def secoes_sistema(nome: str) -> list[SecaoSistema]:
    """Divide o Markdown em seções de segundo nível para menus de consulta."""
    texto = ler_sistema(nome)
    marcadores = list(re.finditer(r"(?m)^## (.+?)\s*$", texto))
    secoes: list[SecaoSistema] = []
    for indice, marcador in enumerate(marcadores):
        inicio = marcador.end()
        fim = marcadores[indice + 1].start() if indice + 1 < len(marcadores) else len(texto)
        conteudo = texto[inicio:fim].strip()
        secoes.append(SecaoSistema(marcador.group(1).strip(), conteudo))
    return secoes


def consultar_secao(nome: str, titulo: str) -> str:
    """Retorna uma seção completa, sem resumir ou reformatar seu conteúdo."""
    procurado = titulo.strip().casefold()
    for secao in secoes_sistema(nome):
        if secao.titulo.casefold() == procurado:
            return secao.conteudo
    raise KeyError(f"Seção não encontrada em {nome}: {titulo}")
