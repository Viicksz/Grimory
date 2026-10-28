import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from comandos.adicionar import Adicionar
from comandos.ajuda import Ajuda
from comandos.combate import CombateCog
from comandos.dados import Dados
from comandos.executar import Executar
from comandos.editar import Editar
from comandos.ficha import Ficha
from comandos.gringots import Gringots
from comandos.habilidades import Habilidades
from comandos.interagir import Interagir
from comandos.inventario import Inventario
from comandos.movimentacoes_taca import MovimentacoesTaca
from comandos.narrativa import Narrativa
from comandos.passagem_ano import PassagemAno
from comandos.preparar import Preparar
from comandos.quadribol import Quadribol
from comandos.remover import Remover
from comandos.revisar_feiticos import RevisarFeiticos
from comandos.taca import TacaDasCasas
from comandos.xp import XP


load_dotenv(encoding="utf-8-sig")
load_dotenv(".env.quadribol", encoding="utf-8-sig")

TOKEN = os.getenv("GRIMORY_DISCORD_TOKEN") or os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


_COMANDOS_SINCRONIZADOS = False


@bot.event
async def on_ready():
    global _COMANDOS_SINCRONIZADOS
    if not _COMANDOS_SINCRONIZADOS:
        await bot.tree.sync()
        _COMANDOS_SINCRONIZADOS = True
    print(f"{bot.user} esta online. Pasta: {os.getcwd()}")


async def main():
    if not TOKEN:
        raise RuntimeError(
            "GRIMORY_DISCORD_TOKEN ou DISCORD_TOKEN nao foi encontrado no arquivo .env."
        )

    async with bot:
        await bot.add_cog(Adicionar(bot))
        await bot.add_cog(Ajuda(bot))
        await bot.add_cog(CombateCog(bot))
        await bot.add_cog(Dados(bot))
        await bot.add_cog(Executar(bot))
        await bot.add_cog(Editar(bot))
        await bot.add_cog(Ficha(bot))
        await bot.add_cog(Gringots(bot))
        await bot.add_cog(Habilidades(bot))
        await bot.add_cog(Interagir(bot))
        await bot.add_cog(Inventario(bot))
        await bot.add_cog(MovimentacoesTaca(bot))
        await bot.add_cog(Narrativa(bot))
        await bot.add_cog(PassagemAno(bot))
        await bot.add_cog(Preparar(bot))
        await bot.add_cog(Quadribol(bot))
        await bot.add_cog(Remover(bot))
        await bot.add_cog(RevisarFeiticos(bot))
        await bot.add_cog(TacaDasCasas(bot))
        await bot.add_cog(XP(bot))
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
