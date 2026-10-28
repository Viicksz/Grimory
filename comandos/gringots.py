from __future__ import annotations

import asyncio
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from comandos.ficha import embed_painel, sincronizar_publicacao_personagem
from comandos.inventario import referencias_permitidas
from utils.biblioteca import normalizar_rotulo
from utils.fichas import (
    EMOJIS_PASTAS_FICHA,
    GRUPOS_FICHA,
    FichaPersonagem,
    listar_fichas,
    paginas_fichas_alfabeticas,
    salvar_ficha,
)
from utils.inventario import MOEDAS, inteiro_positivo, somar_item


OPERACOES = ("Crédito", "Débito")
DESCRICOES_OPERACOES = {
    "Crédito": "Adiciona dinheiro ao inventário da ficha.",
    "Débito": "Retira dinheiro do inventário da ficha.",
}


class ViewGringots(discord.ui.View):
    def __init__(self, usuario_id: int, *, timeout: float = 900):
        super().__init__(timeout=timeout)
        self.usuario_id = usuario_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message(
            "Somente quem abriu este painel pode usar os controles.", ephemeral=True
        )
        return False


class OperacaoGringotsView(ViewGringots):
    def __init__(self, usuario_id: int, administrador: bool):
        super().__init__(usuario_id)
        self.administrador = administrador
        seletor = discord.ui.Select(
            placeholder="Operação monetária",
            options=[
                discord.SelectOption(
                    label=operacao,
                    value=operacao,
                    description=DESCRICOES_OPERACOES[operacao],
                    emoji="➕" if operacao == "Crédito" else "➖",
                )
                for operacao in OPERACOES
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        operacao = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🏦 Gringotts — {operacao}",
                "Escolha a pasta da ficha que terá o saldo movimentado.",
            ),
            view=PastaGringotsView(
                self.usuario_id, self.administrador, operacao
            ),
        )


class PastaGringotsView(ViewGringots):
    def __init__(self, usuario_id: int, administrador: bool, operacao: str):
        super().__init__(usuario_id)
        self.administrador = administrador
        self.operacao = operacao
        referencias = referencias_permitidas(usuario_id, administrador)
        contagens = {
            grupo: sum(referencia.grupo == grupo for referencia in referencias)
            for grupo in GRUPOS_FICHA
        }
        seletor = discord.ui.Select(
            placeholder="Pasta da ficha",
            options=[
                discord.SelectOption(
                    label=grupo,
                    value=grupo,
                    emoji=EMOJIS_PASTAS_FICHA[grupo],
                    description=(
                        f"{contagens[grupo]} ficha(s) disponível(is)."
                        if contagens[grupo]
                        else "Nenhuma ficha disponível nesta pasta."
                    ),
                )
                for grupo in GRUPOS_FICHA
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        grupo = self.seletor.values[0]
        referencias = [
            referencia
            for referencia in referencias_permitidas(self.usuario_id, self.administrador)
            if referencia.grupo == grupo
        ]
        paginas = paginas_fichas_alfabeticas(referencias)
        pagina = next((indice for indice, (_, itens) in enumerate(paginas) if itens), 0)
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🏦 Gringotts — {self.operacao}",
                f"{EMOJIS_PASTAS_FICHA[grupo]} {grupo}: escolha a faixa alfabética e depois a ficha.",
            ),
            view=FichaGringotsView(
                self.usuario_id, self.administrador, self.operacao, grupo, pagina
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel("🏦 Gringotts", "Escolha a operação monetária."),
            view=OperacaoGringotsView(self.usuario_id, self.administrador),
        )


class FichaGringotsView(ViewGringots):
    def __init__(
        self,
        usuario_id: int,
        administrador: bool,
        operacao: str,
        grupo: str,
        pagina: int,
    ):
        super().__init__(usuario_id)
        self.administrador = administrador
        self.operacao = operacao
        self.grupo = grupo
        referencias = [
            referencia
            for referencia in referencias_permitidas(usuario_id, administrador)
            if referencia.grupo == grupo
        ]
        self.paginas = paginas_fichas_alfabeticas(referencias)
        if not self.paginas:
            self.paginas = [("--", [])]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        faixa, self.referencias = self.paginas[self.pagina]
        faixas = discord.ui.Select(
            placeholder=f"Faixa alfabética — {faixa}",
            options=[
                discord.SelectOption(
                    label=nome,
                    value=str(indice),
                    description=(f"{len(itens)} ficha(s)." if itens else "Faixa reservada."),
                    default=indice == self.pagina,
                )
                for indice, (nome, itens) in enumerate(self.paginas)
            ],
            row=0,
        )
        faixas.callback = self.selecionar_faixa
        self.faixas = faixas
        self.add_item(faixas)
        if self.referencias:
            fichas = discord.ui.Select(
                placeholder=f"Fichas — {faixa}",
                options=[
                    discord.SelectOption(label=referencia.nome[:100], value=str(indice))
                    for indice, referencia in enumerate(self.referencias)
                ],
                row=1,
            )
            fichas.callback = self.selecionar_ficha
            self.fichas = fichas
            self.add_item(fichas)
        voltar = discord.ui.Button(label="Voltar às pastas", style=discord.ButtonStyle.secondary, row=2)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar_faixa(self, interaction: discord.Interaction) -> None:
        pagina = int(self.faixas.values[0])
        await interaction.response.edit_message(
            view=FichaGringotsView(
                self.usuario_id, self.administrador, self.operacao, self.grupo, pagina
            )
        )

    async def selecionar_ficha(self, interaction: discord.Interaction) -> None:
        referencia = self.referencias[int(self.fichas.values[0])]
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🏦 Gringotts — {self.operacao}",
                "Escolha a moeda que será movimentada.",
            ),
            view=MoedaGringotsView(
                self.usuario_id, self.administrador, self.operacao, referencia.caminho
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🏦 Gringotts — {self.operacao}",
                "Escolha a pasta da ficha que terá o saldo movimentado.",
            ),
            view=PastaGringotsView(self.usuario_id, self.administrador, self.operacao),
        )


class MoedaGringotsView(ViewGringots):
    def __init__(self, usuario_id: int, administrador: bool, operacao: str, caminho: Path):
        super().__init__(usuario_id)
        self.administrador = administrador
        self.operacao = operacao
        self.caminho = caminho
        seletor = discord.ui.Select(
            placeholder="Moeda",
            options=[
                discord.SelectOption(
                    label=moeda,
                    value=moeda,
                    description="Escolha a unidade monetária do saldo.",
                    emoji="💰",
                )
                for moeda in MOEDAS
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        moeda = self.seletor.values[0]
        await interaction.response.send_modal(
            QuantidadeGringotsModal(self.usuario_id, self.operacao, self.caminho, moeda)
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        referencia = next((r for r in listar_fichas() if r.caminho == self.caminho), None)
        grupo = referencia.grupo if referencia else "Players"
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🏦 Gringotts — {self.operacao}",
                "Escolha a faixa alfabética e depois a ficha.",
            ),
            view=FichaGringotsView(self.usuario_id, self.administrador, self.operacao, grupo, 0),
        )


class QuantidadeGringotsModal(discord.ui.Modal):
    def __init__(self, usuario_id: int, operacao: str, caminho: Path, moeda: str):
        super().__init__(title=f"{operacao} — {moeda}")
        self.usuario_id = usuario_id
        self.operacao = operacao
        self.caminho = caminho
        self.moeda = moeda
        self.quantidade = discord.ui.TextInput(
            label="Quantidade",
            placeholder="Informe um número inteiro positivo",
            min_length=1,
            max_length=9,
        )
        self.add_item(self.quantidade)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            quantidade = int(str(self.quantidade.value).strip())
            if quantidade <= 0:
                raise ValueError
            ficha = FichaPersonagem.carregar(self.caminho)
            anterior = saldo_moeda(ficha, self.moeda)
            delta = quantidade if self.operacao == "Crédito" else -quantidade
            if anterior + delta < 0:
                raise ValueError(f"Saldo insuficiente: a ficha possui {anterior} {self.moeda}.")
            ajustar_moeda(ficha, self.moeda, delta)
            salvar_ficha(ficha, self.caminho)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(f"Não foi possível movimentar o saldo: {erro}", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=embed_movimentacao(self.operacao, ficha, self.moeda, quantidade, anterior, saldo_moeda(ficha, self.moeda), interaction.user),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)


def saldo_moeda(ficha: FichaPersonagem, moeda: str) -> int:
    if normalizar_rotulo(moeda).startswith("gale"):
        return ficha.galeoes
    return sum(
        inteiro_positivo(item.get("quantidade", "0"), 0)
        for item in ficha.itens
        if normalizar_rotulo(item.get("categoria", "")) == normalizar_rotulo("Dinheiro")
        and normalizar_rotulo(item.get("tipo") or item.get("nome", "")) == normalizar_rotulo(moeda)
    )


def ajustar_moeda(ficha: FichaPersonagem, moeda: str, delta: int) -> None:
    if normalizar_rotulo(moeda).startswith("gale"):
        ficha.galeoes += delta
        return
    if delta > 0:
        somar_item(
            ficha,
            {"categoria": "Dinheiro", "nome": moeda, "tipo": moeda, "quantidade": str(delta)},
        )
        return
    restante = -delta
    for item in list(ficha.itens):
        if (
            normalizar_rotulo(item.get("categoria", "")) == normalizar_rotulo("Dinheiro")
            and normalizar_rotulo(item.get("tipo") or item.get("nome", "")) == normalizar_rotulo(moeda)
        ):
            disponivel = inteiro_positivo(item.get("quantidade", "0"), 0)
            consumir = min(disponivel, restante)
            restante -= consumir
            if consumir == disponivel:
                ficha.itens.remove(item)
            else:
                item["quantidade"] = str(disponivel - consumir)
            if restante == 0:
                return
    raise ValueError(f"Saldo insuficiente: a ficha não possui {moeda} suficiente.")


def embed_movimentacao(operacao, ficha, moeda, quantidade, anterior, novo, autor):
    delta = quantidade if operacao == "Crédito" else -quantidade
    embed = discord.Embed(
        title=f"🏦 {operacao} monetário",
        description=f"## {'+' if delta > 0 else '−'}{quantidade} {moeda}",
        color=discord.Color.green() if delta > 0 else discord.Color.red(),
    )
    embed.add_field(name="Ficha", value=ficha.nome, inline=True)
    embed.add_field(name="Saldo anterior", value=f"{anterior} {moeda}", inline=True)
    embed.add_field(name="Novo saldo", value=f"{novo} {moeda}", inline=True)
    embed.set_footer(text=f"Movimentação realizada por {autor.display_name}")
    return embed


class Gringots(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="gringots", description="Movimenta o dinheiro guardado no inventário das fichas.")
    async def gringots(self, interaction: discord.Interaction) -> None:
        administrador = bool(interaction.permissions.manage_guild)
        await interaction.response.send_message(
            embed=embed_painel("🏦 Gringotts", "Escolha a operação monetária."),
            view=OperacaoGringotsView(interaction.user.id, administrador),
            ephemeral=True,
        )
