from __future__ import annotations

import json
import random
import re
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from utils.biblioteca import interpretar_markdown, normalizar_rotulo
from utils.fichas import (
    FichaPersonagem,
    ReferenciaFicha,
    bonus_pericia,
    encontrar_ficha,
    listar_fichas,
    modificador,
    salvar_ficha,
)
from utils.taca import AcontecimentoTaca, CASAS, EstadoTaca, aplicar_acontecimento


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_QUADRIBOL = RAIZ_PROJETO / "biblioteca" / "quadribol"
PASTA_VASSOURAS = PASTA_QUADRIBOL / "vassouras"
PASTA_LINHAS_VASSOURAS = PASTA_VASSOURAS / "linhas"
ARQUIVO_IMAGENS_VASSOURAS = PASTA_LINHAS_VASSOURAS / "Imagens.md"
PASTA_PARTIDAS = PASTA_QUADRIBOL / "partidas"
PASTA_TIMES_AMADORES = PASTA_QUADRIBOL / "times_amadores"
ARQUIVO_TIMES_AMADORES = PASTA_TIMES_AMADORES / "times.json"
ARQUIVO_MANOBRAS = PASTA_QUADRIBOL / "Manobras.md"
ARQUIVO_FALTAS = PASTA_QUADRIBOL / "Faltas.md"

POSICOES = ("Goleiro", "Artilheiro", "Batedor", "Apanhador")
SITUACOES_TIME = ("Titular", "Reserva")

POSICOES_RECOMENDADAS_POR_LINHA = {
    "Cavalier": ("Goleiro", "Batedor"),
    "Comet": ("Goleiro",),
    "Swiftstick": ("Goleiro",),
    "Cleansweep": ("Artilheiro",),
    "Onda Aérea": ("Artilheiro",),
    "Yajirushi": ("Artilheiro",),
    "Oakshaft": ("Batedor",),
    "Stormrider": ("Batedor",),
    "Estrela Cadente": ("Apanhador",),
    "Firebolt": ("Apanhador",),
    "Nimbus": ("Apanhador",),
    "Thunderbolt": ("Batedor", "Apanhador"),
    "Tinderblast": ("Apanhador",),
    "Turbo": ("Apanhador",),
}

PERFIS_SITUACIONAIS_POR_LINHA = {
    "Artesanal": "Versátil",
    "Bluebottle": "Versátil/Resistente",
    "Starsweeper": "Situacional/baixa visibilidade",
    "Twigger": "Versátil/manobras",
}


def descricao_recomendacao_linha(linha: str) -> str:
    posicoes = POSICOES_RECOMENDADAS_POR_LINHA.get(linha, ())
    if posicoes:
        return f"Favorece: {'/'.join(posicoes)}"
    return PERFIS_SITUACIONAIS_POR_LINHA.get(linha, "Versátil")
FORMACAO_PADRAO = {"Goleiro": 1, "Artilheiro": 3, "Batedor": 2, "Apanhador": 1}
JOGOS_TEMPORADA = ("1º jogo", "2º jogo", "Final")
TIPOS_PARTIDA = ("Partida Oficial", "Partida Amistosa")
PROGRESSO_POMO_NECESSARIO = 75
INTENSIDADES_CONDICAO = {
    "Leve": 10,
    "Padrão": 12,
    "Difícil": 14,
    "Muito difícil": 16,
    "Excepcional": 18,
}
PROGRESSO_POMO_POR_VELOCIDADE = {
    15: 30,
    14: 35,
    13: 40,
    12: 45,
    11: 50,
    10: 55,
    9: 60,
    8: 65,
    7: 70,
    6: 75,
    5: 80,
    4: 85,
    3: 105,
}
ESPECIALIZACAO_PRODIGIO = "Prodígio do Quadribol"
PERICIA_POR_POSICAO = {
    "Goleiro": "Reflexo",
    "Artilheiro": "Pontaria",
    "Batedor": "Pontaria",
    "Apanhador": "Vôo",
}


def _inteiro(campos: dict[str, str], nome: str, padrao: int | None = None) -> int:
    valor = campos.get(normalizar_rotulo(nome), "").strip()
    try:
        return int(valor)
    except ValueError:
        if padrao is not None:
            return padrao
        raise ValueError(f"{nome} precisa ser um número inteiro.") from None


def _bonus_direto_ou_dado(
    campos: dict[str, str], nome: str
) -> tuple[int, str]:
    valor = campos.get(normalizar_rotulo(nome), "0").strip().lower().removeprefix("+")
    if valor == "1d4":
        return 0, "1d4"
    try:
        direto = int(valor)
    except ValueError:
        raise ValueError(f"{nome} precisa ser 0, 1, 2, 3 ou 1d4.") from None
    if direto not in (0, 1, 2, 3):
        raise ValueError(f"{nome} precisa ser 0, 1, 2, 3 ou 1d4.")
    return direto, ""


def _bonus_fixo(campos: dict[str, str], nome: str) -> int:
    valor = _inteiro(campos, nome, 0)
    if valor not in (0, 1, 2, 3):
        raise ValueError(f"{nome} precisa estar entre 0 e 3.")
    return valor


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _identificador(prefixo: str) -> str:
    return f"{prefixo}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"


@dataclass(frozen=True)
class Vassoura:
    nome: str
    bonus_voo: int
    vida_maxima: int
    descricao: str = ""
    linha: str = ""
    velocidade: str = ""
    custo: str = ""
    especificacoes: tuple[str, ...] = ()
    bonus_reflexo: int = 0
    bonus_fortitude: int = 0
    bonus_pontaria: int = 0
    dado_bonus_pontaria: str = ""
    uso_bonus_pontaria: str = ""
    avaliacao_bastian: str = ""
    imagem_url: str = ""

    @classmethod
    def carregar(cls, caminho: Path) -> Vassoura:
        entrada = interpretar_markdown(caminho.read_text(encoding="utf-8-sig"))
        campos = {
            normalizar_rotulo(rotulo): valor.strip()
            for rotulo, valor in entrada.campos.items()
        }
        nome = (entrada.titulo or caminho.stem).strip()
        bonus = _bonus_fixo(campos, "Bônus de Vôo")
        vida = _inteiro(campos, "Vida máxima")
        if vida <= 0:
            raise ValueError(f"{nome} precisa possuir Vida máxima positiva.")
        def opcional(rotulo: str) -> str:
            valor = campos.get(normalizar_rotulo(rotulo), "").strip()
            return "" if valor == "--" else valor

        bonus_pontaria, dado_bonus_pontaria = _bonus_direto_ou_dado(
            campos, "Bônus de Pontaria"
        )
        return cls(
            nome=nome,
            bonus_voo=bonus,
            vida_maxima=vida,
            descricao=entrada.descricao.strip(),
            linha=opcional("Linha"),
            velocidade=opcional("Velocidade"),
            custo=opcional("Custo"),
            especificacoes=tuple(
                linha.strip().removeprefix("- ").strip()
                for linha in campos.get(
                    normalizar_rotulo("Especificações"), ""
                ).splitlines()
                if linha.strip().removeprefix("- ").strip()
                and linha.strip().removeprefix("- ").strip() != "--"
            ),
            bonus_reflexo=_bonus_fixo(campos, "Bônus de Reflexo"),
            bonus_fortitude=_bonus_fixo(campos, "Bônus de Fortitude"),
            bonus_pontaria=bonus_pontaria,
            dado_bonus_pontaria=dado_bonus_pontaria,
            uso_bonus_pontaria=opcional("Uso do Bônus de Pontaria"),
            avaliacao_bastian=opcional("Avaliação de Bastian Crowley"),
            imagem_url=opcional("Imagem"),
        )

    def markdown(self) -> str:
        return (
            f"# {self.nome}\n\n"
            f"Bônus de Vôo:\n{self.bonus_voo}\n\n"
            f"Bônus de Reflexo:\n{self.bonus_reflexo}\n\n"
            f"Bônus de Fortitude:\n{self.bonus_fortitude}\n\n"
            f"Bônus de Pontaria:\n{self.dado_bonus_pontaria or self.bonus_pontaria}\n\n"
            f"Uso do Bônus de Pontaria:\n{self.uso_bonus_pontaria or '--'}\n\n"
            f"Vida máxima:\n{self.vida_maxima}\n\n"
            f"Linha:\n{self.linha or '--'}\n\n"
            f"Velocidade:\n{self.velocidade or '--'}\n\n"
            f"Custo:\n{self.custo or '--'}\n\n"
            "Especificações:\n"
            + ("\n".join(f"- {item}" for item in self.especificacoes) or "--")
            + "\n\n"
            f"Descrição:\n{self.descricao or '--'}\n"
            "\n"
            f"Avaliação de Bastian Crowley:\n{self.avaliacao_bastian or '--'}\n"
            "\n"
            f"Imagem:\n{self.imagem_url or '--'}\n"
        )


def descricao_vassoura(vassoura: Vassoura) -> str:
    bonus = []
    if vassoura.bonus_voo:
        bonus.append(f"{vassoura.bonus_voo:+d} de Vôo")
    if vassoura.bonus_reflexo:
        bonus.append(f"{vassoura.bonus_reflexo:+d} de Reflexo")
    if vassoura.bonus_fortitude:
        bonus.append(f"{vassoura.bonus_fortitude:+d} de Fortitude")
    if vassoura.bonus_pontaria:
        uso = f" em {vassoura.uso_bonus_pontaria}" if vassoura.uso_bonus_pontaria else ""
        bonus.append(f"{vassoura.bonus_pontaria:+d} de Pontaria{uso}")
    elif vassoura.dado_bonus_pontaria:
        uso = f" em {vassoura.uso_bonus_pontaria}" if vassoura.uso_bonus_pontaria else ""
        bonus.append(f"+{vassoura.dado_bonus_pontaria} de Pontaria{uso}")
    if not bonus:
        return vassoura.nome
    return f"{vassoura.nome} ({', '.join(bonus)})"


def velocidade_vassoura(vassoura: Vassoura) -> int:
    encontrado = re.fullmatch(r"\s*(\d+)\s*m/s\s*", vassoura.velocidade, re.IGNORECASE)
    return int(encontrado.group(1)) if encontrado else 0


def listar_vassouras(
    termo: str = "",
    pasta: Path | None = None,
) -> list[Vassoura]:
    origem = pasta or PASTA_VASSOURAS
    if not origem.is_dir():
        return []
    busca = normalizar_rotulo(termo)
    imagens = carregar_imagens_vassouras()
    resultado: list[Vassoura] = []
    for arquivo in origem.glob("*.md"):
        try:
            item = Vassoura.carregar(arquivo)
        except ValueError:
            continue
        if not item.imagem_url:
            item = replace(
                item,
                imagem_url=imagens.get(normalizar_rotulo(item.nome), ""),
            )
        if not busca or busca in normalizar_rotulo(item.nome):
            resultado.append(item)
    return sorted(resultado, key=lambda item: item.nome.casefold())


def carregar_imagens_vassouras() -> dict[str, str]:
    if not ARQUIVO_IMAGENS_VASSOURAS.is_file():
        return {}
    imagens: dict[str, str] = {}
    for linha in ARQUIVO_IMAGENS_VASSOURAS.read_text(encoding="utf-8-sig").splitlines():
        conteudo = linha.strip().removeprefix("- ").strip()
        nome, separador, referencia = conteudo.rpartition(": ")
        if linha.strip().startswith("- ") and separador and referencia:
            imagens[normalizar_rotulo(nome)] = referencia.strip()
    return imagens


def encontrar_vassoura(nome: str, pasta: Path | None = None) -> Vassoura | None:
    procurado = normalizar_rotulo(nome)
    encontrados = [
        item for item in listar_vassouras(pasta=pasta)
        if normalizar_rotulo(item.nome) == procurado
    ]
    return encontrados[0] if len(encontrados) == 1 else None


def linhas_vassouras(
    vassouras: Iterable[Vassoura] | None = None,
) -> dict[str, list[Vassoura]]:
    def chave_natural(nome: str) -> tuple[tuple[int, object], ...]:
        return tuple(
            (1, int(parte)) if parte.isdigit() else (0, parte.casefold())
            for parte in re.split(r"(\d+)", nome)
            if parte
        )

    resultado: dict[str, list[Vassoura]] = {}
    for vassoura in vassouras if vassouras is not None else listar_vassouras():
        linha = vassoura.linha or "Outras"
        resultado.setdefault(linha, []).append(vassoura)
    for modelos in resultado.values():
        modelos.sort(key=lambda item: chave_natural(item.nome))
    return dict(sorted(resultado.items(), key=lambda item: item[0].casefold()))


def _preco_vassoura(vassoura: Vassoura) -> tuple[int, str]:
    galeoes = re.search(r"(\d+)\s+Gale", vassoura.custo, re.IGNORECASE)
    sicles = re.search(r"(\d+)\s+Sicle", vassoura.custo, re.IGNORECASE)
    if not galeoes:
        return 10**9, vassoura.nome.casefold()
    total_sicles = int(galeoes.group(1)) * 17 + (int(sicles.group(1)) if sicles else 0)
    return total_sicles, vassoura.nome.casefold()


def linhas_vassouras_por_preco(
    vassouras: Iterable[Vassoura] | None = None,
) -> dict[str, list[Vassoura]]:
    linhas = linhas_vassouras(vassouras)
    ordenadas = [
        (linha, sorted(modelos, key=_preco_vassoura))
        for linha, modelos in linhas.items()
    ]
    ordenadas.sort(
        key=lambda item: min(
            (_preco_vassoura(modelo) for modelo in item[1]),
            default=(10**9, item[0].casefold()),
        )
    )
    return dict(ordenadas)


def avaliacao_linha_vassoura(linha: str) -> str:
    procurado = normalizar_rotulo(linha)
    if not PASTA_LINHAS_VASSOURAS.is_dir():
        return ""
    for arquivo in PASTA_LINHAS_VASSOURAS.glob("*.md"):
        entrada = interpretar_markdown(arquivo.read_text(encoding="utf-8-sig"))
        if normalizar_rotulo(entrada.titulo or arquivo.stem) == procurado:
            return entrada.descricao.strip()
    return ""


def perfil_linha_vassoura(linha: str) -> str:
    procurado = normalizar_rotulo(linha)
    if not PASTA_LINHAS_VASSOURAS.is_dir():
        return ""
    for arquivo in PASTA_LINHAS_VASSOURAS.glob("*.md"):
        entrada = interpretar_markdown(arquivo.read_text(encoding="utf-8-sig"))
        if normalizar_rotulo(entrada.titulo or arquivo.stem) != procurado:
            continue
        campos = {
            normalizar_rotulo(nome): valor.strip()
            for nome, valor in entrada.campos.items()
        }
        return campos.get(normalizar_rotulo("Perfil geral"), "")
    return ""


def faixa_preco_linha(vassouras: Iterable[Vassoura]) -> str:
    modelos = list(vassouras)
    precos: list[tuple[int, int, str]] = []
    for modelo in modelos:
        galeoes = re.search(r"(\d+)\s+Gale", modelo.custo, re.IGNORECASE)
        sicles = re.search(r"(\d+)\s+Sicle", modelo.custo, re.IGNORECASE)
        if galeoes:
            precos.append((int(galeoes.group(1)), int(sicles.group(1)) if sicles else 0, modelo.custo))
    if not precos:
        return "Preço não informado"
    precos.sort()
    if len(precos) == 1 or precos[0][:2] == precos[-1][:2]:
        return precos[0][2]
    return f"{precos[0][2]} – {precos[-1][2]}"


def _indice_informacao(ficha: FichaPersonagem, titulo: str) -> int | None:
    procurado = normalizar_rotulo(titulo)
    return next(
        (
            indice
            for indice, item in enumerate(ficha.informacoes)
            if normalizar_rotulo(item.get("titulo", "")) == procurado
        ),
        None,
    )


def obter_informacao(ficha: FichaPersonagem, titulo: str) -> str:
    indice = _indice_informacao(ficha, titulo)
    return ficha.informacoes[indice].get("descricao", "").strip() if indice is not None else ""


def definir_informacao(ficha: FichaPersonagem, titulo: str, descricao: str) -> None:
    registro = {"titulo": titulo, "descricao": descricao.strip()}
    indice = _indice_informacao(ficha, titulo)
    if indice is None:
        ficha.informacoes.append(registro)
    else:
        ficha.informacoes[indice] = registro


def obter_vassoura_ficha(ficha: FichaPersonagem) -> str:
    vassouras = [
        item
        for item in ficha.itens
        if normalizar_rotulo(item.get("categoria", "")) == normalizar_rotulo("Variados")
        and normalizar_rotulo(item.get("tipo", "")) == normalizar_rotulo("Vassoura")
    ]
    equipada = next(
        (
            item for item in vassouras
            if normalizar_rotulo(item.get("equipada", "")) == normalizar_rotulo("Sim")
        ),
        None,
    )
    escolhida = equipada or (vassouras[0] if vassouras else None)
    if escolhida is not None:
        return escolhida.get("nome", "").strip()
    # Compatibilidade de leitura até todas as fichas antigas serem salvas.
    return obter_informacao(ficha, "Vassoura")


def definir_vassoura_ficha(ficha: FichaPersonagem, nome: str) -> None:
    encontrada = None
    for item in ficha.itens:
        if (
            normalizar_rotulo(item.get("categoria", "")) == normalizar_rotulo("Variados")
            and normalizar_rotulo(item.get("tipo", "")) == normalizar_rotulo("Vassoura")
        ):
            item["equipada"] = "Não"
            if normalizar_rotulo(item.get("nome", "")) == normalizar_rotulo(nome):
                encontrada = item
    if encontrada is None:
        encontrada = {
            "categoria": "Variados",
            "nome": nome,
            "quantidade": "1",
            "tipo": "Vassoura",
            "descricao": "Vassoura de Quadribol vinculada ao catálogo oficial.",
        }
        ficha.itens.append(encontrada)
    encontrada["equipada"] = "Sim"
    indice_antigo = _indice_informacao(ficha, "Vassoura")
    if indice_antigo is not None:
        ficha.informacoes.pop(indice_antigo)


def modelo_vassoura_da_descricao(descricao: str) -> str:
    return re.sub(r"\s*\([^()]*\)\s*$", "", descricao).strip()


def configurar_jogador(
    referencia: ReferenciaFicha,
    posicao: str,
    vassoura: Vassoura,
    *,
    situacao: str = "Titular",
    salvar: bool = True,
) -> FichaPersonagem:
    ficha = FichaPersonagem.carregar(referencia.caminho)
    if referencia.grupo not in {*CASAS, "Players"} or ficha.casa not in CASAS:
        raise ValueError(
            "Apenas personagens de uma das quatro casas podem jogar Quadribol."
        )
    if posicao not in POSICOES:
        raise ValueError("Posição de Quadribol inválida.")
    if situacao not in SITUACOES_TIME:
        raise ValueError("Situação no time inválida.")
    definir_informacao(ficha, "Jogador de Quadribol", posicao)
    definir_informacao(ficha, "Situação no time", situacao)
    # A ficha guarda somente a referência canônica. Bônus, PV, velocidade e
    # especificações são sempre lidos do arquivo atual da biblioteca.
    definir_vassoura_ficha(ficha, vassoura.nome)
    if salvar:
        salvar_ficha(ficha, referencia.caminho)
    return ficha


def casa_da_referencia(referencia: ReferenciaFicha) -> str:
    if referencia.grupo in CASAS:
        return referencia.grupo
    if referencia.grupo != "Players":
        return ""
    try:
        casa = FichaPersonagem.carregar(referencia.caminho).casa
    except (OSError, ValueError):
        return ""
    return casa if casa in CASAS else ""


def listar_fichas_elegiveis(termo: str = "") -> list[ReferenciaFicha]:
    return [item for item in listar_fichas(termo) if casa_da_referencia(item)]


def encontrar_ficha_elegivel(valor: str) -> ReferenciaFicha | None:
    referencia = encontrar_ficha(valor)
    return referencia if referencia is not None and casa_da_referencia(referencia) else None


def total_pericia(ficha: FichaPersonagem, nome: str) -> int:
    totais = bonus_pericia(nome, ficha.pericias.get(nome, 0), ficha.atributos)
    if len(totais) != 1:
        raise ValueError(f"{nome} não possui um único atributo definido para o teste.")
    return totais[0]


def possui_prodigio(ficha: FichaPersonagem) -> bool:
    """Prodígio custa PH e só modifica testes enquanto estiver ativado na ficha."""
    alvo = normalizar_rotulo(ESPECIALIZACAO_PRODIGIO)
    return any(
        normalizar_rotulo(efeito.get("nome", "")) == alvo
        for efeito in ficha.efeitos_habilidades_ativos
    )


def bonus_posicao(
    ficha: FichaPersonagem,
    posicao: str,
    vassoura: Vassoura,
) -> tuple[str, int]:
    if posicao not in PERICIA_POR_POSICAO:
        raise ValueError("Posição de Quadribol inválida.")
    teste = PERICIA_POR_POSICAO[posicao]
    if teste == "Vôo":
        total = ficha.aptidoes.get("Vôo", 0) + vassoura.bonus_voo
    elif teste == "Reflexo":
        total = total_pericia(ficha, teste) + vassoura.bonus_reflexo
    else:
        total = total_pericia(ficha, teste)
    if possui_prodigio(ficha):
        total += 2
    return teste, total


@dataclass(frozen=True)
class ManobraQuadribol:
    nome: str
    cd: int
    requisito_quadribol: int
    posicoes: tuple[str, ...]
    participantes: str
    descricao: str
    execucao: str
    beneficio: str


@dataclass
class TimeAmador:
    nome: str
    jogadores: dict[str, tuple[str, str]] = field(default_factory=dict)
    descricao: str = ""


def carregar_times_amadores(caminho: Path | None = None) -> list[TimeAmador]:
    origem = caminho or ARQUIVO_TIMES_AMADORES
    if not origem.is_file():
        return []
    try:
        dados = json.loads(origem.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    return [
        TimeAmador(
            nome=str(item.get("nome", "")).strip(),
            jogadores={
                str(nome): (str(valor[0]), str(valor[1]))
                for nome, valor in item.get("jogadores", {}).items()
                if isinstance(valor, list) and len(valor) == 2
            },
            descricao=str(item.get("descricao", "")).strip(),
        )
        for item in dados
        if str(item.get("nome", "")).strip()
    ]


def salvar_time_amador(time: TimeAmador, caminho: Path | None = None) -> TimeAmador:
    destino = caminho or ARQUIVO_TIMES_AMADORES
    times = carregar_times_amadores(destino)
    if any(normalizar_rotulo(item.nome) == normalizar_rotulo(time.nome) for item in times):
        raise ValueError(f"Já existe um time amador chamado {time.nome}.")
    if len(time.jogadores) != 7:
        raise ValueError("Um time amador precisa ter exatamente sete jogadores.")
    contagem = {posicao: 0 for posicao in POSICOES}
    for _, (posicao, _) in time.jogadores.items():
        if posicao not in contagem:
            raise ValueError("A escalação contém uma posição inválida.")
        contagem[posicao] += 1
    if contagem != FORMACAO_PADRAO:
        raise ValueError("A escalação precisa ter 1 Goleiro, 3 Artilheiros, 2 Batedores e 1 Apanhador.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    times.append(time)
    temporario = destino.with_name(f".{destino.name}.tmp")
    temporario.write_text(json.dumps([asdict(item) for item in times], ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(destino)
    return time


def manobra_exige_coordenador(manobra: ManobraQuadribol) -> bool:
    """Coordenador só existe quando a equipe executora usa mais de um jogador."""
    participantes = normalizar_rotulo(manobra.participantes)
    return not re.match(r"^(um|uma)\b", participantes)


BONUS_ARREMESSO_MANOBRAS = {
    "relampago de dragao": 4,
    "mergulho do falcao": 1,
    "flecha envenenada": 2,
    "a danca das serpentes": 1,
    "manobra de ploy": 2,
    "rotacao de hydra": 2,
    "voo em espiral": 2,
}


def _possui_efeito_contextual(
    jogador: JogadorPartida,
    nome: str,
    contexto: str = "",
) -> bool:
    nome_alvo = normalizar_rotulo(nome)
    contexto_alvo = normalizar_rotulo(contexto)
    return any(
        normalizar_rotulo(efeito.nome) == nome_alvo
        and (not contexto_alvo or normalizar_rotulo(efeito.contexto) == contexto_alvo)
        for efeito in jogador.efeitos
    )


def batedores_zona_fogo(
    partida: PartidaQuadribol,
    jogador: JogadorPartida,
) -> tuple[JogadorPartida, ...]:
    participantes = tuple(
        item
        for item in partida.jogadores
        if item.casa == jogador.casa
        and item.posicao == "Batedor"
        and item.ativo
        and item.em_campo
        and _possui_efeito_contextual(item, "Zona de Fogo", "zona_fogo")
    )
    return participantes if len(participantes) == 2 else ()


def zona_fogo_ativa(partida: PartidaQuadribol, jogador: JogadorPartida) -> bool:
    return bool(batedores_zona_fogo(partida, jogador))


def encerrar_zona_fogo(
    partida: PartidaQuadribol,
    casa: str,
    motivo: str,
) -> tuple[str, ...]:
    participantes: list[str] = []
    for jogador in partida.jogadores:
        if jogador.casa != casa:
            continue
        removidos = [
            efeito
            for efeito in jogador.efeitos
            if normalizar_rotulo(efeito.nome) == "zona de fogo"
            and normalizar_rotulo(efeito.contexto) == "zona_fogo"
        ]
        if not removidos:
            continue
        jogador.efeitos = [efeito for efeito in jogador.efeitos if efeito not in removidos]
        participantes.append(jogador.nome)
    if participantes:
        partida.eventos.append(
            EventoPartida(
                tipo="fim_efeito",
                casa=casa,
                jogador=", ".join(participantes),
                descricao=f"Zona de Fogo encerrada: {motivo}.",
            )
        )
    return tuple(participantes)


def encerrar_muralha_ogro(
    partida: PartidaQuadribol,
    casa: str,
    motivo: str,
) -> tuple[str, ...]:
    afetados: list[str] = []
    nome_alvo = "formacao muralha de ogro"
    for jogador in partida.jogadores:
        removidos = [
            efeito
            for efeito in jogador.efeitos
            if normalizar_rotulo(efeito.nome) == nome_alvo
            and efeito.origem.endswith(casa)
        ]
        if not removidos:
            continue
        jogador.efeitos = [efeito for efeito in jogador.efeitos if efeito not in removidos]
        afetados.append(jogador.nome)
    if afetados:
        partida.eventos.append(
            EventoPartida(
                tipo="fim_efeito",
                casa=casa,
                jogador=", ".join(afetados),
                descricao=f"Formação Muralha de Ogro encerrada: {motivo}.",
            )
        )
    return tuple(afetados)


def encerrar_hawkshead(
    partida: PartidaQuadribol,
    casa: str,
    motivo: str,
) -> tuple[str, ...]:
    afetados: list[str] = []
    nome_alvo = "formacao de ataque hawkshead (cabeca de falcao)"
    for jogador in partida.jogadores:
        removidos = [
            efeito
            for efeito in jogador.efeitos
            if normalizar_rotulo(efeito.nome) == nome_alvo
            and normalizar_rotulo(efeito.origem).endswith(normalizar_rotulo(casa))
        ]
        if not removidos:
            continue
        jogador.efeitos = [efeito for efeito in jogador.efeitos if efeito not in removidos]
        afetados.append(jogador.nome)
    if afetados:
        partida.eventos.append(
            EventoPartida(
                tipo="fim_efeito",
                casa=casa,
                jogador=", ".join(afetados),
                descricao=f"Formação Hawkshead encerrada: {motivo}.",
            )
        )
    return tuple(afetados)


def manobra_requer_finalizador(manobra: ManobraQuadribol) -> bool:
    return normalizar_rotulo(manobra.nome) in {
        *BONUS_ARREMESSO_MANOBRAS,
        "resgate em gangorra",
    }


def finalizadores_manobra(
    partida: PartidaQuadribol,
    coordenador: str,
) -> list[JogadorPartida]:
    jogador = encontrar_jogador_partida(partida, coordenador)
    return [
        item
        for item in partida.jogadores
        if item.casa == jogador.casa
        and item.posicao == "Artilheiro"
        and item.ativo
        and item.em_campo
    ]


def aplicar_beneficio_manobra(
    partida: PartidaQuadribol,
    manobra: ManobraQuadribol,
    coordenador: str,
    *,
    finalizador: str = "",
) -> str:
    """Transforma a parte mecanicamente definida do benefício em efeito persistido."""
    executor = encontrar_jogador_partida(partida, coordenador)
    nome_normalizado = normalizar_rotulo(manobra.nome)
    if nome_normalizado == "mergulho do falcao":
        if not finalizador:
            raise ValueError("Escolha o Artilheiro que realizará o arremesso final.")
        alvo = encontrar_jogador_partida(partida, finalizador)
        artilheiros = [
            item
            for item in partida.jogadores
            if item.casa == executor.casa
            and item.posicao == "Artilheiro"
            and item.ativo
            and item.em_campo
        ]
        if len(artilheiros) != 3 or alvo not in artilheiros:
            raise ValueError(
                "O Mergulho do Falcão exige os três Artilheiros ativos da equipe."
            )
        enganacoes = [_pericia_jogador(item, "Enganação") for item in artilheiros]
        media_enganacao = sum(enganacoes) / 3
        cd_percepcao = 10 + media_enganacao
        alvo.efeitos.extend(
            (
                EfeitoQuadribol(
                    nome=manobra.nome,
                    origem=f"Manobra: {manobra.nome}",
                    teste="Pontaria",
                    bonus=1,
                    turnos_restantes=0,
                    duracao_tipo="gatilho",
                    gatilho="próximo arremesso",
                    descricao="+1 no próximo arremesso final.",
                    contexto="gol",
                    consumir_ao_usar=True,
                ),
                EfeitoQuadribol(
                    nome=f"{manobra.nome} — Percepção",
                    origem=f"Manobra: {manobra.nome}",
                    teste="Percepção",
                    turnos_restantes=0,
                    cd_resistencia=cd_percepcao,
                    duracao_tipo="gatilho",
                    gatilho="próximo arremesso",
                    descricao=(
                        f"O Goleiro realiza um teste de Percepção contra CD {cd_percepcao:g}; "
                        "em falha, perde a defesa."
                    ),
                    contexto="mergulho_falcao",
                    consumir_ao_usar=True,
                ),
            )
        )
        if partida.posse_goles:
            portador = encontrar_jogador_partida(partida, partida.posse_goles)
            if portador.casa != executor.casa:
                raise ValueError("A equipe precisa estar com a Goles para executar esta manobra.")
            partida.posse_goles = alvo.nome
        detalhes = ", ".join(
            f"{jogador.nome} {valor:+d}"
            for jogador, valor in zip(artilheiros, enganacoes)
        )
        texto = (
            f"{alvo.nome} recebeu +1 no arremesso. O Goleiro enfrentará Percepção "
            f"CD {cd_percepcao:g}, calculada pela média de Enganação: {detalhes}."
        )
    elif nome_normalizado == "formacao muralha de ogro":
        apanhadores = [
            item
            for item in partida.jogadores
            if item.casa == executor.casa
            and item.posicao == "Apanhador"
            and item.ativo
            and item.em_campo
        ]
        batedores = [
            item
            for item in partida.jogadores
            if item.casa == executor.casa
            and item.posicao == "Batedor"
            and item.ativo
            and item.em_campo
        ]
        artilheiros = [
            item
            for item in partida.jogadores
            if item.casa == executor.casa
            and item.posicao == "Artilheiro"
            and item.ativo
            and item.em_campo
        ]
        if len(apanhadores) != 1 or len(batedores) != 2 or len(artilheiros) != 3:
            raise ValueError(
                "A Muralha de Ogro exige o Apanhador, os dois Batedores e os três "
                "Artilheiros ativos da equipe."
            )
        encerrar_muralha_ogro(partida, executor.casa, "uma nova formação foi iniciada")
        origem_formacao = f"Manobra sustentada: {executor.casa}"
        protegido = apanhadores[0]
        for adversario in partida.jogadores:
            if (
                adversario.casa != executor.casa
                and adversario.posicao == "Batedor"
                and adversario.ativo
                and adversario.em_campo
            ):
                adversario.efeitos.append(
                    EfeitoQuadribol(
                        nome=manobra.nome,
                        origem=origem_formacao,
                        teste="Pontaria",
                        bonus=-4,
                        turnos_restantes=0,
                        duracao_tipo="gatilho",
                        gatilho="fim da sustentação da formação",
                        rival=protegido.nome,
                        descricao=f"-4 para acertar {protegido.nome} com Balaços.",
                        contexto="balaco_ataque",
                    )
                )
        for artilheiro in artilheiros:
            artilheiro.efeitos.append(
                EfeitoQuadribol(
                    nome=manobra.nome,
                    origem=origem_formacao,
                    teste="Pontaria",
                    bonus=-2,
                    turnos_restantes=0,
                    duracao_tipo="gatilho",
                    gatilho="fim da sustentação da formação",
                    descricao="-2 em tentativas de pontuar enquanto sustenta a formação.",
                    contexto="gol",
                )
            )
        for participante in [protegido, *batedores]:
            participante.efeitos.append(
                EfeitoQuadribol(
                    nome=manobra.nome,
                    origem=origem_formacao,
                    turnos_restantes=0,
                    duracao_tipo="gatilho",
                    gatilho="fim da sustentação da formação",
                    descricao="Participa da sustentação da Muralha de Ogro.",
                    contexto="muralha_ogro",
                )
            )
        texto = (
            f"Muralha de Ogro ativa protegendo {protegido.nome}; permanece até os "
            "participantes deixarem de sustentá-la."
        )
    elif nome_normalizado == "a danca das serpentes":
        if not finalizador:
            raise ValueError("Escolha o Artilheiro que realizará o arremesso final.")
        alvo = encontrar_jogador_partida(partida, finalizador)
        if (
            alvo.casa != executor.casa
            or alvo.posicao != "Artilheiro"
            or not alvo.ativo
            or not alvo.em_campo
        ):
            raise ValueError("O finalizador precisa ser um Artilheiro ativo da equipe da manobra.")
        if partida.posse_goles:
            portador = encontrar_jogador_partida(partida, partida.posse_goles)
            if portador.casa != executor.casa:
                raise ValueError("A equipe precisa estar com a Goles para concluir a manobra.")
            partida.posse_goles = alvo.nome
        participantes = [
            item
            for item in partida.jogadores
            if item.casa == executor.casa and item.ativo and item.em_campo
        ]
        for participante in participantes:
            participante.efeitos = [
                efeito
                for efeito in participante.efeitos
                if not (
                    normalizar_rotulo(efeito.nome) == nome_normalizado
                    and normalizar_rotulo(efeito.contexto) == "balaco_defesa"
                )
            ]
            participante.efeitos.append(
                EfeitoQuadribol(
                    nome=manobra.nome,
                    origem=f"Manobra: {manobra.nome}",
                    teste="Reflexo",
                    bonus=3,
                    turnos_restantes=0,
                    duracao_tipo="ciclo",
                    rodada_inicial=partida.rodada,
                    gatilho=executor.nome,
                    descricao="+3 em esquivas durante uma volta completa da iniciativa.",
                    contexto="balaco_defesa",
                )
            )
        alvo.efeitos = [
            efeito
            for efeito in alvo.efeitos
            if not (
                normalizar_rotulo(efeito.nome) == nome_normalizado
                and normalizar_rotulo(efeito.contexto) == "gol"
            )
        ]
        alvo.efeitos.append(
            EfeitoQuadribol(
                nome=manobra.nome,
                origem=f"Manobra: {manobra.nome}",
                teste="Pontaria",
                bonus=1,
                turnos_restantes=0,
                duracao_tipo="ciclo",
                rodada_inicial=partida.rodada,
                gatilho=executor.nome,
                descricao="+1 no arremesso final durante uma volta completa da iniciativa.",
                contexto="gol",
            )
        )
        texto = (
            f"A equipe recebeu +3 em esquivas e {alvo.nome} recebeu +1 nos arremessos "
            f"até o turno retornar a {executor.nome}."
        )
    elif nome_normalizado == "zona de fogo":
        participantes = [
            item
            for item in partida.jogadores
            if item.casa == executor.casa
            and item.posicao == "Batedor"
            and item.ativo
            and item.em_campo
        ]
        if len(participantes) != 2:
            raise ValueError("Zona de Fogo exige os dois Batedores ativos da equipe.")
        encerrar_zona_fogo(partida, executor.casa, "uma nova formação foi iniciada")
        for participante in participantes:
            participante.efeitos.append(
                EfeitoQuadribol(
                    nome=manobra.nome,
                    origem=f"Manobra: {manobra.nome}",
                    turnos_restantes=0,
                    duracao_tipo="gatilho",
                    gatilho="interceptação inimiga ou fim da sustentação",
                    descricao=(
                        "Participa da Zona de Fogo; ataques usam a média de Pontaria dos "
                        "dois Batedores e impõem -2 em Reflexo."
                    ),
                    contexto="zona_fogo",
                )
            )
        texto = (
            "Zona de Fogo ativa com "
            + " e ".join(item.nome for item in participantes)
            + "; permanece até ser interrompida ou deixar de ser sustentada."
        )
    elif nome_normalizado == "formacao de ataque hawkshead (cabeca de falcao)":
        artilheiros = [
            item
            for item in partida.jogadores
            if item.casa == executor.casa
            and item.posicao == "Artilheiro"
            and item.ativo
            and item.em_campo
        ]
        if len(artilheiros) != 3:
            raise ValueError("A Formação Hawkshead exige os três Artilheiros ativos da equipe.")
        encerrar_hawkshead(partida, executor.casa, "uma nova formação foi iniciada")
        origem_formacao = f"Manobra sustentada: {executor.casa}"
        for artilheiro in artilheiros:
            artilheiro.efeitos.append(
                EfeitoQuadribol(
                    nome=manobra.nome,
                    origem=origem_formacao,
                    teste="Pontaria",
                    bonus=1,
                    turnos_restantes=0,
                    duracao_tipo="gatilho",
                    gatilho="fim da sustentação da formação",
                    descricao="+1 em Pontaria nos passes entre os Artilheiros.",
                    contexto="passe",
                )
            )
        for adversario in partida.jogadores:
            if (
                adversario.casa != executor.casa
                and adversario.posicao == "Artilheiro"
                and adversario.ativo
                and adversario.em_campo
            ):
                adversario.efeitos.append(
                    EfeitoQuadribol(
                        nome=manobra.nome,
                        origem=origem_formacao,
                        teste="Reflexo",
                        bonus=-2,
                        turnos_restantes=0,
                        duracao_tipo="gatilho",
                        gatilho="fim da sustentação da formação",
                        descricao="-2 em Reflexo ao tentar interceptar os passes da formação.",
                        contexto="interceptacao_passe",
                    )
                )
        texto = (
            "Formação Hawkshead ativa: os três Artilheiros recebem +1 nos passes e "
            "os Artilheiros adversários sofrem -2 ao tentar interceptá-los."
        )
    elif nome_normalizado == "resgate em gangorra":
        if not finalizador:
            raise ValueError("Escolha o Artilheiro que realizará o bote.")
        artilheiros = [
            item
            for item in partida.jogadores
            if item.casa == executor.casa
            and item.posicao == "Artilheiro"
            and item.ativo
            and item.em_campo
        ]
        alvo = encontrar_jogador_partida(partida, finalizador)
        if len(artilheiros) != 3 or alvo not in artilheiros:
            raise ValueError("O Resgate em Gangorra exige os três Artilheiros ativos da equipe.")
        if not partida.posse_goles:
            raise ValueError("Nenhum adversário está com a Goles.")
        portador = encontrar_jogador_partida(partida, partida.posse_goles)
        if portador.casa == executor.casa:
            raise ValueError("O Resgate em Gangorra exige que um adversário esteja com a Goles.")
        partida.posse_goles = alvo.nome
        partida.bonus_passes_gol[portador.casa] = 0
        texto = f"{alvo.nome} realizou o bote e recuperou a Goles para {executor.casa}."
    elif nome_normalizado in BONUS_ARREMESSO_MANOBRAS:
        if not finalizador:
            raise ValueError("Escolha o Artilheiro que realizará o arremesso final.")
        alvo = encontrar_jogador_partida(partida, finalizador)
        if (
            alvo.casa != executor.casa
            or alvo.posicao != "Artilheiro"
            or not alvo.ativo
            or not alvo.em_campo
        ):
            raise ValueError("O finalizador precisa ser um Artilheiro ativo da equipe da manobra.")
        bonus = BONUS_ARREMESSO_MANOBRAS[nome_normalizado]
        if partida.posse_goles:
            portador = encontrar_jogador_partida(partida, partida.posse_goles)
            if portador.casa != executor.casa:
                raise ValueError("A equipe precisa estar com a Goles para executar esta manobra.")
            partida.posse_goles = alvo.nome
        alvo.efeitos.append(
            EfeitoQuadribol(
                nome=manobra.nome,
                origem=f"Manobra: {manobra.nome}",
                teste="Pontaria",
                bonus=bonus,
                turnos_restantes=0,
                duracao_tipo="gatilho",
                gatilho="próximo arremesso",
                descricao=f"{bonus:+d} no próximo arremesso final.",
                contexto="gol",
                consumir_ao_usar=True,
            )
        )
        texto = f"{alvo.nome} recebeu {bonus:+d} no próximo arremesso."
    elif nome_normalizado == "pancada de fingbourg":
        goleiro = next(
            (
                item
                for item in partida.jogadores
                if item.casa != executor.casa
                and item.posicao == "Goleiro"
                and item.ativo
                and item.em_campo
            ),
            None,
        )
        if goleiro is None:
            raise ValueError("A equipe adversária não possui Goleiro ativo.")
        goleiro.efeitos.append(
            EfeitoQuadribol(
                nome=manobra.nome,
                origem=f"Manobra: {manobra.nome}",
                teste="Reflexo",
                bonus=-6,
                turnos_restantes=0,
                duracao_tipo="gatilho",
                gatilho=f"próxima defesa contra {executor.nome}",
                rival=executor.nome,
                descricao="-6 na defesa contra o arremesso correspondente.",
                contexto="gol",
                consumir_ao_usar=True,
            )
        )
        texto = f"{goleiro.nome} sofrerá -6 na próxima defesa contra {executor.nome}."
    elif nome_normalizado == "slip groth roll (desvio da preguica)":
        executor.efeitos.append(
            EfeitoQuadribol(
                nome=manobra.nome,
                origem=f"Manobra: {manobra.nome}",
                teste="Reflexo",
                bonus=2,
                turnos_restantes=0,
                duracao_tipo="gatilho",
                gatilho="próxima esquiva contra Balaço",
                descricao="+2 na próxima esquiva contra um Balaço.",
                contexto="balaco_defesa",
                consumir_ao_usar=True,
            )
        )
        texto = f"{executor.nome} recebeu +2 na próxima esquiva contra um Balaço."
    elif nome_normalizado == "rebate duplo":
        texto = "O benefício é resolvido pelo tipo Rebate Duplo dentro de Acertar Alvo."
    else:
        texto = (
            "A biblioteca ainda não define todos os valores ou não possui a ação necessária "
            "para automatizar este benefício; nenhum modificador foi inventado."
        )
    partida.eventos.append(
        EventoPartida(
            tipo="beneficio_manobra",
            casa=executor.casa,
            jogador=executor.nome,
            alvo=finalizador,
            descricao=f"{manobra.nome}: {texto}",
        )
    )
    return texto


@dataclass(frozen=True)
class FaltaQuadribol:
    nome: str
    posicoes: tuple[str, ...]
    cartao: str
    consequencia: str
    descricao: str


def carregar_faltas(caminho: Path | None = None) -> list[FaltaQuadribol]:
    origem = caminho or ARQUIVO_FALTAS
    if not origem.is_file():
        return []
    blocos = re.split(r"(?m)^##\s+", origem.read_text(encoding="utf-8-sig"))[1:]
    resultado: list[FaltaQuadribol] = []
    for bloco in blocos:
        linhas = bloco.splitlines()
        nome = linhas[0].strip()
        corpo = "\n".join(linhas[1:]).strip()
        entrada = interpretar_markdown(f"# {nome}\n\n{corpo}\n")
        campos = {
            normalizar_rotulo(rotulo): valor.strip()
            for rotulo, valor in entrada.campos.items()
        }
        posicoes = tuple(
            item.strip()
            for item in campos.get(normalizar_rotulo("Posições"), "").split(",")
            if item.strip()
        )
        cartao = campos.get(normalizar_rotulo("Cartão"), "").strip()
        consequencia = campos.get(normalizar_rotulo("Consequência"), "").strip()
        if not posicoes or cartao not in {"Nenhum", "Amarelo", "Vermelho"} or not consequencia:
            continue
        resultado.append(
            FaltaQuadribol(
                nome=nome,
                posicoes=posicoes,
                cartao=cartao,
                consequencia=consequencia,
                descricao=entrada.descricao.strip(),
            )
        )
    return resultado


def carregar_manobras(caminho: Path | None = None) -> list[ManobraQuadribol]:
    origem = caminho or ARQUIVO_MANOBRAS
    if not origem.is_file():
        return []
    blocos = re.split(r"(?m)^##\s+", origem.read_text(encoding="utf-8-sig"))[1:]
    resultado: list[ManobraQuadribol] = []
    for bloco in blocos:
        linhas = bloco.splitlines()
        nome = linhas[0].strip()
        corpo = "\n".join(linhas[1:]).strip()
        entrada = interpretar_markdown(f"# {nome}\n\n{corpo}\n")
        campos = {
            normalizar_rotulo(rotulo): valor.strip()
            for rotulo, valor in entrada.campos.items()
        }
        try:
            cd_texto = campos.get(normalizar_rotulo("CD"), "").strip()
            cd = 0 if cd_texto in {"--", "—"} else int(cd_texto)
            requisito = _inteiro(campos, "Requisito de Quadribol")
        except (TypeError, ValueError):
            continue
        posicoes = tuple(
            item.strip()
            for item in campos.get(normalizar_rotulo("Posições"), "").split(",")
            if item.strip()
        )
        resultado.append(
            ManobraQuadribol(
                nome=nome,
                cd=cd,
                requisito_quadribol=requisito,
                posicoes=posicoes,
                participantes=campos.get(normalizar_rotulo("Participantes"), ""),
                descricao=entrada.descricao.strip(),
                execucao=campos.get(normalizar_rotulo("Execução"), ""),
                beneficio=campos.get(normalizar_rotulo("Benefício"), ""),
            )
        )
    return resultado


def validar_nova_manobra(
    manobra: ManobraQuadribol,
    *,
    caminho: Path | None = None,
) -> ManobraQuadribol:
    """Normaliza e valida uma ficha antes de acrescentá-la à biblioteca."""
    nome = manobra.nome.strip()
    descricao = manobra.descricao.strip()
    participantes = manobra.participantes.strip()
    execucao = manobra.execucao.strip()
    beneficio = manobra.beneficio.strip()
    posicoes = tuple(dict.fromkeys(item.strip() for item in manobra.posicoes if item.strip()))
    if not 2 <= len(nome) <= 100 or "\n" in nome or nome.startswith("#"):
        raise ValueError("O nome da manobra deve possuir entre 2 e 100 caracteres.")
    if manobra.cd < 0 or manobra.cd > 99:
        raise ValueError("A CD deve estar entre 0 e 99; use 0 para execução automática.")
    if manobra.requisito_quadribol not in range(1, 6):
        raise ValueError("O requisito de Quadribol deve estar entre +1 e +5.")
    if not posicoes or any(item not in POSICOES for item in posicoes):
        raise ValueError("Escolha ao menos uma posição válida para a manobra.")
    campos = {
        "descrição": descricao,
        "participantes": participantes,
        "execução": execucao,
        "benefício": beneficio,
    }
    ausentes = [rotulo for rotulo, valor in campos.items() if not valor]
    if ausentes:
        raise ValueError("Preencha " + ", ".join(ausentes) + ".")
    if any("\n## " in f"\n{valor}" for valor in campos.values()):
        raise ValueError("Os textos da manobra não podem criar outra seção com ##.")
    existentes = carregar_manobras(caminho)
    if any(normalizar_rotulo(item.nome) == normalizar_rotulo(nome) for item in existentes):
        raise ValueError(f"Já existe uma manobra chamada {nome}.")
    return ManobraQuadribol(
        nome=nome,
        cd=manobra.cd,
        requisito_quadribol=manobra.requisito_quadribol,
        posicoes=posicoes,
        participantes=participantes,
        descricao=descricao,
        execucao=execucao,
        beneficio=beneficio,
    )


def adicionar_manobra_biblioteca(
    manobra: ManobraQuadribol,
    *,
    caminho: Path | None = None,
) -> ManobraQuadribol:
    """Acrescenta atomicamente uma manobra validada ao Markdown oficial."""
    destino = caminho or ARQUIVO_MANOBRAS
    validada = validar_nova_manobra(manobra, caminho=destino)
    bloco = (
        f"## {validada.nome}\n\n"
        f"CD:\n{validada.cd}\n\n"
        f"Requisito de Quadribol:\n{validada.requisito_quadribol}\n\n"
        f"Posições:\n{', '.join(validada.posicoes)}\n\n"
        f"Participantes:\n{validada.participantes}\n\n"
        f"Descrição:\n{validada.descricao}\n\n"
        f"Execução:\n{validada.execucao}\n\n"
        f"Benefício:\n{validada.beneficio}\n"
    )
    texto_atual = destino.read_text(encoding="utf-8-sig") if destino.is_file() else "# Manobras de Quadribol\n"
    temporario = destino.with_name(f".{destino.name}.tmp")
    temporario.write_text(texto_atual.rstrip() + "\n\n" + bloco, encoding="utf-8")
    temporario.replace(destino)
    return validada


@dataclass
class EfeitoQuadribol:
    nome: str
    origem: str
    teste: str = ""
    bonus: int = 0
    turnos_restantes: int = 1
    cd_recuperacao: int = 0
    categoria: str = ""
    intensidade: str = ""
    cd_resistencia: int = 0
    dado_modificador: str = ""
    duracao_tipo: str = "turnos"
    rodada_final: int = 0
    rodada_inicial: int = 0
    gatilho: str = ""
    rival: str = ""
    descricao: str = ""
    contexto: str = ""
    consumir_ao_usar: bool = False


@dataclass(frozen=True)
class CondicaoQuadribol:
    nome: str
    categoria: str
    origem: str
    descricao: str
    exige_intensidade: bool = False
    teste_resistencia: str = ""
    dado_modificador: str = ""
    duracao_tipo: str = "partida"
    rodadas: int = 0
    exige_gatilho: bool = False
    multiplos_alvos: bool = False
    exige_rival: bool = False


CONDICOES_QUADRIBOL = (
    CondicaoQuadribol(
        "Sob Pressão",
        "Estado emocional",
        "Efeito narrativo",
        "Antes de cada ação com rolagem, realiza um teste de Vontade. Em falha, sofre -1d4 naquela ação. Permanece até ser removido.",
        exige_intensidade=True,
        teste_resistencia="Vontade",
        dado_modificador="-1d4",
    ),
    CondicaoQuadribol(
        "Problemas Pessoais",
        "Estado emocional",
        "Efeito narrativo",
        "Em ações que exigem concentração ou decisão rápida, realiza um teste de Vontade. Em falha, sofre -1d4 naquela ação. Permanece até ser removido.",
        exige_intensidade=True,
        teste_resistencia="Vontade",
        dado_modificador="-1d4",
    ),
    CondicaoQuadribol(
        "Rivalidade",
        "Estado emocional",
        "Efeito narrativo",
        "Em confronto direto com o rival, realiza um teste de Vontade: sucesso concede +1d4 e falha causa -1d4 naquela ação.",
        exige_intensidade=True,
        teste_resistencia="Vontade",
        dado_modificador="±1d4",
        multiplos_alvos=True,
        exige_rival=True,
    ),
    CondicaoQuadribol(
        "Abalado",
        "Estado emocional",
        "Efeito narrativo",
        "Durante a próxima rodada, realiza um teste de Vontade antes de cada ação. Em falha, sofre -1d4 naquela ação.",
        exige_intensidade=True,
        teste_resistencia="Vontade",
        dado_modificador="-1d4",
        duracao_tipo="rodadas",
        rodadas=1,
    ),
    CondicaoQuadribol(
        "Confiante",
        "Estado emocional positivo",
        "Efeito narrativo",
        "+1d4 na primeira ação realizada durante a próxima rodada; é consumido após essa ação.",
        dado_modificador="+1d4",
        duracao_tipo="rodadas",
        rodadas=1,
    ),
    CondicaoQuadribol(
        "Motivado",
        "Estado emocional positivo",
        "Efeito narrativo",
        "+1 em todas as ações enquanto a motivação registrada existir.",
        dado_modificador="+1",
        duracao_tipo="gatilho",
        exige_gatilho=True,
    ),
    CondicaoQuadribol(
        "Em Sintonia",
        "Estado emocional positivo",
        "Efeito narrativo",
        "+1d4 na execução de manobras coletivas com pelo menos dois jogadores afetados; apenas um dado por manobra.",
        dado_modificador="+1d4",
        duracao_tipo="rodadas_1d4",
        multiplos_alvos=True,
    ),
    CondicaoQuadribol(
        "Determinado",
        "Estado emocional positivo",
        "Efeito narrativo",
        "Ignora temporariamente um efeito emocional negativo durante a próxima rodada.",
        duracao_tipo="rodadas",
        rodadas=1,
    ),
    CondicaoQuadribol(
        "Tempo Meteorológico",
        "Condição meteorológica",
        "Efeito narrativo",
        "Antes de cada ação, realiza um teste de Fortitude. Em falha, sofre -(1d4+1) naquela ação. Permanece durante a partida até ser removido.",
        exige_intensidade=True,
        teste_resistencia="Fortitude",
        dado_modificador="-(1d4+1)",
        multiplos_alvos=True,
    ),
)


def encontrar_condicao(nome: str) -> CondicaoQuadribol:
    alvo = normalizar_rotulo(nome)
    encontrada = next(
        (item for item in CONDICOES_QUADRIBOL if normalizar_rotulo(item.nome) == alvo),
        None,
    )
    if encontrada is None:
        raise ValueError("Condição de Quadribol não encontrada.")
    return encontrada


@dataclass
class JogadorPartida:
    nome: str
    casa: str
    posicao: str
    caminho_ficha: str
    vassoura: str
    bonus_vassoura: int
    vida_vassoura: int
    vida_vassoura_maxima: int
    iniciativa_dado: int
    iniciativa_bonus: int
    iniciativa_total: int
    quadribol: int
    voo: int
    fortitude: int
    modificador_forca: int
    teste_posicao: str
    bonus_teste_posicao: int
    prodigio: bool = False
    velocidade_vassoura: int = 0
    reflexo: int = 0
    situacao: str = "Titular"
    ativo: bool = True
    em_campo: bool = True
    expulso: bool = False
    cartoes_amarelos: int = 0
    perseguiu_pomo_no_turno: bool = False
    pomo_perseguido: str = ""
    efeitos: list[EfeitoQuadribol] = field(default_factory=list)
    bonus_pontaria_vassoura: int = 0
    dado_bonus_pontaria_vassoura: str = ""
    uso_bonus_pontaria: str = ""
    atletismo: int = 0
    atributo_atletismo: str = ""
    turnos_pulados: int = 0
    resultado_tempo_externo: int | None = None
    penalidade_tempo_preparada: int | None = None
    cd_tempo_preparada: int = 0
    fonte_tempo_preparada: str = ""

    @property
    def vassoura_quebrada(self) -> bool:
        return self.vida_vassoura <= 0


@dataclass
class EventoPartida:
    tipo: str
    descricao: str
    criado_em: str = field(default_factory=_agora)
    casa: str = ""
    jogador: str = ""
    valor: int = 0
    alvo: str = ""


@dataclass(frozen=True)
class ResultadoPomo:
    jogador: str
    pomo_lado: str
    dado: int
    bonus: int
    total: int
    progresso_anterior: int
    progresso_atual: int
    necessario: int
    velocidade_considerada: int
    usou_disparada: bool
    capturou: bool
    bonus_vassoura_situacional: int = 0
    rolagem_externa: bool = False
    fontes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultadoBalaco:
    atacante: str
    alvo: str
    dado_ataque: int
    total_ataque: int
    defensor: str
    dado_defesa: int
    total_defesa: int
    atingiu: bool
    dado_fortitude: int = 0
    total_fortitude: int = 0
    cd_fortitude: int = 0
    resistiu: bool = False
    progresso_perdido: int = 0
    bonus_vassoura_ataque: int = 0
    bonus_vassoura_defesa: int = 0
    dado_bonus_vassoura_ataque: int = 0
    dado_bonus_vassoura_defesa: int = 0
    dado_bonus_vassoura_reflexo: int = 0
    redirecionou: bool = False
    alvo_redirecionado: str = ""
    dado_reflexo_redirecionado: int = 0
    total_reflexo_redirecionado: int = 0
    atingiu_redirecionado: bool = False
    rolagem_externa_ataque: bool = False
    rolagem_externa_defesa: bool = False
    bonus_manobra_defesa: int = 0
    fontes_manobra_defesa: tuple[str, ...] = ()
    bonus_habilidade_defesa: int = 0
    fontes_habilidade_defesa: tuple[str, ...] = ()
    bonus_habilidade_fortitude: int = 0
    fontes_habilidade_fortitude: tuple[str, ...] = ()
    fontes_ataque: tuple[str, ...] = ()
    fontes_defesa: tuple[str, ...] = ()
    fontes_fortitude: tuple[str, ...] = ()
    fontes_reflexo_redirecionado: tuple[str, ...] = ()
    zona_fogo: bool = False
    zona_fogo_encerrada: bool = False
    posse_perdida_por: str = ""
    casa_nova_posse: str = ""


@dataclass(frozen=True)
class RegistroFalta:
    falta: FaltaQuadribol
    infrator: str
    casa_prejudicada: str
    cartao_aplicado: str
    reserva: str = ""


@dataclass(frozen=True)
class ResultadoPenalti:
    artilheiro: str
    goleiro: str
    dado_artilheiro: int
    total_artilheiro: int
    dado_goleiro: int
    total_goleiro: int
    gol: bool
    bonus_vassoura_artilheiro: int = 0
    dado_bonus_vassoura_artilheiro: int = 0
    dado_bonus_vassoura_goleiro: int = 0
    rolagem_externa_artilheiro: bool = False
    rolagem_externa_goleiro: bool = False
    fontes_artilheiro: tuple[str, ...] = ()
    fontes_goleiro: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultadoGol:
    artilheiro: str
    goleiro: str
    dado_artilheiro: int
    total_artilheiro: int
    dado_goleiro: int
    total_goleiro: int
    gol: bool
    bonus_vassoura_artilheiro: int = 0
    dado_bonus_vassoura_artilheiro: int = 0
    dado_bonus_vassoura_goleiro: int = 0
    rolagem_externa_artilheiro: bool = False
    rolagem_externa_goleiro: bool = False
    bonus_manobra_artilheiro: int = 0
    bonus_passes_artilheiro: int = 0
    bonus_manobra_goleiro: int = 0
    fontes_manobra_artilheiro: tuple[str, ...] = ()
    fontes_manobra_goleiro: tuple[str, ...] = ()
    bonus_habilidade_goleiro: int = 0
    fontes_habilidade_goleiro: tuple[str, ...] = ()
    fontes_artilheiro: tuple[str, ...] = ()
    fontes_goleiro: tuple[str, ...] = ()
    mergulho_falcao: bool = False
    dado_percepcao: int = 0
    total_percepcao: int = 0
    cd_percepcao: float = 0
    passou_percepcao: bool = True
    fontes_percepcao: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultadoPosse:
    acao: str
    atacante: str
    defensor: str
    destinatario: str
    dado_atacante: int
    total_atacante: int
    dado_defensor: int
    total_defensor: int
    novo_portador: str
    sucesso: bool
    fontes_atacante: tuple[str, ...] = ()
    fontes_defensor: tuple[str, ...] = ()
    rolagem_externa_atacante: bool = False
    rolagem_externa_defensor: bool = False
    bonus_passes_acumulado: int = 0
    sequencia_passes_interrompida: bool = False


@dataclass(frozen=True)
class ResultadoHabilidade:
    habilidade: str
    executor: str
    alvo: str
    dado: int = 0
    bonus: int = 0
    total: int = 0
    cd: int = 0
    sucesso: bool = True
    efeito: str = ""
    rolagem_externa: bool = False


@dataclass(frozen=True)
class ResultadoFintaWronski:
    executor: str
    alvo: str
    dado_voo: int
    total_voo: int
    evitou_colisao: bool
    dado_fortitude: int = 0
    total_fortitude: int = 0
    resistiu_impacto: bool = True
    dado_dano: int = 0
    dano_concussivo: int = 0
    pv_vassoura_perdido: int = 0
    fontes_voo: tuple[str, ...] = ()
    fontes_fortitude: tuple[str, ...] = ()


@dataclass
class PartidaQuadribol:
    identificador: str
    jogo: str
    casa_1: str
    casa_2: str
    moderador_id: int
    criado_em: str
    jogadores: list[JogadorPartida]
    gols: dict[str, int]
    tipo_partida: str = "Partida Oficial"
    pomo: str = ""
    estado: str = "ativa"
    indice_turno: int = 0
    rodada: int = 1
    canal_id: int = 0
    mensagem_id: int = 0
    taca_aplicada: bool = False
    progresso_pomo: dict[str, int] = field(default_factory=dict)
    pomos: dict[str, str] = field(default_factory=dict)
    progresso_pomos: dict[str, dict[str, int]] = field(default_factory=dict)
    disparadas_pomo: dict[str, list[str]] = field(default_factory=dict)
    tempo: int = 1
    rodada_tempo: int = 1
    rodadas_surgimento_pomo: dict[str, int] = field(default_factory=dict)
    pomos_anunciados: list[str] = field(default_factory=list)
    vencedor_forcado: str = ""
    penalti_casa: str = ""
    penalti_motivo: str = ""
    penalti_infrator: str = ""
    eventos: list[EventoPartida] = field(default_factory=list)
    acoes_preparadas: list[str] = field(default_factory=list)
    executando_acoes_preparadas: bool = False
    posse_goles: str = ""
    bonus_passes_gol: dict[str, int] = field(default_factory=dict)
    reposicao_goles_casa: str = ""
    reposicao_goles_jogador: str = ""

    def casas(self) -> tuple[str, str]:
        return self.casa_1, self.casa_2

    def placar(self, casa: str) -> int:
        return self.gols.get(casa, 0) * 10 + self.capturas_pomo(casa) * 150

    def capturas_pomo(self, casa: str) -> int:
        if self.pomos:
            return sum(capturou == casa for capturou in self.pomos.values())
        return 1 if self.pomo == casa else 0

    def pomos_ativos(self) -> tuple[str, ...]:
        if self.estado != "ativa":
            return ()
        lado = self.casa_1 if self.tempo == 1 else self.casa_2
        rodada_surgimento = self.rodadas_surgimento_pomo.get(str(self.tempo), 0)
        if (
            lado not in self.pomos
            and rodada_surgimento
            and self.rodada_tempo >= rodada_surgimento
        ):
            return (lado,)
        return ()

    def vencedor(self) -> str:
        if self.vencedor_forcado:
            return self.vencedor_forcado
        placares = {casa: self.placar(casa) for casa in self.casas()}
        if placares[self.casa_1] == placares[self.casa_2]:
            return ""
        return max(placares, key=placares.get)

    def pontos_taca(self, casa: str) -> int:
        return (
            self.gols.get(casa, 0)
            + self.capturas_pomo(casa) * 10
            + (25 if self.vencedor() == casa else 0)
        )

    def jogador_atual(self) -> JogadorPartida | None:
        if self.executando_acoes_preparadas:
            aptos = {
                jogador.nome: jogador
                for jogador in self.jogadores_em_iniciativa()
            }
            return next(
                (aptos[nome] for nome in self.acoes_preparadas if nome in aptos),
                None,
            )
        jogadores = self.jogadores_em_iniciativa()
        if not jogadores:
            return None
        return jogadores[self.indice_turno % len(jogadores)]

    def jogadores_em_iniciativa(self) -> list[JogadorPartida]:
        """Jogadores que recebem turno; Goleiros atuam apenas por reação."""
        return [
            jogador
            for jogador in self.jogadores
            if jogador.em_campo
            and jogador.ativo
            and jogador.posicao != "Goleiro"
        ]

    def markdown(self) -> str:
        dados = json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))
        return f"# Partida de Quadribol — {self.jogo}\n\nDados:\n- {dados}\n"


def sincronizar_vassouras_partida(
    partida: PartidaQuadribol,
    *,
    pasta_vassouras: Path | None = None,
) -> bool:
    """Atualiza snapshots de vassouras usando o catálogo sem apagar dano sofrido."""
    alterou = False
    catalogo = {
        normalizar_rotulo(modelo.nome): modelo
        for modelo in listar_vassouras(pasta=pasta_vassouras)
    }
    for jogador in partida.jogadores:
        modelo = catalogo.get(normalizar_rotulo(jogador.vassoura))
        if modelo is None:
            continue

        estado_anterior = (
            jogador.vassoura,
            jogador.bonus_vassoura,
            jogador.vida_vassoura,
            jogador.vida_vassoura_maxima,
            jogador.velocidade_vassoura,
            jogador.voo,
            jogador.reflexo,
            jogador.fortitude,
            jogador.bonus_teste_posicao,
            jogador.bonus_pontaria_vassoura,
            jogador.dado_bonus_pontaria_vassoura,
            jogador.uso_bonus_pontaria,
        )
        bonus_voo_anterior = jogador.bonus_vassoura
        delta_voo = modelo.bonus_voo - bonus_voo_anterior
        # Reflexo e Fortitude persistem como totais. Para evitar depender de
        # dados antigos sem a origem do bônus, a ficha atual é relida quando
        # estiver disponível; o fallback mantém os totais existentes.
        try:
            ficha = FichaPersonagem.carregar(Path(jogador.caminho_ficha))
        except (OSError, ValueError):
            ficha = None

        vida_anterior = jogador.vida_vassoura_maxima
        vida_atual = jogador.vida_vassoura
        dano_sofrido = max(0, vida_anterior - vida_atual)

        jogador.vassoura = modelo.nome
        jogador.bonus_vassoura = modelo.bonus_voo
        jogador.vida_vassoura_maxima = modelo.vida_maxima
        jogador.vida_vassoura = (
            0
            if vida_atual <= 0
            else max(0, min(modelo.vida_maxima, modelo.vida_maxima - dano_sofrido))
        )
        if jogador.vassoura_quebrada:
            jogador.ativo = False
        jogador.velocidade_vassoura = velocidade_vassoura(modelo)
        jogador.bonus_pontaria_vassoura = modelo.bonus_pontaria
        jogador.dado_bonus_pontaria_vassoura = modelo.dado_bonus_pontaria
        jogador.uso_bonus_pontaria = modelo.uso_bonus_pontaria

        if ficha is not None:
            jogador.voo = ficha.aptidoes.get("Vôo", 0) + modelo.bonus_voo
            jogador.reflexo = total_pericia(ficha, "Reflexo") + modelo.bonus_reflexo
            jogador.fortitude = total_pericia(ficha, "Fortitude") + modelo.bonus_fortitude
            _, jogador.bonus_teste_posicao = bonus_posicao(
                ficha, jogador.posicao, modelo
            )
            atletismos = bonus_pericia(
                "Atletismo", ficha.pericias.get("Atletismo", 0), ficha.atributos
            )
            indice_atletismo = max(range(len(atletismos)), key=atletismos.__getitem__)
            jogador.atletismo = atletismos[indice_atletismo]
            jogador.atributo_atletismo = ("Força", "Destreza")[indice_atletismo]
        elif jogador.teste_posicao == "Vôo":
            jogador.voo += delta_voo
            jogador.bonus_teste_posicao += delta_voo

        estado_atual = (
            jogador.vassoura,
            jogador.bonus_vassoura,
            jogador.vida_vassoura,
            jogador.vida_vassoura_maxima,
            jogador.velocidade_vassoura,
            jogador.voo,
            jogador.reflexo,
            jogador.fortitude,
            jogador.bonus_teste_posicao,
            jogador.bonus_pontaria_vassoura,
            jogador.dado_bonus_pontaria_vassoura,
            jogador.uso_bonus_pontaria,
        )
        alterou = alterou or estado_anterior != estado_atual
    return alterou


def jogador_partida_de_ficha(
    referencia: ReferenciaFicha,
    vassoura: Vassoura,
    *,
    gerador: random.Random,
) -> JogadorPartida:
    ficha = FichaPersonagem.carregar(referencia.caminho)
    posicao = obter_informacao(ficha, "Jogador de Quadribol")
    if posicao not in POSICOES:
        raise ValueError(f"{ficha.nome} não possui uma posição de Quadribol válida.")
    situacao = obter_informacao(ficha, "Situação no time") or "Titular"
    if situacao not in SITUACOES_TIME:
        raise ValueError(f"{ficha.nome} não possui uma situação válida no time.")
    teste, bonus_teste = bonus_posicao(ficha, posicao, vassoura)
    iniciativa = total_pericia(ficha, "Iniciativa")
    if _habilidade_ativa(ficha, "Valente"):
        iniciativa += 2
    if any(
        "soldado" in normalizar_rotulo(efeito.get("nome", ""))
        and "iniciativa" in normalizar_rotulo(efeito.get("efeito", ""))
        for efeito in ficha.efeitos_habilidades_ativos
    ):
        iniciativa += 2
    atletismos = bonus_pericia(
        "Atletismo", ficha.pericias.get("Atletismo", 0), ficha.atributos
    )
    indice_atletismo = max(range(len(atletismos)), key=atletismos.__getitem__)
    atributo_atletismo = ("Força", "Destreza")[indice_atletismo]
    dado = 0 if posicao == "Goleiro" else gerador.randint(1, 20)
    return JogadorPartida(
        nome=ficha.nome,
        casa=ficha.casa,
        posicao=posicao,
        caminho_ficha=str(referencia.caminho),
        vassoura=vassoura.nome,
        bonus_vassoura=vassoura.bonus_voo,
        vida_vassoura=vassoura.vida_maxima,
        vida_vassoura_maxima=vassoura.vida_maxima,
        iniciativa_dado=dado,
        iniciativa_bonus=iniciativa,
        iniciativa_total=0 if posicao == "Goleiro" else dado + iniciativa,
        quadribol=ficha.aptidoes.get("Quadribol", 0),
        voo=ficha.aptidoes.get("Vôo", 0) + vassoura.bonus_voo,
        fortitude=total_pericia(ficha, "Fortitude") + vassoura.bonus_fortitude,
        modificador_forca=modificador(ficha.atributos["Força"]),
        teste_posicao=teste,
        bonus_teste_posicao=bonus_teste,
        prodigio=possui_prodigio(ficha),
        velocidade_vassoura=velocidade_vassoura(vassoura),
        reflexo=total_pericia(ficha, "Reflexo") + vassoura.bonus_reflexo,
        situacao=situacao,
        em_campo=situacao == "Titular",
        bonus_pontaria_vassoura=vassoura.bonus_pontaria,
        dado_bonus_pontaria_vassoura=vassoura.dado_bonus_pontaria,
        uso_bonus_pontaria=vassoura.uso_bonus_pontaria,
        atletismo=atletismos[indice_atletismo],
        atributo_atletismo=atributo_atletismo,
    )


def jogadores_configurados_da_casa(
    casa: str,
    *,
    pasta_vassouras: Path | None = None,
    gerador: random.Random | None = None,
) -> list[JogadorPartida]:
    if casa not in CASAS:
        raise ValueError("Casa inválida.")
    sorteio = gerador or random.SystemRandom()
    jogadores: list[JogadorPartida] = []
    catalogo = {
        normalizar_rotulo(modelo.nome): modelo
        for modelo in listar_vassouras(pasta=pasta_vassouras)
    }
    for referencia in listar_fichas_elegiveis():
        if casa_da_referencia(referencia) != casa:
            continue
        ficha = FichaPersonagem.carregar(referencia.caminho)
        posicao = obter_informacao(ficha, "Jogador de Quadribol")
        if not posicao:
            continue
        modelo = modelo_vassoura_da_descricao(obter_vassoura_ficha(ficha))
        vassoura = catalogo.get(normalizar_rotulo(modelo))
        if vassoura is None:
            raise ValueError(f"A vassoura de {ficha.nome} não existe no catálogo.")
        jogadores.append(jogador_partida_de_ficha(referencia, vassoura, gerador=sorteio))
    return jogadores


def jogadores_configurados_do_time(
    time: TimeAmador,
    *,
    pasta_vassouras: Path | None = None,
    gerador: random.Random | None = None,
) -> list[JogadorPartida]:
    sorteio = gerador or random.SystemRandom()
    catalogo = {normalizar_rotulo(item.nome): item for item in listar_vassouras(pasta=pasta_vassouras)}
    jogadores: list[JogadorPartida] = []
    for nome, (posicao, modelo_nome) in time.jogadores.items():
        referencia = encontrar_ficha_elegivel(nome)
        if referencia is None:
            raise ValueError(f"A ficha de {nome} não foi encontrada.")
        modelo_nome = modelo_nome or modelo_vassoura_da_descricao(obter_vassoura_ficha(FichaPersonagem.carregar(referencia.caminho)))
        modelo = catalogo.get(normalizar_rotulo(modelo_nome))
        if modelo is None:
            raise ValueError(f"A vassoura de {nome} não existe no catálogo.")
        jogador = jogador_partida_de_ficha(referencia, modelo, gerador=sorteio)
        jogador.casa = time.nome
        jogador.posicao = posicao
        jogador.em_campo = True
        jogadores.append(jogador)
    return jogadores


def validar_formacao(jogadores: Iterable[JogadorPartida], casa: str) -> None:
    contagem = {posicao: 0 for posicao in POSICOES}
    for jogador in jogadores:
        if jogador.casa == casa and jogador.em_campo and jogador.posicao in contagem:
            contagem[jogador.posicao] += 1
    erros = [
        f"{posicao}: {contagem[posicao]}/{quantidade}"
        for posicao, quantidade in FORMACAO_PADRAO.items()
        if contagem[posicao] != quantidade
    ]
    if erros:
        raise ValueError(f"Escalação incompleta de {casa}: " + ", ".join(erros) + ".")


def criar_partida(
    casa_1: str,
    casa_2: str,
    jogo: str,
    moderador_id: int,
    *,
    tipo_partida: str = "Partida Oficial",
    pasta_vassouras: Path | None = None,
    gerador: random.Random | None = None,
) -> PartidaQuadribol:
    if tipo_partida not in TIPOS_PARTIDA:
        raise ValueError("Tipo de partida inválido.")
    if casa_1 == casa_2:
        raise ValueError("Escolha duas equipes diferentes.")
    times_amadores = {item.nome: item for item in carregar_times_amadores()}
    if tipo_partida == "Partida Oficial" and (casa_1 not in CASAS or casa_2 not in CASAS):
        raise ValueError("Partidas Oficiais usam exclusivamente as quatro Casas.")
    if tipo_partida == "Partida Amistosa" and (casa_1 not in times_amadores or casa_2 not in times_amadores):
        raise ValueError("Partidas Amistosas usam exclusivamente Times Amadores.")
    if tipo_partida == "Partida Oficial" and jogo not in JOGOS_TEMPORADA:
        raise ValueError("Jogo da temporada inválido.")
    if tipo_partida == "Partida Amistosa":
        jogo = "Amistosa"
    sorteio = gerador or random.SystemRandom()
    jogadores = [
        *(
            jogadores_configurados_da_casa(casa_1, pasta_vassouras=pasta_vassouras, gerador=sorteio)
            if tipo_partida == "Partida Oficial"
            else jogadores_configurados_do_time(times_amadores[casa_1], pasta_vassouras=pasta_vassouras, gerador=sorteio)
        ),
        *(
            jogadores_configurados_da_casa(casa_2, pasta_vassouras=pasta_vassouras, gerador=sorteio)
            if tipo_partida == "Partida Oficial"
            else jogadores_configurados_do_time(times_amadores[casa_2], pasta_vassouras=pasta_vassouras, gerador=sorteio)
        ),
    ]
    validar_formacao(jogadores, casa_1)
    validar_formacao(jogadores, casa_2)
    jogadores.sort(
        key=lambda item: (
            not item.em_campo,
            item.posicao == "Goleiro",
            -item.iniciativa_total,
            -item.iniciativa_bonus,
            item.nome.casefold(),
        )
    )
    partida = PartidaQuadribol(
        identificador=_identificador("quadribol"),
        jogo=jogo,
        casa_1=casa_1,
        casa_2=casa_2,
        moderador_id=moderador_id,
        criado_em=_agora(),
        jogadores=jogadores,
        gols={casa_1: 0, casa_2: 0},
        tipo_partida=tipo_partida,
        progresso_pomos={
            casa_1: {casa_1: 0, casa_2: 0},
            casa_2: {casa_1: 0, casa_2: 0},
        },
        disparadas_pomo={casa_1: [], casa_2: []},
        rodadas_surgimento_pomo={
            "1": sorteio.randint(3, 7),
            "2": sorteio.randint(3, 7),
        },
    )
    artilheiros_iniciais = [
        jogador
        for jogador in partida.jogadores
        if jogador.posicao == "Artilheiro" and jogador.ativo and jogador.em_campo
    ]
    partida.posse_goles = artilheiros_iniciais[
        sorteio.randint(0, len(artilheiros_iniciais) - 1)
    ].nome
    partida.eventos.append(
        EventoPartida(
            tipo="inicio",
            descricao=(
                f"{jogo}: {casa_1} contra {casa_2}. Iniciativas roladas; "
                f"{partida.posse_goles} começa com a Goles."
            ),
        )
    )
    return partida


def _garantir_ativa(partida: PartidaQuadribol) -> None:
    if partida.estado != "ativa":
        raise ValueError("A partida não está ativa.")


def _garantir_sem_penalti(
    partida: PartidaQuadribol,
    *,
    permitir_atordoado: bool = False,
) -> None:
    _garantir_ativa(partida)
    if partida.penalti_casa:
        raise ValueError("Resolva o pênalti pendente antes de continuar a partida.")
    if partida.reposicao_goles_casa:
        raise ValueError("Escolha quem receberá a Goles após o impacto do Balaço.")
    atual = partida.jogador_atual()
    if atual is not None and esta_atordoado(atual) and not permitir_atordoado:
        raise ValueError(
            f"{atual.nome} está Atordoado e só pode realizar o Teste de Recuperação."
        )


def bonus_efeitos(jogador: JogadorPartida, teste: str) -> int:
    alvo = normalizar_rotulo(teste)
    return sum(
        efeito.bonus
        for efeito in jogador.efeitos
        if efeito.teste
        and not efeito.contexto
        and normalizar_rotulo(efeito.teste) == alvo
    )


def fontes_pericia_base(
    jogador: JogadorPartida,
    pericia: str,
    total: int,
) -> list[str]:
    """Separa o valor da ficha do bônus fixo já incorporado pela vassoura."""
    modelo = encontrar_vassoura(jogador.vassoura)
    bonus_vassoura = 0
    alvo = normalizar_rotulo(pericia)
    if modelo is not None:
        if alvo == "voo":
            bonus_vassoura = modelo.bonus_voo
        elif alvo == "reflexo":
            bonus_vassoura = modelo.bonus_reflexo
        elif alvo == "fortitude":
            bonus_vassoura = modelo.bonus_fortitude
    fontes = [f"{pericia} da ficha {total - bonus_vassoura:+d}"]
    if bonus_vassoura:
        fontes.append(f"{jogador.vassoura} {bonus_vassoura:+d} em {pericia}")
    return fontes


def bonus_efeitos_contextuais(
    partida: PartidaQuadribol,
    jogador: JogadorPartida,
    teste: str,
    contexto: str,
    *,
    oponente: str = "",
    consumir: bool = False,
) -> tuple[int, tuple[str, ...]]:
    """Obtém bônus restritos a uma ação e consome os que terminam ao serem usados."""
    teste_alvo = normalizar_rotulo(teste)
    contexto_alvo = normalizar_rotulo(contexto)
    encontrados = [
        efeito
        for efeito in jogador.efeitos
        if efeito.contexto
        and normalizar_rotulo(efeito.contexto) == contexto_alvo
        and efeito.teste
        and normalizar_rotulo(efeito.teste) == teste_alvo
        and (
            not efeito.rival
            or normalizar_rotulo(efeito.rival) == normalizar_rotulo(oponente)
        )
    ]
    total = sum(efeito.bonus for efeito in encontrados)
    fontes = tuple(f"{efeito.nome} ({efeito.bonus:+d})" for efeito in encontrados)
    if consumir:
        consumidos = [efeito for efeito in encontrados if efeito.consumir_ao_usar]
        jogador.efeitos = [efeito for efeito in jogador.efeitos if efeito not in consumidos]
        for efeito in consumidos:
            partida.eventos.append(
                EventoPartida(
                    tipo="fim_efeito",
                    jogador=jogador.nome,
                    descricao=f"{efeito.nome} foi consumido por {jogador.nome}.",
                )
            )
    return total, fontes


def _vontade_jogador(jogador: JogadorPartida) -> int:
    try:
        ficha = FichaPersonagem.carregar(Path(jogador.caminho_ficha))
    except (OSError, ValueError):
        return 0
    bonus = 2 if _habilidade_ativa(ficha, "Soldado") else 0
    return total_pericia(ficha, "Vontade") + bonus


def _pericia_jogador(jogador: JogadorPartida, pericia: str) -> int:
    try:
        ficha = FichaPersonagem.carregar(Path(jogador.caminho_ficha))
    except (OSError, ValueError):
        return 0
    return total_pericia(ficha, pericia)


def _habilidade_ativa(ficha: FichaPersonagem, nome: str) -> bool:
    alvo = normalizar_rotulo(nome)
    return any(
        alvo in normalizar_rotulo(efeito.get("nome", ""))
        for efeito in ficha.efeitos_habilidades_ativos
    )


def rolar_bonus_habilidades_contextuais(
    jogador: JogadorPartida,
    teste: str,
    contexto: str,
    *,
    gerador: random.Random,
) -> tuple[int, tuple[str, ...]]:
    """Aplica passivas e habilidades previamente ativadas na ficha, sem gastar PH dela."""
    try:
        ficha = FichaPersonagem.carregar(Path(jogador.caminho_ficha))
    except (OSError, ValueError):
        return 0, ()
    teste_alvo = normalizar_rotulo(teste)
    contexto_alvo = normalizar_rotulo(contexto)
    total = 0
    fontes: list[str] = []
    if teste_alvo == "reflexo":
        if normalizar_rotulo(ficha.heranca) == "parte-vampiro":
            valor = gerador.randint(1, 4)
            total += valor
            fontes.append(f"Parte-Vampiro 1d4 = {valor}")
        if _habilidade_ativa(ficha, "Agilidade Lupina"):
            valor = gerador.randint(1, 4) + 2
            total += valor
            fontes.append(f"Agilidade Lupina 1d4+2 = {valor}")
        if (
            contexto_alvo in {"gol_defesa", "balaco_defesa", "contra_ataque"}
            and _habilidade_ativa(ficha, "Futuro Subsequente")
        ):
            valor = gerador.randint(1, 4) + 2
            total += valor
            fontes.append(f"Futuro Subsequente 1d4+2 = {valor}")
    elif (
        teste_alvo == "fortitude"
        and contexto_alvo == "balaco_impacto"
        and _habilidade_ativa(ficha, "Brutamontes")
    ):
        total += 4
        fontes.append("Brutamontes +4")
    return total, tuple(fontes)


def modificador_condicoes_acao(
    partida: PartidaQuadribol,
    jogador: JogadorPartida,
    contexto: str,
    *,
    oponente: str = "",
    gerador: random.Random | None = None,
    coletiva: bool = False,
    fontes: list[str] | None = None,
) -> int:
    """Resolve condições narrativas automáticas antes de uma rolagem de ação."""
    efeitos = [
        efeito
        for efeito in jogador.efeitos
        if efeito.categoria
        in {
            "Estado emocional",
            "Estado emocional positivo",
            "Condição meteorológica",
            "Habilidade",
        }
        and (not efeito.rodada_inicial or partida.rodada >= efeito.rodada_inicial)
    ]
    if not efeitos:
        return 0
    sorteio = gerador or random.SystemRandom()
    contexto_normalizado = normalizar_rotulo(contexto)
    determinado = any(normalizar_rotulo(item.nome) == "determinado" for item in efeitos)
    modificador_total = 0
    habilidades_preparadas = [
        efeito
        for efeito in efeitos
        if efeito.categoria == "Habilidade"
        and normalizar_rotulo(efeito.contexto) == "proxima_acao"
    ]
    for efeito in habilidades_preparadas:
        modificador_total += efeito.bonus
        if fontes is not None:
            fontes.append(f"{efeito.nome} {efeito.bonus:+d}")
        if efeito.consumir_ao_usar:
            jogador.efeitos.remove(efeito)
            partida.eventos.append(
                EventoPartida(
                    tipo="fim_efeito",
                    jogador=jogador.nome,
                    descricao=f"{efeito.nome} foi consumido na ação de {jogador.nome}.",
                )
            )
    efeitos_tempo = [
        efeito
        for efeito in efeitos
        if normalizar_rotulo(efeito.nome) == "tempo meteorologico"
    ]
    if contexto_normalizado != "impacto_finta":
        for efeito in efeitos_tempo:
            penalidade_preparada = jogador.penalidade_tempo_preparada
            if penalidade_preparada is not None:
                total_fortitude = jogador.resultado_tempo_externo or 0
                fonte_fortitude = jogador.fonte_tempo_preparada or "resistência preparada"
                penalidade_tempo = penalidade_preparada
                sucesso_tempo = penalidade_tempo == 0
                jogador.resultado_tempo_externo = None
                jogador.penalidade_tempo_preparada = None
                jogador.cd_tempo_preparada = 0
                jogador.fonte_tempo_preparada = ""
            elif jogador.resultado_tempo_externo is None:
                dado_fortitude = sorteio.randint(1, 20)
                total_fortitude = dado_fortitude + jogador.fortitude
                fonte_fortitude = (
                    f"d20 {dado_fortitude} + Fortitude {jogador.fortitude:+d}"
                )
                sucesso_tempo = total_fortitude >= efeito.cd_resistencia
                penalidade_tempo = 0
                if not sucesso_tempo:
                    dado_tempo = sorteio.randint(1, 4)
                    penalidade_tempo = -(dado_tempo + 1)
            else:
                total_fortitude = jogador.resultado_tempo_externo
                jogador.resultado_tempo_externo = None
                fonte_fortitude = f"resultado externo de Fortitude {total_fortitude}"
                sucesso_tempo = total_fortitude >= efeito.cd_resistencia
                penalidade_tempo = 0
                if not sucesso_tempo:
                    dado_tempo = sorteio.randint(1, 4)
                    penalidade_tempo = -(dado_tempo + 1)
            modificador_total += penalidade_tempo
            if fontes is not None:
                fontes.append(
                    f"Tempo Meteorológico: {fonte_fortitude} = {total_fortitude}"
                    f"/{efeito.cd_resistencia}; "
                    + (
                        "resistiu"
                        if sucesso_tempo
                        else f"1d4+1 = {abs(penalidade_tempo)} ({penalidade_tempo:+d})"
                    )
                )
            partida.eventos.append(
                EventoPartida(
                    tipo="condicao_acao",
                    casa=jogador.casa,
                    jogador=jogador.nome,
                    valor=penalidade_tempo,
                    descricao=(
                        f"{jogador.nome} realizou um teste de Fortitude contra Tempo Meteorológico: "
                        f"{total_fortitude} contra CD {efeito.cd_resistencia}; "
                        f"modificador {penalidade_tempo:+d} na ação."
                    ),
                )
            )
    negativos_relevantes: list[EfeitoQuadribol] = []
    for efeito in efeitos:
        nome = normalizar_rotulo(efeito.nome)
        if nome in {"sob pressao", "abalado"}:
            negativos_relevantes.append(efeito)
        elif nome == "problemas pessoais" and contexto_normalizado in {
            "acao",
            "concentracao",
            "decisao rapida",
            "manobra",
            "gol",
            "balaco",
            "pomo",
        }:
            negativos_relevantes.append(efeito)
        elif (
            nome == "rivalidade"
            and oponente
            and normalizar_rotulo(efeito.rival) == normalizar_rotulo(oponente)
        ):
            negativos_relevantes.append(efeito)
    if determinado and negativos_relevantes:
        nomes_ignorados = ", ".join(item.nome for item in negativos_relevantes)
        if fontes is not None:
            fontes.append(f"Determinado: ignorou {nomes_ignorados}")
        partida.eventos.append(
            EventoPartida(
                tipo="condicao_acao",
                jogador=jogador.nome,
                descricao=(
                    f"{jogador.nome} estava Determinado e ignorou os efeitos emocionais "
                    f"negativos nesta ação de {contexto}."
                ),
            )
        )
        negativos_relevantes = []
    vontade = _vontade_jogador(jogador)
    for efeito in negativos_relevantes:
        dado_vontade = sorteio.randint(1, 20)
        total_vontade = dado_vontade + vontade
        dado_efeito = sorteio.randint(1, 4)
        rivalidade = normalizar_rotulo(efeito.nome) == "rivalidade"
        sucesso = total_vontade >= efeito.cd_resistencia
        modificador = dado_efeito if rivalidade and sucesso else (-dado_efeito if not sucesso else 0)
        modificador_total += modificador
        if fontes is not None:
            fontes.append(
                f"{efeito.nome}: Vontade {total_vontade}/{efeito.cd_resistencia}, "
                f"{'+' if modificador >= 0 else ''}{modificador}"
            )
        partida.eventos.append(
            EventoPartida(
                tipo="condicao_acao",
                jogador=jogador.nome,
                alvo=oponente if rivalidade else "",
                valor=modificador,
                descricao=(
                    f"{jogador.nome} realizou um teste de Vontade contra {efeito.nome}: "
                    f"{total_vontade} contra CD {efeito.cd_resistencia}; "
                    f"modificador {modificador:+d} na ação."
                ),
            )
        )

    positivos = {
        normalizar_rotulo(efeito.nome): efeito
        for efeito in efeitos
        if efeito.categoria == "Estado emocional positivo"
    }
    confiante = positivos.get("confiante")
    if confiante is not None:
        valor = sorteio.randint(1, 4)
        modificador_total += valor
        if fontes is not None:
            fontes.append(f"Confiante 1d4 = {valor}")
        jogador.efeitos = [efeito for efeito in jogador.efeitos if efeito is not confiante]
        partida.eventos.append(
            EventoPartida(
                tipo="fim_efeito",
                jogador=jogador.nome,
                descricao=f"Confiante foi consumido na primeira ação de {jogador.nome}.",
            )
        )

    motivado = positivos.get("motivado")
    if motivado is not None:
        modificador_total += 1
        if fontes is not None:
            fontes.append("Motivado +1")

    em_sintonia = positivos.get("em sintonia")
    if em_sintonia is not None and coletiva:
        parceiros = [
            outro
            for outro in partida.jogadores
            if outro.nome != jogador.nome
            and outro.casa == jogador.casa
            and outro.ativo
            and outro.em_campo
            and any(
                normalizar_rotulo(efeito.nome) == "em sintonia"
                and (not efeito.rodada_inicial or partida.rodada >= efeito.rodada_inicial)
                for efeito in outro.efeitos
            )
        ]
        if parceiros:
            valor = sorteio.randint(1, 4)
            modificador_total += valor
            if fontes is not None:
                fontes.append(f"Em Sintonia 1d4 = {valor}")
    return modificador_total


def _ficha_jogador_partida(jogador: JogadorPartida) -> FichaPersonagem:
    try:
        return FichaPersonagem.carregar(Path(jogador.caminho_ficha))
    except (OSError, ValueError) as erro:
        raise ValueError(f"Não foi possível consultar a ficha de {jogador.nome}.") from erro


def habilidades_executaveis_quadribol(jogador: JogadorPartida) -> list[str]:
    """Habilidades ativas já mecanizadas para uso direto durante a partida."""
    try:
        ficha = _ficha_jogador_partida(jogador)
    except ValueError:
        return []
    especializacoes = {normalizar_rotulo(nome): nome for nome in ficha.especializacoes}
    resultado: list[str] = []
    for nome in ("Rei", "Poeta // Artista"):
        possuida = especializacoes.get(normalizar_rotulo(nome))
        if possuida:
            resultado.append(possuida)
    return resultado


def executar_rei(
    partida: PartidaQuadribol,
    executor: str,
    alvo: str,
) -> ResultadoHabilidade:
    origem = encontrar_jogador_partida(partida, executor)
    beneficiado = encontrar_jogador_partida(partida, alvo)
    if "Rei" not in habilidades_executaveis_quadribol(origem):
        raise ValueError(f"{origem.nome} não possui a habilidade Rei.")
    if beneficiado.casa != origem.casa or not beneficiado.ativo or not beneficiado.em_campo:
        raise ValueError("Rei só pode orientar um aliado ativo da própria equipe.")
    ficha = _ficha_jogador_partida(origem)
    bonus = modificador(ficha.atributos.get("Carisma", 10))
    beneficiado.efeitos = [
        efeito
        for efeito in beneficiado.efeitos
        if not (
            normalizar_rotulo(efeito.nome).startswith("orientacao de rei")
            and normalizar_rotulo(efeito.origem).endswith(normalizar_rotulo(origem.nome))
        )
    ]
    nome_efeito = f"Orientação de Rei — {origem.nome}"
    beneficiado.efeitos.append(
        EfeitoQuadribol(
            nome=nome_efeito,
            origem=f"Habilidade: Rei — {origem.nome}",
            teste="Qualquer ação",
            bonus=bonus,
            categoria="Habilidade",
            duracao_tipo="gatilho",
            gatilho="próxima ação com rolagem",
            contexto="proxima_acao",
            consumir_ao_usar=True,
            descricao=(
                f"Recebe o modificador de Carisma de {origem.nome} na próxima ação."
            ),
        )
    )
    partida.eventos.append(
        EventoPartida(
            tipo="habilidade",
            casa=origem.casa,
            jogador=origem.nome,
            alvo=beneficiado.nome,
            valor=bonus,
            descricao=(
                f"{origem.nome} usou Rei para orientar {beneficiado.nome}; "
                f"{bonus:+d} será aplicado à próxima ação do aliado."
            ),
        )
    )
    return ResultadoHabilidade(
        habilidade="Rei",
        executor=origem.nome,
        alvo=beneficiado.nome,
        bonus=bonus,
        total=bonus,
        efeito=f"{bonus:+d} na próxima ação com rolagem",
    )


def executar_poeta(
    partida: PartidaQuadribol,
    executor: str,
    alvo: str,
    condicao: str,
    *,
    resultado_externo: int | None = None,
    gerador: random.Random | None = None,
) -> ResultadoHabilidade:
    origem = encontrar_jogador_partida(partida, executor)
    acolhido = encontrar_jogador_partida(partida, alvo)
    if "Poeta // Artista" not in habilidades_executaveis_quadribol(origem):
        raise ValueError(f"{origem.nome} não possui a habilidade Poeta // Artista.")
    if acolhido.casa != origem.casa or not acolhido.ativo or not acolhido.em_campo:
        raise ValueError("Poeta // Artista só pode acolher um aliado ativo da própria equipe.")
    efeito = next(
        (
            item
            for item in acolhido.efeitos
            if normalizar_rotulo(item.nome) == normalizar_rotulo(condicao)
            and item.categoria == "Estado emocional"
        ),
        None,
    )
    if efeito is None:
        raise ValueError("O aliado não possui essa condição emocional negativa.")
    if resultado_externo is not None and resultado_externo < 0:
        raise ValueError("O resultado externo não pode ser negativo.")
    ficha = _ficha_jogador_partida(origem)
    bonus_persuasao = total_pericia(ficha, "Persuasão")
    sorteio = gerador or random.SystemRandom()
    dado = 0 if resultado_externo is not None else sorteio.randint(1, 20)
    bonus_habilidade = 4
    total = (
        resultado_externo
        if resultado_externo is not None
        else dado + bonus_persuasao + bonus_habilidade
    )
    sucesso = total >= efeito.cd_resistencia
    if sucesso:
        acolhido.efeitos.remove(efeito)
    partida.eventos.append(
        EventoPartida(
            tipo="habilidade",
            casa=origem.casa,
            jogador=origem.nome,
            alvo=acolhido.nome,
            valor=bonus_habilidade,
            descricao=(
                f"{origem.nome} usou Poeta // Artista para acolher {acolhido.nome}: "
                f"{total} contra CD {efeito.cd_resistencia}; "
                + (f"removeu {efeito.nome}." if sucesso else f"não removeu {efeito.nome}.")
            ),
        )
    )
    return ResultadoHabilidade(
        habilidade="Poeta // Artista",
        executor=origem.nome,
        alvo=acolhido.nome,
        dado=dado,
        bonus=(0 if resultado_externo is not None else bonus_persuasao + bonus_habilidade),
        total=total,
        cd=efeito.cd_resistencia,
        sucesso=sucesso,
        efeito=(f"{efeito.nome} removido" if sucesso else f"{efeito.nome} permanece"),
        rolagem_externa=resultado_externo is not None,
    )


def tem_tempo_meteorologico(jogador: JogadorPartida) -> bool:
    return any(
        normalizar_rotulo(efeito.nome) == "tempo meteorologico"
        and efeito.categoria == "Condição meteorológica"
        for efeito in jogador.efeitos
    )


def preparar_fortitude_tempo_externa(
    partida: PartidaQuadribol,
    jogador: str,
    resultado: int,
) -> JogadorPartida:
    _garantir_ativa(partida)
    if resultado < 0:
        raise ValueError("O resultado externo de Fortitude não pode ser negativo.")
    alvo = encontrar_jogador_partida(partida, jogador)
    if not tem_tempo_meteorologico(alvo):
        raise ValueError("Este jogador não está afetado pelo Tempo Meteorológico.")
    alvo.resultado_tempo_externo = resultado
    partida.eventos.append(
        EventoPartida(
            tipo="rolagem_externa_preparada",
            casa=alvo.casa,
            jogador=alvo.nome,
            valor=resultado,
            descricao=(
                f"Fortitude externa {resultado} preparada para a próxima ação de "
                f"{alvo.nome} sob Tempo Meteorológico."
            ),
        )
    )
    return alvo


@dataclass(frozen=True)
class ResultadoResistenciaTempo:
    jogador: str
    dado: int
    fortitude: int
    total: int
    cd: int
    sucesso: bool
    penalidade: int
    rolagem_externa: bool = False


def resolver_resistencia_tempo(
    partida: PartidaQuadribol,
    jogador: str,
    *,
    resultado_externo: int | None = None,
    gerador: random.Random | None = None,
) -> ResultadoResistenciaTempo:
    """Resolve e guarda a resistência meteorológica da próxima ação."""
    _garantir_ativa(partida)
    alvo = encontrar_jogador_partida(partida, jogador)
    efeito = next(
        (
            item
            for item in alvo.efeitos
            if normalizar_rotulo(item.nome) == "tempo meteorologico"
            and item.categoria == "Condição meteorológica"
        ),
        None,
    )
    if efeito is None:
        raise ValueError("Este jogador não está afetado pelo Tempo Meteorológico.")
    if alvo.penalidade_tempo_preparada is not None:
        raise ValueError("A resistência meteorológica deste turno já foi realizada.")
    if resultado_externo is not None and resultado_externo < 0:
        raise ValueError("O resultado externo de Fortitude não pode ser negativo.")
    sorteio = gerador or random.SystemRandom()
    dado = 0 if resultado_externo is not None else sorteio.randint(1, 20)
    total = resultado_externo if resultado_externo is not None else dado + alvo.fortitude
    sucesso = total >= efeito.cd_resistencia
    penalidade = 0 if sucesso else -(sorteio.randint(1, 4) + 1)
    fonte = (
        f"resultado externo de Fortitude {total}"
        if resultado_externo is not None
        else f"d20 {dado} + Fortitude {alvo.fortitude:+d}"
    )
    alvo.resultado_tempo_externo = total
    alvo.penalidade_tempo_preparada = penalidade
    alvo.cd_tempo_preparada = efeito.cd_resistencia
    alvo.fonte_tempo_preparada = fonte
    partida.eventos.append(
        EventoPartida(
            tipo="resistencia_tempo",
            casa=alvo.casa,
            jogador=alvo.nome,
            valor=penalidade,
            descricao=(
                f"{alvo.nome} realizou um teste de Fortitude contra Tempo Meteorológico: "
                f"{total} contra CD {efeito.cd_resistencia}; "
                + (
                    "resistiu sem penalidade."
                    if sucesso
                    else f"receberá {penalidade:+d} na próxima ação."
                )
            ),
        )
    )
    return ResultadoResistenciaTempo(
        jogador=alvo.nome,
        dado=dado,
        fortitude=alvo.fortitude,
        total=total,
        cd=efeito.cd_resistencia,
        sucesso=sucesso,
        penalidade=penalidade,
        rolagem_externa=resultado_externo is not None,
    )


def bonus_pontaria_condicional(jogador: JogadorPartida, uso: str) -> int:
    if normalizar_rotulo(jogador.uso_bonus_pontaria) != normalizar_rotulo(uso):
        return 0
    return jogador.bonus_pontaria_vassoura


def rolar_bonus_pontaria_condicional(
    jogador: JogadorPartida,
    uso: str,
    *,
    gerador: random.Random,
    fontes: list[str] | None = None,
) -> tuple[int, int]:
    if normalizar_rotulo(jogador.uso_bonus_pontaria) != normalizar_rotulo(uso):
        return 0, 0
    if jogador.dado_bonus_pontaria_vassoura == "1d4":
        dado = gerador.randint(1, 4)
        if fontes is not None:
            fontes.append(f"{jogador.vassoura} 1d4 ({uso}) = {dado}")
        return dado, dado
    if jogador.bonus_pontaria_vassoura and fontes is not None:
        fontes.append(
            f"{jogador.vassoura} {jogador.bonus_pontaria_vassoura:+d} ({uso})"
        )
    return jogador.bonus_pontaria_vassoura, 0


def rolar_bonus_situacional_vassoura(
    jogador: JogadorPartida,
    pericia: str,
    termos: Iterable[str],
    *,
    gerador: random.Random,
    correspondencia_exata: bool = False,
    fontes: list[str] | None = None,
) -> int:
    modelo = encontrar_vassoura(jogador.vassoura)
    if modelo is None:
        return 0
    pericia_normalizada = normalizar_rotulo(pericia)
    termos_normalizados = tuple(normalizar_rotulo(termo) for termo in termos)
    for especificacao in modelo.especificacoes:
        texto = normalizar_rotulo(especificacao)
        if "1d4" not in texto or f"testes de {pericia_normalizada}" not in texto:
            continue
        corresponde = (
            texto.rstrip(".") in termos_normalizados
            if correspondencia_exata
            else any(termo in texto for termo in termos_normalizados)
        )
        if corresponde:
            valor = gerador.randint(1, 4)
            if fontes is not None:
                fontes.append(f"{modelo.nome} 1d4 = {valor} — {especificacao}")
            return valor
    return 0


def esta_atordoado(jogador: JogadorPartida) -> bool:
    return any(efeito.nome.startswith("Atordoado por") for efeito in jogador.efeitos)


def progresso_necessario_pomo(jogador: JogadorPartida) -> int:
    velocidade = jogador.velocidade_vassoura
    if not velocidade:
        modelo = encontrar_vassoura(jogador.vassoura)
        velocidade = velocidade_vassoura(modelo) if modelo else 0
    return progresso_necessario_por_velocidade(velocidade)


def progresso_necessario_por_velocidade(velocidade: int) -> int:
    if velocidade >= 15:
        return PROGRESSO_POMO_POR_VELOCIDADE[15]
    if 0 < velocidade <= 3:
        return PROGRESSO_POMO_POR_VELOCIDADE[3]
    return PROGRESSO_POMO_POR_VELOCIDADE.get(velocidade, PROGRESSO_POMO_NECESSARIO)


def velocidade_disparada(jogador: JogadorPartida) -> int:
    modelo = encontrar_vassoura(jogador.vassoura)
    if modelo is None:
        return 0
    for especificacao in modelo.especificacoes:
        encontrada = re.search(r"Disparada de\s*(\d+)\s*m/s", especificacao, re.IGNORECASE)
        if encontrada:
            return int(encontrada.group(1))
    return 0


def adicionar_gol(partida: PartidaQuadribol, casa: str) -> None:
    _garantir_sem_penalti(partida)
    if casa not in partida.casas():
        raise ValueError("Esta casa não está na partida.")
    partida.gols[casa] += 1
    partida.eventos.append(
        EventoPartida(tipo="gol", casa=casa, valor=1, descricao=f"{casa} marcou um gol.")
    )


def artilheiros_ativos(partida: PartidaQuadribol, casa: str) -> list[JogadorPartida]:
    return [
        jogador
        for jogador in partida.jogadores
        if jogador.casa == casa
        and jogador.posicao == "Artilheiro"
        and jogador.ativo
        and jogador.em_campo
    ]


def atribuir_posse_goles(
    partida: PartidaQuadribol,
    jogador: str,
    *,
    motivo: str = "",
) -> JogadorPartida:
    portador = encontrar_jogador_partida(partida, jogador)
    if portador.posicao != "Artilheiro" or not portador.ativo or not portador.em_campo:
        raise ValueError("A Goles precisa ser entregue a um Artilheiro ativo em campo.")
    if (
        partida.reposicao_goles_casa
        and portador.casa != partida.reposicao_goles_casa
    ):
        raise ValueError("A Goles precisa ser entregue a um Artilheiro do time adversário.")
    partida.posse_goles = portador.nome
    partida.bonus_passes_gol[portador.casa] = 0
    partida.reposicao_goles_casa = ""
    partida.reposicao_goles_jogador = ""
    partida.eventos.append(
        EventoPartida(
            tipo="posse_goles",
            casa=portador.casa,
            jogador=portador.nome,
            descricao=(
                f"{portador.nome} recebeu a Goles"
                + (f" {motivo}" if motivo else "")
                + "."
            ),
        )
    )
    return portador


def _validar_disputa_posse(
    partida: PartidaQuadribol,
    atacante: str,
    defensor: str,
) -> tuple[JogadorPartida, JogadorPartida]:
    _garantir_sem_penalti(partida)
    atual = partida.jogador_atual()
    origem = encontrar_jogador_partida(partida, atacante)
    opositor = encontrar_jogador_partida(partida, defensor)
    if atual is None or atual.nome != origem.nome:
        raise ValueError("Somente o Artilheiro em destaque pode realizar esta ação.")
    if origem.posicao != "Artilheiro" or not origem.ativo or not origem.em_campo:
        raise ValueError("A ação exige um Artilheiro ativo em campo.")
    if (
        opositor.posicao != "Artilheiro"
        or not opositor.ativo
        or not opositor.em_campo
        or opositor.casa == origem.casa
    ):
        raise ValueError("Escolha um Artilheiro adversário ativo para a disputa.")
    return origem, opositor


def resolver_passe_goles(
    partida: PartidaQuadribol,
    solicitante: str,
    destinatario: str,
    interceptador: str,
    *,
    resultado_passe_externo: int | None = None,
    resultado_interceptacao_externo: int | None = None,
    gerador: random.Random | None = None,
) -> ResultadoPosse:
    solicitante_jogador, defensor = _validar_disputa_posse(
        partida, solicitante, interceptador
    )
    portador = encontrar_jogador_partida(partida, partida.posse_goles)
    destino = encontrar_jogador_partida(partida, destinatario)
    if portador.casa != solicitante_jogador.casa:
        raise ValueError("A equipe do jogador em destaque não está com a Goles.")
    if solicitante_jogador.nome == portador.nome:
        if destino.nome == portador.nome:
            raise ValueError("Escolha outro Artilheiro aliado para receber o passe.")
    elif destino.nome != solicitante_jogador.nome:
        raise ValueError("Ao pedir passe, o destinatário é o próprio jogador do turno.")
    if (
        destino.casa != portador.casa
        or destino.posicao != "Artilheiro"
        or not destino.ativo
        or not destino.em_campo
    ):
        raise ValueError("Escolha um Artilheiro aliado ativo para receber a Goles.")
    for valor, rotulo in (
        (resultado_passe_externo, "passe"),
        (resultado_interceptacao_externo, "interceptação"),
    ):
        if valor is not None and valor < 0:
            raise ValueError(f"O resultado externo de {rotulo} não pode ser negativo.")
    sorteio = gerador or random.SystemRandom()
    dado_passe = 0 if resultado_passe_externo is not None else sorteio.randint(1, 20)
    dado_defesa = (
        0 if resultado_interceptacao_externo is not None else sorteio.randint(1, 20)
    )
    fontes_passe = [
        f"Resultado externo {resultado_passe_externo}"
        if resultado_passe_externo is not None
        else f"d20 {dado_passe}"
    ]
    fontes_defesa = [
        f"Resultado externo {resultado_interceptacao_externo}"
        if resultado_interceptacao_externo is not None
        else f"d20 {dado_defesa}"
    ]
    bonus_condicao_passe = modificador_condicoes_acao(
        partida, portador, "passe", oponente=defensor.nome, gerador=sorteio, fontes=fontes_passe
    )
    bonus_condicao_defesa = modificador_condicoes_acao(
        partida, defensor, "interceptacao", oponente=portador.nome, gerador=sorteio, fontes=fontes_defesa
    )
    bonus_manobra_passe, fontes_manobra_passe = bonus_efeitos_contextuais(
        partida, portador, "Pontaria", "passe", oponente=defensor.nome
    )
    bonus_manobra_defesa, fontes_manobra_defesa = bonus_efeitos_contextuais(
        partida, defensor, "Reflexo", "interceptacao_passe", oponente=portador.nome
    )
    if resultado_passe_externo is None:
        fontes_passe[1:1] = fontes_pericia_base(
            portador, "Pontaria", portador.bonus_teste_posicao
        )
        total_passe = (
            dado_passe + portador.bonus_teste_posicao + bonus_efeitos(portador, "Pontaria")
            + bonus_condicao_passe + bonus_manobra_passe
        )
    else:
        total_passe = resultado_passe_externo + bonus_condicao_passe + bonus_manobra_passe
    if resultado_interceptacao_externo is None:
        fontes_defesa[1:1] = fontes_pericia_base(defensor, "Reflexo", defensor.reflexo)
        bonus_vassoura = rolar_bonus_situacional_vassoura(
            defensor,
            "Reflexo",
            ("interceptar a goles", "interceptar passes"),
            gerador=sorteio,
            fontes=fontes_defesa,
        )
        total_defesa = (
            dado_defesa + defensor.reflexo + bonus_efeitos(defensor, "Reflexo")
            + bonus_condicao_defesa + bonus_manobra_defesa + bonus_vassoura
        )
    else:
        total_defesa = (
            resultado_interceptacao_externo + bonus_condicao_defesa + bonus_manobra_defesa
        )
    fontes_passe.extend(f"Manobra: {fonte}" for fonte in fontes_manobra_passe)
    fontes_defesa.extend(f"Manobra: {fonte}" for fonte in fontes_manobra_defesa)
    sucesso = total_passe >= total_defesa
    novo_portador = destino if sucesso else defensor
    partida.posse_goles = novo_portador.nome
    if sucesso:
        bonus_passes_acumulado = partida.bonus_passes_gol.get(portador.casa, 0) + 1
        partida.bonus_passes_gol[portador.casa] = bonus_passes_acumulado
        sequencia_passes_interrompida = False
    else:
        partida.bonus_passes_gol[portador.casa] = 0
        bonus_passes_acumulado = 0
        sequencia_passes_interrompida = True
    acao = "Passar a Goles" if solicitante_jogador.nome == portador.nome else "Pedir Passe"
    partida.eventos.append(
        EventoPartida(
            tipo="passe_goles",
            casa=novo_portador.casa,
            jogador=portador.nome,
            alvo=novo_portador.nome,
            descricao=(
                f"{portador.nome} completou o passe para {destino.nome}: "
                f"{total_passe} contra {total_defesa}."
                if sucesso
                else f"{defensor.nome} interceptou o passe de {portador.nome}: "
                f"{total_defesa} contra {total_passe}."
            ),
        )
    )
    return ResultadoPosse(
        acao=acao,
        atacante=portador.nome,
        defensor=defensor.nome,
        destinatario=destino.nome,
        dado_atacante=dado_passe,
        total_atacante=total_passe,
        dado_defensor=dado_defesa,
        total_defensor=total_defesa,
        novo_portador=novo_portador.nome,
        sucesso=sucesso,
        fontes_atacante=tuple(fontes_passe),
        fontes_defensor=tuple(fontes_defesa),
        rolagem_externa_atacante=resultado_passe_externo is not None,
        rolagem_externa_defensor=resultado_interceptacao_externo is not None,
        bonus_passes_acumulado=bonus_passes_acumulado,
        sequencia_passes_interrompida=sequencia_passes_interrompida,
    )


def resolver_tomada_goles(
    partida: PartidaQuadribol,
    atacante: str,
    *,
    resultado_atletismo_externo: int | None = None,
    resultado_reflexo_externo: int | None = None,
    gerador: random.Random | None = None,
) -> ResultadoPosse:
    portador_nome = partida.posse_goles
    origem, portador = _validar_disputa_posse(partida, atacante, portador_nome)
    if resultado_atletismo_externo is not None and resultado_atletismo_externo < 0:
        raise ValueError("O resultado externo de Atletismo não pode ser negativo.")
    if resultado_reflexo_externo is not None and resultado_reflexo_externo < 0:
        raise ValueError("O resultado externo de Reflexo não pode ser negativo.")
    sorteio = gerador or random.SystemRandom()
    dado_atletismo = 0 if resultado_atletismo_externo is not None else sorteio.randint(1, 20)
    dado_reflexo = 0 if resultado_reflexo_externo is not None else sorteio.randint(1, 20)
    fontes_atletismo = [
        f"Resultado externo {resultado_atletismo_externo}"
        if resultado_atletismo_externo is not None else f"d20 {dado_atletismo}"
    ]
    fontes_reflexo = [
        f"Resultado externo {resultado_reflexo_externo}"
        if resultado_reflexo_externo is not None else f"d20 {dado_reflexo}"
    ]
    bonus_condicao_atacante = modificador_condicoes_acao(
        partida, origem, "tomar_goles", oponente=portador.nome, gerador=sorteio, fontes=fontes_atletismo
    )
    bonus_condicao_portador = modificador_condicoes_acao(
        partida, portador, "manter_goles", oponente=origem.nome, gerador=sorteio, fontes=fontes_reflexo
    )
    if resultado_atletismo_externo is None:
        fontes_atletismo.append(
            f"Atletismo com {origem.atributo_atletismo or 'maior atributo'} {origem.atletismo:+d}"
        )
        total_atletismo = dado_atletismo + origem.atletismo + bonus_condicao_atacante
    else:
        total_atletismo = resultado_atletismo_externo + bonus_condicao_atacante
    if resultado_reflexo_externo is None:
        fontes_reflexo[1:1] = fontes_pericia_base(portador, "Reflexo", portador.reflexo)
        total_reflexo = (
            dado_reflexo + portador.reflexo + bonus_efeitos(portador, "Reflexo")
            + bonus_condicao_portador
        )
    else:
        total_reflexo = resultado_reflexo_externo + bonus_condicao_portador
    sucesso = total_atletismo >= total_reflexo
    novo_portador = origem if sucesso else portador
    partida.posse_goles = novo_portador.nome
    if sucesso:
        partida.bonus_passes_gol[portador.casa] = 0
    partida.eventos.append(
        EventoPartida(
            tipo="tomada_goles",
            casa=novo_portador.casa,
            jogador=origem.nome,
            alvo=portador.nome,
            descricao=(
                f"{origem.nome} tomou a Goles de {portador.nome}: "
                f"{total_atletismo} contra {total_reflexo}."
                if sucesso
                else f"{portador.nome} protegeu a Goles contra {origem.nome}: "
                f"{total_reflexo} contra {total_atletismo}."
            ),
        )
    )
    return ResultadoPosse(
        acao="Tomar a Goles",
        atacante=origem.nome,
        defensor=portador.nome,
        destinatario="",
        dado_atacante=dado_atletismo,
        total_atacante=total_atletismo,
        dado_defensor=dado_reflexo,
        total_defensor=total_reflexo,
        novo_portador=novo_portador.nome,
        sucesso=sucesso,
        fontes_atacante=tuple(fontes_atletismo),
        fontes_defensor=tuple(fontes_reflexo),
        rolagem_externa_atacante=resultado_atletismo_externo is not None,
        rolagem_externa_defensor=resultado_reflexo_externo is not None,
        sequencia_passes_interrompida=sucesso,
    )


def resolver_finta_wronski(
    partida: PartidaQuadribol,
    executor: str,
    *,
    resultado_voo_externo: int | None = None,
    resultado_fortitude_externo: int | None = None,
    gerador: random.Random | None = None,
) -> ResultadoFintaWronski:
    _garantir_sem_penalti(partida)
    origem = encontrar_jogador_partida(partida, executor)
    atual = partida.jogador_atual()
    if atual is None or atual.nome != origem.nome or origem.posicao != "Apanhador":
        raise ValueError("A Finta de Wronski deve ser concluída pelo Apanhador em destaque.")
    alvos = [
        jogador
        for jogador in partida.jogadores
        if jogador.casa != origem.casa
        and jogador.posicao == "Apanhador"
        and jogador.ativo
        and jogador.em_campo
    ]
    if len(alvos) != 1:
        raise ValueError("A equipe adversária precisa possuir um Apanhador ativo.")
    alvo = alvos[0]
    for valor, rotulo in (
        (resultado_voo_externo, "Voo"),
        (resultado_fortitude_externo, "Fortitude"),
    ):
        if valor is not None and valor < 0:
            raise ValueError(f"O resultado externo de {rotulo} não pode ser negativo.")
    sorteio = gerador or random.SystemRandom()
    dado_voo = 0 if resultado_voo_externo is not None else sorteio.randint(1, 20)
    fontes_voo = [
        f"Resultado externo {resultado_voo_externo}"
        if resultado_voo_externo is not None else f"d20 {dado_voo}"
    ]
    bonus_condicao_voo = modificador_condicoes_acao(
        partida, alvo, "finta_wronski", oponente=origem.nome, gerador=sorteio, fontes=fontes_voo
    )
    if resultado_voo_externo is None:
        fontes_voo[1:1] = fontes_pericia_base(alvo, "Vôo", alvo.voo)
        bonus_vassoura_voo = rolar_bonus_situacional_vassoura(
            alvo,
            "Vôo",
            ("controle e freio", "mudanças bruscas de direção", "controle de trajetória"),
            gerador=sorteio,
            fontes=fontes_voo,
        )
        total_voo = (
            dado_voo + alvo.voo + bonus_efeitos(alvo, "Vôo")
            + bonus_condicao_voo + bonus_vassoura_voo
        )
    else:
        total_voo = resultado_voo_externo + bonus_condicao_voo
    evitou = total_voo >= 18
    dado_fortitude = total_fortitude = dado_dano = dano = perda_vassoura = 0
    resistiu = True
    fontes_fortitude: list[str] = []
    if not evitou:
        alvo.turnos_pulados += 1
        dado_fortitude = (
            0 if resultado_fortitude_externo is not None else sorteio.randint(1, 20)
        )
        fontes_fortitude.append(
            f"Resultado externo {resultado_fortitude_externo}"
            if resultado_fortitude_externo is not None else f"d20 {dado_fortitude}"
        )
        bonus_condicao_fortitude = modificador_condicoes_acao(
            partida, alvo, "impacto_finta", oponente=origem.nome, gerador=sorteio, fontes=fontes_fortitude
        )
        if resultado_fortitude_externo is None:
            fontes_fortitude[1:1] = fontes_pericia_base(
                alvo, "Fortitude", alvo.fortitude
            )
            total_fortitude = (
                dado_fortitude + alvo.fortitude + bonus_efeitos(alvo, "Fortitude")
                + bonus_condicao_fortitude
            )
        else:
            total_fortitude = resultado_fortitude_externo + bonus_condicao_fortitude
        resistiu = total_fortitude >= 15
        if not resistiu:
            dado_dano = sorteio.randint(1, 6)
            dano = dado_dano + 4
            vida_anterior = alvo.vida_vassoura
            alvo.vida_vassoura = max(0, alvo.vida_vassoura - 3)
            perda_vassoura = vida_anterior - alvo.vida_vassoura
            if alvo.vassoura_quebrada:
                alvo.ativo = False
    partida.eventos.append(
        EventoPartida(
            tipo="finta_wronski",
            casa=origem.casa,
            jogador=origem.nome,
            alvo=alvo.nome,
            valor=dano,
            descricao=(
                f"{alvo.nome} evitou o chão após a Finta de Wronski com Voo {total_voo}."
                if evitou
                else (
                    f"{alvo.nome} colidiu após a Finta de Wronski, perderá seu próximo "
                    f"turno e "
                    + (
                        "resistiu ao impacto."
                        if resistiu
                        else (
                            f"sofreu {dano} de dano concussivo; a vassoura perdeu "
                            f"{perda_vassoura} PV."
                        )
                    )
                )
            ),
        )
    )
    return ResultadoFintaWronski(
        executor=origem.nome,
        alvo=alvo.nome,
        dado_voo=dado_voo,
        total_voo=total_voo,
        evitou_colisao=evitou,
        dado_fortitude=dado_fortitude,
        total_fortitude=total_fortitude,
        resistiu_impacto=resistiu,
        dado_dano=dado_dano,
        dano_concussivo=dano,
        pv_vassoura_perdido=perda_vassoura,
        fontes_voo=tuple(fontes_voo),
        fontes_fortitude=tuple(fontes_fortitude),
    )


def perseguir_pomo(
    partida: PartidaQuadribol,
    jogador: str,
    *,
    usar_disparada: bool = False,
    resultado_externo: int | None = None,
    gerador: random.Random | None = None,
) -> ResultadoPomo:
    _garantir_sem_penalti(partida)
    atual = partida.jogador_atual()
    apanhador = encontrar_jogador_partida(partida, jogador)
    if atual is None or atual.nome != apanhador.nome:
        raise ValueError("Somente o jogador do turno atual pode perseguir o Pomo.")
    if apanhador.posicao != "Apanhador" or not apanhador.em_campo or not apanhador.ativo:
        raise ValueError("Somente um Apanhador ativo em campo pode perseguir o Pomo.")
    if esta_atordoado(apanhador):
        raise ValueError("O Apanhador está Atordoado e não pode perseguir o Pomo.")
    if apanhador.perseguiu_pomo_no_turno:
        raise ValueError("O Apanhador já sustentou a perseguição neste turno.")
    ativos = partida.pomos_ativos()
    if not ativos:
        lado_atual = partida.casa_1 if partida.tempo == 1 else partida.casa_2
        if lado_atual in partida.pomos:
            raise ValueError("O Pomo deste tempo já foi capturado.")
        raise ValueError("O Pomo ainda não surgiu.")
    pomo_lado = ativos[0]
    progresso_lado = partida.progresso_pomos.setdefault(
        pomo_lado,
        {casa: 0 for casa in partida.casas()},
    )
    velocidade_considerada = apanhador.velocidade_vassoura
    if usar_disparada:
        velocidade_considerada = velocidade_disparada(apanhador)
        if not velocidade_considerada:
            raise ValueError("A vassoura deste Apanhador não possui Disparada.")
        usos = partida.disparadas_pomo.setdefault(pomo_lado, [])
        if apanhador.nome in usos:
            raise ValueError("Este Apanhador já usou a Disparada no Pomo atual.")
        usos.append(apanhador.nome)
    sorteio = gerador or random.SystemRandom()
    if resultado_externo is not None and resultado_externo < 0:
        raise ValueError("O resultado externo não pode ser negativo.")
    dado = 0 if resultado_externo is not None else sorteio.randint(1, 20)
    termos_vassoura = (
        (
            "disparada",
            "arrancadas",
            "velocidade de percurso em uma reta",
            "velocidade de percurso em linha reta",
            "aproximações precisas em alta velocidade",
        )
        if usar_disparada
        else (
            "arrancadas",
            "perseguições",
            "ângulo de interceptação",
            "reposicionamento em trajetória planejada",
            "aproximações precisas em alta velocidade",
            "velocidade em linha reta",
        )
    )
    fontes: list[str] = []
    bonus_vassoura_situacional = 0
    bonus_condicoes = modificador_condicoes_acao(
        partida,
        apanhador,
        "pomo",
        gerador=sorteio,
        fontes=fontes,
    )
    bonus = 0
    if resultado_externo is None:
        bonus_vassoura_situacional = rolar_bonus_situacional_vassoura(
            apanhador,
            "Voo",
            termos_vassoura,
            gerador=sorteio,
            fontes=fontes,
        )
        bonus_efeitos_voo = bonus_efeitos(apanhador, "Vôo")
        fontes[0:0] = fontes_pericia_base(apanhador, "Vôo", apanhador.voo)
        if apanhador.prodigio:
            fontes.insert(1, "Prodígio do Quadribol +2")
        if bonus_efeitos_voo:
            fontes.append(f"Efeitos de Vôo {bonus_efeitos_voo:+d}")
        bonus = (
            apanhador.voo
            + (2 if apanhador.prodigio else 0)
            + bonus_efeitos_voo
            + bonus_vassoura_situacional
            + bonus_condicoes
        )
    total = (
        resultado_externo + bonus_condicoes
        if resultado_externo is not None
        else dado + bonus
    )
    anterior = progresso_lado.get(apanhador.casa, 0)
    atual_progresso = anterior + max(0, total)
    progresso_lado[apanhador.casa] = atual_progresso
    apanhador.perseguiu_pomo_no_turno = True
    apanhador.pomo_perseguido = pomo_lado
    necessario = (
        progresso_necessario_por_velocidade(velocidade_considerada)
        if usar_disparada
        else progresso_necessario_pomo(apanhador)
    )
    capturou = atual_progresso >= necessario
    if capturou:
        partida.pomos[pomo_lado] = apanhador.casa
        for jogador_partida in partida.jogadores:
            if jogador_partida.posicao == "Apanhador":
                jogador_partida.pomo_perseguido = ""
    texto_disparada = (
        f" usando a Disparada de {velocidade_considerada}m/s"
        if usar_disparada
        else ""
    )
    partida.eventos.append(
        EventoPartida(
            tipo="pomo" if capturou else "perseguicao_pomo",
            casa=apanhador.casa,
            jogador=apanhador.nome,
            valor=max(0, total),
            alvo=pomo_lado,
            descricao=(
                f"{apanhador.nome} obteve {total} na perseguição ao Pomo "
                f"do lado de {pomo_lado}{texto_disparada} e chegou a "
                f"{atual_progresso}/{necessario}."
                + (" O Pomo foi capturado." if capturou else "")
            ),
        )
    )
    return ResultadoPomo(
        jogador=apanhador.nome,
        pomo_lado=pomo_lado,
        dado=dado,
        bonus=bonus,
        total=total,
        progresso_anterior=anterior,
        progresso_atual=atual_progresso,
        necessario=necessario,
        velocidade_considerada=velocidade_considerada,
        usou_disparada=usar_disparada,
        capturou=capturou,
        bonus_vassoura_situacional=bonus_vassoura_situacional,
        rolagem_externa=resultado_externo is not None,
        fontes=tuple(fontes),
    )


def desfazer_ultima_acao(partida: PartidaQuadribol) -> EventoPartida:
    reversivel = next(
        (item for item in reversed(partida.eventos) if item.tipo in {"gol", "pomo"}),
        None,
    )
    if reversivel is None:
        raise ValueError("Não há gol ou captura do Pomo para desfazer.")
    partida.eventos.remove(reversivel)
    if reversivel.tipo == "gol":
        partida.gols[reversivel.casa] -= 1
    else:
        partida.pomos.pop(reversivel.alvo, None)
        progresso = partida.progresso_pomos.setdefault(
            reversivel.alvo,
            {casa: 0 for casa in partida.casas()},
        )
        progresso[reversivel.casa] = max(
            0,
            progresso.get(reversivel.casa, 0) - reversivel.valor,
        )
    partida.eventos.append(
        EventoPartida(tipo="desfazer", descricao=f"Ação desfeita: {reversivel.descricao}")
    )
    return reversivel


def _registrar_proximo_turno(partida: PartidaQuadribol) -> None:
    atual = partida.jogador_atual()
    if atual is not None:
        expirados: list[tuple[JogadorPartida, EfeitoQuadribol]] = []
        for jogador in partida.jogadores:
            for efeito in jogador.efeitos:
                if (
                    efeito.duracao_tipo == "ciclo"
                    and normalizar_rotulo(efeito.gatilho) == normalizar_rotulo(atual.nome)
                    and partida.rodada > efeito.rodada_inicial
                ):
                    expirados.append((jogador, efeito))
        for jogador, efeito in expirados:
            if efeito in jogador.efeitos:
                jogador.efeitos.remove(efeito)
                partida.eventos.append(
                    EventoPartida(
                        tipo="fim_efeito",
                        jogador=jogador.nome,
                        descricao=(
                            f"{efeito.nome} terminou para {jogador.nome} quando o turno "
                            f"retornou a {atual.nome}."
                        ),
                    )
                )
        partida.eventos.append(
            EventoPartida(
                tipo="turno",
                jogador=atual.nome,
                descricao=f"Turno de {atual.nome}.",
            )
        )


def _ordenar_acoes_preparadas(partida: PartidaQuadribol) -> None:
    aptos = {
        jogador.nome: jogador
        for jogador in partida.jogadores_em_iniciativa()
    }
    ordem_original = {
        jogador.nome: indice
        for indice, jogador in enumerate(partida.jogadores)
    }
    partida.acoes_preparadas = sorted(
        (nome for nome in partida.acoes_preparadas if nome in aptos),
        key=lambda nome: (
            -aptos[nome].iniciativa_total,
            ordem_original.get(nome, len(ordem_original)),
        ),
    )


def preparar_acao(partida: PartidaQuadribol) -> JogadorPartida:
    """Guarda o turno atual para o início da próxima rodada."""
    _garantir_sem_penalti(partida)
    if partida.executando_acoes_preparadas:
        raise ValueError("Uma ação já preparada não pode ser adiada novamente.")
    atual = partida.jogador_atual()
    if atual is None:
        raise ValueError("Não há jogador no turno atual.")
    if atual.nome in partida.acoes_preparadas:
        raise ValueError(f"{atual.nome} já está preparando uma ação.")

    partida.acoes_preparadas.append(atual.nome)
    _ordenar_acoes_preparadas(partida)
    jogadores = partida.jogadores_em_iniciativa()
    proximo_indice = partida.indice_turno + 1
    if proximo_indice < len(jogadores):
        partida.indice_turno = proximo_indice
    else:
        partida.indice_turno = 0
        _iniciar_nova_rodada(partida)
        partida.executando_acoes_preparadas = True
    _registrar_proximo_turno(partida)
    return atual


def avancar_turno(
    partida: PartidaQuadribol,
    *,
    permitir_atordoado: bool = False,
) -> list[EfeitoQuadribol]:
    _garantir_sem_penalti(partida, permitir_atordoado=permitir_atordoado)
    atual = partida.jogador_atual()
    expirados: list[EfeitoQuadribol] = []
    if atual is not None:
        if (
            atual.posicao == "Apanhador"
            and atual.em_campo
            and atual.pomo_perseguido
            and partida.progresso_pomos.get(atual.pomo_perseguido, {}).get(atual.casa, 0) > 0
            and not atual.perseguiu_pomo_no_turno
        ):
            progresso = partida.progresso_pomos[atual.pomo_perseguido]
            perdido = progresso[atual.casa]
            progresso[atual.casa] = 0
            partida.eventos.append(
                EventoPartida(
                    tipo="quebra_concentracao",
                    casa=atual.casa,
                    jogador=atual.nome,
                    valor=perdido,
                    alvo=atual.pomo_perseguido,
                    descricao=(
                        f"{atual.nome} não sustentou a perseguição e perdeu {perdido} "
                        "ponto(s) de progresso do Pomo."
                    ),
                )
            )
            atual.pomo_perseguido = ""
        atual.perseguiu_pomo_no_turno = False
        # Uma resistência meteorológica preparada vale apenas para a ação
        # daquele turno; ao encerrá-lo sem agir, o resultado não é carregado adiante.
        atual.resultado_tempo_externo = None
        atual.penalidade_tempo_preparada = None
        atual.cd_tempo_preparada = 0
        atual.fonte_tempo_preparada = ""
        for efeito in atual.efeitos:
            if efeito.duracao_tipo == "turnos":
                efeito.turnos_restantes -= 1
        expirados = [
            efeito
            for efeito in atual.efeitos
            if efeito.duracao_tipo == "turnos" and efeito.turnos_restantes <= 0
        ]
        atual.efeitos = [efeito for efeito in atual.efeitos if efeito not in expirados]
        for efeito in expirados:
            partida.eventos.append(
                EventoPartida(
                    tipo="fim_efeito",
                    jogador=atual.nome,
                    descricao=f"{efeito.nome} terminou para {atual.nome}.",
                )
            )
    jogadores = partida.jogadores_em_iniciativa()
    if not jogadores:
        raise ValueError("Nenhum jogador com turno ativo permanece em campo.")
    if partida.executando_acoes_preparadas:
        if atual is not None:
            partida.acoes_preparadas = [
                nome for nome in partida.acoes_preparadas if nome != atual.nome
            ]
        nomes_aptos = {jogador.nome for jogador in jogadores}
        partida.acoes_preparadas = [
            nome for nome in partida.acoes_preparadas if nome in nomes_aptos
        ]
        if not partida.acoes_preparadas:
            partida.executando_acoes_preparadas = False
            partida.indice_turno = 0
    else:
        proximo_indice = partida.indice_turno + 1
        if proximo_indice < len(jogadores):
            partida.indice_turno = proximo_indice
        elif partida.acoes_preparadas:
            partida.indice_turno = 0
            _iniciar_nova_rodada(partida)
            _ordenar_acoes_preparadas(partida)
            partida.executando_acoes_preparadas = True
        else:
            partida.indice_turno = 0
            _iniciar_nova_rodada(partida)
    # Efeitos como a Finta de Wronski não removem o jogador da iniciativa:
    # quando a vez chega, ela é registrada e ultrapassada automaticamente.
    limite_pulos = len(jogadores) + len(partida.acoes_preparadas) + 1
    while limite_pulos > 0:
        impedido = partida.jogador_atual()
        if impedido is None or impedido.turnos_pulados <= 0:
            break
        impedido.turnos_pulados -= 1
        partida.eventos.append(
            EventoPartida(
                tipo="turno_pulado",
                casa=impedido.casa,
                jogador=impedido.nome,
                descricao=(
                    f"O turno de {impedido.nome} foi pulado automaticamente "
                    "por causa da Finta de Wronski."
                ),
            )
        )
        jogadores = partida.jogadores_em_iniciativa()
        if partida.executando_acoes_preparadas:
            partida.acoes_preparadas = [
                nome for nome in partida.acoes_preparadas if nome != impedido.nome
            ]
            if not partida.acoes_preparadas:
                partida.executando_acoes_preparadas = False
                partida.indice_turno = 0
        else:
            proximo_indice = partida.indice_turno + 1
            if proximo_indice < len(jogadores):
                partida.indice_turno = proximo_indice
            elif partida.acoes_preparadas:
                partida.indice_turno = 0
                _iniciar_nova_rodada(partida)
                _ordenar_acoes_preparadas(partida)
                partida.executando_acoes_preparadas = True
            else:
                partida.indice_turno = 0
                _iniciar_nova_rodada(partida)
        limite_pulos -= 1
    _registrar_proximo_turno(partida)
    return expirados


def _iniciar_nova_rodada(partida: PartidaQuadribol) -> None:
    partida.rodada += 1
    partida.rodada_tempo += 1
    for jogador in partida.jogadores:
        expirados = [
            efeito
            for efeito in jogador.efeitos
            if efeito.duracao_tipo == "rodadas"
            and efeito.rodada_final
            and partida.rodada > efeito.rodada_final
        ]
        jogador.efeitos = [efeito for efeito in jogador.efeitos if efeito not in expirados]
        for efeito in expirados:
            partida.eventos.append(
                EventoPartida(
                    tipo="fim_efeito",
                    jogador=jogador.nome,
                    descricao=f"{efeito.nome} terminou automaticamente para {jogador.nome}.",
                )
            )
    lado_pomo = partida.casa_1 if partida.tempo == 1 else partida.casa_2
    if (
        partida.rodada_tempo
        == partida.rodadas_surgimento_pomo.get(str(partida.tempo), 0)
        and lado_pomo not in partida.pomos_anunciados
        and lado_pomo not in partida.pomos
    ):
        partida.pomos_anunciados.append(lado_pomo)
        partida.eventos.append(
            EventoPartida(
                tipo="surgimento_pomo",
                alvo=lado_pomo,
                descricao=(
                    f"O POMO SURGIU!!! Ele apareceu no lado de {lado_pomo}, "
                    f"na rodada {partida.rodada_tempo} do {partida.tempo}º tempo."
                ),
            )
        )


def avancar_rodada(partida: PartidaQuadribol) -> list[EfeitoQuadribol]:
    """Encerra os turnos restantes da rodada atual e inicia a próxima."""
    jogadores = partida.jogadores_em_iniciativa()
    if not jogadores:
        raise ValueError("Nenhum jogador com turno ativo permanece em campo.")
    rodada_inicial = partida.rodada
    expirados: list[EfeitoQuadribol] = []
    while partida.rodada == rodada_inicial:
        # Passar a rodada é um controle do narrador, não uma ação do
        # jogador atordoado. Os turnos restantes devem poder ser encerrados.
        expirados.extend(avancar_turno(partida, permitir_atordoado=True))
    partida.eventos.append(
        EventoPartida(
            tipo="rodada",
            descricao=f"A rodada {partida.rodada_tempo} do {partida.tempo}º tempo foi iniciada.",
        )
    )
    return expirados


def encontrar_jogador_partida(partida: PartidaQuadribol, nome: str) -> JogadorPartida:
    alvo = normalizar_rotulo(nome)
    encontrados = [item for item in partida.jogadores if normalizar_rotulo(item.nome) == alvo]
    if len(encontrados) != 1:
        raise ValueError("Jogador da partida não encontrado.")
    return encontrados[0]


def resolver_balaco(
    partida: PartidaQuadribol,
    atacante: str,
    alvo: str,
    *,
    defesa: str = "Reflexo",
    defensor: str = "",
    rebate_duplo: bool = False,
    segundo_batedor: str = "",
    zona_fogo: bool = False,
    redirecionar: bool = False,
    alvo_redirecionado: str = "",
    resultado_ataque_externo: int | None = None,
    resultado_defesa_externo: int | None = None,
    gerador: random.Random | None = None,
) -> ResultadoBalaco:
    _garantir_sem_penalti(partida)
    sorteio = gerador or random.SystemRandom()
    if resultado_ataque_externo is not None and resultado_ataque_externo < 0:
        raise ValueError("O resultado externo do ataque não pode ser negativo.")
    if resultado_defesa_externo is not None and resultado_defesa_externo < 0:
        raise ValueError("O resultado externo da defesa não pode ser negativo.")
    origem = encontrar_jogador_partida(partida, atacante)
    atingido = encontrar_jogador_partida(partida, alvo)
    if origem.casa == atingido.casa and not zona_fogo:
        raise ValueError("O alvo do balaço precisa pertencer ao time adversário.")
    if origem.posicao != "Batedor" or not origem.ativo or not origem.em_campo:
        raise ValueError("Somente um Batedor pode lançar um balaço.")
    if not atingido.ativo or not atingido.em_campo:
        raise ValueError("O alvo precisa estar ativo em campo.")
    bonus_vassoura_ataque = 0
    bonus_vassoura_defesa = 0
    dado_bonus_vassoura_ataque = 0
    dado_bonus_vassoura_defesa = 0
    dado_bonus_vassoura_reflexo = 0
    fontes_ataque: list[str] = []
    fontes_defesa: list[str] = []
    fontes_fortitude: list[str] = []
    fontes_reflexo_redirecionado: list[str] = []
    bonus_condicoes_ataque = modificador_condicoes_acao(
        partida,
        origem,
        "balaco",
        oponente=atingido.nome,
        gerador=sorteio,
        fontes=fontes_ataque,
    )
    bonus_manobra_ataque, fontes_manobra_ataque = bonus_efeitos_contextuais(
        partida,
        origem,
        "Pontaria",
        "balaco_ataque",
        oponente=atingido.nome,
    )
    bonus_persistente_ataque = bonus_efeitos(origem, "Pontaria")
    bonus_ataque = origem.bonus_teste_posicao + bonus_persistente_ataque
    bonus_base_ataque = bonus_ataque
    nome_origem = origem.nome
    participantes_zona: tuple[JogadorPartida, ...] = ()
    if zona_fogo:
        participantes_zona = batedores_zona_fogo(partida, origem)
        if len(participantes_zona) != 2:
            raise ValueError("A equipe deste Batedor não está sustentando uma Zona de Fogo.")
        if atingido in participantes_zona:
            raise ValueError("Os Batedores que sustentam a Zona de Fogo não podem ser o alvo.")
        bonus_individuais: list[float] = []
        fontes_individuais: list[str] = []
        for participante in participantes_zona:
            bonus_persistente_participante = bonus_efeitos(participante, "Pontaria")
            bonus_participante = (
                participante.bonus_teste_posicao + bonus_persistente_participante
            )
            if resultado_ataque_externo is None:
                fontes_base = fontes_pericia_base(
                    participante,
                    "Pontaria",
                    participante.bonus_teste_posicao,
                )
                fontes_individuais.extend(
                    f"{participante.nome}: {fonte}" for fonte in fontes_base
                )
                if bonus_persistente_participante:
                    fontes_individuais.append(
                        f"{participante.nome}: efeitos de Pontaria "
                        f"{bonus_persistente_participante:+d}"
                    )
                fontes_vassoura: list[str] = []
                bonus_vassoura_participante, _ = rolar_bonus_pontaria_condicional(
                    participante,
                    "Ataque direto",
                    gerador=sorteio,
                    fontes=fontes_vassoura,
                )
                bonus_participante += bonus_vassoura_participante
                fontes_individuais.extend(
                    f"{participante.nome}: {fonte}" for fonte in fontes_vassoura
                )
            bonus_individuais.append(bonus_participante)
        media = sum(bonus_individuais) / 2
        bonus_ataque = int(media) if media.is_integer() else media
        bonus_base_ataque = bonus_ataque
        nome_origem = " e ".join(item.nome for item in participantes_zona)
        cd = 12 + origem.modificador_forca
        nome_efeito = "Atordoado por Zona de Fogo"
        if resultado_ataque_externo is None:
            fontes_ataque.extend(fontes_individuais)
            valores = " e ".join(f"{valor:+g}" for valor in bonus_individuais)
            fontes_ataque.append(
                f"Média da Zona de Fogo: ({valores}) ÷ 2 = {bonus_ataque:+g}"
            )
    elif rebate_duplo:
        parceiro = encontrar_jogador_partida(partida, segundo_batedor)
        if (
            parceiro.casa != origem.casa
            or parceiro.posicao != "Batedor"
            or parceiro.nome == origem.nome
            or not parceiro.ativo
            or not parceiro.em_campo
        ):
            raise ValueError("O Rebate Duplo exige dois Batedores diferentes do mesmo time.")
        cd = 14 + max(origem.modificador_forca, parceiro.modificador_forca)
        nome_efeito = "Atordoado por Rebate Duplo"
        bonus_ataque = max(
            bonus_ataque,
            parceiro.bonus_teste_posicao + bonus_efeitos(parceiro, "Pontaria"),
        )
        bonus_base_ataque = bonus_ataque
        nome_origem = f"{origem.nome} e {parceiro.nome}"
    else:
        cd = 12 + origem.modificador_forca
        nome_efeito = "Atordoado por Balaço"
        if resultado_ataque_externo is None:
            bonus_vassoura_ataque, dado_bonus_vassoura_ataque = (
                rolar_bonus_pontaria_condicional(
                    origem,
                    "Ataque direto",
                    gerador=sorteio,
                    fontes=fontes_ataque,
                )
            )
            bonus_ataque += bonus_vassoura_ataque
    bonus_ataque += bonus_condicoes_ataque + bonus_manobra_ataque
    fontes_ataque.extend(f"Manobra: {fonte}" for fonte in fontes_manobra_ataque)
    dado_ataque = 0 if resultado_ataque_externo is not None else sorteio.randint(1, 20)
    fontes_ataque.insert(
        0,
        f"Resultado externo {resultado_ataque_externo}"
        if resultado_ataque_externo is not None
        else f"d20 {dado_ataque}",
    )
    if resultado_ataque_externo is None:
        if not zona_fogo:
            fontes_ataque[1:1] = (
                [f"Melhor Pontaria dos Batedores {bonus_base_ataque:+d}"]
                if rebate_duplo
                else fontes_pericia_base(origem, "Pontaria", origem.bonus_teste_posicao)
            )
        if bonus_persistente_ataque and not rebate_duplo and not zona_fogo:
            fontes_ataque.append(f"Efeitos de Pontaria {bonus_persistente_ataque:+d}")
    total_ataque = (
        resultado_ataque_externo + bonus_condicoes_ataque + bonus_manobra_ataque
        if resultado_ataque_externo is not None
        else dado_ataque + bonus_ataque
    )

    protetor: JogadorPartida | None = None
    novo_alvo: JogadorPartida | None = None
    bonus_condicoes_defesa = 0
    bonus_manobra_defesa = 0
    fontes_manobra_defesa: tuple[str, ...] = ()
    bonus_habilidade_defesa = 0
    fontes_habilidade_defesa: tuple[str, ...] = ()
    bonus_zona_defesa = 0
    if defesa == "Reflexo":
        if redirecionar:
            raise ValueError("Somente um Batedor defensor pode redirecionar o Balaço.")
        nome_defensor = atingido.nome
        bonus_condicoes_defesa = modificador_condicoes_acao(
            partida,
            atingido,
            "balaco",
            oponente=origem.nome,
            gerador=sorteio,
            fontes=fontes_defesa,
        )
        if resultado_defesa_externo is None:
            termos_esquiva = ["+1d4 em testes de Reflexo para esquivar"]
            if atingido.pomo_perseguido:
                termos_esquiva.extend(
                    (
                        "+1d4 em testes de Reflexo para esquivar durante perseguições curtas",
                        "+1d4 em testes de Reflexo para esquivar quando a esquiva fizer parte de uma trajetória contínua",
                    )
                )
            dado_bonus_vassoura_reflexo = rolar_bonus_situacional_vassoura(
                atingido,
                "Reflexo",
                termos_esquiva,
                gerador=sorteio,
                correspondencia_exata=True,
                fontes=fontes_defesa,
            )
        bonus_manobra_defesa, fontes_manobra_defesa = bonus_efeitos_contextuais(
            partida,
            atingido,
            "Reflexo",
            "balaco_defesa",
            oponente=origem.nome,
            consumir=True,
        )
        bonus_habilidade_defesa, fontes_habilidade_defesa = (
            rolar_bonus_habilidades_contextuais(
                atingido,
                "Reflexo",
                "balaco_defesa",
                gerador=sorteio,
            )
        )
        bonus_defesa = (
            atingido.reflexo
            + bonus_efeitos(atingido, "Reflexo")
            + dado_bonus_vassoura_reflexo
            + bonus_condicoes_defesa
            + bonus_manobra_defesa
            + bonus_habilidade_defesa
        )
        if zona_fogo:
            bonus_zona_defesa = -2
            bonus_defesa += bonus_zona_defesa
            fontes_defesa.append("Zona de Fogo -2")
        if resultado_defesa_externo is None:
            fontes_defesa[0:0] = fontes_pericia_base(
                atingido, "Reflexo", atingido.reflexo
            )
            bonus_persistente_defesa = bonus_efeitos(atingido, "Reflexo")
            if bonus_persistente_defesa:
                fontes_defesa.append(f"Efeitos de Reflexo {bonus_persistente_defesa:+d}")
        fontes_defesa.extend(f"Manobra: {fonte}" for fonte in fontes_manobra_defesa)
        fontes_defesa.extend(f"Habilidade: {fonte}" for fonte in fontes_habilidade_defesa)
    elif defesa == "Batedor":
        protetor = encontrar_jogador_partida(partida, defensor)
        if (
            protetor.casa != atingido.casa
            or protetor.posicao != "Batedor"
            or not protetor.ativo
            or not protetor.em_campo
        ):
            raise ValueError("A defesa exige um Batedor ativo do time do alvo.")
        if redirecionar:
            novo_alvo = encontrar_jogador_partida(partida, alvo_redirecionado)
            if (
                novo_alvo.casa != origem.casa
                or not novo_alvo.ativo
                or not novo_alvo.em_campo
            ):
                raise ValueError(
                    "O redirecionamento exige um adversário ativo do Batedor defensor."
                )
        nome_defensor = protetor.nome
        bonus_condicoes_defesa = modificador_condicoes_acao(
            partida,
            protetor,
            "balaco",
            oponente=origem.nome,
            gerador=sorteio,
            fontes=fontes_defesa,
        )
        uso_defesa = "Redirecionamento" if redirecionar else "Interceptacao"
        if resultado_defesa_externo is None:
            bonus_vassoura_defesa, dado_bonus_vassoura_defesa = (
                rolar_bonus_pontaria_condicional(
                    protetor,
                    uso_defesa,
                    gerador=sorteio,
                    fontes=fontes_defesa,
                )
            )
        bonus_defesa = (
            protetor.bonus_teste_posicao
            + bonus_efeitos(protetor, "Pontaria")
            + bonus_vassoura_defesa
            + bonus_condicoes_defesa
        )
        if resultado_defesa_externo is None:
            fontes_defesa[0:0] = fontes_pericia_base(
                protetor, "Pontaria", protetor.bonus_teste_posicao
            )
            bonus_persistente_defesa = bonus_efeitos(protetor, "Pontaria")
            if bonus_persistente_defesa:
                fontes_defesa.append(f"Efeitos de Pontaria {bonus_persistente_defesa:+d}")
    else:
        raise ValueError("Escolha Reflexo ou a defesa de um Batedor.")
    dado_defesa = 0 if resultado_defesa_externo is not None else sorteio.randint(1, 20)
    fontes_defesa.insert(
        0,
        f"Resultado externo {resultado_defesa_externo}"
        if resultado_defesa_externo is not None
        else f"d20 {dado_defesa}",
    )
    total_defesa = (
        resultado_defesa_externo
        + bonus_condicoes_defesa
        + bonus_manobra_defesa
        + bonus_habilidade_defesa
        + bonus_zona_defesa
        if resultado_defesa_externo is not None
        else dado_defesa + bonus_defesa
    )
    atingiu = total_ataque > total_defesa
    zona_fogo_encerrada = False
    if (
        zona_fogo
        and not atingiu
        and defesa == "Batedor"
        and protetor is not None
        and protetor.casa != origem.casa
    ):
        zona_fogo_encerrada = bool(
            encerrar_zona_fogo(
                partida,
                origem.casa,
                f"{protetor.nome} interceptou um dos Balaços",
            )
        )
    redirecionou = False
    dado_reflexo_redirecionado = 0
    total_reflexo_redirecionado = 0
    atingiu_redirecionado = False
    alvo_impacto: JogadorPartida | None = atingido if atingiu else None
    cd_impacto = cd
    nome_efeito_impacto = nome_efeito
    nome_origem_impacto = nome_origem
    if (
        redirecionar
        and not atingiu
        and total_defesa >= total_ataque + 5
        and protetor is not None
        and novo_alvo is not None
    ):
        redirecionou = True
        dado_reflexo_redirecionado = sorteio.randint(1, 20)
        fontes_reflexo_redirecionado.append(f"d20 {dado_reflexo_redirecionado}")
        fontes_reflexo_redirecionado.extend(
            fontes_pericia_base(novo_alvo, "Reflexo", novo_alvo.reflexo)
        )
        bonus_habilidade_redirecionado, fontes_habilidade_redirecionado = (
            rolar_bonus_habilidades_contextuais(
                novo_alvo,
                "Reflexo",
                "contra_ataque",
                gerador=sorteio,
            )
        )
        bonus_condicoes_redirecionado = modificador_condicoes_acao(
            partida,
            novo_alvo,
            "balaco",
            oponente=protetor.nome,
            gerador=sorteio,
            fontes=fontes_reflexo_redirecionado,
        )
        termos_esquiva_redirecionada = ["+1d4 em testes de Reflexo para esquivar"]
        if novo_alvo.pomo_perseguido:
            termos_esquiva_redirecionada.extend(
                (
                    "+1d4 em testes de Reflexo para esquivar durante perseguições curtas",
                    "+1d4 em testes de Reflexo para esquivar quando a esquiva fizer parte de uma trajetória contínua",
                )
            )
        bonus_vassoura_redirecionado = rolar_bonus_situacional_vassoura(
            novo_alvo,
            "Reflexo",
            termos_esquiva_redirecionada,
            gerador=sorteio,
            correspondencia_exata=True,
            fontes=fontes_reflexo_redirecionado,
        )
        bonus_persistente_redirecionado = bonus_efeitos(novo_alvo, "Reflexo")
        if bonus_persistente_redirecionado:
            fontes_reflexo_redirecionado.append(
                f"Efeitos de Reflexo {bonus_persistente_redirecionado:+d}"
            )
        fontes_reflexo_redirecionado.extend(
            f"Habilidade: {fonte}" for fonte in fontes_habilidade_redirecionado
        )
        total_reflexo_redirecionado = (
            dado_reflexo_redirecionado
            + novo_alvo.reflexo
            + bonus_persistente_redirecionado
            + bonus_habilidade_redirecionado
            + bonus_condicoes_redirecionado
            + bonus_vassoura_redirecionado
        )
        atingiu_redirecionado = total_defesa > total_reflexo_redirecionado
        if atingiu_redirecionado:
            alvo_impacto = novo_alvo
            cd_impacto = 12 + protetor.modificador_forca
            nome_efeito_impacto = "Atordoado por Balaço redirecionado"
            nome_origem_impacto = protetor.nome
    dado_fortitude = total_fortitude = 0
    resistiu = False
    progresso_perdido = 0
    bonus_habilidade_fortitude = 0
    fontes_habilidade_fortitude: tuple[str, ...] = ()
    posse_perdida_por = ""
    casa_nova_posse = ""

    if alvo_impacto is not None:
        alvo_impacto.vida_vassoura = max(0, alvo_impacto.vida_vassoura - 1)
        dado_fortitude = sorteio.randint(1, 20)
        bonus_habilidade_fortitude, fontes_habilidade_fortitude = (
            rolar_bonus_habilidades_contextuais(
                alvo_impacto,
                "Fortitude",
                "balaco_impacto",
                gerador=sorteio,
            )
        )
        fontes_fortitude.append(f"d20 {dado_fortitude}")
        fontes_fortitude.extend(
            fontes_pericia_base(alvo_impacto, "Fortitude", alvo_impacto.fortitude)
        )
        fontes_fortitude.extend(
            f"Habilidade: {fonte}" for fonte in fontes_habilidade_fortitude
        )
        total_fortitude = (
            dado_fortitude + alvo_impacto.fortitude + bonus_habilidade_fortitude
        )
        resistiu = total_fortitude >= cd_impacto
        if not resistiu:
            alvo_impacto.efeitos = [
                efeito
                for efeito in alvo_impacto.efeitos
                if not efeito.nome.startswith("Atordoado por")
            ]
            alvo_impacto.efeitos.append(
                EfeitoQuadribol(
                    nome=nome_efeito_impacto,
                    origem=nome_origem_impacto,
                    turnos_restantes=2,
                    cd_recuperacao=cd_impacto,
                )
            )
        if alvo_impacto.posicao == "Apanhador" and (
            not resistiu or alvo_impacto.vida_vassoura == 0
        ):
            alvo_pomo = alvo_impacto.pomo_perseguido
            progresso = partida.progresso_pomos.get(alvo_pomo, {})
            progresso_perdido = progresso.get(alvo_impacto.casa, 0)
            if progresso:
                progresso[alvo_impacto.casa] = 0
            alvo_impacto.perseguiu_pomo_no_turno = False
            alvo_impacto.pomo_perseguido = ""
        if alvo_impacto.vida_vassoura == 0:
            alvo_impacto.ativo = False
        if (
            alvo_impacto.posicao == "Artilheiro"
            and normalizar_rotulo(partida.posse_goles)
            == normalizar_rotulo(alvo_impacto.nome)
        ):
            posse_perdida_por = alvo_impacto.nome
            casa_nova_posse = next(
                casa for casa in partida.casas() if casa != alvo_impacto.casa
            )
            partida.posse_goles = ""
            partida.bonus_passes_gol[alvo_impacto.casa] = 0
            partida.reposicao_goles_casa = casa_nova_posse
            partida.reposicao_goles_jogador = posse_perdida_por

    if redirecionou and novo_alvo is not None:
        if atingiu_redirecionado:
            descricao = (
                f"{nome_defensor} protegeu {atingido.nome} e redirecionou o Balaço de "
                f"{nome_origem} contra {novo_alvo.nome}, que foi atingido."
            )
            if resistiu:
                descricao += (
                    f" {novo_alvo.nome} resistiu com Fortitude {total_fortitude} "
                    f"contra CD {cd_impacto}."
                )
            else:
                descricao += (
                    f" {novo_alvo.nome} ficou Atordoado após Fortitude "
                    f"{total_fortitude} contra CD {cd_impacto}."
                )
        else:
            descricao = (
                f"{nome_defensor} protegeu {atingido.nome} e redirecionou o Balaço de "
                f"{nome_origem} contra {novo_alvo.nome}, que desviou com Reflexo."
            )
    elif not atingiu:
        descricao = (
            f"{nome_defensor} evitou o balaço de {nome_origem}: "
            f"{total_defesa} contra {total_ataque}."
        )
    elif resistiu:
        descricao = (
            f"{alvo_impacto.nome} foi atingido pelo balaço de {nome_origem_impacto}, perdeu 1 de Vida "
            f"da vassoura, mas resistiu ao impacto com Fortitude {total_fortitude} contra CD {cd_impacto}."
        )
    else:
        descricao = (
            f"{alvo_impacto.nome} foi atingido pelo balaço de {nome_origem_impacto}, perdeu 1 de Vida "
            f"da vassoura e ficou Atordoado após Fortitude {total_fortitude} contra CD {cd_impacto}."
        )
        if progresso_perdido:
            descricao += f" Perdeu {progresso_perdido} ponto(s) de progresso do Pomo."
    if alvo_impacto is not None and alvo_impacto.vassoura_quebrada:
        descricao += (
            f" A vassoura de {alvo_impacto.nome} foi **Quebrada** e não pode "
            "continuar sendo usada nesta partida."
        )
    if posse_perdida_por:
        descricao += (
            f" {posse_perdida_por} perdeu a posse da Goles; um Artilheiro da "
            f"{casa_nova_posse} deverá recebê-la."
        )
    partida.eventos.append(
        EventoPartida(
            tipo="balaco",
            casa=protetor.casa if redirecionou and protetor is not None else origem.casa,
            jogador=alvo_impacto.nome if alvo_impacto is not None else atingido.nome,
            valor=progresso_perdido,
            descricao=descricao,
        )
    )
    return ResultadoBalaco(
        atacante=nome_origem,
        alvo=atingido.nome,
        dado_ataque=dado_ataque,
        total_ataque=total_ataque,
        defensor=nome_defensor,
        dado_defesa=dado_defesa,
        total_defesa=total_defesa,
        atingiu=atingiu,
        dado_fortitude=dado_fortitude,
        total_fortitude=total_fortitude,
        cd_fortitude=cd_impacto if alvo_impacto is not None else 0,
        resistiu=resistiu,
        progresso_perdido=progresso_perdido,
        bonus_vassoura_ataque=bonus_vassoura_ataque,
        bonus_vassoura_defesa=bonus_vassoura_defesa,
        dado_bonus_vassoura_ataque=dado_bonus_vassoura_ataque,
        dado_bonus_vassoura_defesa=dado_bonus_vassoura_defesa,
        dado_bonus_vassoura_reflexo=dado_bonus_vassoura_reflexo,
        redirecionou=redirecionou,
        alvo_redirecionado=novo_alvo.nome if novo_alvo is not None else "",
        dado_reflexo_redirecionado=dado_reflexo_redirecionado,
        total_reflexo_redirecionado=total_reflexo_redirecionado,
        atingiu_redirecionado=atingiu_redirecionado,
        rolagem_externa_ataque=resultado_ataque_externo is not None,
        rolagem_externa_defesa=resultado_defesa_externo is not None,
        bonus_manobra_defesa=bonus_manobra_defesa,
        fontes_manobra_defesa=fontes_manobra_defesa,
        bonus_habilidade_defesa=bonus_habilidade_defesa,
        fontes_habilidade_defesa=fontes_habilidade_defesa,
        bonus_habilidade_fortitude=bonus_habilidade_fortitude,
        fontes_habilidade_fortitude=fontes_habilidade_fortitude,
        fontes_ataque=tuple(fontes_ataque),
        fontes_defesa=tuple(fontes_defesa),
        fontes_fortitude=tuple(fontes_fortitude),
        fontes_reflexo_redirecionado=tuple(fontes_reflexo_redirecionado),
        zona_fogo=zona_fogo,
        zona_fogo_encerrada=zona_fogo_encerrada,
        posse_perdida_por=posse_perdida_por,
        casa_nova_posse=casa_nova_posse,
    )


def testar_recuperacao(
    partida: PartidaQuadribol,
    jogador: str,
    *,
    resultado_externo: int | None = None,
    gerador: random.Random | None = None,
    fontes: list[str] | None = None,
) -> tuple[int, int, bool]:
    _garantir_sem_penalti(partida, permitir_atordoado=True)
    alvo = encontrar_jogador_partida(partida, jogador)
    atual = partida.jogador_atual()
    if atual is None or atual.nome != alvo.nome:
        raise ValueError("O Teste de Recuperação só pode ser realizado no próprio turno.")
    efeito = next(
        (item for item in alvo.efeitos if item.nome.startswith("Atordoado por")),
        None,
    )
    if efeito is None:
        raise ValueError("O jogador não está Atordoado.")
    if resultado_externo is not None and resultado_externo < 0:
        raise ValueError("O resultado externo não pode ser negativo.")
    detalhes = fontes if fontes is not None else []
    dado = 0 if resultado_externo is not None else (gerador or random.SystemRandom()).randint(1, 20)
    if resultado_externo is not None:
        detalhes.append(f"Resultado externo {resultado_externo:+d}")
    else:
        detalhes.append(f"d20 ({dado})")
        detalhes.extend(fontes_pericia_base(alvo, "Fortitude", alvo.fortitude))
    total = resultado_externo if resultado_externo is not None else dado + alvo.fortitude
    sucesso = total >= efeito.cd_recuperacao
    if sucesso:
        alvo.efeitos.remove(efeito)
    partida.eventos.append(
        EventoPartida(
            tipo="recuperacao",
            jogador=alvo.nome,
            descricao=(
                f"{alvo.nome} obteve {total} contra "
                f"CD {efeito.cd_recuperacao} e {'se recuperou' if sucesso else 'permaneceu atordoado'}."
            ),
        )
    )
    return dado, total, sucesso


testar_recuperacao.__test__ = False


def adicionar_efeito(
    partida: PartidaQuadribol,
    jogador: str,
    nome: str,
    origem: str,
    teste: str,
    bonus: int,
    turnos: int,
) -> EfeitoQuadribol:
    _garantir_sem_penalti(partida)
    if turnos <= 0:
        raise ValueError("A duração do efeito precisa ser positiva.")
    alvo = encontrar_jogador_partida(partida, jogador)
    efeito = EfeitoQuadribol(
        nome=nome.strip(),
        origem=origem.strip(),
        teste=teste.strip(),
        bonus=bonus,
        turnos_restantes=turnos,
    )
    alvo.efeitos.append(efeito)
    partida.eventos.append(
        EventoPartida(
            tipo="efeito",
            jogador=alvo.nome,
            descricao=f"{alvo.nome} recebeu {efeito.nome} por {turnos} turno(s).",
        )
    )
    return efeito


def adicionar_condicao_catalogada(
    partida: PartidaQuadribol,
    nome: str,
    jogadores: Iterable[str],
    *,
    intensidade: str = "",
    gatilho: str = "",
    origem: str = "",
    gerador: random.Random | None = None,
) -> list[EfeitoQuadribol]:
    _garantir_sem_penalti(partida)
    condicao = encontrar_condicao(nome)
    alvos = [encontrar_jogador_partida(partida, jogador) for jogador in jogadores]
    if not alvos:
        raise ValueError("Escolha pelo menos um jogador para receber a condição.")
    if condicao.multiplos_alvos and len(alvos) < 2:
        raise ValueError(f"{condicao.nome} exige pelo menos dois jogadores.")
    if not condicao.multiplos_alvos and len(alvos) != 1:
        raise ValueError(f"{condicao.nome} deve ser aplicada a um jogador por vez.")
    if condicao.exige_rival and len(alvos) != 2:
        raise ValueError("Rivalidade exige exatamente dois jogadores.")
    if condicao.exige_rival and alvos[0].casa == alvos[1].casa:
        raise ValueError("Rivalidade deve ligar jogadores de equipes adversárias.")
    if condicao.exige_intensidade:
        if intensidade not in INTENSIDADES_CONDICAO:
            raise ValueError("Escolha a intensidade da condição.")
        cd = INTENSIDADES_CONDICAO[intensidade]
    else:
        if intensidade:
            raise ValueError("Efeitos positivos não possuem intensidade.")
        cd = 0
    gatilho = gatilho.strip()
    if condicao.exige_gatilho and not gatilho:
        raise ValueError("Informe o gatilho que encerrará este efeito.")
    sorteio = gerador or random.SystemRandom()
    if condicao.duracao_tipo == "rodadas_1d4":
        rodadas = sorteio.randint(1, 4)
        duracao_tipo = "rodadas"
    else:
        rodadas = condicao.rodadas
        duracao_tipo = condicao.duracao_tipo
    comeca_na_proxima = normalizar_rotulo(condicao.nome) in {
        "abalado",
        "confiante",
        "determinado",
    }
    rodada_inicial = partida.rodada + 1 if comeca_na_proxima else partida.rodada
    rodada_final = partida.rodada + rodadas if duracao_tipo == "rodadas" else 0
    if normalizar_rotulo(condicao.nome) == "tempo meteorologico":
        for participante in partida.jogadores:
            participante.efeitos = [
                efeito
                for efeito in participante.efeitos
                if normalizar_rotulo(efeito.nome) != "tempo meteorologico"
            ]
            participante.resultado_tempo_externo = None
            participante.penalidade_tempo_preparada = None
            participante.cd_tempo_preparada = 0
            participante.fonte_tempo_preparada = ""
    criados: list[EfeitoQuadribol] = []
    for indice, alvo in enumerate(alvos):
        rival = ""
        if condicao.exige_rival:
            rival = alvos[1 - indice].nome
        efeito = EfeitoQuadribol(
            nome=condicao.nome,
            origem=origem.strip() or condicao.origem,
            teste=condicao.teste_resistencia,
            turnos_restantes=0,
            categoria=condicao.categoria,
            intensidade=intensidade,
            cd_resistencia=cd,
            dado_modificador=condicao.dado_modificador,
            duracao_tipo=duracao_tipo,
            rodada_final=rodada_final,
            rodada_inicial=rodada_inicial,
            gatilho=gatilho,
            rival=rival,
            descricao=condicao.descricao,
        )
        alvo.efeitos = [
            existente
            for existente in alvo.efeitos
            if not (
                normalizar_rotulo(existente.nome) == normalizar_rotulo(efeito.nome)
                and normalizar_rotulo(existente.rival) == normalizar_rotulo(efeito.rival)
            )
        ]
        alvo.efeitos.append(efeito)
        criados.append(efeito)
    if duracao_tipo == "rodadas":
        duracao = f"até o fim da rodada {rodada_final}"
    elif duracao_tipo == "gatilho":
        duracao = f'até acontecer: "{gatilho}"'
    else:
        duracao = "até ser removida"
    intensidade_texto = f" ({intensidade}, CD {cd})" if intensidade else ""
    nomes = ", ".join(alvo.nome for alvo in alvos)
    origem_efeito = origem.strip() or condicao.origem
    partida.eventos.append(
        EventoPartida(
            tipo="efeito",
            jogador=nomes,
            descricao=(
                f"{condicao.nome}{intensidade_texto} aplicada a {nomes} "
                f"por {origem_efeito} {duracao}."
            ),
        )
    )
    return criados


def remover_efeito(
    partida: PartidaQuadribol,
    jogador: str,
    indice: int,
) -> EfeitoQuadribol:
    _garantir_sem_penalti(partida)
    alvo = encontrar_jogador_partida(partida, jogador)
    if indice < 0 or indice >= len(alvo.efeitos):
        raise ValueError("O efeito selecionado não está mais ativo.")
    efeito = alvo.efeitos[indice]
    if normalizar_rotulo(efeito.nome) == "tempo meteorologico":
        removidos = 0
        for participante in partida.jogadores:
            anteriores = len(participante.efeitos)
            participante.efeitos = [
                existente
                for existente in participante.efeitos
                if not (
                    normalizar_rotulo(existente.nome) == "tempo meteorologico"
                    and normalizar_rotulo(existente.origem)
                    == normalizar_rotulo(efeito.origem)
                )
            ]
            participante.resultado_tempo_externo = None
            participante.penalidade_tempo_preparada = None
            participante.cd_tempo_preparada = 0
            participante.fonte_tempo_preparada = ""
            removidos += anteriores - len(participante.efeitos)
        partida.eventos.append(
            EventoPartida(
                tipo="fim_efeito",
                jogador=alvo.nome,
                valor=removidos,
                descricao=(
                    f"Tempo Meteorológico foi encerrado para todos os "
                    f"{removidos} jogador(es) afetados."
                ),
            )
        )
        return efeito
    if (
        normalizar_rotulo(efeito.nome) == "zona de fogo"
        and normalizar_rotulo(efeito.contexto) == "zona_fogo"
    ):
        encerrar_zona_fogo(partida, alvo.casa, f"{alvo.nome} deixou de sustentá-la")
        return efeito
    if normalizar_rotulo(efeito.nome) == "formacao muralha de ogro":
        casa_formacao = efeito.origem.rsplit(":", 1)[-1].strip()
        encerrar_muralha_ogro(
            partida,
            casa_formacao,
            f"{alvo.nome} deixou de sustentá-la",
        )
        return efeito
    if normalizar_rotulo(efeito.nome) == "formacao de ataque hawkshead (cabeca de falcao)":
        casa_formacao = efeito.origem.rsplit(":", 1)[-1].strip()
        encerrar_hawkshead(
            partida,
            casa_formacao,
            f"{alvo.nome} deixou de sustentá-la",
        )
        return efeito
    alvo.efeitos.pop(indice)
    partida.eventos.append(
        EventoPartida(
            tipo="fim_efeito",
            jogador=alvo.nome,
            descricao=f"{efeito.nome} foi encerrado para {alvo.nome}.",
        )
    )
    return efeito


def rolar_manobra(
    partida: PartidaQuadribol,
    manobra: ManobraQuadribol,
    coordenador: str,
    *,
    resultado_externo: int | None = None,
    gerador: random.Random | None = None,
    fontes: list[str] | None = None,
) -> tuple[int, int, bool]:
    _garantir_sem_penalti(partida)
    jogador = encontrar_jogador_partida(partida, coordenador)
    atual = partida.jogador_atual()
    if atual is None:
        raise ValueError("Não há jogador no turno atual.")
    if not jogador.ativo or not jogador.em_campo:
        raise ValueError("Quem executa a manobra precisa estar ativo e em campo.")
    if manobra_exige_coordenador(manobra):
        if jogador.casa != atual.casa:
            raise ValueError("O Coordenador da manobra precisa pertencer ao time do turno atual.")
    elif jogador.nome != atual.nome:
        raise ValueError("Uma manobra individual deve ser executada pelo jogador em destaque.")
    if jogador.quadribol < manobra.requisito_quadribol:
        raise ValueError(
            f"{jogador.nome} precisa de pelo menos {manobra.requisito_quadribol:+d} em Quadribol."
        )
    if manobra.posicoes and jogador.posicao not in manobra.posicoes:
        raise ValueError("A posição do coordenador não pode executar esta manobra.")
    if manobra.cd == 0:
        detalhes = fontes if fontes is not None else []
        detalhes.append("Execução automática — sem teste")
        partida.eventos.append(
            EventoPartida(
                tipo="manobra",
                casa=jogador.casa,
                jogador=jogador.nome,
                descricao=(
                    f"{jogador.nome} organizou {manobra.nome} sem teste de execução."
                ),
            )
        )
        return 0, 0, True
    if resultado_externo is not None and resultado_externo < 0:
        raise ValueError("O resultado externo não pode ser negativo.")
    sorteio = gerador or random.SystemRandom()
    detalhes = fontes if fontes is not None else []
    bonus_condicoes = modificador_condicoes_acao(
        partida,
        jogador,
        "manobra",
        gerador=sorteio,
        coletiva=manobra_exige_coordenador(manobra),
        fontes=detalhes,
    )
    bonus_quadribol = bonus_efeitos(jogador, "Quadribol")
    bonus_vassoura = 0
    if resultado_externo is None:
        termos_vassoura = [
            "testes de voo, ao executar manobras",
            "testes de voo para executar manobras",
            "testes de voo envolvendo manobras",
        ]
        if manobra.cd <= 12:
            termos_vassoura.append("testes de voo envolvendo manobras simples")
        texto_manobra = normalizar_rotulo(
            f"{manobra.descricao} {manobra.execucao}"
        )
        if "velocidade" in texto_manobra or "mergulho" in texto_manobra:
            termos_vassoura.append("testes de voo envolvendo manobras em alta velocidade")
        bonus_vassoura = rolar_bonus_situacional_vassoura(
            jogador,
            "Voo",
            termos_vassoura,
            gerador=sorteio,
            fontes=detalhes,
        )
        detalhes.insert(0, f"Quadribol da ficha {jogador.quadribol:+d}")
        if bonus_quadribol:
            detalhes.append(f"Efeitos de Quadribol {bonus_quadribol:+d}")
    dado = 0 if resultado_externo is not None else sorteio.randint(1, 20)
    detalhes.insert(
        0,
        f"Resultado externo {resultado_externo}"
        if resultado_externo is not None
        else f"d20 {dado}",
    )
    total = (
        resultado_externo + bonus_condicoes
        if resultado_externo is not None
        else (
            dado
            + jogador.quadribol
            + bonus_quadribol
            + bonus_vassoura
            + bonus_condicoes
        )
    )
    sucesso = total >= manobra.cd
    partida.eventos.append(
        EventoPartida(
            tipo="manobra",
            casa=jogador.casa,
            jogador=jogador.nome,
            descricao=(
                f"{jogador.nome} coordenou {manobra.nome}: resultado {total} "
                f"contra CD {manobra.cd} — {'sucesso' if sucesso else 'falha'}."
            ),
        )
    )
    return dado, total, sucesso


def reservas_disponiveis(
    partida: PartidaQuadribol,
    jogador: str,
) -> list[JogadorPartida]:
    titular = encontrar_jogador_partida(partida, jogador)
    return [
        item
        for item in partida.jogadores
        if item.casa == titular.casa
        and item.posicao == titular.posicao
        and item.situacao == "Reserva"
        and not item.em_campo
        and item.ativo
        and not item.expulso
    ]


def _expulsar_e_substituir(
    partida: PartidaQuadribol,
    jogador: JogadorPartida,
    reserva_nome: str = "",
) -> str:
    reservas = reservas_disponiveis(partida, jogador.nome)
    reserva: JogadorPartida | None = None
    if reserva_nome:
        reserva = encontrar_jogador_partida(partida, reserva_nome)
        if reserva not in reservas:
            raise ValueError("O reserva escolhido não pode substituir este jogador.")
    elif len(reservas) == 1:
        reserva = reservas[0]
    elif len(reservas) > 1:
        raise ValueError("Escolha qual reserva da mesma posição entrará em campo.")

    jogador.expulso = True
    jogador.ativo = False
    jogador.em_campo = False
    if jogador.posicao == "Apanhador":
        progresso = partida.progresso_pomos.get(jogador.pomo_perseguido, {})
        if progresso:
            progresso[jogador.casa] = 0
        jogador.pomo_perseguido = ""
    if reserva is None:
        return ""

    indice_titular = partida.jogadores.index(jogador)
    indice_reserva = partida.jogadores.index(reserva)
    iniciativa_slot = (
        jogador.iniciativa_dado,
        jogador.iniciativa_bonus,
        jogador.iniciativa_total,
    )
    partida.jogadores[indice_titular], partida.jogadores[indice_reserva] = (
        reserva,
        jogador,
    )
    reserva.iniciativa_dado, reserva.iniciativa_bonus, reserva.iniciativa_total = iniciativa_slot
    reserva.em_campo = True
    reserva.ativo = reserva.vida_vassoura > 0
    return reserva.nome


def registrar_falta(
    partida: PartidaQuadribol,
    infrator: str,
    falta: FaltaQuadribol,
    *,
    reserva: str = "",
) -> RegistroFalta:
    _garantir_sem_penalti(partida)
    jogador = encontrar_jogador_partida(partida, infrator)
    if not jogador.ativo or not jogador.em_campo:
        raise ValueError("O infrator precisa estar ativo em campo.")
    if jogador.posicao not in falta.posicoes:
        raise ValueError(f"{falta.nome} não pode ser cometida por {jogador.posicao}.")
    casa_prejudicada = next(casa for casa in partida.casas() if casa != jogador.casa)
    cartao = falta.cartao
    if cartao == "Amarelo":
        jogador.cartoes_amarelos += 1
        if jogador.cartoes_amarelos >= 2:
            cartao = "Vermelho"
    reserva_usado = ""
    if cartao == "Vermelho":
        reserva_usado = _expulsar_e_substituir(partida, jogador, reserva)

    if falta.consequencia == "Pênalti":
        partida.penalti_casa = casa_prejudicada
        partida.penalti_motivo = falta.nome
        partida.penalti_infrator = jogador.nome
    elif falta.consequencia == "Derrota automática":
        partida.vencedor_forcado = casa_prejudicada
        partida.estado = "aguardando_confirmacao"
    else:
        raise ValueError("A consequência desta falta não é reconhecida.")

    descricao = (
        f"{jogador.nome} cometeu {falta.nome}. Punição: "
        f"{'sem cartão' if cartao == 'Nenhum' else f'cartão {cartao.lower()}'}; "
        f"{falta.consequencia.lower()} para {casa_prejudicada}."
    )
    if reserva_usado:
        descricao += f" {reserva_usado} entrou como reserva de {jogador.posicao}."
    partida.eventos.append(
        EventoPartida(
            tipo="falta",
            casa=jogador.casa,
            jogador=jogador.nome,
            descricao=descricao,
        )
    )
    return RegistroFalta(
        falta=falta,
        infrator=jogador.nome,
        casa_prejudicada=casa_prejudicada,
        cartao_aplicado=cartao,
        reserva=reserva_usado,
    )


def resolver_penalti(
    partida: PartidaQuadribol,
    artilheiro: str,
    *,
    resultado_artilheiro_externo: int | None = None,
    resultado_goleiro_externo: int | None = None,
    gerador: random.Random | None = None,
) -> ResultadoPenalti:
    _garantir_ativa(partida)
    if not partida.penalti_casa:
        raise ValueError("Não há pênalti pendente.")
    cobrador = encontrar_jogador_partida(partida, artilheiro)
    if (
        cobrador.casa != partida.penalti_casa
        or cobrador.posicao != "Artilheiro"
        or not cobrador.ativo
        or not cobrador.em_campo
    ):
        raise ValueError("Escolha um Artilheiro ativo da equipe beneficiada.")
    adversaria = next(casa for casa in partida.casas() if casa != partida.penalti_casa)
    goleiros = [
        item
        for item in partida.jogadores
        if item.casa == adversaria
        and item.posicao == "Goleiro"
        and item.ativo
        and item.em_campo
    ]
    if len(goleiros) != 1:
        raise ValueError("A equipe adversária precisa possuir um Goleiro ativo.")
    goleiro = goleiros[0]
    sorteio = gerador or random.SystemRandom()
    if resultado_artilheiro_externo is not None and resultado_artilheiro_externo < 0:
        raise ValueError("O resultado externo do Artilheiro não pode ser negativo.")
    if resultado_goleiro_externo is not None and resultado_goleiro_externo < 0:
        raise ValueError("O resultado externo do Goleiro não pode ser negativo.")
    dado_artilheiro = 0 if resultado_artilheiro_externo is not None else sorteio.randint(1, 20)
    fontes_artilheiro: list[str] = [
        f"Resultado externo {resultado_artilheiro_externo}"
        if resultado_artilheiro_externo is not None
        else f"d20 {dado_artilheiro}"
    ]
    bonus_condicoes_artilheiro = modificador_condicoes_acao(
        partida,
        cobrador,
        "gol",
        oponente=goleiro.nome,
        gerador=sorteio,
        fontes=fontes_artilheiro,
    )
    bonus_vassoura_artilheiro = dado_bonus_vassoura_artilheiro = 0
    bonus_artilheiro = 0
    if resultado_artilheiro_externo is None:
        fontes_artilheiro[1:1] = fontes_pericia_base(
            cobrador, "Pontaria", cobrador.bonus_teste_posicao
        )
        bonus_vassoura_artilheiro, dado_bonus_vassoura_artilheiro = (
            rolar_bonus_pontaria_condicional(
                cobrador,
                "Finalizacao",
                gerador=sorteio,
                fontes=fontes_artilheiro,
            )
        )
        bonus_persistente_artilheiro = bonus_efeitos(cobrador, "Pontaria")
        if bonus_persistente_artilheiro:
            fontes_artilheiro.append(
                f"Efeitos de Pontaria {bonus_persistente_artilheiro:+d}"
            )
        bonus_artilheiro = (
            cobrador.bonus_teste_posicao
            + bonus_persistente_artilheiro
            + bonus_vassoura_artilheiro
            + bonus_condicoes_artilheiro
        )
    total_artilheiro = (
        resultado_artilheiro_externo + bonus_condicoes_artilheiro
        if resultado_artilheiro_externo is not None
        else dado_artilheiro + bonus_artilheiro
    )
    dado_goleiro = 0 if resultado_goleiro_externo is not None else sorteio.randint(1, 20)
    fontes_goleiro: list[str] = [
        f"Resultado externo {resultado_goleiro_externo}"
        if resultado_goleiro_externo is not None
        else f"d20 {dado_goleiro}"
    ]
    bonus_condicoes_goleiro = modificador_condicoes_acao(
        partida,
        goleiro,
        "gol",
        oponente=cobrador.nome,
        gerador=sorteio,
        fontes=fontes_goleiro,
    )
    dado_bonus_vassoura_goleiro = 0
    bonus_goleiro = 0
    if resultado_goleiro_externo is None:
        fontes_goleiro[1:1] = fontes_pericia_base(
            goleiro, "Reflexo", goleiro.bonus_teste_posicao
        )
        dado_bonus_vassoura_goleiro = rolar_bonus_situacional_vassoura(
            goleiro,
            "Reflexo",
            ("defender os aros", "interceptar a goles"),
            gerador=sorteio,
            fontes=fontes_goleiro,
        )
        bonus_persistente_goleiro = bonus_efeitos(goleiro, "Reflexo")
        if bonus_persistente_goleiro:
            fontes_goleiro.append(f"Efeitos de Reflexo {bonus_persistente_goleiro:+d}")
        bonus_goleiro = (
            goleiro.bonus_teste_posicao
            + bonus_persistente_goleiro
            + dado_bonus_vassoura_goleiro
            + bonus_condicoes_goleiro
        )
    total_goleiro = (
        resultado_goleiro_externo + bonus_condicoes_goleiro
        if resultado_goleiro_externo is not None
        else dado_goleiro + bonus_goleiro
    )
    gol = total_artilheiro > total_goleiro
    motivo = partida.penalti_motivo
    if gol:
        partida.gols[cobrador.casa] += 1
        descricao = (
            f"{cobrador.nome} converteu o pênalti de {motivo}: "
            f"{total_artilheiro} contra {total_goleiro}."
        )
    else:
        descricao = (
            f"{goleiro.nome} defendeu o pênalti de {motivo}: "
            f"{total_goleiro} contra {total_artilheiro}."
        )
    partida.eventos.append(
        EventoPartida(
            tipo="penalti",
            casa=cobrador.casa,
            jogador=cobrador.nome,
            valor=1 if gol else 0,
            descricao=descricao,
        )
    )
    partida.penalti_casa = ""
    partida.penalti_motivo = ""
    partida.penalti_infrator = ""
    return ResultadoPenalti(
        artilheiro=cobrador.nome,
        goleiro=goleiro.nome,
        dado_artilheiro=dado_artilheiro,
        total_artilheiro=total_artilheiro,
        dado_goleiro=dado_goleiro,
        total_goleiro=total_goleiro,
        gol=gol,
        bonus_vassoura_artilheiro=bonus_vassoura_artilheiro,
        dado_bonus_vassoura_artilheiro=dado_bonus_vassoura_artilheiro,
        dado_bonus_vassoura_goleiro=dado_bonus_vassoura_goleiro,
        rolagem_externa_artilheiro=resultado_artilheiro_externo is not None,
        rolagem_externa_goleiro=resultado_goleiro_externo is not None,
        fontes_artilheiro=tuple(fontes_artilheiro),
        fontes_goleiro=tuple(fontes_goleiro),
    )


def resolver_tentativa_gol(
    partida: PartidaQuadribol,
    artilheiro: str,
    *,
    resultado_artilheiro_externo: int | None = None,
    resultado_goleiro_externo: int | None = None,
    resultado_percepcao_externo: int | None = None,
    gerador: random.Random | None = None,
) -> ResultadoGol:
    _garantir_sem_penalti(partida)
    cobrador = encontrar_jogador_partida(partida, artilheiro)
    atual = partida.jogador_atual()
    if (
        atual is None
        or atual.nome != cobrador.nome
        or cobrador.posicao != "Artilheiro"
        or not cobrador.ativo
        or not cobrador.em_campo
    ):
        raise ValueError("Somente o Artilheiro em destaque pode tentar marcar um gol.")
    if partida.posse_goles and partida.posse_goles != cobrador.nome:
        raise ValueError("Somente o Artilheiro em posse da Goles pode tentar marcar um gol.")
    if not partida.posse_goles:
        # Compatibilidade com partidas antigas, anteriores ao sistema de posse.
        partida.posse_goles = cobrador.nome
    goleiros = [
        item
        for item in partida.jogadores
        if item.casa != cobrador.casa
        and item.posicao == "Goleiro"
        and item.ativo
        and item.em_campo
    ]
    if len(goleiros) != 1:
        raise ValueError("A equipe adversária precisa possuir um Goleiro ativo.")
    goleiro = goleiros[0]
    if resultado_artilheiro_externo is not None and resultado_artilheiro_externo < 0:
        raise ValueError("O resultado externo do Artilheiro não pode ser negativo.")
    if resultado_goleiro_externo is not None and resultado_goleiro_externo < 0:
        raise ValueError("O resultado externo do Goleiro não pode ser negativo.")
    if resultado_percepcao_externo is not None and resultado_percepcao_externo < 0:
        raise ValueError("O resultado externo de Percepção não pode ser negativo.")
    sorteio = gerador or random.SystemRandom()
    bonus_passes_artilheiro = partida.bonus_passes_gol.get(cobrador.casa, 0)
    dado_artilheiro = 0 if resultado_artilheiro_externo is not None else sorteio.randint(1, 20)
    fontes_artilheiro: list[str] = [
        f"Resultado externo {resultado_artilheiro_externo}"
        if resultado_artilheiro_externo is not None
        else f"d20 {dado_artilheiro}"
    ]
    bonus_condicoes_artilheiro = modificador_condicoes_acao(
        partida,
        cobrador,
        "gol",
        oponente=goleiro.nome,
        gerador=sorteio,
        fontes=fontes_artilheiro,
    )
    bonus_manobra_artilheiro, fontes_manobra_artilheiro = bonus_efeitos_contextuais(
        partida,
        cobrador,
        "Pontaria",
        "gol",
        oponente=goleiro.nome,
        consumir=True,
    )
    bonus_vassoura_artilheiro = dado_bonus_vassoura_artilheiro = 0
    bonus_artilheiro = 0
    if resultado_artilheiro_externo is None:
        fontes_artilheiro[1:1] = fontes_pericia_base(
            cobrador, "Pontaria", cobrador.bonus_teste_posicao
        )
        bonus_vassoura_artilheiro, dado_bonus_vassoura_artilheiro = (
            rolar_bonus_pontaria_condicional(
                cobrador,
                "Finalizacao",
                gerador=sorteio,
                fontes=fontes_artilheiro,
            )
        )
        bonus_persistente_artilheiro = bonus_efeitos(cobrador, "Pontaria")
        if bonus_persistente_artilheiro:
            fontes_artilheiro.append(
                f"Efeitos de Pontaria {bonus_persistente_artilheiro:+d}"
            )
        bonus_artilheiro = (
            cobrador.bonus_teste_posicao
            + bonus_persistente_artilheiro
            + bonus_vassoura_artilheiro
            + bonus_condicoes_artilheiro
            + bonus_manobra_artilheiro
            + bonus_passes_artilheiro
        )
    total_artilheiro = (
        resultado_artilheiro_externo
        + bonus_condicoes_artilheiro
        + bonus_manobra_artilheiro
        + bonus_passes_artilheiro
        if resultado_artilheiro_externo is not None
        else dado_artilheiro + bonus_artilheiro
    )
    if bonus_passes_artilheiro:
        fontes_artilheiro.append(
            f"Passes bem-sucedidos {bonus_passes_artilheiro:+d}"
        )
    fontes_artilheiro.extend(f"Manobra: {fonte}" for fonte in fontes_manobra_artilheiro)
    efeito_mergulho = next(
        (
            efeito
            for efeito in cobrador.efeitos
            if normalizar_rotulo(efeito.contexto) == "mergulho_falcao"
        ),
        None,
    )
    mergulho_falcao = efeito_mergulho is not None
    dado_percepcao = total_percepcao = 0
    cd_percepcao = 0.0
    passou_percepcao = True
    fontes_percepcao: list[str] = []
    if efeito_mergulho is not None:
        cd_percepcao = float(efeito_mergulho.cd_resistencia)
        dado_percepcao = (
            0
            if resultado_percepcao_externo is not None
            else sorteio.randint(1, 20)
        )
        percepcao_goleiro = _pericia_jogador(goleiro, "Percepção")
        if resultado_percepcao_externo is not None:
            total_percepcao = resultado_percepcao_externo
            fontes_percepcao.append(
                f"Resultado externo de Percepção {resultado_percepcao_externo}"
            )
        else:
            total_percepcao = dado_percepcao + percepcao_goleiro
            fontes_percepcao.extend(
                (f"d20 {dado_percepcao}", f"Percepção da ficha {percepcao_goleiro:+d}")
            )
        passou_percepcao = total_percepcao >= cd_percepcao
        cobrador.efeitos.remove(efeito_mergulho)
        partida.eventos.append(
            EventoPartida(
                tipo="fim_efeito",
                jogador=cobrador.nome,
                descricao=f"{efeito_mergulho.nome} foi resolvido no arremesso.",
            )
        )

    dado_goleiro = 0
    total_goleiro = 0
    fontes_goleiro: list[str] = []
    bonus_condicoes_goleiro = 0
    bonus_manobra_goleiro = 0
    fontes_manobra_goleiro: tuple[str, ...] = ()
    bonus_habilidade_goleiro = 0
    fontes_habilidade_goleiro: tuple[str, ...] = ()
    dado_bonus_vassoura_goleiro = 0
    if passou_percepcao:
        dado_goleiro = (
            0 if resultado_goleiro_externo is not None else sorteio.randint(1, 20)
        )
        fontes_goleiro.append(
            f"Resultado externo {resultado_goleiro_externo}"
            if resultado_goleiro_externo is not None
            else f"d20 {dado_goleiro}"
        )
        bonus_condicoes_goleiro = modificador_condicoes_acao(
            partida,
            goleiro,
            "gol",
            oponente=cobrador.nome,
            gerador=sorteio,
            fontes=fontes_goleiro,
        )
        bonus_manobra_goleiro, fontes_manobra_goleiro = bonus_efeitos_contextuais(
            partida,
            goleiro,
            "Reflexo",
            "gol",
            oponente=cobrador.nome,
            consumir=True,
        )
        bonus_habilidade_goleiro, fontes_habilidade_goleiro = (
            rolar_bonus_habilidades_contextuais(
                goleiro,
                "Reflexo",
                "gol_defesa",
                gerador=sorteio,
            )
        )
        bonus_goleiro = 0
        if resultado_goleiro_externo is None:
            fontes_goleiro[1:1] = fontes_pericia_base(
                goleiro, "Reflexo", goleiro.bonus_teste_posicao
            )
            dado_bonus_vassoura_goleiro = rolar_bonus_situacional_vassoura(
                goleiro,
                "Reflexo",
                ("defender os aros", "interceptar a goles"),
                gerador=sorteio,
                fontes=fontes_goleiro,
            )
            bonus_persistente_goleiro = bonus_efeitos(goleiro, "Reflexo")
            if bonus_persistente_goleiro:
                fontes_goleiro.append(
                    f"Efeitos de Reflexo {bonus_persistente_goleiro:+d}"
                )
            bonus_goleiro = (
                goleiro.bonus_teste_posicao
                + bonus_persistente_goleiro
                + dado_bonus_vassoura_goleiro
                + bonus_condicoes_goleiro
                + bonus_manobra_goleiro
                + bonus_habilidade_goleiro
            )
        total_goleiro = (
            resultado_goleiro_externo
            + bonus_condicoes_goleiro
            + bonus_manobra_goleiro
            + bonus_habilidade_goleiro
            if resultado_goleiro_externo is not None
            else dado_goleiro + bonus_goleiro
        )
        fontes_goleiro.extend(
            f"Manobra: {fonte}" for fonte in fontes_manobra_goleiro
        )
        fontes_goleiro.extend(
            f"Habilidade: {fonte}" for fonte in fontes_habilidade_goleiro
        )
    else:
        fontes_goleiro.append(
            "Mergulho do Falcão — Goleiro enganado; defesa perdida"
        )
    gol = not passou_percepcao or total_artilheiro > total_goleiro
    # O bônus pertence a uma única sequência ofensiva e é consumido pela
    # tentativa, independentemente de ela terminar em gol ou defesa.
    partida.bonus_passes_gol[cobrador.casa] = 0
    if gol:
        partida.gols[cobrador.casa] += 1
        partida.posse_goles = ""
        descricao = (
            f"{cobrador.nome} marcou após o Mergulho do Falcão enganar {goleiro.nome}: "
            f"Percepção {total_percepcao:g} contra CD {cd_percepcao:g}."
            if mergulho_falcao and not passou_percepcao
            else (
                f"{cobrador.nome} marcou: {total_artilheiro} contra {total_goleiro} de "
                f"{goleiro.nome}."
            )
        )
    else:
        partida.posse_goles = goleiro.nome
        descricao = (
            f"{goleiro.nome} defendeu a tentativa de {cobrador.nome}: "
            f"{total_goleiro} contra {total_artilheiro}."
        )
    partida.eventos.append(
        EventoPartida(
            tipo="gol" if gol else "defesa_gol",
            casa=cobrador.casa,
            jogador=cobrador.nome,
            alvo=goleiro.nome,
            valor=1 if gol else 0,
            descricao=descricao,
        )
    )
    return ResultadoGol(
        artilheiro=cobrador.nome,
        goleiro=goleiro.nome,
        dado_artilheiro=dado_artilheiro,
        total_artilheiro=total_artilheiro,
        dado_goleiro=dado_goleiro,
        total_goleiro=total_goleiro,
        gol=gol,
        bonus_vassoura_artilheiro=bonus_vassoura_artilheiro,
        dado_bonus_vassoura_artilheiro=dado_bonus_vassoura_artilheiro,
        dado_bonus_vassoura_goleiro=dado_bonus_vassoura_goleiro,
        rolagem_externa_artilheiro=resultado_artilheiro_externo is not None,
        rolagem_externa_goleiro=resultado_goleiro_externo is not None,
        bonus_manobra_artilheiro=bonus_manobra_artilheiro,
        bonus_passes_artilheiro=bonus_passes_artilheiro,
        bonus_manobra_goleiro=bonus_manobra_goleiro,
        fontes_manobra_artilheiro=fontes_manobra_artilheiro,
        fontes_manobra_goleiro=fontes_manobra_goleiro,
        bonus_habilidade_goleiro=bonus_habilidade_goleiro,
        fontes_habilidade_goleiro=fontes_habilidade_goleiro,
        fontes_artilheiro=tuple(fontes_artilheiro),
        fontes_goleiro=tuple(fontes_goleiro),
        mergulho_falcao=mergulho_falcao,
        dado_percepcao=dado_percepcao,
        total_percepcao=total_percepcao,
        cd_percepcao=cd_percepcao,
        passou_percepcao=passou_percepcao,
        fontes_percepcao=tuple(fontes_percepcao),
    )


def preparar_encerramento(partida: PartidaQuadribol) -> None:
    if partida.estado == "intervalo":
        partida.tempo = 2
        partida.rodada_tempo = 1
        partida.estado = "ativa"
        for jogador in partida.jogadores:
            jogador.perseguiu_pomo_no_turno = False
            jogador.pomo_perseguido = ""
        partida.eventos.append(
            EventoPartida(
                tipo="inicio_segundo_tempo",
                descricao="O intervalo terminou. Começou o 2º tempo da partida.",
            )
        )
        return
    _garantir_sem_penalti(partida)
    if partida.tempo == 1:
        partida.estado = "intervalo"
        for jogador in partida.jogadores:
            jogador.perseguiu_pomo_no_turno = False
            jogador.pomo_perseguido = ""
        partida.eventos.append(
            EventoPartida(
                tipo="intervalo",
                descricao="O 1º tempo terminou. A partida entrou no intervalo.",
            )
        )
        return
    partida.estado = "aguardando_confirmacao"
    partida.eventos.append(
        EventoPartida(
            tipo="fim_tempo",
            descricao="O 2º tempo terminou; o resultado aguarda confirmação.",
        )
    )


def aplicar_resultado_na_taca(
    partida: PartidaQuadribol,
    estado_taca: EstadoTaca,
) -> list[AcontecimentoTaca]:
    if partida.taca_aplicada:
        raise ValueError("O resultado desta partida já foi aplicado à Taça.")
    if partida.estado != "aguardando_confirmacao":
        raise ValueError("Encerre o tempo da partida antes de confirmar o resultado.")
    vencedor = partida.vencedor()
    acontecimentos: list[AcontecimentoTaca] = []
    agora = _agora()
    for casa in partida.casas():
        pontos = partida.pontos_taca(casa)
        if pontos <= 0:
            continue
        partes = [f"{partida.gols[casa]} gol(s)"]
        capturas = partida.capturas_pomo(casa)
        if capturas:
            partes.append(f"{capturas} captura(s) do Pomo")
        if vencedor == casa:
            partes.append(
                "vitória por falta eliminatória"
                if partida.vencedor_forcado
                else "vitória"
            )
        acontecimento = AcontecimentoTaca(
            identificador=_identificador("quadribol-taca"),
            tipo="quadribol",
            autoridade="Partida de Quadribol",
            personagem=f"Equipe da {casa}",
            casa=casa,
            pontos=pontos,
            motivo=f"{partida.jogo}: " + ", ".join(partes),
            moderador_id=partida.moderador_id,
            criado_em=agora,
            categoria="Quadribol",
            detalhes=(
                f"Placar: {partida.casa_1} {partida.placar(partida.casa_1)} x "
                f"{partida.placar(partida.casa_2)} {partida.casa_2}"
            ),
        )
        aplicar_acontecimento(estado_taca, acontecimento)
        acontecimentos.append(acontecimento)
    partida.taca_aplicada = True
    partida.estado = "encerrada"
    partida.eventos.append(
        EventoPartida(
            tipo="fim",
            casa=vencedor,
            descricao=(
                f"{vencedor} venceu; resultado da partida confirmado."
                if vencedor
                else "A partida terminou empatada; resultado confirmado."
            ),
        )
    )
    return acontecimentos


def salvar_partida(partida: PartidaQuadribol, caminho: Path | None = None) -> Path:
    destino = caminho or PASTA_PARTIDAS / f"{partida.identificador}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".md.tmp")
    temporario.write_text(partida.markdown(), encoding="utf-8", newline="\n")
    temporario.replace(destino)
    return destino


def carregar_partida(caminho: Path) -> PartidaQuadribol:
    entrada = interpretar_markdown(caminho.read_text(encoding="utf-8-sig"))
    linhas = entrada.campos.get("Dados", "").splitlines()
    conteudo = next((linha.strip().removeprefix("- ") for linha in linhas if linha.strip()), "")
    if not conteudo:
        raise ValueError("A partida não possui dados persistidos.")
    dados = json.loads(conteudo)
    legado_sem_posse = "posse_goles" not in dados
    dados["jogadores"] = [
        JogadorPartida(
            **{
                **item,
                "efeitos": [EfeitoQuadribol(**efeito) for efeito in item.get("efeitos", [])],
            }
        )
        for item in dados.get("jogadores", [])
    ]
    dados["eventos"] = [EventoPartida(**item) for item in dados.get("eventos", [])]
    partida = PartidaQuadribol(**dados)
    sincronizar_vassouras_partida(partida)
    if legado_sem_posse and partida.estado == "ativa":
        atual = partida.jogador_atual()
        candidatos = artilheiros_ativos(partida, atual.casa) if atual is not None else []
        if atual is not None and atual.posicao == "Artilheiro" and atual in candidatos:
            partida.posse_goles = atual.nome
        elif candidatos:
            partida.posse_goles = candidatos[0].nome
        else:
            todos = [
                jogador
                for casa in partida.casas()
                for jogador in artilheiros_ativos(partida, casa)
            ]
            if todos:
                partida.posse_goles = todos[0].nome
    return partida


def encontrar_partida_por_mensagem(
    mensagem_id: int,
    pasta: Path | None = None,
) -> tuple[PartidaQuadribol, Path] | None:
    origem = pasta or PASTA_PARTIDAS
    if not origem.is_dir():
        return None
    for arquivo in origem.glob("*.md"):
        try:
            partida = carregar_partida(arquivo)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if partida.mensagem_id == mensagem_id:
            return partida, arquivo
    return None
