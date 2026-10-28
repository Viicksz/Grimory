from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from comandos.dados import rolar_d20_balanceado
from comandos.executar import carregar_todos_feiticos, campos_normalizados
from comandos.habilidades import listar_habilidades
from utils.biblioteca import normalizar_rotulo
from utils.efeitos_habilidades import aptidao_efetiva, heranca_desbloqueada
from utils.fichas import (
    ATRIBUTOS,
    GRUPOS_ALFABETICOS_FICHAS,
    GRUPOS_FICHA,
    EMOJIS_PASTAS_FICHA,
    FichaPersonagem,
    encontrar_ficha,
    listar_fichas,
    salvar_ficha,
)
from utils.xp import (
    ContaXP,
    caminho_nova_conta_xp,
    encontrar_conta_do_titular,
    encontrar_conta_xp,
    listar_contas_xp,
    salvar_conta_xp,
)


CATEGORIAS_XP = {
    "heranca": ("Herança Sanguínea", None, None),
    "aula_treino": ("Aula ou Treino", 2, None),
    "side_quest": ("Side-Quest", None, 20),
    "arco_campanha": ("Arco de Campanha", None, 100),
    "credito": ("Crédito", None, 1),
    "debito": ("Débito", None, 1),
}

CATEGORIAS_LIVRES = {"heranca", "aula_treino"}
TEMPO_FLUXO_XP = 20 * 60
PASSOS_CD = (30, 25, 20, 18, 16, 14, 12, 10, 8, 6)


def custo_catalisador(grau: str) -> int:
    grau_normalizado = normalizar_rotulo(grau)
    if grau_normalizado.startswith("intermediario"):
        return 5
    if grau_normalizado.startswith("avancado"):
        return 10
    raise ValueError(
        "O catalisador reduz somente feitiços Intermediários ou Avançados; "
        "feitiços Básicos já estão no menor nível de dificuldade."
    )


def reduzir_cd_em_um_nivel(cd: int) -> int:
    for passo in PASSOS_CD:
        if passo < cd:
            return passo
    return PASSOS_CD[-1]


def ano_referencia_feitico(ficha: FichaPersonagem, campos: dict[str, str]) -> tuple[str, bool]:
    ano_ficha = ficha.ano.strip()
    if re.fullmatch(r"[1-7]\s*[º°o]?\s*Ano", ano_ficha, re.IGNORECASE):
        numero = re.search(r"[1-7]", ano_ficha).group(0)
        return f"{numero}º Ano", False
    desbloqueio = campos.get("ano de desbloqueio", "").strip()
    numero = re.search(r"[1-7]", desbloqueio)
    if numero:
        return f"{numero.group(0)}º Ano", True
    return "+18y", True


def cd_feitico_por_ano(campos: dict[str, str], ano: str) -> int:
    dificuldade = campos.get("dificuldade por ano", "")
    padrao = re.compile(
        rf"^{re.escape(ano)}\s*:\s*(\d+)\+?\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    resultado = padrao.search(dificuldade)
    if resultado is None:
        raise ValueError(f"O feitiço não possui dificuldade registrada para {ano}.")
    return int(resultado.group(1))


@dataclass(frozen=True)
class DestinoXP:
    tipo: str
    nome: str
    caminho: Path


def validar_valor_variavel(categoria: str, texto: str) -> int:
    if not re.fullmatch(r"[0-9]+", texto.strip()):
        raise ValueError("Informe somente o valor em números, sem símbolos.")
    valor = int(texto.strip())
    minimo = CATEGORIAS_XP[categoria][2]
    if minimo is not None and valor < minimo:
        if categoria == "side_quest":
            raise ValueError("Uma Side-Quest concede no mínimo 20 XP.")
        if categoria == "arco_campanha":
            raise ValueError("Um Arco de Campanha concede no mínimo 100 XP.")
        raise ValueError("O valor precisa ser maior que zero.")
    return valor


def resolver_destino(valor: str) -> DestinoXP | None:
    if valor.startswith("ficha:"):
        referencia = encontrar_ficha(valor.removeprefix("ficha:"))
        if referencia:
            return DestinoXP("Ficha", referencia.nome, referencia.caminho)
        return None
    if valor.startswith("conta:"):
        referencia = encontrar_conta_xp(valor.removeprefix("conta:"))
        if referencia:
            return DestinoXP("Banco de XP", referencia.nome, referencia.caminho)
        return None
    referencia_ficha = encontrar_ficha(valor)
    if referencia_ficha:
        return DestinoXP("Ficha", referencia_ficha.nome, referencia_ficha.caminho)
    referencia_conta = encontrar_conta_xp(valor)
    if referencia_conta:
        return DestinoXP("Banco de XP", referencia_conta.nome, referencia_conta.caminho)
    return None


def destino_pertence_ao_usuario(destino: DestinoXP, usuario_id: int) -> bool:
    try:
        if destino.tipo == "Ficha":
            return FichaPersonagem.carregar(destino.caminho).titular_id == usuario_id
        return ContaXP.carregar(destino.caminho).titular_id == usuario_id
    except (OSError, ValueError):
        return False


def opcoes_destino(
    termo: str,
    *,
    usuario_id: int | None = None,
) -> list[app_commands.Choice[str]]:
    termo_normalizado = normalizar_rotulo(termo)
    opcoes: list[app_commands.Choice[str]] = []
    for referencia in listar_fichas():
        if usuario_id is not None:
            destino = DestinoXP("Ficha", referencia.nome, referencia.caminho)
            if not destino_pertence_ao_usuario(destino, usuario_id):
                continue
        rotulo = f"{referencia.nome} • Ficha ({referencia.grupo})"
        if termo_normalizado and termo_normalizado not in normalizar_rotulo(rotulo):
            continue
        relativo = referencia.caminho.relative_to(referencia.caminho.parents[1]).as_posix()
        valor = f"ficha:{relativo}"
        if len(valor) <= 100:
            opcoes.append(app_commands.Choice(name=rotulo[:100], value=valor))
    for referencia in listar_contas_xp():
        if usuario_id is not None and referencia.titular_id != usuario_id:
            continue
        rotulo = f"{referencia.nome} • Banco de XP"
        if termo_normalizado and termo_normalizado not in normalizar_rotulo(rotulo):
            continue
        valor = f"conta:{referencia.nome}"
        if len(valor) <= 100:
            opcoes.append(app_commands.Choice(name=rotulo[:100], value=valor))
    return opcoes[:25]


def listar_destinos_xp(
    tipo: str,
    *,
    usuario_id: int | None = None,
    grupo_ficha: str = "",
) -> list[DestinoXP]:
    destinos: list[DestinoXP] = []
    if tipo == "fichas":
        for referencia in listar_fichas():
            if grupo_ficha and referencia.grupo != grupo_ficha:
                continue
            destino = DestinoXP("Ficha", referencia.nome, referencia.caminho)
            if usuario_id is None or destino_pertence_ao_usuario(destino, usuario_id):
                destinos.append(destino)
    elif tipo == "contas":
        for referencia in listar_contas_xp():
            if usuario_id is None or referencia.titular_id == usuario_id:
                destinos.append(
                    DestinoXP("Banco de XP", referencia.nome, referencia.caminho)
                )
    else:
        raise ValueError("Opção de destino inválida.")
    return sorted(destinos, key=lambda destino: destino.nome.casefold())


def paginas_destinos_xp(
    destinos: list[DestinoXP],
) -> list[tuple[str, list[DestinoXP]]]:
    paginas: list[tuple[str, list[DestinoXP]]] = []
    for grupo in GRUPOS_ALFABETICOS_FICHAS:
        agrupados = [
            destino
            for destino in destinos
            if (normalizar_rotulo(destino.nome)[:1].upper() or "#") in grupo
        ]
        lotes = [
            agrupados[indice:indice + 25]
            for indice in range(0, len(agrupados), 25)
        ] or [[]]
        for indice, lote in enumerate(lotes):
            rotulo = grupo if len(lotes) == 1 else f"{grupo} — {indice + 1}/{len(lotes)}"
            paginas.append((rotulo, lote))
    return paginas


def titulo_categoria_xp(categoria: str) -> str:
    return CATEGORIAS_XP[categoria][0]


class ValorXPModal(discord.ui.Modal):
    def __init__(self, cog: XP, categoria: str, destino: DestinoXP):
        titulo_categoria = CATEGORIAS_XP[categoria][0]
        super().__init__(title=f"XP — {titulo_categoria}")
        self.cog = cog
        self.categoria = categoria
        self.destino = destino
        minimo = CATEGORIAS_XP[categoria][2]
        self.valor = discord.ui.TextInput(
            label="Valor",
            placeholder=f"Mínimo: {minimo}" if minimo and minimo > 1 else "Digite somente o número",
            max_length=10,
        )
        self.add_item(self.valor)
        self.descricao: discord.ui.TextInput | None = None
        if categoria in {"credito", "debito"}:
            self.descricao = discord.ui.TextInput(
                label="Descrição",
                placeholder="Informe o motivo da movimentação",
                style=discord.TextStyle.paragraph,
                required=False,
                max_length=300,
            )
            self.add_item(self.descricao)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            valor = validar_valor_variavel(self.categoria, str(self.valor.value))
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await self.cog.aplicar_e_responder(
            interaction,
            self.categoria,
            self.destino,
            valor,
            str(self.descricao.value).strip() if self.descricao else "",
        )


class ViewXP(discord.ui.View):
    def __init__(self, usuario_id: int):
        super().__init__(timeout=TEMPO_FLUXO_XP)
        self.usuario_id = usuario_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message(
            "Somente quem iniciou esta movimentação pode usar estes controles.",
            ephemeral=True,
        )
        return False


class CategoriasXPView(ViewXP):
    def __init__(self, cog: XP, usuario_id: int, administrador: bool):
        super().__init__(usuario_id)
        self.cog = cog
        self.administrador = administrador
        opcoes = [
            discord.SelectOption(
                label="Herança Sanguínea",
                value="heranca",
                description="Usa as evoluções desbloqueadas da própria linhagem.",
                emoji="🧬",
            ),
            discord.SelectOption(
                label="Aula ou Treino",
                value="aula_treino",
                description="Concede 2 XP por participação em aula ou treino.",
                emoji="📚",
            ),
        ]
        if administrador:
            opcoes.extend(
                [
                    discord.SelectOption(label="Side-Quest", value="side_quest", description="Concede no mínimo 20 XP.", emoji="🧭"),
                    discord.SelectOption(label="Arco de Campanha", value="arco_campanha", description="Concede no mínimo 100 XP.", emoji="📖"),
                    discord.SelectOption(label="Crédito", value="credito", description="Adiciona uma quantidade personalizada de XP.", emoji="➕"),
                    discord.SelectOption(label="Débito", value="debito", description="Retira uma quantidade personalizada de XP.", emoji="➖"),
                ]
            )
        seletor = discord.ui.Select(
            placeholder="Opções de XP",
            options=opcoes,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        categoria = self.seletor.values[0]
        if categoria == "heranca":
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="🧬 XP — Herança Sanguínea",
                    description="Escolha se o XP está em uma ficha ou no Banco de XP.",
                    color=discord.Color.gold(),
                ),
                view=OpcoesDestinoXPView(
                    self.cog,
                    self.usuario_id,
                    categoria,
                    self.administrador,
                ),
            )
            return
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"💰 XP — {titulo_categoria_xp(categoria)}",
                description="Escolha primeiro uma das **Opções de Destino**.",
                color=discord.Color.gold(),
            ),
            view=OpcoesDestinoXPView(
                self.cog,
                self.usuario_id,
                categoria,
                self.administrador,
            ),
        )


class OpcoesDestinoXPView(ViewXP):
    def __init__(
        self,
        cog: XP,
        usuario_id: int,
        categoria: str,
        administrador: bool,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.categoria = categoria
        self.administrador = administrador
        usuario_destinos = None if administrador else usuario_id
        quantidades = {
            tipo: len(listar_destinos_xp(tipo, usuario_id=usuario_destinos))
            for tipo in ("fichas", "contas")
        }
        seletor = discord.ui.Select(
            placeholder="Opções de Destino",
            options=[
                discord.SelectOption(
                    label="Fichas",
                    value="fichas",
                    description=f"{quantidades['fichas']} ficha(s) disponível(is).",
                    emoji="📋",
                ),
                discord.SelectOption(
                    label="Banco de XP",
                    value="contas",
                    description=f"{quantidades['contas']} conta(s) disponível(is).",
                    emoji="🏦",
                ),
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar às Opções de XP",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        tipo = self.seletor.values[0]
        if tipo == "fichas":
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title=f"💰 XP — {titulo_categoria_xp(self.categoria)}",
                    description=(
                        "**Opção de Destino:** Fichas\n"
                        "Escolha a pasta da biblioteca que deseja consultar."
                    ),
                    color=discord.Color.gold(),
                ),
                view=PastasFichaXPView(
                    self.cog,
                    self.usuario_id,
                    self.categoria,
                    self.administrador,
                ),
            )
            return
        usuario_destinos = None if self.administrador else self.usuario_id
        paginas = paginas_destinos_xp(
            listar_destinos_xp(tipo, usuario_id=usuario_destinos)
        )
        primeira_preenchida = next(
            (indice for indice, (_, itens) in enumerate(paginas) if itens),
            0,
        )
        nome_tipo = "Fichas" if tipo == "fichas" else "Banco de XP"
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"💰 XP — {titulo_categoria_xp(self.categoria)}",
                description=(
                    f"**Opção de Destino:** {nome_tipo}\n"
                    "Escolha a faixa alfabética e, em seguida, o destino."
                ),
                color=discord.Color.gold(),
            ),
            view=DestinosAlfabeticosXPView(
                self.cog,
                self.usuario_id,
                self.categoria,
                tipo,
                self.administrador,
                primeira_preenchida,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="💰 XP",
                description="Escolha uma das opções disponíveis.",
                color=discord.Color.gold(),
            ),
            view=CategoriasXPView(
                self.cog,
                self.usuario_id,
                self.administrador,
            ),
        )


class PastasFichaXPView(ViewXP):
    def __init__(
        self,
        cog: XP,
        usuario_id: int,
        categoria: str,
        administrador: bool,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.categoria = categoria
        self.administrador = administrador
        usuario_destinos = None if administrador else usuario_id
        contagens = {
            grupo: len(
                listar_destinos_xp(
                    "fichas",
                    usuario_id=usuario_destinos,
                    grupo_ficha=grupo,
                )
            )
            for grupo in GRUPOS_FICHA
        }
        seletor = discord.ui.Select(
            placeholder="Pastas de Fichas",
            options=[
                discord.SelectOption(
                    label=grupo,
                    value=grupo,
                    emoji=EMOJIS_PASTAS_FICHA[grupo],
                    description=(
                        f"{contagens[grupo]} ficha(s) disponível(is)."
                        if contagens[grupo]
                        else "Pasta reservada; ainda não possui destinos disponíveis."
                    ),
                )
                for grupo in GRUPOS_FICHA
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar às Opções de Destino",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        grupo = self.seletor.values[0]
        usuario_destinos = None if self.administrador else self.usuario_id
        paginas = paginas_destinos_xp(
            listar_destinos_xp(
                "fichas",
                usuario_id=usuario_destinos,
                grupo_ficha=grupo,
            )
        )
        primeira_preenchida = next(
            (indice for indice, (_, itens) in enumerate(paginas) if itens),
            0,
        )
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"💰 XP — {titulo_categoria_xp(self.categoria)}",
                description=(
                    f"**Opção de Destino:** Fichas — **{grupo}**\n"
                    "Escolha a faixa alfabética e, em seguida, a ficha."
                ),
                color=discord.Color.gold(),
            ),
            view=DestinosAlfabeticosXPView(
                self.cog,
                self.usuario_id,
                self.categoria,
                "fichas",
                self.administrador,
                primeira_preenchida,
                grupo,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"💰 XP — {titulo_categoria_xp(self.categoria)}",
                description="Escolha primeiro uma das **Opções de Destino**.",
                color=discord.Color.gold(),
            ),
            view=OpcoesDestinoXPView(
                self.cog,
                self.usuario_id,
                self.categoria,
                self.administrador,
            ),
        )


class DestinosAlfabeticosXPView(ViewXP):
    def __init__(
        self,
        cog: XP,
        usuario_id: int,
        categoria: str,
        tipo: str,
        administrador: bool,
        pagina: int,
        grupo_ficha: str = "",
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.categoria = categoria
        self.tipo = tipo
        self.administrador = administrador
        self.grupo_ficha = grupo_ficha
        usuario_destinos = None if administrador else usuario_id
        self.paginas = paginas_destinos_xp(
            listar_destinos_xp(
                tipo,
                usuario_id=usuario_destinos,
                grupo_ficha=grupo_ficha,
            )
        )
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        rotulo, destinos = self.paginas[self.pagina]
        self.destinos = destinos

        faixas = discord.ui.Select(
            placeholder=f"Faixa alfabética — {rotulo}",
            options=[
                discord.SelectOption(
                    label=rotulo_pagina,
                    value=str(indice),
                    description=(
                        f"{len(itens)} destino(s) nesta faixa."
                        if itens
                        else "Faixa reservada para destinos futuros."
                    ),
                    default=indice == self.pagina,
                )
                for indice, (rotulo_pagina, itens) in enumerate(self.paginas)
            ],
            row=0,
        )
        faixas.callback = self.selecionar_faixa
        self.faixas = faixas
        self.add_item(faixas)

        if destinos:
            seletor_destinos = discord.ui.Select(
                placeholder=f"Destinos — {rotulo}",
                options=[
                    discord.SelectOption(
                        label=destino.nome[:100],
                        value=str(indice),
                        description=(
                            f"Ficha — {destino.caminho.parent.name}"
                            if destino.tipo == "Ficha"
                            else "Conta do Banco de XP"
                        )[:100],
                    )
                    for indice, destino in enumerate(destinos)
                ],
                row=1,
            )
            seletor_destinos.callback = self.selecionar_destino
            self.seletor_destinos = seletor_destinos
            self.add_item(seletor_destinos)

        voltar = discord.ui.Button(
            label=(
                "Voltar às Pastas de Fichas"
                if tipo == "fichas"
                else "Voltar às Opções de Destino"
            ),
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar_faixa(self, interaction: discord.Interaction) -> None:
        pagina = int(self.faixas.values[0])
        rotulo, itens = self.paginas[pagina]
        nome_tipo = "Fichas" if self.tipo == "fichas" else "Banco de XP"
        contexto = (
            f"{nome_tipo} — **{self.grupo_ficha}**"
            if self.grupo_ficha
            else nome_tipo
        )
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"💰 XP — {titulo_categoria_xp(self.categoria)}",
                description=(
                    f"**Opção de Destino:** {contexto} — **{rotulo}**\n"
                    + (
                        "Escolha um destino nesta faixa."
                        if itens
                        else "Esta faixa ainda não possui destinos. Escolha outra."
                    )
                ),
                color=discord.Color.gold(),
            ),
            view=DestinosAlfabeticosXPView(
                self.cog,
                self.usuario_id,
                self.categoria,
                self.tipo,
                self.administrador,
                pagina,
                self.grupo_ficha,
            ),
        )

    async def selecionar_destino(self, interaction: discord.Interaction) -> None:
        destino = self.destinos[int(self.seletor_destinos.values[0])]
        if not destino.caminho.is_file():
            await interaction.response.send_message(
                "O destino escolhido não está mais disponível.",
                ephemeral=True,
            )
            return
        if (
            not self.administrador
            and not destino_pertence_ao_usuario(destino, self.usuario_id)
        ):
            await interaction.response.send_message(
                "Você só pode movimentar XP nas fichas e contas criadas por você.",
                ephemeral=True,
            )
            return
        if self.categoria == "heranca":
            registro = carregar_registro_destino(destino)
            await interaction.response.edit_message(
                embed=embed_opcoes_heranca(registro, destino),
                view=OpcoesHerancaXPView(
                    self.cog,
                    self.usuario_id,
                    destino,
                    self.administrador,
                ),
            )
            return
        self.stop()
        valor_fixo = CATEGORIAS_XP[self.categoria][1]
        if valor_fixo is None:
            await interaction.response.send_modal(
                ValorXPModal(self.cog, self.categoria, destino)
            )
            return
        await self.cog.aplicar_e_responder(
            interaction,
            self.categoria,
            destino,
            valor_fixo,
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        if self.tipo == "fichas":
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title=f"💰 XP — {titulo_categoria_xp(self.categoria)}",
                    description=(
                        "**Opção de Destino:** Fichas\n"
                        "Escolha a pasta da biblioteca que deseja consultar."
                    ),
                    color=discord.Color.gold(),
                ),
                view=PastasFichaXPView(
                    self.cog,
                    self.usuario_id,
                    self.categoria,
                    self.administrador,
                ),
            )
            return
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"💰 XP — {titulo_categoria_xp(self.categoria)}",
                description="Escolha primeiro uma das **Opções de Destino**.",
                color=discord.Color.gold(),
            ),
            view=OpcoesDestinoXPView(
                self.cog,
                self.usuario_id,
                self.categoria,
                self.administrador,
            ),
        )


def _heranca_normalizada(ficha: FichaPersonagem) -> str:
    return normalizar_rotulo(ficha.heranca)


def carregar_registro_destino(destino: DestinoXP) -> FichaPersonagem | ContaXP:
    if destino.tipo == "Ficha":
        return FichaPersonagem.carregar(destino.caminho)
    return ContaXP.carregar(destino.caminho)


def ficha_para_rolagem(destino: DestinoXP) -> FichaPersonagem:
    registro = carregar_registro_destino(destino)
    if isinstance(registro, FichaPersonagem):
        return registro
    return FichaPersonagem(
        nome=registro.nome,
        grupo="Banco de XP",
        casa="--",
        heranca="Sangue Puro",
        nucleo="--",
        titular_id=registro.titular_id,
        xp=registro.xp,
        evolucao_heranca=5,
    )


def _heranca_compativel(ficha: FichaPersonagem) -> bool:
    return _heranca_normalizada(ficha) in {
        normalizar_rotulo("Sangue Puro"),
        normalizar_rotulo("Meio-Sangue"),
        normalizar_rotulo("Nascido-Trouxa"),
    }


def _rotulo_evento_heranca(ficha: FichaPersonagem) -> tuple[str, str]:
    heranca = _heranca_normalizada(ficha)
    if heranca == normalizar_rotulo("Sangue Puro"):
        return "Ganhar por maestria", "Registra um feitiço com resultado 18 ou maior e concede 2 XP."
    if heranca == normalizar_rotulo("Meio-Sangue"):
        return "Ganhar por crítico", "Registra um sucesso crítico em uma ação e concede 2 XP."
    return "Ganhar por ação trouxa", "Registra uma ação de natureza trouxa e concede 2 XP."


def embed_opcoes_heranca(
    registro: FichaPersonagem | ContaXP,
    destino: DestinoXP,
) -> discord.Embed:
    if isinstance(registro, FichaPersonagem):
        descricao = (
            f"**Ficha:** {registro.nome}\n"
            f"**Herança:** {registro.heranca}\n"
            f"**Evolução:** {registro.evolucao_heranca}/5\n"
            f"**XP disponível:** {registro.xp} XP\n\n"
            "A ficha usa somente as mecânicas já desbloqueadas. Compras confirmadas não podem ser revertidas."
        )
        if not _heranca_compativel(registro):
            descricao += "\n\nEsta Herança ainda não possui ações automáticas neste menu."
    else:
        descricao = (
            f"**Banco de XP:** {registro.nome}\n"
            f"**XP disponível:** {registro.xp} XP\n\n"
            "Como o Banco não possui ficha nem evolução registrada, todas as opções deste menu ficam disponíveis. "
            "Atributos de cena são registrados apenas no comprovante e rolagens usam bônus +0."
        )
    return discord.Embed(
        title="🧬 Herança Sanguínea",
        description=descricao,
        color=discord.Color.gold(),
    )


def itens_catalisador(categoria: str = "") -> list:
    itens = []
    categoria_normalizada = normalizar_rotulo(categoria)
    for item in carregar_todos_feiticos():
        campos = campos_normalizados(item.entrada)
        if categoria_normalizada and normalizar_rotulo(campos.get("categoria", "")) != categoria_normalizada:
            continue
        try:
            custo_catalisador(campos.get("grau de dificuldade", ""))
        except ValueError:
            continue
        itens.append(item)
    return sorted(itens, key=lambda item: item.nome.casefold())


def dados_rolagem_catalisador(ficha: FichaPersonagem, item) -> dict[str, object]:
    campos = campos_normalizados(item.entrada)
    categoria = campos.get("categoria", "").strip()
    grau = campos.get("grau de dificuldade", "").strip()
    custo = custo_catalisador(grau)
    ano, ano_fallback = ano_referencia_feitico(ficha, campos)
    cd_original = cd_feitico_por_ano(campos, ano)
    cd_reduzida = reduzir_cd_em_um_nivel(cd_original)
    aptidao = next(
        (
            nome
            for nome in ficha.aptidoes
            if normalizar_rotulo(nome) == normalizar_rotulo(categoria)
        ),
        categoria,
    )
    bonus = aptidao_efetiva(ficha, aptidao)
    return {
        "categoria": categoria,
        "grau": grau,
        "custo": custo,
        "ano": ano,
        "ano_fallback": ano_fallback,
        "cd_original": cd_original,
        "cd_reduzida": cd_reduzida,
        "aptidao": aptidao,
        "bonus": bonus,
    }


class OpcoesHerancaXPView(ViewXP):
    def __init__(self, cog: XP, usuario_id: int, destino: DestinoXP, administrador: bool):
        super().__init__(usuario_id)
        self.cog = cog
        self.destino = destino
        self.administrador = administrador
        registro = carregar_registro_destino(destino)
        eh_banco = isinstance(registro, ContaXP)
        opcoes: list[discord.SelectOption] = []
        if eh_banco:
            opcoes.extend(
                [
                    discord.SelectOption(label="Ganhar por crítico", value="evento_critico", description="Meio-Sangue: registra um sucesso crítico e concede 2 XP.", emoji="✨"),
                    discord.SelectOption(label="Ganhar por maestria", value="evento_maestria", description="Sangue Puro: registra um feitiço com resultado 18+ e concede 2 XP.", emoji="✨"),
                    discord.SelectOption(label="Ganhar por ação trouxa", value="evento_trouxa", description="Nascido-Trouxa: registra uma ação de natureza trouxa e concede 2 XP.", emoji="✨"),
                ]
            )
        elif _heranca_compativel(registro) and heranca_desbloqueada(registro, 1):
            rotulo, descricao = _rotulo_evento_heranca(registro)
            opcoes.append(discord.SelectOption(label=rotulo, value="evento", description=descricao, emoji="✨"))
        if eh_banco or (_heranca_compativel(registro) and heranca_desbloqueada(registro, 3)):
            opcoes.append(
                discord.SelectOption(
                    label="Comprar atributo de cena",
                    value="atributo",
                    description="Gasta 10 XP para conceder +2 cumulativo a um atributo durante a cena.",
                    emoji="🔥",
                )
            )
        if eh_banco or (
            _heranca_normalizada(registro) == normalizar_rotulo("Sangue Puro")
            and heranca_desbloqueada(registro, 5)
        ):
            opcoes.append(
                discord.SelectOption(
                    label="Diminuir dificuldade",
                    value="reducao_dificuldade",
                    description="Sangue Puro: conjura um feitiço com a dificuldade reduzida em um nível.",
                    emoji="🪄",
                )
            )
        if eh_banco or (
            _heranca_normalizada(registro) == normalizar_rotulo("Meio-Sangue")
            and heranca_desbloqueada(registro, 5)
        ):
            opcoes.append(
                discord.SelectOption(
                    label="Criar catalisador temporário",
                    value="catalisador_temporario",
                    description="Gasta 5 XP para usar um objeto não mágico como catalisador por 1d4+1 rodadas.",
                    emoji="🪄",
                )
            )
        if eh_banco or (
            _heranca_normalizada(registro) == normalizar_rotulo("Nascido-Trouxa")
            and heranca_desbloqueada(registro, 5)
        ):
            opcoes.append(
                discord.SelectOption(
                    label="Comprar Especialização",
                    value="especializacao",
                    description="Nascido-Trouxa: gasta 5 XP para usar uma Especialização sem cumprir os requisitos.",
                    emoji="🎓",
                )
            )
        if opcoes:
            seletor = discord.ui.Select(placeholder="Opções da Herança Sanguínea", options=opcoes)
            seletor.callback = self.selecionar
            self.seletor = seletor
            self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar aos destinos", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        acao = self.seletor.values[0]
        registro = carregar_registro_destino(self.destino)
        if acao.startswith("evento"):
            if isinstance(registro, ContaXP):
                eventos_banco = {
                    "evento_critico": ("Ganhar por crítico", "Registra um sucesso crítico e concede 2 XP."),
                    "evento_maestria": ("Ganhar por maestria", "Registra um feitiço com resultado 18 ou maior e concede 2 XP."),
                    "evento_trouxa": ("Ganhar por ação trouxa", "Registra uma ação de natureza trouxa e concede 2 XP."),
                }
                rotulo, descricao = eventos_banco[acao]
            else:
                rotulo, descricao = _rotulo_evento_heranca(registro)
            await interaction.response.edit_message(
                embed=discord.Embed(title=f"✨ {rotulo}", description=f"{descricao}\n\nConfirma o registro?", color=discord.Color.gold()),
                view=ConfirmarHerancaXPView(self.cog, self.usuario_id, self.destino, self.administrador, acao),
            )
            return
        if acao == "catalisador_temporario":
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="🪄 Catalisador temporário",
                    description="Gastar **5 XP** para transformar um objeto não mágico em catalisador por **1d4+1 rodadas**?",
                    color=discord.Color.gold(),
                ),
                view=ConfirmarHerancaXPView(self.cog, self.usuario_id, self.destino, self.administrador, "catalisador"),
            )
            return
        if acao == "atributo":
            await interaction.response.edit_message(
                embed=discord.Embed(title="🔥 Atributo de cena", description="Escolha o atributo que receberá +2 até o fim da cena.", color=discord.Color.gold()),
                view=AtributoHerancaXPView(self.cog, self.usuario_id, self.destino, self.administrador),
            )
            return
        if acao == "especializacao":
            nomes = listar_habilidades("especializacao", limite=None)
            paginas = _paginas_nomes(nomes)
            primeira = next((i for i, (_, grupo) in enumerate(paginas) if grupo), 0)
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="🎓 Comprar Especialização",
                    description="Escolha a Especialização que será usada sem cumprir seus requisitos. A compra custa **5 XP** e vale para este uso.",
                    color=discord.Color.gold(),
                ),
                view=EspecializacoesHerancaXPView(self.cog, self.usuario_id, self.destino, self.administrador, nomes, primeira),
            )
            return
        categorias = sorted(
            {campos_normalizados(item.entrada).get("categoria", "") for item in itens_catalisador()},
            key=str.casefold,
        )
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="🪄 Diminuir dificuldade",
                description="Escolha a categoria do feitiço. A redução custa **5 XP** para feitiços Intermediários ou **10 XP** para Avançados e diminui a CD em um nível.",
                color=discord.Color.gold(),
            ),
            view=CategoriaCatalisadorXPView(self.cog, self.usuario_id, self.destino, self.administrador, categorias),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=discord.Embed(title="🧬 XP — Herança Sanguínea", description="Escolha se o XP está em uma ficha ou no Banco de XP.", color=discord.Color.gold()),
            view=OpcoesDestinoXPView(self.cog, self.usuario_id, "heranca", self.administrador),
        )


class AtributoHerancaXPView(ViewXP):
    def __init__(self, cog: XP, usuario_id: int, destino: DestinoXP, administrador: bool):
        super().__init__(usuario_id)
        self.cog = cog
        self.destino = destino
        self.administrador = administrador
        seletor = discord.ui.Select(
            placeholder="Atributo",
            options=[discord.SelectOption(label=atributo, value=atributo) for atributo in ATRIBUTOS],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        atributo = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=discord.Embed(title="🔥 Confirmar atributo de cena", description=f"Gastar **10 XP** para conceder **+2 em {atributo}** até o fim da cena?", color=discord.Color.gold()),
            view=ConfirmarHerancaXPView(self.cog, self.usuario_id, self.destino, self.administrador, "atributo", atributo),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        registro = carregar_registro_destino(self.destino)
        await interaction.response.edit_message(embed=embed_opcoes_heranca(registro, self.destino), view=OpcoesHerancaXPView(self.cog, self.usuario_id, self.destino, self.administrador))


def _paginas_nomes(nomes: list[str]) -> list[tuple[str, list[str]]]:
    paginas: list[tuple[str, list[str]]] = []
    for grupo in GRUPOS_ALFABETICOS_FICHAS:
        agrupados = [
            nome
            for nome in nomes
            if (normalizar_rotulo(nome)[:1].upper() or "#") in grupo
        ]
        lotes = [agrupados[indice:indice + 25] for indice in range(0, len(agrupados), 25)] or [[]]
        for indice, lote in enumerate(lotes):
            rotulo = grupo if len(lotes) == 1 else f"{grupo} — {indice + 1}/{len(lotes)}"
            paginas.append((rotulo, lote))
    return paginas


class EspecializacoesHerancaXPView(ViewXP):
    def __init__(self, cog: XP, usuario_id: int, destino: DestinoXP, administrador: bool, nomes: list[str], pagina: int):
        super().__init__(usuario_id)
        self.cog = cog
        self.destino = destino
        self.administrador = administrador
        self.nomes = nomes
        self.paginas = _paginas_nomes(nomes)
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        rotulo, itens = self.paginas[self.pagina]
        faixas = discord.ui.Select(
            placeholder=f"Faixa alfabética — {rotulo}",
            options=[
                discord.SelectOption(
                    label=nome,
                    value=str(indice),
                    description=f"{len(grupo)} Especialização(ões).",
                    default=indice == self.pagina,
                )
                for indice, (nome, grupo) in enumerate(self.paginas)
            ],
            row=0,
        )
        faixas.callback = self.selecionar_faixa
        self.faixas = faixas
        self.add_item(faixas)
        if itens:
            seletor = discord.ui.Select(
                placeholder=f"Especializações — {rotulo}",
                options=[discord.SelectOption(label=nome[:100], value=nome[:100]) for nome in itens],
                row=1,
            )
            seletor.callback = self.selecionar_especializacao
            self.seletor = seletor
            self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=2)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar_faixa(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=EspecializacoesHerancaXPView(
                self.cog,
                self.usuario_id,
                self.destino,
                self.administrador,
                self.nomes,
                int(self.faixas.values[0]),
            )
        )

    async def selecionar_especializacao(self, interaction: discord.Interaction) -> None:
        nome = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="🎓 Confirmar Especialização",
                description=f"Gastar **5 XP** para usar **{nome}** sem cumprir seus requisitos? Esta compra vale para o uso atual.",
                color=discord.Color.gold(),
            ),
            view=ConfirmarHerancaXPView(
                self.cog,
                self.usuario_id,
                self.destino,
                self.administrador,
                "especializacao_improvisada",
                nome,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        registro = carregar_registro_destino(self.destino)
        await interaction.response.edit_message(
            embed=embed_opcoes_heranca(registro, self.destino),
            view=OpcoesHerancaXPView(self.cog, self.usuario_id, self.destino, self.administrador),
        )


class ConfirmarHerancaXPView(ViewXP):
    def __init__(self, cog: XP, usuario_id: int, destino: DestinoXP, administrador: bool, acao: str, item: str = ""):
        super().__init__(usuario_id)
        self.cog = cog
        self.destino = destino
        self.administrador = administrador
        self.acao = acao
        self.item = item
        self.concluido = False

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, emoji="✅")
    async def confirmar(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        if self.concluido:
            await interaction.response.send_message("Esta operação já foi concluída.", ephemeral=True)
            return
        caminho = self.destino.caminho.resolve()
        bloqueio = self.cog.bloqueios_destino.setdefault(caminho, asyncio.Lock())
        async with bloqueio:
            try:
                registro = carregar_registro_destino(self.destino)
                if not self.administrador and registro.titular_id != self.usuario_id:
                    raise ValueError("Você só pode usar a Herança Sanguínea de um destino vinculado a você.")
                if isinstance(registro, ContaXP):
                    if self.acao.startswith("evento"):
                        registro.xp += 2
                        mensagens_evento = {
                            "evento_critico": "O sucesso crítico concedeu **+2 XP**.",
                            "evento_maestria": "A maestria com resultado 18 ou maior concedeu **+2 XP**.",
                            "evento_trouxa": "A ação de natureza trouxa concedeu **+2 XP**.",
                        }
                        mensagem = mensagens_evento.get(self.acao, "O evento concedeu **+2 XP**.")
                    elif self.acao == "atributo":
                        if registro.xp < 10:
                            raise ValueError("XP insuficiente: esta ativação custa 10 XP.")
                        registro.xp -= 10
                        mensagem = f"Foi comprado **+2 em {self.item}** até o fim da cena."
                    elif self.acao == "especializacao_improvisada":
                        if registro.xp < 5:
                            raise ValueError("XP insuficiente: esta ativação custa 5 XP.")
                        registro.xp -= 5
                        mensagem = f"Foi comprado o uso de **{self.item}** sem cumprir seus requisitos."
                    elif self.acao == "catalisador":
                        if registro.xp < 5:
                            raise ValueError("XP insuficiente: esta ativação custa 5 XP.")
                        registro.xp -= 5
                        mensagem = "Foi criado um **Catalisador Temporário** por **1d4+1 rodadas**."
                    else:
                        raise ValueError("Esta ação não está disponível para o Banco de XP.")
                    salvar_conta_xp(registro, caminho)
                else:
                    from comandos.ficha import aplicar_mecanica_heranca
                    heranca = _heranca_normalizada(registro)
                    acao = self.acao
                    if acao == "evento" and heranca == normalizar_rotulo("Sangue Puro"):
                        acao = "maestria"
                    _, mensagem = aplicar_mecanica_heranca(registro, acao, self.item)
                    salvar_ficha(registro, caminho)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return
        self.concluido = True
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(title="✅ Herança Sanguínea aplicada", description=f"{mensagem}\n\n**Saldo atual:** {registro.xp} XP", color=discord.Color.green()),
            view=OpcoesHerancaXPView(self.cog, self.usuario_id, self.destino, self.administrador),
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        registro = carregar_registro_destino(self.destino)
        await interaction.response.edit_message(embed=embed_opcoes_heranca(registro, self.destino), view=OpcoesHerancaXPView(self.cog, self.usuario_id, self.destino, self.administrador))


class CategoriaCatalisadorXPView(ViewXP):
    def __init__(self, cog: XP, usuario_id: int, destino: DestinoXP, administrador: bool, categorias: list[str]):
        super().__init__(usuario_id)
        self.cog = cog
        self.destino = destino
        self.administrador = administrador
        seletor = discord.ui.Select(
            placeholder="Categoria do feitiço",
            options=[discord.SelectOption(label=categoria, value=categoria, description="Mostra os feitiços Intermediários e Avançados desta categoria.", emoji="🪄") for categoria in categorias],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        categoria = self.seletor.values[0]
        itens = itens_catalisador(categoria)
        primeira = next((i for i, (_, grupo) in enumerate(_paginas_feiticos(itens)) if grupo), 0)
        await interaction.response.edit_message(
            embed=discord.Embed(title=f"🪄 Diminuir dificuldade — {categoria}", description="Escolha a faixa alfabética e o feitiço que será conjurado com a CD reduzida.", color=discord.Color.gold()),
            view=FeiticosCatalisadorXPView(self.cog, self.usuario_id, self.destino, self.administrador, categoria, primeira),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        registro = carregar_registro_destino(self.destino)
        await interaction.response.edit_message(embed=embed_opcoes_heranca(registro, self.destino), view=OpcoesHerancaXPView(self.cog, self.usuario_id, self.destino, self.administrador))


def _paginas_feiticos(itens: list) -> list[tuple[str, list]]:
    paginas: list[tuple[str, list]] = []
    for grupo in GRUPOS_ALFABETICOS_FICHAS:
        agrupados = [
            item
            for item in itens
            if (normalizar_rotulo(item.nome)[:1].upper() or "#") in grupo
        ]
        lotes = [agrupados[indice:indice + 25] for indice in range(0, len(agrupados), 25)] or [[]]
        for indice, lote in enumerate(lotes):
            rotulo = grupo if len(lotes) == 1 else f"{grupo} — {indice + 1}/{len(lotes)}"
            paginas.append((rotulo, lote))
    return paginas


class FeiticosCatalisadorXPView(ViewXP):
    def __init__(self, cog: XP, usuario_id: int, destino: DestinoXP, administrador: bool, categoria: str, pagina: int):
        super().__init__(usuario_id)
        self.cog = cog
        self.destino = destino
        self.administrador = administrador
        self.categoria = categoria
        self.paginas = _paginas_feiticos(itens_catalisador(categoria))
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        rotulo, itens = self.paginas[self.pagina]
        faixas = discord.ui.Select(
            placeholder=f"Faixa alfabética — {rotulo}",
            options=[discord.SelectOption(label=nome, value=str(i), description=f"{len(grupo)} feitiço(s).", default=i == self.pagina) for i, (nome, grupo) in enumerate(self.paginas)],
            row=0,
        )
        faixas.callback = self.selecionar_faixa
        self.faixas = faixas
        self.add_item(faixas)
        if itens:
            seletor = discord.ui.Select(
                placeholder=f"Feitiços — {rotulo}",
                options=[discord.SelectOption(label=item.nome[:100], value=str(i), description=campos_normalizados(item.entrada).get("grau de dificuldade", "")[:100]) for i, item in enumerate(itens)],
                row=1,
            )
            seletor.callback = self.selecionar_feitico
            self.seletor = seletor
            self.itens = itens
            self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar às categorias", style=discord.ButtonStyle.secondary, row=2)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar_faixa(self, interaction: discord.Interaction) -> None:
        pagina = int(self.faixas.values[0])
        await interaction.response.edit_message(view=FeiticosCatalisadorXPView(self.cog, self.usuario_id, self.destino, self.administrador, self.categoria, pagina))

    async def selecionar_feitico(self, interaction: discord.Interaction) -> None:
        item = self.itens[int(self.seletor.values[0])]
        ficha = ficha_para_rolagem(self.destino)
        try:
            dados = dados_rolagem_catalisador(ficha, item)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        referencia = " (ano de desbloqueio usado porque a ficha não possui Ano)" if dados["ano_fallback"] else ""
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"🪄 Confirmar redução — {item.nome}",
                description=(
                    f"**Categoria:** {dados['categoria']}\n"
                    f"**Grau:** {dados['grau']}\n"
                    f"**Custo:** {dados['custo']} XP\n"
                    f"**Ano de referência:** {dados['ano']}{referencia}\n"
                    f"**CD:** {dados['cd_original']} → **{dados['cd_reduzida']}**\n"
                    f"**Rolagem:** 1d20 + {dados['aptidao']} {int(dados['bonus']):+d}\n\n"
                    "Ao confirmar, o XP será descontado e a rolagem será realizada imediatamente."
                ),
                color=discord.Color.gold(),
            ),
            view=ConfirmarCatalisadorXPView(self.cog, self.usuario_id, self.destino, self.administrador, self.categoria, item.nome),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        categorias = sorted({campos_normalizados(item.entrada).get("categoria", "") for item in itens_catalisador()}, key=str.casefold)
        await interaction.response.edit_message(
            embed=discord.Embed(title="🪄 Diminuir dificuldade", description="Escolha a categoria do feitiço.", color=discord.Color.gold()),
            view=CategoriaCatalisadorXPView(self.cog, self.usuario_id, self.destino, self.administrador, categorias),
        )


class ConfirmarCatalisadorXPView(ViewXP):
    def __init__(self, cog: XP, usuario_id: int, destino: DestinoXP, administrador: bool, categoria: str, nome_feitico: str):
        super().__init__(usuario_id)
        self.cog = cog
        self.destino = destino
        self.administrador = administrador
        self.categoria = categoria
        self.nome_feitico = nome_feitico
        self.concluido = False

    @discord.ui.button(label="Conjurar e descontar XP", style=discord.ButtonStyle.success, emoji="🪄")
    async def confirmar(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        if self.concluido:
            await interaction.response.send_message("Esta conjuração já foi concluída.", ephemeral=True)
            return
        caminho = self.destino.caminho.resolve()
        bloqueio = self.cog.bloqueios_destino.setdefault(caminho, asyncio.Lock())
        async with bloqueio:
            try:
                registro = carregar_registro_destino(self.destino)
                if not self.administrador and registro.titular_id != self.usuario_id:
                    raise ValueError("Você só pode usar a Herança Sanguínea de um destino vinculado a você.")
                ficha = ficha_para_rolagem(self.destino)
                if isinstance(registro, FichaPersonagem) and (
                    not heranca_desbloqueada(ficha, 5)
                    or _heranca_normalizada(ficha) != normalizar_rotulo("Sangue Puro")
                ):
                    raise ValueError("A Última Evolução de Sangue Puro ainda não foi desbloqueada.")
                item = next((item for item in itens_catalisador(self.categoria) if normalizar_rotulo(item.nome) == normalizar_rotulo(self.nome_feitico)), None)
                if item is None:
                    raise ValueError("O feitiço escolhido não está mais disponível na biblioteca.")
                dados = dados_rolagem_catalisador(ficha, item)
                custo = int(dados["custo"])
                if registro.xp < custo:
                    raise ValueError(f"XP insuficiente: esta redução custa {custo} XP.")
                registro.xp -= custo
                dado = rolar_d20_balanceado()
                total = dado + int(dados["bonus"])
                sucesso = total >= int(dados["cd_reduzida"])
                if isinstance(registro, FichaPersonagem):
                    salvar_ficha(registro, caminho)
                else:
                    salvar_conta_xp(registro, caminho)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return
        self.concluido = True
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"🪄 {self.nome_feitico}",
                description=(
                    f"`{dado}` 1d20 + **{int(dados['bonus']):+d} {dados['aptidao']}** = **{total}**\n"
                    f"CD reduzida: **{dados['cd_original']} → {dados['cd_reduzida']}**\n\n"
                    f"## {'Sucesso' if sucesso else 'Falha'}\n"
                    f"Foram descontados **{custo} XP**. Saldo atual: **{registro.xp} XP**."
                ),
                color=discord.Color.green() if sucesso else discord.Color.red(),
            ),
            view=None,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        itens = itens_catalisador(self.categoria)
        await interaction.response.edit_message(
            embed=discord.Embed(title=f"🪄 Diminuir dificuldade — {self.categoria}", description="Escolha a faixa alfabética e o feitiço que será conjurado com a CD reduzida.", color=discord.Color.gold()),
            view=FeiticosCatalisadorXPView(self.cog, self.usuario_id, self.destino, self.administrador, self.categoria, next((i for i, (_, grupo) in enumerate(_paginas_feiticos(itens)) if grupo), 0)),
        )


class XP(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bloqueio_contas = asyncio.Lock()
        self.bloqueios_destino: dict[Path, asyncio.Lock] = {}

    async def autocomplete_conta(
        self,
        interaction: discord.Interaction,
        atual: str,
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=referencia.nome[:100], value=referencia.nome[:100])
            for referencia in listar_contas_xp(atual)[:25]
        ]

    @app_commands.command(
        name="abrir-conta",
        description="Abre uma conta pessoal no Banco de XP.",
    )
    @app_commands.describe(nome="Nome obrigatório e único da conta")
    async def abrir_conta(self, interaction: discord.Interaction, nome: str) -> None:
        nome = nome.strip()
        try:
            caminho = caminho_nova_conta_xp(nome)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return

        async with self.bloqueio_contas:
            existente_titular = encontrar_conta_do_titular(interaction.user.id)
            if existente_titular:
                await interaction.response.send_message(
                    f"Você já possui a conta **{existente_titular.nome}** no Banco de XP.",
                    ephemeral=True,
                )
                return
            if encontrar_conta_xp(nome) or caminho.exists():
                await interaction.response.send_message(
                    "Já existe uma conta com esse nome. Escolha outro nome.",
                    ephemeral=True,
                )
                return
            try:
                conta = ContaXP(nome=nome, titular_id=interaction.user.id)
                salvar_conta_xp(conta, caminho, nova=True)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(
                    f"Não foi possível abrir a conta: {erro}",
                    ephemeral=True,
                )
                return

        embed = discord.Embed(
            title="🏦 Nova conta no Banco de XP",
            description="A conta foi aberta com sucesso e já pode receber XP!",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="📖 Nome da conta",
            value=f"**{conta.nome}**",
            inline=True,
        )
        embed.add_field(
            name="👤 Titular",
            value=interaction.user.mention,
            inline=True,
        )
        embed.add_field(
            name="💰 Saldo inicial",
            value="**0 XP**",
            inline=False,
        )
        embed.set_footer(text="Use /xp para movimentar o saldo desta conta.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="conta",
        description="Consulta uma conta e seu saldo no Banco de XP.",
    )
    @app_commands.describe(nome="Nome obrigatório da conta que deseja consultar")
    @app_commands.autocomplete(nome=autocomplete_conta)
    async def consultar_conta(
        self,
        interaction: discord.Interaction,
        nome: str,
    ) -> None:
        referencia = encontrar_conta_xp(nome)
        if referencia is None:
            await interaction.response.send_message(
                "A conta escolhida não foi encontrada no Banco de XP.",
                ephemeral=True,
            )
            return
        try:
            conta = ContaXP.carregar(referencia.caminho)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(
                f"Não foi possível consultar sua conta: {erro}",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🏦 Banco de XP",
            description="Sua conta está ativa e pronta para receber XP.",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="📖 Nome da conta",
            value=f"**{conta.nome}**",
            inline=True,
        )
        embed.add_field(
            name="👤 Titular",
            value=f"<@{conta.titular_id}>",
            inline=True,
        )
        embed.add_field(
            name="💰 Saldo disponível",
            value=f"**{conta.xp} XP**",
            inline=False,
        )
        embed.set_footer(text="Este saldo pode ser usado nas evoluções do personagem.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="xp",
        description="Abre as opções de XP disponíveis para você.",
    )
    async def xp(
        self,
        interaction: discord.Interaction,
    ) -> None:
        administrador = bool(interaction.permissions.manage_guild)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="💰 XP",
                description="Escolha uma das opções disponíveis.",
                color=discord.Color.gold(),
            ),
            view=CategoriasXPView(
                self,
                interaction.user.id,
                administrador,
            ),
            ephemeral=True,
        )

    async def aplicar_e_responder(
        self,
        interaction: discord.Interaction,
        categoria: str,
        destino: DestinoXP,
        valor: int,
        descricao: str = "",
    ) -> None:
        caminho = destino.caminho.resolve()
        bloqueio = self.bloqueios_destino.setdefault(caminho, asyncio.Lock())
        async with bloqueio:
            try:
                if destino.tipo == "Ficha":
                    registro = FichaPersonagem.carregar(caminho)
                else:
                    registro = ContaXP.carregar(caminho)
                anterior = registro.xp
                delta = -valor if categoria == "debito" else valor
                novo = anterior + delta
                if novo < 0:
                    await interaction.response.send_message(
                        f"Saldo insuficiente: **{destino.nome}** possui **{anterior} XP**.",
                        ephemeral=True,
                    )
                    return
                registro.xp = novo
                if destino.tipo == "Ficha":
                    salvar_ficha(registro, caminho)
                else:
                    salvar_conta_xp(registro, caminho)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(
                    f"Não foi possível atualizar o XP: {erro}",
                    ephemeral=True,
                )
                return

        nome_categoria = CATEGORIAS_XP[categoria][0]
        if delta < 0:
            titulo = "💳 XP debitado"
            destaque = f"## −{abs(delta)} XP"
            cor = discord.Color.red()
        else:
            titulo = "💳 XP recebido!" if categoria == "credito" else "💰 XP recebido!"
            destaque = f"## +{delta} XP"
            cor = discord.Color.green()
        embed = discord.Embed(
            title=titulo,
            description=destaque,
            color=cor,
        )
        embed.add_field(
            name="🎯 Destino",
            value=f"**{destino.nome}**\n{destino.tipo}",
            inline=True,
        )
        embed.add_field(
            name="📚 Motivo",
            value=nome_categoria,
            inline=True,
        )
        if descricao:
            embed.add_field(
                name="📝 Descrição",
                value=descricao,
                inline=False,
            )
        embed.add_field(
            name="Saldo anterior",
            value=f"`{anterior} XP`",
            inline=True,
        )
        embed.add_field(
            name="Novo saldo",
            value=f"**{novo} XP**",
            inline=True,
        )
        embed.set_footer(text=f"Movimentação realizada por {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)
