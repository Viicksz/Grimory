from __future__ import annotations

import asyncio
import os

import discord
from dotenv import load_dotenv

from comandos.ficha import publicar_personagem_em_partes
from comandos.ficha_criaturas import montar_embeds_criatura
from utils.fichas import FichaPersonagem, listar_fichas, salvar_ficha
from utils.fichas_criaturas import FichaCriatura, listar_fichas_criaturas, salvar_ficha_criatura
from utils.publicacao_fichas import (
    cabecalho_criatura,
    destino_criatura,
    publicar_ou_atualizar_ficha,
)


async def publicar_todas() -> None:
    load_dotenv(encoding="utf-8-sig")
    token = os.getenv("GRIMORY_DISCORD_TOKEN") or os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Token do Grimory não encontrado.")

    cliente = discord.Client(intents=discord.Intents.default())
    executado = False

    @cliente.event
    async def on_ready() -> None:
        nonlocal executado
        if executado:
            return
        executado = True
        try:
            for referencia in listar_fichas():
                ficha = FichaPersonagem.carregar(referencia.caminho)
                mensagem, mensagem_parte_2, mensagem_parte_3 = (
                    await publicar_personagem_em_partes(cliente, ficha)
                )
                ficha.mensagem_discord_id = mensagem.id
                ficha.mensagem_discord_parte_2_id = (
                    mensagem_parte_2.id if mensagem_parte_2 else 0
                )
                ficha.mensagem_discord_parte_3_id = (
                    mensagem_parte_3.id if mensagem_parte_3 else 0
                )
                salvar_ficha(ficha, referencia.caminho)
                print(f"PUBLICADA | {ficha.nome} | {mensagem.jump_url}")

            for referencia in listar_fichas_criaturas():
                ficha = FichaCriatura.carregar(referencia.caminho)
                mensagem = await publicar_ou_atualizar_ficha(
                    cliente,
                    destino_criatura(),
                    montar_embeds_criatura(ficha),
                    ficha.mensagem_discord_id,
                    cabecalho_criatura(ficha.nome, ficha.periculosidade),
                )
                ficha.mensagem_discord_id = mensagem.id
                salvar_ficha_criatura(ficha, referencia.caminho)
                print(f"PUBLICADA | {ficha.nome} | {mensagem.jump_url}")
        finally:
            await cliente.close()

    await cliente.start(token)


if __name__ == "__main__":
    asyncio.run(publicar_todas())
