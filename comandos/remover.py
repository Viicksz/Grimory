import asyncio
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from comandos.adicionar import carregar_threads
from comandos.executar import extrair_aett, normalizar_ano
from utils.biblioteca import interpretar_markdown, normalizar_rotulo
from utils.fichas import (
    EMOJIS_PASTAS_FICHA,
    GRUPOS_ALFABETICOS_FICHAS,
    ORDEM_PASTAS_FICHA,
)


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_BIBLIOTECA = RAIZ_PROJETO / "biblioteca"
PASTA_LIXEIRA = PASTA_BIBLIOTECA / "lixeira"
TEMPO_CONFIRMACAO = 15 * 60
RAIZES_REMOVIVEIS = (
    PASTA_BIBLIOTECA / "feitiços",
    PASTA_BIBLIOTECA / "runas",
    PASTA_BIBLIOTECA / "bindrunes",
    PASTA_BIBLIOTECA / "poções",
    PASTA_BIBLIOTECA / "criaturas",
    PASTA_BIBLIOTECA / "fichas",
    PASTA_BIBLIOTECA / "Habilidades",
)
ARQUIVOS_LIXEIRA = {
    "Encantamentos": PASTA_LIXEIRA / "Encantamentos.md",
    "Transfiguração": PASTA_LIXEIRA / "Transfiguração.md",
    "Duelos": PASTA_LIXEIRA / "Duelos.md",
    "Defesa Contra Arte das Trevas": (
        PASTA_LIXEIRA / "Defesa Contra Arte das Trevas.md"
    ),
    "Arte das Trevas": PASTA_LIXEIRA / "Arte das Trevas.md",
    "Runas Antigas": PASTA_LIXEIRA / "Runas Antigas.md",
    "Bindrunes": PASTA_LIXEIRA / "Bindrunes.md",
    "Poções": PASTA_LIXEIRA / "Poções.md",
    "Criaturas": PASTA_LIXEIRA / "Criaturas.md",
    "Fichas": PASTA_LIXEIRA / "Fichas.md",
    "Herança Sanguínea": PASTA_LIXEIRA / "Herança Sanguínea.md",
    "Origem Mágica": PASTA_LIXEIRA / "Origem Mágica.md",
    "Especialização": PASTA_LIXEIRA / "Especialização.md",
}
CATEGORIAS_NAVEGACAO_REMOVER = tuple(ARQUIVOS_LIXEIRA)
PASTAS_FICHAS_REMOVIVEIS = ORDEM_PASTAS_FICHA
EMOJIS_CATEGORIAS_REMOVER = {
    "Encantamentos": "🪄",
    "Transfiguração": "🪄",
    "Duelos": "🪄",
    "Defesa Contra Arte das Trevas": "🪄",
    "Arte das Trevas": "🪄",
    "Runas Antigas": "📜",
    "Bindrunes": "📜",
    "Poções": "🧪",
    "Criaturas": "🐾",
    "Fichas": "📋",
    "Herança Sanguínea": "🧬",
    "Origem Mágica": "✨",
    "Especialização": "🎓",
}


class ErroRemocao(RuntimeError):
    pass


@dataclass(frozen=True)
class ItemRemovivel:
    arquivo: Path
    identificador: str
    nome: str
    titulo: str
    categoria: str
    secao_thread: str
    chave_thread: str


@dataclass
class SessaoRemocao:
    usuario_id: int
    acao: str
    item: Optional[ItemRemovivel] = None
    mensagem_id_prevista: Optional[int] = None
    thread_id_prevista: Optional[int] = None


@dataclass(frozen=True)
class MovimentoLixeira:
    item: ItemRemovivel
    conteudo_original: str
    conteudo_anterior_lixeira: str


def campos_normalizados(conteudo: str) -> tuple[str, str, dict[str, str]]:
    entrada = interpretar_markdown(conteudo)
    campos = {
        normalizar_rotulo(rotulo): valor.strip()
        for rotulo, valor in entrada.campos.items()
    }
    return entrada.titulo, entrada.descricao, campos


def classificar_item(arquivo: Path) -> ItemRemovivel:
    try:
        relativo = arquivo.resolve().relative_to(PASTA_BIBLIOTECA.resolve())
    except ValueError as erro:
        raise ErroRemocao("O item ficou fora da biblioteca do Grimory.") from erro

    partes = relativo.parts
    conteudo = arquivo.read_text(encoding="utf-8-sig")
    titulo, descricao, campos = campos_normalizados(conteudo)
    nome = arquivo.stem
    raiz = partes[0]

    if raiz == "feitiços":
        ramo = partes[1]
        if ramo == "Trevas":
            categoria = "Arte das Trevas"
            secao = "Arte das Trevas"
            chave = partes[2]
        else:
            categoria = (
                "Defesa Contra Arte das Trevas" if ramo == "DCAT" else ramo
            )
            secao = categoria
            chave = normalizar_ano(campos.get("ano de desbloqueio", ""))
    elif raiz == "runas":
        categoria = "Runas Antigas"
        secao = "Runas Antigas"
        chave = extrair_aett(descricao) or ""
    elif raiz == "bindrunes":
        categoria = "Bindrunes"
        secao = "Runas Antigas"
        chave = "Bindrunes"
    elif raiz == "poções":
        categoria = "Poções"
        secao = "Poções"
        chave = normalizar_ano(
            campos.get("ano de desbloqueio", "") or arquivo.parent.name
        )
    elif raiz == "criaturas":
        categoria = "Criaturas"
        secao = "Trato de Criaturas Mágicas"
        chave = campos.get("periculosidade", "") or arquivo.parent.name
    elif raiz == "fichas":
        if len(partes) < 3 or normalizar_rotulo(partes[1]) == "configuracoes":
            raise ErroRemocao("As configurações de ficha não podem ser removidas.")
        categoria = "Fichas"
        if partes[1] == "Criaturas":
            secao = "Fichas de Criatura"
            chave = "Criaturas"
        else:
            secao = "Fichas de Personagem"
            chave = partes[1]
    elif raiz == "Habilidades":
        if len(partes) < 3:
            raise ErroRemocao("A habilidade não possui uma categoria válida.")
        categoria = partes[1]
        if categoria not in {"Herança Sanguínea", "Origem Mágica", "Especialização"}:
            raise ErroRemocao("Essa categoria de habilidade não pode ser removida.")
        secao = "Habilidades"
        chave = categoria
    else:
        raise ErroRemocao("Essa parte da biblioteca não pode ser removida.")

    if categoria not in ARQUIVOS_LIXEIRA:
        raise ErroRemocao(f"Não existe uma categoria de lixeira para **{categoria}**.")

    return ItemRemovivel(
        arquivo=arquivo,
        identificador=relativo.as_posix(),
        nome=nome,
        titulo=titulo or nome,
        categoria=categoria,
        secao_thread=secao,
        chave_thread=chave,
    )


def listar_itens_removiveis() -> list[ItemRemovivel]:
    itens = []
    for raiz in RAIZES_REMOVIVEIS:
        if not raiz.is_dir():
            continue
        for arquivo in raiz.rglob("*.md"):
            if not arquivo.is_file():
                continue
            relativo = arquivo.relative_to(PASTA_BIBLIOTECA)
            if (
                relativo.parts[0] == "fichas"
                and len(relativo.parts) > 1
                and normalizar_rotulo(relativo.parts[1]) == "configuracoes"
            ):
                continue
            itens.append(classificar_item(arquivo))
    return sorted(itens, key=lambda item: (item.nome.casefold(), item.categoria.casefold()))


def itens_removiveis_da_categoria(
    categoria: str,
    pasta_ficha: str = "",
) -> list[ItemRemovivel]:
    itens = [
        item for item in listar_itens_removiveis()
        if item.categoria == categoria
    ]
    if categoria == "Fichas" and pasta_ficha:
        itens = [
            item
            for item in itens
            if len(Path(item.identificador).parts) > 1
            and Path(item.identificador).parts[1] == pasta_ficha
        ]
    return itens


def paginas_itens_removiveis(
    itens: list[ItemRemovivel],
) -> list[tuple[str, list[ItemRemovivel]]]:
    paginas: list[tuple[str, list[ItemRemovivel]]] = []
    for grupo in GRUPOS_ALFABETICOS_FICHAS:
        agrupados = [
            item
            for item in itens
            if (normalizar_rotulo(item.nome)[:1].upper() or "#") in grupo
        ]
        lotes = [
            agrupados[indice:indice + 25]
            for indice in range(0, len(agrupados), 25)
        ] or [[]]
        for indice, lote in enumerate(lotes):
            rotulo = grupo if len(lotes) == 1 else f"{grupo} — {indice + 1}/{len(lotes)}"
            paginas.append((rotulo, lote))
    return paginas


def resolver_item(valor: str) -> tuple[Optional[ItemRemovivel], list[ItemRemovivel]]:
    procurado = valor.strip().replace("\\", "/")
    itens = listar_itens_removiveis()

    por_identificador = [
        item for item in itens if item.identificador.casefold() == procurado.casefold()
    ]
    if por_identificador:
        return por_identificador[0], []

    chave = normalizar_rotulo(procurado)
    por_nome = [
        item
        for item in itens
        if normalizar_rotulo(item.nome) == chave
        or normalizar_rotulo(item.titulo) == chave
    ]
    if len(por_nome) == 1:
        return por_nome[0], []
    return None, por_nome


def garantir_lixeira() -> None:
    PASTA_LIXEIRA.mkdir(parents=True, exist_ok=True)
    for arquivo in ARQUIVOS_LIXEIRA.values():
        if not arquivo.exists():
            arquivo.touch()


def escrever_atomico(arquivo: Path, conteudo: str) -> None:
    temporario = arquivo.with_name(f".{arquivo.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporario.write_text(conteudo, encoding="utf-8")
        os.replace(temporario, arquivo)
    finally:
        temporario.unlink(missing_ok=True)


def mover_para_lixeira(item: ItemRemovivel, usuario_id: int) -> MovimentoLixeira:
    garantir_lixeira()
    if not item.arquivo.is_file():
        raise ErroRemocao(f"**{item.nome}** já não existe na biblioteca.")

    arquivo_lixeira = ARQUIVOS_LIXEIRA[item.categoria]
    conteudo_original = item.arquivo.read_text(encoding="utf-8-sig")
    conteudo_anterior = arquivo_lixeira.read_text(encoding="utf-8-sig")
    marcador = uuid.uuid4().hex
    data = datetime.now(timezone.utc).isoformat(timespec="seconds")
    bloco = (
        f"<!-- grimory-lixeira-inicio:{marcador} -->\n"
        f"<!-- origem: {item.identificador} | usuario: {usuario_id} | data: {data} -->\n"
        f"{conteudo_original.rstrip()}\n"
        f"<!-- grimory-lixeira-fim:{marcador} -->\n"
    )
    novo_conteudo = (
        f"{conteudo_anterior.rstrip()}\n\n{bloco}"
        if conteudo_anterior.strip()
        else bloco
    )

    escrever_atomico(arquivo_lixeira, novo_conteudo)
    try:
        item.arquivo.unlink()
    except OSError:
        escrever_atomico(arquivo_lixeira, conteudo_anterior)
        raise

    return MovimentoLixeira(item, conteudo_original, conteudo_anterior)


def restaurar_movimento(movimento: MovimentoLixeira) -> None:
    movimento.item.arquivo.parent.mkdir(parents=True, exist_ok=True)
    escrever_atomico(movimento.item.arquivo, movimento.conteudo_original)
    escrever_atomico(
        ARQUIVOS_LIXEIRA[movimento.item.categoria],
        movimento.conteudo_anterior_lixeira,
    )


def estado_lixeira() -> tuple[int, int]:
    garantir_lixeira()
    itens = 0
    categorias = 0
    for arquivo in ARQUIVOS_LIXEIRA.values():
        conteudo = arquivo.read_text(encoding="utf-8-sig")
        quantidade = conteudo.count("<!-- grimory-lixeira-inicio:")
        if conteudo.strip():
            categorias += 1
        itens += quantidade
    return itens, categorias


def limpar_lixeira() -> tuple[int, int]:
    garantir_lixeira()
    anteriores = {
        arquivo: arquivo.read_text(encoding="utf-8-sig")
        for arquivo in ARQUIVOS_LIXEIRA.values()
    }
    itens = sum(
        conteudo.count("<!-- grimory-lixeira-inicio:")
        for conteudo in anteriores.values()
    )
    categorias = sum(bool(conteudo.strip()) for conteudo in anteriores.values())

    alterados = []
    try:
        for arquivo in ARQUIVOS_LIXEIRA.values():
            escrever_atomico(arquivo, "")
            alterados.append(arquivo)
    except OSError:
        for arquivo in alterados:
            escrever_atomico(arquivo, anteriores[arquivo])
        raise

    return itens, categorias


def encontrar_thread_id(item: ItemRemovivel) -> Optional[int]:
    try:
        threads = carregar_threads()
    except (OSError, ValueError) as erro:
        raise ErroRemocao("Não consegui ler o cadastro das threads.") from erro
    secao = normalizar_rotulo(item.secao_thread)
    chave = normalizar_rotulo(item.chave_thread)
    encontrado = threads.get((secao, chave))

    if encontrado is None and secao == normalizar_rotulo("Trato de Criaturas Mágicas"):
        encontrado = (
            threads.get((normalizar_rotulo("Criaturas"), chave))
            or threads.get((normalizar_rotulo("Criaturas"), "criaturas"))
            or threads.get((secao, "criaturas"))
        )
    return encontrado


def mensagem_corresponde(message: discord.Message, item: ItemRemovivel) -> bool:
    alvos = {normalizar_rotulo(item.nome), normalizar_rotulo(item.titulo)}

    for embed in message.embeds:
        if embed.title and normalizar_rotulo(embed.title) in alvos:
            return True

    textos = [message.content]
    textos.extend(embed.description or "" for embed in message.embeds)
    for texto in textos:
        for linha in texto.splitlines():
            cabecalho = re.match(r"^#{1,6}\s+(.+?)\s*$", linha.strip())
            if cabecalho:
                titulo = cabecalho.group(1).strip().strip("*_")
                titulo = re.sub(r"^[^\wÀ-ÿ]+", "", titulo).strip()
                if normalizar_rotulo(titulo) in alvos:
                    return True
    return False


async def obter_thread(
    bot: commands.Bot,
    thread_id: Optional[int],
) -> Optional[discord.abc.Messageable]:
    if thread_id is None:
        return None
    canal = bot.get_channel(thread_id)
    if canal is None:
        try:
            canal = await bot.fetch_channel(thread_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException) as erro:
            raise ErroRemocao(f"Não consegui acessar a thread configurada: {erro}") from erro
    if not hasattr(canal, "history"):
        raise ErroRemocao("O ID configurado não pertence a uma thread pesquisável.")
    return canal


async def localizar_mensagens(
    bot: commands.Bot,
    item: ItemRemovivel,
    thread_id: Optional[int],
) -> list[discord.Message]:
    canal = await obter_thread(bot, thread_id)
    if canal is None:
        return []

    encontradas = []
    try:
        async for mensagem in canal.history(limit=None):
            if mensagem_corresponde(mensagem, item):
                encontradas.append(mensagem)
                if len(encontradas) >= 2:
                    break
    except (discord.Forbidden, discord.HTTPException) as erro:
        raise ErroRemocao(f"Não consegui pesquisar a thread: {erro}") from erro
    return encontradas


class ViewDaSessao(discord.ui.View):
    def __init__(self, sessao: SessaoRemocao):
        super().__init__(timeout=TEMPO_CONFIRMACAO)
        self.sessao = sessao

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.sessao.usuario_id:
            return True
        await interaction.response.send_message(
            "Somente quem iniciou este `/remove` pode usar estes controles.",
            ephemeral=True,
        )
        return False

    async def cancelar(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(
            content="Operação cancelada. Nada foi alterado.",
            embed=None,
            view=None,
        )


class CategoriasRemocaoView(ViewDaSessao):
    def __init__(self, cog: Remover, usuario_id: int):
        super().__init__(SessaoRemocao(usuario_id, "navegar"))
        self.cog = cog
        itens = listar_itens_removiveis()
        contagens = {
            categoria: sum(item.categoria == categoria for item in itens)
            for categoria in CATEGORIAS_NAVEGACAO_REMOVER
        }
        quantidade_lixeira, _ = estado_lixeira()
        seletor = discord.ui.Select(
            placeholder="Categoria da Biblioteca",
            options=[
                discord.SelectOption(
                    label="Lixeira",
                    value="__lixeira__",
                    description=f"Limpa os {quantidade_lixeira} item(ns) arquivado(s).",
                    emoji="🗑️",
                ),
                *[
                    discord.SelectOption(
                        label=categoria,
                        value=categoria,
                        emoji=EMOJIS_CATEGORIAS_REMOVER[categoria],
                        description=(
                            f"{contagens[categoria]} item(ns) disponível(is)."
                            if contagens[categoria]
                            else "Categoria reservada; ainda não possui itens."
                        ),
                    )
                    for categoria in CATEGORIAS_NAVEGACAO_REMOVER
                ],
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        categoria = self.seletor.values[0]
        if categoria == "__lixeira__":
            await interaction.response.defer()
            await self.cog.preparar_limpeza_lixeira(interaction)
            return
        if categoria == "Fichas":
            await interaction.response.edit_message(
                content=None,
                embed=discord.Embed(
                    title="🗑️ Remover — Fichas",
                    description="Escolha a pasta de fichas da biblioteca.",
                    color=0xB00020,
                ),
                view=PastasFichaRemocaoView(
                    self.cog,
                    self.sessao.usuario_id,
                ),
            )
            return
        paginas = paginas_itens_removiveis(
            itens_categoria := itens_removiveis_da_categoria(categoria)
        )
        primeira_preenchida = next(
            (indice for indice, (_, itens) in enumerate(paginas) if itens),
            0,
        )
        await interaction.response.edit_message(
            content=None,
            embed=discord.Embed(
                title=f"🗑️ Remover — {categoria}",
                description="Escolha a faixa alfabética e, em seguida, o item.",
                color=0xB00020,
            ),
            view=ItensRemocaoAlfabeticosView(
                self.cog,
                self.sessao.usuario_id,
                categoria,
                primeira_preenchida,
                itens_disponiveis=itens_categoria,
            ),
        )


class PastasFichaRemocaoView(ViewDaSessao):
    def __init__(self, cog: Remover, usuario_id: int):
        super().__init__(SessaoRemocao(usuario_id, "navegar"))
        self.cog = cog
        fichas = itens_removiveis_da_categoria("Fichas")
        contagens = {
            pasta: sum(
                len(Path(item.identificador).parts) > 1
                and Path(item.identificador).parts[1] == pasta
                for item in fichas
            )
            for pasta in PASTAS_FICHAS_REMOVIVEIS
        }
        seletor = discord.ui.Select(
            placeholder="Pastas de Fichas",
            options=[
                discord.SelectOption(
                    label=pasta,
                    value=pasta,
                    emoji=EMOJIS_PASTAS_FICHA[pasta],
                    description=(
                        f"{contagens[pasta]} ficha(s) disponível(is)."
                        if contagens[pasta]
                        else "Pasta reservada; ainda não possui fichas."
                    ),
                )
                for pasta in PASTAS_FICHAS_REMOVIVEIS
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar às categorias",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        pasta = self.seletor.values[0]
        itens_pasta = itens_removiveis_da_categoria("Fichas", pasta)
        paginas = paginas_itens_removiveis(itens_pasta)
        primeira_preenchida = next(
            (indice for indice, (_, itens) in enumerate(paginas) if itens),
            0,
        )
        await interaction.response.edit_message(
            content=None,
            embed=discord.Embed(
                title=f"🗑️ Remover — Fichas — {pasta}",
                description="Escolha a faixa alfabética e, em seguida, a ficha.",
                color=0xB00020,
            ),
            view=ItensRemocaoAlfabeticosView(
                self.cog,
                self.sessao.usuario_id,
                "Fichas",
                primeira_preenchida,
                pasta,
                itens_pasta,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=discord.Embed(
                title="🗑️ Remover item",
                description="Escolha primeiro a categoria da biblioteca.",
                color=0xB00020,
            ),
            view=CategoriasRemocaoView(self.cog, self.sessao.usuario_id),
        )


class ItensRemocaoAlfabeticosView(ViewDaSessao):
    def __init__(
        self,
        cog: Remover,
        usuario_id: int,
        categoria: str,
        pagina: int,
        pasta_ficha: str = "",
        itens_disponiveis: Optional[list[ItemRemovivel]] = None,
    ):
        super().__init__(SessaoRemocao(usuario_id, "navegar"))
        self.cog = cog
        self.categoria = categoria
        self.pasta_ficha = pasta_ficha
        self.itens_disponiveis = (
            itens_removiveis_da_categoria(categoria, pasta_ficha)
            if itens_disponiveis is None
            else itens_disponiveis
        )
        self.paginas = paginas_itens_removiveis(
            self.itens_disponiveis
        )
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        rotulo, itens = self.paginas[self.pagina]
        self.itens = itens

        faixas = discord.ui.Select(
            placeholder=f"Faixa alfabética — {rotulo}",
            options=[
                discord.SelectOption(
                    label=rotulo_pagina,
                    value=str(indice),
                    description=(
                        f"{len(itens_pagina)} item(ns) nesta faixa."
                        if itens_pagina
                        else "Faixa reservada para itens futuros."
                    ),
                    default=indice == self.pagina,
                )
                for indice, (rotulo_pagina, itens_pagina) in enumerate(self.paginas)
            ],
            row=0,
        )
        faixas.callback = self.selecionar_faixa
        self.faixas = faixas
        self.add_item(faixas)

        if itens:
            seletor_itens = discord.ui.Select(
                placeholder=f"Itens — {rotulo}",
                options=[
                    discord.SelectOption(
                        label=item.nome[:100],
                        value=str(indice),
                        description=item.identificador[:100],
                    )
                    for indice, item in enumerate(itens)
                ],
                row=1,
            )
            seletor_itens.callback = self.selecionar_item
            self.seletor_itens = seletor_itens
            self.add_item(seletor_itens)

        voltar = discord.ui.Button(
            label=(
                "Voltar às Pastas de Fichas"
                if pasta_ficha
                else "Voltar às categorias"
            ),
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar_faixa(self, interaction: discord.Interaction) -> None:
        pagina = int(self.faixas.values[0])
        rotulo, itens = self.paginas[pagina]
        contexto = (
            f"{self.categoria} — {self.pasta_ficha}"
            if self.pasta_ficha
            else self.categoria
        )
        await interaction.response.edit_message(
            content=None,
            embed=discord.Embed(
                title=f"🗑️ Remover — {contexto} — {rotulo}",
                description=(
                    "Escolha um item nesta faixa."
                    if itens
                    else "Esta faixa ainda não possui itens. Escolha outra."
                ),
                color=0xB00020,
            ),
            view=ItensRemocaoAlfabeticosView(
                self.cog,
                self.sessao.usuario_id,
                self.categoria,
                pagina,
                self.pasta_ficha,
                self.itens_disponiveis,
            ),
        )

    async def selecionar_item(self, interaction: discord.Interaction) -> None:
        item = self.itens[int(self.seletor_itens.values[0])]
        await interaction.response.defer()
        await self.cog.preparar_remocao_item(interaction, item)

    async def voltar(self, interaction: discord.Interaction) -> None:
        if self.pasta_ficha:
            await interaction.response.edit_message(
                content=None,
                embed=discord.Embed(
                    title="🗑️ Remover — Fichas",
                    description="Escolha a pasta de fichas da biblioteca.",
                    color=0xB00020,
                ),
                view=PastasFichaRemocaoView(
                    self.cog,
                    self.sessao.usuario_id,
                ),
            )
            return
        await interaction.response.edit_message(
            content=None,
            embed=discord.Embed(
                title="🗑️ Remover item",
                description="Escolha primeiro a categoria da biblioteca.",
                color=0xB00020,
            ),
            view=CategoriasRemocaoView(self.cog, self.sessao.usuario_id),
        )


class ViewConfirmacaoFinal(ViewDaSessao):
    @discord.ui.button(label="Confirmar operação", style=discord.ButtonStyle.danger)
    async def confirmar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        await interaction.response.defer()
        cog = interaction.client.get_cog("Remover")
        if cog is None:
            await interaction.edit_original_response(
                content="O comando `/remove` não está disponível.",
                view=None,
            )
            return
        await cog.executar_confirmacao(interaction, self.sessao)
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def botao_cancelar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        await self.cancelar(interaction)


class Remover(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bloqueio = asyncio.Lock()

    async def cog_load(self) -> None:
        garantir_lixeira()

    async def preparar_limpeza_lixeira(
        self,
        interaction: discord.Interaction,
    ) -> None:
        quantidade, categorias = estado_lixeira()
        sessao = SessaoRemocao(interaction.user.id, "limpar")
        embed = discord.Embed(
            title="Limpar lixeira",
            description=(
                "Os arquivos das categorias serão preservados, mas todo o texto "
                "guardado neles será apagado."
            ),
            color=0xB00020,
        )
        embed.add_field(name="Itens arquivados", value=str(quantidade), inline=True)
        embed.add_field(name="Categorias ocupadas", value=str(categorias), inline=True)
        await interaction.edit_original_response(
            content="Confira antes de continuar.",
            embed=embed,
            view=ViewConfirmacaoFinal(sessao),
        )

    async def preparar_remocao_item(
        self,
        interaction: discord.Interaction,
        item: ItemRemovivel,
    ) -> None:
        encontrado, ambiguos = resolver_item(item.identificador)
        if encontrado is None or ambiguos:
            await interaction.edit_original_response(
                content="O item escolhido não está mais disponível na biblioteca.",
                embed=None,
                view=None,
            )
            return

        try:
            thread_id = encontrar_thread_id(encontrado)
            mensagens = await localizar_mensagens(self.bot, encontrado, thread_id)
        except ErroRemocao as erro:
            await interaction.edit_original_response(content=str(erro), embed=None, view=None)
            return

        if len(mensagens) > 1:
            await interaction.edit_original_response(
                content=(
                    f"Encontrei mais de uma publicação de **{encontrado.nome}** na "
                    "thread. Para evitar apagar a mensagem errada, a operação foi bloqueada."
                ),
                embed=None,
                view=None,
            )
            return

        mensagem = mensagens[0] if mensagens else None
        sessao = SessaoRemocao(
            interaction.user.id,
            "remover",
            encontrado,
            mensagem.id if mensagem else None,
            thread_id,
        )
        embed = discord.Embed(
            title="Confirmar remoção",
            description=(
                "O conteúdo será preservado na lixeira e deixará de aparecer "
                "nos comandos da biblioteca."
            ),
            color=0xB00020,
        )
        embed.add_field(name="Item", value=encontrado.nome, inline=True)
        embed.add_field(name="Categoria", value=encontrado.categoria, inline=True)
        embed.add_field(
            name="Arquivo de origem",
            value=f"`{encontrado.identificador}`",
            inline=False,
        )
        if mensagem:
            estado_discord = f"[Mensagem localizada]({mensagem.jump_url})"
        elif thread_id is None:
            estado_discord = "Sem thread configurada; não há mensagem para apagar."
        else:
            estado_discord = "Nenhuma mensagem correspondente foi encontrada na thread."
        embed.add_field(name="Discord", value=estado_discord, inline=False)
        await interaction.edit_original_response(
            content="Confira cuidadosamente antes de continuar.",
            embed=embed,
            view=ViewConfirmacaoFinal(sessao),
        )

    @app_commands.command(
        name="remove",
        description="Move um item para a lixeira ou limpa a lixeira com confirmação.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def remover(self, interaction: discord.Interaction):
        membro = interaction.user
        if not isinstance(membro, discord.Member) or not membro.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Você precisa da permissão **Gerenciar servidor** para usar `/remove`.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🗑️ Remover item",
                description="Escolha primeiro a categoria da biblioteca.",
                color=0xB00020,
            ),
            view=CategoriasRemocaoView(self, membro.id),
            ephemeral=True,
        )

    async def executar_confirmacao(
        self,
        interaction: discord.Interaction,
        sessao: SessaoRemocao,
    ) -> None:
        async with self.bloqueio:
            if sessao.acao == "limpar":
                try:
                    itens, categorias = limpar_lixeira()
                except OSError as erro:
                    await interaction.edit_original_response(
                        content=f"Não consegui limpar a lixeira: {erro}",
                        embed=None,
                        view=None,
                    )
                    return
                await interaction.edit_original_response(
                    content=(
                        f"Lixeira limpa: **{itens} item(ns)** removidos do texto de "
                        f"**{categorias} categoria(s)**. Os arquivos das categorias "
                        "continuam existentes."
                    ),
                    embed=None,
                    view=None,
                )
                return

            item_atual, ambiguos = resolver_item(sessao.item.identificador)
            if item_atual is None or ambiguos:
                await interaction.edit_original_response(
                    content="O item mudou ou já foi removido. Recomece o `/remove`.",
                    embed=None,
                    view=None,
                )
                return

            try:
                thread_id = encontrar_thread_id(item_atual)
                mensagens = await localizar_mensagens(self.bot, item_atual, thread_id)
            except ErroRemocao as erro:
                await interaction.edit_original_response(content=str(erro), embed=None, view=None)
                return

            ids = [mensagem.id for mensagem in mensagens]
            esperado = (
                [sessao.mensagem_id_prevista]
                if sessao.mensagem_id_prevista is not None
                else []
            )
            if thread_id != sessao.thread_id_prevista or ids != esperado:
                await interaction.edit_original_response(
                    content=(
                        "A thread ou a mensagem mudou durante a confirmação. "
                        "Nada foi alterado; recomece o `/remove`."
                    ),
                    embed=None,
                    view=None,
                )
                return

            try:
                movimento = mover_para_lixeira(item_atual, interaction.user.id)
            except (ErroRemocao, OSError) as erro:
                await interaction.edit_original_response(
                    content=f"Não consegui mover o item para a lixeira: {erro}",
                    embed=None,
                    view=None,
                )
                return

            if mensagens:
                try:
                    await mensagens[0].delete()
                except (discord.Forbidden, discord.NotFound, discord.HTTPException) as erro:
                    try:
                        restaurar_movimento(movimento)
                    except OSError as restauracao:
                        detalhe = f"; a restauração local também falhou: {restauracao}"
                    else:
                        detalhe = "; a biblioteca local foi restaurada"
                    await interaction.edit_original_response(
                        content=f"Não consegui apagar a mensagem do Discord: {erro}{detalhe}.",
                        embed=None,
                        view=None,
                    )
                    return

            await interaction.edit_original_response(
                content=(
                    f"**{item_atual.nome}** foi movido para "
                    f"`biblioteca/lixeira/{ARQUIVOS_LIXEIRA[item_atual.categoria].name}`"
                    + (" e sua mensagem foi apagada da thread." if mensagens else ".")
                ),
                embed=None,
                view=None,
            )
