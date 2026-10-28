from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from comandos.ficha import sincronizar_publicacao_personagem, validar_tamanho_ficha
from utils.biblioteca import normalizar_rotulo
from utils.fichas import (
    ATRIBUTOS_POR_PERICIA,
    FichaPersonagem,
    ReferenciaFicha,
    encontrar_ficha,
    listar_fichas,
    modificador,
    nome_com_estado_pv,
    paginas_fichas_alfabeticas,
)
from utils.quadribol import (
    ARQUIVO_MANOBRAS,
    CONDICOES_QUADRIBOL,
    FORMACAO_PADRAO,
    INTENSIDADES_CONDICAO,
    JOGOS_TEMPORADA,
    PERFIS_SITUACIONAIS_POR_LINHA,
    POSICOES,
    POSICOES_RECOMENDADAS_POR_LINHA,
    PROGRESSO_POMO_NECESSARIO,
    SITUACOES_TIME,
    TIPOS_PARTIDA,
    TimeAmador,
    EventoPartida,
    FaltaQuadribol,
    ManobraQuadribol,
    PartidaQuadribol,
    RegistroFalta,
    ResultadoBalaco,
    ResultadoGol,
    ResultadoHabilidade,
    ResultadoFintaWronski,
    ResultadoPenalti,
    ResultadoPomo,
    ResultadoPosse,
    ResultadoResistenciaTempo,
    Vassoura,
    adicionar_condicao_catalogada,
    adicionar_gol,
    adicionar_manobra_biblioteca,
    artilheiros_ativos,
    atribuir_posse_goles,
    aplicar_beneficio_manobra,
    aplicar_resultado_na_taca,
    avancar_rodada,
    avancar_turno,
    avaliacao_linha_vassoura,
    bonus_posicao,
    carregar_faltas,
    carregar_times_amadores,
    carregar_manobras,
    casa_da_referencia,
    configurar_jogador,
    criar_partida,
    descricao_vassoura,
    desfazer_ultima_acao,
    encontrar_ficha_elegivel,
    encontrar_condicao,
    encontrar_jogador_partida,
    encontrar_partida_por_mensagem,
    encontrar_vassoura,
    executar_poeta,
    executar_rei,
    esta_atordoado,
    descricao_recomendacao_linha,
    faixa_preco_linha,
    habilidades_executaveis_quadribol,
    listar_fichas_elegiveis,
    linhas_vassouras,
    linhas_vassouras_por_preco,
    listar_vassouras,
    manobra_exige_coordenador,
    manobra_requer_finalizador,
    modelo_vassoura_da_descricao,
    obter_vassoura_ficha,
    obter_informacao,
    perseguir_pomo,
    perfil_linha_vassoura,
    preparar_acao,
    preparar_fortitude_tempo_externa,
    preparar_encerramento,
    progresso_necessario_pomo,
    progresso_necessario_por_velocidade,
    registrar_falta,
    reservas_disponiveis,
    remover_efeito,
    resolver_balaco,
    resolver_penalti,
    resolver_passe_goles,
    resolver_tomada_goles,
    resolver_finta_wronski,
    resolver_resistencia_tempo,
    resolver_tentativa_gol,
    rolar_manobra,
    salvar_partida,
    salvar_time_amador,
    testar_recuperacao,
    tem_tempo_meteorologico,
    total_pericia,
    validar_nova_manobra,
    velocidade_disparada,
    zona_fogo_ativa,
)
from utils.taca import CASAS, carregar_estado_taca, salvar_estado_taca
from utils.midia import aplicar_imagem, criar_arquivos_discord, resolver_anexo


COR_QUADRIBOL = 0x7A5C1E
GUILD_GRIMORY_ID = 935603393710424084
MENSAGEM_INDICE_MANOBRAS_ID = 1540854369208107071
THREAD_MANOBRAS_ID = MENSAGEM_INDICE_MANOBRAS_ID
GUIA_QUADRIBOL = (
    Path(__file__).resolve().parents[1]
    / "exports"
    / "quadribol"
    / "guia-jogadores-discord.md"
)
EMOJIS_CASAS = {
    "Grifinória": "❤️",
    "Sonserina": "💚",
    "Lufa-Lufa": "💛",
    "Corvinal": "💙",
}


def _texto_bonus(valor: int) -> str:
    return f"{valor:+d}"


def _texto_bonus_pontaria_vassoura(vassoura: Vassoura) -> str:
    valor = f"+{vassoura.dado_bonus_pontaria}" if vassoura.dado_bonus_pontaria else f"{vassoura.bonus_pontaria:+d}"
    if vassoura.uso_bonus_pontaria:
        valor += f" — {vassoura.uso_bonus_pontaria}"
    return valor


def formatar_cabecalho_vassoura(vassoura: Vassoura) -> str:
    linha = vassoura.linha or "Outras"
    return (
        "## ══════◄••🧹••►══════\n"
        f"## 🧹 {vassoura.nome}\n"
        f"_Linha {linha}_\n"
        "## ══════◄••🧹••►══════"
    )


def formatar_cabecalho_linha_vassouras(linha: str) -> str:
    return (
        "## ══════◄••🧹••►══════\n"
        f"## 🧹 {linha}\n"
        "_Linha de Vassouras_\n"
        "## ══════◄••🧹••►══════"
    )


def montar_embeds_vassoura(vassoura: Vassoura) -> list[discord.Embed]:
    avaliacao = vassoura.avaliacao_bastian or "Avaliação não informada."
    embed = discord.Embed(
        title=vassoura.nome,
        description=f'*"{avaliacao}"*\n**— Bastian Crowley**',
    )
    embed.add_field(
        name="Perfil:",
        value=vassoura.descricao or "--",
        inline=False,
    )
    embed.add_field(name="Pontos de Vida:", value=str(vassoura.vida_maxima), inline=True)
    embed.add_field(name="Velocidade:", value=vassoura.velocidade or "--", inline=True)
    embed.add_field(name="Custo:", value=vassoura.custo or "--", inline=True)
    embed.add_field(
        name="Especificações:",
        value="\n".join(vassoura.especificacoes) or "--",
        inline=False,
    )
    if vassoura.imagem_url:
        aplicar_imagem(embed, vassoura.imagem_url, f"vassoura-{vassoura.nome}")
    return [embed]


def anexos_vassoura(vassoura: Vassoura):
    if not vassoura.imagem_url:
        return []
    anexo = resolver_anexo(vassoura.imagem_url, f"vassoura-{vassoura.nome}")
    return [anexo] if anexo is not None else []


def montar_embed_linha_vassouras(linha: str) -> discord.Embed | None:
    avaliacao = avaliacao_linha_vassoura(linha)
    if not avaliacao:
        return None
    return discord.Embed(description=f'*"{avaliacao}"*')


def montar_publicacao_linha_vassouras(
    linha: str,
    modelos: list[Vassoura],
) -> tuple[str, list[discord.Embed]]:
    embeds: list[discord.Embed] = []
    apresentacao = montar_embed_linha_vassouras(linha)
    if apresentacao is not None:
        embeds.append(apresentacao)
    for modelo in modelos:
        embeds.extend(montar_embeds_vassoura(modelo))
    return formatar_cabecalho_linha_vassouras(linha), embeds


def embed_catalogo_vassouras() -> discord.Embed:
    linhas = linhas_vassouras_por_preco()
    embed = discord.Embed(
        title="🧹 Catálogo de Vassouras",
        description="Escolha uma linha e, em seguida, o modelo que deseja consultar.",
        color=COR_QUADRIBOL,
    )
    for linha, modelos in linhas.items():
        perfil = perfil_linha_vassoura(linha) or descricao_recomendacao_linha(linha)
        embed.add_field(
            name=linha,
            value=f"{perfil}\n*{faixa_preco_linha(modelos)}*",
            inline=False,
        )
    return embed


def embed_linha_vassouras(linha: str, modelos: list[Vassoura]) -> discord.Embed:
    embed = discord.Embed(
        title=f"🧹 Linha {linha}",
        description="Escolha o modelo cuja ficha completa deseja consultar.",
        color=COR_QUADRIBOL,
    )
    for modelo in modelos:
        embed.add_field(
            name=modelo.nome,
            value=f"{modelo.velocidade or '--'} • {modelo.custo or '--'} • {modelo.vida_maxima} PV",
            inline=True,
        )
    return embed


GRAUS_PERICIA = {0: "Inexperiente", 2: "Treinada", 4: "Expert", 6: "Mestre"}


def detalhar_total_pericia_campo(
    ficha: FichaPersonagem,
    nome: str,
    *,
    bonus_vassoura: int = 0,
    bonus_habilidade: int = 0,
) -> str:
    atributos = ATRIBUTOS_POR_PERICIA[nome]
    if len(atributos) != 1:
        raise ValueError(f"{nome} não possui um único atributo para detalhar.")
    atributo = atributos[0]
    bonus_atributo = modificador(ficha.atributos[atributo])
    treinamento = ficha.pericias.get(nome, 0)
    partes = [
        f"{bonus_atributo:+d} {atributo}",
        f"{treinamento:+d} {GRAUS_PERICIA.get(treinamento, 'Treinamento')}",
    ]
    if bonus_vassoura:
        partes.append(f"{bonus_vassoura:+d} Vassoura")
    if bonus_habilidade:
        partes.append(f"{bonus_habilidade:+d} Habilidade")
    total = bonus_atributo + treinamento + bonus_vassoura + bonus_habilidade
    return f"» **{nome}:** {' '.join(partes)} = **{total:+d} total**"


def detalhar_total_aptidao_campo(
    nome: str,
    valor: int,
    *,
    bonus_vassoura: int = 0,
    bonus_habilidade: int = 0,
) -> str:
    partes = [f"{valor:+d} Aptidão"]
    if bonus_vassoura:
        partes.append(f"{bonus_vassoura:+d} Vassoura")
    if bonus_habilidade:
        partes.append(f"{bonus_habilidade:+d} Habilidade")
    total = valor + bonus_vassoura + bonus_habilidade
    return f"» **{nome}:** {' '.join(partes)} = **{total:+d} total**"


def embed_previa_jogador(
    ficha: FichaPersonagem,
    posicao: str,
    situacao: str,
    vassoura: Vassoura,
) -> discord.Embed:
    embed = discord.Embed(
        title="🏟️ Inscrição no time de Quadribol",
        description="Confira as informações antes de atualizar a ficha.",
        color=COR_QUADRIBOL,
    )
    embed.add_field(name="Personagem", value=nome_com_estado_pv(ficha.nome, ficha.pv), inline=False)
    embed.add_field(name="Casa", value=ficha.casa, inline=True)
    embed.add_field(name="Posição", value=posicao, inline=True)
    embed.add_field(name="Situação no time", value=situacao, inline=True)
    resumo_vassoura = (
        f"**{vassoura.nome}** *{vassoura.linha}*\n"
        f"» **PV**: {vassoura.vida_maxima}\n"
        f"» **Velocidade**: {vassoura.velocidade}\n"
        f"» **Valor**: {vassoura.custo}"
    )
    embed.add_field(name="Vassoura", value=resumo_vassoura, inline=False)
    especificacoes = [
        f"» **Vôo: {vassoura.bonus_voo:+d}**",
        f"» **Reflexo: {vassoura.bonus_reflexo:+d}**",
        f"» **Fortitude: {vassoura.bonus_fortitude:+d}**",
        *(f"» {item}" for item in vassoura.especificacoes),
    ]
    if vassoura.bonus_pontaria or vassoura.dado_bonus_pontaria:
        especificacoes.insert(
            3,
            f"» **Pontaria: {_texto_bonus_pontaria_vassoura(vassoura)}**",
        )
    embed.add_field(
        name="Especificações da vassoura",
        value="\n".join(especificacoes)[:1024],
        inline=False,
    )
    embed.set_footer(text="Nada será salvo antes da confirmação.")
    return embed


def embed_registro_jogador(
    ficha: FichaPersonagem,
    posicao: str,
    situacao: str,
    vassoura: Vassoura,
    *,
    concluido: bool,
) -> discord.Embed:
    embed = embed_previa_jogador(ficha, posicao, situacao, vassoura)
    if concluido:
        embed.title = "✅ Inscrição no time concluída"
        embed.description = "O jogador foi registrado e sua ficha foi atualizada."
        embed.color = discord.Color.green()
        embed.set_footer(text="Inscrição concluída.")
    else:
        embed.title = "⏳ Registrando inscrição…"
        embed.description = "Aguarde enquanto a ficha do jogador é atualizada."
        embed.set_footer(text="Processando…")
    return embed


def embed_jogador_time(
    ficha: FichaPersonagem,
    posicao: str,
    situacao: str,
    vassoura: Vassoura,
) -> discord.Embed:
    teste_posicao, _ = bonus_posicao(ficha, posicao, vassoura)
    prodigio_ativo = any(
        normalizar_rotulo(efeito.get("nome", ""))
        == normalizar_rotulo("Prodígio do Quadribol")
        for efeito in ficha.efeitos_habilidades_ativos
    )
    bonus_habilidade_posicao = 2 if prodigio_ativo else 0
    linha_iniciativa = detalhar_total_pericia_campo(ficha, "Iniciativa")
    linha_pontaria = detalhar_total_pericia_campo(
        ficha,
        "Pontaria",
        bonus_habilidade=(bonus_habilidade_posicao if teste_posicao == "Pontaria" else 0),
    )
    linha_reflexo = detalhar_total_pericia_campo(
        ficha,
        "Reflexo",
        bonus_vassoura=vassoura.bonus_reflexo,
        bonus_habilidade=(bonus_habilidade_posicao if teste_posicao == "Reflexo" else 0),
    )
    linha_fortitude = detalhar_total_pericia_campo(
        ficha,
        "Fortitude",
        bonus_vassoura=vassoura.bonus_fortitude,
    )
    linha_voo = detalhar_total_aptidao_campo(
        "Vôo",
        ficha.aptidoes.get("Vôo", 0),
        bonus_vassoura=vassoura.bonus_voo,
        bonus_habilidade=(bonus_habilidade_posicao if teste_posicao == "Vôo" else 0),
    )
    linha_quadribol = detalhar_total_aptidao_campo(
        "Quadribol", ficha.aptidoes.get("Quadribol", 0)
    )
    bonus_vassoura = (
        f"Vôo {vassoura.bonus_voo:+d} • Reflexo {vassoura.bonus_reflexo:+d} • "
        f"Fortitude {vassoura.bonus_fortitude:+d}"
    )
    if vassoura.bonus_pontaria or vassoura.dado_bonus_pontaria:
        bonus_vassoura += f" • Pontaria {_texto_bonus_pontaria_vassoura(vassoura)}"
    texto_vassoura = (
        f"**{vassoura.nome}** *{vassoura.linha}*\n"
        f"» **Bônus:** {bonus_vassoura}\n"
        f"» **PV:** {vassoura.vida_maxima}\n"
        f"» **Velocidade:** {vassoura.velocidade}"
    )
    if vassoura.especificacoes:
        texto_vassoura += "\n" + "\n".join(
            f"» {especificacao}"
            for especificacao in vassoura.especificacoes
        )
    embed = discord.Embed(
        title=f"{EMOJIS_CASAS[ficha.casa]} {nome_com_estado_pv(ficha.nome, ficha.pv)}",
        description=f"**{posicao} • {situacao}**",
        color=COR_QUADRIBOL,
    )
    embed.add_field(name="Vassoura", value=texto_vassoura, inline=False)
    linhas_por_teste = {
        "Iniciativa": linha_iniciativa,
        "Pontaria": linha_pontaria,
        "Reflexo": linha_reflexo,
        "Fortitude": linha_fortitude,
        "Vôo": linha_voo,
        "Quadribol": linha_quadribol,
    }
    ordem_testes = ("Iniciativa", "Pontaria", "Reflexo", "Fortitude", "Vôo", "Quadribol")
    embed.add_field(
        name="Teste principal da posição",
        value=linhas_por_teste[teste_posicao],
        inline=False,
    )
    embed.add_field(
        name="Testes em campo",
        value="\n".join(
            linhas_por_teste[nome]
            for nome in ordem_testes
            if nome != teste_posicao
        ),
        inline=False,
    )
    habilidades_aplicaveis = []
    if any(
        normalizar_rotulo(nome) == normalizar_rotulo("Prodígio do Quadribol")
        for nome in ficha.especializacoes
    ):
        habilidades_aplicaveis.append(
            f"» **Prodígio do Quadribol — 2ph:** +2 em {teste_posicao}. "
            + ("**Ativo.**" if prodigio_ativo else "Disponível para ativação.")
        )
    embed.add_field(
        name="Habilidades aplicáveis",
        value="\n".join(habilidades_aplicaveis) or "--",
        inline=False,
    )
    embed.set_footer(text=f"Equipe da {ficha.casa}")
    return embed


def embed_vaga_time(casa: str, posicao: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"{EMOJIS_CASAS[casa]} --",
        description=f"**{posicao} • Titular**",
        color=COR_QUADRIBOL,
    )
    embed.add_field(name="Vassoura", value="--", inline=False)
    embed.add_field(name="Teste principal da posição", value="--", inline=False)
    embed.add_field(name="Testes em campo", value="--", inline=False)
    embed.add_field(name="Habilidades aplicáveis", value="--", inline=False)
    embed.set_footer(text=f"Equipe da {casa} • vaga não preenchida")
    return embed


def embeds_time(casa: str) -> list[discord.Embed]:
    if casa not in CASAS:
        raise ValueError("Casa inválida.")
    ordem_posicao = {posicao: indice for indice, posicao in enumerate(POSICOES)}
    catalogo = {
        normalizar_rotulo(modelo.nome): modelo
        for modelo in listar_vassouras()
    }
    registros: list[tuple[FichaPersonagem, str, str, Vassoura | None, str]] = []
    for referencia in listar_fichas_elegiveis():
        if casa_da_referencia(referencia) != casa:
            continue
        ficha = FichaPersonagem.carregar(referencia.caminho)
        posicao = obter_informacao(ficha, "Jogador de Quadribol")
        if posicao not in POSICOES:
            continue
        situacao = obter_informacao(ficha, "Situação no time") or "Titular"
        nome_vassoura = modelo_vassoura_da_descricao(
            obter_vassoura_ficha(ficha)
        )
        vassoura = (
            catalogo.get(normalizar_rotulo(nome_vassoura))
            if nome_vassoura
            else None
        )
        registros.append((ficha, posicao, situacao, vassoura, nome_vassoura))
    titulares = sorted(
        (item for item in registros if item[2] == "Titular"),
        key=lambda item: (ordem_posicao[item[1]], item[0].nome.casefold()),
    )
    reservas = sorted(
        (item for item in registros if item[2] != "Titular"),
        key=lambda item: (ordem_posicao[item[1]], item[0].nome.casefold()),
    )
    resultado: list[discord.Embed] = []

    def adicionar_jogador(
        registro: tuple[FichaPersonagem, str, str, Vassoura | None, str],
    ) -> None:
        ficha, posicao, situacao, vassoura, nome_vassoura = registro
        if vassoura is not None:
            resultado.append(embed_jogador_time(ficha, posicao, situacao, vassoura))
            return
        embed = discord.Embed(
            title=f"{EMOJIS_CASAS[casa]} {nome_com_estado_pv(ficha.nome, ficha.pv)}",
            description=f"**{posicao} • {situacao}**",
            color=COR_QUADRIBOL,
        )
        embed.add_field(
            name="Vassoura",
            value=(
                f"O modelo **{nome_vassoura}** não foi encontrado no catálogo."
                if nome_vassoura
                else "Nenhuma vassoura foi definida."
            ),
            inline=False,
        )
        embed.set_footer(text=f"Equipe da {casa} • cadastro incompleto")
        resultado.append(embed)

    for posicao, quantidade in FORMACAO_PADRAO.items():
        jogadores_posicao = [item for item in titulares if item[1] == posicao]
        for registro in jogadores_posicao:
            adicionar_jogador(registro)
        for _ in range(max(0, quantidade - len(jogadores_posicao))):
            resultado.append(embed_vaga_time(casa, posicao))
    for registro in reservas:
        adicionar_jogador(registro)
    return resultado


def lotes_embeds(embeds: list[discord.Embed]) -> list[list[discord.Embed]]:
    lotes: list[list[discord.Embed]] = []
    atual: list[discord.Embed] = []
    tamanho = 0
    for embed in embeds:
        if atual and (len(atual) == 10 or tamanho + len(embed) > 6000):
            lotes.append(atual)
            atual = []
            tamanho = 0
        atual.append(embed)
        tamanho += len(embed)
    if atual:
        lotes.append(atual)
    return lotes


class TimeAmadorModal(discord.ui.Modal):
    def __init__(self, view: "CriarTimeAmadorView"):
        super().__init__(title="Criar Time Amador")
        self.view_criacao = view
        self.nome = discord.ui.TextInput(label="Nome do time", min_length=2, max_length=80)
        self.add_item(self.nome)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        nome = str(self.nome.value).strip()
        self.view_criacao = CriarTimeAmadorView(interaction.user.id, self.view_criacao.cog, nome)
        await interaction.response.edit_message(
            content=None,
            embed=embed_rascunho_time_amador(self.view_criacao),
            view=self.view_criacao,
        )


class CriarTimeAmadorView(discord.ui.View):
    def __init__(self, usuario_id: int, cog: Quadribol, nome: str = "", descricao: str = ""):
        super().__init__(timeout=600)
        self.usuario_id = usuario_id
        self.cog = cog
        self.nome = nome
        self.descricao = descricao
        self.jogadores_configurados: dict[str, tuple[str, str]] = {}
        self._montar_controles()

    def _montar_controles(self) -> None:
        pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message("Este painel pertence a outro usuário.", ephemeral=True)
        return False

    @discord.ui.button(label="Novo Jogador", emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def novo_jogador(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            content="Escolha a faixa alfabética e depois a ficha que entrará no time.",
            embed=None,
            view=SelecionarFichaJogadorView(self.cog, self.usuario_id, "", time_view=self),
        )

    @discord.ui.button(label="Salvar time", style=discord.ButtonStyle.success, row=4)
    async def salvar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.nome:
            await interaction.response.send_message("Defina o nome do time primeiro.", ephemeral=True)
            return
        try:
            salvar_time_amador(TimeAmador(self.nome, self.jogadores_configurados, self.descricao))
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(f"Não foi possível salvar o time: {erro}", ephemeral=True)
            return
        await interaction.response.edit_message(content=f"✅ Time Amador **{self.nome}** criado com sete jogadores.", view=None)
        self.stop()


def embed_rascunho_time_amador(view: CriarTimeAmadorView) -> discord.Embed:
    linhas = []
    for posicao, quantidade in FORMACAO_PADRAO.items():
        ocupantes = [nome for nome, dados in view.jogadores_configurados.items() if dados[0] == posicao]
        nomes = ", ".join(ocupantes) if ocupantes else "-- vaga(s)"
        linhas.append(f"**{posicao} ({len(ocupantes)}/{quantidade})** — {nomes}")
    return discord.Embed(
        title=f"🏏 {view.nome or 'Novo Time Amador'}",
        description=(view.descricao or "Defina a escalação do time a partir das fichas da biblioteca.") + "\n\n" + "\n".join(linhas),
        color=COR_QUADRIBOL,
    )


class CentralTimesView(discord.ui.View):
    def __init__(self, usuario_id: int, cog: Quadribol):
        super().__init__(timeout=300)
        self.usuario_id = usuario_id
        self.cog = cog
        seletor = discord.ui.Select(
            placeholder="Escolha o que deseja fazer",
            options=[
                discord.SelectOption(
                    label="Consultar",
                    value="consultar",
                    emoji="🔎",
                    description="Localiza uma equipe das Casas ou um Time Amador.",
                ),
                discord.SelectOption(
                    label="Criar",
                    value="criar",
                    emoji="➕",
                    description="Inicia um novo Time Amador.",
                ),
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message("Este painel pertence a outro usuário.", ephemeral=True)
        return False

    async def selecionar(self, interaction: discord.Interaction) -> None:
        if self.seletor.values[0] == "consultar":
            await interaction.response.edit_message(content=None, embed=embed_consulta_times(), view=SelecionarCasaTimeView(self.usuario_id, self.cog))
            return
        await interaction.response.send_modal(TimeAmadorModal(CriarTimeAmadorView(self.usuario_id, self.cog)))


def embed_central_times() -> discord.Embed:
    return discord.Embed(
        title="🏏 Times de Quadribol",
        description="Escolha se deseja consultar uma equipe ou criar um novo Time Amador.",
        color=COR_QUADRIBOL,
    )


def embed_consulta_times() -> discord.Embed:
    return discord.Embed(
        title="🔎 Consultar equipe",
        description="Escolha uma das quatro Casas ou abra a pasta de Times Amadores.",
        color=COR_QUADRIBOL,
    )


def embed_tipo_partida() -> discord.Embed:
    return discord.Embed(
        title="🏟️ Nova partida de Quadribol",
        description="Escolha primeiro o formato da partida. Partidas Oficiais usam as Casas; partidas Amistosas usam Times Amadores.",
        color=COR_QUADRIBOL,
    )


def embed_configurar_partida(tipo_partida: str) -> discord.Embed:
    if tipo_partida == "Partida Amistosa":
        descricao = "Escolha os dois Times Amadores que disputarão a partida."
        titulo = "🎉 Partida Amistosa"
    else:
        descricao = "Escolha as duas Casas e o jogo da temporada."
        titulo = "🏆 Partida Oficial"
    return discord.Embed(title=titulo, description=descricao, color=COR_QUADRIBOL)


class EscolherTipoPartidaView(discord.ui.View):
    def __init__(self, cog: Quadribol, usuario_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.usuario_id = usuario_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message("Esta configuração pertence a outro moderador.", ephemeral=True)
        return False

    @discord.ui.button(label="Partida Oficial", emoji="🏆", style=discord.ButtonStyle.primary)
    async def oficial(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=None, embed=embed_configurar_partida("Partida Oficial"), view=ConfigurarPartidaView(self.cog, self.usuario_id, tipo_partida="Partida Oficial"))

    @discord.ui.button(label="Partida Amistosa", emoji="🎉", style=discord.ButtonStyle.success)
    async def amistosa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=None, embed=embed_configurar_partida("Partida Amistosa"), view=ConfigurarPartidaView(self.cog, self.usuario_id, tipo_partida="Partida Amistosa"))


class SelecionarTimeAmadorView(discord.ui.View):
    def __init__(self, usuario_id: int, cog: Quadribol | None = None):
        super().__init__(timeout=180)
        self.usuario_id = usuario_id
        self.cog = cog
        times = carregar_times_amadores()
        seletor = discord.ui.Select(
            placeholder="Escolha um Time Amador",
            options=[
                discord.SelectOption(label=time.nome[:100], value=time.nome, emoji="🏏")
                for time in times
            ][:25] or [discord.SelectOption(label="Nenhum time criado", value="__none")],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message("Este painel pertence a outro usuário.", ephemeral=True)
        return False

    async def selecionar(self, interaction: discord.Interaction) -> None:
        valor = self.seletor.values[0]
        if valor == "__none":
            await interaction.response.send_message("Ainda não há Times Amadores cadastrados.", ephemeral=True)
            return
        time = next(item for item in carregar_times_amadores() if item.nome == valor)
        embed = discord.Embed(title=f"🏏 {time.nome}", description=time.descricao or "Time Amador", color=COR_QUADRIBOL)
        embed.add_field(name="Jogadores", value="\n".join(f"{nome} — {dados[0]}" for nome, dados in time.jogadores.items()) or "--", inline=False)
        await interaction.response.edit_message(content=None, embed=embed, view=None)

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary, row=1)
    async def voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=None, embed=embed_consulta_times(), view=SelecionarCasaTimeView(self.usuario_id, self.cog))


class ResultadoTimeCasaView(discord.ui.View):
    def __init__(self, usuario_id: int, cog: Quadribol, casa: str):
        super().__init__(timeout=300)
        self.usuario_id = usuario_id
        self.cog = cog
        self.casa = casa

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message("Este painel pertence a outro usuário.", ephemeral=True)
        return False

    @discord.ui.button(label="Novo Jogador", style=discord.ButtonStyle.success)
    async def novo_jogador(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=f"**Casa:** {self.casa}\nEscolha a faixa alfabética e depois o jogador.", embeds=[], view=SelecionarFichaJogadorView(self.cog, self.usuario_id, self.casa))

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary)
    async def voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=None, embed=embed_consulta_times(), view=SelecionarCasaTimeView(self.usuario_id, self.cog))


class SelecionarCasaTimeView(discord.ui.View):
    def __init__(self, usuario_id: int, cog: Quadribol | None = None):
        super().__init__(timeout=180)
        self.usuario_id = usuario_id
        self.cog = cog
        seletor = discord.ui.Select(
            placeholder="Casa do time",
            options=[
                discord.SelectOption(
                    label=casa,
                    value=casa,
                    emoji=EMOJIS_CASAS.get(casa, "🏏"),
                    description=f"Visualizar a equipe da {casa}.",
                )
                for casa in CASAS
            ] + [discord.SelectOption(label="Time Amador", value="amador", emoji="🏏", description="Consultar times criados externamente.")],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message(
            "Este menu pertence a outro usuário.", ephemeral=True
        )
        return False

    async def selecionar(self, interaction: discord.Interaction) -> None:
        casa = self.seletor.values[0]
        if casa == "amador":
            await interaction.response.edit_message(content=None, embed=embed_consulta_times(), view=SelecionarTimeAmadorView(self.usuario_id, self.cog))
            return
        await interaction.response.defer()
        try:
            embeds = embeds_time(casa)
        except (OSError, ValueError) as erro:
            await interaction.edit_original_response(
                content=f"Não foi possível consultar o time: {erro}",
                embeds=[],
                view=None,
            )
            return
        lotes = lotes_embeds(embeds)
        self.stop()
        await interaction.edit_original_response(
            content=(
                f"{EMOJIS_CASAS[casa]} **Equipe de Quadribol da {casa}**\n"
                "Formação titular e reservas cadastrados."
            ),
            embeds=lotes[0],
            view=ResultadoTimeCasaView(self.usuario_id, self.cog, casa) if self.cog else None,
        )
        for lote in lotes[1:]:
            await interaction.followup.send(embeds=lote, ephemeral=True)


def _duracao_efeito(efeito) -> str:
    if efeito.duracao_tipo == "rodadas" and efeito.rodada_final:
        return f"até o fim da rodada {efeito.rodada_final}"
    if efeito.duracao_tipo == "partida":
        return "durante a partida"
    if efeito.duracao_tipo == "gatilho":
        return f"até {efeito.gatilho}" if efeito.gatilho else "até o gatilho"
    if efeito.duracao_tipo == "ciclo":
        return f"até o turno retornar a {efeito.gatilho}"
    if efeito.turnos_restantes:
        unidade = "turno restante" if efeito.turnos_restantes == 1 else "turnos restantes"
        return f"{efeito.turnos_restantes} {unidade}"
    return "ativo"


def _modificador_efeito(efeito) -> str:
    if efeito.dado_modificador:
        return efeito.dado_modificador
    if efeito.bonus:
        return f"{efeito.bonus:+d}"
    return ""


def _rotulo_efeito_ativo(efeito) -> str:
    detalhes: list[str] = []
    if efeito.intensidade:
        intensidade = efeito.intensidade
        if efeito.cd_resistencia:
            intensidade += f", CD {efeito.cd_resistencia}"
        detalhes.append(intensidade)
    elif efeito.cd_recuperacao:
        detalhes.append(f"Fortitude CD {efeito.cd_recuperacao}")
    detalhes.append(_duracao_efeito(efeito))
    modificador = _modificador_efeito(efeito)
    final = f" `{modificador}`" if modificador else ""
    return f"{efeito.nome} — {' • '.join(detalhes)}{final}"


def _linha_jogador(
    jogador,
    atual: bool = False,
    *,
    mostrar_efeitos: bool = True,
) -> str:
    marcador = "▶" if atual else "•"
    efeitos = ""
    if mostrar_efeitos and jogador.efeitos:
        efeitos = " — " + ", ".join(
            _rotulo_efeito_ativo(item) for item in jogador.efeitos
        )
    if mostrar_efeitos and jogador.penalidade_tempo_preparada is not None:
        efeitos += (
            " — Clima resistido: "
            + (
                "sem penalidade"
                if jogador.penalidade_tempo_preparada == 0
                else f"{jogador.penalidade_tempo_preparada:+d} na próxima ação"
            )
        )
    elif mostrar_efeitos and jogador.resultado_tempo_externo is not None:
        efeitos += (
            f" — Fortitude meteorológica externa "
            f"{jogador.resultado_tempo_externo} preparada"
        )
    if not jogador.ativo:
        efeitos += " — **fora de campo**"
    cartoes = ""
    if jogador.cartoes_amarelos:
        cartoes = f" | 🟨 {jogador.cartoes_amarelos}"
    if jogador.expulso:
        cartoes = " | 🟥 expulso"
    casa = f" da {jogador.casa}" if jogador.casa else ""
    emoji = EMOJIS_CASAS.get(jogador.casa, "")
    return (
        f"{marcador} {emoji} **{jogador.nome}** — {jogador.posicao}{casa} | "
        f"Inic. {jogador.iniciativa_total}{cartoes}{efeitos}"
    )


def _jogadores_priorizados(
    partida: PartidaQuadribol,
    jogadores=None,
) -> list:
    """Ordena seletores pelo contexto do turno sem alterar a ordem interna dos grupos."""
    candidatos = list(partida.jogadores if jogadores is None else jogadores)
    atual = partida.jogador_atual()
    if atual is None:
        return candidatos

    def prioridade(item) -> int:
        if item.nome == atual.nome:
            return 0
        if item.casa == atual.casa:
            return 1
        return 2

    return [
        item
        for _, item in sorted(
            enumerate(candidatos),
            key=lambda par: (prioridade(par[1]), par[0]),
        )
    ]


def _fixar_selecao(seletor: discord.ui.Select, valor: str) -> None:
    """Mantém visível no Discord a escolha única já guardada pelo fluxo."""
    for opcao in seletor.options:
        opcao.default = opcao.value == valor


def _linhas_efeitos_ativos(partida: PartidaQuadribol) -> list[str]:
    linhas: list[str] = []
    climas: dict[tuple[str, str, int, str, str], set[str]] = {}
    for jogador in partida.jogadores:
        for efeito in jogador.efeitos:
            if normalizar_rotulo(efeito.nome) != "tempo meteorologico":
                continue
            chave = (
                efeito.origem,
                efeito.intensidade,
                efeito.cd_resistencia,
                efeito.dado_modificador,
                _duracao_efeito(efeito),
            )
            climas.setdefault(chave, set()).add(jogador.casa)
    for (origem, intensidade, cd, modificador, duracao), casas in climas.items():
        if casas == set(partida.casas()):
            afetados = "Ambas as equipes"
        else:
            afetados = " e ".join(
                f"{EMOJIS_CASAS.get(casa, '')} **{casa}**"
                for casa in partida.casas()
                if casa in casas
            )
        contexto = origem.split("—", 1)[1].strip() if "—" in origem else ""
        detalhes = [item for item in (contexto, intensidade) if item]
        if cd:
            detalhes.append(f"Fortitude CD {cd}")
        detalhes.append(duracao)
        bonus = f" `{modificador}`" if modificador else ""
        linhas.append(
            f"🌦️ **Tempo Meteorológico — {afetados}**\n"
            f"» {' • '.join(detalhes)}{bonus}"
        )

    atual = partida.jogador_atual()
    ordenados = ([atual] if atual is not None else []) + [
        jogador
        for jogador in partida.jogadores
        if atual is None or jogador.nome != atual.nome
    ]
    for jogador in ordenados:
        efeitos = [
            efeito
            for efeito in jogador.efeitos
            if normalizar_rotulo(efeito.nome) != "tempo meteorologico"
        ]
        if not efeitos and jogador.resultado_tempo_externo is None:
            continue
        detalhes = [f"» {_rotulo_efeito_ativo(efeito)}" for efeito in efeitos]
        if jogador.resultado_tempo_externo is not None:
            detalhes.append(
                "» Fortitude meteorológica externa preparada "
                f"`{jogador.resultado_tempo_externo}`"
            )
        linhas.append(
            f"{EMOJIS_CASAS.get(jogador.casa, '')} **{jogador.nome}**\n"
            + "\n".join(detalhes)
        )
    return linhas


def embed_placar_partida(partida: PartidaQuadribol) -> discord.Embed:
    casa_1, casa_2 = partida.casas()
    placar_1, placar_2 = partida.placar(casa_1), partida.placar(casa_2)
    return discord.Embed(
        title=f"🏆 {partida.jogo} de Quadribol • {partida.tipo_partida} • {partida.tempo}º tempo",
        description=(
            f"## {EMOJIS_CASAS.get(casa_1, '🏏')} **{casa_1} {placar_1} × {placar_2} "
            f"{casa_2}** {EMOJIS_CASAS.get(casa_2, '🏏')}\n"
            f"**Gols: {partida.gols[casa_1]} × {partida.gols[casa_2]}**"
        ),
        color=COR_QUADRIBOL,
    )


def embed_partida(partida: PartidaQuadribol) -> discord.Embed:
    descricao: list[str] = []
    if partida.pomos:
        descricao.append(
            " • ".join(
                f"Pomo do lado de {lado}: **{capturou}**"
                for lado, capturou in partida.pomos.items()
            )
        )
    if partida.vencedor_forcado:
        descricao.append(
            f"**{partida.vencedor_forcado}** venceu por falta eliminatória."
        )
    embed = discord.Embed(
        description="\n".join(descricao) or None,
        color=COR_QUADRIBOL,
    )
    if partida.posse_goles:
        try:
            portador_goles = encontrar_jogador_partida(partida, partida.posse_goles)
            texto_posse = (
                f"{EMOJIS_CASAS.get(portador_goles.casa, '')} **{portador_goles.nome}** — "
                f"{portador_goles.posicao} da {portador_goles.casa}"
            )
        except ValueError:
            texto_posse = f"**{partida.posse_goles}**"
    elif partida.reposicao_goles_casa:
        texto_posse = (
            "Aguardando um Artilheiro da "
            f"**{partida.reposicao_goles_casa}** receber a Goles após o impacto do Balaço."
        )
    else:
        texto_posse = "Aguardando reposição."
    bonus_passes = 0
    casa_posse = ""
    if partida.posse_goles:
        try:
            casa_posse = encontrar_jogador_partida(partida, partida.posse_goles).casa
            bonus_passes = partida.bonus_passes_gol.get(casa_posse, 0)
        except ValueError:
            pass
    if bonus_passes:
        texto_posse += (
            f"\n🎯 **Sequência de passes de {casa_posse}:** "
            f"{bonus_passes:+d} no próximo arremesso"
        )
    embed.add_field(name="🏐 Posse da Goles", value=texto_posse, inline=False)
    ativos = partida.pomos_ativos()
    if ativos:
        pomo_lado = ativos[0]
        linhas_progresso = []
        progresso_atual = partida.progresso_pomos.get(pomo_lado, {})
        for casa in partida.casas():
            apanhador = next(
                (
                    item
                    for item in partida.jogadores
                    if item.casa == casa and item.posicao == "Apanhador" and item.em_campo
                ),
                None,
            )
            meta = progresso_necessario_pomo(apanhador) if apanhador else PROGRESSO_POMO_NECESSARIO
            velocidade = (
                f" • 🧹 {apanhador.velocidade_vassoura}m/s"
                if apanhador and apanhador.velocidade_vassoura
                else ""
            )
            disparada = velocidade_disparada(apanhador) if apanhador else 0
            if disparada:
                usada = apanhador.nome in partida.disparadas_pomo.get(pomo_lado, [])
                velocidade += (
                    f" • Disparada {disparada}m/s "
                    + (
                        "(já usada neste Pomo)"
                        if usada
                        else "(pode ser usada no próprio turno)"
                    )
                )
            linhas_progresso.append(
                f"{EMOJIS_CASAS.get(casa, '🏏')} **{casa}: "
                f"{progresso_atual.get(casa, 0)}/{meta}**{velocidade}"
            )
        embed.add_field(
            name=f"🟡 Pomo atual — lado de {pomo_lado}",
            value="\n".join(linhas_progresso),
            inline=False,
        )
    else:
        lado_tempo = partida.casa_1 if partida.tempo == 1 else partida.casa_2
        if partida.estado == "intervalo":
            situacao_pomo = "Intervalo: não há Pomo em campo."
        elif lado_tempo in partida.pomos:
            situacao_pomo = (
                f"O Pomo do {partida.tempo}º tempo já foi capturado. "
                "O jogo continua até o fim do tempo."
            )
        elif partida.estado == "ativa":
            situacao_pomo = "O Pomo ainda não surgiu."
        else:
            situacao_pomo = "O tempo da partida foi encerrado."
        embed.add_field(
            name="🟡 Pomos de Ouro",
            value=situacao_pomo,
            inline=False,
        )
    if partida.penalti_casa:
        embed.add_field(
            name="🚨 Pênalti pendente",
            value=(
                f"**{partida.penalti_casa}** cobrará pela falta "
                f"**{partida.penalti_motivo}**."
            ),
            inline=False,
        )

    atual = partida.jogador_atual()
    if atual is not None:
        estado = (
            f"**Rodada {partida.rodada_tempo} do {partida.tempo}º tempo**\n"
            f"{_linha_jogador(atual, True, mostrar_efeitos=False)}\n"
            f"Fortitude {_texto_bonus(atual.fortitude)} • Quadribol {_texto_bonus(atual.quadribol)} • "
            f"Vôo {_texto_bonus(atual.voo)}"
        )
        if atual.posicao == "Artilheiro":
            estado += (
                f"\nPontaria {_texto_bonus(atual.bonus_teste_posicao)} • "
                f"Reflexo {_texto_bonus(atual.reflexo)} • "
                f"Atletismo {_texto_bonus(atual.atletismo)}"
                + (f" ({atual.atributo_atletismo})" if atual.atributo_atletismo else "")
            )
        embed.add_field(name="Turno atual", value=estado, inline=False)

    titulares = partida.jogadores_em_iniciativa()
    indices_iniciativa = {
        jogador.nome: indice
        for indice, jogador in enumerate(titulares, start=1)
    }
    nomes_preparados = set(partida.acoes_preparadas)
    if partida.acoes_preparadas:
        titulo_preparadas = (
            "⏳ Ações preparadas em execução: prioridade antes da iniciativa normal desta rodada."
            if partida.executando_acoes_preparadas
            else "⏳ Ações preparadas para a próxima rodada"
        )
        linhas_preparadas = [
            f"`{indices_iniciativa[nome]:02d}` "
            f"{_linha_jogador(encontrar_jogador_partida(partida, nome), mostrar_efeitos=False)}"
            for nome in partida.acoes_preparadas
            if nome in indices_iniciativa
        ]
        embed.add_field(
            name=titulo_preparadas,
            value="\n".join(linhas_preparadas),
            inline=False,
        )

    linhas_efeitos = _linhas_efeitos_ativos(partida)
    if linhas_efeitos:
        _adicionar_resumo_fragmentado(
            embed,
            "⏳ Efeitos e condições ativos",
            linhas_efeitos,
            "",
        )

    iniciativa_visivel = [
        (indice, jogador)
        for indice, jogador in enumerate(titulares, start=1)
        if not (
            partida.executando_acoes_preparadas
            and jogador.nome in nomes_preparados
        )
    ]
    ordem_completa = "\n".join(
        f"`{indice:02d}` {_linha_jogador(jogador, mostrar_efeitos=False)}"
        for indice, jogador in enumerate(titulares, start=1)
    )
    if len(ordem_completa) > 1024:
        metade = (len(titulares) + 1) // 2
        blocos = (
            [(indice, jogador) for indice, jogador in iniciativa_visivel if indice <= metade],
            [(indice, jogador) for indice, jogador in iniciativa_visivel if indice > metade],
        )
        for numero, bloco in enumerate(blocos, start=1):
            embed.add_field(
                name=f"Ordem de iniciativa {numero}/2",
                value="\n".join(
                    f"`{indice:02d}` {_linha_jogador(jogador, mostrar_efeitos=False)}"
                    for indice, jogador in bloco
                ) or "--",
                inline=False,
            )
    else:
        embed.add_field(
            name="Ordem de iniciativa",
            value=(
                "\n".join(
                    f"`{indice:02d}` {_linha_jogador(jogador, mostrar_efeitos=False)}"
                    for indice, jogador in iniciativa_visivel
                )
                or "--"
            ),
            inline=False,
        )

    goleiros = [
        item
        for item in partida.jogadores
        if item.em_campo and item.ativo and item.posicao == "Goleiro"
    ]
    embed.add_field(
        name="🧤 Goleiros em espera",
        value=(
            "\n".join(
                f"{EMOJIS_CASAS.get(item.casa, '')} **{item.nome}** — "
                f"Goleiro da {item.casa} | Reflexo {_texto_bonus(item.reflexo)}"
                for item in goleiros
            )
            or "--"
        ),
        inline=False,
    )

    reservas = [
        item for item in partida.jogadores
        if item.situacao == "Reserva" and not item.em_campo and not item.expulso
    ]
    if reservas:
        embed.add_field(
            name="Reservas disponíveis",
            value="\n".join(
                f"• {EMOJIS_CASAS.get(item.casa, '')} **{item.nome}** — "
                f"{item.posicao} da {item.casa}"
                for item in reservas
            )[:1024],
            inline=False,
        )

    recentes = partida.eventos[-5:]
    embed.add_field(
        name="Acontecimentos recentes",
        value=(
            "\n".join(f"• {item.descricao}" for item in reversed(recentes))
            if recentes
            else "--"
        ),
        inline=False,
    )
    rodape = {
        "ativa": "Partida em andamento.",
        "intervalo": "Intervalo da partida.",
        "aguardando_confirmacao": "Resultado definido: confira e confirme o encerramento.",
        "encerrada": "Partida encerrada.",
    }.get(partida.estado, partida.estado)
    embed.set_footer(text=rodape)
    return embed


def embeds_partida(partida: PartidaQuadribol) -> list[discord.Embed]:
    return [embed_placar_partida(partida), embed_partida(partida)]


def _adicionar_resumo_fragmentado(
    embed: discord.Embed,
    titulo: str,
    linhas: list[str],
    vazio: str,
) -> None:
    if not linhas:
        embed.add_field(name=titulo, value=vazio, inline=False)
        return
    blocos: list[str] = []
    atual = ""
    for linha in linhas:
        trecho = linha[:1000]
        candidato = f"{atual}\n{trecho}" if atual else trecho
        if len(candidato) > 1024:
            blocos.append(atual)
            atual = trecho
        else:
            atual = candidato
    if atual:
        blocos.append(atual)
    for indice, bloco in enumerate(blocos, start=1):
        nome = titulo if indice == 1 else f"{titulo} — continuação {indice}"
        embed.add_field(name=nome, value=bloco, inline=False)


def embed_resultado_partida(partida: PartidaQuadribol) -> discord.Embed:
    casa_1, casa_2 = partida.casas()
    placar_1, placar_2 = partida.placar(casa_1), partida.placar(casa_2)
    vencedor = partida.vencedor()
    resultado = (
        f"**Vitória da {vencedor}.**"
        if vencedor
        else "**A partida terminou empatada.**"
    )
    embed = discord.Embed(
        title=f"🏆 Resultado Final • {partida.jogo} • {partida.tipo_partida}",
        description=(
            f"{EMOJIS_CASAS.get(casa_1, '🏏')} **{casa_1} {placar_1} × {placar_2} {casa_2}** "
            f"{EMOJIS_CASAS.get(casa_2, '🏏')}\n"
            f"Gols: **{partida.gols[casa_1]} × {partida.gols[casa_2]}** • "
            f"Pomos: **{partida.capturas_pomo(casa_1)} × "
            f"{partida.capturas_pomo(casa_2)}**\n{resultado}"
        ),
        color=COR_QUADRIBOL,
    )
    jogadas_placar: list[str] = []
    faltas: list[str] = []
    penaltis: list[str] = []
    adversidades_meteorologicas: list[str] = []
    for evento in partida.eventos:
        if (
            evento.tipo == "efeito"
            and normalizar_rotulo(evento.descricao).startswith("tempo meteorologico")
        ):
            adversidades_meteorologicas.append(f"• {evento.descricao}")
        if evento.tipo == "gol" and evento.valor > 0:
            jogadas_placar.append(f"• 🥅 **Gol (+10):** {evento.descricao}")
        elif evento.tipo == "pomo":
            jogadas_placar.append(f"• 🟡 **Pomo capturado (+150):** {evento.descricao}")
        elif evento.tipo == "penalti":
            penaltis.append(f"• {evento.descricao}")
            if evento.valor > 0:
                jogadas_placar.append(
                    f"• 🚨 **Pênalti convertido (+10):** {evento.descricao}"
                )
        if evento.tipo == "falta":
            faltas.append(f"• {evento.descricao}")
    if adversidades_meteorologicas:
        _adicionar_resumo_fragmentado(
            embed,
            "🌦️ Adversidade meteorológica",
            adversidades_meteorologicas,
            "",
        )
    _adicionar_resumo_fragmentado(
        embed,
        "📈 Jogadas que alteraram o placar",
        jogadas_placar,
        "Nenhum gol ou Pomo foi registrado.",
    )
    _adicionar_resumo_fragmentado(
        embed,
        "🚨 Faltas registradas",
        faltas,
        "Nenhuma falta foi registrada.",
    )
    _adicionar_resumo_fragmentado(
        embed,
        "🥅 Pênaltis",
        penaltis,
        "Nenhum pênalti foi cobrado.",
    )
    if partida.tipo_partida == "Partida Oficial":
        embed.add_field(
            name="🏅 Pontos concedidos à Taça das Casas",
            value="\n".join(
                f"{EMOJIS_CASAS.get(casa, '🏏')} **{casa}: +{partida.pontos_taca(casa)}**"
                for casa in partida.casas()
            ),
            inline=False,
        )
        embed.set_footer(text="Resultado confirmado e aplicado à Taça das Casas.")
    else:
        embed.add_field(name="Partida Amistosa", value="O resultado não altera a Taça das Casas.", inline=False)
    return embed


def _formatar_fontes_rolagem(fontes: tuple[str, ...], total: int) -> str:
    if not fontes:
        return f"**Total: {total}**"
    return "\n".join(f"`{fonte}`" for fonte in fontes) + f"\n**Total: {total}**"


def embed_resultado_pomo(resultado: ResultadoPomo, partida: PartidaQuadribol) -> discord.Embed:
    apanhador = encontrar_jogador_partida(partida, resultado.jogador)
    titulo = "🟡 Pomo de Ouro capturado!" if resultado.capturou else "🟡 Perseguição ao Pomo"
    descricao = (
        f"O Pomo está no lado de **{resultado.pomo_lado}**.\n"
        f"**{resultado.jogador}** mantém a perseguição"
        + (
            f" com a **Disparada de {resultado.velocidade_considerada}m/s**"
            if resultado.usou_disparada
            else ""
        )
        + (
            ".\n" + _formatar_fontes_rolagem(resultado.fontes, resultado.total) + "\n"
        )
        + f"Progresso de **{apanhador.casa}**: "
        f"**{resultado.progresso_anterior} → {resultado.progresso_atual}/"
        f"{resultado.necessario}**."
    )
    if resultado.capturou:
        descricao += "\n\nO Apanhador alcança a bola dourada e garante **150 pontos esportivos**."
        if partida.tempo == 1:
            descricao += (
                " O próximo Pomo só poderá surgir no lado oposto durante o "
                "**2º tempo**, após o intervalo."
            )
        else:
            descricao += " O jogo continua até o fim do tempo."
    return discord.Embed(
        title=titulo,
        description=descricao,
        color=0xFEE75C,
    )


def embed_surgimento_pomo(partida: PartidaQuadribol, lado: str) -> discord.Embed:
    return discord.Embed(
        title="🟡 O POMO SURGIU!!!",
        description=(
            f"Na **rodada {partida.rodada_tempo} do {partida.tempo}º tempo**, "
            f"o brilho dourado aparece no lado de **{lado}**.\n\n"
            "Os Apanhadores já podem iniciar a perseguição."
        ),
        color=0xFEE75C,
    )


def embed_resultado_balaco(resultado: ResultadoBalaco, partida: PartidaQuadribol) -> discord.Embed:
    linhas = [
        f"**{resultado.atacante} — ataque**\n"
        + _formatar_fontes_rolagem(resultado.fontes_ataque, resultado.total_ataque),
        f"**{resultado.defensor} — defesa**\n"
        + _formatar_fontes_rolagem(resultado.fontes_defesa, resultado.total_defesa),
    ]
    if resultado.redirecionou:
        novo_alvo = encontrar_jogador_partida(partida, resultado.alvo_redirecionado)
        linhas.append(
            "\nA defesa superou a rebatida por pelo menos **5** e devolveu o Balaço "
            f"contra **{resultado.alvo_redirecionado}**."
        )
        linhas.append(
            f"**{resultado.alvo_redirecionado}** tenta desviar: "
            "\n" + _formatar_fontes_rolagem(
                resultado.fontes_reflexo_redirecionado,
                resultado.total_reflexo_redirecionado,
            )
        )
        if resultado.atingiu_redirecionado:
            estado = (
                f"{novo_alvo.vida_vassoura}/{novo_alvo.vida_vassoura_maxima} de Vida"
                + (" — **Quebrada**" if novo_alvo.vassoura_quebrada else "")
            )
            linhas.append(
                f"\nO Balaço redirecionado atingiu **{resultado.alvo_redirecionado}**. "
                f"A vassoura ficou com **{estado}**."
            )
            linhas.append(
                "**Fortitude**\n"
                + _formatar_fontes_rolagem(resultado.fontes_fortitude, resultado.total_fortitude)
                + f"\n**CD {resultado.cd_fortitude}**"
            )
            if resultado.resistiu:
                linhas.append("O jogador suportou o impacto e pode continuar normalmente.")
                cor = 0xFEE75C
                titulo = "↩️ Contra-ataque resistido"
            else:
                linhas.append("O jogador ficou **Atordoado por 2 turnos próprios**.")
                cor = 0xED4245
                titulo = "↩️ Contra-ataque certeiro"
        else:
            linhas.append("\nO novo alvo desviou e evitou o Balaço redirecionado.")
            cor = 0x57F287
            titulo = "↩️ Balaço redirecionado e evitado"
    elif not resultado.atingiu:
        linhas.append("\nA defesa igualou ou superou o ataque, e o balaço foi evitado.")
        cor = 0x57F287
        titulo = "🛡️ Balaço evitado"
    else:
        alvo = encontrar_jogador_partida(partida, resultado.alvo)
        estado = (
            f"{alvo.vida_vassoura}/{alvo.vida_vassoura_maxima} de Vida"
            + (" — **Quebrada**" if alvo.vassoura_quebrada else "")
        )
        linhas.append(
            f"\nO balaço atingiu **{resultado.alvo}**. "
            f"A vassoura ficou com **{estado}**."
        )
        linhas.append(
            "**Fortitude**\n"
            + _formatar_fontes_rolagem(resultado.fontes_fortitude, resultado.total_fortitude)
            + f"\n**CD {resultado.cd_fortitude}**"
        )
        if resultado.resistiu:
            linhas.append("O jogador suportou o impacto e pode continuar normalmente.")
            cor = 0xFEE75C
            titulo = "💥 Impacto resistido"
        else:
            linhas.append("O jogador ficou **Atordoado por 2 turnos próprios**.")
            if resultado.progresso_perdido:
                linhas.append(
                    f"A perseguição ao Pomo foi interrompida e perdeu "
                    f"**{resultado.progresso_perdido}** de progresso."
                )
            cor = 0xED4245
            titulo = "💥 Balaço certeiro"
    if resultado.zona_fogo:
        linhas.insert(
            0,
            "**Zona de Fogo:** o ataque usa a média dos bônus de Pontaria dos dois "
            "Batedores; a esquiva direta sofre **-2 em Reflexo**.\n",
        )
    if resultado.zona_fogo_encerrada:
        linhas.append(
            "\nA interceptação do Batedor adversário encerrou a **Zona de Fogo**."
        )
    if resultado.posse_perdida_por:
        linhas.append(
            f"\n🏐 **{resultado.posse_perdida_por} perdeu a posse da Goles.** "
            f"Escolha um Artilheiro da **{resultado.casa_nova_posse}** para recebê-la."
        )
    return discord.Embed(title=titulo, description="\n".join(linhas), color=cor)


def embed_resultado_recuperacao(
    jogador: str,
    condicao: str,
    fontes: tuple[str, ...],
    total: int,
    cd: int,
    sucesso: bool,
) -> discord.Embed:
    if sucesso:
        titulo = "✅ Recuperação bem-sucedida"
        desfecho = (
            f"**{jogador} superou o Atordoamento.**\n"
            "A condição foi removida e o jogador pode agir normalmente neste turno."
        )
        cor = 0x57F287
    else:
        titulo = "❌ Recuperação malsucedida"
        desfecho = (
            f"**{jogador} permanece Atordoado.**\n"
            "O turno foi encerrado automaticamente; uma nova recuperação poderá ser "
            "tentada no próximo turno próprio."
        )
        cor = 0xED4245
    return discord.Embed(
        title=titulo,
        description=(
            f"**Condição:** {condicao}\n\n"
            f"**Fortitude contra CD {cd}**\n"
            f"{_formatar_fontes_rolagem(fontes, total)}\n\n"
            f"{desfecho}"
        ),
        color=cor,
    )


def embed_falta(registro: RegistroFalta) -> discord.Embed:
    cartao = {
        "Nenhum": "Sem cartão",
        "Amarelo": "🟨 Cartão amarelo",
        "Vermelho": "🟥 Cartão vermelho",
    }[registro.cartao_aplicado]
    linhas = [
        registro.falta.descricao,
        f"\n**Infrator:** {registro.infrator}",
        f"**Punição:** {cartao}",
    ]
    if registro.falta.consequencia == "Pênalti":
        linhas.append(
            f"**Consequência:** a jogada é interrompida e **{registro.casa_prejudicada}** "
            "recebe uma cobrança direta: Artilheiro contra Goleiro."
        )
    else:
        linhas.append(
            f"**Consequência:** **{registro.casa_prejudicada}** vence automaticamente a partida."
        )
    if registro.reserva:
        linhas.append(f"**Substituição imediata:** {registro.reserva} entra na mesma posição e iniciativa.")
    elif registro.cartao_aplicado == "Vermelho":
        linhas.append("**Substituição:** não há reserva disponível; a equipe segue sem essa posição.")
    return discord.Embed(
        title=f"🚨 Falta: {registro.falta.nome}",
        description="\n".join(linhas),
        color=0xED4245,
    )


def embed_resultado_penalti(resultado: ResultadoPenalti) -> discord.Embed:
    if resultado.gol:
        titulo = "🥅 Pênalti convertido"
        desfecho = f"**{resultado.artilheiro}** vence o duelo e marca o gol."
        cor = 0x57F287
    else:
        titulo = "🧤 Pênalti defendido"
        desfecho = f"**{resultado.goleiro}** iguala ou supera a cobrança e impede o gol."
        cor = 0x5865F2
    ataque = _formatar_fontes_rolagem(
        resultado.fontes_artilheiro,
        resultado.total_artilheiro,
    )
    defesa = _formatar_fontes_rolagem(
        resultado.fontes_goleiro,
        resultado.total_goleiro,
    )
    return discord.Embed(
        title=titulo,
        description=(
            "A partida para. Os demais jogadores se afastam, deixando a cobrança direta.\n\n"
            f"**Artilheiro — {resultado.artilheiro}**\n{ataque}\n\n"
            f"**Goleiro — {resultado.goleiro}**\n{defesa}\n\n"
            + desfecho
        ),
        color=cor,
    )


def embed_resultado_gol(resultado: ResultadoGol) -> discord.Embed:
    if resultado.gol:
        titulo = "🥅 Gol!"
        desfecho = (
            f"**{resultado.goleiro}** foi enganado pelo Mergulho do Falcão e perdeu "
            f"a chance de defesa. **{resultado.artilheiro}** marca o gol."
            if resultado.mergulho_falcao and not resultado.passou_percepcao
            else f"**{resultado.artilheiro}** supera a defesa e marca o gol."
        )
        cor = 0x57F287
    else:
        titulo = "🧤 Defesa do Goleiro"
        desfecho = f"**{resultado.goleiro}** iguala ou supera o arremesso e impede o gol."
        cor = 0x5865F2
    ataque = _formatar_fontes_rolagem(
        resultado.fontes_artilheiro,
        resultado.total_artilheiro,
    )
    defesa = _formatar_fontes_rolagem(
        resultado.fontes_goleiro,
        resultado.total_goleiro,
    )
    percepcao = ""
    if resultado.mergulho_falcao:
        percepcao = (
            "**Percepção contra o Mergulho do Falcão**\n"
            + _formatar_fontes_rolagem(
                resultado.fontes_percepcao,
                resultado.total_percepcao,
            )
            + f"\n**CD {resultado.cd_percepcao:g}** — "
            + (
                "o Goleiro identificou o verdadeiro portador."
                if resultado.passou_percepcao
                else "o Goleiro foi enganado e perdeu a defesa."
            )
            + "\n\n"
        )
    return discord.Embed(
        title=titulo,
        description=(
            f"**Artilheiro — {resultado.artilheiro}**\n{ataque}\n\n"
            f"{percepcao}"
            f"**Goleiro — {resultado.goleiro}**\n{defesa}\n\n"
            f"{desfecho}"
        ),
        color=cor,
    )


class ConfigurarJogadorView(discord.ui.View):
    def __init__(
        self,
        cog: Quadribol,
        referencia: ReferenciaFicha,
        usuario_id: int,
        *,
        posicao: str = "",
        situacao: str = "",
        linha: str = "",
        vassoura: str = "",
        time_view: "CriarTimeAmadorView | None" = None,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.referencia = referencia
        self.usuario_id = usuario_id
        self.time_view = time_view
        ficha = FichaPersonagem.carregar(referencia.caminho)
        posicao_atual = obter_informacao(ficha, "Jogador de Quadribol")
        situacao_atual = obter_informacao(ficha, "Situação no time")
        nome_vassoura = modelo_vassoura_da_descricao(obter_vassoura_ficha(ficha))
        vassoura_atual = encontrar_vassoura(nome_vassoura) if nome_vassoura else None
        modelos = listar_vassouras()
        if not modelos:
            raise ValueError(
                "O catálogo de vassouras ainda está vazio. Cadastre os modelos reais antes de inscrever jogadores."
            )
        self.vassouras = {item.nome: item for item in modelos}
        self.catalogo = linhas_vassouras(modelos)
        self.posicao = posicao or (posicao_atual if posicao_atual in POSICOES else "")
        self.situacao = situacao or (
            situacao_atual if situacao_atual in SITUACOES_TIME else ""
        )
        self.linha = linha or (vassoura_atual.linha if vassoura_atual else "")
        self.vassoura = vassoura or (
            vassoura_atual.nome
            if vassoura_atual and vassoura_atual.linha == self.linha
            else ""
        )

        posicoes = discord.ui.Select(
            placeholder="Posição do jogador",
            options=[
                discord.SelectOption(
                    label=item,
                    value=item,
                    default=item == self.posicao,
                )
                for item in POSICOES
            ],
            row=0,
        )
        situacoes = discord.ui.Select(
            placeholder="Situação no time",
            options=[
                discord.SelectOption(
                    label=item,
                    value=item,
                    description=(
                        "Começa a partida em campo."
                        if item == "Titular"
                        else "Entra quando um jogador da mesma posição for substituído."
                    ),
                    default=item == self.situacao,
                )
                for item in SITUACOES_TIME
            ],
            row=1,
        )
        linhas = discord.ui.Select(
            placeholder="Linha da vassoura",
            options=[
                discord.SelectOption(
                    label=nome[:100],
                    value=nome[:100],
                    description=descricao_recomendacao_linha(nome)[:100],
                    default=nome == self.linha,
                )
                for nome, itens in sorted(
                    self.catalogo.items(),
                    key=lambda item: (
                        0
                        if self.posicao
                        in POSICOES_RECOMENDADAS_POR_LINHA.get(item[0], ())
                        else 1
                        if item[0] in PERFIS_SITUACIONAIS_POR_LINHA
                        else 2,
                        item[0].casefold(),
                    ),
                )
            ],
            row=2,
        )

        async def selecionar(interaction: discord.Interaction, atributo: str, valor: str) -> None:
            setattr(self, atributo, valor)
            await interaction.response.defer()

        async def selecionar_posicao(interaction: discord.Interaction) -> None:
            await interaction.response.edit_message(
                view=ConfigurarJogadorView(
                    self.cog,
                    self.referencia,
                    self.usuario_id,
                    posicao=posicoes.values[0],
                    situacao=self.situacao,
                    linha=self.linha,
                    vassoura=self.vassoura,
                    time_view=self.time_view,
                )
            )

        posicoes.callback = selecionar_posicao
        situacoes.callback = lambda interaction: selecionar(
            interaction, "situacao", situacoes.values[0]
        )
        async def selecionar_linha(interaction: discord.Interaction) -> None:
            await interaction.response.edit_message(
                view=ConfigurarJogadorView(
                    self.cog,
                    self.referencia,
                    self.usuario_id,
                    posicao=self.posicao,
                    situacao=self.situacao,
                    linha=linhas.values[0],
                )
            )

        linhas.callback = selecionar_linha
        self.add_item(posicoes)
        self.add_item(situacoes)
        self.add_item(linhas)
        if self.linha in self.catalogo:
            modelos_linha = self.catalogo[self.linha]
            vassouras = discord.ui.Select(
                placeholder=f"Modelo — {self.linha}",
                options=[
                    discord.SelectOption(
                        label=item.nome[:100],
                        value=item.nome[:100],
                        description=(
                            f"Vôo {item.bonus_voo:+d} • Reflexo {item.bonus_reflexo:+d} • "
                            f"{item.vida_maxima} PV • {item.velocidade} • {item.custo}"
                        )[:100],
                        default=item.nome == self.vassoura,
                    )
                    for item in modelos_linha
                ],
                row=3,
            )
            vassouras.callback = lambda interaction: selecionar(
                interaction, "vassoura", vassouras.values[0]
            )
            self.add_item(vassouras)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.usuario_id:
            await interaction.response.send_message(
                "Esta configuração pertence a outro moderador.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Revisar inscrição", style=discord.ButtonStyle.success, row=4)
    async def revisar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.posicao or not self.situacao or not self.vassoura:
            await interaction.response.send_message(
                "Escolha a posição, a situação no time, a linha e o modelo da vassoura.", ephemeral=True
            )
            return
        referencia = encontrar_ficha(
            self.referencia.caminho.relative_to(self.referencia.caminho.parents[1]).as_posix()
        )
        if referencia is None:
            await interaction.response.send_message(
                "A ficha escolhida não está mais disponível.", ephemeral=True
            )
            return
        ficha = FichaPersonagem.carregar(referencia.caminho)
        modelo = self.vassouras[self.vassoura]
        self.stop()
        await interaction.response.edit_message(
            content=None,
            embed=embed_previa_jogador(ficha, self.posicao, self.situacao, modelo),
            view=(ConfirmarJogadorTimeView(
                self.time_view,
                referencia,
                self.posicao,
                self.situacao,
                modelo,
                self.usuario_id,
            ) if self.time_view is not None else ConfirmarJogadorView(
                self.cog,
                referencia,
                self.posicao,
                self.situacao,
                modelo,
                self.usuario_id,
            )),
        )


class SelecionarFichaJogadorView(discord.ui.View):
    def __init__(
        self,
        cog: Quadribol,
        usuario_id: int,
        casa: str,
        pagina: int = 0,
        time_view: "CriarTimeAmadorView | None" = None,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.usuario_id = usuario_id
        self.casa = casa
        self.time_view = time_view
        # A inscrição deve permitir qualquer ficha da pasta escolhida, não
        # apenas fichas que já tenham os campos de Quadribol preenchidos.
        referencias_por_caminho = {
            item.caminho: item
            for item in listar_fichas()
            if item.grupo != "Criaturas"
        }
        # Mantém referências de fichas com a Casa definida no próprio arquivo
        # (pasta Players), além das fichas que estão na pasta da Casa.
        referencias_por_caminho.update(
            {
                item.caminho: item
                for item in listar_fichas_elegiveis()
                if item.grupo != "Criaturas"
            }
        )
        referencias = [
            item for item in referencias_por_caminho.values()
            if not casa or casa_da_referencia(item) == casa or item.grupo == casa
        ]
        self.paginas = paginas_fichas_alfabeticas(referencias)
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        rotulo, fichas = self.paginas[self.pagina]
        self.fichas = fichas
        referencias_elegiveis = {
            item.caminho for item in listar_fichas_elegiveis()
        }
        self.jogadores = [
            item for item in fichas if item.caminho in referencias_elegiveis
        ]  # compatibilidade com integrações antigas
        faixas = discord.ui.Select(
            placeholder=f"Faixa alfabética — {rotulo}",
            options=[
                discord.SelectOption(
                    label=nome,
                    value=str(indice),
                    description=(
                        f"{len(itens)} ficha(s) nesta faixa."
                        if itens
                        else "Faixa sem fichas nesta pasta."
                    ),
                    default=indice == self.pagina,
                )
                for indice, (nome, itens) in enumerate(self.paginas)
            ],
            row=0,
        )
        faixas.callback = self.selecionar_faixa
        self.faixas = faixas
        self.add_item(faixas)
        if fichas:
            seletor = discord.ui.Select(
                placeholder=(f"Fichas da {casa} — {rotulo}" if casa else f"Fichas da biblioteca — {rotulo}"),
                options=[
                    discord.SelectOption(
                        label=item.nome[:100],
                        value=item.caminho.relative_to(item.caminho.parents[1]).as_posix()[:100],
                    )
                    for item in fichas
                ],
                row=1,
            )
            seletor.callback = self.selecionar_jogador
            self.seletor = seletor
            self.add_item(seletor)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.usuario_id:
            await interaction.response.send_message(
                "Esta seleção pertence a outro moderador.", ephemeral=True
            )
            return False
        return True

    async def selecionar_faixa(self, interaction: discord.Interaction) -> None:
        pagina = int(self.faixas.values[0])
        rotulo, fichas = self.paginas[pagina]
        await interaction.response.edit_message(
            content=(
                    f"**{'Casa: ' + self.casa if self.casa else 'Fichas da biblioteca'}** • **Faixa:** {rotulo}\n"
                + (
                    "Escolha a ficha que será inscrita."
                    if fichas
                    else "Esta faixa ainda não possui fichas. Escolha outra."
                )
            ),
            view=SelecionarFichaJogadorView(
                self.cog, self.usuario_id, self.casa, pagina, self.time_view
            ),
        )

    async def selecionar_jogador(self, interaction: discord.Interaction) -> None:
        referencia = encontrar_ficha(self.seletor.values[0])
        if referencia is None or referencia.grupo == "Criaturas" or (self.casa and referencia.grupo != self.casa):
            await interaction.response.send_message(
                "A ficha escolhida não está mais disponível nesta casa.", ephemeral=True
            )
            return
        try:
            proxima = ConfigurarJogadorView(self.cog, referencia, self.usuario_id, time_view=self.time_view)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(
            content=f"**Jogador:** {referencia.nome}\nDefina a posição e a vassoura que serão usadas no time.",
            view=proxima,
        )

    @discord.ui.button(label="Voltar às casas", style=discord.ButtonStyle.secondary, row=2)
    async def voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        if self.time_view is not None:
            await interaction.response.edit_message(content=None, embed=embed_rascunho_time_amador(self.time_view), view=self.time_view)
            return
        await interaction.response.edit_message(
            content="Escolha a casa do jogador.",
            view=SelecionarCasaJogadorView(self.cog, self.usuario_id),
        )


class SelecionarCasaJogadorView(discord.ui.View):
    def __init__(self, cog: Quadribol, usuario_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.usuario_id = usuario_id
        seletor = discord.ui.Select(
            placeholder="Casa do jogador",
            options=[
                discord.SelectOption(
                    label=casa,
                    value=casa,
                    emoji=EMOJIS_CASAS.get(casa, "🏏"),
                    description=f"Consultar os jogadores da {casa}.",
                )
                for casa in CASAS
            ],
        )
        seletor.callback = self.selecionar_casa
        self.seletor = seletor
        self.add_item(seletor)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.usuario_id:
            await interaction.response.send_message(
                "Esta seleção pertence a outro moderador.", ephemeral=True
            )
            return False
        return True

    async def selecionar_casa(self, interaction: discord.Interaction) -> None:
        casa = self.seletor.values[0]
        self.stop()
        await interaction.response.edit_message(
            content=f"**Casa:** {casa}\nEscolha a faixa alfabética e depois o jogador.",
            view=SelecionarFichaJogadorView(self.cog, self.usuario_id, casa),
        )


class ConfirmarJogadorTimeView(discord.ui.View):
    def __init__(self, time_view: CriarTimeAmadorView, referencia: ReferenciaFicha, posicao: str, situacao: str, vassoura: Vassoura, usuario_id: int):
        super().__init__(timeout=300)
        self.time_view = time_view
        self.referencia = referencia
        self.posicao = posicao
        self.situacao = situacao
        self.vassoura = vassoura
        self.usuario_id = usuario_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message("Esta confirmação pertence a outro usuário.", ephemeral=True)
        return False

    @discord.ui.button(label="Confirmar jogador", style=discord.ButtonStyle.success, emoji="✅")
    async def confirmar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        ficha = FichaPersonagem.carregar(self.referencia.caminho)
        self.time_view.jogadores_configurados[ficha.nome] = (self.posicao, self.vassoura.nome)
        await interaction.response.edit_message(content=None, embed=embed_rascunho_time_amador(self.time_view), view=self.time_view)
        self.stop()

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary)
    async def voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Escolha a posição e a vassoura do jogador.", embed=None, view=ConfigurarJogadorView(self.time_view.cog, self.referencia, self.usuario_id, time_view=self.time_view))


class ConfirmarJogadorView(discord.ui.View):
    def __init__(
        self,
        cog: Quadribol,
        referencia: ReferenciaFicha,
        posicao: str,
        situacao: str,
        vassoura: Vassoura,
        usuario_id: int,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.referencia = referencia
        self.posicao = posicao
        self.situacao = situacao
        self.vassoura = vassoura
        self.usuario_id = usuario_id
        self.finalizada = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.usuario_id:
            await interaction.response.send_message("Esta confirmação pertence a outro moderador.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, emoji="✅")
    async def confirmar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.finalizada:
            await interaction.response.send_message("Esta operação já foi concluída.", ephemeral=True)
            return
        self.finalizada = True
        ficha_previa = FichaPersonagem.carregar(self.referencia.caminho)
        await interaction.response.edit_message(
            content=None,
            embed=embed_registro_jogador(
                ficha_previa,
                self.posicao,
                self.situacao,
                self.vassoura,
                concluido=False,
            ),
            view=None,
        )
        try:
            referencia = encontrar_ficha_elegivel(
                self.referencia.caminho.relative_to(self.referencia.caminho.parents[1]).as_posix()
            )
            if referencia is None:
                raise ValueError("A ficha selecionada não está mais disponível.")
            async with self.cog.bloqueio_jogadores:
                ficha = configurar_jogador(
                    referencia,
                    self.posicao,
                    self.vassoura,
                    situacao=self.situacao,
                    salvar=False,
                )
                validar_tamanho_ficha(ficha)
                ficha = configurar_jogador(
                    referencia,
                    self.posicao,
                    self.vassoura,
                    situacao=self.situacao,
                    salvar=True,
                )
            await sincronizar_publicacao_personagem(interaction, ficha, referencia.caminho)
        except (OSError, ValueError) as erro:
            self.finalizada = False
            await interaction.edit_original_response(content=f"Não foi possível inscrever o jogador: {erro}", embed=None, view=None)
            return
        self.stop()
        await interaction.edit_original_response(
            content=None,
            embed=embed_registro_jogador(
                ficha,
                self.posicao,
                self.situacao,
                self.vassoura,
                concluido=True,
            ),
            view=None,
        )

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            content=None,
            embed=None,
            view=ConfigurarJogadorView(
                self.cog,
                self.referencia,
                self.usuario_id,
                posicao=self.posicao,
                situacao=self.situacao,
                linha=self.vassoura.linha,
                vassoura=self.vassoura.nome,
            ),
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.finalizada = True
        self.stop()
        await interaction.response.edit_message(content="Inscrição cancelada.", embed=None, view=None)


class RolagemExternaModal(discord.ui.Modal):
    def __init__(self, rotulo: str, ao_confirmar):
        super().__init__(title="Rolagem Externa")
        self.ao_confirmar = ao_confirmar
        self.resultado = discord.ui.TextInput(
            label=rotulo[:45],
            placeholder="Digite somente o total final. Ex.: 18",
            min_length=1,
            max_length=3,
        )
        self.add_item(self.resultado)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        texto = str(self.resultado.value).strip()
        if not texto.isdigit():
            await interaction.response.send_message(
                "Digite somente números inteiros no resultado final.",
                ephemeral=True,
            )
            return
        await self.ao_confirmar(interaction, int(texto))


class RolagensOpostasModal(discord.ui.Modal):
    def __init__(
        self,
        rotulo_atacante: str,
        rotulo_defensor: str,
        ao_confirmar,
        *,
        titulo: str = "Resultados Externos — Disputa",
        ajuda_atacante: str = "Digite o resultado total da primeira ação",
        ajuda_defensor: str = "Digite o resultado total da resposta",
    ):
        super().__init__(title=titulo[:45])
        self.ao_confirmar = ao_confirmar
        self.atacante = discord.ui.TextInput(
            label=rotulo_atacante[:45],
            placeholder=ajuda_atacante[:100],
            min_length=1,
            max_length=3,
        )
        self.defensor = discord.ui.TextInput(
            label=rotulo_defensor[:45],
            placeholder=ajuda_defensor[:100],
            min_length=1,
            max_length=3,
        )
        self.add_item(self.atacante)
        self.add_item(self.defensor)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        atacante = str(self.atacante.value).strip()
        defensor = str(self.defensor.value).strip()
        if not atacante.isdigit() or not defensor.isdigit():
            await interaction.response.send_message(
                "Digite somente números inteiros nos dois resultados finais.",
                ephemeral=True,
            )
            return
        await self.ao_confirmar(interaction, int(atacante), int(defensor))


class DefesaFintaExternaModal(discord.ui.Modal):
    def __init__(self, ao_confirmar):
        super().__init__(title="Rolagem Externa — Finta de Wronski")
        self.ao_confirmar = ao_confirmar
        self.voo = discord.ui.TextInput(
            label="Total de Voo contra CD 18",
            placeholder="Resultado final do Apanhador adversário",
            min_length=1,
            max_length=3,
        )
        self.fortitude = discord.ui.TextInput(
            label="Fortitude CD 15 se colidir",
            placeholder="Opcional; o bot rola se ficar vazio",
            required=False,
            max_length=3,
        )
        self.add_item(self.voo)
        self.add_item(self.fortitude)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        voo = str(self.voo.value).strip()
        fortitude = str(self.fortitude.value).strip()
        if not voo.isdigit() or (fortitude and not fortitude.isdigit()):
            await interaction.response.send_message(
                "Digite somente números inteiros nos resultados finais.", ephemeral=True
            )
            return
        await self.ao_confirmar(
            interaction, int(voo), int(fortitude) if fortitude else None
        )


class DefesaMergulhoExternaModal(discord.ui.Modal):
    def __init__(self, ao_confirmar):
        super().__init__(title="Rolagem Externa — Mergulho")
        self.ao_confirmar = ao_confirmar
        self.percepcao = discord.ui.TextInput(
            label="Total de Percepção",
            placeholder="Digite o total final da Percepção",
            min_length=1,
            max_length=3,
        )
        self.reflexo = discord.ui.TextInput(
            label="Total de Reflexo se passar",
            placeholder="Opcional se a Percepção falhar",
            required=False,
            max_length=3,
        )
        self.add_item(self.percepcao)
        self.add_item(self.reflexo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        percepcao = str(self.percepcao.value).strip()
        reflexo = str(self.reflexo.value).strip()
        if not percepcao.isdigit() or (reflexo and not reflexo.isdigit()):
            await interaction.response.send_message(
                "Digite somente números inteiros nos resultados finais.",
                ephemeral=True,
            )
            return
        await self.ao_confirmar(
            interaction,
            int(reflexo) if reflexo else None,
            int(percepcao),
        )


class ManobraView(discord.ui.View):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(timeout=180)
        self.cog = cog
        self.partida_id = partida.identificador
        self.nome_manobra = ""
        self.coordenador = ""
        self.finalizador = ""
        atual = partida.jogador_atual()
        if atual is None or not atual.ativo or not atual.em_campo:
            raise ValueError("Não há jogador ativo no turno atual.")
        self.manobras = [
            manobra
            for manobra in carregar_manobras()
            if (not manobra.posicoes or atual.posicao in manobra.posicoes)
            and atual.quadribol >= manobra.requisito_quadribol
        ]
        if not self.manobras:
            raise ValueError(
                f"{atual.nome} não possui manobras compatíveis com {atual.posicao} "
                f"e Quadribol {atual.quadribol:+d}."
            )
        self.jogador_turno = atual.nome
        self.casa_turno = atual.casa
        manobras = discord.ui.Select(
            placeholder="Manobra",
            options=[
                discord.SelectOption(
                    label=item.nome[:100],
                    value=item.nome,
                    description=(
                        f"{'Execução automática' if item.cd == 0 else f'CD {item.cd}'} "
                        f"• requisito {item.requisito_quadribol:+d} Quadribol"
                    ),
                )
                for item in self.manobras[:25]
            ],
            row=0,
        )
        coordenadores = discord.ui.Select(
            placeholder="Escolha a manobra primeiro",
            options=[discord.SelectOption(label="Escolha a manobra primeiro", value="-")],
            disabled=True,
            row=1,
        )
        finalizadores = discord.ui.Select(
            placeholder="Escolha uma manobra com arremesso final",
            options=[
                discord.SelectOption(
                    label="A manobra selecionada não exige finalizador",
                    value="-",
                )
            ],
            disabled=True,
            row=2,
        )

        async def escolher_manobra(interaction: discord.Interaction) -> None:
            self.nome_manobra = manobras.values[0]
            self.coordenador = ""
            self.finalizador = ""
            for opcao in manobras.options:
                opcao.default = opcao.value == self.nome_manobra
            manobra = next(item for item in self.manobras if item.nome == self.nome_manobra)
            for seletor in (coordenadores, finalizadores):
                if seletor in self.children:
                    self.remove_item(seletor)
            if not manobra_exige_coordenador(manobra):
                self.coordenador = atual.nome
                compativel = not manobra.posicoes or atual.posicao in manobra.posicoes
                requisito = atual.quadribol >= manobra.requisito_quadribol
                detalhes = [atual.posicao, f"Quadribol {atual.quadribol:+d}"]
                if not compativel:
                    detalhes.append("posição incompatível")
                elif not requisito:
                    detalhes.append("requisito insuficiente")
                coordenadores.placeholder = "Executor da manobra individual"
                coordenadores.options = [
                    discord.SelectOption(
                        label=atual.nome[:100],
                        value=atual.nome,
                        description=" • ".join(detalhes)[:100],
                        default=True,
                    )
                ]
                coordenadores.disabled = True
            else:
                elegiveis = _jogadores_priorizados(partida, [
                    item
                    for item in partida.jogadores
                    if item.casa == atual.casa
                    and item.ativo
                    and item.em_campo
                    and (not manobra.posicoes or item.posicao in manobra.posicoes)
                    and item.quadribol >= manobra.requisito_quadribol
                ])
                coordenadores.placeholder = "Coordenador da manobra"
                coordenadores.options = (
                    [
                        discord.SelectOption(
                            label=item.nome[:100],
                            value=item.nome,
                            description=f"{item.posicao} • Quadribol {item.quadribol:+d}",
                        )
                        for item in elegiveis[:25]
                    ]
                    or [
                        discord.SelectOption(
                            label="Nenhum participante atende aos requisitos",
                            value="-",
                        )
                    ]
                )
                coordenadores.disabled = not elegiveis
                self.add_item(coordenadores)
            if manobra_requer_finalizador(manobra):
                elegiveis_finalizacao = _jogadores_priorizados(partida, [
                    item
                    for item in partida.jogadores
                    if item.casa == atual.casa
                    and item.posicao == "Artilheiro"
                    and item.ativo
                    and item.em_campo
                ])
                finalizadores.placeholder = (
                    "Artilheiro que realizará o bote"
                    if normalizar_rotulo(manobra.nome) == "resgate em gangorra"
                    else "Artilheiro do arremesso final"
                )
                finalizadores.options = [
                    discord.SelectOption(
                        label=item.nome[:100],
                        value=item.nome,
                        description=f"{item.casa} • {item.posicao}"[:100],
                    )
                    for item in elegiveis_finalizacao[:25]
                ]
                finalizadores.disabled = not elegiveis_finalizacao
                self.add_item(finalizadores)
            else:
                finalizadores.placeholder = "Esta manobra não exige finalizador"
                finalizadores.options = [
                    discord.SelectOption(
                        label="Benefício sem arremesso final selecionável",
                        value="-",
                    )
                ]
                finalizadores.disabled = True
            await interaction.response.edit_message(
                embed=embed_detalhe_manobra(manobra),
                view=self,
            )

        async def escolher_coordenador(interaction: discord.Interaction) -> None:
            self.coordenador = coordenadores.values[0]
            for opcao in coordenadores.options:
                opcao.default = opcao.value == self.coordenador
            await interaction.response.edit_message(view=self)

        async def escolher_finalizador(interaction: discord.Interaction) -> None:
            self.finalizador = finalizadores.values[0]
            for opcao in finalizadores.options:
                opcao.default = opcao.value == self.finalizador
            await interaction.response.edit_message(view=self)

        manobras.callback = escolher_manobra
        coordenadores.callback = escolher_coordenador
        finalizadores.callback = escolher_finalizador
        self.add_item(manobras)
        voltar = discord.ui.Button(
            label="Voltar",
            emoji="↩️",
            style=discord.ButtonStyle.secondary,
            row=4,
        )
        voltar.callback = self.voltar_acoes
        self.add_item(voltar)

    async def voltar_acoes(self, interaction: discord.Interaction) -> None:
        partida, _ = self.cog._localizar_por_id(self.partida_id)
        self.stop()
        await interaction.response.edit_message(
            content=None,
            embed=_embed_painel_acao(
                partida,
                "⚡ Ações do Turno",
                "Escolha a ação do jogador em destaque.",
            ),
            view=AcoesTurnoView(self.cog, partida),
        )

    @discord.ui.button(label="Executar manobra", style=discord.ButtonStyle.primary, row=3)
    async def executar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._executar(interaction)

    @discord.ui.button(label="Rolagem Externa", style=discord.ButtonStyle.secondary, row=3)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.nome_manobra or not self.coordenador:
            await interaction.response.send_message(
                "Escolha a manobra e, se ela for coletiva, o Coordenador da manobra.",
                ephemeral=True,
            )
            return
        manobra = next(item for item in self.manobras if item.nome == self.nome_manobra)
        if manobra.cd == 0:
            await interaction.response.send_message(
                "Esta formação não exige rolagem de execução; use **Executar manobra**.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            RolagemExternaModal("Total do teste da manobra", self._executar)
        )

    async def _executar(
        self,
        interaction: discord.Interaction,
        resultado_externo: int | None = None,
    ) -> None:
        if not self.nome_manobra or not self.coordenador:
            await interaction.response.send_message(
                "Escolha a manobra e, se ela for coletiva, o Coordenador da manobra.",
                ephemeral=True,
            )
            return
        manobra = next(item for item in self.manobras if item.nome == self.nome_manobra)
        if manobra_requer_finalizador(manobra) and not self.finalizador:
            acao_final = (
                "realizará o bote"
                if normalizar_rotulo(manobra.nome) == "resgate em gangorra"
                else "realizará o arremesso final"
            )
            await interaction.response.send_message(
                f"Escolha o Artilheiro que {acao_final}.",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        resultado: tuple[int, int, bool] | None = None
        eventos_turno: list[EventoPartida] = []
        beneficio_aplicado = ""
        fontes_rolagem: list[str] = []
        finta_pendente = normalizar_rotulo(manobra.nome) == "finta de wronski"

        def acao(partida: PartidaQuadribol) -> None:
            nonlocal resultado, beneficio_aplicado
            resultado = rolar_manobra(
                partida,
                manobra,
                self.coordenador,
                resultado_externo=resultado_externo,
                fontes=fontes_rolagem,
            )
            if resultado[2] and not finta_pendente:
                beneficio_aplicado = aplicar_beneficio_manobra(
                    partida,
                    manobra,
                    self.coordenador,
                    finalizador=self.finalizador,
                )
            if not (resultado[2] and finta_pendente):
                inicio = len(partida.eventos)
                avancar_turno(partida)
                eventos_turno.extend(partida.eventos[inicio:])

        try:
            partida = await self.cog.mutar_partida(self.partida_id, acao)
            if not (resultado is not None and resultado[2] and finta_pendente):
                await self.cog.atualizar_mensagem(partida)
                await self.cog.publicar_surgimentos(partida, eventos_turno)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.edit_original_response(
                content=f"Não foi possível executar a manobra: {erro}",
                embed=None,
                view=self,
            )
            return
        assert resultado is not None
        dado, total, sucesso = resultado
        self.stop()
        embed = discord.Embed(
            title=f"{'✅' if sucesso else '❌'} {manobra.nome}",
            description=(
                (
                    f"**{self.coordenador}** organizou a formação automaticamente, "
                    "sem teste de execução.\n\n"
                    if manobra.cd == 0
                    else (
                        f"**{self.coordenador}** "
                        + (
                            f"apresentou a conta `{' + '.join(fontes_rolagem)} = {total}`"
                            if resultado_externo is not None
                            else f"rolou `{' + '.join(fontes_rolagem)} = {total}`"
                        )
                        + f" contra **CD {manobra.cd}**.\n\n"
                    )
                )
                + (
                    f"**Benefício:** {manobra.beneficio}\n\n"
                    f"**Aplicação automática:** {beneficio_aplicado}"
                    if sucesso
                    else "A coordenação da manobra falhou."
                )
            ),
            color=0x57F287 if sucesso else 0xED4245,
        )
        if sucesso and finta_pendente:
            embed.add_field(
                name="Próxima etapa",
                value=(
                    "O Apanhador adversário deve realizar **Voo CD 18** para frear ou "
                    "desviar antes de atingir o chão."
                ),
                inline=False,
            )
            alvo_finta = next(
                item
                for item in partida.jogadores
                if item.casa != self.casa_turno
                and item.posicao == "Apanhador"
                and item.ativo
                and item.em_campo
            )
            view_finta = DefesaFintaWronskiView(
                self.cog,
                partida,
                self.coordenador,
            )
            if await exigir_resistencia_tempo(
                interaction,
                self.cog,
                partida,
                alvo_finta,
                "reagir à Finta de Wronski",
                view_finta,
                self,
            ):
                return
            await interaction.edit_original_response(
                content=None,
                embed=embed,
                view=view_finta,
            )
        else:
            await interaction.edit_original_response(
                content=None,
                embed=embed,
                view=PainelResultadoView(self.cog, partida),
            )


def embed_resultado_finta(resultado: ResultadoFintaWronski) -> discord.Embed:
    voo = _formatar_fontes_rolagem(resultado.fontes_voo, resultado.total_voo)
    if resultado.evitou_colisao:
        desfecho = (
            f"**{resultado.alvo}** alcança a CD 18, corrige a trajetória e evita o chão."
        )
    else:
        fortitude = _formatar_fontes_rolagem(
            resultado.fontes_fortitude, resultado.total_fortitude
        )
        desfecho = (
            f"**{resultado.alvo}** falha no Voo e colide com o solo. Seu próximo turno "
            "será pulado automaticamente.\n\n"
            f"**Fortitude contra CD 15**\n{fortitude}\n\n"
        )
        if resultado.resistiu_impacto:
            desfecho += "Resiste ao impacto; não há dano adicional."
        else:
            desfecho += (
                f"**Dano concussivo destacado:** 1d6 ({resultado.dado_dano}) + 4 = "
                f"**{resultado.dano_concussivo}**. A ficha não foi alterada.\n"
                f"**Vassoura na partida:** -{resultado.pv_vassoura_perdido} PV."
            )
    return discord.Embed(
        title="🧹 Finta de Wronski",
        description=(
            f"**Voo — {resultado.alvo}**\n{voo}\n\n{desfecho}"
        ),
        color=0x5865F2 if resultado.evitou_colisao else 0xED4245,
    )


class DefesaFintaWronskiView(discord.ui.View):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol, executor: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.partida_id = partida.identificador
        self.executor = executor

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        membro = interaction.user
        if isinstance(membro, discord.Member) and membro.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message(
            "Você precisa da permissão **Gerenciar servidor** para controlar a partida.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Resolver Voo", style=discord.ButtonStyle.primary)
    async def resolver(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._resolver(interaction)

    @discord.ui.button(label="Rolagem Externa", style=discord.ButtonStyle.secondary)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(DefesaFintaExternaModal(self._resolver))

    async def _resolver(
        self,
        interaction: discord.Interaction,
        resultado_voo_externo: int | None = None,
        resultado_fortitude_externo: int | None = None,
    ) -> None:
        await interaction.response.defer()
        resultado: ResultadoFintaWronski | None = None
        eventos_turno: list[EventoPartida] = []

        def acao(item: PartidaQuadribol) -> None:
            nonlocal resultado
            resultado = resolver_finta_wronski(
                item,
                self.executor,
                resultado_voo_externo=resultado_voo_externo,
                resultado_fortitude_externo=resultado_fortitude_externo,
            )
            inicio = len(item.eventos)
            avancar_turno(item)
            eventos_turno.extend(item.eventos[inicio:])

        try:
            partida = await self.cog.mutar_partida(self.partida_id, acao)
            await self.cog.atualizar_mensagem(partida)
            await self.cog.publicar_surgimentos(partida, eventos_turno)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.edit_original_response(
                content=f"Não foi possível resolver a Finta de Wronski: {erro}",
                embed=None,
                view=self,
            )
            return
        assert resultado is not None
        self.stop()
        await interaction.edit_original_response(
            content=None,
            embed=embed_resultado_finta(resultado),
            view=PainelResultadoView(self.cog, partida),
        )


class BalacoView(discord.ui.View):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(timeout=180)
        self.cog = cog
        self.partida_id = partida.identificador
        atacante_atual = partida.jogador_atual()
        if (
            atacante_atual is None
            or atacante_atual.posicao != "Batedor"
            or not atacante_atual.ativo
            or not atacante_atual.em_campo
        ):
            raise ValueError("Somente o Batedor em destaque pode iniciar um ataque com Balaço.")
        self.atacante = atacante_atual.nome
        self.alvo = ""
        self.tipo = "normal"
        self.parceiro = ""
        self._alvos_normais = [
            item
            for item in _jogadores_priorizados(partida)
            if item.ativo and item.em_campo and item.casa != atacante_atual.casa
        ]
        self._alvos_zona = [
            item
            for item in _jogadores_priorizados(partida)
            if item.ativo
            and item.em_campo
            and item.nome != atacante_atual.nome
            and not (
                item.casa == atacante_atual.casa
                and item.posicao == "Batedor"
                and zona_fogo_ativa(partida, item)
            )
        ]
        self._parceiros = _jogadores_priorizados(partida, [
            item for item in partida.jogadores
            if item.ativo
            and item.em_campo
            and item.posicao == "Batedor"
            and item.casa == atacante_atual.casa
            and item.nome != atacante_atual.nome
        ])
        alvo = discord.ui.Select(
            placeholder="Jogador atingido",
            options=[
                discord.SelectOption(
                    label=item.nome,
                    value=item.nome,
                    description=f"{item.casa} • {item.posicao}",
                )
                for item in self._alvos_normais
            ][:25],
            row=0,
        )
        tipo = discord.ui.Select(
            placeholder="Tipo de rebatida",
            options=[
                discord.SelectOption(label="Balaço comum", value="normal", description="Recuperação: CD 12 + Força do atacante"),
                discord.SelectOption(label="Rebate Duplo", value="duplo", description="Recuperação: CD 14 + maior Força"),
            ]
            + (
                [
                    discord.SelectOption(
                        label="Zona de Fogo",
                        value="zona",
                        description="Média da Pontaria dos dois Batedores • Reflexo -2",
                    )
                ]
                if zona_fogo_ativa(partida, atacante_atual)
                else []
            ),
            row=1,
        )
        self.seletor_alvo = alvo
        self.seletor_tipo = tipo
        self.seletor_parceiro: discord.ui.Select | None = None

        async def escolher_alvo(interaction: discord.Interaction) -> None:
            self.alvo = alvo.values[0]
            _fixar_selecao(alvo, self.alvo)
            await interaction.response.edit_message(view=self)

        alvo.callback = escolher_alvo

        async def escolher_tipo(interaction: discord.Interaction) -> None:
            self.definir_tipo(tipo.values[0])
            await interaction.response.edit_message(view=self)

        tipo.callback = escolher_tipo
        self.add_item(alvo)
        self.add_item(tipo)

    def definir_tipo(self, tipo: str) -> None:
        self.tipo = tipo
        for opcao in self.seletor_tipo.options:
            opcao.default = opcao.value == tipo
        alvos = self._alvos_zona if tipo == "zona" else self._alvos_normais
        self.seletor_alvo.options = [
            discord.SelectOption(
                label=item.nome,
                value=item.nome,
                description=f"{item.casa} • {item.posicao}",
                default=item.nome == self.alvo,
            )
            for item in alvos[:25]
        ]
        if self.alvo not in {item.nome for item in alvos}:
            self.alvo = ""
        self.parceiro = ""
        if self.seletor_parceiro is not None:
            self.remove_item(self.seletor_parceiro)
            self.seletor_parceiro = None
        if tipo != "duplo":
            return
        opcoes = [
            discord.SelectOption(
                label=item.nome,
                value=item.nome,
                description=f"Batedor da {item.casa}",
            )
            for item in self._parceiros
        ]
        if not opcoes:
            opcoes = [
                discord.SelectOption(
                    label="Nenhum Batedor aliado disponível",
                    value="--",
                )
            ]
        parceiro = discord.ui.Select(
            placeholder="Segundo Batedor do Rebate Duplo",
            options=opcoes,
            row=2,
            disabled=not self._parceiros,
        )

        async def escolher_parceiro(interaction: discord.Interaction) -> None:
            self.parceiro = parceiro.values[0]
            _fixar_selecao(parceiro, self.parceiro)
            await interaction.response.edit_message(view=self)

        parceiro.callback = escolher_parceiro
        self.seletor_parceiro = parceiro
        self.add_item(parceiro)

    @discord.ui.button(label="Concluir ação", style=discord.ButtonStyle.primary, row=4)
    async def registrar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._continuar(interaction)

    @discord.ui.button(label="Rolagem Externa", style=discord.ButtonStyle.secondary, row=4)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.alvo or (self.tipo == "duplo" and self.parceiro in {"", "--"}):
            await interaction.response.send_message("Preencha os jogadores necessários.", ephemeral=True)
            return
        await interaction.response.send_modal(
            RolagemExternaModal("Total do ataque do Batedor", self._continuar)
        )

    @discord.ui.button(label="↩️ Voltar", style=discord.ButtonStyle.secondary, row=4)
    async def voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            partida, _ = self.cog._localizar_por_id(self.partida_id)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(
            content=None,
            embed=_embed_painel_acao(
                partida,
                "⚡ Ações do Turno",
                "Escolha a ação do jogador em destaque.",
            ),
            view=AcoesTurnoView(self.cog, partida),
        )

    async def _continuar(
        self,
        interaction: discord.Interaction,
        resultado_ataque_externo: int | None = None,
    ) -> None:
        if not self.alvo or (self.tipo == "duplo" and self.parceiro in {"", "--"}):
            await interaction.response.send_message("Preencha os jogadores necessários.", ephemeral=True)
            return
        try:
            partida, _ = self.cog._localizar_por_id(self.partida_id)
            atacante = encontrar_jogador_partida(partida, self.atacante)
            alvo = encontrar_jogador_partida(partida, self.alvo)
            if atacante.casa == alvo.casa and self.tipo != "zona":
                raise ValueError("O Batedor e o alvo precisam ser de equipes adversárias.")
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(
            content=None,
            embed=_embed_cabecalho_rolagem(
                "🛡️ Defesa contra o Balaço",
                (
                    f"Antes de resolver o impacto, **{alvo.nome}** precisa escolher "
                    "como reagirá ao Balaço."
                ),
            ),
            view=DefesaBalacoView(
                self.cog,
                partida,
                self.atacante,
                self.alvo,
                self.tipo == "duplo",
                self.parceiro,
                resultado_ataque_externo,
                zona_fogo=self.tipo == "zona",
            ),
        )


class DefesaBalacoView(discord.ui.View):
    def __init__(
        self,
        cog: Quadribol,
        partida: PartidaQuadribol,
        atacante: str,
        alvo: str,
        rebate_duplo: bool,
        parceiro: str,
        resultado_ataque_externo: int | None = None,
        *,
        zona_fogo: bool = False,
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.partida_id = partida.identificador
        self.atacante = atacante
        self.alvo = alvo
        self.rebate_duplo = rebate_duplo
        self.parceiro = parceiro
        self.resultado_ataque_externo = resultado_ataque_externo
        self.zona_fogo = zona_fogo
        self.defesa = "Reflexo"
        self.defensor = ""
        self.redirecionar = False
        self.alvo_redirecionado = ""
        atingido = encontrar_jogador_partida(partida, alvo)
        atacante_partida = encontrar_jogador_partida(partida, atacante)
        protetores = _jogadores_priorizados(partida, [
            item for item in partida.jogadores
            if item.casa == atingido.casa
            and item.posicao == "Batedor"
            and item.ativo
            and item.em_campo
        ])
        tipo = discord.ui.Select(
            placeholder="Forma de defesa",
            options=[
                discord.SelectOption(
                    label="Desviar com Reflexo",
                    value="Reflexo",
                    description=f"{atingido.nome} tenta sair da trajetória",
                ),
                discord.SelectOption(
                    label="Defesa de um Batedor",
                    value="Batedor",
                    description="Um aliado tenta interceptar o balaço",
                ),
                discord.SelectOption(
                    label="Redirecionar com um Batedor",
                    value="Redirecionar",
                    description="Exige superar a rebatida por 5 ou mais",
                ),
            ],
            row=0,
        )
        protetor = discord.ui.Select(
            placeholder="Batedor defensor — apenas se escolhido acima",
            options=(
                [
                    discord.SelectOption(
                        label=item.nome,
                        value=item.nome,
                        description=f"Pontaria {item.bonus_teste_posicao:+d}",
                    )
                    for item in protetores
                ]
                or [discord.SelectOption(label="Nenhum Batedor disponível", value="--")]
            ),
            row=1,
        )
        alvo_redirecionado = discord.ui.Select(
            placeholder="Novo alvo — apenas para redirecionamento",
            options=[
                discord.SelectOption(
                    label=item.nome,
                    value=item.nome,
                    description=f"{item.casa} • {item.posicao}",
                )
                for item in _jogadores_priorizados(partida)
                if item.casa == atacante_partida.casa and item.ativo and item.em_campo
            ][:25],
            row=2,
        )
        self.seletor_tipo = tipo
        self.seletor_protetor = protetor
        self.seletor_alvo_redirecionado = alvo_redirecionado

        async def escolher_tipo(interaction: discord.Interaction) -> None:
            self.definir_defesa(tipo.values[0])
            await interaction.response.edit_message(view=self)

        async def escolher_protetor(interaction: discord.Interaction) -> None:
            self.defensor = protetor.values[0]
            _fixar_selecao(protetor, self.defensor)
            await interaction.response.edit_message(view=self)

        async def escolher_novo_alvo(interaction: discord.Interaction) -> None:
            self.alvo_redirecionado = alvo_redirecionado.values[0]
            _fixar_selecao(alvo_redirecionado, self.alvo_redirecionado)
            await interaction.response.edit_message(view=self)

        tipo.callback = escolher_tipo
        protetor.callback = escolher_protetor
        alvo_redirecionado.callback = escolher_novo_alvo
        self.add_item(tipo)

    def definir_defesa(self, escolha: str) -> None:
        self.redirecionar = escolha == "Redirecionar"
        self.defesa = "Batedor" if self.redirecionar else escolha
        for opcao in self.seletor_tipo.options:
            opcao.default = opcao.value == escolha
        for seletor in (
            self.seletor_protetor,
            self.seletor_alvo_redirecionado,
        ):
            if seletor in self.children:
                self.remove_item(seletor)
        if self.defesa == "Reflexo":
            self.defensor = ""
        else:
            self.add_item(self.seletor_protetor)
        if self.redirecionar:
            self.add_item(self.seletor_alvo_redirecionado)
        else:
            self.alvo_redirecionado = ""

    @discord.ui.button(label="Resolver balaço", style=discord.ButtonStyle.danger, row=3)
    async def resolver(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if await self._exigir_tempo_defensor(interaction):
            return
        await self._resolver(interaction)

    @discord.ui.button(label="Rolagem Externa", style=discord.ButtonStyle.secondary, row=3)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.defesa == "Batedor" and self.defensor in {"", "--"}:
            await interaction.response.send_message("Escolha um Batedor defensor.", ephemeral=True)
            return
        if self.redirecionar and not self.alvo_redirecionado:
            await interaction.response.send_message(
                "Escolha o adversário que receberá o Balaço redirecionado.", ephemeral=True
            )
            return
        if await self._exigir_tempo_defensor(interaction):
            return
        await interaction.response.send_modal(
            RolagemExternaModal("Total da defesa", self._resolver)
        )

    async def _exigir_tempo_defensor(self, interaction: discord.Interaction) -> bool:
        if self.defesa == "Batedor" and self.defensor in {"", "--"}:
            return False
        partida, _ = self.cog._localizar_por_id(self.partida_id)
        nome_defensor = self.alvo if self.defesa == "Reflexo" else self.defensor
        defensor = encontrar_jogador_partida(partida, nome_defensor)
        return await exigir_resistencia_tempo(
            interaction,
            self.cog,
            partida,
            defensor,
            "reagir ao Balaço",
            self,
            self,
        )

    async def _resolver(
        self,
        interaction: discord.Interaction,
        resultado_defesa_externo: int | None = None,
    ) -> None:
        if self.defesa == "Batedor" and self.defensor in {"", "--"}:
            await interaction.response.send_message("Escolha um Batedor defensor.", ephemeral=True)
            return
        if self.redirecionar and not self.alvo_redirecionado:
            await interaction.response.send_message(
                "Escolha o adversário que receberá o Balaço redirecionado.",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        resultado: ResultadoBalaco | None = None
        eventos_turno: list[EventoPartida] = []

        def acao(partida: PartidaQuadribol) -> None:
            nonlocal resultado
            resultado = resolver_balaco(
                partida,
                self.atacante,
                self.alvo,
                defesa=self.defesa,
                defensor=self.defensor,
                rebate_duplo=self.rebate_duplo,
                segundo_batedor=self.parceiro,
                zona_fogo=self.zona_fogo,
                redirecionar=self.redirecionar,
                alvo_redirecionado=self.alvo_redirecionado,
                resultado_ataque_externo=self.resultado_ataque_externo,
                resultado_defesa_externo=resultado_defesa_externo,
            )
            if not resultado.posse_perdida_por:
                inicio = len(partida.eventos)
                avancar_turno(partida)
                eventos_turno.extend(partida.eventos[inicio:])

        try:
            partida = await self.cog.mutar_partida(self.partida_id, acao)
            await self.cog.atualizar_mensagem(partida)
            await self.cog.publicar_surgimentos(partida, eventos_turno)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.edit_original_response(
                content=f"Não foi possível resolver o balaço: {erro}",
                embed=None,
                view=None,
            )
            return
        assert resultado is not None
        embed = embed_resultado_balaco(resultado, partida)
        self.stop()
        view: discord.ui.View = (
            ReposicaoGolesAposBalacoView(self.cog, partida, resultado)
            if resultado.posse_perdida_por
            else PainelResultadoView(self.cog, partida)
        )
        await interaction.edit_original_response(content=None, embed=embed, view=view)


class ReposicaoGolesAposBalacoView(discord.ui.View):
    def __init__(
        self,
        cog: Quadribol,
        partida: PartidaQuadribol,
        resultado: ResultadoBalaco | None = None,
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.partida_id = partida.identificador
        self.resultado = resultado
        self.casa_nova_posse = (
            resultado.casa_nova_posse if resultado else partida.reposicao_goles_casa
        )
        self.posse_perdida_por = (
            resultado.posse_perdida_por if resultado else partida.reposicao_goles_jogador
        )
        self.escolhido = ""
        candidatos = _jogadores_priorizados(
            partida,
            artilheiros_ativos(partida, self.casa_nova_posse),
        )
        self.tem_candidatos = bool(candidatos)
        seletor = discord.ui.Select(
            placeholder=f"Artilheiro da {self.casa_nova_posse}",
            options=(
                [
                    discord.SelectOption(
                        label=item.nome,
                        value=item.nome,
                        description=f"Artilheiro da {item.casa}",
                    )
                    for item in candidatos[:25]
                ]
                or [
                    discord.SelectOption(
                        label="Nenhum Artilheiro ativo disponível",
                        value="--",
                    )
                ]
            ),
            row=0,
            disabled=not candidatos,
        )

        async def escolher(interaction: discord.Interaction) -> None:
            self.escolhido = seletor.values[0]
            for opcao in seletor.options:
                opcao.default = opcao.value == self.escolhido
            await interaction.response.edit_message(view=self)

        seletor.callback = escolher
        self.add_item(seletor)

    @discord.ui.button(
        label="Confirmar nova posse",
        style=discord.ButtonStyle.success,
        row=1,
    )
    async def confirmar(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        if not self.escolhido:
            mensagem = (
                f"A {self.casa_nova_posse} não possui Artilheiro ativo para receber a Goles."
                if not self.tem_candidatos
                else "Escolha o Artilheiro que receberá a Goles."
            )
            await interaction.response.send_message(
                mensagem,
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        eventos_turno: list[EventoPartida] = []

        def acao(partida: PartidaQuadribol) -> None:
            inicio = len(partida.eventos)
            atribuir_posse_goles(
                partida,
                self.escolhido,
                motivo=f"após {self.posse_perdida_por} ser atingido por um Balaço",
            )
            avancar_turno(partida)
            eventos_turno.extend(partida.eventos[inicio:])

        try:
            partida = await self.cog.mutar_partida(self.partida_id, acao)
            await self.cog.atualizar_mensagem(partida)
            await self.cog.publicar_surgimentos(partida, eventos_turno)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.edit_original_response(
                content=f"Não foi possível entregar a Goles: {erro}",
                embed=None,
                view=None,
            )
            return
        embed = (
            embed_resultado_balaco(self.resultado, partida)
            if self.resultado is not None
            else discord.Embed(
                title="🏐 Nova posse da Goles",
                description=(
                    f"**{self.posse_perdida_por}** foi atingido por um Balaço e perdeu a posse."
                ),
                color=COR_QUADRIBOL,
            )
        )
        embed.add_field(
            name="🏐 Nova posse",
            value=f"**{self.escolhido}**, da **{self.casa_nova_posse}**, recebeu a Goles.",
            inline=False,
        )
        self.stop()
        await interaction.edit_original_response(
            content=None,
            embed=embed,
            view=PainelResultadoView(self.cog, partida),
        )


class FluxoEfeitoView(discord.ui.View):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(timeout=300)
        self.cog = cog
        self.partida_id = partida.identificador

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        membro = interaction.user
        if isinstance(membro, discord.Member) and membro.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message(
            "Você precisa da permissão **Gerenciar servidor** para controlar a partida.",
            ephemeral=True,
        )
        return False

    def carregar(self, interaction: discord.Interaction) -> PartidaQuadribol:
        partida, _ = self.cog._localizar_por_id(self.partida_id)
        return partida

    @discord.ui.button(label="Voltar", emoji="↩️", style=discord.ButtonStyle.secondary, row=4)
    async def voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content=None,
            view=EscolherCondicaoCatalogadaView(self.cog, partida, "Efeito narrativo"),
        )


def _embed_previa_condicao(
    partida: PartidaQuadribol,
    condicao_nome: str,
    alvos: list[str],
    *,
    intensidade: str = "",
    gatilho: str = "",
    origem: str = "Efeito narrativo",
) -> discord.Embed:
    condicao = encontrar_condicao(condicao_nome)
    embed = discord.Embed(
        title=f"⏳ {condicao.nome}",
        description="Confira o efeito antes de aplicá-lo à partida.",
        color=COR_QUADRIBOL,
    )
    embed.add_field(name="Categoria", value=condicao.categoria, inline=True)
    embed.add_field(name="Origem", value=origem, inline=True)
    if normalizar_rotulo(condicao.nome) == "tempo meteorologico":
        casas_afetadas = sorted(
            {
                encontrar_jogador_partida(partida, nome).casa
                for nome in alvos
            }
        )
        embed.add_field(
            name="Equipe(s) afetada(s)",
            value="\n".join(
                f"• {EMOJIS_CASAS.get(casa, '')} {casa}" for casa in casas_afetadas
            ),
            inline=False,
        )
    else:
        embed.add_field(name="Jogador(es)", value="\n".join(f"• {nome}" for nome in alvos), inline=False)
    if intensidade:
        embed.add_field(
            name="Resistência",
            value=(
                f"{condicao.teste_resistencia} • **{intensidade} "
                f"(CD {INTENSIDADES_CONDICAO[intensidade]})**"
            ),
            inline=False,
        )
    embed.add_field(name="Efeito", value=condicao.descricao, inline=False)
    if condicao.duracao_tipo == "rodadas":
        duracao = f"Próxima rodada, encerrando automaticamente após a rodada {partida.rodada + condicao.rodadas}."
    elif condicao.duracao_tipo == "rodadas_1d4":
        duracao = "1d4 rodadas; a duração será rolada ao confirmar e terminará automaticamente."
    elif condicao.duracao_tipo == "gatilho":
        duracao = f'Até acontecer: **{gatilho}**'
    else:
        duracao = "Partida inteira, até remoção do moderador."
    embed.add_field(name="Duração", value=duracao, inline=False)
    return embed


class ConfirmarCondicaoView(FluxoEfeitoView):
    def __init__(
        self,
        cog: Quadribol,
        partida: PartidaQuadribol,
        condicao: str,
        alvos: list[str],
        *,
        intensidade: str = "",
        gatilho: str = "",
        origem: str = "Efeito narrativo",
    ):
        super().__init__(cog, partida)
        self.condicao = condicao
        self.alvos = alvos
        self.intensidade = intensidade
        self.gatilho = gatilho
        self.origem = origem
        self.voltar.callback = self.voltar_catalogo

    async def voltar_catalogo(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content="Escolha uma condição narrativa cadastrada.",
            embed=_embed_painel_acao(
                partida,
                "⏳ Efeitos e Condições",
                "Escolha a origem, a condição cadastrada e os envolvidos. Efeitos com duração definida terminam automaticamente.",
            ),
            view=EscolherCondicaoCatalogadaView(self.cog, partida, self.origem),
        )

    @discord.ui.button(label="Confirmar aplicação", emoji="✅", style=discord.ButtonStyle.success, row=0)
    async def confirmar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            partida = await self.cog.mutar_partida(
                self.partida_id,
                lambda item: adicionar_condicao_catalogada(
                    item,
                    self.condicao,
                    self.alvos,
                    intensidade=self.intensidade,
                    gatilho=self.gatilho,
                    origem=self.origem,
                ),
            )
            await self.cog.atualizar_mensagem(partida)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.response.send_message(
                f"Não foi possível aplicar a condição: {erro}",
                ephemeral=True,
            )
            return
        efeitos = [
            efeito
            for nome in self.alvos
            for efeito in encontrar_jogador_partida(partida, nome).efeitos
            if normalizar_rotulo(efeito.nome) == normalizar_rotulo(self.condicao)
        ]
        detalhe = ""
        if efeitos and efeitos[0].duracao_tipo == "rodadas":
            detalhe = f" Ela ficará ativa até o fim da rodada {efeitos[0].rodada_final}."
        elif efeitos and efeitos[0].duracao_tipo == "gatilho":
            detalhe = f' Ela ficará ativa até acontecer: "{efeitos[0].gatilho}".'
        self.stop()
        if normalizar_rotulo(self.condicao) == "tempo meteorologico":
            casas = sorted(
                {
                    encontrar_jogador_partida(partida, nome).casa
                    for nome in self.alvos
                }
            )
            aplicacao = "Aplicado a **" + " e ".join(casas) + "**."
        else:
            aplicacao = f"Aplicada a **{', '.join(self.alvos)}**."
        embed = discord.Embed(
            title=f"✅ {self.condicao}",
            description=f"{aplicacao}{detalhe}",
            color=0x57F287,
        )
        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=PainelResultadoView(self.cog, partida),
        )


class IntensidadeCondicaoView(FluxoEfeitoView):
    def __init__(
        self,
        cog: Quadribol,
        partida: PartidaQuadribol,
        condicao: str,
        alvos: list[str],
        origem: str,
    ):
        super().__init__(cog, partida)
        self.condicao = condicao
        self.alvos = alvos
        self.origem = origem
        self.voltar.callback = self.voltar_catalogo
        condicao_catalogada = encontrar_condicao(condicao)
        seletor = discord.ui.Select(
            placeholder="Intensidade da condição",
            options=[
                discord.SelectOption(
                    label=nome,
                    value=nome,
                    description=f"{condicao_catalogada.teste_resistencia} CD {cd}",
                )
                for nome, cd in INTENSIDADES_CONDICAO.items()
            ],
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            partida_atual = self.carregar(interaction)
            intensidade = seletor.values[0]
            await interaction.response.edit_message(
                content=None,
                embed=_embed_previa_condicao(
                    partida_atual,
                    self.condicao,
                    self.alvos,
                    intensidade=intensidade,
                    origem=self.origem,
                ),
                view=ConfirmarCondicaoView(
                    self.cog,
                    partida_atual,
                    self.condicao,
                    self.alvos,
                    intensidade=intensidade,
                    origem=self.origem,
                ),
            )

        seletor.callback = selecionar
        self.add_item(seletor)

    async def voltar_catalogo(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content="Escolha uma condição narrativa cadastrada.",
            view=EscolherCondicaoCatalogadaView(self.cog, partida, self.origem),
        )


class GatilhoCondicaoModal(discord.ui.Modal, title="Motivado"):
    motivo = discord.ui.TextInput(
        label="O que está motivando o jogador?",
        placeholder="Ex.: proteger um colega de equipe",
        max_length=120,
    )
    gatilho = discord.ui.TextInput(
        label="O que encerra o efeito?",
        placeholder="Ex.: o colega sair de perigo",
        max_length=120,
    )

    def __init__(self, cog: Quadribol, partida_id: str, alvos: list[str], origem: str):
        super().__init__()
        self.cog = cog
        self.partida_id = partida_id
        self.alvos = alvos
        self.origem = origem

    async def on_submit(self, interaction: discord.Interaction) -> None:
        partida, _ = self.cog._localizar_por_id(self.partida_id)
        gatilho = f"{self.gatilho.value} — Motivação: {self.motivo.value}"
        await interaction.response.edit_message(
            content=None,
            embed=_embed_previa_condicao(
                partida,
                "Motivado",
                self.alvos,
                gatilho=gatilho,
                origem=self.origem,
            ),
            view=ConfirmarCondicaoView(
                self.cog,
                partida,
                "Motivado",
                self.alvos,
                gatilho=gatilho,
                origem=self.origem,
            ),
        )


class EscolherAlvosCondicaoView(FluxoEfeitoView):
    def __init__(
        self,
        cog: Quadribol,
        partida: PartidaQuadribol,
        condicao_nome: str,
        origem: str,
    ):
        super().__init__(cog, partida)
        self.condicao = encontrar_condicao(condicao_nome)
        self.origem = origem
        self.voltar.callback = self.voltar_catalogo
        maximo = len(partida.jogadores) if self.condicao.multiplos_alvos else 1
        minimo = 2 if self.condicao.multiplos_alvos else 1
        if self.condicao.exige_rival:
            maximo = 2
        seletor = discord.ui.Select(
            placeholder="Jogador(es) afetado(s)",
            min_values=minimo,
            max_values=min(maximo, 25),
            options=[
                discord.SelectOption(
                    label=item.nome,
                    value=item.nome,
                    description=f"{item.casa} • {item.posicao}",
                )
                for item in _jogadores_priorizados(partida)[:25]
            ],
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            partida_atual = self.carregar(interaction)
            alvos = list(seletor.values)
            if self.condicao.exige_rival:
                jogadores = [encontrar_jogador_partida(partida_atual, nome) for nome in alvos]
                if jogadores[0].casa == jogadores[1].casa:
                    await interaction.response.send_message(
                        "Rivalidade exige dois jogadores de equipes adversárias.",
                        ephemeral=True,
                    )
                    return
            if self.condicao.exige_intensidade:
                await interaction.response.edit_message(
                    content="Escolha a intensidade. Ela define a CD do teste de Vontade.",
                    view=IntensidadeCondicaoView(
                        self.cog,
                        partida_atual,
                        self.condicao.nome,
                        alvos,
                        self.origem,
                    ),
                )
            elif self.condicao.exige_gatilho:
                await interaction.response.send_modal(
                    GatilhoCondicaoModal(
                        self.cog,
                        partida_atual.identificador,
                        alvos,
                        self.origem,
                    )
                )
            else:
                await interaction.response.edit_message(
                    content=None,
                    embed=_embed_previa_condicao(
                        partida_atual,
                        self.condicao.nome,
                        alvos,
                        origem=self.origem,
                    ),
                    view=ConfirmarCondicaoView(
                        self.cog,
                        partida_atual,
                        self.condicao.nome,
                        alvos,
                        origem=self.origem,
                    ),
                )

        seletor.callback = selecionar
        self.add_item(seletor)

    async def voltar_catalogo(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content="Escolha uma condição narrativa cadastrada.",
            view=EscolherCondicaoCatalogadaView(self.cog, partida, self.origem),
        )


class TempoMeteorologicoModal(discord.ui.Modal):
    def __init__(self, cog: Quadribol, partida_id: str, origem: str):
        super().__init__(title="Tempo Meteorológico")
        self.cog = cog
        self.partida_id = partida_id
        self.origem = origem
        self.condicao = discord.ui.TextInput(
            label="Condição meteorológica",
            placeholder="Ex.: chuva intensa, neblina ou fortes correntes de vento",
            style=discord.TextStyle.paragraph,
            min_length=3,
            max_length=300,
        )
        self.add_item(self.condicao)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        partida, _ = self.cog._localizar_por_id(self.partida_id)
        descricao = str(self.condicao.value).strip()
        origem = f"{self.origem} — {descricao}"
        await interaction.response.edit_message(
            content=None,
            embed=_embed_painel_acao(
                partida,
                "🌦️ Tempo Meteorológico",
                f"**Condição:** {descricao}\nEscolha se ela afeta uma equipe ou ambas.",
            ),
            view=EscopoTempoMeteorologicoView(self.cog, partida, origem),
        )


class EscopoTempoMeteorologicoView(FluxoEfeitoView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol, origem: str):
        super().__init__(cog, partida)
        self.origem = origem
        self.voltar.callback = self.voltar_catalogo
        seletor = discord.ui.Select(
            placeholder="Equipes afetadas pelo tempo",
            options=[
                discord.SelectOption(
                    label="Uma equipe",
                    value="uma",
                    description="A condição atingirá apenas a equipe escolhida.",
                ),
                discord.SelectOption(
                    label="Ambas as equipes",
                    value="ambas",
                    description="Todos os jogadores da partida serão afetados.",
                ),
            ],
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            partida_atual = self.carregar(interaction)
            if seletor.values[0] == "uma":
                await interaction.response.edit_message(
                    view=EquipeTempoMeteorologicoView(
                        self.cog, partida_atual, self.origem
                    )
                )
                return
            alvos = [jogador.nome for jogador in partida_atual.jogadores]
            await interaction.response.edit_message(
                content="Escolha a intensidade do Tempo Meteorológico.",
                view=IntensidadeCondicaoView(
                    self.cog,
                    partida_atual,
                    "Tempo Meteorológico",
                    alvos,
                    self.origem,
                ),
            )

        seletor.callback = selecionar
        self.add_item(seletor)

    async def voltar_catalogo(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content=None,
            embed=_embed_painel_acao(
                partida,
                "⏳ Efeitos e Condições",
                "Escolha a origem, a condição cadastrada e os envolvidos.",
            ),
            view=EscolherCondicaoCatalogadaView(self.cog, partida, "Efeito narrativo"),
        )


class EquipeTempoMeteorologicoView(FluxoEfeitoView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol, origem: str):
        super().__init__(cog, partida)
        self.origem = origem
        self.voltar.callback = self.voltar_escopo
        seletor = discord.ui.Select(
            placeholder="Equipe afetada",
            options=[
                discord.SelectOption(
                    label=casa,
                    value=casa,
                    emoji=EMOJIS_CASAS.get(casa),
                )
                for casa in partida.casas()
            ],
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            partida_atual = self.carregar(interaction)
            casa = seletor.values[0]
            alvos = [
                jogador.nome
                for jogador in partida_atual.jogadores
                if jogador.casa == casa
            ]
            await interaction.response.edit_message(
                content=f"Escolha a intensidade que afetará a **{casa}**.",
                view=IntensidadeCondicaoView(
                    self.cog,
                    partida_atual,
                    "Tempo Meteorológico",
                    alvos,
                    self.origem,
                ),
            )

        seletor.callback = selecionar
        self.add_item(seletor)

    async def voltar_escopo(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            view=EscopoTempoMeteorologicoView(self.cog, partida, self.origem)
        )


class EscolherCondicaoCatalogadaView(FluxoEfeitoView):
    def __init__(
        self,
        cog: Quadribol,
        partida: PartidaQuadribol,
        origem: str = "Efeito narrativo",
    ):
        super().__init__(cog, partida)
        self.origem = origem
        self.voltar.callback = self.voltar_acoes
        seletor = discord.ui.Select(
            placeholder="Condição ou efeito",
            options=[
                discord.SelectOption(
                    label=item.nome,
                    value=item.nome,
                    description=item.categoria[:100],
                )
                for item in CONDICOES_QUADRIBOL
            ],
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            partida_atual = self.carregar(interaction)
            if normalizar_rotulo(seletor.values[0]) == "tempo meteorologico":
                await interaction.response.send_modal(
                    TempoMeteorologicoModal(
                        self.cog,
                        partida_atual.identificador,
                        self.origem,
                    )
                )
                return
            await interaction.response.edit_message(
                content=f"Escolha quem receberá **{seletor.values[0]}**.",
                view=EscolherAlvosCondicaoView(
                    self.cog,
                    partida_atual,
                    seletor.values[0],
                    self.origem,
                ),
            )

        seletor.callback = selecionar
        self.add_item(seletor)

    @discord.ui.button(label="Encerrar efeito", style=discord.ButtonStyle.danger, row=1)
    async def encerrar_efeito(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content="Escolha o efeito que deseja encerrar.",
            view=RemoverEfeitoView(self.cog, partida),
        )

    async def voltar_acoes(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content=None,
            embed=_embed_painel_acao(
                partida,
                "⚡ Ações do Turno",
                "Escolha a ação do jogador em destaque.",
            ),
            view=AcoesTurnoView(self.cog, partida),
        )


class EscolherOrigemEfeitoView(FluxoEfeitoView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(cog, partida)
        self.voltar.callback = self.voltar_acoes
        seletor = discord.ui.Select(
            placeholder="Origem do efeito ou condição",
            options=[
                discord.SelectOption(
                    label="Efeito narrativo",
                    value="Efeito narrativo",
                    description="Pressão, motivação, rivalidade ou situação narrativa.",
                ),
            ],
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            partida_atual = self.carregar(interaction)
            origem = seletor.values[0]
            texto = "Origem: **Efeito narrativo**. Agora escolha a condição ou efeito."
            view = EscolherCondicaoCatalogadaView(
                self.cog,
                partida_atual,
                "Efeito narrativo",
            )
            await interaction.response.edit_message(content=texto, view=view)

        seletor.callback = selecionar
        self.add_item(seletor)

    async def voltar_acoes(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content=None,
            embed=_embed_painel_acao(
                partida,
                "⚡ Ações do Turno",
                "Escolha a ação do jogador em destaque.",
            ),
            view=AcoesTurnoView(self.cog, partida),
        )


class OrigemDetalhadaEfeitoView(FluxoEfeitoView):
    async def voltar_origens(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content="Escolha a origem do efeito ou condição.",
            view=EscolherOrigemEfeitoView(self.cog, partida),
        )


class EscolherManobraOrigemEfeitoView(OrigemDetalhadaEfeitoView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(cog, partida)
        self.voltar.callback = self.voltar_origens
        manobras = carregar_manobras()
        seletor = discord.ui.Select(
            placeholder="Manobra que originou o efeito",
            options=[
                discord.SelectOption(
                    label=item.nome[:100],
                    value=str(indice),
                    description=f"CD {item.cd} • {item.participantes}"[:100],
                )
                for indice, item in enumerate(manobras[:25])
            ],
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            partida_atual = self.carregar(interaction)
            manobra = manobras[int(seletor.values[0])]
            origem = f"Manobra: {manobra.nome}"
            await interaction.response.edit_message(
                content=f"Origem: **{origem}**. Agora escolha a condição ou efeito.",
                view=EscolherCondicaoCatalogadaView(self.cog, partida_atual, origem),
            )

        seletor.callback = selecionar
        self.add_item(seletor)


HABILIDADES_QUADRIBOL = {
    normalizar_rotulo(nome)
    for nome in (
        "Aparência Inofensiva",
        "Brutamontes",
        "Clarividência",
        "Licantropia",
        "Parte-Vampiro",
        "Poeta // Artista",
        "Presença Marcante",
        "Rei",
        "Sangue nos Olhos // Combo",
        "Soldado",
        "Sortudo",
        "Valente",
    )
}


def _habilidades_quadribol_da_ficha(jogador) -> list[str]:
    try:
        ficha = FichaPersonagem.carregar(Path(jogador.caminho_ficha))
    except (OSError, ValueError):
        return []
    possuidas = [ficha.heranca, *ficha.origens_magicas, *ficha.especializacoes]
    return [
        nome
        for nome in possuidas
        if nome and normalizar_rotulo(nome) in HABILIDADES_QUADRIBOL
    ]


class EscolherJogadorHabilidadeEfeitoView(OrigemDetalhadaEfeitoView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(cog, partida)
        self.voltar.callback = self.voltar_origens
        jogadores = _jogadores_priorizados(partida, [
            item
            for item in partida.jogadores
            if item.ativo and item.em_campo and _habilidades_quadribol_da_ficha(item)
        ])
        if not jogadores:
            self.add_item(
                discord.ui.Button(
                    label="Nenhum jogador possui habilidade aplicável",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                    row=0,
                )
            )
            return
        seletor = discord.ui.Select(
            placeholder="Personagem com a habilidade",
            options=[
                discord.SelectOption(
                    label=item.nome[:100],
                    value=str(indice),
                    description=f"{item.casa} • {item.posicao}"[:100],
                )
                for indice, item in enumerate(jogadores[:25])
            ],
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            partida_atual = self.carregar(interaction)
            jogador = jogadores[int(seletor.values[0])]
            await interaction.response.edit_message(
                content=f"Escolha uma habilidade que **{jogador.nome}** realmente possui.",
                view=EscolherHabilidadeEfeitoView(self.cog, partida_atual, jogador.nome),
            )

        seletor.callback = selecionar
        self.add_item(seletor)


class EscolherHabilidadeEfeitoView(OrigemDetalhadaEfeitoView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol, jogador_nome: str):
        super().__init__(cog, partida)
        self.jogador_nome = jogador_nome
        self.voltar.callback = self.voltar_jogadores
        jogador = encontrar_jogador_partida(partida, jogador_nome)
        habilidades = _habilidades_quadribol_da_ficha(jogador)
        seletor = discord.ui.Select(
            placeholder="Habilidade do personagem",
            options=[
                discord.SelectOption(label=nome[:100], value=str(indice))
                for indice, nome in enumerate(habilidades[:25])
            ],
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            partida_atual = self.carregar(interaction)
            habilidade = habilidades[int(seletor.values[0])]
            origem = f"Habilidade: {habilidade} — {self.jogador_nome}"
            await interaction.response.edit_message(
                content=f"Origem: **{origem}**. Agora escolha a condição ou efeito provocado.",
                view=EscolherCondicaoCatalogadaView(self.cog, partida_atual, origem),
            )

        seletor.callback = selecionar
        self.add_item(seletor)

    async def voltar_jogadores(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content="Escolha o personagem que utilizará a habilidade.",
            view=EscolherJogadorHabilidadeEfeitoView(self.cog, partida),
        )


class EscolherAcontecimentoEfeitoView(OrigemDetalhadaEfeitoView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(cog, partida)
        self.voltar.callback = self.voltar_origens
        eventos = [
            evento
            for evento in reversed(partida.eventos)
            if evento.tipo not in {"turno", "fim_efeito", "condicao_acao"}
        ][:25]
        if not eventos:
            self.add_item(
                discord.ui.Button(
                    label="Nenhum acontecimento registrado",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                    row=0,
                )
            )
            return
        seletor = discord.ui.Select(
            placeholder="Impacto ou acontecimento registrado",
            options=[
                discord.SelectOption(
                    label=evento.descricao[:100],
                    value=str(indice),
                    description=evento.tipo.replace("_", " ").capitalize()[:100],
                )
                for indice, evento in enumerate(eventos)
            ],
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            partida_atual = self.carregar(interaction)
            evento = eventos[int(seletor.values[0])]
            origem = f"Acontecimento: {evento.descricao}"
            await interaction.response.edit_message(
                content="Acontecimento selecionado. Agora escolha a condição ou efeito provocado.",
                view=EscolherCondicaoCatalogadaView(self.cog, partida_atual, origem),
            )

        seletor.callback = selecionar
        self.add_item(seletor)


class ConfirmarRemocaoEfeitoView(FluxoEfeitoView):
    def __init__(
        self,
        cog: Quadribol,
        partida: PartidaQuadribol,
        jogador: str,
        indice: int,
    ):
        super().__init__(cog, partida)
        self.jogador = jogador
        self.indice = indice
        self.voltar.callback = self.voltar_lista

    async def voltar_lista(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content="Escolha o efeito que deseja encerrar.",
            view=RemoverEfeitoView(self.cog, partida),
        )

    @discord.ui.button(label="Encerrar efeito", style=discord.ButtonStyle.danger, row=0)
    async def confirmar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            removido = None

            def acao(partida: PartidaQuadribol) -> None:
                nonlocal removido
                removido = remover_efeito(partida, self.jogador, self.indice)

            partida = await self.cog.mutar_partida(self.partida_id, acao)
            await self.cog.atualizar_mensagem(partida)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.response.send_message(
                f"Não foi possível encerrar o efeito: {erro}",
                ephemeral=True,
            )
            return
        self.stop()
        embed = discord.Embed(
            title=f"✅ {removido.nome} encerrado",
            description=(
                "A condição meteorológica foi encerrada para todas as equipes afetadas."
                if normalizar_rotulo(removido.nome) == "tempo meteorologico"
                else f"O efeito foi encerrado para **{self.jogador}**."
            ),
            color=0x57F287,
        )
        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=PainelResultadoView(self.cog, partida),
        )


class RemoverEfeitoView(FluxoEfeitoView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(cog, partida)
        self.voltar.callback = self.voltar_catalogo
        opcoes = []
        ordem_jogadores = {
            item.nome: indice
            for indice, item in enumerate(_jogadores_priorizados(partida))
        }
        jogadores_com_indice = list(enumerate(partida.jogadores))
        jogadores_com_indice.sort(
            key=lambda par: ordem_jogadores.get(par[1].nome, len(ordem_jogadores))
        )
        for indice_jogador, jogador in jogadores_com_indice:
            for indice_efeito, efeito in enumerate(jogador.efeitos):
                opcoes.append(
                    discord.SelectOption(
                        label=f"{jogador.nome} — {efeito.nome}"[:100],
                        value=f"{indice_jogador}:{indice_efeito}",
                        description=(efeito.intensidade or efeito.categoria or efeito.origem)[:100],
                    )
                )
        if not opcoes:
            aviso = discord.ui.Button(
                label="Nenhum efeito ativo",
                disabled=True,
                style=discord.ButtonStyle.secondary,
                row=0,
            )
            self.add_item(aviso)
            return
        seletor = discord.ui.Select(
            placeholder="Efeito ativo",
            options=opcoes[:25],
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            partida_atual = self.carregar(interaction)
            indice_jogador, indice_efeito = map(int, seletor.values[0].split(":"))
            jogador = partida_atual.jogadores[indice_jogador]
            efeito = jogador.efeitos[indice_efeito]
            await interaction.response.edit_message(
                content=(
                    f"Deseja encerrar **{efeito.nome}** para **{jogador.nome}**?\n\n"
                    "Use isto quando um gatilho narrativo acontecer ou quando a narrativa remover uma condição persistente."
                ),
                view=ConfirmarRemocaoEfeitoView(
                    self.cog,
                    partida_atual,
                    jogador.nome,
                    indice_efeito,
                ),
            )

        seletor.callback = selecionar
        self.add_item(seletor)

    async def voltar_catalogo(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content=None,
            view=EscolherCondicaoCatalogadaView(self.cog, partida, "Efeito narrativo"),
        )


class EscolherFaltaView(discord.ui.View):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol, infrator: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.partida_id = partida.identificador
        self.infrator = infrator
        self.nome_falta = ""
        self.reserva = ""
        jogador = encontrar_jogador_partida(partida, infrator)
        self.faltas = {
            item.nome: item
            for item in carregar_faltas()
            if jogador.posicao in item.posicoes
        }
        faltas = discord.ui.Select(
            placeholder="Falta cometida",
            options=[
                discord.SelectOption(
                    label=item.nome,
                    value=item.nome,
                    description=f"{item.cartao} • {item.consequencia}"[:100],
                )
                for item in self.faltas.values()
            ],
            row=0,
        )
        reservas = reservas_disponiveis(partida, infrator)
        reserva = discord.ui.Select(
            placeholder="Reserva para uma possível expulsão",
            options=[
                discord.SelectOption(
                    label="Escolha automática",
                    value="--",
                    description="Usa o único reserva disponível ou deixa a posição vazia",
                ),
                *[
                    discord.SelectOption(
                        label=item.nome,
                        value=item.nome,
                        description=f"{item.posicao} • {item.vassoura}"[:100],
                    )
                    for item in reservas[:24]
                ],
            ],
            row=1,
        )

        async def escolher_falta(interaction: discord.Interaction) -> None:
            self.nome_falta = faltas.values[0]
            await interaction.response.defer()

        async def escolher_reserva(interaction: discord.Interaction) -> None:
            self.reserva = "" if reserva.values[0] == "--" else reserva.values[0]
            await interaction.response.defer()

        faltas.callback = escolher_falta
        reserva.callback = escolher_reserva
        self.add_item(faltas)
        self.add_item(reserva)

    @discord.ui.button(label="Aplicar falta", style=discord.ButtonStyle.danger, row=2)
    async def aplicar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.nome_falta:
            await interaction.response.send_message("Escolha a falta cometida.", ephemeral=True)
            return
        await interaction.response.defer()
        registro: RegistroFalta | None = None

        def acao(partida: PartidaQuadribol) -> None:
            nonlocal registro
            registro = registrar_falta(
                partida,
                self.infrator,
                self.faltas[self.nome_falta],
                reserva=self.reserva,
            )

        try:
            partida = await self.cog.mutar_partida(self.partida_id, acao)
            await self.cog.atualizar_mensagem(partida)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.edit_original_response(
                content=f"Não foi possível aplicar a falta: {erro}",
                embed=None,
                view=self,
            )
            return
        assert registro is not None
        evento = embed_falta(registro)
        self.stop()
        if partida.penalti_casa:
            await interaction.edit_original_response(
                content="A falta foi aplicada. Escolha o Artilheiro que cobrará o pênalti.",
                embed=evento,
                view=PenaltiView(self.cog, partida),
            )
        else:
            await interaction.edit_original_response(
                content=None,
                embed=evento,
                view=PainelResultadoView(self.cog, partida),
            )


class EscolherInfratorFaltaView(discord.ui.View):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(timeout=120)
        self.cog = cog
        seletor = discord.ui.Select(
            placeholder="Jogador que cometeu a falta",
            options=[
                discord.SelectOption(
                    label=item.nome,
                    value=item.nome,
                    description=f"{item.casa} • {item.posicao}",
                )
                for item in _jogadores_priorizados(partida)
                if item.ativo and item.em_campo
            ][:25],
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            self.stop()
            await interaction.response.edit_message(
                content="Agora escolha a infração. A punição já está definida na própria falta.",
                view=EscolherFaltaView(self.cog, partida, seletor.values[0]),
            )

        seletor.callback = selecionar
        self.add_item(seletor)


class PenaltiView(discord.ui.View):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(timeout=180)
        self.cog = cog
        self.partida_id = partida.identificador
        self.artilheiro = ""
        cobradores = _jogadores_priorizados(partida, [
            item
            for item in partida.jogadores
            if item.casa == partida.penalti_casa
            and item.posicao == "Artilheiro"
            and item.ativo
            and item.em_campo
        ])
        seletor = discord.ui.Select(
            placeholder="Artilheiro cobrador",
            options=[
                discord.SelectOption(
                    label=item.nome,
                    value=item.nome,
                    description=f"Pontaria {item.bonus_teste_posicao:+d}",
                )
                for item in cobradores
            ],
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            self.artilheiro = seletor.values[0]
            _fixar_selecao(seletor, self.artilheiro)
            await interaction.response.edit_message(view=self)

        seletor.callback = selecionar
        self.add_item(seletor)
    @discord.ui.button(label="Cobrar pênalti", style=discord.ButtonStyle.success, row=1)
    async def cobrar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if await self._exigir_tempo_cobrador(interaction):
            return
        await self._seguir_para_defesa(interaction)

    @discord.ui.button(label="Rolagem Externa", style=discord.ButtonStyle.secondary, row=1)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.artilheiro:
            await interaction.response.send_message("Escolha o Artilheiro cobrador.", ephemeral=True)
            return
        if await self._exigir_tempo_cobrador(interaction):
            return
        await interaction.response.send_modal(
            RolagemExternaModal("Total do Artilheiro", self._seguir_para_defesa)
        )

    async def _exigir_tempo_cobrador(self, interaction: discord.Interaction) -> bool:
        if not self.artilheiro:
            return False
        partida, _ = self.cog._localizar_por_id(self.partida_id)
        cobrador = encontrar_jogador_partida(partida, self.artilheiro)
        return await exigir_resistencia_tempo(
            interaction,
            self.cog,
            partida,
            cobrador,
            "cobrar o pênalti",
            self,
            self,
        )

    async def _seguir_para_defesa(
        self,
        interaction: discord.Interaction,
        resultado_artilheiro_externo: int | None = None,
    ) -> None:
        if not self.artilheiro:
            await interaction.response.send_message("Escolha o Artilheiro cobrador.", ephemeral=True)
            return
        partida, _ = self.cog._localizar_por_id(self.partida_id)
        cobrador = encontrar_jogador_partida(partida, self.artilheiro)
        goleiro = next(
            (
                item for item in partida.jogadores
                if item.casa != cobrador.casa
                and item.posicao == "Goleiro"
                and item.ativo
                and item.em_campo
            ),
            None,
        )
        if goleiro is None:
            await interaction.response.send_message(
                "A equipe adversária precisa possuir um Goleiro ativo.", ephemeral=True
            )
            return
        view_defesa = DefesaPenaltiView(
            self.cog,
            partida,
            self.artilheiro,
            resultado_artilheiro_externo,
        )
        if await exigir_resistencia_tempo(
            interaction,
            self.cog,
            partida,
            goleiro,
            "defender o pênalti",
            view_defesa,
            self,
        ):
            return
        self.stop()
        await interaction.response.edit_message(
            content=None,
            embed=_embed_cabecalho_rolagem(
                "🧤 Defesa do Pênalti",
                (
                    f"**{self.artilheiro}** fará a cobrança. Agora **{goleiro.nome}** "
                    "precisa escolher como realizará a defesa."
                ),
            ),
            view=view_defesa,
        )


class DefesaPenaltiView(discord.ui.View):
    def __init__(
        self,
        cog: Quadribol,
        partida: PartidaQuadribol,
        artilheiro: str,
        resultado_artilheiro_externo: int | None,
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.partida_id = partida.identificador
        self.artilheiro = artilheiro
        self.resultado_artilheiro_externo = resultado_artilheiro_externo
        cobrador = encontrar_jogador_partida(partida, artilheiro)
        goleiro = next(
            item
            for item in partida.jogadores
            if item.casa != cobrador.casa
            and item.posicao == "Goleiro"
            and item.ativo
            and item.em_campo
        )
        self.goleiro = goleiro.nome

    @discord.ui.button(label="Realizar Defesa", style=discord.ButtonStyle.primary)
    async def defender(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._resolver(interaction)

    @discord.ui.button(label="Rolagem Externa", style=discord.ButtonStyle.secondary)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            RolagemExternaModal("Total do Goleiro", self._resolver)
        )

    async def _resolver(
        self,
        interaction: discord.Interaction,
        resultado_goleiro_externo: int | None = None,
    ) -> None:
        await interaction.response.defer()
        resultado: ResultadoPenalti | None = None
        eventos_turno: list[EventoPartida] = []

        def acao(partida: PartidaQuadribol) -> None:
            nonlocal resultado
            resultado = resolver_penalti(
                partida,
                self.artilheiro,
                resultado_artilheiro_externo=self.resultado_artilheiro_externo,
                resultado_goleiro_externo=resultado_goleiro_externo,
            )
            inicio = len(partida.eventos)
            avancar_turno(partida)
            eventos_turno.extend(partida.eventos[inicio:])

        try:
            partida = await self.cog.mutar_partida(self.partida_id, acao)
            await self.cog.atualizar_mensagem(partida)
            await self.cog.publicar_surgimentos(partida, eventos_turno)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.edit_original_response(
                content=f"Não foi possível cobrar o pênalti: {erro}",
                embed=None,
                view=self,
            )
            return
        assert resultado is not None
        evento = embed_resultado_penalti(resultado)
        self.stop()
        await interaction.edit_original_response(
            content=None,
            embed=evento,
            view=PainelResultadoView(self.cog, partida),
        )


class ConfigurarPartidaView(discord.ui.View):
    def __init__(
        self,
        cog: Quadribol,
        usuario_id: int,
        casa_1: str = "",
        casa_2: str = "",
        jogo: str = "",
        tipo_partida: str = "",
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.usuario_id = usuario_id
        self.casa_1 = casa_1
        self.casa_2 = casa_2
        self.jogo = jogo
        self.tipo_partida = tipo_partida
        equipes = list(CASAS) if tipo_partida != "Partida Amistosa" else [item.nome for item in carregar_times_amadores()]
        time_1 = discord.ui.Select(
            placeholder="Primeira equipe",
            options=[
                discord.SelectOption(
                    label=casa,
                    value=casa,
                    emoji=EMOJIS_CASAS.get(casa, "🏏"),
                    default=casa == casa_1,
                )
                for casa in equipes
                if casa != casa_2
            ],
            row=0,
        )
        time_2 = discord.ui.Select(
            placeholder="Equipe adversária",
            options=[
                discord.SelectOption(
                    label=casa,
                    value=casa,
                    emoji=EMOJIS_CASAS.get(casa, "🏏"),
                    description=(
                        "Indisponível quando escolhida como primeira equipe."
                        if casa == casa_1
                        else None
                    ),
                    default=casa == casa_2,
                )
                for casa in equipes
                if casa != casa_1
            ],
            row=1,
        )
        jogo_select = discord.ui.Select(
            placeholder="Jogo da temporada",
            options=[
                discord.SelectOption(
                    label=item,
                    value=item,
                    description=(
                        "Último jogo da temporada."
                        if item == "Final"
                        else f"{item.capitalize()} da temporada."
                    ),
                    default=item == jogo,
                )
                for item in JOGOS_TEMPORADA
            ],
            row=2,
        )
        async def selecionar_time_1(interaction: discord.Interaction) -> None:
            selecionada = time_1.values[0]
            adversaria = "" if selecionada == self.casa_2 else self.casa_2
            await interaction.response.edit_message(
                view=ConfigurarPartidaView(
                    self.cog,
                    self.usuario_id,
                    selecionada,
                    adversaria,
                    self.jogo,
                    self.tipo_partida,
                )
            )

        async def selecionar_time_2(interaction: discord.Interaction) -> None:
            selecionada = time_2.values[0]
            if selecionada == self.casa_1:
                await interaction.response.send_message(
                    "As duas equipes precisam ser diferentes.", ephemeral=True
                )
                return
            await interaction.response.edit_message(
                view=ConfigurarPartidaView(
                    self.cog,
                    self.usuario_id,
                    self.casa_1,
                    selecionada,
                    self.jogo,
                    self.tipo_partida,
                )
            )

        async def selecionar_jogo(interaction: discord.Interaction) -> None:
            await interaction.response.edit_message(
                view=ConfigurarPartidaView(
                    self.cog,
                    self.usuario_id,
                    self.casa_1,
                    self.casa_2,
                    jogo_select.values[0],
                    self.tipo_partida,
                )
            )

        time_1.callback = selecionar_time_1
        time_2.callback = selecionar_time_2
        jogo_select.callback = selecionar_jogo
        self.add_item(time_1)
        self.add_item(time_2)
        if tipo_partida != "Partida Amistosa":
            self.add_item(jogo_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.usuario_id:
            await interaction.response.send_message(
                "Esta configuração pertence a outro moderador.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Iniciar partida", style=discord.ButtonStyle.success, row=4)
    async def iniciar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.casa_1 or not self.casa_2 or not self.tipo_partida or (self.tipo_partida == "Partida Oficial" and not self.jogo):
            await interaction.response.send_message(
                "Escolha as duas equipes adversárias e o jogo da temporada.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            async with self.cog.bloqueio_partidas:
                partida = criar_partida(
                    self.casa_1,
                    self.casa_2,
                    self.jogo or "Amistosa",
                    self.usuario_id,
                    tipo_partida=self.tipo_partida,
                )
                if interaction.channel is None or not hasattr(interaction.channel, "send"):
                    raise ValueError("O canal não permite publicar o painel da partida.")
                mensagem = await interaction.channel.send(
                    embeds=embeds_partida(partida),
                    view=QuadribolView(self.cog, partida),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                partida.canal_id = interaction.channel_id
                partida.mensagem_id = mensagem.id
                salvar_partida(partida)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.edit_original_response(
                content=f"Não foi possível iniciar a partida: {erro}", view=self
            )
            return
        self.stop()
        await interaction.edit_original_response(
            content=(
                f"Partida iniciada: **{self.casa_1} × {self.casa_2}** — "
                f"**{self.jogo}**. O painel público foi publicado neste canal."
            ),
            view=None,
        )


class PerseguirPomoView(discord.ui.View):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(timeout=120)
        self.cog = cog
        self.partida_id = partida.identificador
        self.modo = "normal"
        apanhador = partida.jogador_atual()
        if apanhador is None:
            raise ValueError("Não há jogador no turno atual.")
        if apanhador.posicao != "Apanhador" or not apanhador.ativo or not apanhador.em_campo:
            raise ValueError("Somente o Apanhador ativo pode perseguir o Pomo no próprio turno.")
        if apanhador.perseguiu_pomo_no_turno:
            raise ValueError("O Apanhador já sustentou a perseguição neste turno.")
        ativos = partida.pomos_ativos()
        if not ativos:
            lado_atual = partida.casa_1 if partida.tempo == 1 else partida.casa_2
            if lado_atual in partida.pomos:
                raise ValueError("O Pomo deste tempo já foi capturado.")
            raise ValueError("O Pomo ainda não surgiu.")
        self.jogador = apanhador.nome
        self.pomo_lado = ativos[0]
        opcoes = [
            discord.SelectOption(
                label="Perseguição normal",
                value="normal",
                description=(
                    f"Velocidade {apanhador.velocidade_vassoura}m/s • "
                    f"meta {progresso_necessario_pomo(apanhador)}"
                ),
                default=True,
            )
        ]
        disparada = velocidade_disparada(apanhador)
        usada = apanhador.nome in partida.disparadas_pomo.get(self.pomo_lado, [])
        if disparada and not usada:
            opcoes.append(
                discord.SelectOption(
                    label="Usar Disparada",
                    value="disparada",
                    description=(
                        f"Uma vez neste Pomo • {disparada}m/s • "
                        f"meta {progresso_necessario_por_velocidade(disparada)} neste turno"
                    )[:100],
                )
            )
        modo = discord.ui.Select(
            placeholder="Forma de perseguição",
            options=opcoes,
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            self.modo = modo.values[0]
            _fixar_selecao(modo, self.modo)
            await interaction.response.edit_message(view=self)

        modo.callback = selecionar
        self.add_item(modo)

    @discord.ui.button(label="Rolar perseguição", style=discord.ButtonStyle.success, row=1)
    async def rolar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._resolver(interaction)

    @discord.ui.button(label="Rolagem Externa", style=discord.ButtonStyle.secondary, row=1)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            RolagemExternaModal("Total da perseguição", self._resolver)
        )

    @discord.ui.button(label="Voltar", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)
    async def voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        partida, _ = self.cog._localizar_por_id(self.partida_id)
        self.stop()
        await interaction.response.edit_message(
            embed=_embed_painel_acao(
                partida,
                "⚡ Ações do Turno",
                "Escolha a ação do jogador em destaque.",
            ),
            view=AcoesTurnoView(self.cog, partida),
        )

    async def _resolver(
        self,
        interaction: discord.Interaction,
        resultado_externo: int | None = None,
    ) -> None:
        await interaction.response.defer()
        resultado: ResultadoPomo | None = None
        eventos_turno: list[EventoPartida] = []

        def acao(partida: PartidaQuadribol) -> None:
            nonlocal resultado
            resultado = perseguir_pomo(
                partida,
                self.jogador,
                usar_disparada=self.modo == "disparada",
                resultado_externo=resultado_externo,
            )
            inicio = len(partida.eventos)
            avancar_turno(partida)
            eventos_turno.extend(partida.eventos[inicio:])

        try:
            partida = await self.cog.mutar_partida(self.partida_id, acao)
            await self.cog.atualizar_mensagem(partida)
            await self.cog.publicar_surgimentos(partida, eventos_turno)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.edit_original_response(
                content=f"Não foi possível perseguir o Pomo: {erro}",
                view=self,
            )
            return
        assert resultado is not None
        evento = embed_resultado_pomo(resultado, partida)
        self.stop()
        await interaction.edit_original_response(
            content=None,
            embed=evento,
            view=PainelResultadoView(self.cog, partida),
        )


class TentativaGolView(discord.ui.View):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(timeout=180)
        self.cog = cog
        self.partida_id = partida.identificador
        atual = partida.jogador_atual()
        if atual is None or atual.posicao != "Artilheiro" or not atual.ativo or not atual.em_campo:
            raise ValueError("Somente o Artilheiro em destaque pode tentar marcar um gol.")
        if partida.posse_goles and partida.posse_goles != atual.nome:
            raise ValueError("Somente o Artilheiro em posse da Goles pode tentar marcar um gol.")
        self.artilheiro = atual.nome
        voltar = discord.ui.Button(label="Voltar", emoji="↩️", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar_acoes
        self.add_item(voltar)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        membro = interaction.user
        if isinstance(membro, discord.Member) and membro.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message(
            "Você precisa da permissão **Gerenciar servidor** para controlar a partida.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Realizar Arremesso", style=discord.ButtonStyle.success, row=0)
    async def arremessar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._seguir_para_defesa(interaction)

    @discord.ui.button(label="Rolagem Externa", style=discord.ButtonStyle.secondary, row=0)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            RolagemExternaModal("Total do Artilheiro", self._seguir_para_defesa)
        )

    async def _seguir_para_defesa(
        self,
        interaction: discord.Interaction,
        resultado_artilheiro_externo: int | None = None,
    ) -> None:
        try:
            partida, _ = self.cog._localizar_por_id(self.partida_id)
            artilheiro = encontrar_jogador_partida(partida, self.artilheiro)
            goleiro = next(
                item
                for item in partida.jogadores
                if item.casa != artilheiro.casa
                and item.posicao == "Goleiro"
                and item.ativo
                and item.em_campo
            )
        except (StopIteration, ValueError) as erro:
            mensagem = "A equipe adversária precisa possuir um Goleiro ativo." if isinstance(erro, StopIteration) else str(erro)
            await interaction.response.send_message(mensagem, ephemeral=True)
            return
        view_defesa = DefesaGolView(
            self.cog,
            partida,
            self.artilheiro,
            resultado_artilheiro_externo,
        )
        if await exigir_resistencia_tempo(
            interaction,
            self.cog,
            partida,
            goleiro,
            "defender o arremesso",
            view_defesa,
            self,
        ):
            return
        self.stop()
        await interaction.response.edit_message(
            content=None,
            embed=_embed_cabecalho_rolagem(
                "🧤 Defesa do Goleiro",
                (
                    f"{EMOJIS_CASAS.get(artilheiro.casa, '')} **{artilheiro.nome}** prepara o arremesso. "
                    f"Agora {EMOJIS_CASAS.get(goleiro.casa, '')} **{goleiro.nome}** precisa "
                    + (
                        "identificar o verdadeiro portador antes de tentar a defesa."
                        if any(
                            normalizar_rotulo(efeito.contexto) == "mergulho_falcao"
                            for efeito in artilheiro.efeitos
                        )
                        else "defender."
                    )
                ),
            ),
            view=view_defesa,
        )

    async def voltar_acoes(self, interaction: discord.Interaction) -> None:
        partida, _ = self.cog._localizar_por_id(self.partida_id)
        self.stop()
        await interaction.response.edit_message(
            embed=_embed_painel_acao(
                partida,
                "⚡ Ações do Turno",
                "Escolha a ação do jogador em destaque.",
            ),
            view=AcoesTurnoView(self.cog, partida),
        )


class DefesaGolView(discord.ui.View):
    def __init__(
        self,
        cog: Quadribol,
        partida: PartidaQuadribol,
        artilheiro: str,
        resultado_artilheiro_externo: int | None,
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.partida_id = partida.identificador
        self.artilheiro = artilheiro
        self.resultado_artilheiro_externo = resultado_artilheiro_externo
        jogador = encontrar_jogador_partida(partida, artilheiro)
        self.mergulho_falcao = any(
            normalizar_rotulo(efeito.contexto) == "mergulho_falcao"
            for efeito in jogador.efeitos
        )
        goleiro = next(
            item
            for item in partida.jogadores
            if item.casa != jogador.casa
            and item.posicao == "Goleiro"
            and item.ativo
            and item.em_campo
        )
        self.goleiro = goleiro.nome
        voltar = discord.ui.Button(label="Voltar", emoji="↩️", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar_arremesso
        self.add_item(voltar)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        membro = interaction.user
        if isinstance(membro, discord.Member) and membro.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message(
            "Você precisa da permissão **Gerenciar servidor** para controlar a partida.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Realizar Defesa", style=discord.ButtonStyle.primary, row=0)
    async def defender(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._resolver(interaction)

    @discord.ui.button(label="Rolagem Externa", style=discord.ButtonStyle.secondary, row=0)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.mergulho_falcao:
            await interaction.response.send_modal(
                DefesaMergulhoExternaModal(self._resolver)
            )
        else:
            await interaction.response.send_modal(
                RolagemExternaModal("Total do Goleiro", self._resolver)
            )

    async def _resolver(
        self,
        interaction: discord.Interaction,
        resultado_goleiro_externo: int | None = None,
        resultado_percepcao_externo: int | None = None,
    ) -> None:
        await interaction.response.defer()
        resultado: ResultadoGol | None = None

        def acao(partida: PartidaQuadribol) -> None:
            nonlocal resultado
            resultado = resolver_tentativa_gol(
                partida,
                self.artilheiro,
                resultado_artilheiro_externo=self.resultado_artilheiro_externo,
                resultado_goleiro_externo=resultado_goleiro_externo,
                resultado_percepcao_externo=resultado_percepcao_externo,
            )

        try:
            partida = await self.cog.mutar_partida(self.partida_id, acao)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.edit_original_response(
                content=f"Não foi possível resolver a tentativa de gol: {erro}",
                embed=None,
                view=self,
            )
            return
        assert resultado is not None
        evento = embed_resultado_gol(resultado)
        evento.add_field(
            name="🏐 Reposição da Goles",
            value=(
                "Escolha abaixo o Artilheiro da equipe que sofreu o gol."
                if resultado.gol
                else f"**{resultado.goleiro}** defendeu e escolherá um Artilheiro aliado."
            ),
            inline=False,
        )
        self.stop()
        await interaction.edit_original_response(
            content=None,
            embed=evento,
            view=DistribuirGolesView(self.cog, partida, resultado),
        )

    async def voltar_arremesso(self, interaction: discord.Interaction) -> None:
        partida, _ = self.cog._localizar_por_id(self.partida_id)
        self.stop()
        await interaction.response.edit_message(
            embed=_embed_painel_acao(
                partida,
                "🥅 Tentativa de Gol",
                "Escolha se o Artilheiro fará a rolagem pelo bot ou apresentará o total externo.",
            ),
            view=TentativaGolView(self.cog, partida),
        )


def _partida_da_interacao(interaction: discord.Interaction) -> PartidaQuadribol:
    mensagem_id = interaction.message.id if interaction.message else 0
    encontrado = encontrar_partida_por_mensagem(mensagem_id)
    if encontrado is None:
        raise ValueError("Não encontrei o estado persistido desta partida.")
    return encontrado[0]


def _embed_cabecalho_rolagem(
    titulo: str,
    subtitulo: str,
    *,
    cor: int = COR_QUADRIBOL,
) -> discord.Embed:
    return discord.Embed(
        description=f"# {titulo}\n## {subtitulo}",
        color=cor,
    )


def _embed_painel_acao(
    partida: PartidaQuadribol,
    titulo: str,
    descricao: str,
) -> discord.Embed:
    atual = partida.jogador_atual()
    embed = _embed_cabecalho_rolagem(titulo, descricao)
    embed.add_field(
        name="Jogador em destaque",
        value=_linha_jogador(atual, True) if atual else "--",
        inline=False,
    )
    return embed


def embed_resistencia_tempo(resultado: ResultadoResistenciaTempo) -> discord.Embed:
    if resultado.rolagem_externa:
        calculo = f"Resultado externo de Fortitude: **{resultado.total}**"
    else:
        calculo = (
            f"d20 **{resultado.dado}** + Fortitude **{resultado.fortitude:+d}** "
            f"= **{resultado.total}**"
        )
    if resultado.sucesso:
        desfecho = (
            "✅ **Resistência bem-sucedida.** A ação será realizada sem "
            "penalidade meteorológica."
        )
        cor = 0x57F287
    else:
        desfecho = (
            "❌ **Resistência malsucedida.** A próxima ação receberá "
            f"**{resultado.penalidade:+d}**."
        )
        cor = 0xED4245
    return discord.Embed(
        description=(
            "# 🌦️ Resistência às Condições Meteorológicas\n"
            f"## **{resultado.jogador}** realizou um teste de **Fortitude** contra "
            f"**CD {resultado.cd}**.\n\n{calculo}\n\n{desfecho}\n\n"
            "Escolha agora a ação do turno."
        ),
        color=cor,
    )


def embed_detalhe_manobra(manobra) -> discord.Embed:
    """Apresenta a manobra usando os blocos autoritativos da biblioteca."""
    embed = discord.Embed(
        title=f"🧩 {manobra.nome}",
        description=manobra.descricao or "--",
        color=COR_QUADRIBOL,
    )
    embed.add_field(
        name="CD",
        value="Execução automática" if manobra.cd == 0 else str(manobra.cd),
        inline=True,
    )
    embed.add_field(
        name="Requisito de Quadribol",
        value=f"{manobra.requisito_quadribol:+d}",
        inline=True,
    )
    embed.add_field(
        name="Posições",
        value=", ".join(manobra.posicoes) or "--",
        inline=True,
    )
    embed.add_field(
        name="Participantes",
        value=manobra.participantes or "--",
        inline=False,
    )
    embed.add_field(
        name="Execução",
        value=manobra.execucao or "--",
        inline=False,
    )
    embed.add_field(
        name="Benefício",
        value=manobra.beneficio or "--",
        inline=False,
    )
    return embed


class PainelPartidaView(discord.ui.View):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(timeout=300)
        self.cog = cog
        self.partida_id = partida.identificador
        self._resolucao_em_andamento = False
        self._estado_controles: dict[int, bool] = {}

    async def iniciar_resolucao(self, interaction: discord.Interaction) -> bool:
        """Impede cliques e envios repetidos da mesma ação enquanto ela é resolvida."""
        if self._resolucao_em_andamento:
            mensagem = "Esta ação já está sendo resolvida. Aguarde o resultado."
            if interaction.response.is_done():
                await interaction.followup.send(mensagem, ephemeral=True)
            else:
                await interaction.response.send_message(mensagem, ephemeral=True)
            return False
        self._resolucao_em_andamento = True
        self._estado_controles = {
            id(item): item.disabled
            for item in self.children
            if hasattr(item, "disabled")
        }
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True
        return True

    def liberar_resolucao(self) -> None:
        self._resolucao_em_andamento = False
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = self._estado_controles.get(id(item), item.disabled)
        self._estado_controles.clear()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        membro = interaction.user
        if isinstance(membro, discord.Member) and membro.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message(
            "Você precisa da permissão **Gerenciar servidor** para controlar a partida.",
            ephemeral=True,
        )
        return False

    def carregar(self, interaction: discord.Interaction) -> PartidaQuadribol:
        partida, _ = self.cog._localizar_por_id(self.partida_id)
        return partida

    @discord.ui.button(label="Voltar", emoji="↩️", style=discord.ButtonStyle.secondary, row=4)
    async def voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        await self.cog.fechar_painel_privado(interaction, self.partida_id)


def _efeito_tempo_pendente(jogador) -> object | None:
    if jogador.penalidade_tempo_preparada is not None:
        return None
    return next(
        (
            efeito
            for efeito in jogador.efeitos
            if normalizar_rotulo(efeito.nome) == "tempo meteorologico"
        ),
        None,
    )


def _embed_resistencia_tempo_obrigatoria(
    partida: PartidaQuadribol,
    jogador,
    contexto: str,
) -> discord.Embed:
    efeito = _efeito_tempo_pendente(jogador)
    cd = getattr(efeito, "cd_resistencia", 0)
    intensidade = getattr(efeito, "intensidade", "") or "Padrão"
    embed = _embed_cabecalho_rolagem(
        "🌦️ Resistir a Condições Meteorológicas",
        (
            f"Antes de {contexto}, **{jogador.nome}** precisa realizar um teste de "
            f"**Fortitude** contra **CD {cd}**."
        ),
        cor=0xED4245,
    )
    embed.add_field(
        name="Jogador em ação ou reação",
        value=_linha_jogador(jogador, jogador == partida.jogador_atual()),
        inline=False,
    )
    embed.add_field(
        name="Tempo Meteorológico",
        value=(
            f"**{intensidade} • CD {cd}**\n"
            "Sucesso: continua sem penalidade.\n"
            "Falha: recebe `-(1d4+1)` no teste que realizará em seguida."
        ),
        inline=False,
    )
    return embed


class ResistenciaTempoObrigatoriaView(PainelPartidaView):
    def __init__(
        self,
        cog: Quadribol,
        partida: PartidaQuadribol,
        jogador: str,
        contexto: str,
        view_liberada: discord.ui.View,
        view_anterior: discord.ui.View,
        *,
        content_anterior: str | None,
        embeds_anteriores: list[discord.Embed],
    ):
        super().__init__(cog, partida)
        self.jogador = jogador
        self.contexto = contexto
        self.view_liberada = view_liberada
        self.view_anterior = view_anterior
        self.content_anterior = content_anterior
        self.embeds_anteriores = embeds_anteriores
        self.voltar.callback = self.voltar_etapa
        self.voltar.style = discord.ButtonStyle.secondary
        resistir = discord.ui.Button(
            label="Resistir a Condições Meteorológicas",
            style=discord.ButtonStyle.danger,
            row=0,
        )
        resistir.callback = self.resistir
        self.add_item(resistir)
        externa = discord.ui.Button(
            label="Rolagem Externa",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        externa.callback = self.externa
        self.add_item(externa)

    async def voltar_etapa(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=self.content_anterior,
            embeds=self.embeds_anteriores,
            view=self.view_anterior,
        )

    async def resistir(self, interaction: discord.Interaction) -> None:
        await self._resolver(interaction)

    async def externa(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            RolagemExternaModal("Total final de Fortitude", self._resolver)
        )

    async def _resolver(
        self,
        interaction: discord.Interaction,
        resultado_externo: int | None = None,
    ) -> None:
        await interaction.response.defer()
        resultado: ResultadoResistenciaTempo | None = None

        def acao(item: PartidaQuadribol) -> None:
            nonlocal resultado
            resultado = resolver_resistencia_tempo(
                item,
                self.jogador,
                resultado_externo=resultado_externo,
            )

        try:
            partida = await self.cog.mutar_partida(self.partida_id, acao)
        except (OSError, ValueError) as erro:
            await interaction.edit_original_response(content=str(erro), view=self)
            return
        assert resultado is not None
        embed = embed_resistencia_tempo(resultado)
        embed.add_field(
            name="Próxima etapa liberada",
            value=f"**{self.contexto.capitalize()}** pode continuar agora.",
            inline=False,
        )
        await interaction.edit_original_response(
            content=None,
            embed=embed,
            view=self.view_liberada,
        )


async def exigir_resistencia_tempo(
    interaction: discord.Interaction,
    cog: Quadribol,
    partida: PartidaQuadribol,
    jogador,
    contexto: str,
    view_liberada: discord.ui.View,
    view_anterior: discord.ui.View,
) -> bool:
    if _efeito_tempo_pendente(jogador) is None:
        return False
    mensagem = interaction.message
    conteudo = {
        "content": None,
        "embed": _embed_resistencia_tempo_obrigatoria(partida, jogador, contexto),
        "view": ResistenciaTempoObrigatoriaView(
            cog,
            partida,
            jogador.nome,
            contexto,
            view_liberada,
            view_anterior,
            content_anterior=mensagem.content if mensagem else None,
            embeds_anteriores=list(mensagem.embeds) if mensagem else [],
        ),
    }
    if interaction.response.is_done():
        await interaction.edit_original_response(**conteudo)
    else:
        await interaction.response.edit_message(**conteudo)
    return True


class PainelResultadoView(PainelPartidaView):
    """Mantém o resultado no painel único e permite reutilizá-lo ou fechá-lo."""

    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(cog, partida)
        for item in self.children:
            if getattr(item, "label", "") == "Voltar":
                item.label = "Fechar painel"
                item.emoji = "✖️"

    @discord.ui.button(
        label="Ver turno atual",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def turno_atual(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        partida = self.carregar(interaction)
        atual = partida.jogador_atual()
        if atual is not None and esta_atordoado(atual):
            embed = _embed_painel_acao(
                partida,
                "🩹 Teste de Recuperação",
                (
                    f"**{atual.nome}** está Atordoado e só pode realizar o Teste de "
                    "Recuperação."
                ),
            )
            view: discord.ui.View = RecuperacaoView(self.cog, partida)
        else:
            precisa_tempo = bool(
                atual is not None
                and tem_tempo_meteorologico(atual)
                and atual.penalidade_tempo_preparada is None
            )
            embed = _embed_painel_acao(
                partida,
                "🌦️ Condições Meteorológicas" if precisa_tempo else "⚡ Ações do Turno",
                (
                    "Resista às condições meteorológicas antes de escolher a ação."
                    if precisa_tempo
                    else "Escolha a ação do jogador em destaque."
                ),
            )
            view = AcoesTurnoView(self.cog, partida)
        await interaction.response.edit_message(content=None, embed=embed, view=view)


class DistribuirGolesView(PainelPartidaView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol, resultado: ResultadoGol):
        super().__init__(cog, partida)
        self.resultado = resultado
        self.escolhido = ""
        goleiro = encontrar_jogador_partida(partida, resultado.goleiro)
        candidatos = _jogadores_priorizados(
            partida, artilheiros_ativos(partida, goleiro.casa)
        )
        if not candidatos:
            raise ValueError("A equipe da reposição não possui Artilheiro ativo.")
        seletor = discord.ui.Select(
            placeholder=(
                "Artilheiro da reposição após o gol"
                if resultado.gol
                else "Artilheiro que receberá a Goles do Goleiro"
            ),
            options=[
                discord.SelectOption(
                    label=item.nome[:100],
                    value=item.nome,
                    description=f"{item.casa} • Artilheiro"[:100],
                )
                for item in candidatos
            ],
            row=0,
        )

        async def escolher(interaction: discord.Interaction) -> None:
            self.escolhido = seletor.values[0]
            _fixar_selecao(seletor, self.escolhido)
            await interaction.response.edit_message(view=self)

        seletor.callback = escolher
        self.add_item(seletor)
        for item in list(self.children):
            if getattr(item, "label", "") == "Voltar":
                self.remove_item(item)

    @discord.ui.button(label="Confirmar reposição", style=discord.ButtonStyle.success, row=1)
    async def confirmar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.escolhido:
            await interaction.response.send_message(
                "Escolha o Artilheiro que receberá a Goles.", ephemeral=True
            )
            return
        await interaction.response.defer()
        eventos_turno: list[EventoPartida] = []

        def acao(item: PartidaQuadribol) -> None:
            atribuir_posse_goles(
                item,
                self.escolhido,
                motivo=(
                    "para reiniciar o jogo após sofrer o gol"
                    if self.resultado.gol
                    else f"das mãos de {self.resultado.goleiro} após a defesa"
                ),
            )
            inicio = len(item.eventos)
            avancar_turno(item)
            eventos_turno.extend(item.eventos[inicio:])

        try:
            partida = await self.cog.mutar_partida(self.partida_id, acao)
            await self.cog.atualizar_mensagem(partida)
            await self.cog.publicar_surgimentos(partida, eventos_turno)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.edit_original_response(
                content=f"Não foi possível concluir a reposição: {erro}",
                embed=None,
                view=self,
            )
            return
        embed = embed_resultado_gol(self.resultado)
        embed.add_field(
            name="🏐 Reposição concluída",
            value=f"**{self.escolhido}** recebeu a Goles.",
            inline=False,
        )
        self.stop()
        await interaction.edit_original_response(
            content=None,
            embed=embed,
            view=PainelResultadoView(self.cog, partida),
        )


def embed_resultado_posse(resultado: ResultadoPosse) -> discord.Embed:
    ataque = _formatar_fontes_rolagem(
        resultado.fontes_atacante, resultado.total_atacante
    )
    defesa = _formatar_fontes_rolagem(
        resultado.fontes_defensor, resultado.total_defensor
    )
    if resultado.acao == "Tomar a Goles":
        titulo_ataque = f"Atletismo — {resultado.atacante}"
        titulo_defesa = f"Reflexo — {resultado.defensor}"
        desfecho = (
            f"**{resultado.atacante}** toma a Goles."
            if resultado.sucesso
            else f"**{resultado.defensor}** protege a Goles."
        )
    else:
        titulo_ataque = f"Passe de Pontaria — {resultado.atacante}"
        titulo_defesa = f"Interceptação de Reflexo — {resultado.defensor}"
        desfecho = (
            f"O passe chega a **{resultado.destinatario}**."
            if resultado.sucesso
            else f"**{resultado.defensor}** intercepta e toma a Goles."
        )
        if resultado.sucesso:
            desfecho += (
                "\n🎯 **Bônus no próximo arremesso:** "
                f"{resultado.bonus_passes_acumulado:+d}"
            )
        elif resultado.sequencia_passes_interrompida:
            desfecho += "\n💨 **Sequência de passes interrompida.**"
    return discord.Embed(
        title=f"🏐 {resultado.acao}",
        description=(
            f"**{titulo_ataque}**\n{ataque}\n\n"
            f"**{titulo_defesa}**\n{defesa}\n\n"
            f"{desfecho}\n\n**Nova posse:** {resultado.novo_portador}"
        ),
        color=0x57F287 if resultado.sucesso else 0xFEE75C,
    )


class PosseGolesView(PainelPartidaView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol, acao: str):
        super().__init__(cog, partida)
        self.acao = acao
        self.destinatario = ""
        self.interceptador = ""
        atual = partida.jogador_atual()
        if atual is None or atual.posicao != "Artilheiro":
            raise ValueError("Somente um Artilheiro pode realizar esta ação.")
        self.jogador_turno = atual.nome
        try:
            portador = encontrar_jogador_partida(partida, partida.posse_goles)
        except ValueError:
            raise ValueError("A partida ainda não possui um portador válido da Goles.") from None
        self.portador = portador.nome
        self.voltar.callback = self.voltar_acoes

        if acao == "passar":
            aliados = [
                item
                for item in artilheiros_ativos(partida, atual.casa)
                if item.nome != atual.nome
            ]
            destino = discord.ui.Select(
                placeholder="Artilheiro aliado que receberá a Goles",
                options=[
                    discord.SelectOption(
                        label=item.nome[:100],
                        value=item.nome,
                        description=f"Pontaria {_texto_bonus(item.bonus_teste_posicao)} • Reflexo {_texto_bonus(item.reflexo)}"[:100],
                    )
                    for item in _jogadores_priorizados(partida, aliados)
                ],
                row=0,
            )

            async def escolher_destino(interaction: discord.Interaction) -> None:
                self.destinatario = destino.values[0]
                _fixar_selecao(destino, self.destinatario)
                await interaction.response.edit_message(view=self)

            destino.callback = escolher_destino
            self.add_item(destino)
        else:
            self.destinatario = atual.nome if acao == "pedir" else ""

        if acao in {"passar", "pedir"}:
            adversarios = artilheiros_ativos(
                partida, next(casa for casa in partida.casas() if casa != atual.casa)
            )
            interceptador = discord.ui.Select(
                placeholder="Artilheiro adversário que tentará interceptar",
                options=[
                    discord.SelectOption(
                        label=item.nome[:100],
                        value=item.nome,
                        description=f"Reflexo {_texto_bonus(item.reflexo)}"[:100],
                    )
                    for item in _jogadores_priorizados(partida, adversarios)
                ],
                row=1,
            )

            async def escolher_interceptador(interaction: discord.Interaction) -> None:
                self.interceptador = interceptador.values[0]
                _fixar_selecao(interceptador, self.interceptador)
                await interaction.response.edit_message(view=self)

            interceptador.callback = escolher_interceptador
            self.add_item(interceptador)

    async def voltar_acoes(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        self.stop()
        await interaction.response.edit_message(
            embed=_embed_painel_acao(
                partida, "⚡ Ações do Turno", "Escolha a ação do jogador em destaque."
            ),
            view=AcoesTurnoView(self.cog, partida),
        )

    @discord.ui.button(label="Concluir", style=discord.ButtonStyle.success, row=3)
    async def concluir(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if await self._exigir_tempo_oponente(interaction):
            return
        await self._resolver(interaction)

    @discord.ui.button(label="Rolagem Externa", style=discord.ButtonStyle.secondary, row=3)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.acao in {"passar", "pedir"} and (
            not self.destinatario or not self.interceptador
        ):
            await interaction.response.send_message(
                "Escolha o destinatário e o Artilheiro que tentará interceptar.",
                ephemeral=True,
            )
            return
        if await self._exigir_tempo_oponente(interaction):
            return
        if self.acao == "tomar":
            modal = RolagensOpostasModal(
                f"Atletismo — {self.jogador_turno}",
                f"Reflexo — {self.portador}",
                self._resolver,
                titulo="Tomada da Goles — Resultados",
                ajuda_atacante="Total final de quem tenta tomar a Goles",
                ajuda_defensor="Total final de quem protege a Goles",
            )
        else:
            modal = RolagensOpostasModal(
                f"Pontaria — {self.portador}",
                f"Reflexo — {self.interceptador}",
                self._resolver,
                titulo="Passe × Interceptação — Resultados",
                ajuda_atacante=f"Total final do passe para {self.destinatario}",
                ajuda_defensor="Total final da tentativa de interceptação",
            )
        await interaction.response.send_modal(modal)

    async def _exigir_tempo_oponente(self, interaction: discord.Interaction) -> bool:
        if self.acao in {"passar", "pedir"} and not self.interceptador:
            return False
        partida = self.carregar(interaction)
        nome = self.portador if self.acao == "tomar" else self.interceptador
        defensor = encontrar_jogador_partida(partida, nome)
        return await exigir_resistencia_tempo(
            interaction,
            self.cog,
            partida,
            defensor,
            "reagir à disputa pela Goles",
            self,
            self,
        )

    async def _resolver(
        self,
        interaction: discord.Interaction,
        resultado_atacante_externo: int | None = None,
        resultado_defensor_externo: int | None = None,
    ) -> None:
        if self.acao in {"passar", "pedir"} and (
            not self.destinatario or not self.interceptador
        ):
            await interaction.response.send_message(
                "Escolha o destinatário e o Artilheiro que tentará interceptar.",
                ephemeral=True,
            )
            return
        if not await self.iniciar_resolucao(interaction):
            return
        jogador_turno = self.jogador_turno
        destinatario = self.destinatario
        interceptador = self.interceptador
        await interaction.response.defer()
        await interaction.edit_original_response(view=self)
        resultado: ResultadoPosse | None = None
        eventos_turno: list[EventoPartida] = []

        def acao_mutacao(item: PartidaQuadribol) -> None:
            nonlocal resultado
            if self.acao == "tomar":
                resultado = resolver_tomada_goles(
                    item,
                    jogador_turno,
                    resultado_atletismo_externo=resultado_atacante_externo,
                    resultado_reflexo_externo=resultado_defensor_externo,
                )
            else:
                resultado = resolver_passe_goles(
                    item,
                    jogador_turno,
                    destinatario,
                    interceptador,
                    resultado_passe_externo=resultado_atacante_externo,
                    resultado_interceptacao_externo=resultado_defensor_externo,
                )
            inicio = len(item.eventos)
            avancar_turno(item)
            eventos_turno.extend(item.eventos[inicio:])

        try:
            partida = await self.cog.mutar_partida(self.partida_id, acao_mutacao)
            await self.cog.atualizar_mensagem(partida)
            await self.cog.publicar_surgimentos(partida, eventos_turno)
        except (OSError, ValueError, discord.HTTPException) as erro:
            self.liberar_resolucao()
            await interaction.edit_original_response(
                content=f"Não foi possível concluir a disputa pela Goles: {erro}",
                embed=None,
                view=self,
            )
            return
        assert resultado is not None
        self.stop()
        await interaction.edit_original_response(
            content=None,
            embed=embed_resultado_posse(resultado),
            view=PainelResultadoView(self.cog, partida),
        )


class FortitudeTempoExternaView(PainelPartidaView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(cog, partida)
        self.jogador = ""
        self.voltar.callback = self.voltar_acoes
        afetados = _jogadores_priorizados(
            partida,
            [
                jogador
                for jogador in partida.jogadores
                if jogador.ativo
                and jogador.em_campo
                and tem_tempo_meteorologico(jogador)
            ],
        )
        if not afetados:
            raise ValueError("Nenhum jogador ativo está sob Tempo Meteorológico.")
        seletor = discord.ui.Select(
            placeholder="Jogador que apresentará Fortitude externa",
            options=[
                discord.SelectOption(
                    label=jogador.nome[:100],
                    value=jogador.nome,
                    description=(
                        f"{jogador.casa} • {jogador.posicao} • "
                        f"Fortitude {_texto_bonus(jogador.fortitude)}"
                    )[:100],
                )
                for jogador in afetados[:25]
            ],
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            self.jogador = seletor.values[0]
            _fixar_selecao(seletor, self.jogador)
            await interaction.response.edit_message(view=self)

        seletor.callback = selecionar
        self.add_item(seletor)

    async def voltar_acoes(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content=None,
            embed=_embed_painel_acao(
                partida,
                "⚡ Ações do Turno",
                "Escolha a ação do jogador em destaque.",
            ),
            view=AcoesTurnoView(self.cog, partida),
        )

    @discord.ui.button(label="Rolagem Externa", style=discord.ButtonStyle.secondary, row=1)
    async def informar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.jogador:
            await interaction.response.send_message(
                "Escolha primeiro o jogador que realizou a Fortitude.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            RolagemExternaModal("Total de Fortitude", self._salvar)
        )

    async def _salvar(self, interaction: discord.Interaction, resultado: int) -> None:
        try:
            partida = await self.cog.mutar_partida(
                self.partida_id,
                lambda item: preparar_fortitude_tempo_externa(
                    item, self.jogador, resultado
                ),
            )
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(
            content=(
                f"Fortitude externa **{resultado}** preparada para a próxima ação de "
                f"**{self.jogador}**."
            ),
            embed=_embed_painel_acao(
                partida,
                "⚡ Ações do Turno",
                "Escolha a ação do jogador em destaque.",
            ),
            view=AcoesTurnoView(self.cog, partida),
        )


def embed_resultado_habilidade(resultado: ResultadoHabilidade) -> discord.Embed:
    if resultado.habilidade == "Rei":
        descricao = (
            f"**{resultado.executor}** orientou **{resultado.alvo}**.\n\n"
            f"🎯 **Efeito preparado:** `{resultado.bonus:+d}` na próxima ação com rolagem "
            "do aliado. O bônus será aplicado e consumido automaticamente."
        )
        cor = 0x5865F2
    else:
        calculo = (
            f"Resultado externo: **{resultado.total}**"
            if resultado.rolagem_externa
            else f"d20 **{resultado.dado}** + bônus **{resultado.bonus:+d}** = **{resultado.total}**"
        )
        descricao = (
            f"**{resultado.executor}** acolheu **{resultado.alvo}**.\n"
            f"{calculo} contra **CD {resultado.cd}**.\n\n"
            + (
                f"✅ **Sucesso:** {resultado.efeito}."
                if resultado.sucesso
                else f"❌ **Falha:** {resultado.efeito}."
            )
        )
        cor = 0x57F287 if resultado.sucesso else 0xED4245
    return discord.Embed(
        title=f"✨ {resultado.habilidade}",
        description=descricao,
        color=cor,
    )


class HabilidadeView(PainelPartidaView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(cog, partida)
        atual = partida.jogador_atual()
        if atual is None or not atual.ativo or not atual.em_campo:
            raise ValueError("Não há jogador ativo no turno atual.")
        self.executor = atual.nome
        self.habilidade = ""
        self.alvo = ""
        self.condicao = ""
        habilidades = habilidades_executaveis_quadribol(atual)
        if not habilidades:
            raise ValueError(f"{atual.nome} não possui habilidade ativa utilizável no Quadribol.")

        seletor_habilidade = discord.ui.Select(
            placeholder="Habilidade do personagem",
            options=[
                discord.SelectOption(
                    label=nome,
                    value=nome,
                    description=(
                        "Oriente um aliado com seu modificador de Carisma."
                        if normalizar_rotulo(nome) == "rei"
                        else "Acolha um aliado e tente remover uma condição emocional."
                    ),
                )
                for nome in habilidades
            ],
            row=0,
        )
        seletor_alvo = discord.ui.Select(
            placeholder="Escolha primeiro a habilidade",
            options=[discord.SelectOption(label="Escolha primeiro a habilidade", value="-")],
            disabled=True,
            row=1,
        )
        seletor_condicao = discord.ui.Select(
            placeholder="Condição emocional a aliviar",
            options=[discord.SelectOption(label="Escolha primeiro o aliado", value="-")],
            disabled=True,
            row=2,
        )

        async def escolher_habilidade(interaction: discord.Interaction) -> None:
            partida_atual = self.carregar(interaction)
            executor = encontrar_jogador_partida(partida_atual, self.executor)
            self.habilidade = seletor_habilidade.values[0]
            _fixar_selecao(seletor_habilidade, self.habilidade)
            self.alvo = ""
            self.condicao = ""
            poeta_artista = (
                normalizar_rotulo(self.habilidade)
                == normalizar_rotulo("Poeta // Artista")
            )
            alvos = _jogadores_priorizados(
                partida_atual,
                [
                    item
                    for item in partida_atual.jogadores
                    if item.casa == executor.casa and item.ativo and item.em_campo
                ],
            )
            if poeta_artista:
                alvos = [
                    item
                    for item in alvos
                    if any(efeito.categoria == "Estado emocional" for efeito in item.efeitos)
                ]
            seletor_alvo.placeholder = (
                "Nenhum aliado com condição emocional ativa"
                if poeta_artista and not alvos
                else "Aliado beneficiado"
            )
            seletor_alvo.options = (
                [
                    discord.SelectOption(
                        label=item.nome[:100],
                        value=item.nome,
                        description=f"{item.casa} • {item.posicao}"[:100],
                    )
                    for item in alvos[:25]
                ]
                or [discord.SelectOption(label="Nenhum aliado elegível", value="-")]
            )
            seletor_alvo.disabled = not alvos
            _fixar_selecao(seletor_alvo, "")
            seletor_condicao.options = [
                discord.SelectOption(label="Escolha primeiro o aliado", value="-")
            ]
            seletor_condicao.disabled = True
            await interaction.response.edit_message(
                embed=_embed_cabecalho_rolagem(
                    f"✨ {self.habilidade}",
                    (
                        "Escolha o aliado que receberá o modificador de Carisma na próxima ação."
                        if normalizar_rotulo(self.habilidade) == "rei"
                        else (
                            "Escolha um aliado afetado e a condição emocional que deseja aliviar. "
                            "O teste recebe **+4** e enfrenta a mesma CD da condição."
                            + (
                                "\n\n⚠️ **Nenhum aliado possui uma condição emocional negativa ativa.** "
                                "Tempo Meteorológico, Atordoamento e efeitos de manobra não podem "
                                "ser removidos por esta habilidade."
                                if not alvos
                                else ""
                            )
                        )
                    ),
                    cor=0x5865F2,
                ),
                view=self,
            )

        async def escolher_alvo(interaction: discord.Interaction) -> None:
            self.alvo = seletor_alvo.values[0]
            _fixar_selecao(seletor_alvo, self.alvo)
            self.condicao = ""
            partida_atual = self.carregar(interaction)
            if normalizar_rotulo(self.habilidade) == normalizar_rotulo("Poeta // Artista"):
                alvo = encontrar_jogador_partida(partida_atual, self.alvo)
                condicoes = [
                    efeito
                    for efeito in alvo.efeitos
                    if efeito.categoria == "Estado emocional"
                ]
                seletor_condicao.options = [
                    discord.SelectOption(
                        label=efeito.nome[:100],
                        value=efeito.nome,
                        description=f"CD {efeito.cd_resistencia} • {efeito.intensidade}"[:100],
                    )
                    for efeito in condicoes[:25]
                ]
                seletor_condicao.disabled = not condicoes
                _fixar_selecao(seletor_condicao, "")
            else:
                seletor_condicao.disabled = True
            await interaction.response.edit_message(view=self)

        async def escolher_condicao(interaction: discord.Interaction) -> None:
            self.condicao = seletor_condicao.values[0]
            _fixar_selecao(seletor_condicao, self.condicao)
            await interaction.response.edit_message(view=self)

        seletor_habilidade.callback = escolher_habilidade
        seletor_alvo.callback = escolher_alvo
        seletor_condicao.callback = escolher_condicao
        self.add_item(seletor_habilidade)
        self.add_item(seletor_alvo)
        self.add_item(seletor_condicao)
        self.voltar.callback = self.voltar_acoes

    async def voltar_acoes(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content=None,
            embed=_embed_painel_acao(
                partida, "⚡ Ações do Turno", "Escolha a ação do jogador em destaque."
            ),
            view=AcoesTurnoView(self.cog, partida),
        )

    @discord.ui.button(label="Executar habilidade", style=discord.ButtonStyle.primary, row=3)
    async def executar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._executar(interaction)

    @discord.ui.button(label="Rolagem Externa", style=discord.ButtonStyle.secondary, row=3)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if normalizar_rotulo(self.habilidade) != normalizar_rotulo("Poeta // Artista"):
            await interaction.response.send_message(
                "A habilidade selecionada não exige rolagem externa.", ephemeral=True
            )
            return
        if not self.alvo or not self.condicao:
            await interaction.response.send_message(
                "Escolha o aliado e a condição emocional.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            RolagemExternaModal("Total final do teste com +4", self._executar)
        )

    async def _executar(
        self,
        interaction: discord.Interaction,
        resultado_externo: int | None = None,
    ) -> None:
        if not self.habilidade or not self.alvo:
            await interaction.response.send_message(
                "Escolha a habilidade e o aliado beneficiado.", ephemeral=True
            )
            return
        if (
            normalizar_rotulo(self.habilidade) == normalizar_rotulo("Poeta // Artista")
            and not self.condicao
        ):
            await interaction.response.send_message(
                "Escolha a condição emocional que será aliviada.", ephemeral=True
            )
            return
        if not await self.iniciar_resolucao(interaction):
            return
        habilidade = self.habilidade
        alvo = self.alvo
        condicao = self.condicao
        await interaction.response.defer()
        await interaction.edit_original_response(view=self)
        resultado: ResultadoHabilidade | None = None
        eventos_turno: list[EventoPartida] = []

        def aplicar(item: PartidaQuadribol) -> None:
            nonlocal resultado
            if normalizar_rotulo(habilidade) == "rei":
                resultado = executar_rei(item, self.executor, alvo)
            else:
                resultado = executar_poeta(
                    item,
                    self.executor,
                    alvo,
                    condicao,
                    resultado_externo=resultado_externo,
                )
            inicio = len(item.eventos)
            avancar_turno(item)
            eventos_turno.extend(item.eventos[inicio:])

        try:
            partida = await self.cog.mutar_partida(self.partida_id, aplicar)
            await self.cog.atualizar_mensagem(partida)
            await self.cog.publicar_surgimentos(partida, eventos_turno)
        except (OSError, ValueError, discord.HTTPException) as erro:
            self.liberar_resolucao()
            await interaction.edit_original_response(
                content=f"Não foi possível executar a habilidade: {erro}",
                embed=None,
                view=self,
            )
            return
        assert resultado is not None
        self.stop()
        await interaction.edit_original_response(
            content=None,
            embed=embed_resultado_habilidade(resultado),
            view=PainelResultadoView(self.cog, partida),
        )


class AcoesTurnoView(PainelPartidaView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(cog, partida)
        for item in self.children:
            if getattr(item, "label", "") == "Voltar":
                item.style = discord.ButtonStyle.secondary
                item.row = 2
        atual = partida.jogador_atual()
        if (
            atual is not None
            and tem_tempo_meteorologico(atual)
            and atual.penalidade_tempo_preparada is None
        ):
            for item in list(self.children):
                if getattr(item, "label", "") != "Voltar":
                    self.remove_item(item)
            resistir = discord.ui.Button(
                label="Resistir a Condições Meteorológicas",
                style=discord.ButtonStyle.danger,
                custom_id="quadribol:acao:tempo:resistir",
                row=0,
            )
            resistir.callback = self.resistir_tempo
            self.add_item(resistir)
            externa = discord.ui.Button(
                label="Rolagem Externa",
                style=discord.ButtonStyle.secondary,
                custom_id="quadribol:acao:tempo:resistir:externa",
                row=1,
            )
            externa.callback = self.resistir_tempo_externo
            self.add_item(externa)
            return
        posicao = atual.posicao if atual is not None else ""
        manobras_compativeis = bool(
            atual
            and any(
                (not manobra.posicoes or atual.posicao in manobra.posicoes)
                and atual.quadribol >= manobra.requisito_quadribol
                for manobra in carregar_manobras()
            )
        )
        habilidades_compativeis = bool(
            atual and habilidades_executaveis_quadribol(atual)
        )
        for item in list(self.children):
            rotulo = getattr(item, "label", "")
            if rotulo == "Executar Manobra" and not manobras_compativeis:
                self.remove_item(item)
            elif rotulo == "Executar Habilidade" and not habilidades_compativeis:
                self.remove_item(item)
        exclusivos = {
            "Marcar Gol": "Artilheiro",
            "Perseguir Pomo": "Apanhador",
        }
        for item in list(self.children):
            exigida = exclusivos.get(getattr(item, "label", ""))
            if exigida and posicao != exigida:
                self.remove_item(item)
        if posicao == "Artilheiro" and atual is not None:
            try:
                portador = encontrar_jogador_partida(partida, partida.posse_goles)
            except ValueError:
                portador = None
            if portador is not None and portador.nome != atual.nome:
                for item in list(self.children):
                    if getattr(item, "label", "") == "Marcar Gol":
                        self.remove_item(item)
            if portador is not None:
                if portador.nome == atual.nome:
                    rotulo_posse, acao_posse = "Passar a Goles", "passar"
                elif portador.casa == atual.casa:
                    rotulo_posse, acao_posse = "Pedir Passe", "pedir"
                else:
                    rotulo_posse, acao_posse = "Tomar a Goles", "tomar"
                botao_posse = discord.ui.Button(
                    label=rotulo_posse,
                    style=discord.ButtonStyle.success,
                    custom_id=f"quadribol:acao:goles:{acao_posse}",
                    row=0,
                )

                async def abrir_posse(interaction: discord.Interaction) -> None:
                    partida_atual = self.carregar(interaction)
                    atual_atual = partida_atual.jogador_atual()
                    portador_atual = encontrar_jogador_partida(
                        partida_atual, partida_atual.posse_goles
                    )
                    if acao_posse == "passar":
                        descricao = (
                            f"**{atual_atual.nome}** escolhe um Artilheiro aliado para receber "
                            "a Goles e um adversário para tentar interceptar."
                        )
                    elif acao_posse == "pedir":
                        descricao = (
                            f"**{atual_atual.nome}** pede a Goles a **{portador_atual.nome}**. "
                            "Escolha quem tentará interceptar o passe."
                        )
                    else:
                        descricao = (
                            f"**{atual_atual.nome}** tentará tomar a Goles de "
                            f"**{portador_atual.nome}** usando Atletismo "
                            f"{_texto_bonus(atual_atual.atletismo)} "
                            f"({atual_atual.atributo_atletismo or 'maior atributo'})."
                        )
                    await interaction.response.edit_message(
                        embed=_embed_painel_acao(
                            partida_atual, f"🏐 {rotulo_posse}", descricao
                        ),
                        view=PosseGolesView(self.cog, partida_atual, acao_posse),
                    )

                botao_posse.callback = abrir_posse
                self.add_item(botao_posse)
        if posicao == "Batedor":
            acertar = discord.ui.Button(
                label="Acertar Alvo",
                style=discord.ButtonStyle.success,
                custom_id="quadribol:acao:acertar_alvo",
                row=0,
            )
            acertar.callback = self.acertar_alvo
            self.add_item(acertar)

    async def resistir_tempo(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        atual = partida.jogador_atual()
        if atual is None:
            await interaction.response.send_message(
                "Não há jogador no turno atual.", ephemeral=True
            )
            return
        resultado: ResultadoResistenciaTempo | None = None

        def resolver(item: PartidaQuadribol) -> None:
            nonlocal resultado
            resultado = resolver_resistencia_tempo(item, atual.nome)

        try:
            partida = await self.cog.mutar_partida(self.partida_id, resolver)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        assert resultado is not None
        await interaction.response.edit_message(
            content=None,
            embed=embed_resistencia_tempo(resultado),
            view=AcoesTurnoView(self.cog, partida),
        )

    async def resistir_tempo_externo(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            RolagemExternaModal("Total final de Fortitude", self._salvar_resistencia_tempo)
        )

    async def _salvar_resistencia_tempo(
        self,
        interaction: discord.Interaction,
        resultado_externo: int,
    ) -> None:
        partida_atual = self.carregar(interaction)
        atual = partida_atual.jogador_atual()
        if atual is None:
            await interaction.response.send_message(
                "Não há jogador no turno atual.", ephemeral=True
            )
            return
        resultado: ResultadoResistenciaTempo | None = None

        def resolver(item: PartidaQuadribol) -> None:
            nonlocal resultado
            resultado = resolver_resistencia_tempo(
                item, atual.nome, resultado_externo=resultado_externo
            )

        try:
            partida = await self.cog.mutar_partida(self.partida_id, resolver)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        assert resultado is not None
        await interaction.response.edit_message(
            content=None,
            embed=embed_resistencia_tempo(resultado),
            view=AcoesTurnoView(self.cog, partida),
        )

    @discord.ui.button(label="Executar Manobra", style=discord.ButtonStyle.primary, row=1)
    async def manobra(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        partida = self.carregar(interaction)
        texto = (
            "Consulte a CD, os participantes e o benefício. Manobras individuais usam o jogador "
            "em destaque; manobras coletivas pedem um Coordenador da mesma equipe."
        )
        await interaction.response.edit_message(
            content=None,
            embed=_embed_painel_acao(partida, "🧩 Executar Manobra", texto),
            view=ManobraView(self.cog, partida),
        )

    @discord.ui.button(label="Executar Habilidade", style=discord.ButtonStyle.primary, row=1)
    async def habilidade(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        partida = self.carregar(interaction)
        atual = partida.jogador_atual()
        if atual is None or not habilidades_executaveis_quadribol(atual):
            await interaction.response.send_message(
                "O jogador em destaque não possui habilidade ativa utilizável no Quadribol.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            content=None,
            embed=_embed_painel_acao(
                partida,
                "✨ Executar Habilidade",
                "Escolha uma habilidade realmente presente na ficha e quem será beneficiado.",
            ),
            view=HabilidadeView(self.cog, partida),
        )

    @discord.ui.button(label="Efeitos e Condições", style=discord.ButtonStyle.secondary, row=2)
    async def condicao(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        partida = self.carregar(interaction)
        await interaction.response.edit_message(
            content=None,
            embed=_embed_painel_acao(
                partida,
                "⏳ Efeitos e Condições",
                "Escolha a condição narrativa e os envolvidos. Efeitos com duração definida terminam automaticamente; impactos e manobras são aplicados por suas próprias ações.",
            ),
            view=EscolherCondicaoCatalogadaView(self.cog, partida, "Efeito narrativo"),
        )

    @discord.ui.button(label="Marcar Gol", style=discord.ButtonStyle.success, row=0)
    async def gol(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        partida = self.carregar(interaction)
        atual = partida.jogador_atual()
        if atual is None:
            descricao = "Não há jogador ativo neste turno."
        elif atual.posicao != "Artilheiro":
            descricao = f"**{atual.nome}** é {atual.posicao}. Somente um Artilheiro pode concluir a jogada com um gol."
        else:
            descricao = (
                f"**{atual.nome}** tentará superar o Goleiro adversário. "
                "Escolha entre a rolagem automática do bot e o total de uma rolagem externa."
            )
        try:
            view = TentativaGolView(self.cog, partida)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=_embed_painel_acao(partida, "🥅 Tentativa de Gol", descricao),
            view=view,
        )

    @discord.ui.button(label="Perseguir Pomo", style=discord.ButtonStyle.success, row=0)
    async def pomo(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        partida = self.carregar(interaction)
        atual = partida.jogador_atual()
        try:
            view = PerseguirPomoView(self.cog, partida)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        lado = partida.pomos_ativos()[0]
        progresso = partida.progresso_pomos.get(lado, {}).get(atual.casa, 0)
        meta = progresso_necessario_pomo(atual)
        await interaction.response.edit_message(
            embed=_embed_painel_acao(
                partida,
                "🟡 Perseguir Pomo",
                f"**{atual.nome}** está em **{progresso}/{meta}** no Pomo do lado de **{lado}**. Escolha a forma de perseguição e faça a rolagem.",
            ),
            view=view,
        )

    async def acertar_alvo(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        atual = partida.jogador_atual()
        try:
            view = BalacoView(self.cog, partida)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        descricao = (
            f"**{atual.nome}** é o Batedor atacante. Escolha o alvo e a forma de "
            "rebater o Balaço. O bot rolará o ataque e a defesa escolhida."
        )
        await interaction.response.edit_message(
            content=None,
            embed=_embed_painel_acao(partida, "💥 Acertar Alvo", descricao),
            view=view,
        )

    async def fortitude_tempo_externa(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        try:
            view = FortitudeTempoExternaView(self.cog, partida)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embed=_embed_painel_acao(
                partida,
                "🌦️ Fortitude contra o Tempo",
                "Escolha qualquer jogador afetado. O total externo será usado somente na próxima ação dele; se não houver resultado preparado, o bot rolará normalmente.",
            ),
            view=view,
        )


class DetalheAcaoView(PainelPartidaView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol, acao: str):
        super().__init__(cog, partida)
        self.acao = acao
        self.voltar.callback = self.voltar_acoes
        if acao == "defesa":
            return
        rotulos = {
            "manobra": "Escolher Manobra",
            "gol": "Confirmar Gol",
            "balaco": "Escolher Alvo",
        }
        continuar = discord.ui.Button(
            label=rotulos[acao],
            style=discord.ButtonStyle.success,
            custom_id=f"quadribol:acao:{acao}:continuar",
            row=0,
        )
        continuar.callback = self.continuar
        self.add_item(continuar)

    async def voltar_acoes(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        self.stop()
        await interaction.response.edit_message(
            embed=_embed_painel_acao(
                partida,
                "⚡ Ações do Turno",
                "Escolha a ação do jogador em destaque.",
            ),
            view=AcoesTurnoView(self.cog, partida),
        )

    async def continuar(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        try:
            if self.acao == "manobra":
                view = ManobraView(self.cog, partida)
                texto = "Escolha a manobra. Se ela for coletiva, escolha também o Coordenador da manobra."
            elif self.acao == "balaco":
                atual = partida.jogador_atual()
                if atual is None or atual.posicao != "Batedor":
                    raise ValueError("Somente o Batedor em destaque pode acertar um alvo.")
                view = BalacoView(self.cog, partida)
                texto = (
                    f"**{atual.nome}** é o Batedor atacante. "
                    "Escolha o alvo e a forma de rebater o Balaço."
                )
            else:
                atual = partida.jogador_atual()
                if atual is None or atual.posicao != "Artilheiro":
                    raise ValueError("Somente o Artilheiro em destaque pode confirmar o gol.")
                eventos_turno: list[EventoPartida] = []

                def marcar_gol(item: PartidaQuadribol) -> None:
                    adicionar_gol(item, atual.casa)
                    inicio = len(item.eventos)
                    avancar_turno(item)
                    eventos_turno.extend(item.eventos[inicio:])

                partida = await self.cog.mutar_partida(
                    partida.identificador,
                    marcar_gol,
                )
                await interaction.response.edit_message(
                    embeds=embeds_partida(partida),
                    view=QuadribolView(self.cog, partida),
                )
                await self.cog.publicar_surgimentos(partida, eventos_turno)
                return
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(content=texto, view=view)


class QuadribolView(discord.ui.View):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.partida_id = partida.identificador if partida is not None else ""
        casas = partida.casas() if partida else ("Time 1", "Time 2")
        ativa = partida is None or partida.estado == "ativa"
        penalti_pendente = partida is not None and bool(partida.penalti_casa)
        reposicao_pendente = partida is not None and bool(partida.reposicao_goles_casa)
        atual = partida.jogador_atual() if partida is not None else None
        recuperacao_pendente = bool(
            ativa
            and atual is not None
            and esta_atordoado(atual)
            and not penalti_pendente
            and not reposicao_pendente
        )
        livre = ativa and not penalti_pendente and not reposicao_pendente
        intervalo = partida is not None and partida.estado == "intervalo"
        aguardando = partida is not None and partida.estado == "aguardando_confirmacao"
        encerrada = partida is not None and partida.estado == "encerrada"
        if aguardando:
            rotulo_encerrar = "Confirmar encerramento"
        elif intervalo:
            rotulo_encerrar = "Iniciar 2º tempo"
        elif partida is not None and partida.tempo == 1:
            rotulo_encerrar = "Encerrar 1º tempo"
        else:
            rotulo_encerrar = "Encerrar por tempo"

        if recuperacao_pendente:
            botao_recuperacao = discord.ui.Button(
                label="Teste de Recuperação",
                custom_id="quadribol:recuperacao-atordoamento",
                style=discord.ButtonStyle.danger,
                row=0,
            )
            botao_recuperacao.callback = self.abrir_recuperacao_atordoamento
            self.add_item(botao_recuperacao)
            botao_rodada = discord.ui.Button(
                label="Passar rodada",
                custom_id="quadribol:rodada",
                style=discord.ButtonStyle.danger,
                row=0,
            )
            botao_rodada.callback = self.proxima_rodada
            self.add_item(botao_rodada)
            return

        controles = [
            ("Ações do turno", "quadribol:acoes", discord.ButtonStyle.primary, 0, self.acoes),
            ("Passar turno", "quadribol:turno", discord.ButtonStyle.primary, 0, self.proximo_turno),
            ("Passar rodada", "quadribol:rodada", discord.ButtonStyle.danger, 0, self.proxima_rodada),
            ("Preparar ação", "quadribol:preparar", discord.ButtonStyle.secondary, 1, self.preparando_acao),
            ("Outros controles", "quadribol:outros", discord.ButtonStyle.secondary, 1, self.outros),
        ]
        for label, custom_id, style, row, callback in controles:
            botao = discord.ui.Button(label=label, custom_id=custom_id, style=style, row=row)
            botao.disabled = not livre
            botao.callback = callback
            self.add_item(botao)
        if reposicao_pendente:
            botao_reposicao = discord.ui.Button(
                label="Escolher nova posse",
                custom_id="quadribol:reposicao-goles-balaco",
                style=discord.ButtonStyle.success,
                row=2,
            )
            botao_reposicao.callback = self.repor_goles_apos_balaco
            self.add_item(botao_reposicao)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        membro = interaction.user
        if not isinstance(membro, discord.Member) or not membro.guild_permissions.manage_guild:
            await interaction.response.send_message("Você precisa da permissão **Gerenciar servidor** para controlar a partida.", ephemeral=True)
            return False
        return True

    def _carregar(self, interaction: discord.Interaction) -> PartidaQuadribol:
        if self.partida_id:
            return self.cog._localizar_por_id(self.partida_id)[0]
        return _partida_da_interacao(interaction)

    async def acoes(self, interaction: discord.Interaction) -> None:
        try:
            partida = self._carregar(interaction)
            atual = partida.jogador_atual()
            if atual is not None and esta_atordoado(atual):
                await self._enviar_recuperacao(interaction, partida)
                return
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        precisa_resistir_tempo = bool(
            atual is not None
            and tem_tempo_meteorologico(atual)
            and atual.penalidade_tempo_preparada is None
        )
        await self.cog.abrir_painel_privado(
            interaction,
            partida,
            embed=_embed_painel_acao(
                partida,
                (
                    "🌦️ Condições Meteorológicas"
                    if precisa_resistir_tempo
                    else "⚡ Ações do Turno"
                ),
                (
                    "Antes de agir, o jogador precisa realizar um teste de **Fortitude** contra a "
                    "CD do clima. Em caso de falha, o resultado de `-(1d4+1)` será "
                    "aplicado automaticamente à ação escolhida."
                    if precisa_resistir_tempo
                    else "Escolha a ação do jogador em destaque."
                ),
            ),
            view=AcoesTurnoView(self.cog, partida),
        )

    async def _enviar_recuperacao(
        self,
        interaction: discord.Interaction,
        partida: PartidaQuadribol,
    ) -> None:
        atual = partida.jogador_atual()
        await self.cog.abrir_painel_privado(
            interaction,
            partida,
            embed=_embed_painel_acao(
                partida,
                "🩹 Teste de Recuperação",
                (
                    f"**{atual.nome}** está Atordoado e não pode realizar nenhuma outra "
                    "ação. Realize um teste de Fortitude contra a CD do impacto."
                ),
            ),
            view=RecuperacaoView(self.cog, partida),
        )

    async def abrir_recuperacao_atordoamento(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            partida = self._carregar(interaction)
            atual = partida.jogador_atual()
            if atual is None or not esta_atordoado(atual):
                raise ValueError("O jogador em destaque não está Atordoado.")
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await self._enviar_recuperacao(interaction, partida)

    async def repor_goles_apos_balaco(self, interaction: discord.Interaction) -> None:
        try:
            partida = self._carregar(interaction)
            if not partida.reposicao_goles_casa:
                raise ValueError("Não existe uma reposição da Goles pendente.")
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await self.cog.abrir_painel_privado(
            interaction,
            partida,
            embed=discord.Embed(
                title="🏐 Reposição da Goles",
                description=(
                    f"**{partida.reposicao_goles_jogador}** perdeu a posse após ser "
                    "atingido por um Balaço. Escolha o novo portador adversário."
                ),
                color=COR_QUADRIBOL,
            ),
            view=ReposicaoGolesAposBalacoView(self.cog, partida),
        )

    async def preparando_acao(self, interaction: discord.Interaction) -> None:
        try:
            atual = self._carregar(interaction)

            def acao(partida: PartidaQuadribol) -> None:
                jogador = partida.jogador_atual()
                if jogador is None:
                    raise ValueError("Não há jogador no turno atual.")
                partida.eventos.append(
                    EventoPartida(
                        tipo="preparando_acao",
                        jogador=jogador.nome,
                        casa=jogador.casa,
                        descricao=(
                            f"{jogador.nome} preparou a ação para agir antes da "
                            "iniciativa normal da próxima rodada."
                        ),
                    )
                )
                preparar_acao(partida)

            partida = await self.cog.mutar_partida(atual.identificador, acao)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(
            embeds=embeds_partida(partida),
            view=QuadribolView(self.cog, partida),
        )

    async def _publicar_surgimentos(self, partida: PartidaQuadribol, inicio: int) -> None:
        for evento in partida.eventos[inicio:]:
            if evento.tipo == "surgimento_pomo":
                await self.cog.publicar_evento(partida, embed_surgimento_pomo(partida, evento.alvo))

    async def proxima_rodada(self, interaction: discord.Interaction) -> None:
        try:
            atual = self._carregar(interaction)
            quantidade_eventos = len(atual.eventos)
            partida = await self.cog.mutar_partida(atual.identificador, avancar_rodada)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(embeds=embeds_partida(partida), view=QuadribolView(self.cog, partida))
        await self._publicar_surgimentos(partida, quantidade_eventos)

    async def outros(self, interaction: discord.Interaction) -> None:
        try:
            partida = self._carregar(interaction)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await self.cog.abrir_painel_privado(
            interaction,
            partida,
            embed=_embed_painel_acao(
                partida,
                "🏛️ Outros controles",
                "Acesse ocorrências, recuperação, penalidades e encerramento da partida.",
            ),
            view=OutrosControlesView(self.cog, partida),
        )

    async def _gol(self, interaction: discord.Interaction, indice: int) -> None:
        try:
            atual = self._carregar(interaction)
            partida = await self.cog.mutar_partida(
                atual.identificador,
                lambda item: adicionar_gol(item, item.casas()[indice]),
            )
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(embeds=embeds_partida(partida), view=QuadribolView(self.cog, partida))

    async def gol_1(self, interaction: discord.Interaction) -> None:
        await self._gol(interaction, 0)

    async def gol_2(self, interaction: discord.Interaction) -> None:
        await self._gol(interaction, 1)

    async def pomo(self, interaction: discord.Interaction) -> None:
        try:
            partida = self._carregar(interaction)
            view = PerseguirPomoView(self.cog, partida)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await self.cog.abrir_painel_privado(
            interaction,
            partida,
            content=f"O Pomo atual está no lado de **{view.pomo_lado}**. Escolha a forma de perseguição.",
            view=view,
        )

    async def proximo_turno(self, interaction: discord.Interaction) -> None:
        try:
            atual = self._carregar(interaction)
            quantidade_eventos = len(atual.eventos)
            partida = await self.cog.mutar_partida(atual.identificador, avancar_turno)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(embeds=embeds_partida(partida), view=QuadribolView(self.cog, partida))
        await self._publicar_surgimentos(partida, quantidade_eventos)

    async def recuperacao(self, interaction: discord.Interaction) -> None:
        try:
            atual = self._carregar(interaction)
            jogador = atual.jogador_atual()
            if jogador is None:
                raise ValueError("Não há jogador no turno atual.")
            resultado = None
            fontes_rolagem: list[str] = []

            def acao(partida: PartidaQuadribol) -> None:
                nonlocal resultado
                resultado = testar_recuperacao(
                    partida,
                    jogador.nome,
                    fontes=fontes_rolagem,
                )

            partida = await self.cog.mutar_partida(atual.identificador, acao)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        assert resultado is not None
        dado, total, sucesso = resultado
        await interaction.response.edit_message(embeds=embeds_partida(partida), view=QuadribolView(self.cog, partida))

    async def desfazer(self, interaction: discord.Interaction) -> None:
        try:
            atual = self._carregar(interaction)
            partida = await self.cog.mutar_partida(atual.identificador, desfazer_ultima_acao)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(embeds=embeds_partida(partida), view=QuadribolView(self.cog, partida))

    async def encerrar(self, interaction: discord.Interaction) -> None:
        try:
            atual = self._carregar(interaction)
            if atual.estado in {"ativa", "intervalo"}:
                partida = await self.cog.mutar_partida(
                    atual.identificador,
                    preparar_encerramento,
                )
            else:
                partida = await self.cog.finalizar_partida(atual.identificador)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(f"Não foi possível encerrar: {erro}", ephemeral=True)
            return
        if partida.estado == "encerrada":
            await interaction.response.edit_message(
                embed=embed_resultado_partida(partida),
                view=None,
            )
        else:
            await interaction.response.edit_message(
                embeds=embeds_partida(partida),
                view=QuadribolView(self.cog, partida),
            )

    async def manobra(self, interaction: discord.Interaction) -> None:
        try:
            partida = self._carregar(interaction)
            if not carregar_manobras():
                raise ValueError("Nenhuma manobra completa está cadastrada.")
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await self.cog.abrir_painel_privado(
            interaction,
            partida,
            content="Escolha a manobra. Se ela for coletiva, escolha também o Coordenador da manobra.",
            view=ManobraView(self.cog, partida),
        )

    async def balaco(self, interaction: discord.Interaction) -> None:
        try:
            partida = self._carregar(interaction)
            view = BalacoView(self.cog, partida)
            atacante = partida.jogador_atual()
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await self.cog.abrir_painel_privado(
            interaction,
            partida,
            content=f"**{atacante.nome}** é o Batedor atacante. Escolha o alvo e a rebatida.",
            view=view,
        )

    async def efeito(self, interaction: discord.Interaction) -> None:
        try:
            partida = self._carregar(interaction)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await self.cog.abrir_painel_privado(
            interaction,
            partida,
            content=None,
            embed=_embed_painel_acao(
                partida,
                "⏳ Efeitos e Condições",
                "Escolha a condição narrativa e os envolvidos. Efeitos com duração definida terminam automaticamente; impactos e manobras são aplicados por suas próprias ações.",
            ),
            view=EscolherCondicaoCatalogadaView(self.cog, partida, "Efeito narrativo"),
        )

    async def falta(self, interaction: discord.Interaction) -> None:
        try:
            partida = self._carregar(interaction)
            if not carregar_faltas():
                raise ValueError("Nenhuma falta está cadastrada.")
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await self.cog.abrir_painel_privado(
            interaction,
            partida,
            content="Escolha quem cometeu a falta.",
            view=EscolherInfratorFaltaView(self.cog, partida),
        )

    async def penalti(self, interaction: discord.Interaction) -> None:
        try:
            partida = self._carregar(interaction)
            if not partida.penalti_casa:
                raise ValueError("Não há pênalti pendente.")
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await self.cog.abrir_painel_privado(
            interaction,
            partida,
            content=f"Escolha o Artilheiro de **{partida.penalti_casa}** que fará a cobrança direta.",
            view=PenaltiView(self.cog, partida),
        )


class RecuperacaoView(discord.ui.View):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(timeout=120)
        self.cog = cog
        self.partida_id = partida.identificador
        atual = partida.jogador_atual()
        if atual is None:
            raise ValueError("Não há jogador no turno atual.")
        self.jogador = atual.nome

    @discord.ui.button(label="Realizar Teste", style=discord.ButtonStyle.primary)
    async def testar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if await self._exigir_tempo(interaction):
            return
        await self._resolver(interaction)

    @discord.ui.button(label="Rolagem Externa", style=discord.ButtonStyle.secondary)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if await self._exigir_tempo(interaction):
            return
        await interaction.response.send_modal(
            RolagemExternaModal("Total de Fortitude", self._resolver)
        )

    async def _exigir_tempo(self, interaction: discord.Interaction) -> bool:
        partida, _ = self.cog._localizar_por_id(self.partida_id)
        jogador = encontrar_jogador_partida(partida, self.jogador)
        return await exigir_resistencia_tempo(
            interaction,
            self.cog,
            partida,
            jogador,
            "realizar o Teste de Recuperação",
            self,
            self,
        )

    async def _resolver(
        self,
        interaction: discord.Interaction,
        resultado_externo: int | None = None,
    ) -> None:
        await interaction.response.defer()
        resultado: tuple[int, int, bool] | None = None
        fontes_rolagem: list[str] = []
        eventos_turno: list[EventoPartida] = []
        condicao = "Atordoado"
        cd_recuperacao = 0

        def recuperar(partida: PartidaQuadribol) -> None:
            nonlocal resultado, condicao, cd_recuperacao
            jogador = encontrar_jogador_partida(partida, self.jogador)
            efeito = next(
                item
                for item in jogador.efeitos
                if item.nome.startswith("Atordoado por")
            )
            condicao = efeito.nome
            cd_recuperacao = efeito.cd_recuperacao
            resultado = testar_recuperacao(
                partida,
                self.jogador,
                resultado_externo=resultado_externo,
                fontes=fontes_rolagem,
            )
            if not resultado[2]:
                inicio = len(partida.eventos)
                avancar_turno(partida, permitir_atordoado=True)
                eventos_turno.extend(partida.eventos[inicio:])

        try:
            partida = await self.cog.mutar_partida(self.partida_id, recuperar)
            await self.cog.atualizar_mensagem(partida)
            if not resultado[2]:
                await self.cog.publicar_surgimentos(partida, eventos_turno)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.edit_original_response(
                content=f"Não foi possível realizar a recuperação: {erro}", view=self
            )
            return
        assert resultado is not None
        _, total, sucesso = resultado
        self.stop()
        await interaction.edit_original_response(
            content=None,
            embed=embed_resultado_recuperacao(
                self.jogador,
                condicao,
                tuple(fontes_rolagem),
                total,
                cd_recuperacao,
                sucesso,
            ),
            view=PainelResultadoView(self.cog, partida),
        )


class OutrosControlesView(PainelPartidaView):
    OPCOES = (
        ("Registrar Falta", "falta", discord.ButtonStyle.danger),
        ("Desfazer placar", "desfazer", discord.ButtonStyle.secondary),
        ("Encerrar / Intervalo", "encerrar", discord.ButtonStyle.primary),
    )

    def __init__(self, cog: Quadribol, partida: PartidaQuadribol):
        super().__init__(cog, partida)
        for indice, (rotulo, acao, estilo) in enumerate(self.OPCOES):
            botao = discord.ui.Button(
                label=rotulo,
                style=estilo,
                custom_id=f"quadribol:outros:{acao}",
                row=indice // 3,
            )
            botao.callback = self._callback(acao)
            self.add_item(botao)

    def _callback(self, acao: str):
        async def callback(interaction: discord.Interaction) -> None:
            partida = self.carregar(interaction)
            textos = {
                "balaco": ("💥 Redirecionar Balaço", "Escolha o Batedor, o alvo e a rebatida. O ataque e a defesa serão rolados pelo bot."),
                "recuperacao": ("🩹 Recuperação", "O jogador em destaque realizará um teste de Fortitude contra a CD do efeito que o impede de agir."),
                "falta": ("🚫 Registrar Falta", "Escolha o infrator e a falta. A punição predefinida será aplicada e o pênalti ficará pendente."),
                "penalti": ("🧹 Cobrar Pênalti", "Um Artilheiro cobrará diretamente contra o Goleiro adversário."),
                "desfazer": ("↩️ Desfazer placar", "Remove o último gol ou captura registrado no placar."),
                "encerrar": ("⏱️ Encerrar / Intervalo", "No 1º tempo, abre o intervalo. No 2º, prepara o resultado para confirmação."),
            }
            titulo, descricao = textos[acao]
            await interaction.response.edit_message(
                embed=_embed_painel_acao(partida, titulo, descricao),
                view=DetalheOutroView(self.cog, partida, acao),
            )
        return callback


class DetalheOutroView(PainelPartidaView):
    def __init__(self, cog: Quadribol, partida: PartidaQuadribol, acao: str):
        super().__init__(cog, partida)
        self.acao = acao
        self.voltar.callback = self.voltar_outros
        botao = discord.ui.Button(
            label="Continuar",
            style=discord.ButtonStyle.success,
            custom_id=f"quadribol:outros:{acao}:continuar",
            row=0,
        )
        botao.callback = self.continuar
        self.add_item(botao)

    async def voltar_outros(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        self.stop()
        await interaction.response.edit_message(
            embed=_embed_painel_acao(
                partida,
                "🏛️ Outros controles",
                "Acesse ocorrências, recuperação, penalidades e encerramento da partida.",
            ),
            view=OutrosControlesView(self.cog, partida),
        )

    async def continuar(self, interaction: discord.Interaction) -> None:
        partida = self.carregar(interaction)
        try:
            if self.acao == "balaco":
                atacante = partida.jogador_atual()
                view = BalacoView(self.cog, partida)
                await interaction.response.edit_message(
                    content=
                    f"**{atacante.nome}** é o Batedor atacante. Escolha o alvo e a rebatida.",
                    view=view,
                )
                return
            if self.acao == "falta":
                await interaction.response.edit_message(
                    content="Escolha quem cometeu a falta.",
                    view=EscolherInfratorFaltaView(self.cog, partida),
                )
                return
            if self.acao == "penalti":
                if not partida.penalti_casa:
                    raise ValueError("Não há pênalti pendente.")
                await interaction.response.edit_message(
                    content=f"Escolha o Artilheiro de **{partida.penalti_casa}**.",
                    view=PenaltiView(self.cog, partida),
                )
                return
            if self.acao == "recuperacao":
                await interaction.response.edit_message(
                    content="Escolha como será feito o teste de recuperação.",
                    view=RecuperacaoView(self.cog, partida),
                )
                return
            elif self.acao == "desfazer":
                partida = await self.cog.mutar_partida(partida.identificador, desfazer_ultima_acao)
            else:
                if partida.estado in {"ativa", "intervalo"}:
                    partida = await self.cog.mutar_partida(partida.identificador, preparar_encerramento)
                else:
                    partida = await self.cog.finalizar_partida(partida.identificador)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await self.cog.atualizar_mensagem(partida)
        await interaction.response.edit_message(
            embeds=embeds_partida(partida),
            view=QuadribolView(self.cog, partida),
        )


class VassourasViewBase(discord.ui.View):
    def __init__(self, usuario_id: int):
        super().__init__(timeout=300)
        self.usuario_id = usuario_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message(
            "Somente quem abriu o catálogo pode usar estes controles.",
            ephemeral=True,
        )
        return False


class VassourasLinhasView(VassourasViewBase):
    def __init__(self, usuario_id: int):
        super().__init__(usuario_id)
        self.linhas = linhas_vassouras_por_preco()
        seletor = discord.ui.Select(
            placeholder="Escolha a linha da vassoura",
            options=[
                discord.SelectOption(
                    label=linha,
                    value=linha,
                    description=(
                        perfil_linha_vassoura(linha)
                        or descricao_recomendacao_linha(linha)
                    )[:100],
                )
                for linha, modelos in self.linhas.items()
            ],
        )
        seletor.callback = self.selecionar_linha
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar_linha(self, interaction: discord.Interaction) -> None:
        linha = self.seletor.values[0]
        modelos = self.linhas[linha]
        await interaction.response.edit_message(
            content=None,
            embed=embed_linha_vassouras(linha, modelos),
            view=VassourasModelosView(self.usuario_id, linha, modelos),
        )


class VassourasModelosView(VassourasViewBase):
    def __init__(self, usuario_id: int, linha: str, modelos: list[Vassoura]):
        super().__init__(usuario_id)
        self.linha = linha
        self.modelos = {modelo.nome: modelo for modelo in modelos}
        seletor = discord.ui.Select(
            placeholder=f"Modelo — {linha}",
            options=[
                discord.SelectOption(
                    label=modelo.nome,
                    value=modelo.nome,
                    description=(
                        f"{modelo.velocidade or '--'} • {modelo.custo or '--'} • "
                        f"{modelo.vida_maxima} PV"
                    )[:100],
                )
                for modelo in modelos
            ],
            row=0,
        )
        seletor.callback = self.selecionar_modelo
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar às linhas",
            style=discord.ButtonStyle.secondary,
            emoji="↩️",
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar_modelo(self, interaction: discord.Interaction) -> None:
        modelo = self.modelos[self.seletor.values[0]]
        embeds = montar_embeds_vassoura(modelo)
        apresentacao_linha = montar_embed_linha_vassouras(self.linha)
        if apresentacao_linha is not None:
            embeds.insert(0, apresentacao_linha)
        await interaction.response.edit_message(
            content=formatar_cabecalho_vassoura(modelo),
            embeds=embeds,
            view=VassourasDetalheView(
                self.usuario_id,
                self.linha,
                list(self.modelos.values()),
            ),
            attachments=criar_arquivos_discord(anexos_vassoura(modelo)),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_catalogo_vassouras(),
            view=VassourasLinhasView(self.usuario_id),
            attachments=[],
        )


class VassourasDetalheView(VassourasViewBase):
    def __init__(self, usuario_id: int, linha: str, modelos: list[Vassoura]):
        super().__init__(usuario_id)
        self.linha = linha
        self.modelos = modelos

    @discord.ui.button(
        label="Voltar aos modelos",
        style=discord.ButtonStyle.secondary,
        emoji="↩️",
    )
    async def voltar_modelos(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_linha_vassouras(self.linha, self.modelos),
            view=VassourasModelosView(self.usuario_id, self.linha, self.modelos),
            attachments=[],
        )

    @discord.ui.button(
        label="Voltar às linhas",
        style=discord.ButtonStyle.secondary,
        emoji="⏪",
    )
    async def voltar_linhas(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_catalogo_vassouras(),
            view=VassourasLinhasView(self.usuario_id),
        )


def embed_central_manobras() -> discord.Embed:
    manobras = carregar_manobras()
    return discord.Embed(
        title="🧩 Manobras de Quadribol",
        description=(
            f"Consulte as **{len(manobras)} manobras** da biblioteca ou crie uma "
            "nova ficha para o catálogo oficial.\n\n"
            "A criação exige uma prévia e confirmação antes de salvar ou publicar."
        ),
        color=COR_QUADRIBOL,
    )


class ManobrasViewBase(discord.ui.View):
    def __init__(self, usuario_id: int, *, timeout: float = 600):
        super().__init__(timeout=timeout)
        self.usuario_id = usuario_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message(
            "Somente quem abriu a central pode usar estes controles.",
            ephemeral=True,
        )
        return False


class ConsultarManobrasView(ManobrasViewBase):
    def __init__(self, usuario_id: int, cog: Quadribol | None = None):
        super().__init__(usuario_id)
        self.cog = cog
        self.manobras = {item.nome: item for item in carregar_manobras()}
        seletor = discord.ui.Select(
            placeholder="Escolha uma manobra",
            options=[
                discord.SelectOption(
                    label=item.nome[:100],
                    value=item.nome,
                    description=(
                        f"{'Automática' if item.cd == 0 else f'CD {item.cd}'} • "
                        f"Quadribol {item.requisito_quadribol:+d} • "
                        f"{', '.join(item.posicoes)}"
                    )[:100],
                )
                for item in self.manobras.values()
            ][:25],
            row=0,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar",
            emoji="↩️",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        nome = self.seletor.values[0]
        for opcao in self.seletor.options:
            opcao.default = opcao.value == nome
        await interaction.response.edit_message(
            content=None,
            embed=embed_detalhe_manobra(self.manobras[nome]),
            view=self,
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_central_manobras(),
            view=CentralManobrasView(self.usuario_id, self.cog),
        )


@dataclass
class RascunhoManobra:
    nome: str = ""
    descricao: str = ""
    cd: int = 0
    requisito: int = 1
    posicoes: tuple[str, ...] = field(default_factory=tuple)
    participantes: str = ""
    execucao: str = ""
    beneficio: str = ""

    def converter(self) -> ManobraQuadribol:
        return ManobraQuadribol(
            nome=self.nome,
            cd=self.cd,
            requisito_quadribol=self.requisito,
            posicoes=self.posicoes,
            participantes=self.participantes,
            descricao=self.descricao,
            execucao=self.execucao,
            beneficio=self.beneficio,
        )


def embed_rascunho_manobra(rascunho: RascunhoManobra) -> discord.Embed:
    embed = discord.Embed(
        title="🧩 Criar Manobra",
        description=(
            "Preencha os dados em duas etapas, escolha o requisito e as posições e "
            "então revise a ficha completa."
        ),
        color=COR_QUADRIBOL,
    )
    embed.add_field(name="Nome", value=rascunho.nome or "--", inline=False)
    embed.add_field(
        name="CD",
        value=("Execução automática" if rascunho.cd == 0 else str(rascunho.cd)),
        inline=True,
    )
    embed.add_field(
        name="Requisito",
        value=f"{rascunho.requisito:+d} Quadribol",
        inline=True,
    )
    embed.add_field(
        name="Posições",
        value=", ".join(rascunho.posicoes) or "--",
        inline=True,
    )
    embed.add_field(
        name="Dados básicos",
        value=("✅ Preenchidos" if all((rascunho.nome, rascunho.descricao, rascunho.participantes)) else "❌ Pendentes"),
        inline=True,
    )
    embed.add_field(
        name="Execução e benefício",
        value=("✅ Preenchidos" if rascunho.execucao and rascunho.beneficio else "❌ Pendentes"),
        inline=True,
    )
    return embed


class DadosBasicosManobraModal(discord.ui.Modal):
    def __init__(self, view: CriarManobraView):
        super().__init__(title="Criar Manobra — Dados Básicos")
        self.view_criacao = view
        atual = view.rascunho
        self.nome = discord.ui.TextInput(
            label="Nome da manobra",
            default=atual.nome,
            min_length=2,
            max_length=100,
        )
        self.descricao = discord.ui.TextInput(
            label="Descrição",
            default=atual.descricao,
            style=discord.TextStyle.paragraph,
            min_length=10,
            max_length=1000,
        )
        self.cd = discord.ui.TextInput(
            label="CD — use 0 para execução automática",
            default=str(atual.cd),
            min_length=1,
            max_length=2,
        )
        self.participantes = discord.ui.TextInput(
            label="Participantes",
            default=atual.participantes,
            placeholder="Ex.: Três Artilheiros.",
            min_length=3,
            max_length=300,
        )
        for item in (self.nome, self.descricao, self.cd, self.participantes):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cd = str(self.cd.value).strip()
        if not cd.isdigit() or not 0 <= int(cd) <= 99:
            await interaction.response.send_message(
                "A CD deve ser um número entre 0 e 99.", ephemeral=True
            )
            return
        rascunho = self.view_criacao.rascunho
        rascunho.nome = str(self.nome.value).strip()
        rascunho.descricao = str(self.descricao.value).strip()
        rascunho.cd = int(cd)
        rascunho.participantes = str(self.participantes.value).strip()
        await interaction.response.edit_message(
            embed=embed_rascunho_manobra(rascunho),
            view=self.view_criacao,
        )


class TextosManobraModal(discord.ui.Modal):
    def __init__(self, view: CriarManobraView):
        super().__init__(title="Criar Manobra — Execução")
        self.view_criacao = view
        atual = view.rascunho
        self.execucao = discord.ui.TextInput(
            label="Execução",
            default=atual.execucao,
            style=discord.TextStyle.paragraph,
            min_length=10,
            max_length=1000,
        )
        self.beneficio = discord.ui.TextInput(
            label="Benefício",
            default=atual.beneficio,
            style=discord.TextStyle.paragraph,
            min_length=5,
            max_length=1000,
        )
        self.add_item(self.execucao)
        self.add_item(self.beneficio)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        rascunho = self.view_criacao.rascunho
        rascunho.execucao = str(self.execucao.value).strip()
        rascunho.beneficio = str(self.beneficio.value).strip()
        await interaction.response.edit_message(
            embed=embed_rascunho_manobra(rascunho),
            view=self.view_criacao,
        )


class CriarManobraView(ManobrasViewBase):
    def __init__(
        self,
        cog: Quadribol,
        usuario_id: int,
        rascunho: RascunhoManobra | None = None,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.rascunho = rascunho or RascunhoManobra()
        requisito = discord.ui.Select(
            placeholder="Requisito de Quadribol",
            options=[
                discord.SelectOption(
                    label=f"Quadribol +{valor}",
                    value=str(valor),
                    description=(
                        "Acessível" if valor == 1 else
                        "Treinada" if valor == 2 else
                        "Avançada" if valor == 3 else
                        "Elite" if valor == 4 else "Excepcional"
                    ),
                    default=self.rascunho.requisito == valor,
                )
                for valor in range(1, 6)
            ],
            row=0,
        )
        posicoes = discord.ui.Select(
            placeholder="Posições participantes",
            min_values=1,
            max_values=len(POSICOES),
            options=[
                discord.SelectOption(
                    label=posicao,
                    value=posicao,
                    default=posicao in self.rascunho.posicoes,
                )
                for posicao in POSICOES
            ],
            row=1,
        )

        async def escolher_requisito(interaction: discord.Interaction) -> None:
            self.rascunho.requisito = int(requisito.values[0])
            for opcao in requisito.options:
                opcao.default = opcao.value == requisito.values[0]
            await interaction.response.edit_message(
                embed=embed_rascunho_manobra(self.rascunho), view=self
            )

        async def escolher_posicoes(interaction: discord.Interaction) -> None:
            self.rascunho.posicoes = tuple(posicoes.values)
            for opcao in posicoes.options:
                opcao.default = opcao.value in posicoes.values
            await interaction.response.edit_message(
                embed=embed_rascunho_manobra(self.rascunho), view=self
            )

        requisito.callback = escolher_requisito
        posicoes.callback = escolher_posicoes
        self.add_item(requisito)
        self.add_item(posicoes)
        dados = discord.ui.Button(
            label="Dados Básicos",
            style=discord.ButtonStyle.primary,
            row=2,
        )
        textos = discord.ui.Button(
            label="Execução e Benefício",
            style=discord.ButtonStyle.primary,
            row=2,
        )
        revisar = discord.ui.Button(
            label="Revisar Manobra",
            style=discord.ButtonStyle.success,
            row=3,
        )
        voltar = discord.ui.Button(
            label="Voltar",
            emoji="↩️",
            style=discord.ButtonStyle.secondary,
            row=3,
        )

        async def abrir_dados(interaction: discord.Interaction) -> None:
            await interaction.response.send_modal(DadosBasicosManobraModal(self))

        async def abrir_textos(interaction: discord.Interaction) -> None:
            await interaction.response.send_modal(TextosManobraModal(self))

        async def revisar_ficha(interaction: discord.Interaction) -> None:
            try:
                manobra = validar_nova_manobra(self.rascunho.converter())
            except ValueError as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return
            await interaction.response.edit_message(
                content=None,
                embed=embed_detalhe_manobra(manobra),
                view=ConfirmarCriacaoManobraView(
                    self.cog, self.usuario_id, self.rascunho
                ),
            )

        async def voltar_central(interaction: discord.Interaction) -> None:
            await interaction.response.edit_message(
                content=None,
                embed=embed_central_manobras(),
                view=CentralManobrasView(self.usuario_id),
            )

        dados.callback = abrir_dados
        textos.callback = abrir_textos
        revisar.callback = revisar_ficha
        voltar.callback = voltar_central
        for item in (dados, textos, revisar, voltar):
            self.add_item(item)


class ConfirmarCriacaoManobraView(ManobrasViewBase):
    def __init__(self, cog: Quadribol, usuario_id: int, rascunho: RascunhoManobra):
        super().__init__(usuario_id)
        self.cog = cog
        self.rascunho = rascunho

    @discord.ui.button(
        label="Confirmar e Publicar",
        style=discord.ButtonStyle.success,
        row=0,
    )
    async def confirmar(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        membro = interaction.user
        if not isinstance(membro, discord.Member) or not membro.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Você precisa da permissão **Gerenciar servidor** para publicar.",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        try:
            manobra, link = await self.cog.criar_e_publicar_manobra(
                self.rascunho.converter()
            )
        except (OSError, ValueError, RuntimeError, aiohttp.ClientError) as erro:
            await interaction.edit_original_response(
                content=f"Não foi possível criar a manobra: {erro}",
                embed=None,
                view=CriarManobraView(self.cog, self.usuario_id, self.rascunho),
            )
            return
        await interaction.edit_original_response(
            content=f"✅ **{manobra.nome}** foi salva e publicada: {link}",
            embed=embed_detalhe_manobra(manobra),
            view=ConsultarManobrasView(self.usuario_id, self.cog),
        )

    @discord.ui.button(label="Voltar à Edição", style=discord.ButtonStyle.secondary)
    async def voltar(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_rascunho_manobra(self.rascunho),
            view=CriarManobraView(self.cog, self.usuario_id, self.rascunho),
        )


class CentralManobrasView(ManobrasViewBase):
    def __init__(self, usuario_id: int, cog: Quadribol | None = None):
        super().__init__(usuario_id)
        self.cog = cog

    @discord.ui.button(label="Consultar Manobras", style=discord.ButtonStyle.primary)
    async def consultar(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_detalhe_manobra(carregar_manobras()[0]),
            view=ConsultarManobrasView(self.usuario_id, self.cog),
        )

    @discord.ui.button(label="Criar Manobra", style=discord.ButtonStyle.success)
    async def criar(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        membro = interaction.user
        if self.cog is None or not isinstance(membro, discord.Member) or not membro.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Você precisa da permissão **Gerenciar servidor** para criar manobras.",
                ephemeral=True,
            )
            return
        view = CriarManobraView(self.cog, self.usuario_id)
        await interaction.response.edit_message(
            content=None,
            embed=embed_rascunho_manobra(view.rascunho),
            view=view,
        )


class Quadribol(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bloqueio_jogadores = asyncio.Lock()
        self.bloqueio_partidas = asyncio.Lock()
        self.bloqueio_manobras = asyncio.Lock()
        self.tarefa_restaurar_paineis: asyncio.Task | None = None
        self.paineis_privados: dict[tuple[str, int], discord.WebhookMessage] = {}

    @staticmethod
    async def _requisicao_webhook(
        sessao: aiohttp.ClientSession,
        metodo: str,
        url: str,
        **opcoes,
    ) -> dict:
        while True:
            async with sessao.request(metodo, url, **opcoes) as resposta:
                corpo = await resposta.text()
                if resposta.status == 429:
                    dados = json.loads(corpo)
                    await asyncio.sleep(float(dados.get("retry_after", 1)))
                    continue
                if resposta.status >= 400:
                    raise RuntimeError(
                        f"O catálogo do Discord recusou a operação (HTTP {resposta.status})."
                    )
                return json.loads(corpo) if corpo else {}

    @staticmethod
    def _inserir_link_manobra_indice(texto: str, nome: str, link: str) -> str:
        linha = f"» [{nome}]({link})"
        if linha in texto:
            return texto
        marcador = "\n> Selecione o nome de uma manobra"
        if marcador in texto:
            return texto.replace(marcador, f"\n{linha}\n{marcador}", 1)
        proxima_secao = "\n## 12 — Efeitos e condições"
        if proxima_secao in texto:
            return texto.replace(proxima_secao, f"\n{linha}\n{proxima_secao}", 1)
        return f"{texto.rstrip()}\n{linha}"

    async def criar_e_publicar_manobra(
        self,
        manobra: ManobraQuadribol,
    ) -> tuple[ManobraQuadribol, str]:
        webhook = os.environ.get("GRIMORY_QUADRIBOL_WEBHOOK", "").strip().rstrip("/")
        if not webhook:
            raise RuntimeError("O webhook do catálogo de Quadribol não está configurado.")
        async with self.bloqueio_manobras:
            validada = validar_nova_manobra(manobra)
            texto_manobras_anterior = ARQUIVO_MANOBRAS.read_text(encoding="utf-8-sig")
            texto_guia_anterior = GUIA_QUADRIBOL.read_text(encoding="utf-8-sig")
            mensagem_publicada = ""
            indice_original: dict | None = None
            try:
                validada = adicionar_manobra_biblioteca(validada)
                async with aiohttp.ClientSession() as sessao:
                    publicada = await self._requisicao_webhook(
                        sessao,
                        "POST",
                        f"{webhook}?wait=true&thread_id={THREAD_MANOBRAS_ID}",
                        json={
                            "embeds": [embed_detalhe_manobra(validada).to_dict()],
                            "allowed_mentions": {"parse": []},
                        },
                    )
                    mensagem_publicada = str(publicada["id"])
                    link = (
                        f"https://discord.com/channels/{GUILD_GRIMORY_ID}/"
                        f"{THREAD_MANOBRAS_ID}/{mensagem_publicada}"
                    )
                    indice_url = f"{webhook}/messages/{MENSAGEM_INDICE_MANOBRAS_ID}"
                    indice_original = await self._requisicao_webhook(
                        sessao, "GET", indice_url
                    )
                    embeds_indice = indice_original.get("embeds", [])
                    alvo = next(
                        (
                            item
                            for item in embeds_indice
                            if item.get("title") == "🧩 Manobras de Quadribol"
                        ),
                        None,
                    )
                    if alvo is None:
                        raise ValueError("Não encontrei a embed principal de manobras.")
                    alvo["description"] = self._inserir_link_manobra_indice(
                        str(alvo.get("description", "")), validada.nome, link
                    )
                    if len(alvo["description"]) > 4096:
                        raise ValueError("O índice de manobras atingiu o limite do Discord.")
                    novo_guia = self._inserir_link_manobra_indice(
                        texto_guia_anterior, validada.nome, link
                    )
                    temporario_guia = GUIA_QUADRIBOL.with_name(
                        f".{GUIA_QUADRIBOL.name}.tmp"
                    )
                    temporario_guia.write_text(novo_guia, encoding="utf-8")
                    temporario_guia.replace(GUIA_QUADRIBOL)
                    await self._requisicao_webhook(
                        sessao,
                        "PATCH",
                        indice_url,
                        json={
                            "embeds": embeds_indice,
                            "allowed_mentions": {"parse": []},
                        },
                    )
                return validada, link
            except Exception:
                ARQUIVO_MANOBRAS.write_text(texto_manobras_anterior, encoding="utf-8")
                GUIA_QUADRIBOL.write_text(texto_guia_anterior, encoding="utf-8")
                if mensagem_publicada:
                    try:
                        async with aiohttp.ClientSession() as sessao:
                            if indice_original is not None:
                                await self._requisicao_webhook(
                                    sessao,
                                    "PATCH",
                                    f"{webhook}/messages/{MENSAGEM_INDICE_MANOBRAS_ID}",
                                    json={
                                        "embeds": indice_original.get("embeds", []),
                                        "allowed_mentions": {"parse": []},
                                    },
                                )
                            await self._requisicao_webhook(
                                sessao,
                                "DELETE",
                                f"{webhook}/messages/{mensagem_publicada}"
                                f"?thread_id={THREAD_MANOBRAS_ID}",
                            )
                    except (aiohttp.ClientError, RuntimeError):
                        pass
                raise

    async def abrir_painel_privado(
        self,
        interaction: discord.Interaction,
        partida: PartidaQuadribol,
        **conteudo,
    ) -> discord.WebhookMessage:
        """Mantém uma única mensagem efêmera por moderador e partida."""
        chave = (partida.identificador, interaction.user.id)
        anterior = self.paineis_privados.pop(chave, None)
        if anterior is not None:
            try:
                await anterior.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
        await interaction.response.send_message(ephemeral=True, **conteudo)
        mensagem = await interaction.original_response()
        self.paineis_privados[chave] = mensagem
        return mensagem

    async def fechar_painel_privado(
        self,
        interaction: discord.Interaction,
        partida_id: str,
    ) -> None:
        chave = (partida_id, interaction.user.id)
        self.paineis_privados.pop(chave, None)
        if not interaction.response.is_done():
            await interaction.response.defer()
        try:
            await interaction.delete_original_response()
        except (discord.NotFound, discord.HTTPException):
            mensagem = interaction.message
            if mensagem is not None:
                try:
                    await mensagem.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass

    async def cog_load(self) -> None:
        self.bot.add_view(QuadribolView(self))
        self.tarefa_restaurar_paineis = asyncio.create_task(self._restaurar_paineis())

    async def cog_unload(self) -> None:
        if self.tarefa_restaurar_paineis is not None:
            self.tarefa_restaurar_paineis.cancel()

    async def _restaurar_paineis(self) -> None:
        """Recoloca a interface atual nas partidas persistidas após reiniciar."""
        from utils.quadribol import PASTA_PARTIDAS, carregar_partida

        await self.bot.wait_until_ready()
        if not PASTA_PARTIDAS.is_dir():
            return
        for caminho in PASTA_PARTIDAS.glob("*.md"):
            try:
                partida = carregar_partida(caminho)
                if not partida.canal_id or not partida.mensagem_id or partida.estado == "encerrada":
                    continue
                self.bot.add_view(
                    QuadribolView(self, partida),
                    message_id=partida.mensagem_id,
                )
                await self.atualizar_mensagem(partida)
            except (OSError, ValueError, TypeError, discord.HTTPException):
                continue

    async def autocomplete_personagem(
        self,
        interaction: discord.Interaction,
        atual: str,
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(
                name=f"{item.nome} — {casa_da_referencia(item)}"[:100],
                value=item.caminho.relative_to(item.caminho.parents[1]).as_posix()[:100],
            )
            for item in listar_fichas_elegiveis(atual)[:25]
        ]

    async def autocomplete_vassoura(
        self,
        interaction: discord.Interaction,
        atual: str,
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=descricao_vassoura(item)[:100], value=item.nome[:100])
            for item in listar_vassouras(atual)[:25]
        ]

    @app_commands.command(
        name="vassouras",
        description="Consulta as fichas completas das vassouras do Grimory.",
    )
    @app_commands.guild_only()
    async def vassouras(self, interaction: discord.Interaction) -> None:
        if not listar_vassouras():
            await interaction.response.send_message(
                "O catálogo de vassouras está vazio.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=embed_catalogo_vassouras(),
            view=VassourasLinhasView(interaction.user.id),
            ephemeral=True,
        )

    @app_commands.command(
        name="manobras",
        description="Consulta ou cria manobras para o Quadribol.",
    )
    @app_commands.guild_only()
    async def manobras(self, interaction: discord.Interaction) -> None:
        if not carregar_manobras():
            await interaction.response.send_message(
                "O catálogo de manobras está vazio.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=embed_central_manobras(),
            view=CentralManobrasView(interaction.user.id, self),
            ephemeral=True,
        )

    @app_commands.command(name="time", description="Consulta ou cria equipes de Quadribol.")
    @app_commands.guild_only()
    async def time(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.send_message(
            embed=embed_central_times(),
            view=CentralTimesView(interaction.user.id, self),
            ephemeral=True,
        )

    @app_commands.command(name="quadribol", description="Inicia o painel de uma partida de Quadribol.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def quadribol(
        self,
        interaction: discord.Interaction,
    ) -> None:
        membro = interaction.user
        if not isinstance(membro, discord.Member) or not membro.guild_permissions.manage_guild:
            await interaction.response.send_message("Você precisa da permissão **Gerenciar servidor** para usar este comando.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=embed_tipo_partida(),
            view=EscolherTipoPartidaView(self, membro.id),
            ephemeral=True,
        )

    def _localizar_por_id(self, partida_id: str) -> tuple[PartidaQuadribol, Path]:
        from utils.quadribol import PASTA_PARTIDAS, carregar_partida

        caminho = PASTA_PARTIDAS / f"{partida_id}.md"
        if not caminho.is_file():
            raise ValueError("A partida não foi encontrada.")
        return carregar_partida(caminho), caminho

    async def mutar_partida(self, partida_id: str, acao) -> PartidaQuadribol:
        async with self.bloqueio_partidas:
            partida, caminho = self._localizar_por_id(partida_id)
            acao(partida)
            salvar_partida(partida, caminho)
            return partida

    async def finalizar_partida(self, partida_id: str) -> PartidaQuadribol:
        async with self.bloqueio_partidas:
            partida, caminho = self._localizar_por_id(partida_id)
            if partida.tipo_partida == "Partida Oficial":
                estado = carregar_estado_taca()
                aplicar_resultado_na_taca(partida, estado)
                salvar_estado_taca(estado)
            else:
                if partida.estado != "aguardando_confirmacao":
                    raise ValueError("Encerre o tempo da partida antes de confirmar o resultado.")
                partida.estado = "encerrada"
                partida.eventos.append(EventoPartida(tipo="fim", casa=partida.vencedor(), descricao="Partida amistosa encerrada; resultado não altera a Taça das Casas."))
            salvar_partida(partida, caminho)
            return partida

    async def atualizar_mensagem(self, partida: PartidaQuadribol) -> None:
        canal = self.bot.get_channel(partida.canal_id)
        if canal is None:
            canal = await self.bot.fetch_channel(partida.canal_id)
        if hasattr(canal, "get_partial_message"):
            mensagem = canal.get_partial_message(partida.mensagem_id)
        elif hasattr(canal, "fetch_message"):
            mensagem = await canal.fetch_message(partida.mensagem_id)
        else:
            raise ValueError("O canal da partida não permite atualizar a mensagem.")
        encerrada = partida.estado == "encerrada"
        if encerrada:
            await mensagem.edit(
                embed=embed_resultado_partida(partida),
                view=None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            await mensagem.edit(
                embeds=embeds_partida(partida),
                view=QuadribolView(self, partida),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def publicar_evento(self, partida: PartidaQuadribol, embed: discord.Embed) -> None:
        canal = self.bot.get_channel(partida.canal_id)
        if canal is None:
            canal = await self.bot.fetch_channel(partida.canal_id)
        if not hasattr(canal, "send"):
            raise ValueError("O canal da partida não permite publicar a narração.")
        await canal.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    async def publicar_surgimentos(
        self,
        partida: PartidaQuadribol,
        eventos: list[EventoPartida],
    ) -> None:
        for evento in eventos:
            if evento.tipo == "surgimento_pomo":
                await self.publicar_evento(
                    partida,
                    embed_surgimento_pomo(partida, evento.alvo),
                )
