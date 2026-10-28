from __future__ import annotations

import asyncio
import random
import re
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from comandos.executar import (
    CORES_FEITICOS,
    COR_EMBED_FEITICO,
    GrupoIndice,
    ItemIndice,
    campos_normalizados,
    carregar_todos_feiticos,
    criar_embeds_entrada,
    criar_embeds_indice,
    criar_grupos_indice,
    localizar_links_oficiais,
    normalizar_ano,
)
from comandos.ficha import (
    LOCKS_FICHA,
    acoes_ph_habilidade,
    carregar_habilidade,
    sincronizar_publicacao_personagem,
)
from comandos.preparar import interpretar_pocao
from utils.biblioteca import BibliotecaCategoria, normalizar_rotulo
from utils.fichas import (
    EMOJIS_PASTAS_FICHA,
    ORDEM_PASTAS_FICHA,
    FichaPersonagem,
    bonus_pericia,
    paginas_fichas_alfabeticas,
    salvar_ficha,
)
from utils.fichas_criaturas import (
    FichaCriatura,
    PERICULOSIDADES,
    somar_atributo_ao_dano,
)
from utils.inventario import consumir_item, inteiro_positivo
from utils.combate import (
    DESCANSOS,
    EQUIPE_ALIADOS,
    EQUIPE_OPONENTES,
    PASTA_COMBATES,
    Combate,
    EventoCombate,
    ParticipanteCombate,
    ReferenciaCombatente,
    aplicar_dano_combate,
    ativar_habilidade_combate,
    adicionar_participante,
    alterar_recursos,
    avancar_turno,
    carregar_combate,
    criar_combate,
    criar_novo_combate,
    encerrar_combate,
    extrair_expressao_dano,
    encontrar_combate_por_mensagem,
    iniciar_combate,
    listar_referencias_combate,
    remover_participante,
    registrar_acao_narrativa,
    registrar_ataque_combate,
    rolar_expressao_dano,
    salvar_combate,
    valores_rolaveis,
)


COR_COMBATE = 0x992D22
EMOJI_ALIADOS = "👥"
EMOJI_OPONENTES = "🔥"
EMOJI_COMBATE = "⚔️"
EMOJI_ESQUIVA = "💨"
EMOJI_DEFESA = "🛡️"
EMOJI_CURA = "💖"
EMOJI_ATAQUE = "🗡️"
EMOJI_HABILIDADE = "📋"
EMOJI_FEITICO = "🪄"
EMOJI_ARMA = "🔪"
EMOJI_POCAO = "🧪"
POCOES_BIBLIOTECA = BibliotecaCategoria("poções")
PERFIS_REACAO_MAGICA = {
    normalizar_rotulo("Aequora Teggo"): "fogo",
    normalizar_rotulo("Deflecto"): "lampejo_intermediario",
    normalizar_rotulo("Impedimenta"): "conjuracao",
    normalizar_rotulo("Impedimenta Trevolli"): "lampejo",
    normalizar_rotulo("Protego"): "duelos_direto",
    normalizar_rotulo("Redderio"): "lampejo_ou_azaracao",
    normalizar_rotulo("Repellere Basiorum"): "basico_direto",
    normalizar_rotulo("Repellium"): "basico_direto",
    normalizar_rotulo("Repello"): "corporeo",
    normalizar_rotulo("Specullum Duo"): "lampejo",
    normalizar_rotulo("Vital Reflectus"): "avada_kedavra",
    normalizar_rotulo("Úmero Miratta"): "qualquer_feitico",
}
VIDEOS_HOMENAGEM = (
    "https://static.klipy.com/ii/4e7bea9f7a3371424e6c16ebc93252fe/55/79/nvooU8vfAl6VhP4LUB4A.webm",
    "https://static.klipy.com/ii/39f2394ae36df6e199be9eb7c9fa1012/2b/c9/qQu7aXfJFQ5uM8TQR.webm",
    "https://static.klipy.com/ii/35ccce3d852f7995dd2da910f2abd795/05/eb/HwDi72WZg0vexc.webm",
    "https://static.klipy.com/ii/d7aec6f6f171607374b2065c836f92f4/0b/e2/m1z82EmUI0ZzYCV.webm",
)


def _estado_participante(participante: ParticipanteCombate) -> str:
    if participante.estado == "morto":
        return "Morto"
    if participante.estado == "incapacitado" or participante.pv_atual <= 0:
        return "Incapacitado"
    return ""


def _linha_participante(
    participante: ParticipanteCombate,
    *,
    atual: bool = False,
    posicao: int | None = None,
) -> str:
    prefixo = "➤ " if atual else ""
    ordem = f"`{posicao:02d}` " if posicao is not None else ""
    iniciativa = (
        f" • Inic. {participante.iniciativa_total}"
        if participante.iniciativa_dado
        else ""
    )
    origem = "Criatura" if participante.tipo_ficha == "criatura" else "Personagem"
    estado = _estado_participante(participante)
    estado_texto = f" • **{estado}**" if estado else ""
    return (
        f"{prefixo}{ordem}**{participante.nome}**{estado_texto}\n"
        f"> {participante.recurso_vida} `{participante.pv_atual}/{participante.pv_maximo}` • "
        f"PH `{participante.ph_atual}/{participante.ph_maximo}`{iniciativa} • {origem}"
    )


def _campo_equipe(combate: Combate, equipe: str) -> str:
    participantes = combate.por_equipe(equipe)
    if not participantes:
        return "*Nenhuma ficha adicionada.*"
    atual = combate.participante_atual()
    linhas: list[str] = []
    for indice, participante in enumerate(combate.participantes, 1):
        if participante.equipe != equipe:
            continue
        linhas.append(
            _linha_participante(
                participante,
                atual=atual is participante,
                posicao=indice if combate.estado == "ativo" else None,
            )
        )
    texto = "\n".join(linhas)
    if len(texto) <= 1024:
        return texto
    visiveis: list[str] = []
    usados = 0
    for linha in linhas:
        if usados + len(linha) + 1 > 940:
            break
        visiveis.append(linha)
        usados += len(linha) + 1
    restantes = len(linhas) - len(visiveis)
    return "\n".join(visiveis) + f"\n*…e mais {restantes} participante(s).*"


def _rodada_por_extenso(rodada: int) -> str:
    nomes = {
        1: "Primeira",
        2: "Segunda",
        3: "Terceira",
        4: "Quarta",
        5: "Quinta",
        6: "Sexta",
        7: "Sétima",
        8: "Oitava",
        9: "Nona",
        10: "Décima",
    }
    return nomes.get(rodada, f"{rodada}ª")


def _marcacao_tempo(combate: Combate) -> str:
    return (
        f"⏱️ **{combate.indice_turno + 1}º turno da "
        f"{_rodada_por_extenso(combate.rodada)} Rodada**"
    )


def _simbolo_acao(disponivel: bool) -> str:
    return "✅" if disponivel else "⛔"


def _texto_acoes(participante: ParticipanteCombate) -> str:
    completa = not (
        participante.acao_padrao_usada
        or participante.acao_movimento_usada
        or participante.acao_livre_usada
    )
    return "\n".join(
        (
            f"Ação Completa: {_simbolo_acao(completa)}",
            f"Ação Padrão: {_simbolo_acao(not participante.acao_padrao_usada)}",
            f"Ação de Movimento: {_simbolo_acao(not participante.acao_movimento_usada)}",
            f"Ação Livre: {_simbolo_acao(not participante.acao_livre_usada)}",
        )
    )


def embed_painel_combate(
    titulo: str,
    descricao: str,
    *,
    participante: ParticipanteCombate | None = None,
) -> discord.Embed:
    embed = discord.Embed(title=titulo, description=descricao, color=COR_COMBATE)
    if participante is not None:
        embed.add_field(
            name="Ações disponíveis",
            value=_texto_acoes(participante),
            inline=False,
        )
    return embed


def embed_acoes_turno(
    participante: ParticipanteCombate,
    descricao: str = "Escolha se usará uma habilidade antes do ataque.",
) -> discord.Embed:
    return embed_painel_combate(
        f"{EMOJI_ATAQUE} Turno de {participante.nome}",
        descricao,
        participante=participante,
    )


def embed_combate(combate: Combate) -> discord.Embed:
    titulos_estado = {
        "preparacao": "Preparação",
        "ativo": f"Rodada {combate.rodada}",
        "encerrado": "Encerrado",
    }
    atual = combate.participante_atual()
    descricao = (
        "Adicione as fichas das duas equipes e inicie a batalha."
        if combate.estado == "preparacao"
        else (
            f"{_marcacao_tempo(combate)}\n"
            f"É o turno de **{atual.nome}**, dos **{atual.equipe}**."
            if atual is not None
            else "Não há participante apto a agir."
        )
    )
    embed = discord.Embed(
        title=f"{EMOJI_COMBATE} Combate",
        description=descricao,
        color=COR_COMBATE,
    )
    embed.add_field(
        name=f"{EMOJI_ALIADOS} Aliados",
        value=_campo_equipe(combate, EQUIPE_ALIADOS),
        inline=False,
    )
    embed.add_field(
        name=f"{EMOJI_OPONENTES} Oponentes",
        value=_campo_equipe(combate, EQUIPE_OPONENTES),
        inline=False,
    )
    embed.set_footer(
        text=(
            f"{titulos_estado[combate.estado]} • PV/Alma e PH são temporários e não alteram as fichas"
        )
    )
    return embed


def embed_relatorio(combate: Combate) -> discord.Embed:
    aliados = combate.por_equipe(EQUIPE_ALIADOS)
    oponentes = combate.por_equipe(EQUIPE_OPONENTES)
    vivos = [item for item in combate.participantes if item.vivo]
    mortos = [item for item in combate.participantes if not item.vivo]
    embed = discord.Embed(
        title=f"{EMOJI_COMBATE} Relatório do combate",
        description=f"A batalha terminou após **{combate.rodada} rodada(s)**.",
        color=discord.Color.dark_red(),
    )
    embed.add_field(name=f"{EMOJI_ALIADOS} Aliados", value=str(len(aliados)), inline=True)
    embed.add_field(name=f"{EMOJI_OPONENTES} Oponentes", value=str(len(oponentes)), inline=True)
    embed.add_field(name="Sobreviventes", value=str(len(vivos)), inline=True)
    destaques = sorted(
        combate.participantes,
        key=lambda item: (item.dano_causado, item.cura_realizada, item.criticos),
        reverse=True,
    )[:5]
    if destaques:
        embed.add_field(
            name="Resumo dos participantes",
            value="\n".join(
                f"**{item.nome}:** {item.dano_causado} dano causado • "
                f"{item.dano_recebido} recebido • {EMOJI_CURA} {item.cura_realizada} recuperado • "
                f"{item.criticos} crítico(s)"
                for item in destaques
            )[:1024],
            inline=False,
        )
    if mortos:
        embed.add_field(
            name="🕯️ Honra aos que ficaram, descansem em paz 🕊",
            value="\n".join(f"• **{item.nome}** — {item.equipe}" for item in mortos)[:1024],
            inline=False,
        )
    embed.set_footer(text="Os valores temporários de PV/Alma e PH não foram gravados nas fichas.")
    return embed


def embed_rolagem(
    participante: ParticipanteCombate,
    teste: str,
    bonus: int,
    total: int,
    *,
    dado: int | None,
) -> discord.Embed:
    origem = "Rolagem externa" if dado is None else f"d20 `{dado}` + bônus `{bonus:+d}`"
    return discord.Embed(
        title=f"{participante.nome} — {teste}",
        description=f"{origem}\n## Total: `{total}`",
        color=COR_COMBATE,
    )


def _ficha_participante(
    participante: ParticipanteCombate,
) -> FichaPersonagem | FichaCriatura:
    caminho = Path(participante.caminho_ficha)
    if participante.tipo_ficha == "criatura":
        return FichaCriatura.carregar(caminho)
    return FichaPersonagem.carregar(caminho)


def _bonus_pericia_ficha(
    ficha: FichaPersonagem | FichaCriatura,
    nome: str,
) -> int:
    return max(
        bonus_pericia(nome, ficha.pericias.get(nome, 0), ficha.atributos),
    )


def _categoria_aptidao(categoria: str) -> str:
    aliases = {
        "dcat": "Defesa contra Arte das Trevas",
        "defesa contra as artes das trevas": "Defesa contra Arte das Trevas",
        "defesa contra arte das trevas": "Defesa contra Arte das Trevas",
    }
    return aliases.get(normalizar_rotulo(categoria), categoria)


def _cd_feitico_por_ficha(
    item: ItemIndice,
    ficha: FichaPersonagem,
) -> tuple[int, str]:
    campos = campos_normalizados(item.entrada)
    tabela = campos.get("dificuldade por ano", "")
    correspondencia = re.search(r"([1-7])", ficha.ano or "")
    rotulo = f"{correspondencia.group(1)} ano" if correspondencia else "+18y"
    for linha in tabela.splitlines():
        if ":" not in linha:
            continue
        nome, valor = linha.split(":", 1)
        if normalizar_rotulo(nome).replace("º", "").replace("°", "") != rotulo:
            continue
        numero = re.search(r"\d+", valor)
        if numero:
            return int(numero.group()), nome.strip()
    raise ValueError(
        f"{item.nome} não possui dificuldade cadastrada para {ficha.ano or '+18y'}."
    )


def _feitico_eh_lampejo(item: ItemIndice) -> bool:
    perfil = getattr(item.entrada, "perfil_combate", None)
    if perfil:
        return perfil.get("mira") == "Lampejo"
    return "lampejo" in normalizar_rotulo(item.entrada.descricao)


def _feitico_eh_reacao_magica(item: ItemIndice) -> bool:
    """Usa somente reações imediatas revisadas na biblioteca oficial."""
    perfil = getattr(item.entrada, "perfil_combate", None)
    if perfil:
        defesa = perfil.get("defesa", {})
        contra = perfil.get("contra_feitico", {})
        return defesa.get("momento") in {"Reação", "Ambas"} or bool(
            contra.get("habilitado") and contra.get("momento") == "Reação"
        )
    return normalizar_rotulo(item.nome) in PERFIS_REACAO_MAGICA


def _ano_numerico(texto: str) -> int:
    numero = re.search(r"([1-7])", texto or "")
    if numero:
        return int(numero.group(1))
    return 8 if "18" in (texto or "") else 0


def _feitico_disponivel_para_ficha(
    item: ItemIndice,
    ficha: FichaPersonagem,
) -> bool:
    campos = campos_normalizados(item.entrada)
    ano_ficha = _ano_numerico(ficha.ano)
    ano_desbloqueio = _ano_numerico(campos.get("ano de desbloqueio", ""))
    if not ano_ficha or not ano_desbloqueio or ano_ficha < ano_desbloqueio:
        return False
    aptidao = _categoria_aptidao(campos.get("categoria", ""))
    return ficha.aptidoes.get(aptidao, 0) != 0


def _reacao_magica_compativel(
    reacao: ItemIndice,
    ataque: ItemIndice | None,
    *,
    lampejo: bool,
) -> bool:
    perfil_reacao = getattr(reacao.entrada, "perfil_combate", None)
    if perfil_reacao:
        defesa = perfil_reacao.get("defesa", {})
        contra = perfil_reacao.get("contra_feitico", {})
        nomes = {
            normalizar_rotulo(nome)
            for nome in contra.get("feiticos", [])
            if str(nome).strip()
        }
        if ataque and normalizar_rotulo(ataque.nome) in nomes:
            return True
        propriedades = {
            normalizar_rotulo(valor)
            for valor in (*defesa.get("propriedades", []), *contra.get("propriedades", []))
            if str(valor).strip()
        }
        if "qualquer feitico" in propriedades:
            return ataque is not None
        perfil_ataque = getattr(ataque.entrada, "perfil_combate", None) if ataque else None
        if perfil_ataque:
            dano = perfil_ataque.get("dano", {})
            marcadores = {
                normalizar_rotulo(perfil_ataque.get("mira", "")),
                *(normalizar_rotulo(tipo) for tipo in perfil_ataque.get("tipos", [])),
                normalizar_rotulo(dano.get("tipo_inicial", "")),
                normalizar_rotulo(dano.get("tipo_sustentado", "")),
            }
            marcadores.discard("")
            return bool(propriedades & marcadores)
        return False
    perfil = PERFIS_REACAO_MAGICA.get(normalizar_rotulo(reacao.nome), "")
    if not perfil:
        return False
    nome_ataque = normalizar_rotulo(ataque.nome) if ataque else ""
    campos = campos_normalizados(ataque.entrada) if ataque else {}
    descricao = normalizar_rotulo(ataque.entrada.descricao) if ataque else ""
    categoria = normalizar_rotulo(campos.get("categoria", ""))
    grau = normalizar_rotulo(campos.get("grau de dificuldade", ""))
    eh_azaracao = "azaracao" in descricao
    eh_direto = lampejo or eh_azaracao or "diret" in descricao

    if perfil == "qualquer_feitico":
        return ataque is not None
    if perfil == "avada_kedavra":
        return nome_ataque == normalizar_rotulo("Avada Kedavra")
    if perfil == "lampejo":
        return lampejo
    if perfil == "lampejo_intermediario":
        return lampejo and grau.startswith("intermediario")
    if perfil == "fogo":
        return any(
            marcador in descricao
            for marcador in ("fogo", "flama", "chama", "igne", "incend")
        )
    if perfil == "duelos_direto":
        return categoria == normalizar_rotulo("Duelos") and eh_direto
    if perfil == "lampejo_ou_azaracao":
        return lampejo or eh_azaracao
    if perfil == "basico_direto":
        return grau.startswith("basico") and eh_direto
    if perfil == "corporeo":
        return any(
            marcador in descricao
            for marcador in ("corporeo", "objeto", "projetil", "corpo lancado")
        )
    if perfil == "conjuracao":
        return ataque is not None
    return False


def _encontrar_feitico_combate(nome: str) -> ItemIndice | None:
    chave = normalizar_rotulo(nome)
    return next(
        (item for item in carregar_todos_feiticos() if normalizar_rotulo(item.nome) == chave),
        None,
    )


def _reacoes_magicas_disponiveis(
    ficha: FichaPersonagem,
    nome_ataque: str,
    *,
    lampejo: bool,
) -> list[ItemIndice]:
    ataque = _encontrar_feitico_combate(nome_ataque)
    return [
        item
        for item in carregar_todos_feiticos()
        if _feitico_eh_reacao_magica(item)
        and _feitico_disponivel_para_ficha(item, ficha)
        and _reacao_magica_compativel(item, ataque, lampejo=lampejo)
    ]


def _ajuste_cd_reacao(item: ItemIndice) -> int:
    perfil = getattr(item.entrada, "perfil_combate", None)
    if perfil:
        return int(perfil.get("defesa", {}).get("ajuste_cd_reacao", 0) or 0)
    descricao = normalizar_rotulo(item.entrada.descricao)
    encontrado = re.search(
        r"(?:conjurad[oa]|usad[oa]) como reacao[^.]{0,100}?\+(\d+)",
        descricao,
    )
    return int(encontrado.group(1)) if encontrado else 0


def _dano_feitico(item: ItemIndice) -> str:
    perfil = getattr(item.entrada, "perfil_combate", None)
    if perfil:
        return str(perfil.get("dano", {}).get("inicial", "")).strip()
    return item.entrada.descricao


def _armas_participante(participante: ParticipanteCombate) -> list[dict[str, str]]:
    try:
        ficha = _ficha_participante(participante)
    except (OSError, ValueError):
        return []
    if isinstance(ficha, FichaCriatura):
        return ficha.armas_naturais
    return [
        {
            **item,
            "categoria": item.get("categoria", "Armas"),
            "tipo de dano": item.get("tipo de dano", item.get("tipo", "")),
            "crítico": item.get("crítico", item.get("critico", "")),
            "dano": somar_atributo_ao_dano(item.get("dano", ""), ficha.atributos),
        }
        for item in ficha.itens
        if normalizar_rotulo(item.get("categoria", "")) == normalizar_rotulo("Armas")
        and inteiro_positivo(item.get("quantidade", "0"), 0) > 0
    ]


def _pocoes_participante(participante: ParticipanteCombate) -> list[dict[str, str]]:
    try:
        ficha = _ficha_participante(participante)
    except (OSError, ValueError):
        return []
    if not isinstance(ficha, FichaPersonagem):
        return []
    return [
        dict(item)
        for item in ficha.itens
        if normalizar_rotulo(item.get("categoria", "")) == normalizar_rotulo("Poções")
        and inteiro_positivo(item.get("quantidade", "0"), 0) > 0
    ]


def _dados_pocao(nome: str) -> tuple[str, str, str]:
    conteudo = POCOES_BIBLIOTECA.ler_entrada(nome)
    if conteudo is None:
        return "", "Efeito não localizado na biblioteca; o mestre define sua aplicação.", ""
    entrada, _, _ = interpretar_pocao(conteudo)
    campos = {normalizar_rotulo(chave): valor for chave, valor in entrada.campos.items()}
    return (
        entrada.descricao,
        campos.get(normalizar_rotulo("Efeito"), "Efeito definido pela descrição oficial."),
        campos.get(normalizar_rotulo("Consumo"), ""),
    )


def _embed_pocao(
    participante: ParticipanteCombate,
    pocao: dict[str, str],
    *,
    alvo: ParticipanteCombate | None = None,
) -> discord.Embed:
    nome = pocao.get("nome", "Poção")
    descricao, efeito, consumo = _dados_pocao(nome)
    embed = discord.Embed(title=f"{EMOJI_POCAO} {nome}", description=descricao or None, color=0x66F060)
    embed.add_field(name="Efeito oficial", value=efeito[:1024], inline=False)
    if consumo:
        embed.add_field(name="Forma de uso", value=consumo[:1024], inline=False)
    embed.add_field(
        name="Quantidade disponível",
        value=f"{inteiro_positivo(pocao.get('quantidade', '0'), 0)} frasco(s)",
        inline=True,
    )
    if alvo is not None:
        embed.add_field(name="Alvo escolhido", value=alvo.nome, inline=True)
    embed.set_footer(text=f"Inventário de {participante.nome}")
    return embed


def _embed_arma(participante: ParticipanteCombate, arma: dict[str, str]) -> discord.Embed:
    embed = discord.Embed(
        title=arma.get("nome", "Arma"),
        description=arma.get("descrição", arma.get("descricao", "")) or None,
        color=COR_COMBATE,
    )
    for rotulo, chave in (
        ("Categoria", "categoria"),
        ("Dano", "dano"),
        ("Tipo de dano", "tipo de dano"),
        ("Crítico", "crítico"),
        ("Alcance", "alcance"),
    ):
        valor = arma.get(chave, "").strip()
        if valor:
            embed.add_field(name=rotulo, value=valor, inline=True)
    embed.set_footer(text=f"Arma registrada na ficha de {participante.nome}")
    return embed


def _tipo_ataque_arma(arma: dict[str, str]) -> str:
    return "Pontaria" if arma.get("alcance", "").strip() else "Luta"


def _bonus_registrado(texto: str) -> int:
    encontrado = re.search(r"([+-]\s*\d+)\s*$", texto.strip())
    return int(encontrado.group(1).replace(" ", "")) if encontrado else 0


def _tipo_acao_registrado(texto: str) -> str:
    valor = normalizar_rotulo(texto)
    if "completa" in valor:
        return "completa"
    if "movimento" in valor:
        return "movimento"
    if valor == "livre" or valor == "acao livre":
        return "livre"
    if valor in {"reacao", "imediata", "imediato"}:
        return "nenhuma"
    return "padrao"


def _embed_habilidade_criatura(item: dict[str, str]) -> discord.Embed:
    embed = discord.Embed(
        title=item.get("nome", "Habilidade"),
        description=item.get("descrição", item.get("descricao", "")) or None,
        color=COR_COMBATE,
    )
    efeito = item.get("efeito", "").strip()
    if efeito:
        embed.add_field(name="Efeito", value=efeito, inline=False)
    campos = (
        ("Ação", "tipo de ação"),
        ("Custo", "mecânica de custo"),
        ("Alcance", "alcance"),
        ("Alvo", "alvo"),
        ("Acerto", "rolagem de acerto"),
        ("Resistência", "rolagem de resistência"),
        ("Reação", "rolagem de reação"),
        ("CD", "CD mágica"),
        ("Recarga", "recarga"),
    )
    for rotulo, chave in campos:
        valor = item.get(chave, "").strip()
        if valor:
            embed.add_field(name=rotulo, value=valor, inline=True)
    return embed


class ViewUsuario(discord.ui.View):
    def __init__(self, usuario_id: int, *, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.usuario_id = usuario_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message(
            "Somente quem abriu este painel pode usar os controles.",
            ephemeral=True,
        )
        return False

    def adicionar_finalizar(self, disponivel: bool) -> None:
        if not disponivel:
            return
        finalizar = discord.ui.Button(
            label="Finalizar",
            style=discord.ButtonStyle.success,
            row=4,
        )
        finalizar.callback = self.finalizar
        self.add_item(finalizar)

    async def finalizar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await interaction.delete_original_response()


ORIGEM_CRIATURAS = "Criaturas"


def _referencias_da_origem(
    origem: str,
    periculosidade: str = "",
) -> list[ReferenciaCombatente]:
    referencias = listar_referencias_combate()
    if origem == ORIGEM_CRIATURAS:
        return [
            item
            for item in referencias
            if item.tipo == "criatura"
            and (
                not periculosidade
                or item.grupo == f"Criatura {periculosidade}"
            )
        ]
    return [
        item
        for item in referencias
        if item.tipo == "personagem" and item.grupo == origem
    ]


class SelecionarOrigemCombateView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        equipe: str,
        pode_finalizar: bool = False,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.equipe = equipe
        self.pode_finalizar = pode_finalizar
        origens = ORDEM_PASTAS_FICHA
        contagens = {
            origem: len(_referencias_da_origem(origem))
            for origem in origens
        }
        seletor = discord.ui.Select(
            placeholder="Escolha a pasta da ficha",
            options=[
                discord.SelectOption(
                    label=origem,
                    value=origem,
                    emoji=EMOJIS_PASTAS_FICHA[origem],
                    description=(
                        f"{contagens[origem]} ficha(s) disponível(is)."
                        if contagens[origem]
                        else "Pasta reservada; ainda não possui fichas."
                    ),
                )
                for origem in origens
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        self.adicionar_finalizar(pode_finalizar)
        voltar = discord.ui.Button(
            label="Voltar", style=discord.ButtonStyle.secondary, row=4
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await interaction.delete_original_response()

    async def selecionar(self, interaction: discord.Interaction) -> None:
        origem = self.seletor.values[0]
        if origem == ORIGEM_CRIATURAS:
            await interaction.response.edit_message(
                content=None,
                embed=embed_painel_combate(
                    f"Adicionar aos {self.equipe} — Criaturas",
                    "Escolha a pasta de periculosidade.",
                ),
                view=SelecionarPericulosidadeCombateView(
                    self.cog,
                    self.usuario_id,
                    self.combate_id,
                    self.equipe,
                    self.pode_finalizar,
                ),
            )
            return
        paginas = paginas_fichas_alfabeticas(_referencias_da_origem(origem))
        primeira = next(
            (indice for indice, (_, itens) in enumerate(paginas) if itens),
            0,
        )
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"Adicionar aos {self.equipe} — {origem}",
                "Escolha a faixa alfabética e depois a ficha.",
            ),
            view=SelecionarFaixaCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.equipe,
                origem,
                primeira,
                pode_finalizar=self.pode_finalizar,
            ),
        )


class SelecionarPericulosidadeCombateView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        equipe: str,
        pode_finalizar: bool = False,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.equipe = equipe
        self.pode_finalizar = pode_finalizar
        contagens = {
            perigo: len(_referencias_da_origem(ORIGEM_CRIATURAS, perigo))
            for perigo in PERICULOSIDADES
        }
        seletor = discord.ui.Select(
            placeholder="Escolha a periculosidade",
            options=[
                discord.SelectOption(
                    label=perigo,
                    value=perigo,
                    description=(
                        f"{contagens[perigo]} ficha(s) disponível(is)."
                        if contagens[perigo]
                        else "Pasta reservada; ainda não possui fichas."
                    ),
                )
                for perigo in PERICULOSIDADES
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        self.adicionar_finalizar(pode_finalizar)
        voltar = discord.ui.Button(
            label="Voltar",
            style=discord.ButtonStyle.secondary,
            row=4,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        perigo = self.seletor.values[0]
        paginas = paginas_fichas_alfabeticas(
            _referencias_da_origem(ORIGEM_CRIATURAS, perigo)
        )
        primeira = next(
            (indice for indice, (_, itens) in enumerate(paginas) if itens),
            0,
        )
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"Adicionar aos {self.equipe} — Criaturas {perigo}",
                "Escolha a faixa alfabética e depois a ficha.",
            ),
            view=SelecionarFaixaCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.equipe,
                ORIGEM_CRIATURAS,
                primeira,
                periculosidade=perigo,
                pode_finalizar=self.pode_finalizar,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"Adicionar aos {self.equipe}",
                "Escolha a pasta de origem da ficha.",
            ),
            view=SelecionarOrigemCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.equipe,
                self.pode_finalizar,
            )
        )


class SelecionarFaixaCombateView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        equipe: str,
        origem: str,
        pagina: int,
        *,
        periculosidade: str = "",
        pode_finalizar: bool = False,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.equipe = equipe
        self.origem = origem
        self.periculosidade = periculosidade
        self.pode_finalizar = pode_finalizar
        self.paginas = paginas_fichas_alfabeticas(
            _referencias_da_origem(origem, periculosidade)
        )
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        rotulo, referencias = self.paginas[self.pagina]
        self.referencias = referencias

        faixas = discord.ui.Select(
            placeholder=f"Faixa alfabética — {rotulo}",
            options=[
                discord.SelectOption(
                    label=rotulo_pagina,
                    value=str(indice),
                    description=(
                        f"{len(itens)} ficha(s) nesta faixa."
                        if itens
                        else "Faixa reservada para fichas futuras."
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

        if referencias:
            fichas = discord.ui.Select(
                placeholder=f"Fichas — {rotulo}",
                options=[
                    discord.SelectOption(
                        label=referencia.nome[:100],
                        value=str(indice),
                    )
                    for indice, referencia in enumerate(referencias)
                ],
                row=1,
            )
            fichas.callback = self.selecionar_ficha
            self.fichas = fichas
            self.add_item(fichas)

        self.adicionar_finalizar(pode_finalizar)

        voltar = discord.ui.Button(
            label="Voltar",
            style=discord.ButtonStyle.secondary,
            row=4,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    def _nova(self, pagina: int) -> "SelecionarFaixaCombateView":
        return SelecionarFaixaCombateView(
            self.cog,
            self.usuario_id,
            self.combate_id,
            self.equipe,
            self.origem,
            pagina,
            periculosidade=self.periculosidade,
            pode_finalizar=self.pode_finalizar,
        )

    async def selecionar_faixa(self, interaction: discord.Interaction) -> None:
        pagina = int(self.faixas.values[0])
        rotulo, itens = self.paginas[pagina]
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"Adicionar aos {self.equipe} — {self.origem} — {rotulo}",
                (
                    "Escolha uma ficha nesta faixa."
                    if itens
                    else "Esta faixa ainda não possui fichas. Escolha outra faixa."
                ),
            ),
            view=self._nova(pagina),
        )

    async def selecionar_ficha(self, interaction: discord.Interaction) -> None:
        referencia = self.referencias[int(self.fichas.values[0])]
        try:
            combate, participante = await self.cog.adicionar_ficha(
                self.combate_id,
                referencia,
                self.equipe,
            )
            await self.cog.atualizar_mensagem(combate)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{participante.nome} adicionado",
                f"A ficha entrou nos **{self.equipe}**. Você pode adicionar outra "
                "ficha desta faixa ou voltar às pastas.",
            ),
            view=SelecionarFaixaCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.equipe,
                self.origem,
                self.pagina,
                periculosidade=self.periculosidade,
                pode_finalizar=True,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        if self.origem == ORIGEM_CRIATURAS:
            await interaction.response.edit_message(
                content=None,
                embed=embed_painel_combate(
                    f"Adicionar aos {self.equipe} — Criaturas",
                    "Escolha a pasta de periculosidade.",
                ),
                view=SelecionarPericulosidadeCombateView(
                    self.cog,
                    self.usuario_id,
                    self.combate_id,
                    self.equipe,
                    self.pode_finalizar,
                ),
            )
            return
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"Adicionar aos {self.equipe}",
                "Escolha a pasta de origem da ficha.",
            ),
            view=SelecionarOrigemCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.equipe,
                self.pode_finalizar,
            ),
        )


class AjustarRecursosModal(discord.ui.Modal):
    def __init__(
        self,
        cog: "CombateCog",
        combate_id: str,
        participante: ParticipanteCombate,
    ):
        super().__init__(title=f"Recursos — {participante.nome[:30]}")
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante.identificador
        self.pv = discord.ui.TextInput(
            label=f"{participante.recurso_vida} atual (máximo {participante.pv_maximo})",
            default=str(participante.pv_atual),
            max_length=8,
        )
        self.ph = discord.ui.TextInput(
            label=f"PH atual (máximo {participante.ph_maximo})",
            default=str(participante.ph_atual),
            max_length=8,
        )
        self.estado = discord.ui.TextInput(
            label="Estado: ativo, incapacitado ou morto",
            default=participante.estado,
            max_length=12,
        )
        self.add_item(self.pv)
        self.add_item(self.ph)
        self.add_item(self.estado)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            pv = int(str(self.pv))
            ph = int(str(self.ph))
            estado = str(self.estado).strip().casefold()
            combate = await self.cog.mutar(
                self.combate_id,
                lambda item: alterar_recursos(
                    item.participante(self.participante_id),
                    pv=pv,
                    ph=ph,
                    estado=estado,
                ),
            )
            await self.cog.atualizar_mensagem(combate)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        participante = combate.participante(self.participante_id)
        await interaction.response.send_message(
            f"**{participante.nome}** agora está com "
            f"`{participante.pv_atual}/{participante.pv_maximo} {participante.recurso_vida}` e "
            f"`{participante.ph_atual}/{participante.ph_maximo} PH` — **{participante.estado}**.",
            ephemeral=True,
        )


class SelecionarParticipanteView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate: Combate,
        finalidade: str,
        pagina: int = 0,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate.identificador
        self.finalidade = finalidade
        self.paginas = [
            combate.participantes[indice : indice + 25]
            for indice in range(0, len(combate.participantes), 25)
        ] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        atual = self.paginas[self.pagina]
        if atual:
            seletor = discord.ui.Select(
                placeholder=f"Escolha o participante — {self.pagina + 1}/{len(self.paginas)}",
                options=[
                    discord.SelectOption(
                        label=item.nome[:100],
                        value=item.identificador,
                        description=(
                            f"{item.equipe} • {item.pv_atual}/{item.pv_maximo} {item.recurso_vida} • "
                            f"{item.ph_atual}/{item.ph_maximo} PH"
                        )[:100],
                    )
                    for item in atual
                ],
            )
            seletor.callback = self.selecionar
            self.seletor = seletor
            self.add_item(seletor)
        if len(self.paginas) > 1:
            anterior = discord.ui.Button(
                label="Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == 0,
                row=1,
            )
            anterior.callback = self.anterior
            self.add_item(anterior)
            proxima = discord.ui.Button(
                label="Próxima",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == len(self.paginas) - 1,
                row=1,
            )
            proxima.callback = self.proxima
            self.add_item(proxima)
        voltar = discord.ui.Button(
            label="Voltar", style=discord.ButtonStyle.secondary, row=4
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction: discord.Interaction) -> None:
        if self.finalidade == "recursos":
            combate, _ = self.cog.localizar(self.combate_id)
            await interaction.response.edit_message(
                content=None,
                embed=embed_painel_combate(
                    f"{EMOJI_COMBATE} Controle de Combate",
                    "Ferramentas exclusivas da moderação para administrar a cena.",
                ),
                view=ControleCombateView(self.cog, self.usuario_id, combate),
            )
            return
        await interaction.response.defer()
        await interaction.delete_original_response()

    async def selecionar(self, interaction: discord.Interaction) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.seletor.values[0])
        if self.finalidade == "recursos":
            await interaction.response.send_modal(
                AjustarRecursosModal(self.cog, self.combate_id, participante)
            )
            return
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"Rolagem de {participante.nome}",
                "Escolha o teste que deseja realizar.",
            ),
            view=SelecionarTesteView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                participante.identificador,
            ),
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        await interaction.response.edit_message(
            view=SelecionarParticipanteView(
                self.cog, self.usuario_id, combate, self.finalidade, self.pagina - 1
            )
        )

    async def proxima(self, interaction: discord.Interaction) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        await interaction.response.edit_message(
            view=SelecionarParticipanteView(
                self.cog, self.usuario_id, combate, self.finalidade, self.pagina + 1
            )
        )


class SelecionarTesteView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        participante_id: str,
        pagina: int = 0,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        combate, _ = cog.localizar(combate_id)
        participante = combate.participante(participante_id)
        self.testes = valores_rolaveis(participante)
        self.paginas = [
            self.testes[indice : indice + 25]
            for indice in range(0, len(self.testes), 25)
        ] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        atual = self.paginas[self.pagina]
        seletor = discord.ui.Select(
            placeholder=f"Teste — página {self.pagina + 1}/{len(self.paginas)}",
            options=[
                discord.SelectOption(
                    label=nome[:100],
                    value=str(indice),
                    description=f"{categoria} • bônus {bonus:+d}"[:100],
                )
                for indice, (nome, bonus, categoria) in enumerate(atual)
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        if len(self.paginas) > 1:
            anterior = discord.ui.Button(
                label="Anterior", style=discord.ButtonStyle.secondary,
                disabled=self.pagina == 0, row=1,
            )
            anterior.callback = self.anterior
            self.add_item(anterior)
            proxima = discord.ui.Button(
                label="Próxima", style=discord.ButtonStyle.secondary,
                disabled=self.pagina == len(self.paginas) - 1, row=1,
            )
            proxima.callback = self.proxima
            self.add_item(proxima)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        nome, bonus, _ = self.paginas[self.pagina][int(self.seletor.values[0])]
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"Rolagem — {nome} {bonus:+d}",
                "Escolha como deseja realizar a rolagem.",
            ),
            view=ModoRolagemView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
                nome,
                bonus,
            ),
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=SelecionarTesteView(
                self.cog, self.usuario_id, self.combate_id,
                self.participante_id, self.pagina - 1,
            )
        )

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=SelecionarTesteView(
                self.cog, self.usuario_id, self.combate_id,
                self.participante_id, self.pagina + 1,
            )
        )


class RolagemExternaCombateModal(discord.ui.Modal):
    def __init__(
        self,
        cog: "CombateCog",
        combate_id: str,
        participante_id: str,
        teste: str,
        bonus: int,
    ):
        super().__init__(title=f"Rolagem externa — {teste[:25]}")
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.teste = teste
        self.bonus = bonus
        self.total = discord.ui.TextInput(label="Resultado total", max_length=8)
        self.add_item(self.total)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            total = int(str(self.total))
            combate, _ = self.cog.localizar(self.combate_id)
            participante = combate.participante(self.participante_id)
            await self.cog.registrar_rolagem(
                combate,
                participante,
                self.teste,
                self.bonus,
                total,
                dado=None,
            )
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.send_message("Rolagem externa registrada.", ephemeral=True)


class ModoRolagemView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        participante_id: str,
        teste: str,
        bonus: int,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.teste = teste
        self.bonus = bonus

    @discord.ui.button(label="Rolar no Grimory", style=discord.ButtonStyle.primary)
    async def interna(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        dado = random.randint(1, 20)
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        await self.cog.registrar_rolagem(
            combate,
            participante,
            self.teste,
            self.bonus,
            dado + self.bonus,
            dado=dado,
        )
        await interaction.response.edit_message(content="Rolagem realizada.", view=None)

    @discord.ui.button(label="Rolagem externa", style=discord.ButtonStyle.secondary)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            RolagemExternaCombateModal(
                self.cog,
                self.combate_id,
                self.participante_id,
                self.teste,
                self.bonus,
            )
        )


class AcoesCombateView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate: Combate,
        participante: ParticipanteCombate,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate.identificador
        self.participante_id = participante.identificador
        if not participante.acao_padrao_usada:
            habilidade = discord.ui.Button(
                label="Usar habilidade",
                emoji=EMOJI_HABILIDADE,
                style=discord.ButtonStyle.primary,
                row=0,
            )
            habilidade.callback = self.habilidade
            self.add_item(habilidade)
            sem_habilidade = discord.ui.Button(
                label="Não usar habilidade",
                style=discord.ButtonStyle.secondary,
                row=0,
            )
            sem_habilidade.callback = self.ataque
            self.add_item(sem_habilidade)
            if _pocoes_participante(participante):
                pocao = discord.ui.Button(
                    label="Usar poção",
                    emoji=EMOJI_POCAO,
                    style=discord.ButtonStyle.secondary,
                    row=1,
                )
                pocao.callback = self.pocao
                self.add_item(pocao)
        encerrar = discord.ui.Button(
            label="Encerrar turno",
            style=discord.ButtonStyle.danger,
            row=4,
        )
        encerrar.callback = self.encerrar_turno
        self.add_item(encerrar)
        voltar = discord.ui.Button(
            label="Voltar",
            style=discord.ButtonStyle.secondary,
            row=4,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    def participante(self) -> ParticipanteCombate:
        combate, _ = self.cog.localizar(self.combate_id)
        return combate.participante(self.participante_id)

    async def ataque(self, interaction: discord.Interaction) -> None:
        participante = self.participante()
        view = TipoAtaqueView(
            self.cog,
            self.usuario_id,
            self.combate_id,
            self.participante_id,
        )
        tem_ataque = any(
            isinstance(item, discord.ui.Button) and item.label in {"Feitiço", "Arma"}
            for item in view.children
        )
        descricao = (
            "Você optou por não usar uma habilidade. Escolha o tipo de ataque."
            if tem_ataque
            else (
                "A Ação Padrão já foi consumida neste turno; não é possível "
                "realizar outro ataque."
                if participante.acao_padrao_usada
                else "Esta ficha não possui feitiços ou armas disponíveis para atacar."
            )
        )
        await interaction.response.edit_message(
            content=None,
            embed=embed_acoes_turno(participante, descricao),
            view=view,
        )

    async def habilidade(self, interaction: discord.Interaction) -> None:
        participante = self.participante()
        if participante.tipo_ficha == "criatura":
            await interaction.response.edit_message(
                content=None,
                embed=embed_painel_combate(
                    f"{EMOJI_HABILIDADE} Habilidades de {participante.nome}",
                    "Escolha uma habilidade registrada na ficha.",
                    participante=participante,
                ),
                view=HabilidadesCriaturaCombateView(
                    self.cog,
                    self.usuario_id,
                    self.combate_id,
                    participante.identificador,
                ),
            )
            return
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_HABILIDADE} Habilidades de {participante.nome}",
                "Escolha a origem da habilidade que deseja ativar.",
                participante=participante,
            ),
            view=CategoriaHabilidadeCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                participante.identificador,
            ),
        )

    async def pocao(self, interaction: discord.Interaction) -> None:
        participante = self.participante()
        pocoes = _pocoes_participante(participante)
        if not pocoes:
            await interaction.response.send_message(
                "Esta ficha não possui frascos de poção no inventário.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_POCAO} Poções de {participante.nome}",
                "Escolha uma poção existente no inventário. O uso consumirá um frasco e a Ação Padrão.",
                participante=participante,
            ),
            view=SelecionarPocaoCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                participante.identificador,
                pocoes,
            ),
        )

    async def encerrar_turno(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            combate, _ = self.cog.localizar(self.combate_id)
            atual = combate.participante_atual()
            if atual is None or atual.identificador != self.participante_id:
                raise ValueError("Este turno já foi encerrado.")
            combate = await self.cog.mutar(combate.identificador, avancar_turno)
            await self.cog.atualizar_mensagem(combate)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.followup.send(str(erro), ephemeral=True)
            return
        await interaction.delete_original_response()

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await interaction.delete_original_response()


async def _retornar_ao_turno(
    interaction: discord.Interaction,
    cog: "CombateCog",
    usuario_id: int,
    combate_id: str,
    participante_id: str,
    descricao: str,
) -> None:
    combate, _ = cog.localizar(combate_id)
    participante = combate.participante(participante_id)
    await interaction.response.edit_message(
        content=None,
        embed=embed_acoes_turno(participante, descricao),
        view=AcoesCombateView(cog, usuario_id, combate, participante),
    )


class AcaoNarrativaModal(discord.ui.Modal):
    def __init__(
        self,
        cog: "CombateCog",
        combate_id: str,
        participante_id: str,
        tipo: str,
    ):
        super().__init__(title="Ação de movimento" if tipo == "movimento" else "Ação livre")
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.tipo = tipo
        self.descricao = discord.ui.TextInput(
            label=(
                "Deslocamento ou preparação"
                if tipo == "movimento"
                else "Descreva a ação livre"
            ),
            style=discord.TextStyle.paragraph,
            max_length=700,
        )
        self.add_item(self.descricao)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        descricao = str(self.descricao).strip()
        try:
            combate = await self.cog.mutar(
                self.combate_id,
                lambda atual: registrar_acao_narrativa(
                    atual,
                    self.participante_id,
                    self.tipo,
                    descricao,
                ),
            )
            await self.cog.atualizar_mensagem(combate)
            participante = combate.participante(self.participante_id)
            await self.cog.publicar_descricao_acao(
                combate,
                participante,
                "Movimento" if self.tipo == "movimento" else "Ação livre",
                descricao,
            )
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.send_message("Ação registrada.", ephemeral=True)


class TipoAtaqueView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        participante_id: str,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        combate, _ = cog.localizar(combate_id)
        participante = combate.participante(participante_id)
        ficha = _ficha_participante(participante)
        if not participante.acao_padrao_usada and isinstance(ficha, FichaPersonagem) and any(
            valor != 0 for valor in ficha.aptidoes.values()
        ):
            feitico = discord.ui.Button(
                label="Feitiço", emoji=EMOJI_FEITICO, style=discord.ButtonStyle.primary
            )
            feitico.callback = self.feitico
            self.add_item(feitico)
        if not participante.acao_padrao_usada and _armas_participante(participante):
            arma = discord.ui.Button(
                label="Arma", emoji=EMOJI_ARMA, style=discord.ButtonStyle.danger
            )
            arma.callback = self.arma
            self.add_item(arma)
        voltar = discord.ui.Button(
            label="Voltar", style=discord.ButtonStyle.secondary, row=4
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def feitico(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_FEITICO} Feitiço",
                "Escolha a categoria do feitiço.",
            ),
            view=CategoriaFeiticoCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
            ),
        )

    async def arma(self, interaction: discord.Interaction) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        armas = _armas_participante(participante)
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_ARMA} Arma de {participante.nome}",
                "Escolha uma arma registrada na ficha.",
            ),
            view=SelecionarArmaCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                participante.identificador,
                armas,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        await interaction.response.edit_message(
            content=None,
            embed=embed_acoes_turno(participante),
            view=AcoesCombateView(
                self.cog, self.usuario_id, combate, participante
            ),
        )


class CategoriaFeiticoCombateView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        participante_id: str,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.itens = carregar_todos_feiticos()
        categorias: dict[str, str] = {}
        for item in self.itens:
            categoria = campos_normalizados(item.entrada).get("categoria", "").strip()
            if categoria:
                categorias.setdefault(normalizar_rotulo(categoria), categoria)
        seletor = discord.ui.Select(
            placeholder="Categoria de feitiços",
            options=[
                discord.SelectOption(
                    label=nome[:100],
                    value=chave,
                    description=f"{sum(1 for item in self.itens if normalizar_rotulo(campos_normalizados(item.entrada).get('categoria', '')) == chave)} feitiço(s)",
                )
                for chave, nome in sorted(categorias.items(), key=lambda par: par[1].casefold())
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        categoria = self.seletor.values[0]
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_FEITICO} Ano de desbloqueio",
                "Escolha o ano em que o feitiço é desbloqueado.",
            ),
            view=AnoFeiticoCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
                categoria,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        await interaction.response.edit_message(
            content=None,
            embed=embed_acoes_turno(participante, "Escolha o tipo de ataque."),
            view=TipoAtaqueView(
                self.cog, self.usuario_id, self.combate_id, self.participante_id
            ),
        )


class AnoFeiticoCombateView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        participante_id: str,
        categoria: str,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.categoria = categoria
        self.itens = [
            item
            for item in carregar_todos_feiticos()
            if normalizar_rotulo(campos_normalizados(item.entrada).get("categoria", ""))
            == categoria
        ]
        anos = {
            normalizar_ano(campos_normalizados(item.entrada).get("ano de desbloqueio", ""))
            for item in self.itens
        }

        def chave_ano(valor: str) -> tuple[int, str]:
            numero = re.match(r"([1-7])º Ano$", valor)
            return (int(numero.group(1)), valor.casefold()) if numero else (99, valor.casefold())

        seletor = discord.ui.Select(
            placeholder="Ano de desbloqueio",
            options=[
                discord.SelectOption(
                    label=ano[:100],
                    value=ano,
                    description=f"{sum(1 for item in self.itens if normalizar_ano(campos_normalizados(item.entrada).get('ano de desbloqueio', '')) == ano)} feitiço(s)",
                )
                for ano in sorted(anos, key=chave_ano)
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        ano = self.seletor.values[0]
        itens = sorted(
            (
                item
                for item in self.itens
                if normalizar_ano(campos_normalizados(item.entrada).get("ano de desbloqueio", ""))
                == ano
            ),
            key=lambda item: normalizar_rotulo(item.nome),
        )
        await interaction.response.defer()
        indice_oficial = criar_grupos_indice(
            campos_normalizados(itens[0].entrada).get("categoria", self.categoria)
        )
        links_por_nome: dict[str, str] = {}
        if indice_oficial is not None:
            titulo, grupos, _ = indice_oficial
            links = await localizar_links_oficiais(self.cog.bot, titulo, grupos)
            for (_, nome), url in links.items():
                links_por_nome.setdefault(nome, url)
        view = SelecionarFeiticoCombateView(
            self.cog,
            self.usuario_id,
            self.combate_id,
            self.participante_id,
            self.categoria,
            ano,
            itens,
            links_por_nome,
            0,
        )
        await interaction.edit_original_response(
            content=None,
            embeds=[view.embed_indice()],
            view=view,
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_FEITICO} Feitiço",
                "Escolha a categoria do feitiço.",
            ),
            view=CategoriaFeiticoCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
            )
        )


class SelecionarFeiticoCombateView(ViewUsuario):
    def __init__(self, cog, usuario_id, combate_id, participante_id, categoria, ano, itens, links, pagina=0):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.categoria = categoria
        self.ano = ano
        self.todos_itens = list(itens)
        self.links = dict(links)
        self.paginas = [self.todos_itens[i:i + 25] for i in range(0, len(self.todos_itens), 25)] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        self.itens = self.paginas[self.pagina]
        seletor = discord.ui.Select(
            placeholder=f"Escolha o feitiço — {self.pagina + 1}/{len(self.paginas)}",
            options=[
                discord.SelectOption(
                    label=item.nome[:100],
                    value=str(indice),
                    description=campos_normalizados(item.entrada).get("grau de dificuldade", "")[:100] or None,
                )
                for indice, item in enumerate(self.itens)
            ],
            row=0,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        if len(self.paginas) > 1:
            anterior = discord.ui.Button(label="Anterior", style=discord.ButtonStyle.secondary, disabled=self.pagina == 0, row=1)
            anterior.callback = self.anterior
            self.add_item(anterior)
            proxima = discord.ui.Button(label="Próxima", style=discord.ButtonStyle.secondary, disabled=self.pagina == len(self.paginas) - 1, row=1)
            proxima.callback = self.proxima
            self.add_item(proxima)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    def embed_indice(self) -> discord.Embed:
        categoria_visivel = campos_normalizados(self.todos_itens[0].entrada).get("categoria", self.categoria)
        grupo = GrupoIndice(self.ano, self.itens)
        links = {
            (normalizar_rotulo(self.ano), normalizar_rotulo(item.nome)): self.links[normalizar_rotulo(item.nome)]
            for item in self.itens
            if normalizar_rotulo(item.nome) in self.links
        }
        cor = CORES_FEITICOS.get(normalizar_rotulo(categoria_visivel), COR_EMBED_FEITICO)
        embed = criar_embeds_indice(categoria_visivel, [grupo], cor, links)[0]
        embed.insert_field_at(
            0,
            name="Escolha do feitiço",
            value=(
                "Clique em um nome para abrir a mensagem oficial ou use o seletor "
                "abaixo para escolher o feitiço."
            ),
            inline=False,
        )
        if len(self.paginas) > 1:
            embed.set_footer(text=f"Página {self.pagina + 1} de {len(self.paginas)}")
        return embed

    def nova(self, pagina: int) -> "SelecionarFeiticoCombateView":
        return SelecionarFeiticoCombateView(
            self.cog, self.usuario_id, self.combate_id, self.participante_id,
            self.categoria, self.ano, self.todos_itens, self.links, pagina,
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        view = self.nova(self.pagina - 1)
        await interaction.response.edit_message(embeds=[view.embed_indice()], view=view)

    async def proxima(self, interaction: discord.Interaction) -> None:
        view = self.nova(self.pagina + 1)
        await interaction.response.edit_message(embeds=[view.embed_indice()], view=view)

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_FEITICO} Ano de desbloqueio",
                "Escolha o ano em que o feitiço é desbloqueado.",
            ),
            view=AnoFeiticoCombateView(
                self.cog, self.usuario_id, self.combate_id, self.participante_id, self.categoria
            ),
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        item = self.itens[int(self.seletor.values[0])]
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        ficha = _ficha_participante(participante)
        assert isinstance(ficha, FichaPersonagem)
        try:
            cd, rotulo_ano = _cd_feitico_por_ficha(item, ficha)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        categoria = campos_normalizados(item.entrada).get("categoria", "")
        aptidao = _categoria_aptidao(categoria)
        bonus = ficha.aptidoes.get(aptidao, 0)
        embeds = criar_embeds_entrada(item.entrada, "feitico", item.nome)
        embeds[0].add_field(
            name="Execução no combate",
            value=(
                f"Aptidão: **{aptidao} {bonus:+d}**\n"
                f"Dificuldade para {rotulo_ano}: **CD {cd}**\n"
                f"{EMOJI_ESQUIVA} Esquiva: **{'permitida' if _feitico_eh_lampejo(item) else 'não permitida'}**"
            ),
            inline=False,
        )
        await interaction.response.edit_message(
            content=None,
            embeds=embeds[:10],
            view=ExecutarAtaqueView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
                tipo="feitico",
                nome=item.nome,
                bonus=bonus,
                cd=cd,
                lampejo=_feitico_eh_lampejo(item),
                dano=_dano_feitico(item),
                tipo_acao=_tipo_acao_registrado(
                    str((getattr(item.entrada, "perfil_combate", None) or {}).get("tipo_acao", "Padrão"))
                ),
                voltar_feiticos=(self.categoria, self.ano, self.todos_itens, self.links, self.pagina),
            ),
        )


class SelecionarArmaCombateView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        participante_id: str,
        armas: list[dict[str, str]],
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.armas = armas[:25]
        seletor = discord.ui.Select(
            placeholder="Escolha a arma",
            options=[
                discord.SelectOption(
                    label=arma.get("nome", "Arma")[:100],
                    value=str(indice),
                    description=(
                        f"{arma.get('categoria', '--')} • {arma.get('dano', '--')}"
                    )[:100],
                )
                for indice, arma in enumerate(self.armas)
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar", style=discord.ButtonStyle.secondary, row=4
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction: discord.Interaction) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        await interaction.response.edit_message(
            content=None,
            embed=embed_acoes_turno(participante, "Escolha o tipo de ataque."),
            view=TipoAtaqueView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
            ),
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        arma = self.armas[int(self.seletor.values[0])]
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        ficha = _ficha_participante(participante)
        pericia = _tipo_ataque_arma(arma)
        bonus = _bonus_pericia_ficha(ficha, pericia)
        await interaction.response.edit_message(
            content=None,
            embed=_embed_arma(participante, arma),
            view=ExecutarAtaqueView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
                tipo="arma",
                nome=arma.get("nome", "Arma"),
                bonus=bonus,
                dano=arma.get("dano", ""),
            ),
        )


class SelecionarPocaoCombateView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        participante_id: str,
        pocoes: list[dict[str, str]],
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.pocoes = pocoes[:25]
        seletor = discord.ui.Select(
            placeholder="Escolha a poção",
            options=[
                discord.SelectOption(
                    label=pocao.get("nome", "Poção")[:100],
                    value=str(indice),
                    description=f"{inteiro_positivo(pocao.get('quantidade', '0'), 0)} frasco(s) disponível(is).",
                )
                for indice, pocao in enumerate(self.pocoes)
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        pocao = self.pocoes[int(self.seletor.values[0])]
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        await interaction.response.edit_message(
            content=None,
            embed=_embed_pocao(participante, pocao),
            view=SelecionarAlvoPocaoCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
                pocao,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        await interaction.response.edit_message(
            content=None,
            embed=embed_acoes_turno(participante),
            view=AcoesCombateView(self.cog, self.usuario_id, combate, participante),
        )


class SelecionarAlvoPocaoCombateView(ViewUsuario):
    def __init__(self, cog, usuario_id, combate_id, participante_id, pocao):
        super().__init__(usuario_id)
        self.cog, self.combate_id = cog, combate_id
        self.participante_id, self.pocao = participante_id, pocao
        combate, _ = cog.localizar(combate_id)
        self.alvos = [item for item in combate.participantes if item.vivo][:25]
        seletor = discord.ui.Select(
            placeholder="Escolha quem receberá a poção",
            options=[
                discord.SelectOption(
                    label=alvo.nome[:100],
                    value=str(indice),
                    description=f"{alvo.equipe} • {alvo.pv_atual}/{alvo.pv_maximo} {alvo.recurso_vida}",
                )
                for indice, alvo in enumerate(self.alvos)
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar às poções", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        alvo = self.alvos[int(self.seletor.values[0])]
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        await interaction.response.edit_message(
            content=None,
            embed=_embed_pocao(participante, self.pocao, alvo=alvo),
            view=ConfirmarUsoPocaoCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
                alvo.identificador,
                self.pocao,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        participante = self.cog.localizar(self.combate_id)[0].participante(self.participante_id)
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_POCAO} Poções de {participante.nome}",
                "Escolha uma poção existente no inventário.",
                participante=participante,
            ),
            view=SelecionarPocaoCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
                _pocoes_participante(participante),
            ),
        )


class ConfirmarUsoPocaoCombateView(ViewUsuario):
    def __init__(self, cog, usuario_id, combate_id, participante_id, alvo_id, pocao):
        super().__init__(usuario_id)
        self.cog, self.combate_id = cog, combate_id
        self.participante_id, self.alvo_id, self.pocao = participante_id, alvo_id, pocao
        confirmar = discord.ui.Button(
            label="Usar 1 frasco",
            emoji=EMOJI_POCAO,
            style=discord.ButtonStyle.success,
        )
        confirmar.callback = self.confirmar
        self.add_item(confirmar)
        voltar = discord.ui.Button(label="Voltar aos alvos", style=discord.ButtonStyle.secondary)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def confirmar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            combate, ficha, restante = await self.cog.usar_pocao_inventario(
                self.combate_id,
                self.participante_id,
                self.alvo_id,
                self.pocao.get("nome", "Poção"),
            )
            await self.cog.atualizar_mensagem(combate)
            participante = combate.participante(self.participante_id)
            alvo = combate.participante(self.alvo_id)
            descricao, efeito, consumo = _dados_pocao(self.pocao.get("nome", "Poção"))
            embed = discord.Embed(
                title=f"{EMOJI_POCAO} {participante.nome} usou {self.pocao.get('nome', 'Poção')}",
                description=descricao or None,
                color=0x66F060,
            )
            embed.add_field(name="Alvo", value=alvo.nome, inline=True)
            embed.add_field(name="Frascos restantes", value=str(restante), inline=True)
            embed.add_field(name="Efeito oficial", value=efeito[:1024], inline=False)
            if consumo:
                embed.add_field(name="Forma de uso", value=consumo[:1024], inline=False)
            await self.cog.publicar_atualizacao(combate, embed)
            await sincronizar_publicacao_personagem(
                interaction,
                ficha,
                Path(participante.caminho_ficha),
            )
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.edit_original_response(
                embed=embed_painel_combate(f"{EMOJI_POCAO} Poção", str(erro)),
                view=None,
            )
            return
        await interaction.edit_original_response(
            embed=embed_acoes_turno(
                participante,
                f"Poção utilizada em **{alvo.nome}**. O efeito oficial foi publicado para aplicação na mesa.",
            ),
            view=AcoesCombateView(self.cog, self.usuario_id, combate, participante),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        await interaction.response.edit_message(
            content=None,
            embed=_embed_pocao(participante, self.pocao),
            view=SelecionarAlvoPocaoCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
                self.pocao,
            ),
        )


class ExecutarAtaqueView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        participante_id: str,
        *,
        tipo: str,
        nome: str,
        bonus: int,
        cd: int = 0,
        lampejo: bool = False,
        dano: str = "",
        tipo_acao: str = "padrao",
        custo_ph: int = 0,
        recarga: str = "",
        voltar_feiticos=None,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.tipo = tipo
        self.nome = nome
        self.bonus = bonus
        self.cd = cd
        self.lampejo = lampejo
        self.dano = dano
        self.tipo_acao = tipo_acao
        self.custo_ph = custo_ph
        self.recarga = recarga
        self.voltar_feiticos = voltar_feiticos
        if voltar_feiticos is not None:
            voltar = discord.ui.Button(
                label="Voltar", style=discord.ButtonStyle.secondary, row=4
            )
            voltar.callback = self.voltar_para_indice
            self.add_item(voltar)
        else:
            voltar = discord.ui.Button(
                label="Voltar", style=discord.ButtonStyle.secondary, row=4
            )
            voltar.callback = self.voltar_para_tipo
            self.add_item(voltar)

    async def voltar_para_tipo(self, interaction: discord.Interaction) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        await interaction.response.edit_message(
            content=None,
            embed=embed_acoes_turno(participante, "Escolha o tipo de ataque."),
            view=TipoAtaqueView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
            ),
        )

    async def voltar_para_indice(self, interaction: discord.Interaction) -> None:
        categoria, ano, itens, links, pagina = self.voltar_feiticos
        view = SelecionarFeiticoCombateView(
            self.cog,
            self.usuario_id,
            self.combate_id,
            self.participante_id,
            categoria,
            ano,
            itens,
            links,
            pagina,
        )
        await interaction.response.edit_message(
            content=None,
            embeds=[view.embed_indice()],
            view=view,
        )

    def proxima(self, externo: bool) -> "SelecionarAlvoAtaqueView":
        return SelecionarAlvoAtaqueView(
            self.cog,
            self.usuario_id,
            self.combate_id,
            self.participante_id,
            tipo=self.tipo,
            nome=self.nome,
            bonus=self.bonus,
            cd=self.cd,
            lampejo=self.lampejo,
            dano=self.dano,
            tipo_acao=self.tipo_acao,
            custo_ph=self.custo_ph,
            recarga=self.recarga,
            voltar_feiticos=self.voltar_feiticos,
            externo=externo,
        )

    @discord.ui.button(label="Executar", style=discord.ButtonStyle.danger)
    async def executar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            view = self.proxima(False)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_ATAQUE} Escolha do alvo",
                "Selecione um participante vivo da equipe adversária.",
            ),
            view=view,
        )

    @discord.ui.button(label="Rolagem externa", style=discord.ButtonStyle.secondary)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            view = self.proxima(True)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_ATAQUE} Escolha do alvo",
                "Selecione um participante vivo da equipe adversária.",
            ),
            view=view,
        )


class SelecionarAlvoAtaqueView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        participante_id: str,
        *,
        tipo: str,
        nome: str,
        bonus: int,
        cd: int,
        lampejo: bool,
        dano: str,
        externo: bool,
        tipo_acao: str = "padrao",
        custo_ph: int = 0,
        recarga: str = "",
        voltar_feiticos=None,
        pagina: int = 0,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.tipo = tipo
        self.nome = nome
        self.bonus = bonus
        self.cd = cd
        self.lampejo = lampejo
        self.dano = dano
        self.externo = externo
        self.tipo_acao = tipo_acao
        self.custo_ph = custo_ph
        self.recarga = recarga
        self.voltar_feiticos = voltar_feiticos
        combate, _ = cog.localizar(combate_id)
        atacante = combate.participante(participante_id)
        alvos = [
            item
            for item in combate.participantes
            if item.vivo and item.equipe != atacante.equipe
        ]
        if not alvos:
            raise ValueError("Não há adversários vivos disponíveis como alvo.")
        self.paginas = [alvos[i : i + 25] for i in range(0, len(alvos), 25)] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        self.alvos = self.paginas[self.pagina]
        seletor = discord.ui.Select(
            placeholder=f"Alvo — página {self.pagina + 1}/{len(self.paginas)}",
            options=[
                discord.SelectOption(
                    label=item.nome[:100],
                    value=item.identificador,
                    description=f"{item.equipe} • {item.pv_atual}/{item.pv_maximo} {item.recurso_vida}"[:100],
                )
                for item in self.alvos
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        if len(self.paginas) > 1:
            anterior = discord.ui.Button(
                label="Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == 0,
                row=1,
            )
            anterior.callback = self.anterior
            self.add_item(anterior)
            proxima = discord.ui.Button(
                label="Próxima",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == len(self.paginas) - 1,
                row=1,
            )
            proxima.callback = self.proxima
            self.add_item(proxima)
        if voltar_feiticos is not None:
            voltar = discord.ui.Button(
                label="Voltar", style=discord.ButtonStyle.secondary, row=4
            )
            voltar.callback = self.voltar_para_indice
            self.add_item(voltar)
        else:
            voltar = discord.ui.Button(
                label="Voltar", style=discord.ButtonStyle.secondary, row=4
            )
            voltar.callback = self.voltar_para_tipo
            self.add_item(voltar)

    async def voltar_para_tipo(self, interaction: discord.Interaction) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        await interaction.response.edit_message(
            content=None,
            embed=embed_acoes_turno(participante, "Escolha o tipo de ataque."),
            view=TipoAtaqueView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
            ),
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        alvo_id = self.seletor.values[0]
        if self.externo:
            await interaction.response.send_modal(
                AtaqueExternoModal(
                    self.cog,
                    self.combate_id,
                    self.participante_id,
                    alvo_id,
                    tipo=self.tipo,
                    nome=self.nome,
                    bonus=self.bonus,
                    cd=self.cd,
                    lampejo=self.lampejo,
                    dano=self.dano,
                    tipo_acao=self.tipo_acao,
                    custo_ph=self.custo_ph,
                    recarga=self.recarga,
                )
            )
            return
        await interaction.response.defer()
        dado = random.randint(1, 20)
        try:
            combate, embed, view_resolucao = await self.cog.resolver_ataque(
                self.combate_id,
                self.participante_id,
                alvo_id,
                tipo=self.tipo,
                nome=self.nome,
                bonus=self.bonus,
                total=dado + self.bonus,
                dado=dado,
                cd=self.cd,
                lampejo=self.lampejo,
                dano=self.dano,
                tipo_acao=self.tipo_acao,
                custo_ph=self.custo_ph,
                recarga=self.recarga,
                painel_privado=interaction.message,
                painel_usuario_id=self.usuario_id,
            )
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.followup.send(str(erro), ephemeral=True)
            return
        participante = combate.participante(self.participante_id)
        embed.add_field(
            name="Ações disponíveis",
            value=_texto_acoes(participante),
            inline=False,
        )
        await interaction.edit_original_response(
            content=None,
            embed=embed,
            view=view_resolucao or AcoesCombateView(
                self.cog, self.usuario_id, combate, participante
            ),
        )

    def _nova(self, pagina: int) -> "SelecionarAlvoAtaqueView":
        return SelecionarAlvoAtaqueView(
            self.cog,
            self.usuario_id,
            self.combate_id,
            self.participante_id,
            tipo=self.tipo,
            nome=self.nome,
            bonus=self.bonus,
            cd=self.cd,
            lampejo=self.lampejo,
            dano=self.dano,
            externo=self.externo,
            tipo_acao=self.tipo_acao,
            custo_ph=self.custo_ph,
            recarga=self.recarga,
            voltar_feiticos=self.voltar_feiticos,
            pagina=pagina,
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=self._nova(self.pagina - 1))

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=self._nova(self.pagina + 1))

    async def voltar_para_indice(self, interaction: discord.Interaction) -> None:
        categoria, ano, itens, links, pagina = self.voltar_feiticos
        view = SelecionarFeiticoCombateView(
            self.cog,
            self.usuario_id,
            self.combate_id,
            self.participante_id,
            categoria,
            ano,
            itens,
            links,
            pagina,
        )
        await interaction.response.edit_message(
            content=None,
            embeds=[view.embed_indice()],
            view=view,
        )


class AtaqueExternoModal(discord.ui.Modal):
    def __init__(
        self,
        cog: "CombateCog",
        combate_id: str,
        participante_id: str,
        alvo_id: str,
        **dados,
    ):
        super().__init__(title=f"Rolagem externa — {dados['nome'][:25]}")
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.alvo_id = alvo_id
        self.dados = dados
        self.total = discord.ui.TextInput(label="Resultado total do ataque", max_length=8)
        self.add_item(self.total)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            total = int(str(self.total))
            combate, embed, view_resolucao = await self.cog.resolver_ataque(
                self.combate_id,
                self.participante_id,
                self.alvo_id,
                total=total,
                dado=None,
                painel_privado=interaction.message,
                painel_usuario_id=interaction.user.id,
                **self.dados,
            )
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.followup.send(str(erro), ephemeral=True)
            return
        participante = combate.participante(self.participante_id)
        embed.add_field(
            name="Ações disponíveis",
            value=_texto_acoes(participante),
            inline=False,
        )
        await interaction.edit_original_response(
            content=None,
            embed=embed,
            view=view_resolucao or AcoesCombateView(
                self.cog, interaction.user.id, combate, participante
            ),
        )


class ReacaoAtaqueView(discord.ui.View):
    def __init__(
        self,
        cog: "CombateCog",
        combate_id: str,
        alvo_id: str,
        ataque_total: int,
        *,
        tipo: str,
        lampejo: bool,
        atacante_id: str = "",
        nome_ataque: str = "",
        dano: str = "",
        painel_privado: discord.Message | None = None,
        painel_usuario_id: int = 0,
        publico: bool = True,
    ):
        super().__init__(timeout=600)
        self.cog = cog
        self.combate_id = combate_id
        self.alvo_id = alvo_id
        self.ataque_total = ataque_total
        self.tipo = tipo
        self.lampejo = lampejo
        self.atacante_id = atacante_id
        self.nome_ataque = nome_ataque
        self.dano = extrair_expressao_dano(dano)
        self.painel_privado = painel_privado
        self.painel_usuario_id = painel_usuario_id
        self.publico = publico
        if tipo == "arma":
            self._adicionar_reacao("Defesa", "Fortitude", EMOJI_DEFESA)
            self._adicionar_reacao("Esquiva", "Reflexo", EMOJI_ESQUIVA)
        else:
            ataque = _encontrar_feitico_combate(self.nome_ataque)
            perfil_ataque = (
                getattr(ataque.entrada, "perfil_combate", None) if ataque else None
            ) or {}
            respostas = set(perfil_ataque.get("respostas", []))
            if lampejo:
                self._adicionar_reacao("Esquiva", "Reflexo", EMOJI_ESQUIVA)
            for pericia in ("Vontade", "Fortitude", "Reflexo"):
                if pericia in respostas and not (pericia == "Reflexo" and lampejo):
                    self._adicionar_reacao(
                        f"Resistência — {pericia}", pericia, EMOJI_DEFESA
                    )
        combate, _ = self.cog.localizar(self.combate_id)
        alvo = combate.participante(self.alvo_id)
        ficha_alvo = _ficha_participante(alvo)
        reacoes_magicas = (
            _reacoes_magicas_disponiveis(
                ficha_alvo,
                self.nome_ataque,
                lampejo=self.lampejo,
            )
            if isinstance(ficha_alvo, FichaPersonagem)
            else []
        )
        if tipo == "feitico" and reacoes_magicas:
            contra = discord.ui.Button(
                label="Contra-feitiço",
                style=discord.ButtonStyle.primary,
            )
            contra.callback = self.contra_feitico
            self.add_item(contra)
        ignorar = discord.ui.Button(label="Não reagir", style=discord.ButtonStyle.secondary)
        ignorar.callback = self.nao_reagir
        self.add_item(ignorar)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        combate, _ = self.cog.localizar(self.combate_id)
        alvo = combate.participante(self.alvo_id)
        membro = interaction.user
        moderador = interaction.user.id == combate.moderador_id or (
            isinstance(membro, discord.Member) and membro.guild_permissions.manage_guild
        )
        if moderador or (alvo.usuario_id and alvo.usuario_id == interaction.user.id):
            return True
        await interaction.response.send_message(
            "Somente o alvo ou o mestre pode escolher esta reação.", ephemeral=True
        )
        return False

    def _adicionar_reacao(self, label: str, pericia: str, emoji: str) -> None:
        botao = discord.ui.Button(
            label=label, emoji=emoji, style=discord.ButtonStyle.primary
        )

        async def callback(interaction: discord.Interaction) -> None:
            retorno_embed = (
                interaction.message.embeds[0]
                if interaction.message.embeds
                else discord.Embed(color=COR_COMBATE)
            )
            await interaction.response.edit_message(
                content=None,
                embed=embed_painel_combate(
                    f"{emoji} {label}",
                    f"Escolha como realizar **{label}**.",
                ),
                view=ModoReacaoView(
                    self.cog,
                    interaction.user.id,
                    self.combate_id,
                    self.alvo_id,
                    self.ataque_total,
                    label,
                    pericia,
                    interaction.message.id,
                    self.atacante_id,
                    self.nome_ataque,
                    self.dano,
                    self.painel_privado,
                    self.painel_usuario_id,
                    retorno_embed,
                    self,
                    self.publico,
                ),
            )

        botao.callback = callback
        self.add_item(botao)

    async def contra_feitico(self, interaction: discord.Interaction) -> None:
        retorno_embed = (
            interaction.message.embeds[0]
            if interaction.message.embeds
            else discord.Embed(color=COR_COMBATE)
        )
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_DEFESA} Reação a {self.nome_ataque}",
                "Escolha uma reação imediata compatível, disponível para o ano e "
                "as aptidões mágicas desta ficha.",
            ),
            view=ContraFeiticoCombateView(
                self.cog,
                interaction.user.id,
                self.combate_id,
                self.alvo_id,
                interaction.message.id,
                self.atacante_id,
                self.nome_ataque,
                self.dano,
                self.lampejo,
                self.painel_privado,
                self.painel_usuario_id,
                retorno_embed,
                self,
                self.publico,
            ),
        )

    async def nao_reagir(self, interaction: discord.Interaction) -> None:
        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.add_field(name="Resolução", value="O alvo não reagiu; o ataque o atingiu.", inline=False)
        view = self._dano_view(interaction.message.id)
        await interaction.response.edit_message(embed=embed, view=view)
        if self.publico:
            await self.cog.atualizar_painel_acao(
                self.combate_id,
                self.atacante_id,
                self.painel_usuario_id,
                self.painel_privado,
                embed,
            )
        elif view is None:
            await self.cog.atualizar_painel_acao(
                self.combate_id,
                self.atacante_id,
                self.painel_usuario_id,
                interaction.message,
                embed,
            )
        if self.publico and view is None:
            await self.cog.remover_atualizacao_acao(
                self.combate_id, interaction.message
            )

    def _dano_view(self, mensagem_id: int) -> discord.ui.View | None:
        if not self.dano or not self.atacante_id:
            return None
        return DanoAtaqueView(
            self.cog,
            self.combate_id,
            self.atacante_id,
            self.alvo_id,
            self.nome_ataque,
            self.dano,
            mensagem_id,
            self.painel_privado,
            self.painel_usuario_id,
            self.publico,
        )


class ModoReacaoView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        alvo_id: str,
        ataque_total: int,
        nome: str,
        pericia: str,
        mensagem_ataque_id: int,
        atacante_id: str = "",
        nome_ataque: str = "",
        dano: str = "",
        painel_privado: discord.Message | None = None,
        painel_usuario_id: int = 0,
        retorno_embed: discord.Embed | None = None,
        retorno_view: discord.ui.View | None = None,
        publico: bool = True,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.alvo_id = alvo_id
        self.ataque_total = ataque_total
        self.nome = nome
        self.pericia = pericia
        self.mensagem_ataque_id = mensagem_ataque_id
        self.atacante_id = atacante_id
        self.nome_ataque = nome_ataque
        self.dano = dano
        self.painel_privado = painel_privado
        self.painel_usuario_id = painel_usuario_id
        self.retorno_embed = retorno_embed
        self.retorno_view = retorno_view
        self.publico = publico

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
    async def voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=self.retorno_embed,
            view=self.retorno_view,
        )

    @discord.ui.button(label="Rolar no Grimory", style=discord.ButtonStyle.primary)
    async def interna(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        combate, _ = self.cog.localizar(self.combate_id)
        alvo = combate.participante(self.alvo_id)
        ficha = _ficha_participante(alvo)
        bonus = _bonus_pericia_ficha(ficha, self.pericia)
        dado = random.randint(1, 20)
        await self.cog.publicar_resultado_reacao(
            combate,
            self.mensagem_ataque_id,
            alvo,
            self.nome,
            dado + bonus,
            self.ataque_total,
            detalhe=f"d20 {dado} + {bonus:+d}",
            atacante_id=self.atacante_id,
            nome_ataque=self.nome_ataque,
            dano=self.dano,
            painel_privado=self.painel_privado,
            painel_usuario_id=self.painel_usuario_id,
            mensagem_direta=None if self.publico else interaction.message,
            embed_base=self.retorno_embed,
            publico=self.publico,
        )

    @discord.ui.button(label="Rolagem externa", style=discord.ButtonStyle.secondary)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            ReacaoExternaModal(
                self.cog,
                self.combate_id,
                self.alvo_id,
                self.ataque_total,
                self.nome,
                self.mensagem_ataque_id,
                self.atacante_id,
                self.nome_ataque,
                self.dano,
                self.painel_privado,
                self.painel_usuario_id,
                self.retorno_embed,
                self.retorno_view,
                self.publico,
            )
        )


class ReacaoExternaModal(discord.ui.Modal):
    def __init__(
        self,
        cog: "CombateCog",
        combate_id: str,
        alvo_id: str,
        ataque_total: int,
        nome: str,
        mensagem_ataque_id: int,
        atacante_id: str = "",
        nome_ataque: str = "",
        dano: str = "",
        painel_privado: discord.Message | None = None,
        painel_usuario_id: int = 0,
        retorno_embed: discord.Embed | None = None,
        retorno_view: discord.ui.View | None = None,
        publico: bool = True,
    ):
        super().__init__(title=f"Rolagem externa — {nome}")
        self.cog = cog
        self.combate_id = combate_id
        self.alvo_id = alvo_id
        self.ataque_total = ataque_total
        self.nome = nome
        self.mensagem_ataque_id = mensagem_ataque_id
        self.atacante_id = atacante_id
        self.nome_ataque = nome_ataque
        self.dano = dano
        self.painel_privado = painel_privado
        self.painel_usuario_id = painel_usuario_id
        self.retorno_embed = retorno_embed
        self.retorno_view = retorno_view
        self.publico = publico
        self.total = discord.ui.TextInput(label="Resultado total", max_length=8)
        self.add_item(self.total)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            total = int(str(self.total))
            combate, _ = self.cog.localizar(self.combate_id)
            alvo = combate.participante(self.alvo_id)
            await self.cog.publicar_resultado_reacao(
                combate,
                self.mensagem_ataque_id,
                alvo,
                self.nome,
                total,
                self.ataque_total,
                detalhe="rolagem externa",
                atacante_id=self.atacante_id,
                nome_ataque=self.nome_ataque,
                dano=self.dano,
                painel_privado=self.painel_privado,
                painel_usuario_id=self.painel_usuario_id,
                mensagem_direta=None if self.publico else interaction.message,
                embed_base=self.retorno_embed,
                publico=self.publico,
            )
        except (ValueError, discord.HTTPException) as erro:
            await interaction.followup.send(str(erro), ephemeral=True)
            return


class ContraFeiticoCombateView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate_id: str,
        alvo_id: str,
        mensagem_ataque_id: int,
        atacante_id: str = "",
        nome_ataque: str = "",
        dano: str = "",
        lampejo: bool = False,
        painel_privado: discord.Message | None = None,
        painel_usuario_id: int = 0,
        retorno_embed: discord.Embed | None = None,
        retorno_view: discord.ui.View | None = None,
        publico: bool = True,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.alvo_id = alvo_id
        self.mensagem_ataque_id = mensagem_ataque_id
        self.atacante_id = atacante_id
        self.nome_ataque = nome_ataque
        self.dano = dano
        self.painel_privado = painel_privado
        self.painel_usuario_id = painel_usuario_id
        self.retorno_embed = retorno_embed
        self.retorno_view = retorno_view
        self.publico = publico
        combate, _ = cog.localizar(combate_id)
        alvo = combate.participante(alvo_id)
        ficha = _ficha_participante(alvo)
        itens = (
            _reacoes_magicas_disponiveis(
                ficha,
                nome_ataque,
                lampejo=lampejo,
            )
            if isinstance(ficha, FichaPersonagem)
            else []
        )
        self.itens = itens[:25]
        seletor = discord.ui.Select(
            placeholder="Escolha o contra-feitiço",
            options=[
                discord.SelectOption(label=item.nome[:100], value=str(indice))
                for indice, item in enumerate(self.itens)
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar", style=discord.ButtonStyle.secondary, row=4
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=self.retorno_embed,
            view=self.retorno_view,
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        item = self.itens[int(self.seletor.values[0])]
        combate, _ = self.cog.localizar(self.combate_id)
        alvo = combate.participante(self.alvo_id)
        ficha = _ficha_participante(alvo)
        if not isinstance(ficha, FichaPersonagem):
            await interaction.response.send_message(
                "A ficha não possui uma tabela de dificuldade por ano para contra-feitiços.",
                ephemeral=True,
            )
            return
        try:
            cd, _ = _cd_feitico_por_ficha(item, ficha)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        ajuste_reacao = _ajuste_cd_reacao(item)
        cd += ajuste_reacao
        campos = campos_normalizados(item.entrada)
        aptidao = _categoria_aptidao(campos.get("categoria", ""))
        bonus = ficha.aptidoes.get(aptidao, 0)
        embeds = criar_embeds_entrada(item.entrada, "feitico", item.nome)
        embeds[0].add_field(
            name="Execução como reação",
            value=(
                f"Resposta a: **{self.nome_ataque}**\n"
                f"Aptidão: **{aptidao} {bonus:+d}**\n"
                f"Dificuldade: **CD {cd}**"
                + (f" *(inclui +{ajuste_reacao} pela reação)*" if ajuste_reacao else "")
            ),
            inline=False,
        )
        await interaction.response.edit_message(
            content=None,
            embeds=embeds[:10],
            view=ExecutarContraFeiticoView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                alvo.identificador,
                self.mensagem_ataque_id,
                item.nome,
                cd,
                bonus,
                self.atacante_id,
                self.nome_ataque,
                self.dano,
                self.painel_privado,
                self.painel_usuario_id,
                self.publico,
                self.retorno_embed,
            ),
        )


class ExecutarContraFeiticoView(ViewUsuario):
    def __init__(self, cog, usuario_id, combate_id, alvo_id, mensagem_id, nome, cd, bonus, atacante_id="", nome_ataque="", dano="", painel_privado=None, painel_usuario_id=0, publico=True, embed_base=None):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.alvo_id = alvo_id
        self.mensagem_id = mensagem_id
        self.nome = nome
        self.cd = cd
        self.bonus = bonus
        self.atacante_id = atacante_id
        self.nome_ataque = nome_ataque
        self.dano = dano
        self.painel_privado = painel_privado
        self.painel_usuario_id = painel_usuario_id
        self.publico = publico
        self.embed_base = embed_base

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
    async def voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        await interaction.delete_original_response()

    @discord.ui.button(label="Executar", style=discord.ButtonStyle.primary)
    async def executar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        dado = random.randint(1, 20)
        total = dado + self.bonus
        await self.cog.publicar_contra_feitico(
            self.combate_id,
            self.mensagem_id,
            self.alvo_id,
            self.nome,
            total,
            self.cd,
            f"d20 {dado} + {self.bonus:+d}",
            self.atacante_id,
            self.nome_ataque,
            self.dano,
            self.painel_privado,
            self.painel_usuario_id,
            None if self.publico else interaction.message,
            self.embed_base,
            self.publico,
        )

    @discord.ui.button(label="Rolagem externa", style=discord.ButtonStyle.secondary)
    async def externa(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            ContraFeiticoExternoModal(
                self.cog,
                self.combate_id,
                self.alvo_id,
                self.mensagem_id,
                self.nome,
                self.cd,
                self.atacante_id,
                self.nome_ataque,
                self.dano,
                self.painel_privado,
                self.painel_usuario_id,
                self.publico,
                self.embed_base,
            )
        )


class ContraFeiticoExternoModal(discord.ui.Modal):
    def __init__(self, cog, combate_id, alvo_id, mensagem_id, nome, cd, atacante_id="", nome_ataque="", dano="", painel_privado=None, painel_usuario_id=0, publico=True, embed_base=None):
        super().__init__(title=f"Rolagem externa — {nome[:25]}")
        self.cog = cog
        self.combate_id = combate_id
        self.alvo_id = alvo_id
        self.mensagem_id = mensagem_id
        self.nome = nome
        self.cd = cd
        self.atacante_id = atacante_id
        self.nome_ataque = nome_ataque
        self.dano = dano
        self.painel_privado = painel_privado
        self.painel_usuario_id = painel_usuario_id
        self.publico = publico
        self.embed_base = embed_base
        self.total = discord.ui.TextInput(label="Resultado total", max_length=8)
        self.add_item(self.total)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            total = int(str(self.total))
            await self.cog.publicar_contra_feitico(
                self.combate_id,
                self.mensagem_id,
                self.alvo_id,
                self.nome,
                total,
                self.cd,
                "rolagem externa",
                self.atacante_id,
                self.nome_ataque,
                self.dano,
                self.painel_privado,
                self.painel_usuario_id,
                None if self.publico else interaction.message,
                self.embed_base,
                self.publico,
            )
        except (ValueError, discord.HTTPException) as erro:
            await interaction.followup.send(str(erro), ephemeral=True)
            return


class DanoAtaqueView(discord.ui.View):
    def __init__(self, cog, combate_id, atacante_id, alvo_id, nome, expressao, mensagem_id, painel_privado=None, painel_usuario_id=0, publico=True):
        super().__init__(timeout=600)
        self.cog = cog
        self.combate_id = combate_id
        self.atacante_id = atacante_id
        self.alvo_id = alvo_id
        self.nome = nome
        self.expressao = expressao
        self.mensagem_id = mensagem_id
        self.painel_privado = painel_privado
        self.painel_usuario_id = painel_usuario_id
        self.publico = publico

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        combate, _ = self.cog.localizar(self.combate_id)
        atacante = combate.participante(self.atacante_id)
        membro = interaction.user
        moderador = interaction.user.id == combate.moderador_id or (
            isinstance(membro, discord.Member) and membro.guild_permissions.manage_guild
        )
        if moderador or (atacante.usuario_id and atacante.usuario_id == interaction.user.id):
            return True
        await interaction.response.send_message(
            "Somente o atacante ou o mestre pode resolver este dano.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Rolar dano", style=discord.ButtonStyle.danger)
    async def interno(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        try:
            total, dados, modificador = rolar_expressao_dano(self.expressao)
            await self.cog.resolver_dano(
                self.combate_id,
                self.atacante_id,
                self.alvo_id,
                self.nome,
                self.expressao,
                total,
                self.mensagem_id,
                detalhe=(
                    f"dados {dados}"
                    + (f" {modificador:+d}" if modificador else "")
                ),
                painel_privado=self.painel_privado,
                painel_usuario_id=self.painel_usuario_id,
                mensagem_direta=None if self.publico else interaction.message,
                publico=self.publico,
            )
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.followup.send(str(erro), ephemeral=True)
            return

    @discord.ui.button(label="Dano externo", style=discord.ButtonStyle.secondary)
    async def externo(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            DanoExternoModal(
                self.cog,
                self.combate_id,
                self.atacante_id,
                self.alvo_id,
                self.nome,
                self.expressao,
                self.mensagem_id,
                self.painel_privado,
                self.painel_usuario_id,
                self.publico,
            )
        )


class DanoExternoModal(discord.ui.Modal):
    def __init__(self, cog, combate_id, atacante_id, alvo_id, nome, expressao, mensagem_id, painel_privado=None, painel_usuario_id=0, publico=True):
        super().__init__(title=f"Dano externo — {nome[:25]}")
        self.cog = cog
        self.combate_id = combate_id
        self.atacante_id = atacante_id
        self.alvo_id = alvo_id
        self.nome = nome
        self.expressao = expressao
        self.mensagem_id = mensagem_id
        self.painel_privado = painel_privado
        self.painel_usuario_id = painel_usuario_id
        self.publico = publico
        self.total = discord.ui.TextInput(label="Dano total", max_length=8)
        self.add_item(self.total)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            total = int(str(self.total))
            if total < 0:
                raise ValueError("O dano não pode ser negativo.")
            await self.cog.resolver_dano(
                self.combate_id,
                self.atacante_id,
                self.alvo_id,
                self.nome,
                self.expressao,
                total,
                self.mensagem_id,
                detalhe="rolagem externa",
                painel_privado=self.painel_privado,
                painel_usuario_id=self.painel_usuario_id,
                mensagem_direta=None if self.publico else interaction.message,
                publico=self.publico,
            )
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.followup.send(str(erro), ephemeral=True)
            return


class CategoriaHabilidadeCombateView(ViewUsuario):
    def __init__(self, cog, usuario_id, combate_id, participante_id):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        for label, chave in (
            ("Herança Sanguínea", "heranca_sanguinea"),
            ("Origem Mágica", "origem_magica"),
            ("Especialização", "especializacao"),
        ):
            botao = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary)

            async def callback(interaction: discord.Interaction, categoria=chave) -> None:
                await self.abrir(interaction, categoria)

            botao.callback = callback
            self.add_item(botao)
        voltar = discord.ui.Button(
            label="Voltar", style=discord.ButtonStyle.secondary, row=4
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction: discord.Interaction) -> None:
        await _retornar_ao_turno(
            interaction,
            self.cog,
            self.usuario_id,
            self.combate_id,
            self.participante_id,
            "Escolha se usará uma habilidade antes do ataque.",
        )

    async def abrir(self, interaction: discord.Interaction, categoria: str) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        ficha = _ficha_participante(participante)
        assert isinstance(ficha, FichaPersonagem)
        if categoria == "heranca_sanguinea":
            nomes = [ficha.heranca] if ficha.heranca and ficha.heranca != "--" else []
        elif categoria == "origem_magica":
            nomes = ficha.origens_magicas
        else:
            nomes = ficha.especializacoes
        if not nomes:
            await interaction.response.send_message(
                "A ficha não possui habilidades nesta categoria.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_HABILIDADE} Habilidade de {participante.nome}",
                "Escolha a habilidade registrada na ficha.",
                participante=participante,
            ),
            view=SelecionarFonteHabilidadeView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
                categoria,
                nomes,
            ),
        )


class SelecionarFonteHabilidadeView(ViewUsuario):
    def __init__(self, cog, usuario_id, combate_id, participante_id, categoria, nomes):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.categoria = categoria
        self.nomes = list(nomes)[:25]
        seletor = discord.ui.Select(
            placeholder="Escolha a habilidade",
            options=[discord.SelectOption(label=nome[:100], value=str(i)) for i, nome in enumerate(self.nomes)],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar", style=discord.ButtonStyle.secondary, row=4
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_HABILIDADE} Habilidades",
                "Escolha a origem da habilidade que deseja ativar.",
            ),
            view=CategoriaHabilidadeCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
            ),
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        nome = self.nomes[int(self.seletor.values[0])]
        combate, _ = self.cog.localizar(self.combate_id)
        participante = combate.participante(self.participante_id)
        ficha = _ficha_participante(participante)
        assert isinstance(ficha, FichaPersonagem)
        acoes = acoes_ph_habilidade(self.categoria, nome)
        if self.categoria == "heranca_sanguinea":
            acoes = [
                acao
                for acao in acoes
                if int(acao.get("evolucao", 0)) <= ficha.evolucao_heranca
            ]
        if self.categoria == "especializacao" and not acoes:
            entrada = carregar_habilidade(self.categoria, nome)
            if entrada is not None:
                acoes = [{"nome": nome, "custos": [0], "descricao": entrada.descricao}]
        if not acoes:
            await interaction.response.send_message(
                "Nenhum efeito ativável foi encontrado na biblioteca para esta habilidade.",
                ephemeral=True,
            )
            return
        opcoes: list[tuple[str, int, str]] = []
        for acao in acoes:
            custos = list(acao.get("custos", [])) or [0]
            for custo in custos:
                opcoes.append((str(acao["nome"]), int(custo), str(acao["descricao"])))
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_HABILIDADE} {nome}",
                "Escolha o efeito que deseja ativar.",
                participante=participante,
            ),
            view=SelecionarEfeitoHabilidadeView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
                nome,
                opcoes[:25],
            ),
        )


class SelecionarEfeitoHabilidadeView(ViewUsuario):
    def __init__(self, cog, usuario_id, combate_id, participante_id, fonte, opcoes):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.fonte = fonte
        self.opcoes = opcoes
        seletor = discord.ui.Select(
            placeholder="Escolha o efeito",
            options=[
                discord.SelectOption(
                    label=nome[:100],
                    value=str(i),
                    description=f"{custo}ph" if custo else "Ativação imediata",
                )
                for i, (nome, custo, _) in enumerate(opcoes)
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar", style=discord.ButtonStyle.secondary, row=4
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_HABILIDADE} Habilidades",
                "Escolha a origem da habilidade que deseja ativar.",
            ),
            view=CategoriaHabilidadeCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
            ),
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        nome, custo, descricao = self.opcoes[int(self.seletor.values[0])]
        embed = discord.Embed(
            title=f"{self.fonte} — {nome}",
            description=descricao,
            color=COR_COMBATE,
        )
        embed.add_field(name="Custo", value=f"{custo}ph" if custo else "Sem custo de PH")
        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=AtivarHabilidadeCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
                nome,
                descricao,
                custo,
            ),
        )


class AtivarHabilidadeCombateView(ViewUsuario):
    def __init__(self, cog, usuario_id, combate_id, participante_id, nome, descricao, custo):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        self.nome = nome
        self.descricao = descricao
        self.custo = custo
        voltar = discord.ui.Button(
            label="Voltar", style=discord.ButtonStyle.secondary, row=4
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_HABILIDADE} Habilidades",
                "Escolha a origem da habilidade que deseja ativar.",
            ),
            view=CategoriaHabilidadeCombateView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
            ),
        )

    @discord.ui.button(label="Ativar", style=discord.ButtonStyle.primary)
    async def ativar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            combate = await self.cog.mutar(
                self.combate_id,
                lambda atual: ativar_habilidade_combate(
                    atual,
                    self.participante_id,
                    self.nome,
                    self.descricao,
                    self.custo,
                ),
            )
            await self.cog.atualizar_mensagem(combate)
            participante = combate.participante(self.participante_id)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        pode_atacar = not participante.acao_padrao_usada
        view = (
            TipoAtaqueView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
            )
            if pode_atacar
            else AcoesCombateView(
                self.cog,
                self.usuario_id,
                combate,
                participante,
            )
        )
        await interaction.response.edit_message(
            content=None,
            embed=embed_acoes_turno(
                participante,
                "Habilidade ativada. Escolha o ataque."
                if pode_atacar
                else (
                    "Habilidade ativada. A Ação Padrão foi consumida; ataques "
                    "não estão mais disponíveis neste turno."
                ),
            ),
            view=view,
        )


class HabilidadesCriaturaCombateView(ViewUsuario):
    def __init__(self, cog, usuario_id, combate_id, participante_id):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        self.participante_id = participante_id
        combate, _ = cog.localizar(combate_id)
        ficha = _ficha_participante(combate.participante(participante_id))
        assert isinstance(ficha, FichaCriatura)
        self.habilidades = ficha.habilidades[:25]
        if self.habilidades:
            seletor = discord.ui.Select(
                placeholder="Habilidade da criatura",
                options=[
                    discord.SelectOption(
                        label=item.get("nome", "Habilidade")[:100], value=str(i)
                    )
                    for i, item in enumerate(self.habilidades)
                ],
            )
            seletor.callback = self.selecionar
            self.seletor = seletor
            self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar", style=discord.ButtonStyle.secondary, row=4
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction: discord.Interaction) -> None:
        await _retornar_ao_turno(
            interaction,
            self.cog,
            self.usuario_id,
            self.combate_id,
            self.participante_id,
            "Escolha se usará uma habilidade antes do ataque.",
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        item = self.habilidades[int(self.seletor.values[0])]
        nome = item.get("nome", "Habilidade")
        dano = item.get("efeito calculado", "") or item.get("efeito", "")
        acerto = item.get("rolagem de acerto", "")
        reacao = normalizar_rotulo(item.get("rolagem de reação", ""))
        tipo = "feitico" if reacao == "efeito magico direto" else "arma"
        cd = int(item.get("CD mágica", "0") or 0)
        custo = int(item.get("custo de PH", item.get("custo de Mana", "0")) or 0)
        await interaction.response.edit_message(
            content=None,
            embed=_embed_habilidade_criatura(item),
            view=ExecutarAtaqueView(
                self.cog,
                self.usuario_id,
                self.combate_id,
                self.participante_id,
                tipo=tipo,
                nome=nome,
                bonus=_bonus_registrado(acerto),
                cd=cd,
                lampejo="lampejo" in normalizar_rotulo(
                    item.get("efeito", "") + " " + item.get("descrição", "")
                ),
                dano=dano,
                tipo_acao=_tipo_acao_registrado(item.get("tipo de ação", "Padrão")),
                custo_ph=custo,
                recarga=item.get("recarga", ""),
            ),
        )


class DescansoView(ViewUsuario):
    def __init__(self, cog: "CombateCog", usuario_id: int, combate_id: str):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id
        seletor = discord.ui.Select(
            placeholder="Escolha o tempo de descanso",
            options=[
                discord.SelectOption(label=nome, value=chave, description=recuperacao)
                for chave, (nome, recuperacao) in DESCANSOS.items()
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar", style=discord.ButtonStyle.secondary, row=4
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction: discord.Interaction) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_COMBATE} Controle de Combate",
                "Ferramentas exclusivas da moderação para administrar a cena.",
            ),
            view=ControleCombateView(self.cog, self.usuario_id, combate),
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            anterior, novo = await self.cog.preparar_novo_combate(
                self.combate_id,
                self.seletor.values[0],
            )
            await self.cog.atualizar_mensagem(anterior)
            canal = interaction.channel
            if canal is None or not hasattr(canal, "send"):
                raise ValueError("Não foi possível publicar o novo combate neste canal.")
            mensagem = await canal.send(
                embed=embed_combate(novo),
                view=PainelCombateView(self.cog, novo),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            novo.canal_id = mensagem.channel.id
            novo.mensagem_id = mensagem.id
            salvar_combate(novo)
            await interaction.followup.send(
                "O combate anterior foi encerrado e a próxima cena está pronta. "
                "A recuperação de PH permanece inalterada até sua tabela ser definida.",
                ephemeral=True,
            )
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.followup.send(str(erro), ephemeral=True)


class ConfirmarEncerramentoView(ViewUsuario):
    def __init__(self, cog: "CombateCog", usuario_id: int, combate_id: str):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate_id

    @discord.ui.button(label="Confirmar encerramento", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            combate = await self.cog.mutar(self.combate_id, encerrar_combate)
            await self.cog.atualizar_mensagem(combate)
        except (OSError, ValueError, discord.HTTPException) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_COMBATE} Combate encerrado",
                "O relatório final foi publicado no painel do combate.",
            ),
            view=None,
        )

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
    async def cancelar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        combate, _ = self.cog.localizar(self.combate_id)
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_COMBATE} Controle de Combate",
                "Ferramentas exclusivas da moderação para administrar a cena.",
            ),
            view=ControleCombateView(self.cog, self.usuario_id, combate),
        )


class ControleCombateView(ViewUsuario):
    def __init__(
        self,
        cog: "CombateCog",
        usuario_id: int,
        combate: Combate,
    ):
        super().__init__(usuario_id)
        self.cog = cog
        self.combate_id = combate.identificador
        tem_participantes = bool(combate.participantes)
        self.recursos.disabled = not tem_participantes or combate.estado == "encerrado"
        self.novo.disabled = combate.estado == "preparacao"
        self.encerrar.disabled = combate.estado == "encerrado"
        voltar = discord.ui.Button(
            label="Voltar", style=discord.ButtonStyle.secondary, row=4
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    def carregar(self) -> Combate:
        return self.cog.localizar(self.combate_id)[0]

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await interaction.delete_original_response()

    @discord.ui.button(
        label="PV, PH e estado",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def recursos(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            combate = self.carregar()
            if not combate.participantes:
                raise ValueError("Ainda não há participantes no combate.")
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_COMBATE} Recursos e estado",
                "Escolha o participante que deseja atualizar.",
            ),
            view=SelecionarParticipanteView(
                self.cog, self.usuario_id, combate, "recursos"
            ),
        )

    @discord.ui.button(
        label="Novo combate",
        style=discord.ButtonStyle.success,
        row=0,
    )
    async def novo(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        combate = self.carregar()
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_COMBATE} Novo combate",
                "Escolha o descanso entre esta cena e o novo combate.\n"
                "Habilidades, itens e Primeiros Socorros ainda podem complementar a recuperação.",
            ),
            view=DescansoView(self.cog, self.usuario_id, combate.identificador),
        )

    @discord.ui.button(
        label="Encerrar combate",
        style=discord.ButtonStyle.danger,
        row=0,
    )
    async def encerrar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        combate = self.carregar()
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_COMBATE} Encerrar combate",
                "Deseja realmente encerrar este combate? O relatório final será publicado no painel.",
            ),
            view=ConfirmarEncerramentoView(
                self.cog, self.usuario_id, combate.identificador
            ),
        )


class PainelCombateView(discord.ui.View):
    def __init__(self, cog: "CombateCog", combate: Combate | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.combate_id = combate.identificador if combate is not None else ""
        estado = combate.estado if combate is not None else "ativo"
        tem_participantes = bool(combate and combate.participantes)
        self.iniciar.disabled = estado != "preparacao"
        self.acao.disabled = estado != "ativo"
        self.passar.disabled = estado != "ativo"
        self.controle.disabled = estado == "encerrado"

    def carregar(self, interaction: discord.Interaction) -> Combate:
        if self.combate_id:
            return self.cog.localizar(self.combate_id)[0]
        encontrado = encontrar_combate_por_mensagem(interaction.message.id)
        if encontrado is None:
            raise ValueError("Este painel de combate não possui mais um estado salvo.")
        return encontrado[0]

    def _eh_moderador(self, interaction: discord.Interaction, combate: Combate) -> bool:
        membro = interaction.user
        return interaction.user.id == combate.moderador_id or (
            isinstance(membro, discord.Member)
            and membro.guild_permissions.manage_guild
        )

    async def _exigir_moderador(
        self,
        interaction: discord.Interaction,
        combate: Combate,
    ) -> bool:
        if self._eh_moderador(interaction, combate):
            return True
        await interaction.response.send_message(
            "Você precisa da permissão **Gerenciar servidor** para conduzir este combate.",
            ephemeral=True,
        )
        return False

    async def _adicionar(self, interaction: discord.Interaction, equipe: str) -> None:
        try:
            combate = self.carregar(interaction)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        if not await self._exigir_moderador(interaction, combate):
            return
        referencias = listar_referencias_combate()
        if not referencias:
            await interaction.response.send_message(
                "Nenhuma ficha de personagem ou criatura foi encontrada.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            content=None,
            embed=embed_painel_combate(
                f"Adicionar aos {equipe}",
                "Escolha a pasta de origem da ficha.",
            ),
            view=SelecionarOrigemCombateView(
                self.cog, interaction.user.id, combate.identificador, equipe
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Novo aliado", style=discord.ButtonStyle.success,
        row=0, custom_id="combate:novo_aliado",
    )
    async def novo_aliado(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._adicionar(interaction, EQUIPE_ALIADOS)

    @discord.ui.button(
        label="Novo oponente", style=discord.ButtonStyle.danger,
        row=0, custom_id="combate:novo_oponente",
    )
    async def novo_oponente(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._adicionar(interaction, EQUIPE_OPONENTES)

    @discord.ui.button(
        label="Iniciar combate", style=discord.ButtonStyle.primary,
        row=0, custom_id="combate:iniciar",
    )
    async def iniciar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            atual = self.carregar(interaction)
            if not await self._exigir_moderador(interaction, atual):
                return
            combate = await self.cog.mutar(atual.identificador, iniciar_combate)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=embed_combate(combate), view=PainelCombateView(self.cog, combate)
        )

    @discord.ui.button(
        label="Ação", style=discord.ButtonStyle.primary,
        row=1, custom_id="combate:acao",
    )
    async def acao(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            combate = self.carregar(interaction)
            atual = combate.participante_atual()
            if atual is None:
                raise ValueError("Não há participante ativo neste turno.")
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        if not self._eh_moderador(interaction, combate):
            if not atual.usuario_id or atual.usuario_id != interaction.user.id:
                await interaction.response.send_message(
                    "Somente o titular desta ficha ou o mestre pode realizar sua ação.",
                    ephemeral=True,
                )
                return
        await interaction.response.send_message(
            content=None,
            embed=embed_acoes_turno(atual),
            view=AcoesCombateView(
                self.cog,
                interaction.user.id,
                combate,
                atual,
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Passar turno", style=discord.ButtonStyle.secondary,
        row=1, custom_id="combate:passar",
    )
    async def passar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            atual = self.carregar(interaction)
            if not await self._exigir_moderador(interaction, atual):
                return
            combate = await self.cog.mutar(atual.identificador, avancar_turno)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=embed_combate(combate), view=PainelCombateView(self.cog, combate)
        )

    @discord.ui.button(
        label="Controle de Combate",
        style=discord.ButtonStyle.secondary,
        row=1,
        custom_id="combate:controle",
    )
    async def controle(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            combate = self.carregar(interaction)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        if not await self._exigir_moderador(interaction, combate):
            return
        await interaction.response.send_message(
            content=None,
            embed=embed_painel_combate(
                f"{EMOJI_COMBATE} Controle de Combate",
                "Ferramentas exclusivas da moderação para administrar a cena.",
            ),
            view=ControleCombateView(
                self.cog, interaction.user.id, combate
            ),
            ephemeral=True,
        )


class CombateCog(commands.Cog, name="Combate"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bloqueio = asyncio.Lock()
        self.tarefa_restaurar: asyncio.Task | None = None

    async def cog_load(self) -> None:
        self.bot.add_view(PainelCombateView(self))
        self.tarefa_restaurar = asyncio.create_task(self._restaurar_paineis())

    async def cog_unload(self) -> None:
        if self.tarefa_restaurar is not None:
            self.tarefa_restaurar.cancel()

    async def _restaurar_paineis(self) -> None:
        await self.bot.wait_until_ready()
        if not PASTA_COMBATES.is_dir():
            return
        for caminho in PASTA_COMBATES.glob("*.md"):
            try:
                combate = carregar_combate(caminho)
                if combate.estado == "encerrado" or not combate.mensagem_id:
                    continue
                self.bot.add_view(
                    PainelCombateView(self, combate), message_id=combate.mensagem_id
                )
                await self.atualizar_mensagem(combate)
            except (OSError, ValueError, TypeError, discord.HTTPException):
                continue

    def localizar(self, combate_id: str) -> tuple[Combate, Path]:
        caminho = PASTA_COMBATES / f"{combate_id}.md"
        if not caminho.is_file():
            raise ValueError("O combate não foi encontrado.")
        return carregar_combate(caminho), caminho

    async def mutar(self, combate_id: str, acao) -> Combate:
        async with self.bloqueio:
            combate, caminho = self.localizar(combate_id)
            acao(combate)
            salvar_combate(combate, caminho)
            return combate

    async def usar_pocao_inventario(
        self,
        combate_id: str,
        participante_id: str,
        alvo_id: str,
        nome_pocao: str,
    ) -> tuple[Combate, FichaPersonagem, int]:
        """Consome a poção da ficha e registra seu uso no mesmo turno."""
        async with self.bloqueio:
            combate, caminho_combate = self.localizar(combate_id)
            participante = combate.participante(participante_id)
            alvo = combate.participante(alvo_id)
            atual = combate.participante_atual()
            if atual is None or atual.identificador != participante.identificador:
                raise ValueError("Este participante não é mais o personagem ativo do turno.")
            if participante.tipo_ficha != "personagem":
                raise ValueError("Somente fichas com inventário podem utilizar poções dessa forma.")
            registrar_acao_narrativa(
                combate,
                participante.identificador,
                "padrao",
                f"usou {nome_pocao} em {alvo.nome}.",
            )
            caminho_ficha = Path(participante.caminho_ficha).resolve()
            lock_ficha = LOCKS_FICHA.setdefault(caminho_ficha, asyncio.Lock())
            async with lock_ficha:
                ficha = FichaPersonagem.carregar(caminho_ficha)
                restante = consumir_item(ficha, "Poções", nome_pocao, 1)
                salvar_ficha(ficha, caminho_ficha)
            salvar_combate(combate, caminho_combate)
            return combate, ficha, restante

    async def adicionar_ficha(
        self,
        combate_id: str,
        referencia: ReferenciaCombatente,
        equipe: str,
    ) -> tuple[Combate, ParticipanteCombate]:
        participante: ParticipanteCombate | None = None

        def aplicar(combate: Combate) -> None:
            nonlocal participante
            participante = adicionar_participante(combate, referencia, equipe)

        combate = await self.mutar(combate_id, aplicar)
        assert participante is not None
        return combate, participante

    async def registrar_rolagem(
        self,
        combate: Combate,
        participante: ParticipanteCombate,
        teste: str,
        bonus: int,
        total: int,
        *,
        dado: int | None,
    ) -> None:
        def registrar(atual: Combate) -> None:
            alvo = atual.participante(participante.identificador)
            if dado == 20:
                alvo.criticos += 1
            atual.eventos.append(
                EventoCombate(
                    tipo="rolagem",
                    participante_id=alvo.identificador,
                    valor=total,
                    descricao=(
                        f"{alvo.nome} realizou {teste}: total {total} "
                        f"({'externa' if dado is None else f'd20 {dado} + {bonus:+d}'})."
                    ),
                )
            )

        atualizado = await self.mutar(combate.identificador, registrar)
        alvo = atualizado.participante(participante.identificador)
        await self.publicar_atualizacao(
            atualizado,
            embed_rolagem(alvo, teste, bonus, total, dado=dado),
        )

    async def _canal_combate(self, combate: Combate):
        canal = self.bot.get_channel(combate.canal_id)
        if canal is None:
            canal = await self.bot.fetch_channel(combate.canal_id)
        if not hasattr(canal, "send"):
            raise ValueError("O canal do combate não permite publicar ações.")
        return canal

    async def publicar_atualizacao(
        self,
        combate: Combate,
        embed: discord.Embed,
        view: discord.ui.View | None = None,
    ) -> discord.Message:
        """Mantém uma única mensagem pública para rolagens e ações do combate."""
        canal = await self._canal_combate(combate)
        if combate.mensagem_atualizacao_id and hasattr(canal, "fetch_message"):
            try:
                mensagem = await canal.fetch_message(combate.mensagem_atualizacao_id)
                await mensagem.edit(
                    content=None,
                    embed=embed,
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return mensagem
            except discord.NotFound:
                pass
        mensagem = await canal.send(
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )

        def registrar_mensagem(atual: Combate) -> None:
            atual.mensagem_atualizacao_id = mensagem.id

        await self.mutar(combate.identificador, registrar_mensagem)
        combate.mensagem_atualizacao_id = mensagem.id
        return mensagem

    async def publicar_descricao_acao(
        self,
        combate: Combate,
        participante: ParticipanteCombate,
        titulo: str,
        descricao: str,
    ) -> None:
        await self.publicar_atualizacao(
            combate,
            discord.Embed(
                title=f"{participante.nome} — {titulo}",
                description=descricao,
                color=COR_COMBATE,
            ),
        )

    async def atualizar_painel_acao(
        self,
        combate_id: str,
        atacante_id: str,
        usuario_id: int,
        painel: discord.Message | None,
        embed: discord.Embed,
    ) -> None:
        """Espelha a resolução na janela particular que iniciou a ação."""
        if painel is None or not atacante_id or not usuario_id:
            return
        combate, _ = self.localizar(combate_id)
        atacante = combate.participante(atacante_id)
        privado = embed.copy()
        for indice in range(len(privado.fields) - 1, -1, -1):
            if privado.fields[indice].name == "Ações disponíveis":
                privado.remove_field(indice)
        privado.add_field(
            name="Ações disponíveis",
            value=_texto_acoes(atacante),
            inline=False,
        )
        try:
            await painel.edit(
                content=None,
                embed=privado,
                view=AcoesCombateView(self, usuario_id, combate, atacante),
            )
        except discord.NotFound:
            pass

    async def remover_atualizacao_acao(
        self,
        combate_id: str,
        mensagem: discord.Message,
    ) -> None:
        """Remove o aviso público temporário assim que a reação termina."""
        mensagem_id = mensagem.id
        try:
            await mensagem.delete()
        except discord.NotFound:
            pass

        def limpar(atual: Combate) -> None:
            if atual.mensagem_atualizacao_id == mensagem_id:
                atual.mensagem_atualizacao_id = 0

        await self.mutar(combate_id, limpar)

    async def resolver_ataque(
        self,
        combate_id: str,
        atacante_id: str,
        alvo_id: str,
        *,
        tipo: str,
        nome: str,
        bonus: int,
        total: int,
        dado: int | None,
        cd: int = 0,
        lampejo: bool = False,
        dano: str = "",
        tipo_acao: str = "padrao",
        custo_ph: int = 0,
        recarga: str = "",
        painel_privado: discord.Message | None = None,
        painel_usuario_id: int = 0,
    ) -> tuple[Combate, discord.Embed, discord.ui.View | None]:
        def registrar(atual: Combate) -> None:
            atacante = atual.participante(atacante_id)
            alvo = atual.participante(alvo_id)
            registrar_ataque_combate(
                atual,
                atacante_id,
                f"{atacante.nome} atacou {alvo.nome} com {nome}; total {total}.",
                tipo_acao=tipo_acao,
                custo_ph=custo_ph,
                nome_recarga=nome if recarga else "",
                recarga=recarga,
            )
            if dado == 20:
                atacante.criticos += 1

        combate = await self.mutar(combate_id, registrar)
        await self.atualizar_mensagem(combate)
        atacante = combate.participante(atacante_id)
        alvo = combate.participante(alvo_id)
        detalhe = "Rolagem externa" if dado is None else f"d20 `{dado}` + bônus `{bonus:+d}`"
        embed = discord.Embed(
            title=f"{EMOJI_ATAQUE} {atacante.nome} ataca {alvo.nome}",
            description=f"**{nome}**\n{detalhe}\n## Total: `{total}`",
            color=COR_COMBATE,
        )
        if tipo == "feitico":
            sucesso = total >= cd
            embed.add_field(
                name="Conjuração",
                value=(
                    f"CD `{cd}` • **{'Sucesso' if sucesso else 'Falha'}**"
                ),
                inline=False,
            )
            if not sucesso:
                embed.set_footer(text="A conjuração falhou; o alvo não precisa reagir.")
        else:
            sucesso = True
            if dano:
                embed.add_field(name="Dano da arma", value=dano, inline=False)
        if custo_ph:
            embed.add_field(name="Custo pago", value=f"{custo_ph} PH", inline=True)
        if recarga:
            embed.add_field(name="Recarga", value=recarga, inline=True)
        controle_privado = bool(
            painel_privado is not None
            and painel_usuario_id
            and (
                painel_usuario_id == combate.moderador_id
                or painel_usuario_id == alvo.usuario_id
            )
        )
        view = (
            ReacaoAtaqueView(
                self,
                combate.identificador,
                alvo.identificador,
                total,
                tipo=tipo,
                lampejo=lampejo,
                atacante_id=atacante.identificador,
                nome_ataque=nome,
                dano=dano,
                painel_privado=painel_privado,
                painel_usuario_id=painel_usuario_id,
                publico=not controle_privado,
            )
            if sucesso
            else None
        )
        if sucesso and not controle_privado:
            await self.publicar_atualizacao(combate, embed, view)
        return combate, embed, view if controle_privado else None

    async def publicar_resultado_reacao(
        self,
        combate: Combate,
        mensagem_id: int,
        alvo: ParticipanteCombate,
        nome: str,
        total: int,
        ataque_total: int,
        *,
        detalhe: str,
        atacante_id: str = "",
        nome_ataque: str = "",
        dano: str = "",
        painel_privado: discord.Message | None = None,
        painel_usuario_id: int = 0,
        mensagem_direta: discord.Message | None = None,
        embed_base: discord.Embed | None = None,
        publico: bool = True,
    ) -> None:
        if mensagem_direta is not None:
            mensagem = mensagem_direta
            embed = (
                embed_base.copy()
                if embed_base is not None
                else discord.Embed(color=COR_COMBATE)
            )
        else:
            canal = await self._canal_combate(combate)
            if not hasattr(canal, "fetch_message"):
                raise ValueError("O canal não permite recuperar a mensagem do ataque.")
            mensagem = await canal.fetch_message(mensagem_id)
            embed = mensagem.embeds[0] if mensagem.embeds else discord.Embed(color=COR_COMBATE)
        evitou = total > ataque_total
        embed.add_field(
            name=f"{EMOJI_ESQUIVA if nome == 'Esquiva' else EMOJI_DEFESA} Reação — {nome}",
            value=(
                f"{alvo.nome}: {detalhe} = **{total}**\n"
                f"Ataque: **{ataque_total}**\n"
                f"**{'Ataque evitado' if evitou else 'Ataque atingiu o alvo'}**"
            ),
            inline=False,
        )
        view = None
        expressao = extrair_expressao_dano(dano)
        if not evitou and atacante_id and expressao:
            view = DanoAtaqueView(
                self,
                combate.identificador,
                atacante_id,
                alvo.identificador,
                nome_ataque,
                expressao,
                mensagem_id,
                painel_privado,
                painel_usuario_id,
                publico,
            )
        await mensagem.edit(embed=embed, view=view)
        if publico:
            await self.atualizar_painel_acao(
                combate.identificador,
                atacante_id,
                painel_usuario_id,
                painel_privado,
                embed,
            )
        elif view is None:
            await self.atualizar_painel_acao(
                combate.identificador,
                atacante_id,
                painel_usuario_id,
                mensagem,
                embed,
            )
        if publico and view is None:
            await self.remover_atualizacao_acao(combate.identificador, mensagem)

    async def resolver_dano(
        self,
        combate_id: str,
        atacante_id: str,
        alvo_id: str,
        nome: str,
        expressao: str,
        total: int,
        mensagem_id: int,
        *,
        detalhe: str,
        painel_privado: discord.Message | None = None,
        painel_usuario_id: int = 0,
        mensagem_direta: discord.Message | None = None,
        publico: bool = True,
    ) -> None:
        aplicado = 0

        def registrar(atual: Combate) -> None:
            nonlocal aplicado
            aplicado = aplicar_dano_combate(
                atual, atacante_id, alvo_id, total, nome
            )

        combate = await self.mutar(combate_id, registrar)
        await self.atualizar_mensagem(combate)
        alvo = combate.participante(alvo_id)
        if mensagem_direta is not None:
            mensagem = mensagem_direta
        else:
            canal = await self._canal_combate(combate)
            if not hasattr(canal, "fetch_message"):
                raise ValueError("O canal não permite recuperar a mensagem do ataque.")
            mensagem = await canal.fetch_message(mensagem_id)
        embed = mensagem.embeds[0] if mensagem.embeds else discord.Embed(color=COR_COMBATE)
        embed.add_field(
            name=f"Dano — {nome}",
            value=(
                f"{expressao}: {detalhe} = **{total}**\n"
                f"Dano aplicado: **{aplicado}**\n"
                f"{alvo.nome}: **{alvo.pv_atual}/{alvo.pv_maximo} {alvo.recurso_vida}**"
            ),
            inline=False,
        )
        await self.atualizar_painel_acao(
            combate.identificador,
            atacante_id,
            painel_usuario_id,
            painel_privado if publico else mensagem,
            embed,
        )
        if publico:
            await self.remover_atualizacao_acao(combate.identificador, mensagem)

    async def publicar_contra_feitico(
        self,
        combate_id: str,
        mensagem_id: int,
        alvo_id: str,
        nome: str,
        total: int,
        cd: int,
        detalhe: str,
        atacante_id: str = "",
        nome_ataque: str = "",
        dano: str = "",
        painel_privado: discord.Message | None = None,
        painel_usuario_id: int = 0,
        mensagem_direta: discord.Message | None = None,
        embed_base: discord.Embed | None = None,
        publico: bool = True,
    ) -> None:
        combate, _ = self.localizar(combate_id)
        alvo = combate.participante(alvo_id)
        if mensagem_direta is not None:
            mensagem = mensagem_direta
            embed = (
                embed_base.copy()
                if embed_base is not None
                else discord.Embed(color=COR_COMBATE)
            )
        else:
            canal = await self._canal_combate(combate)
            if not hasattr(canal, "fetch_message"):
                raise ValueError("O canal não permite recuperar a mensagem do ataque.")
            mensagem = await canal.fetch_message(mensagem_id)
            embed = mensagem.embeds[0] if mensagem.embeds else discord.Embed(color=COR_COMBATE)
        sucesso = total >= cd
        embed.add_field(
            name=f"Contra-feitiço — {nome}",
            value=(
                f"{alvo.nome}: {detalhe} = **{total}** • CD **{cd}**\n"
                + (
                    "**Execução bem-sucedida.** O mestre confirma se o contra-feitiço é adequado ao ataque."
                    if sucesso
                    else "**A execução falhou; o ataque atingiu o alvo.**"
                )
            ),
            inline=False,
        )
        view = None
        expressao = extrair_expressao_dano(dano)
        if not sucesso and atacante_id and expressao:
            view = DanoAtaqueView(
                self,
                combate.identificador,
                atacante_id,
                alvo.identificador,
                nome_ataque,
                expressao,
                mensagem_id,
                painel_privado,
                painel_usuario_id,
                publico,
            )
        await mensagem.edit(embed=embed, view=view)
        if publico:
            await self.atualizar_painel_acao(
                combate.identificador,
                atacante_id,
                painel_usuario_id,
                painel_privado,
                embed,
            )
        elif view is None:
            await self.atualizar_painel_acao(
                combate.identificador,
                atacante_id,
                painel_usuario_id,
                mensagem,
                embed,
            )
        if publico and view is None:
            await self.remover_atualizacao_acao(combate.identificador, mensagem)

    async def preparar_novo_combate(
        self,
        combate_id: str,
        descanso: str,
    ) -> tuple[Combate, Combate]:
        async with self.bloqueio:
            anterior, caminho = self.localizar(combate_id)
            novo = criar_novo_combate(anterior, descanso)
            salvar_combate(anterior, caminho)
            salvar_combate(novo)
            return anterior, novo

    async def atualizar_mensagem(self, combate: Combate) -> None:
        canal = self.bot.get_channel(combate.canal_id)
        if canal is None:
            canal = await self.bot.fetch_channel(combate.canal_id)
        if hasattr(canal, "get_partial_message"):
            mensagem = canal.get_partial_message(combate.mensagem_id)
        elif hasattr(canal, "fetch_message"):
            mensagem = await canal.fetch_message(combate.mensagem_id)
        else:
            raise ValueError("O canal do combate não permite atualizar a mensagem.")
        if combate.estado == "encerrado":
            mortos = any(not item.vivo for item in combate.participantes)
            await mensagem.edit(
                content=random.choice(VIDEOS_HOMENAGEM) if mortos else None,
                embed=embed_relatorio(combate),
                view=None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        await mensagem.edit(
            embed=embed_combate(combate),
            view=PainelCombateView(self, combate),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(
        name="combate",
        description="Inicia e conduz um combate integrado às fichas do Grimory.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def combate(self, interaction: discord.Interaction) -> None:
        membro = interaction.user
        if not isinstance(membro, discord.Member) or not membro.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Você precisa da permissão **Gerenciar servidor** para usar este comando.",
                ephemeral=True,
            )
            return
        combate = criar_combate(membro.id)
        await interaction.response.send_message(
            embed=embed_combate(combate),
            view=PainelCombateView(self, combate),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        mensagem = await interaction.original_response()
        combate.canal_id = mensagem.channel.id
        combate.mensagem_id = mensagem.id
        salvar_combate(combate)
