from __future__ import annotations

import json
import random
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from utils.biblioteca import interpretar_markdown, normalizar_rotulo
from utils.fichas import FichaPersonagem, ReferenciaFicha, bonus_pericia, listar_fichas
from utils.fichas_criaturas import (
    FichaCriatura,
    ReferenciaFichaCriatura,
    listar_fichas_criaturas,
)


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_COMBATES = RAIZ_PROJETO / "biblioteca" / "combates"
EQUIPE_ALIADOS = "Aliados"
EQUIPE_OPONENTES = "Oponentes"
EQUIPES = (EQUIPE_ALIADOS, EQUIPE_OPONENTES)
ESTADOS_PARTICIPANTE = ("ativo", "incapacitado", "morto")

DESCANSOS = {
    "5m": ("Descanso curto — 5 minutos", "1d4+1"),
    "15m": ("Descanso curto — 15 minutos", "1d6+1"),
    "30m": ("Descanso curto — 30 minutos", "1d8+2"),
    "1h": ("Descanso longo — 1 hora", "3d8+6"),
    "6h": ("Descanso longo — 6 horas", "metade da vida total"),
    "12h": ("Descanso longo — 12 horas", "vida cheia"),
}


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _novo_identificador() -> str:
    return uuid.uuid4().hex[:12]


@dataclass(frozen=True)
class ReferenciaCombatente:
    nome: str
    tipo: str
    grupo: str
    caminho: Path

    @property
    def chave(self) -> str:
        return f"{self.tipo}:{self.caminho.as_posix()}"


@dataclass
class ParticipanteCombate:
    identificador: str
    nome: str
    equipe: str
    tipo_ficha: str
    caminho_ficha: str
    pv_maximo: int
    ph_maximo: int
    pv_atual: int
    ph_atual: int
    iniciativa_bonus: int
    ordem_entrada: int
    recurso_vida: str = "PV"
    usuario_id: int = 0
    iniciativa_dado: int = 0
    iniciativa_total: int = 0
    estado: str = "ativo"
    dano_causado: int = 0
    dano_recebido: int = 0
    cura_realizada: int = 0
    criticos: int = 0
    turnos_realizados: int = 0
    acao_padrao_usada: bool = False
    acao_movimento_usada: bool = False
    acao_livre_usada: bool = False
    recargas: dict[str, int] = field(default_factory=dict)

    @property
    def vivo(self) -> bool:
        return self.estado != "morto"

    @property
    def pode_agir(self) -> bool:
        return self.estado == "ativo" and self.pv_atual > 0


@dataclass
class EventoCombate:
    tipo: str
    descricao: str
    criado_em: str = field(default_factory=_agora)
    participante_id: str = ""
    valor: int = 0


@dataclass
class Combate:
    identificador: str
    moderador_id: int
    criado_em: str
    participantes: list[ParticipanteCombate] = field(default_factory=list)
    estado: str = "preparacao"
    rodada: int = 0
    indice_turno: int = 0
    canal_id: int = 0
    mensagem_id: int = 0
    mensagem_atualizacao_id: int = 0
    eventos: list[EventoCombate] = field(default_factory=list)
    encerrado_em: str = ""
    combate_anterior_id: str = ""
    descanso_anterior: str = ""

    def por_equipe(self, equipe: str) -> list[ParticipanteCombate]:
        return [item for item in self.participantes if item.equipe == equipe]

    def participante(self, identificador: str) -> ParticipanteCombate:
        encontrado = next(
            (item for item in self.participantes if item.identificador == identificador),
            None,
        )
        if encontrado is None:
            raise ValueError("O participante não foi encontrado neste combate.")
        return encontrado

    def participante_atual(self) -> ParticipanteCombate | None:
        if self.estado != "ativo" or not self.participantes:
            return None
        self.indice_turno %= len(self.participantes)
        return self.participantes[self.indice_turno]

    def markdown(self) -> str:
        dados = json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))
        return f"# Combate {self.identificador}\n\nDados:\n- {dados}\n"


def listar_referencias_combate(termo: str = "") -> list[ReferenciaCombatente]:
    referencias: list[ReferenciaCombatente] = [
        ReferenciaCombatente(item.nome, "personagem", item.grupo, item.caminho)
        for item in listar_fichas(termo)
    ]
    referencias.extend(
        ReferenciaCombatente(
            item.nome,
            "criatura",
            f"Criatura {item.periculosidade}",
            item.caminho,
        )
        for item in listar_fichas_criaturas(termo)
    )
    return sorted(
        referencias,
        key=lambda item: (normalizar_rotulo(item.nome), item.tipo, item.grupo),
    )


def encontrar_referencia_combate(chave: str) -> ReferenciaCombatente | None:
    alvo = normalizar_rotulo(chave)
    for referencia in listar_referencias_combate():
        if normalizar_rotulo(referencia.chave) == alvo:
            return referencia
    return None


def _iniciativa_personagem(ficha: FichaPersonagem) -> int:
    return bonus_pericia(
        "Iniciativa",
        ficha.pericias.get("Iniciativa", 0),
        ficha.atributos,
    )[0]


def _iniciativa_criatura(ficha: FichaCriatura) -> int:
    return bonus_pericia(
        "Iniciativa",
        ficha.pericias.get("Iniciativa", 0),
        ficha.atributos,
    )[0]


def participante_da_referencia(
    referencia: ReferenciaCombatente,
    equipe: str,
    ordem_entrada: int,
) -> ParticipanteCombate:
    if equipe not in EQUIPES:
        raise ValueError("A equipe precisa ser Aliados ou Oponentes.")
    if referencia.tipo == "personagem":
        ficha = FichaPersonagem.carregar(referencia.caminho)
        espirito = ficha.tipo_npc == "Espírito"
        pv, ph = (ficha.alma if espirito else ficha.pv), ficha.ph
        recurso_vida = "Alma" if espirito else "PV"
        iniciativa = _iniciativa_personagem(ficha)
    elif referencia.tipo == "criatura":
        ficha = FichaCriatura.carregar(referencia.caminho)
        pv, ph = ficha.pv, ficha.ph
        recurso_vida = "PV"
        iniciativa = _iniciativa_criatura(ficha)
    else:
        raise ValueError("Tipo de ficha incompatível com o combate.")
    return ParticipanteCombate(
        identificador=_novo_identificador(),
        nome=referencia.nome,
        equipe=equipe,
        tipo_ficha=referencia.tipo,
        caminho_ficha=str(referencia.caminho.resolve()),
        pv_maximo=max(0, int(pv)),
        ph_maximo=max(0, int(ph)),
        pv_atual=max(0, int(pv)),
        ph_atual=max(0, int(ph)),
        iniciativa_bonus=iniciativa,
        ordem_entrada=ordem_entrada,
        recurso_vida=recurso_vida,
        usuario_id=int(getattr(ficha, "titular_id", 0) or 0),
    )


def criar_combate(moderador_id: int) -> Combate:
    return Combate(
        identificador=_novo_identificador(),
        moderador_id=moderador_id,
        criado_em=_agora(),
    )


def adicionar_participante(
    combate: Combate,
    referencia: ReferenciaCombatente,
    equipe: str,
) -> ParticipanteCombate:
    if combate.estado == "encerrado":
        raise ValueError("Este combate já foi encerrado.")
    participante = participante_da_referencia(
        referencia,
        equipe,
        ordem_entrada=len(combate.participantes),
    )
    # Depois do início, a lista já representa a iniciativa. Acrescentar preserva
    # a regra de que reforços sempre entram no fim da roda.
    combate.participantes.append(participante)
    combate.eventos.append(
        EventoCombate(
            tipo="entrada",
            participante_id=participante.identificador,
            descricao=f"{participante.nome} entrou entre os {equipe}.",
        )
    )
    return participante


def iniciar_combate(
    combate: Combate,
    rolar_d20: Callable[[], int] | None = None,
) -> None:
    if combate.estado != "preparacao":
        raise ValueError("O combate já foi iniciado.")
    if not combate.por_equipe(EQUIPE_ALIADOS) or not combate.por_equipe(EQUIPE_OPONENTES):
        raise ValueError("Adicione pelo menos um Aliado e um Oponente antes de começar.")
    rolar = rolar_d20 or (lambda: random.randint(1, 20))
    for participante in combate.participantes:
        participante.iniciativa_dado = int(rolar())
        participante.iniciativa_total = (
            participante.iniciativa_dado + participante.iniciativa_bonus
        )
    combate.participantes.sort(
        key=lambda item: (
            -item.iniciativa_total,
            -item.iniciativa_bonus,
            item.ordem_entrada,
        )
    )
    combate.estado = "ativo"
    combate.rodada = 1
    combate.indice_turno = 0
    combate.eventos.append(
        EventoCombate(tipo="inicio", descricao="O combate começou e as iniciativas foram definidas.")
    )


def reiniciar_acoes(participante: ParticipanteCombate) -> None:
    participante.acao_padrao_usada = False
    participante.acao_movimento_usada = False
    participante.acao_livre_usada = False
    participante.recargas = {
        nome: rodadas - 1
        for nome, rodadas in participante.recargas.items()
        if rodadas > 1
    }


def consumir_acao(participante: ParticipanteCombate, tipo: str) -> str:
    tipo_normalizado = normalizar_rotulo(tipo)
    if tipo_normalizado in {"nenhuma", "sem acao", "imediata", "imediato", "reacao"}:
        return "não consome ação"
    if tipo_normalizado in {"livre", "acao livre"}:
        if participante.acao_livre_usada:
            raise ValueError("A ação livre deste turno já foi utilizada.")
        participante.acao_livre_usada = True
        return "livre"
    if tipo_normalizado in {"padrao", "acao padrao", "ataque"}:
        if participante.acao_padrao_usada:
            raise ValueError("A ação padrão deste turno já foi utilizada.")
        participante.acao_padrao_usada = True
        return "padrão"
    if tipo_normalizado in {"movimento", "acao de movimento"}:
        if not participante.acao_movimento_usada:
            participante.acao_movimento_usada = True
            return "movimento"
        if not participante.acao_padrao_usada:
            participante.acao_padrao_usada = True
            return "padrão convertida em movimento"
        raise ValueError("As ações de movimento disponíveis neste turno já foram utilizadas.")
    if tipo_normalizado in {"completa", "acao completa"}:
        if (
            participante.acao_padrao_usada
            or participante.acao_movimento_usada
            or participante.acao_livre_usada
        ):
            raise ValueError("Uma ação completa exige todas as ações disponíveis.")
        participante.acao_padrao_usada = True
        participante.acao_movimento_usada = True
        participante.acao_livre_usada = True
        return "completa"
    raise ValueError("Tipo de ação desconhecido.")


def tipo_acao_descricao(descricao: str) -> str:
    texto = normalizar_rotulo(descricao)
    if "acao completa" in texto:
        return "completa"
    if "acao padrao" in texto:
        return "padrao"
    if "acao de movimento" in texto:
        return "movimento"
    if "acao livre" in texto:
        return "livre"
    return "nenhuma"


def registrar_acao_narrativa(
    combate: Combate,
    participante_id: str,
    tipo: str,
    descricao: str,
) -> str:
    participante = combate.participante(participante_id)
    consumo = consumir_acao(participante, tipo)
    combate.eventos.append(
        EventoCombate(
            tipo=f"acao_{normalizar_rotulo(tipo).replace(' ', '_')}",
            participante_id=participante.identificador,
            descricao=f"{participante.nome}: {descricao}",
        )
    )
    return consumo


def ativar_habilidade_combate(
    combate: Combate,
    participante_id: str,
    nome: str,
    descricao: str,
    custo_ph: int,
) -> str:
    participante = combate.participante(participante_id)
    custo = max(0, int(custo_ph))
    if participante.ph_atual < custo:
        raise ValueError(
            f"PH insuficiente: {nome} custa {custo}ph e "
            f"{participante.nome} possui {participante.ph_atual}ph."
        )
    tipo = tipo_acao_descricao(descricao)
    consumo = consumir_acao(participante, tipo)
    participante.ph_atual -= custo
    combate.eventos.append(
        EventoCombate(
            tipo="habilidade",
            participante_id=participante.identificador,
            valor=custo,
            descricao=(
                f"{participante.nome} ativou {nome} por {custo}ph "
                f"como ação {consumo}."
            ),
        )
    )
    return consumo


def registrar_ataque_combate(
    combate: Combate,
    participante_id: str,
    descricao: str,
    tipo_acao: str = "padrao",
    custo_ph: int = 0,
    nome_recarga: str = "",
    recarga: str = "",
) -> None:
    participante = combate.participante(participante_id)
    if nome_recarga and participante.recargas.get(nome_recarga, 0) > 0:
        raise ValueError(
            f"{nome_recarga} ainda está em recarga por "
            f"{participante.recargas[nome_recarga]} rodada(s)."
        )
    custo = max(0, int(custo_ph))
    if participante.ph_atual < custo:
        raise ValueError(
            f"PH insuficiente: a ação custa {custo} e "
            f"{participante.nome} possui {participante.ph_atual}."
        )
    consumir_acao(participante, tipo_acao)
    participante.ph_atual -= custo
    if nome_recarga:
        texto_recarga = normalizar_rotulo(recarga)
        numero = re.search(r"\d+", texto_recarga)
        if numero:
            participante.recargas[nome_recarga] = int(numero.group())
        elif "uma vez" in texto_recarga:
            participante.recargas[nome_recarga] = 10**9
    combate.eventos.append(
        EventoCombate(
            tipo="ataque",
            participante_id=participante.identificador,
            descricao=descricao,
        )
    )


def extrair_expressao_dano(texto: str) -> str:
    """Extrai somente uma expressão numérica de dados, sem inventar modificadores."""
    encontrado = re.search(r"\b(\d+d\d+(?:\s*[+-]\s*\d+)?)\b", texto, re.IGNORECASE)
    return re.sub(r"\s+", "", encontrado.group(1)) if encontrado else ""


def rolar_expressao_dano(
    expressao: str,
    rolar: Callable[[int, int], int] | None = None,
) -> tuple[int, list[int], int]:
    encontrado = re.fullmatch(r"(\d+)d(\d+)([+-]\d+)?", expressao.strip(), re.IGNORECASE)
    if not encontrado:
        raise ValueError("A ficha não possui uma expressão de dano numérica reconhecível.")
    quantidade, faces = int(encontrado.group(1)), int(encontrado.group(2))
    modificador = int(encontrado.group(3) or 0)
    if quantidade < 1 or quantidade > 100 or faces < 2 or faces > 1000:
        raise ValueError("A expressão de dano registrada na ficha é inválida.")
    gerador = rolar or (lambda minimo, maximo: random.randint(minimo, maximo))
    dados = [int(gerador(1, faces)) for _ in range(quantidade)]
    return max(0, sum(dados) + modificador), dados, modificador


def aplicar_dano_combate(
    combate: Combate,
    atacante_id: str,
    alvo_id: str,
    valor: int,
    fonte: str,
) -> int:
    atacante = combate.participante(atacante_id)
    alvo = combate.participante(alvo_id)
    dano = max(0, int(valor))
    pv_anterior = alvo.pv_atual
    alterar_recursos(alvo, pv=alvo.pv_atual - dano)
    aplicado = pv_anterior - alvo.pv_atual
    atacante.dano_causado += aplicado
    combate.eventos.append(
        EventoCombate(
            tipo="dano",
            participante_id=atacante.identificador,
            valor=aplicado,
            descricao=(
                f"{atacante.nome} causou {aplicado} de dano em {alvo.nome} "
                f"com {fonte}."
            ),
        )
    )
    return aplicado


def avancar_turno(combate: Combate) -> ParticipanteCombate | None:
    if combate.estado != "ativo":
        raise ValueError("O combate não está ativo.")
    if not combate.participantes:
        raise ValueError("Não há participantes na ordem de combate.")
    atual = combate.participante_atual()
    if atual is not None:
        atual.turnos_realizados += 1
    quantidade = len(combate.participantes)
    for _ in range(quantidade):
        combate.indice_turno += 1
        if combate.indice_turno >= quantidade:
            combate.indice_turno = 0
            combate.rodada += 1
        candidato = combate.participante_atual()
        if candidato is not None and candidato.pode_agir:
            reiniciar_acoes(candidato)
            return candidato
    return combate.participante_atual()


def alterar_recursos(
    participante: ParticipanteCombate,
    *,
    pv: int | None = None,
    ph: int | None = None,
    estado: str | None = None,
) -> None:
    pv_anterior = participante.pv_atual
    if pv is not None:
        participante.pv_atual = min(participante.pv_maximo, max(0, int(pv)))
        diferenca = participante.pv_atual - pv_anterior
        if diferenca < 0:
            participante.dano_recebido += abs(diferenca)
        elif diferenca > 0:
            participante.cura_realizada += diferenca
    if ph is not None:
        participante.ph_atual = min(participante.ph_maximo, max(0, int(ph)))
    if estado is not None:
        if estado not in ESTADOS_PARTICIPANTE:
            raise ValueError("Estado de participante inválido.")
        participante.estado = estado
    elif participante.pv_atual == 0 and participante.estado == "ativo":
        participante.estado = "incapacitado"
    elif participante.pv_atual > 0 and participante.estado == "incapacitado":
        participante.estado = "ativo"


def remover_participante(combate: Combate, identificador: str) -> ParticipanteCombate:
    participante = combate.participante(identificador)
    indice = combate.participantes.index(participante)
    combate.participantes.pop(indice)
    if combate.participantes:
        if indice < combate.indice_turno:
            combate.indice_turno -= 1
        combate.indice_turno %= len(combate.participantes)
    else:
        combate.indice_turno = 0
    combate.eventos.append(
        EventoCombate(
            tipo="saida",
            participante_id=identificador,
            descricao=f"{participante.nome} foi retirado do combate.",
        )
    )
    return participante


def encerrar_combate(combate: Combate) -> None:
    if combate.estado == "encerrado":
        raise ValueError("Este combate já foi encerrado.")
    combate.estado = "encerrado"
    combate.encerrado_em = _agora()
    combate.eventos.append(
        EventoCombate(tipo="fim", descricao=f"O combate terminou após {combate.rodada} rodada(s).")
    )


def _rolar_expressao_descanso(chave: str, rolar: Callable[[int, int], int]) -> int:
    if chave == "5m":
        return rolar(1, 4) + 1
    if chave == "15m":
        return rolar(1, 6) + 1
    if chave == "30m":
        return rolar(1, 8) + 2
    if chave == "1h":
        return rolar(3, 8) + 6
    raise ValueError("O descanso escolhido não usa uma rolagem de recuperação.")


def criar_novo_combate(
    anterior: Combate,
    descanso: str,
    *,
    rolar_dados: Callable[[int, int], int] | None = None,
) -> Combate:
    if descanso not in DESCANSOS:
        raise ValueError("Tempo de descanso inválido.")
    rolar = rolar_dados or (
        lambda quantidade, faces: sum(random.randint(1, faces) for _ in range(quantidade))
    )
    novo = criar_combate(anterior.moderador_id)
    novo.combate_anterior_id = anterior.identificador
    novo.descanso_anterior = descanso
    for antigo in anterior.participantes:
        if not antigo.vivo:
            continue
        participante = ParticipanteCombate(
            identificador=_novo_identificador(),
            nome=antigo.nome,
            equipe=antigo.equipe,
            tipo_ficha=antigo.tipo_ficha,
            caminho_ficha=antigo.caminho_ficha,
            pv_maximo=antigo.pv_maximo,
            ph_maximo=antigo.ph_maximo,
            pv_atual=antigo.pv_atual,
            ph_atual=antigo.ph_atual,
            iniciativa_bonus=antigo.iniciativa_bonus,
            ordem_entrada=len(novo.participantes),
            usuario_id=antigo.usuario_id,
        )
        if descanso == "12h":
            participante.pv_atual = participante.pv_maximo
        elif descanso == "6h":
            participante.pv_atual = min(
                participante.pv_maximo,
                participante.pv_atual + participante.pv_maximo // 2,
            )
        else:
            participante.pv_atual = min(
                participante.pv_maximo,
                participante.pv_atual + _rolar_expressao_descanso(descanso, rolar),
            )
        # A tabela de PH ainda não foi definida. O recurso é preservado entre cenas.
        if participante.pv_atual > 0 and participante.estado == "incapacitado":
            participante.estado = "ativo"
        novo.participantes.append(participante)
    novo.eventos.append(
        EventoCombate(
            tipo="descanso",
            descricao=f"Novo combate preparado após {DESCANSOS[descanso][0].lower()}.",
        )
    )
    encerrar_combate(anterior)
    return novo


def salvar_combate(combate: Combate, caminho: Path | None = None) -> Path:
    destino = caminho or PASTA_COMBATES / f"{combate.identificador}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".md.tmp")
    temporario.write_text(combate.markdown(), encoding="utf-8", newline="\n")
    temporario.replace(destino)
    return destino


def carregar_combate(caminho: Path) -> Combate:
    entrada = interpretar_markdown(caminho.read_text(encoding="utf-8-sig"))
    linhas = entrada.campos.get("Dados", "").splitlines()
    conteudo = next(
        (linha.strip().removeprefix("- ") for linha in linhas if linha.strip()),
        "",
    )
    if not conteudo:
        raise ValueError("O combate não possui dados persistidos.")
    dados = json.loads(conteudo)
    dados["participantes"] = [
        ParticipanteCombate(**item) for item in dados.get("participantes", [])
    ]
    dados["eventos"] = [EventoCombate(**item) for item in dados.get("eventos", [])]
    return Combate(**dados)


def encontrar_combate_por_mensagem(
    mensagem_id: int,
    pasta: Path | None = None,
) -> tuple[Combate, Path] | None:
    origem = pasta or PASTA_COMBATES
    if not origem.is_dir():
        return None
    for caminho in origem.glob("*.md"):
        try:
            combate = carregar_combate(caminho)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if combate.mensagem_id == mensagem_id:
            return combate, caminho
    return None


def valores_rolaveis(participante: ParticipanteCombate) -> list[tuple[str, int, str]]:
    caminho = Path(participante.caminho_ficha)
    if participante.tipo_ficha == "personagem":
        ficha = FichaPersonagem.carregar(caminho)
        resultado: list[tuple[str, int, str]] = []
        for nome, valor in ficha.atributos.items():
            resultado.append((nome, (valor - 10) // 2, "Atributo"))
        for nome, treinamento in ficha.pericias.items():
            bonus = bonus_pericia(nome, treinamento, ficha.atributos)
            for indice, valor in enumerate(bonus):
                sufixo = "" if len(bonus) == 1 else f" {indice + 1}"
                resultado.append((f"{nome}{sufixo}", valor, "Perícia"))
        resultado.extend((nome, valor, "Aptidão") for nome, valor in ficha.aptidoes.items())
        return resultado
    ficha = FichaCriatura.carregar(caminho)
    resultado = [
        (nome, (valor - 10) // 2, "Atributo")
        for nome, valor in ficha.atributos.items()
    ]
    for nome, treinamento in ficha.pericias.items():
        bonus = bonus_pericia(nome, treinamento, ficha.atributos)
        for indice, valor in enumerate(bonus):
            sufixo = "" if len(bonus) == 1 else f" {indice + 1}"
            resultado.append((f"{nome}{sufixo}", valor, "Perícia"))
    return resultado
