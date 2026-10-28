from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import discord


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
EXTENSOES_PERMITIDAS = {".png", ".jpg", ".jpeg", ".webp"}
LIMITE_IMAGEM = 25 * 1024 * 1024


@dataclass(frozen=True)
class AnexoLocal:
    caminho: Path
    nome: str

    def arquivo_discord(self) -> discord.File:
        return discord.File(self.caminho, filename=self.nome)


def _slug(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    sem_acentos = "".join(c for c in normalizado if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", sem_acentos.casefold()).strip("-") or "imagem"


def extensao_imagem(conteudo: bytes) -> str:
    if conteudo.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if conteudo.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if len(conteudo) >= 12 and conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("O arquivo precisa ser uma imagem PNG, JPG ou WEBP válida.")


def referencia_imagem(registro: dict[str, str]) -> str:
    return (registro.get("arquivo") or registro.get("url") or "").strip()


def resolver_anexo(referencia: str, prefixo: str = "imagem") -> AnexoLocal | None:
    referencia = referencia.strip()
    if not referencia or referencia == "--" or referencia.startswith(("http://", "https://")):
        return None
    caminho = (RAIZ_PROJETO / referencia.replace("/", "\\")).resolve()
    try:
        caminho.relative_to(RAIZ_PROJETO.resolve())
    except ValueError as erro:
        raise ValueError("A imagem cadastrada está fora da biblioteca do Grimory.") from erro
    if not caminho.is_file() or caminho.suffix.casefold() not in EXTENSOES_PERMITIDAS:
        raise ValueError(f"A imagem local não foi encontrada: {referencia}")
    identificador = hashlib.sha256(referencia.encode("utf-8")).hexdigest()[:10]
    return AnexoLocal(caminho, f"{_slug(prefixo)}-{identificador}{caminho.suffix.casefold()}")


def aplicar_imagem(embed: discord.Embed, referencia: str, prefixo: str = "imagem") -> AnexoLocal | None:
    anexo = resolver_anexo(referencia, prefixo)
    if anexo is not None:
        embed.set_image(url=f"attachment://{anexo.nome}")
    elif referencia.startswith(("http://", "https://")):
        embed.set_image(url=referencia)
    return anexo


def criar_arquivos_discord(anexos: list[AnexoLocal] | tuple[AnexoLocal, ...]) -> list[discord.File]:
    unicos: dict[str, AnexoLocal] = {anexo.nome: anexo for anexo in anexos}
    return [anexo.arquivo_discord() for anexo in unicos.values()]


async def salvar_upload_ficha(
    anexo: discord.Attachment,
    grupo: str,
    personagem: str,
    titulo: str,
) -> str:
    if anexo.size > LIMITE_IMAGEM:
        raise ValueError("A imagem ultrapassa o limite de 25 MB.")
    conteudo = await anexo.read()
    extensao = extensao_imagem(conteudo)
    pasta = RAIZ_PROJETO / "biblioteca" / "fichas" / "imagens" / _slug(grupo)
    pasta.mkdir(parents=True, exist_ok=True)
    base = _slug(f"{personagem}-{titulo or 'aparencia'}")
    digest = hashlib.sha256(conteudo).hexdigest()[:10]
    destino = pasta / f"{base}-{digest}{extensao}"
    if destino.exists():
        if destino.read_bytes() != conteudo:
            raise ValueError("Já existe outra imagem usando esse identificador.")
    else:
        destino.write_bytes(conteudo)
    return destino.relative_to(RAIZ_PROJETO).as_posix()


async def salvar_upload_item(
    anexo: discord.Attachment,
    personagem: str,
    item: str,
) -> str:
    if anexo.size > LIMITE_IMAGEM:
        raise ValueError("A imagem ultrapassa o limite de 25 MB.")
    conteudo = await anexo.read()
    extensao = extensao_imagem(conteudo)
    pasta = (
        RAIZ_PROJETO
        / "biblioteca"
        / "fichas"
        / "imagens"
        / "itens"
        / _slug(personagem)
    )
    pasta.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(conteudo).hexdigest()[:10]
    destino = pasta / f"{_slug(item)}-{digest}{extensao}"
    if destino.exists():
        if destino.read_bytes() != conteudo:
            raise ValueError("Já existe outra imagem usando esse identificador.")
    else:
        destino.write_bytes(conteudo)
    return destino.relative_to(RAIZ_PROJETO).as_posix()
