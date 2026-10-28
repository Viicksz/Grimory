from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from utils.fichas import (
    FichaPersonagem,
    PASTA_FICHAS,
    ReferenciaFicha,
    encontrar_ficha,
    listar_fichas,
    nome_com_estado_pv,
    salvar_ficha,
)

from utils.sessoes import (
    Encerramento,
    RespostaEncerramento,
    agora_iso,
    encerramento_ativo,
    listar_encerramentos,
    novo_encerramento,
    salvar_encerramento,
    ultimo_encerramento_concluido,
)


COR_SESSAO = 0x5865F2
ESTACOES = {
    "outono": ("Outono", "🍂", 0),
    "inverno": ("Inverno", "❄️", 28),
    "primavera": ("Primavera", "🌸", 63),
    "verao": ("Verão", "☀️", 98),
}
DIAS = {
    "segunda": ("segunda-feira", 0),
    "terca": ("terça-feira", 1),
    "quarta": ("quarta-feira", 2),
    "quinta": ("quinta-feira", 3),
    "sexta": ("sexta-feira", 4),
    "sabado": ("sábado", 5),
    "domingo": ("domingo", 6),
}
CICLO_DIAS = 182


def cabecalho_narrativo(titulo: str) -> str:
    return (
        "## ══════◄••📖••►══════\n"
        f"## {titulo}\n"
        "## ══════◄••📖••►══════"
    )


@dataclass(frozen=True)
class EventoAcademico:
    nome: str
    posicao: int
    data: str


EVENTOS = (
    EventoAcademico("Cerimônia de início de ano", 0, "Outono, 1ª semana, segunda-feira"),
    EventoAcademico("Festa de boas-vindas das snakes", 5, "Outono, 1ª semana, sábado"),
    EventoAcademico("Primeiro jogo de quadribol", 9, "Outono, 2ª semana, quarta-feira"),
    EventoAcademico("Segundo jogo de quadribol", 16, "Outono, 3ª semana, quarta-feira"),
    EventoAcademico("Final do jogo de quadribol", 23, "Outono, 4ª semana, quarta-feira"),
    EventoAcademico("Halloween", 27, "Outono, 4ª semana, domingo"),
    EventoAcademico("Primeiro jogo de quadribol", 37, "Inverno, 2ª semana, quarta-feira"),
    EventoAcademico("Valentines Day", 40, "Inverno, 2ª semana, sábado"),
    EventoAcademico("Segundo jogo de quadribol", 44, "Inverno, 3ª semana, quarta-feira"),
    EventoAcademico("Final do jogo de quadribol", 51, "Inverno, 4ª semana, quarta-feira"),
    EventoAcademico("Christmas Day", 53, "Inverno, 4ª semana, sexta-feira"),
    EventoAcademico("Winter Break", 56, "após o Inverno — uma semana de recesso"),
    EventoAcademico("Primeiro jogo de quadribol", 72, "Primavera, 2ª semana, quarta-feira"),
    EventoAcademico("Segundo jogo de quadribol", 79, "Primavera, 3ª semana, quarta-feira"),
    EventoAcademico("Final do jogo de quadribol", 86, "Primavera, 4ª semana, quarta-feira"),
    EventoAcademico("Easter Day", 90, "Primavera, 4ª semana, domingo"),
    EventoAcademico("Spring Break", 91, "após a Primavera — uma semana de recesso"),
    EventoAcademico("Dia de los muertos", 102, "Verão, 1ª semana, sexta-feira"),
    EventoAcademico("Primeiro jogo de quadribol", 107, "Verão, 2ª semana, quarta-feira"),
    EventoAcademico("Segundo jogo de quadribol", 114, "Verão, 3ª semana, quarta-feira"),
    EventoAcademico("N.O.M.s", 119, "Verão, 4ª semana, segunda-feira"),
    EventoAcademico("N.I.E.M.s", 120, "Verão, 4ª semana, terça-feira"),
    EventoAcademico("Final do jogo de quadribol", 121, "Verão, 4ª semana, quarta-feira"),
    EventoAcademico("Resultado das provas", 122, "Verão, 4ª semana, quinta-feira"),
    EventoAcademico("Summer Vacation", 126, "após o Verão — férias de dois meses"),
)


def posicao_calendario(estacao: str, semana: int, dia: str) -> int:
    if estacao not in ESTACOES or dia not in DIAS or semana not in {1, 2, 3, 4}:
        raise ValueError("Data narrativa inválida.")
    return ESTACOES[estacao][2] + (semana - 1) * 7 + DIAS[dia][1]


def evento_mais_proximo(estacao: str, semana: int, dia: str) -> tuple[EventoAcademico, bool]:
    atual = posicao_calendario(estacao, semana, dia)

    def chave(evento: EventoAcademico) -> tuple[int, int]:
        futuro = (evento.posicao - atual) % CICLO_DIAS
        passado = (atual - evento.posicao) % CICLO_DIAS
        return min(futuro, passado), futuro

    evento = min(EVENTOS, key=chave)
    return evento, evento.posicao == atual


def rotulo_data(resposta: RespostaEncerramento) -> str:
    nome_estacao, emoji, _ = ESTACOES[resposta.estacao]
    nome_dia, _ = DIAS[resposta.dia]
    return f"{emoji} {nome_estacao} • {resposta.semana}ª semana, {nome_dia}"


def localizar_ficha_participante(
    nome: str,
    usuario_id: int,
    identificador: str = "",
) -> ReferenciaFicha | None:
    if identificador:
        referencia = encontrar_ficha(identificador)
        if referencia is not None:
            return referencia

    referencia = encontrar_ficha(nome)
    if referencia is not None:
        return referencia

    proprias: list[ReferenciaFicha] = []
    for item in listar_fichas():
        try:
            ficha = FichaPersonagem.carregar(item.caminho)
        except (OSError, ValueError):
            continue
        if ficha.titular_id == usuario_id:
            proprias.append(item)
    return proprias[0] if len(proprias) == 1 else None


def identificador_ficha(referencia: ReferenciaFicha) -> str:
    return referencia.caminho.resolve().relative_to(PASTA_FICHAS.resolve()).as_posix()


def inteiro_recurso(
    valor: str,
    rotulo: str,
    *,
    permitir_negativo: bool = False,
) -> int | None:
    texto = valor.strip()
    if not texto:
        return None
    try:
        numero = int(texto)
    except ValueError as erro:
        regra = "um número inteiro" if permitir_negativo else "um número inteiro igual ou maior que zero"
        raise ValueError(f"{rotulo} deve ser {regra}.") from erro
    if numero < 0 and not permitir_negativo:
        raise ValueError(f"{rotulo} deve ser um número inteiro igual ou maior que zero.")
    return numero


def criar_embed_participante(encerramento: Encerramento, usuario_id: int) -> discord.Embed:
    participante = encerramento.participantes[usuario_id]
    resposta = participante.resposta
    nome_exibicao = nome_com_estado_pv(
        participante.nome,
        resposta.pv if resposta and resposta.pv is not None else 0,
    )
    embed = discord.Embed(
        title=f"{nome_exibicao} — Última Sessão",
        color=COR_SESSAO,
    )
    embed.description = f"<@{usuario_id}>"
    if resposta is None:
        embed.add_field(
            name="Registro",
            value="*Aguardando as informações deste personagem.*",
            inline=False,
        )
    else:
        evento, mesmo_dia = evento_mais_proximo(
            resposta.estacao,
            resposta.semana,
            resposta.dia,
        )
        embed.add_field(name="📅 Data", value=rotulo_data(resposta), inline=False)
        embed.add_field(
            name="🕰️ Horário",
            value=f"{resposta.hora}:{resposta.minuto:02d} {resposta.periodo}",
            inline=True,
        )
        embed.add_field(
            name="📆 Evento do dia" if mesmo_dia else "📆 Evento próximo",
            value=f"**{evento.nome}** — {evento.data}",
            inline=False,
        )
        embed.add_field(name="📍 Local", value=resposta.local, inline=False)
        embed.add_field(name="🎭 Ação", value=resposta.acao, inline=False)
        embed.add_field(name="🎯 Objetivo", value=resposta.objetivo, inline=False)
        if resposta.pv is not None:
            embed.add_field(name="❤️ PV", value=str(resposta.pv), inline=True)
        if resposta.ph is not None:
            embed.add_field(name="✨ PH", value=str(resposta.ph), inline=True)
    estado = "Encerramento concluído" if encerramento.concluido else "Encerramento em preenchimento"
    embed.set_footer(text=estado)
    return embed


def grupos_embeds(encerramento: Encerramento) -> list[list[discord.Embed]]:
    embeds = [
        criar_embed_participante(encerramento, usuario_id)
        for usuario_id in encerramento.participantes
    ]
    return [embeds[indice : indice + 10] for indice in range(0, len(embeds), 10)]


def eh_moderador(interaction: discord.Interaction, encerramento: Encerramento) -> bool:
    return (
        interaction.user.id == encerramento.moderador_id
        or interaction.permissions.manage_guild
    )


def opcao_padrao(valor: str, atual: str | int | None) -> bool:
    return atual is not None and str(valor) == str(atual)


class SeletorParticipantes(discord.ui.UserSelect):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Selecione os personagens da sessão",
            min_values=1,
            max_values=25,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if isinstance(view, PrepararEncerramentoView):
            view.selecionados = list(self.values)
        await interaction.response.defer()


class PrepararEncerramentoView(discord.ui.View):
    def __init__(self, cog: Narrativa, moderador_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.moderador_id = moderador_id
        self.selecionados: list[discord.Member | discord.User] = []
        self.add_item(SeletorParticipantes())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.moderador_id:
            return True
        await interaction.response.send_message(
            "Somente quem iniciou `/encerrar` pode usar esta seleção.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Criar Última Sessão", style=discord.ButtonStyle.success, emoji="✅", row=1)
    async def confirmar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        membros = [item for item in self.selecionados if not item.bot]
        if not membros:
            await interaction.response.send_message(
                "Selecione ao menos um jogador que não seja um bot.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            encerramento = await self.cog.criar_encerramento(interaction, membros)
        except ValueError as erro:
            await interaction.edit_original_response(content=str(erro), embed=None, view=None)
            return
        self.stop()
        await interaction.edit_original_response(
            content=(
                f"**Última Sessão** criada para {len(encerramento.participantes)} "
                "personagem(ns)."
            ),
            embed=None,
            view=None,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, row=1)
    async def cancelar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content="Criação cancelada.", embed=None, view=None)


class CalendarioView(discord.ui.View):
    def __init__(
        self,
        cog: Narrativa,
        encerramento_id: str,
        alvo_id: int,
        editor_id: int,
        resposta: RespostaEncerramento | None = None,
    ):
        super().__init__(timeout=600)
        self.cog = cog
        self.encerramento_id = encerramento_id
        self.alvo_id = alvo_id
        self.editor_id = editor_id
        self.resposta = resposta
        self.estacao = resposta.estacao if resposta else None
        self.semana = resposta.semana if resposta else None
        self.dia = resposta.dia if resposta else None

        estacao = discord.ui.Select(
            placeholder="Estação",
            options=[
                discord.SelectOption(
                    label=nome,
                    value=chave,
                    emoji=emoji,
                    default=opcao_padrao(chave, self.estacao),
                )
                for chave, (nome, emoji, _) in ESTACOES.items()
            ],
            row=0,
        )
        semana = discord.ui.Select(
            placeholder="Semana",
            options=[
                discord.SelectOption(
                    label=f"{numero}ª semana",
                    value=str(numero),
                    default=opcao_padrao(numero, self.semana),
                )
                for numero in range(1, 5)
            ],
            row=1,
        )
        dia = discord.ui.Select(
            placeholder="Dia da semana",
            options=[
                discord.SelectOption(
                    label=nome,
                    value=chave,
                    default=opcao_padrao(chave, self.dia),
                )
                for chave, (nome, _) in DIAS.items()
            ],
            row=2,
        )

        async def selecionar_estacao(interaction: discord.Interaction) -> None:
            self.estacao = estacao.values[0]
            await interaction.response.defer()

        async def selecionar_semana(interaction: discord.Interaction) -> None:
            self.semana = int(semana.values[0])
            await interaction.response.defer()

        async def selecionar_dia(interaction: discord.Interaction) -> None:
            self.dia = dia.values[0]
            await interaction.response.defer()

        estacao.callback = selecionar_estacao
        semana.callback = selecionar_semana
        dia.callback = selecionar_dia
        self.add_item(estacao)
        self.add_item(semana)
        self.add_item(dia)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.editor_id:
            return True
        await interaction.response.send_message("Este formulário não pertence a você.", ephemeral=True)
        return False

    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.primary, row=3)
    async def continuar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.estacao is None or self.semana is None or self.dia is None:
            await interaction.response.send_message(
                "Selecione a estação, a semana e o dia da semana.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Última Sessão — Horário",
                description="Agora selecione o horário narrativo deste personagem.",
                color=COR_SESSAO,
            ),
            view=HorarioView(
                self.cog,
                self.encerramento_id,
                self.alvo_id,
                self.editor_id,
                self.estacao,
                self.semana,
                self.dia,
                self.resposta,
            ),
        )


class HorarioView(discord.ui.View):
    def __init__(
        self,
        cog: Narrativa,
        encerramento_id: str,
        alvo_id: int,
        editor_id: int,
        estacao: str,
        semana: int,
        dia: str,
        resposta: RespostaEncerramento | None,
    ):
        super().__init__(timeout=600)
        self.cog = cog
        self.encerramento_id = encerramento_id
        self.alvo_id = alvo_id
        self.editor_id = editor_id
        self.estacao = estacao
        self.semana = semana
        self.dia = dia
        self.resposta = resposta
        self.hora = resposta.hora if resposta else None
        self.minuto = resposta.minuto if resposta else None
        self.periodo = resposta.periodo if resposta else None

        hora = discord.ui.Select(
            placeholder="Hora",
            options=[
                discord.SelectOption(
                    label=str(numero),
                    value=str(numero),
                    default=opcao_padrao(numero, self.hora),
                )
                for numero in range(1, 13)
            ],
            row=0,
        )
        minuto = discord.ui.Select(
            placeholder="Minutos",
            options=[
                discord.SelectOption(
                    label=f"{numero:02d}",
                    value=str(numero),
                    default=opcao_padrao(numero, self.minuto),
                )
                for numero in range(0, 60, 5)
            ],
            row=1,
        )
        periodo = discord.ui.Select(
            placeholder="AM ou PM",
            options=[
                discord.SelectOption(label=valor, value=valor, default=opcao_padrao(valor, self.periodo))
                for valor in ("AM", "PM")
            ],
            row=2,
        )

        async def selecionar_hora(interaction: discord.Interaction) -> None:
            self.hora = int(hora.values[0])
            await interaction.response.defer()

        async def selecionar_minuto(interaction: discord.Interaction) -> None:
            self.minuto = int(minuto.values[0])
            await interaction.response.defer()

        async def selecionar_periodo(interaction: discord.Interaction) -> None:
            self.periodo = periodo.values[0]
            await interaction.response.defer()

        hora.callback = selecionar_hora
        minuto.callback = selecionar_minuto
        periodo.callback = selecionar_periodo
        self.add_item(hora)
        self.add_item(minuto)
        self.add_item(periodo)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.editor_id:
            return True
        await interaction.response.send_message("Este formulário não pertence a você.", ephemeral=True)
        return False

    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.primary, row=3)
    async def continuar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.hora is None or self.minuto is None or self.periodo is None:
            await interaction.response.send_message(
                "Selecione a hora, os minutos e AM ou PM.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            DetalhesEncerramentoModal(
                self.cog,
                self.encerramento_id,
                self.alvo_id,
                self.estacao,
                self.semana,
                self.dia,
                self.hora,
                self.minuto,
                self.periodo,
                self.resposta,
            )
        )

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary, row=3)
    async def voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Última Sessão — Data",
                description="Selecione a data narrativa deste personagem.",
                color=COR_SESSAO,
            ),
            view=CalendarioView(
                self.cog,
                self.encerramento_id,
                self.alvo_id,
                self.editor_id,
                self.resposta,
            ),
        )


class DetalhesEncerramentoModal(discord.ui.Modal):
    def __init__(
        self,
        cog: Narrativa,
        encerramento_id: str,
        alvo_id: int,
        estacao: str,
        semana: int,
        dia: str,
        hora: int,
        minuto: int,
        periodo: str,
        resposta: RespostaEncerramento | None,
    ):
        super().__init__(title="Última Sessão — Personagem")
        self.cog = cog
        self.encerramento_id = encerramento_id
        self.alvo_id = alvo_id
        self.estacao = estacao
        self.semana = semana
        self.dia = dia
        self.hora = hora
        self.minuto = minuto
        self.periodo = periodo
        encerramento = cog.obter_encerramento(encerramento_id)
        participante = encerramento.participantes.get(alvo_id) if encerramento else None
        referencia = (
            localizar_ficha_participante(
                participante.nome,
                alvo_id,
                resposta.ficha if resposta else "",
            )
            if participante is not None
            else None
        )
        ficha = None
        if referencia is not None:
            try:
                ficha = FichaPersonagem.carregar(referencia.caminho)
            except (OSError, ValueError):
                referencia = None
        self.referencia_ficha = referencia
        self.local = discord.ui.TextInput(
            label="Local — onde você parou?",
            placeholder="Informe onde o personagem encerrou a sessão",
            default=resposta.local if resposta else None,
            max_length=500,
        )
        self.acao = discord.ui.TextInput(
            label="Ação — o que estava fazendo?",
            placeholder="Descreva a ação no momento da pausa",
            default=resposta.acao if resposta else None,
            style=discord.TextStyle.paragraph,
            max_length=1000,
        )
        self.objetivo = discord.ui.TextInput(
            label="Objetivo — o que pretende fazer?",
            placeholder="Descreva os próximos objetivos do personagem",
            default=resposta.objetivo if resposta else None,
            style=discord.TextStyle.paragraph,
            max_length=1000,
        )
        pv_atual = resposta.pv if resposta and resposta.pv is not None else ficha.pv if ficha else None
        ph_atual = resposta.ph if resposta and resposta.ph is not None else ficha.ph if ficha else None
        self.pv = discord.ui.TextInput(
            label="PV atual",
            placeholder="Pontos de Vida atuais",
            default=str(pv_atual) if pv_atual is not None else None,
            required=False,
            max_length=6,
        )
        self.ph = discord.ui.TextInput(
            label="PH atual",
            placeholder="Pontos de Habilidade atuais",
            default=str(ph_atual) if ph_atual is not None else None,
            required=False,
            max_length=6,
        )
        self.add_item(self.local)
        self.add_item(self.acao)
        self.add_item(self.objetivo)
        self.add_item(self.pv)
        self.add_item(self.ph)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            pv = inteiro_recurso(str(self.pv.value), "PV", permitir_negativo=True)
            ph = inteiro_recurso(str(self.ph.value), "PH")
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        resposta = RespostaEncerramento(
            estacao=self.estacao,
            semana=self.semana,
            dia=self.dia,
            hora=self.hora,
            minuto=self.minuto,
            periodo=self.periodo,
            local=str(self.local.value).strip(),
            acao=str(self.acao.value).strip(),
            objetivo=str(self.objetivo.value).strip(),
            atualizado_por=interaction.user.id,
            atualizado_em=agora_iso(),
            pv=pv,
            ph=ph,
            ficha=(identificador_ficha(self.referencia_ficha) if self.referencia_ficha else ""),
        )
        try:
            ficha_atualizada = await self.cog.salvar_resposta(
                self.encerramento_id,
                self.alvo_id,
                interaction,
                resposta,
            )
        except ValueError as erro:
            await interaction.edit_original_response(content=str(erro))
            return
        detalhe = ""
        if (pv is not None or ph is not None) and not ficha_atualizada:
            detalhe = (
                " PV e PH ficaram registrados nesta sessão, mas nenhuma ficha única foi "
                "identificada para atualização automática."
            )
        await interaction.edit_original_response(
            content=f"Resposta salva e embed do personagem atualizada.{detalhe}",
            embed=None,
            view=None,
        )


class CorrecaoView(discord.ui.View):
    def __init__(self, cog: Narrativa, encerramento: Encerramento, editor_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.encerramento = encerramento
        self.editor_id = editor_id
        self.alvo_id: int | None = None
        seletor = discord.ui.Select(
            placeholder="Escolha o personagem",
            options=[
                discord.SelectOption(
                    label=participante.nome[:100],
                    value=str(usuario_id),
                    description=("Resposta registrada" if participante.resposta else "Aguardando resposta"),
                )
                for usuario_id, participante in encerramento.participantes.items()
            ],
            row=0,
        )

        async def selecionar(interaction: discord.Interaction) -> None:
            self.alvo_id = int(seletor.values[0])
            await interaction.response.defer()

        seletor.callback = selecionar
        self.add_item(seletor)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.editor_id:
            return True
        await interaction.response.send_message("Este controle não pertence a você.", ephemeral=True)
        return False

    @discord.ui.button(label="Editar resposta", style=discord.ButtonStyle.primary, emoji="✏️", row=1)
    async def editar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.alvo_id is None:
            await interaction.response.send_message("Escolha primeiro um personagem.", ephemeral=True)
            return
        atual = self.cog.obter_encerramento(self.encerramento.identificador)
        if atual is None:
            await interaction.response.send_message("Este encerramento não foi encontrado.", ephemeral=True)
            return
        resposta = atual.participantes[self.alvo_id].resposta
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Correção — Data narrativa",
                description=f"Editando a resposta de **{atual.participantes[self.alvo_id].nome}**.",
                color=COR_SESSAO,
            ),
            view=CalendarioView(
                self.cog,
                atual.identificador,
                self.alvo_id,
                interaction.user.id,
                resposta,
            ),
        )


class EncerramentoPublicoView(discord.ui.View):
    def __init__(self, cog: Narrativa, encerramento_id: str, *, concluido: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.encerramento_id = encerramento_id
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id in {
                "narrativa:registrar",
                "narrativa:concluir",
            }:
                item.disabled = concluido

    @discord.ui.button(
        label="Registrar ou atualizar",
        style=discord.ButtonStyle.primary,
        emoji="📝",
        custom_id="narrativa:registrar",
    )
    async def registrar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        encerramento = self.cog.obter_encerramento(self.encerramento_id)
        if encerramento is None:
            await interaction.response.send_message("Este encerramento não foi encontrado.", ephemeral=True)
            return
        if encerramento.concluido:
            await interaction.response.send_message("Este encerramento já foi concluído.", ephemeral=True)
            return
        if interaction.user.id not in encerramento.participantes:
            await interaction.response.send_message(
                "Você não foi mencionado pelo moderador neste encerramento.",
                ephemeral=True,
            )
            return
        participante = encerramento.participantes[interaction.user.id]
        if isinstance(interaction.user, discord.Member):
            participante.nome = interaction.user.display_name
            salvar_encerramento(encerramento)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Última Sessão — Data",
                description="Selecione a data narrativa do seu personagem.",
                color=COR_SESSAO,
            ),
            view=CalendarioView(
                self.cog,
                encerramento.identificador,
                interaction.user.id,
                interaction.user.id,
                participante.resposta,
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Corrigir respostas",
        style=discord.ButtonStyle.secondary,
        emoji="✏️",
        custom_id="narrativa:corrigir",
    )
    async def corrigir(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        encerramento = self.cog.obter_encerramento(self.encerramento_id)
        if encerramento is None:
            await interaction.response.send_message("Este encerramento não foi encontrado.", ephemeral=True)
            return
        if not eh_moderador(interaction, encerramento):
            await interaction.response.send_message(
                "Somente moderadores podem corrigir respostas.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Corrigir Última Sessão",
                description="Selecione o personagem cuja resposta deseja corrigir.",
                color=COR_SESSAO,
            ),
            view=CorrecaoView(self.cog, encerramento, interaction.user.id),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Concluir encerramento",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="narrativa:concluir",
    )
    async def concluir(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        encerramento = self.cog.obter_encerramento(self.encerramento_id)
        if encerramento is None:
            await interaction.response.send_message("Este encerramento não foi encontrado.", ephemeral=True)
            return
        if not eh_moderador(interaction, encerramento):
            await interaction.response.send_message(
                "Somente moderadores podem concluir este encerramento.",
                ephemeral=True,
            )
            return
        faltantes = [
            participante.nome
            for participante in encerramento.participantes.values()
            if participante.resposta is None
        ]
        if faltantes:
            nomes = "\n".join(f"• {nome}" for nome in faltantes)
            await interaction.response.send_message(
                f"Ainda faltam respostas de:\n{nomes}",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.cog.concluir_encerramento(encerramento.identificador)
        await interaction.edit_original_response(content="Encerramento concluído. `/recapitular` já está disponível.")


class Narrativa(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bloqueio = asyncio.Lock()

    async def cog_load(self) -> None:
        for encerramento in listar_encerramentos():
            if encerramento.mensagens_discord:
                self.bot.add_view(
                    EncerramentoPublicoView(
                        self,
                        encerramento.identificador,
                        concluido=encerramento.concluido,
                    ),
                    message_id=encerramento.mensagens_discord[0],
                )

    def obter_encerramento(self, identificador: str) -> Encerramento | None:
        return next(
            (item for item in listar_encerramentos() if item.identificador == identificador),
            None,
        )

    async def obter_canal(self, canal_id: int):
        canal = self.bot.get_channel(canal_id)
        if canal is None:
            canal = await self.bot.fetch_channel(canal_id)
        return canal

    async def criar_encerramento(
        self,
        interaction: discord.Interaction,
        membros: list[discord.Member | discord.User],
    ) -> Encerramento:
        if interaction.guild_id is None or interaction.channel_id is None:
            raise ValueError("Use `/encerrar` dentro de um canal do servidor.")
        async with self.bloqueio:
            if encerramento_ativo(interaction.guild_id):
                raise ValueError("Já existe uma Última Sessão em preenchimento neste servidor.")
            unicos = {membro.id: membro for membro in membros}
            encerramento = novo_encerramento(
                interaction.guild_id,
                interaction.channel_id,
                interaction.user.id,
                [(membro.id, membro.display_name) for membro in unicos.values()],
            )
            salvar_encerramento(encerramento)

            canal = interaction.channel
            if canal is None or not hasattr(canal, "send"):
                raise ValueError("Não consegui publicar o encerramento neste canal.")
            grupos = grupos_embeds(encerramento)
            mensagens: list[discord.Message] = []
            try:
                for indice, embeds in enumerate(grupos):
                    mensagem = await canal.send(
                        content=cabecalho_narrativo("Última Sessão") if indice == 0 else None,
                        embeds=embeds,
                        view=(
                            EncerramentoPublicoView(self, encerramento.identificador)
                            if indice == 0
                            else None
                        ),
                        allowed_mentions=discord.AllowedMentions(users=True),
                    )
                    mensagens.append(mensagem)
            except discord.HTTPException as erro:
                raise ValueError(f"Não consegui publicar a Última Sessão: {erro}") from erro
            encerramento.mensagens_discord = [mensagem.id for mensagem in mensagens]
            salvar_encerramento(encerramento)
            return encerramento

    async def atualizar_mensagens(self, encerramento: Encerramento) -> None:
        canal = await self.obter_canal(encerramento.canal_id)
        grupos = grupos_embeds(encerramento)
        for indice, mensagem_id in enumerate(encerramento.mensagens_discord):
            if indice >= len(grupos):
                break
            try:
                mensagem = await canal.fetch_message(mensagem_id)
                await mensagem.edit(
                    embeds=grupos[indice],
                    view=(
                        EncerramentoPublicoView(
                            self,
                            encerramento.identificador,
                            concluido=encerramento.concluido,
                        )
                        if indice == 0
                        else None
                    ),
                )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue

    async def salvar_resposta(
        self,
        identificador: str,
        alvo_id: int,
        interaction: discord.Interaction,
        resposta: RespostaEncerramento,
    ) -> bool:
        ficha_atualizada: FichaPersonagem | None = None
        caminho_ficha: Path | None = None
        async with self.bloqueio:
            encerramento = self.obter_encerramento(identificador)
            if encerramento is None or alvo_id not in encerramento.participantes:
                raise ValueError("Este personagem não pertence ao encerramento.")
            moderador = eh_moderador(interaction, encerramento)
            if encerramento.concluido and not moderador:
                raise ValueError("Este encerramento já foi concluído.")
            if interaction.user.id != alvo_id and not moderador:
                raise ValueError("Você não pode alterar a resposta de outro personagem.")
            participante = encerramento.participantes[alvo_id]
            if interaction.user.id == alvo_id and isinstance(interaction.user, discord.Member):
                participante.nome = interaction.user.display_name
            referencia = localizar_ficha_participante(
                participante.nome,
                alvo_id,
                resposta.ficha,
            )
            if referencia is not None and (resposta.pv is not None or resposta.ph is not None):
                ficha_atualizada = FichaPersonagem.carregar(referencia.caminho)
                if resposta.pv is not None:
                    ficha_atualizada.pv = resposta.pv
                if resposta.ph is not None:
                    ficha_atualizada.ph = resposta.ph
                salvar_ficha(ficha_atualizada, referencia.caminho)
                caminho_ficha = referencia.caminho
                resposta.ficha = identificador_ficha(referencia)
            participante.resposta = resposta
            salvar_encerramento(encerramento)
        await self.atualizar_mensagens(encerramento)
        if ficha_atualizada is not None and caminho_ficha is not None:
            from comandos.ficha import sincronizar_publicacao_personagem

            await sincronizar_publicacao_personagem(
                interaction,
                ficha_atualizada,
                caminho_ficha,
            )
        return ficha_atualizada is not None

    async def concluir_encerramento(self, identificador: str) -> None:
        async with self.bloqueio:
            encerramento = self.obter_encerramento(identificador)
            if encerramento is None:
                raise ValueError("Este encerramento não foi encontrado.")
            if any(item.resposta is None for item in encerramento.participantes.values()):
                raise ValueError("Ainda existem personagens sem resposta.")
            encerramento.concluido = True
            encerramento.concluido_em = agora_iso()
            salvar_encerramento(encerramento)
        await self.atualizar_mensagens(encerramento)

    @app_commands.command(name="encerrar", description="Inicia o registro da Última Sessão dos personagens.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def encerrar(self, interaction: discord.Interaction) -> None:
        membro = interaction.user
        if not isinstance(membro, discord.Member) or not membro.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Você precisa da permissão **Gerenciar servidor** para usar `/encerrar`.",
                ephemeral=True,
            )
            return
        if interaction.guild_id is not None and encerramento_ativo(interaction.guild_id):
            await interaction.response.send_message(
                "Já existe uma **Última Sessão** em preenchimento neste servidor.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Última Sessão — Participantes",
                description=(
                    "Selecione somente os jogadores que poderão registrar onde seus "
                    "personagens encerraram a sessão."
                ),
                color=COR_SESSAO,
            ),
            view=PrepararEncerramentoView(self, membro.id),
            ephemeral=True,
        )

    @app_commands.command(name="recapitular", description="Mostra os detalhes da última sessão concluída.")
    @app_commands.guild_only()
    async def recapitular(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("Use `/recapitular` em um servidor.", ephemeral=True)
            return
        encerramento = ultimo_encerramento_concluido(interaction.guild_id)
        if encerramento is None:
            await interaction.response.send_message(
                "Ainda não existe uma **Última Sessão** concluída neste servidor.",
                ephemeral=True,
            )
            return
        grupos = grupos_embeds(encerramento)
        await interaction.response.send_message(
            content=cabecalho_narrativo("Recapitulação da Última Sessão"),
            embeds=grupos[0],
            allowed_mentions=discord.AllowedMentions.none(),
        )
        for embeds in grupos[1:]:
            await interaction.followup.send(
                embeds=embeds,
                allowed_mentions=discord.AllowedMentions.none(),
            )
