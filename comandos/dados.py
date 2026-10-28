import random
import re

import discord
from discord import app_commands
from discord.ext import commands


PADRAO_DADO = re.compile(r"^\s*(?:(\d+)\s*)?d\s*(\d+)\s*$", re.IGNORECASE)
PADRAO_NUMERO = re.compile(r"^\s*\d+\s*$")
PADRAO_REPETICAO = re.compile(r"^\s*(\d+)\s*#\s*(.+?)\s*$")
MAXIMO_DADOS = 100
MAXIMO_LADOS = 100000
MAXIMO_REPETICOES = 20
COR_EMBED_DADOS = 16777215


def montar_baralho_d20() -> list[int]:
    resultados = [
        1,
        20,
        *[random.randint(2, 9) for _ in range(5)],
        *[random.randint(10, 19) for _ in range(8)],
    ]
    random.shuffle(resultados)
    return resultados


def rolar_d20_balanceado() -> int:
    return montar_baralho_d20().pop()


def interpretar_expressao(expressao: str) -> tuple[int, int] | None:
    resultado = PADRAO_DADO.match(expressao)

    if resultado is None:
        return None

    quantidade_texto, lados_texto = resultado.groups()
    quantidade = int(quantidade_texto or 1)
    lados = int(lados_texto)

    if quantidade < 1 or lados < 1:
        return None

    return quantidade, lados


def resumir_resultados(resultados: list[int]) -> str:
    texto = ", ".join(str(resultado) for resultado in resultados)

    if len(texto) <= 900:
        return texto

    return f"{texto[:897]}..."


def rolar_dado_comum(quantidade: int, lados: int) -> list[int]:
    return [random.randint(1, lados) for _ in range(quantidade)]


def formatar_expressao_dado(quantidade: int, lados: int) -> str:
    if quantidade == 1:
        return f"1d{lados}"

    return f"{quantidade}d{lados}"


def formatar_termo_dado(quantidade: int, lados: int, resultados: list[int]) -> str:
    expressao = formatar_expressao_dado(quantidade, lados)

    if quantidade == 1:
        return f"[{resultados[0]}] {expressao}"

    return f"[{resumir_resultados(resultados)}] {expressao}"


def formatar_resultado(total: int, detalhe: str) -> str:
    return f"`{total}` ⇐ {detalhe}"


def rolar_expressao_comum(expressao: str) -> tuple[int, str] | None:
    termos = expressao.split("+")

    if any(not termo.strip() for termo in termos):
        return None

    total = 0
    partes: list[str] = []

    for termo in termos:
        dado = interpretar_expressao(termo)

        if dado is not None:
            quantidade, lados = dado

            if quantidade > MAXIMO_DADOS or lados > MAXIMO_LADOS:
                return None

            resultados = rolar_dado_comum(quantidade, lados)
            total += sum(resultados)
            partes.append(formatar_termo_dado(quantidade, lados, resultados))
            continue

        if PADRAO_NUMERO.match(termo):
            numero = int(termo.strip())
            total += numero
            partes.append(str(numero))
            continue

        return None

    return total, formatar_resultado(total, " + ".join(partes))


def rolar_repeticao(expressao: str) -> tuple[int, str, list[str]] | None:
    repeticao = PADRAO_REPETICAO.match(expressao)

    if repeticao is None:
        return None

    quantidade_texto, expressao_repetida = repeticao.groups()
    quantidade = int(quantidade_texto)

    if quantidade < 1 or quantidade > MAXIMO_REPETICOES:
        return None

    resultados: list[str] = []

    for _ in range(quantidade):
        rolagem = rolar_expressao_comum(expressao_repetida)

        if rolagem is None:
            return None

        _, detalhe = rolagem
        resultados.append(detalhe)

    return quantidade, expressao_repetida.strip(), resultados


class Dados(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rolar", description="Rolagem de dados.")
    @app_commands.describe(dado="Formato da rolagem. Exemplos: d20, 1d4+1, 2#d20+5")
    async def rolar(self, interaction: discord.Interaction, dado: str):
        repeticao = rolar_repeticao(dado)

        if repeticao is not None:
            _, _, resultados_repetidos = repeticao
            titulo = dado.strip()
            descricao = "\n".join(resultados_repetidos)
            embed = discord.Embed(title=titulo, description=descricao, color=COR_EMBED_DADOS)
            embed.set_footer(text="Rolagem comum")

            await interaction.response.send_message(embed=embed)
            return

        expressao = interpretar_expressao(dado)

        if expressao is None:
            rolagem_comum = rolar_expressao_comum(dado)

            if rolagem_comum is None:
                await interaction.response.send_message(
                    "Use formatos como `d20`, `1d4+1`, `d20+d6+5`, `6d20+35` ou `2#d20+5`.",
                    ephemeral=True,
                )
                return

            _, detalhe = rolagem_comum
            titulo = dado.strip()
            descricao = detalhe
            embed = discord.Embed(title=titulo, description=descricao, color=COR_EMBED_DADOS)
            embed.set_footer(text="Rolagem comum")

            await interaction.response.send_message(embed=embed)
            return

        quantidade, lados = expressao

        if quantidade > MAXIMO_DADOS:
            await interaction.response.send_message(
                f"Posso rolar no maximo {MAXIMO_DADOS} dados por vez.",
                ephemeral=True,
            )
            return

        if lados > MAXIMO_LADOS:
            await interaction.response.send_message(
                f"Posso rolar dados de ate {MAXIMO_LADOS} lados.",
                ephemeral=True,
            )
            return

        if quantidade == 1 and lados == 20:
            resultados = [rolar_d20_balanceado()]
            observacao = "d20 Balanceado"
        else:
            resultados = rolar_dado_comum(quantidade, lados)
            observacao = "Rolagem comum"

        titulo = f"{quantidade}d{lados}"
        total = sum(resultados)
        detalhe = formatar_termo_dado(quantidade, lados, resultados)
        descricao = formatar_resultado(total, detalhe)

        embed = discord.Embed(title=titulo, description=descricao, color=COR_EMBED_DADOS)
        embed.set_footer(text=observacao)

        await interaction.response.send_message(embed=embed)
