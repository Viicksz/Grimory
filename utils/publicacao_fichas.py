from __future__ import annotations

import re
from pathlib import Path

import discord

from utils.biblioteca import normalizar_rotulo
from utils.midia import AnexoLocal, criar_arquivos_discord


ARQUIVO_THREADS = Path(__file__).resolve().parents[1] / "biblioteca" / "modelos" / "threads-categorias.md"


class ErroPublicacaoFicha(RuntimeError):
    pass


def carregar_destinos_fichas() -> dict[tuple[str, str], int]:
    if not ARQUIVO_THREADS.is_file():
        raise ErroPublicacaoFicha("O cadastro das threads não foi encontrado.")
    secao = ""
    destinos: dict[tuple[str, str], int] = {}
    for linha in ARQUIVO_THREADS.read_text(encoding="utf-8-sig").splitlines():
        if linha.startswith("## "):
            secao = linha.removeprefix("## ").strip()
            continue
        correspondencia = re.match(r"^-\s+(.+?):\s*(\d{15,22})\s*$", linha.strip())
        if secao and correspondencia:
            chave, identificador = correspondencia.groups()
            destinos[(normalizar_rotulo(secao), normalizar_rotulo(chave))] = int(identificador)
    return destinos


def destino_personagem(grupo: str) -> int:
    destino = carregar_destinos_fichas().get(
        (normalizar_rotulo("Fichas de Personagem"), normalizar_rotulo(grupo))
    )
    if destino is None:
        raise ErroPublicacaoFicha(f"Não há uma thread configurada para fichas do grupo {grupo}.")
    return destino


def destino_criatura() -> int:
    destino = carregar_destinos_fichas().get(
        (normalizar_rotulo("Fichas de Criatura"), normalizar_rotulo("Criaturas"))
    )
    if destino is None:
        raise ErroPublicacaoFicha("Não há uma thread configurada para fichas de criatura.")
    return destino


def cabecalho_personagem(nome: str, grupo: str) -> str:
    return (
        "## ══════◄••👤••►══════\n"
        f"## {nome}\n"
        f"_Ficha de Personagem • {grupo}_\n"
        "## ══════◄••👤••►══════"
    )


def cabecalho_personagem_parte_2(nome: str) -> str:
    # Partes excedentes pertencem visualmente ao cabeçalho da mensagem
    # principal e, por isso, não recebem um novo título textual.
    return ""


def excede_limite_mensagem(embeds: list[discord.Embed]) -> bool:
    return len(embeds) > 10 or sum(len(embed) for embed in embeds) > 6000


def cabecalho_criatura(nome: str, periculosidade: str) -> str:
    return (
        "## ══════◄••🐾••►══════\n"
        f"## {nome}\n"
        f"_Ficha de Criatura • {periculosidade}_\n"
        "## ══════◄••🐾••►══════"
    )


async def publicar_ou_atualizar_ficha(
    cliente: discord.Client,
    thread_id: int,
    embeds: list[discord.Embed],
    mensagem_id: int = 0,
    conteudo: str = "",
    *,
    anexos: list[AnexoLocal] | tuple[AnexoLocal, ...] = (),
) -> discord.Message:
    canal = cliente.get_channel(thread_id)
    if canal is None:
        try:
            canal = await cliente.fetch_channel(thread_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException) as erro:
            raise ErroPublicacaoFicha(f"Não consegui acessar a thread configurada: {erro}") from erro
    if not hasattr(canal, "send"):
        raise ErroPublicacaoFicha("O destino configurado não permite publicar mensagens.")
    if mensagem_id and hasattr(canal, "fetch_message"):
        try:
            mensagem = await canal.fetch_message(mensagem_id)
        except discord.NotFound:
            mensagem = None
        except (discord.Forbidden, discord.HTTPException) as erro:
            raise ErroPublicacaoFicha(f"Não consegui localizar a publicação da ficha: {erro}") from erro
        if mensagem is not None:
            try:
                argumentos = {
                    "content": conteudo,
                    "embeds": embeds,
                    "allowed_mentions": discord.AllowedMentions.none(),
                }
                arquivos: list[discord.File] = []
                if anexos:
                    arquivos = criar_arquivos_discord(anexos)
                    argumentos["attachments"] = arquivos
                try:
                    await mensagem.edit(**argumentos)
                finally:
                    for arquivo in arquivos:
                        arquivo.close()
            except (discord.Forbidden, discord.HTTPException) as erro:
                raise ErroPublicacaoFicha(f"Não consegui atualizar a publicação da ficha: {erro}") from erro
            return mensagem
    try:
        argumentos = {
            "content": conteudo,
            "embeds": embeds,
            "allowed_mentions": discord.AllowedMentions.none(),
        }
        arquivos: list[discord.File] = []
        if anexos:
            arquivos = criar_arquivos_discord(anexos)
            argumentos["files"] = arquivos
        try:
            return await canal.send(**argumentos)
        finally:
            for arquivo in arquivos:
                arquivo.close()
    except (discord.Forbidden, discord.HTTPException) as erro:
        raise ErroPublicacaoFicha(f"Não consegui publicar a ficha: {erro}") from erro


async def excluir_publicacao_ficha(
    cliente: discord.Client,
    thread_id: int,
    mensagem_id: int,
) -> None:
    if not mensagem_id:
        return
    canal = cliente.get_channel(thread_id)
    if canal is None:
        try:
            canal = await cliente.fetch_channel(thread_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException) as erro:
            raise ErroPublicacaoFicha(f"Não consegui acessar a thread configurada: {erro}") from erro
    if not hasattr(canal, "fetch_message"):
        raise ErroPublicacaoFicha("O destino configurado não permite localizar mensagens.")
    try:
        mensagem = await canal.fetch_message(mensagem_id)
        await mensagem.delete()
    except discord.NotFound:
        return
    except (discord.Forbidden, discord.HTTPException) as erro:
        raise ErroPublicacaoFicha(f"Não consegui remover a parte excedente da ficha: {erro}") from erro
