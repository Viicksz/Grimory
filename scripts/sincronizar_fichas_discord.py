from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from comandos.ficha import (
    anexos_ficha,
    dividir_embeds_publicacao_personagem,
)
from utils.fichas import FichaPersonagem, PASTA_FICHAS, salvar_ficha
from utils.midia import AnexoLocal
from utils.publicacao_fichas import (
    cabecalho_personagem,
    cabecalho_personagem_parte_2,
    destino_personagem,
)


ARQUIVO_LOG = RAIZ / "exports" / "sincronizacao_fichas_discord.log"
ORDEM_AUTORIDADES = (
    "Minerva McGonagall",
    "Rhysand Velaris",
    "Arthur Carter",
    "Kin Yamazaki",
    "Alessa Belshoff",
    "Madame Brulee",
    "Sr.Grayson",
    "Sr.Windsom",
    "Renee Moretti",
    "Sra.Targellan",
    "Lyz Evans",
    "Rúbeo Hagrid",
    "Gideon Aldrich",
    "Srta. Gabriella Dubois",
    "Dra. Muerstein",
    "Sr.Grumblefoot",
    "Sr.Nyström",
    "Illyana Corvielle",
    "Cassian Vale",
    "Owen Jones",
    "Magnus Whitmore",
)


def registrar(texto: str) -> None:
    ARQUIVO_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ARQUIVO_LOG.open("a", encoding="utf-8") as arquivo:
        arquivo.write(texto + "\n")
    print(texto, flush=True)


def referencias_personagens() -> list[Path]:
    return sorted(
        (
            caminho
            for caminho in PASTA_FICHAS.rglob("*.md")
            if "Criaturas" not in caminho.parts
        ),
        key=lambda caminho: caminho.as_posix().casefold(),
    )


def autoridades_ordenadas() -> list[Path]:
    pasta = PASTA_FICHAS / "Figuras de Autoridade"
    por_nome = {caminho.stem: caminho for caminho in pasta.glob("*.md")}
    ausentes = [nome for nome in ORDEM_AUTORIDADES if nome not in por_nome]
    extras = [nome for nome in por_nome if nome not in ORDEM_AUTORIDADES]
    if ausentes or extras:
        raise RuntimeError(f"Catálogo de autoridades divergente. Ausentes={ausentes}; extras={extras}")
    return [por_nome[nome] for nome in ORDEM_AUTORIDADES]


class DiscordREST:
    def __init__(self, token: str):
        self.token = token
        self.sessao: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "DiscordREST":
        self.sessao = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bot {self.token}",
                "User-Agent": "DiscordBot (Grimory, 1.0)",
            }
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self.sessao is not None:
            await self.sessao.close()

    async def requisitar(
        self,
        metodo: str,
        rota: str,
        *,
        payload: dict[str, object],
        anexos: list[AnexoLocal],
    ) -> tuple[int, dict[str, object]]:
        if self.sessao is None:
            raise RuntimeError("Sessão HTTP não iniciada.")
        url = f"https://discord.com/api/v10{rota}"
        unicos = list({anexo.nome: anexo for anexo in anexos}.values())
        payload = dict(payload)
        payload["attachments"] = [
            {"id": indice, "filename": anexo.nome}
            for indice, anexo in enumerate(unicos)
        ]
        while True:
            formularios = aiohttp.FormData()
            formularios.add_field("payload_json", json.dumps(payload, ensure_ascii=False))
            arquivos = []
            try:
                for indice, anexo in enumerate(unicos):
                    arquivo = anexo.caminho.open("rb")
                    arquivos.append(arquivo)
                    formularios.add_field(
                        f"files[{indice}]",
                        arquivo,
                        filename=anexo.nome,
                        content_type="application/octet-stream",
                    )
                async with self.sessao.request(metodo, url, data=formularios) as resposta:
                    dados = await resposta.json(content_type=None)
                    if resposta.status == 429:
                        await asyncio.sleep(float(dados.get("retry_after", 1)))
                        continue
                    return resposta.status, dados
            finally:
                for arquivo in arquivos:
                    arquivo.close()

    async def publicar_ou_editar(
        self,
        ficha: FichaPersonagem,
        mensagem_id: int,
        *,
        parte: int = 1,
    ) -> tuple[int, str, bool]:
        destino = destino_personagem(ficha.grupo)
        principal, parte_2, parte_3 = dividir_embeds_publicacao_personagem(ficha)
        embeds = (principal, parte_2, parte_3)[parte - 1]
        payload: dict[str, object] = {
            "content": "" if parte > 1 else cabecalho_personagem(ficha.nome, ficha.grupo),
            "embeds": [embed.to_dict() for embed in embeds],
            "allowed_mentions": {"parse": []},
        }
        anexos = [] if parte > 1 else anexos_ficha(ficha)
        if mensagem_id:
            status, dados = await self.requisitar(
                "PATCH",
                f"/channels/{destino}/messages/{mensagem_id}",
                payload=payload,
                anexos=anexos,
            )
            if status not in {404} and not 200 <= status < 300:
                raise RuntimeError(f"Discord recusou a edição de {ficha.nome}: {status} {dados}")
            if 200 <= status < 300:
                return int(dados["id"]), str(dados.get("guild_id", "")), False
        status, dados = await self.requisitar(
            "POST",
            f"/channels/{destino}/messages",
            payload=payload,
            anexos=anexos,
        )
        if not 200 <= status < 300:
            raise RuntimeError(f"Discord recusou a publicação de {ficha.nome}: {status} {dados}")
        return int(dados["id"]), str(dados.get("guild_id", "")), True

    async def excluir(self, destino: int, mensagem_id: int) -> None:
        if self.sessao is None or not mensagem_id:
            return
        url = f"https://discord.com/api/v10/channels/{destino}/messages/{mensagem_id}"
        while True:
            async with self.sessao.delete(url) as resposta:
                if resposta.status == 429:
                    dados = await resposta.json(content_type=None)
                    await asyncio.sleep(float(dados.get("retry_after", 1)))
                    continue
                if resposta.status in {204, 404}:
                    return
                texto = await resposta.text()
                raise RuntimeError(
                    f"Discord recusou a remoção de uma parte excedente: {resposta.status} {texto}"
                )


async def executar(intervalo_minutos: int, republicar_autoridades: bool = False) -> None:
    load_dotenv(RAIZ / ".env", encoding="utf-8-sig")
    token = os.getenv("GRIMORY_DISCORD_TOKEN") or os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Token do Grimory não encontrado.")
    ARQUIVO_LOG.write_text("", encoding="utf-8")
    async with DiscordREST(token) as discord:
        async def sincronizar_caminho(
            caminho: Path,
        ) -> tuple[FichaPersonagem, int, str, bool]:
            ficha = FichaPersonagem.carregar(caminho)
            _, parte_2, parte_3 = dividir_embeds_publicacao_personagem(ficha)
            quantidade_necessaria = 1 + int(bool(parte_2)) + int(bool(parte_3))
            quantidade_registrada = (
                1
                + int(bool(ficha.mensagem_discord_parte_2_id))
                + int(bool(ficha.mensagem_discord_parte_3_id))
                if ficha.mensagem_discord_id
                else 0
            )
            # Quando a ficha passa de uma para duas mensagens (ou de duas para
            # três), editar a principal e publicar apenas a nova parte deixaria
            # as duas metades afastadas na thread. Recriamos exclusivamente a
            # publicação dessa ficha para manter o conjunto contíguo.
            if ficha.mensagem_discord_id and quantidade_necessaria != quantidade_registrada:
                for mensagem_antiga in (
                    ficha.mensagem_discord_id,
                    ficha.mensagem_discord_parte_2_id,
                    ficha.mensagem_discord_parte_3_id,
                ):
                    if mensagem_antiga:
                        await discord.excluir(destino_personagem(ficha.grupo), mensagem_antiga)
                ficha.mensagem_discord_id = 0
                ficha.mensagem_discord_parte_2_id = 0
                ficha.mensagem_discord_parte_3_id = 0
            mensagem_id, guild_id, criada = await discord.publicar_ou_editar(
                ficha, ficha.mensagem_discord_id
            )
            parte_2_id = 0
            if parte_2:
                parte_2_id, _, _ = await discord.publicar_ou_editar(
                    ficha,
                    ficha.mensagem_discord_parte_2_id,
                    parte=2,
                )
            elif ficha.mensagem_discord_parte_2_id:
                await discord.excluir(
                    destino_personagem(ficha.grupo),
                    ficha.mensagem_discord_parte_2_id,
                )
            parte_3_id = 0
            if parte_3:
                parte_3_id, _, _ = await discord.publicar_ou_editar(
                    ficha,
                    ficha.mensagem_discord_parte_3_id,
                    parte=3,
                )
            elif ficha.mensagem_discord_parte_3_id:
                await discord.excluir(
                    destino_personagem(ficha.grupo),
                    ficha.mensagem_discord_parte_3_id,
                )
            atual = FichaPersonagem.carregar(caminho)
            atual.mensagem_discord_id = mensagem_id
            atual.mensagem_discord_parte_2_id = parte_2_id
            atual.mensagem_discord_parte_3_id = parte_3_id
            salvar_ficha(atual, caminho)
            return ficha, mensagem_id, guild_id, criada

        atualizadas = 0
        if not republicar_autoridades:
            for caminho in referencias_personagens():
                ficha = FichaPersonagem.carregar(caminho)
                if ficha.grupo == "Figuras de Autoridade" or not ficha.mensagem_discord_id:
                    continue
                ficha, mensagem_id, guild_id, criada = await sincronizar_caminho(caminho)
                if criada:
                    raise RuntimeError(f"A mensagem existente de {ficha.nome} desapareceu; operação interrompida.")
                registrar(
                    f"ATUALIZADA | {ficha.nome} | https://discord.com/channels/{guild_id}/{destino_personagem(ficha.grupo)}/{mensagem_id}"
                )
                atualizadas += 1

        autoridades = autoridades_ordenadas()
        for indice, caminho in enumerate(autoridades):
            if republicar_autoridades:
                anterior = FichaPersonagem.carregar(caminho)
                for mensagem_antiga in (
                    anterior.mensagem_discord_id,
                    anterior.mensagem_discord_parte_2_id,
                    anterior.mensagem_discord_parte_3_id,
                ):
                    if mensagem_antiga:
                        await discord.excluir(
                            destino_personagem(anterior.grupo), mensagem_antiga
                        )
                anterior.mensagem_discord_id = 0
                anterior.mensagem_discord_parte_2_id = 0
                anterior.mensagem_discord_parte_3_id = 0
                salvar_ficha(anterior, caminho)
            ficha, mensagem_id, guild_id, criada = await sincronizar_caminho(caminho)
            acao = "PUBLICADA" if criada else "ATUALIZADA"
            registrar(
                f"{acao} | {ficha.nome} | https://discord.com/channels/{guild_id}/{destino_personagem(ficha.grupo)}/{mensagem_id}"
            )
            ainda_ha_novas = any(
                not FichaPersonagem.carregar(restante).mensagem_discord_id
                for restante in autoridades[indice + 1 :]
            )
            if ainda_ha_novas:
                registrar(f"AGUARDANDO | {intervalo_minutos} minutos antes da próxima autoridade")
                await asyncio.sleep(intervalo_minutos * 60)
        registrar(f"CONCLUÍDA | {atualizadas} existentes atualizadas | {len(autoridades)} autoridades sincronizadas")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intervalo-minutos", type=int, default=10)
    parser.add_argument(
        "--republicar-autoridades",
        action="store_true",
        help="Recria em sequência apenas as publicações registradas das autoridades.",
    )
    argumentos = parser.parse_args()
    asyncio.run(
        executar(
            max(1, argumentos.intervalo_minutos),
            republicar_autoridades=argumentos.republicar_autoridades,
        )
    )


if __name__ == "__main__":
    main()
