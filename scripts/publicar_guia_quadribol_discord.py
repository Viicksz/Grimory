from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import aiohttp
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
CONFIGURACAO = {
    **dotenv_values(RAIZ / ".env.quadribol"),
    **dotenv_values(RAIZ / ".env.discord-webhook"),
}

from utils.quadribol import carregar_manobras


GUIA = RAIZ / "exports" / "quadribol" / "guia-jogadores-discord.md"
IMAGEM_CINEMATICA = Path(r"C:\Users\VickS\Downloads\quidditch-game.webp")
IMAGEM_CAMPO = Path(r"C:\Users\VickS\Downloads\render top.png")
THREAD_MANOBRAS_ID = "1540854369208107071"

COR_GERAL = 0xB88A36
COR_GOLES = 0xA9343A
COR_BALACO = 0x66717E
COR_POMO = 0xD8AD32
COR_MANOBRA = 0x4F7A57
COR_EFEITO = 0x72548B
COR_FALTA = 0xA63D40

MENSAGENS_PUBLICADAS = {
    "guia-01": "1540854344394743831",
    "guia-02": "1540854349574447307",
    "guia-05": "1540854352460120077",
    "guia-07": "1540854356121882757",
    "guia-09": "1540854359728979990",
    # As três mensagens foram redistribuídas para que a apresentação das
    # manobras apareça imediatamente antes do catálogo de fichas.
    "guia-12": "1540854363222966343",
    "guia-15": "1540854366343397490",
    "guia-11": "1540854369208107071",
    "manobra-01": "1540876252477530174",
    "manobra-02": "1540876255379988491",
    "manobra-03": "1540876258060144683",
    "manobra-04": "1540876260824055890",
    "manobra-05": "1540876263609081907",
    "manobra-06": "1540876266989690962",
    "manobra-07": "1540876270068568195",
    "manobra-08": "1540876273159512196",
    "manobra-09": "1540876276116496435",
    "manobra-10": "1540876279178334259",
    "manobra-11": "1540876281892184115",
    "manobra-12": "1540876284421345415",
    "manobra-13": "1540876287550160938",
    "manobra-14": "1540876290809139251",
    "manobra-15": "1540876293799673867",
}


def _cor_secao(numero: int) -> int:
    if numero in {5, 6}:
        return COR_GOLES
    if numero in {7, 8}:
        return COR_BALACO
    if numero in {9, 10}:
        return COR_POMO
    if numero == 11:
        return COR_MANOBRA
    if numero in {12, 13, 14}:
        return COR_EFEITO
    if numero == 15:
        return COR_FALTA
    return COR_GERAL


def carregar_secoes() -> dict[int, dict[str, object]]:
    texto = GUIA.read_text(encoding="utf-8-sig")
    corpo = texto.split("## Apêndice", 1)[0]
    blocos = re.split(r"(?m)^## (\d{2}) — [^\n]+\n", corpo)[1:]
    secoes: dict[int, dict[str, object]] = {}
    for indice in range(0, len(blocos), 2):
        numero = int(blocos[indice])
        linhas = blocos[indice + 1].strip().splitlines()
        titulo = linhas.pop(0).removeprefix("# ").strip()
        while linhas and not linhas[0].strip():
            linhas.pop(0)
        subtitulo = ""
        if linhas and linhas[0].startswith("## "):
            subtitulo = linhas.pop(0).removeprefix("## ").strip()
            while linhas and not linhas[0].strip():
                linhas.pop(0)
        linhas_compactas: list[str] = []
        for numero_linha, linha in enumerate(linhas):
            if not linha.strip():
                anterior = linhas[numero_linha - 1].lstrip() if numero_linha else ""
                seguinte = (
                    linhas[numero_linha + 1].lstrip()
                    if numero_linha + 1 < len(linhas)
                    else ""
                )
                if anterior.startswith(">") or seguinte.startswith(">"):
                    continue
            linhas_compactas.append(linha)
        corpo_descricao = "\n".join(linhas_compactas).strip()
        descricao = (
            f"**{subtitulo}**\n{corpo_descricao}"
            if subtitulo
            else corpo_descricao
        )
        secoes[numero] = {
            "title": titulo,
            "description": descricao,
            "color": _cor_secao(numero),
        }
    return secoes


def embeds_manobras() -> list[dict[str, object]]:
    embeds: list[dict[str, object]] = []
    for manobra in carregar_manobras():
        cd = "Não exige teste" if manobra.cd == 0 else str(manobra.cd)
        embeds.append(
            {
                "title": f"🧩 {manobra.nome}",
                "description": f"_{manobra.descricao}_",
                "color": COR_MANOBRA,
                "fields": [
                    {"name": "CD", "value": f"» {cd}", "inline": True},
                    {
                        "name": "Requisito de Quadribol",
                        "value": f"» +{manobra.requisito_quadribol}",
                        "inline": True,
                    },
                    {
                        "name": "Posições",
                        "value": "» " + ", ".join(manobra.posicoes),
                        "inline": True,
                    },
                    {
                        "name": "Participantes",
                        "value": f"» {manobra.participantes}",
                        "inline": False,
                    },
                    {"name": "Execução", "value": f"» {manobra.execucao}", "inline": False},
                    {"name": "Benefício", "value": f"» {manobra.beneficio}", "inline": False},
                ],
            }
        )
    return embeds


def montar_publicacoes() -> list[dict[str, object]]:
    secoes = carregar_secoes()
    secoes[1]["image"] = {"url": "attachment://quidditch-game.webp"}
    secoes[1]["thumbnail"] = {"url": "attachment://render-top.png"}
    grupos = [
        [1],
        [2, 3, 4],
        [5, 6],
        [7, 8],
        [9, 10],
        [12, 13, 14],
        [15],
        [11],
    ]
    publicacoes = [
        {
            "nome": f"guia-{grupo[0]:02d}",
            "embeds": [secoes[numero] for numero in grupo],
            "imagens": grupo == [1],
        }
        for grupo in grupos
    ]
    manobras = embeds_manobras()
    for indice, manobra in enumerate(manobras, start=1):
        publicacoes.append(
            {
                "nome": f"manobra-{indice:02d}",
                "embeds": [manobra],
                "imagens": False,
            }
        )
    return publicacoes


def validar(publicacoes: list[dict[str, object]]) -> None:
    for publicacao in publicacoes:
        embeds = publicacao["embeds"]
        if not isinstance(embeds, list) or not 1 <= len(embeds) <= 10:
            raise ValueError(f"{publicacao['nome']}: quantidade inválida de embeds.")
        total = 0
        for embed in embeds:
            titulo = str(embed.get("title", ""))
            descricao = str(embed.get("description", ""))
            if len(titulo) > 256:
                raise ValueError(f"{publicacao['nome']}: título excede 256 caracteres.")
            if len(descricao) > 4096:
                raise ValueError(f"{publicacao['nome']}: descrição excede 4096 caracteres.")
            total += len(titulo) + len(descricao)
            campos = embed.get("fields", [])
            if len(campos) > 25:
                raise ValueError(f"{publicacao['nome']}: mais de 25 campos.")
            for campo in campos:
                if len(str(campo["name"])) > 256 or len(str(campo["value"])) > 1024:
                    raise ValueError(f"{publicacao['nome']}: campo excede o limite.")
                total += len(str(campo["name"])) + len(str(campo["value"]))
        if total > 6000:
            raise ValueError(f"{publicacao['nome']}: embeds somam {total}/6000 caracteres.")


async def enviar(
    sessao: aiohttp.ClientSession,
    webhook: str,
    publicacao: dict[str, object],
) -> dict[str, object]:
    payload = {
        "embeds": publicacao["embeds"],
        "allowed_mentions": {"parse": []},
    }
    parametros = "wait=true"
    if str(publicacao["nome"]).startswith("manobra-"):
        parametros += f"&thread_id={THREAD_MANOBRAS_ID}"
    destino = webhook + ("&" if "?" in webhook else "?") + parametros
    while True:
        if publicacao["imagens"]:
            formulario = aiohttp.FormData()
            formulario.add_field("payload_json", json.dumps(payload, ensure_ascii=False))
            formulario.add_field(
                "files[0]",
                IMAGEM_CINEMATICA.read_bytes(),
                filename="quidditch-game.webp",
                content_type="image/webp",
            )
            formulario.add_field(
                "files[1]",
                IMAGEM_CAMPO.read_bytes(),
                filename="render-top.png",
                content_type="image/png",
            )
            resposta = await sessao.post(destino, data=formulario)
        else:
            resposta = await sessao.post(destino, json=payload)
        if resposta.status == 429:
            dados = await resposta.json()
            await asyncio.sleep(float(dados.get("retry_after", 1)))
            continue
        corpo = await resposta.text()
        if resposta.status >= 400:
            raise RuntimeError(
                f"Falha ao publicar {publicacao['nome']}: HTTP {resposta.status}: {corpo}"
            )
        return json.loads(corpo)


async def publicar(webhook: str, publicacoes: list[dict[str, object]]) -> None:
    resultados: list[dict[str, str]] = []
    async with aiohttp.ClientSession() as sessao:
        for publicacao in publicacoes:
            mensagem = await enviar(sessao, webhook, publicacao)
            resultados.append(
                {
                    "nome": str(publicacao["nome"]),
                    "id": str(mensagem["id"]),
                    "canal": str(mensagem["channel_id"]),
                }
            )
            await asyncio.sleep(0.35)
    print(json.dumps(resultados, ensure_ascii=False, indent=2))


async def atualizar(webhook: str, publicacoes: list[dict[str, object]]) -> None:
    resultados: list[dict[str, str]] = []
    async with aiohttp.ClientSession() as sessao:
        for publicacao in publicacoes:
            nome = str(publicacao["nome"])
            mensagem_id = MENSAGENS_PUBLICADAS[nome]
            destino = f"{webhook}/messages/{mensagem_id}"
            if nome.startswith("manobra-"):
                destino += f"?thread_id={THREAD_MANOBRAS_ID}"
            payload = {
                "embeds": publicacao["embeds"],
                "allowed_mentions": {"parse": []},
            }
            while True:
                resposta = await sessao.patch(destino, json=payload)
                if resposta.status == 429:
                    dados = await resposta.json()
                    await asyncio.sleep(float(dados.get("retry_after", 1)))
                    continue
                corpo = await resposta.text()
                if resposta.status >= 400:
                    raise RuntimeError(
                        f"Falha ao atualizar {nome}: HTTP {resposta.status}: {corpo}"
                    )
                mensagem = json.loads(corpo)
                resultados.append({"nome": nome, "id": str(mensagem["id"])})
                break
            await asyncio.sleep(0.35)
    print(json.dumps(resultados, ensure_ascii=False, indent=2))


def main() -> None:
    analisador = argparse.ArgumentParser()
    analisador.add_argument("--validar", action="store_true")
    analisador.add_argument("--atualizar", action="store_true")
    argumentos = analisador.parse_args()
    publicacoes = montar_publicacoes()
    validar(publicacoes)
    if argumentos.validar:
        print(
            json.dumps(
                {
                    "publicacoes": len(publicacoes),
                    "embeds": sum(len(item["embeds"]) for item in publicacoes),
                    "manobras": len(embeds_manobras()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    webhook = (
        os.environ.get("GRIMORY_QUADRIBOL_WEBHOOK")
        or CONFIGURACAO.get("GRIMORY_QUADRIBOL_WEBHOOK")
        or ""
    ).strip()
    if not webhook:
        raise SystemExit("Defina GRIMORY_QUADRIBOL_WEBHOOK antes de publicar.")
    if not IMAGEM_CINEMATICA.is_file() or not IMAGEM_CAMPO.is_file():
        raise SystemExit("As duas imagens do campo precisam existir antes da publicação.")
    if argumentos.atualizar:
        asyncio.run(atualizar(webhook, publicacoes))
    else:
        asyncio.run(publicar(webhook, publicacoes))


if __name__ == "__main__":
    main()
