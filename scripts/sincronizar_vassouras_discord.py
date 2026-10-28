from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from dotenv import dotenv_values

from comandos.quadribol import anexos_vassoura, montar_publicacao_linha_vassouras
from utils.quadribol import linhas_vassouras


THREAD_ID = "1516602986267283588"
MENSAGENS = {
    "Artesanal": "1533214515108384954",
    "Twigger": "1533214517473968282",
    "Comet": "1533214519092838584",
    "Bluebottle": "1533214520074305702",
    "Cleansweep": "1533214522242764882",
    "Cavalier": "1533214525069852838",
    "Swiftstick": "1533214526462365882",
    "Starsweeper": "1533214545881862299",
    "Stormrider": "1533214546960060603",
    "Estrela Cadente": "1533214549107540072",
    "Nimbus": "1533214551120543829",
    "Yajirushi": "1533214552668246131",
    "Oakshaft": "1533214555117977694",
    "Onda Aérea": "1533214556979986626",
    "Tinderblast": "1533214578031198343",
    "Thunderbolt": "1533214579897929813",
    "Turbo": "1533214581852471474",
    "Firebolt": "1533214583399907503",
}


def webhook_configurado() -> str:
    valores = {
        chave.lstrip("\ufeff"): valor
        for chave, valor in dotenv_values(".env").items()
    }
    return (
        os.getenv("GRIMORY_VASSOURAS_WEBHOOK_URL")
        or valores.get("GRIMORY_VASSOURAS_WEBHOOK_URL", "")
        or ""
    ).strip()


def decompor_webhook(url: str) -> tuple[str, str]:
    encontrado = re.fullmatch(
        r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/(\d+)/([^/?]+).*",
        url,
    )
    if not encontrado:
        raise ValueError("GRIMORY_VASSOURAS_WEBHOOK_URL não contém um webhook válido.")
    return encontrado.group(1), encontrado.group(2)


def bot_token_configurado() -> str:
    valores = {
        chave.lstrip("\ufeff"): valor
        for chave, valor in dotenv_values(".env").items()
    }
    return (os.getenv("DISCORD_TOKEN") or valores.get("DISCORD_TOKEN", "") or "").strip()


def requisitar(
    url: str,
    *,
    metodo: str = "GET",
    dados: dict | None = None,
    autorizacao: str = "",
) -> dict:
    corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8") if dados is not None else None
    for tentativa in range(4):
        requisicao = urllib.request.Request(
            url,
            data=corpo,
            method=metodo,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Grimory-Vassouras/1.0",
                **({"Authorization": autorizacao} if autorizacao else {}),
            },
        )
        try:
            with urllib.request.urlopen(requisicao, timeout=30) as resposta:
                return json.load(resposta)
        except urllib.error.HTTPError as erro:
            if erro.code != 429 or tentativa == 3:
                detalhe = erro.read().decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"Discord respondeu {erro.code}: {detalhe}") from erro
            try:
                espera = float(json.loads(erro.read()).get("retry_after", 1))
            except (ValueError, json.JSONDecodeError):
                espera = 1
            time.sleep(max(espera, 0.5))
    raise RuntimeError("Não foi possível concluir a solicitação ao Discord.")


def requisitar_multipart(
    url: str,
    payload: dict,
    arquivos,
    *,
    autorizacao: str,
) -> dict:
    limite = f"grimory-{uuid.uuid4().hex}"
    partes: list[bytes] = []

    def campo(nome: str, conteudo: bytes, tipo: str, arquivo: str = "") -> None:
        disposicao = f'form-data; name="{nome}"'
        if arquivo:
            disposicao += f'; filename="{arquivo}"'
        partes.extend(
            [
                f"--{limite}\r\n".encode(),
                f"Content-Disposition: {disposicao}\r\n".encode(),
                f"Content-Type: {tipo}\r\n\r\n".encode(),
                conteudo,
                b"\r\n",
            ]
        )

    campo(
        "payload_json",
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        "application/json",
    )
    for indice, anexo in enumerate(arquivos):
        campo(
            f"files[{indice}]",
            anexo.caminho.read_bytes(),
            mimetypes.guess_type(anexo.nome)[0] or "application/octet-stream",
            anexo.nome,
        )
    partes.append(f"--{limite}--\r\n".encode())
    corpo = b"".join(partes)
    for tentativa in range(8):
        requisicao = urllib.request.Request(
            url,
            data=corpo,
            method="PATCH",
            headers={
                "Authorization": autorizacao,
                "Content-Type": f"multipart/form-data; boundary={limite}",
                "User-Agent": "Grimory-Vassouras/1.0",
            },
        )
        try:
            with urllib.request.urlopen(requisicao, timeout=60) as resposta:
                return json.load(resposta)
        except urllib.error.HTTPError as erro:
            detalhe_completo = erro.read().decode("utf-8", errors="replace")
            if erro.code != 429 or tentativa == 7:
                raise RuntimeError(
                    f"Discord respondeu {erro.code}: {detalhe_completo[:500]}"
                ) from erro
            try:
                espera = float(json.loads(detalhe_completo).get("retry_after", 2))
            except (ValueError, json.JSONDecodeError):
                espera = 2
            time.sleep(max(espera, 1) + 0.25)
    raise RuntimeError("Não foi possível concluir a edição no Discord.")


def anexos_preservados(mensagem: dict) -> list[dict]:
    return [
        {
            chave: anexo[chave]
            for chave in ("id", "filename", "description")
            if chave in anexo and anexo[chave] is not None
        }
        for anexo in mensagem.get("attachments", [])
    ]


def limpar_embed_discord(embed: dict, anexos: list[dict] | None = None) -> dict:
    limpo = json.loads(json.dumps(embed))
    for atributo in ("type", "flags", "content_scan_version"):
        limpo.pop(atributo, None)
    for chave in ("image", "thumbnail"):
        midia = limpo.get(chave)
        if isinstance(midia, dict):
            for atributo in ("proxy_url", "width", "height", "content_type", "placeholder", "placeholder_version"):
                midia.pop(atributo, None)
            url = urllib.parse.unquote(str(midia.get("url", "")))
            nome_url = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]
            if nome_url.startswith("vassoura-"):
                midia["url"] = f"attachment://{nome_url}"
            for anexo in anexos or []:
                nome = str(anexo.get("filename", ""))
                if nome and (
                    url == anexo.get("url")
                    or url == anexo.get("proxy_url")
                    or url.endswith(f"/{nome}")
                    or f"/{nome}?" in url
                ):
                    midia["url"] = f"attachment://{nome}"
                    break
    return limpo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    argumentos = parser.parse_args()
    token = bot_token_configurado()
    if not token:
        raise SystemExit("Defina DISCORD_TOKEN no .env antes da sincronização.")
    autorizacao = f"Bot {token}"
    identidade = requisitar(
        "https://discord.com/api/v10/users/@me", autorizacao=autorizacao
    )
    catalogo = linhas_vassouras()
    if set(catalogo) != set(MENSAGENS):
        faltantes = sorted(set(catalogo) ^ set(MENSAGENS))
        raise SystemExit(f"Mapa de mensagens incompleto: {', '.join(faltantes)}")

    atualizadas = 0
    for linha, mensagem_id in MENSAGENS.items():
        consulta = f"https://discord.com/api/v10/channels/{THREAD_ID}/messages/{mensagem_id}"
        mensagem = requisitar(consulta, autorizacao=autorizacao)
        if str(mensagem.get("author", {}).get("id", "")) != str(identidade.get("id", "")):
            raise SystemExit(f"{linha}: a mensagem não pertence ao bot atual.")
        modelos = catalogo[linha]
        conteudo, embeds = montar_publicacao_linha_vassouras(linha, modelos)
        anexos_por_nome = {
            anexo.nome: anexo
            for modelo in modelos
            for anexo in anexos_vassoura(modelo)
        }
        anexos = list(anexos_por_nome.values())
        payload = {
            "content": conteudo,
            "embeds": [embed.to_dict() for embed in embeds],
            "attachments": [
                {"id": indice, "filename": anexo.nome}
                for indice, anexo in enumerate(anexos)
            ],
        }
        mudou = (
            mensagem.get("content", "") != conteudo
            or [
                limpar_embed_discord(item, mensagem.get("attachments", []))
                for item in mensagem.get("embeds", [])
            ]
            != [limpar_embed_discord(item) for item in payload["embeds"]]
        )
        if mudou and argumentos.apply:
            requisitar_multipart(
                consulta,
                payload,
                anexos,
                autorizacao=autorizacao,
            )
            atualizadas += 1
            print(f"Atualizada: {linha}")
        else:
            estado = "precisa atualizar" if mudou else "já está atualizada"
            print(f"{linha}: {estado}")
        time.sleep(0.35)
    print(f"{atualizadas} publicação(ões) atualizada(s).")


if __name__ == "__main__":
    main()
