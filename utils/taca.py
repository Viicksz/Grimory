from __future__ import annotations

import json
import random
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from utils.biblioteca import interpretar_markdown, normalizar_rotulo


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_FICHAS = RAIZ_PROJETO / "biblioteca" / "fichas"
PASTA_AUTORIDADES = PASTA_FICHAS / "Figuras de Autoridade"
ARQUIVO_TACA = RAIZ_PROJETO / "biblioteca" / "taça das casas" / "Taça das Casas.md"
CANAL_PROFETA_DIARIO_ID = 1154807244496572456

CASAS = ("Grifinória", "Sonserina", "Lufa-Lufa", "Corvinal")
PASTAS_CASAS = {casa: casa for casa in CASAS}
CARGOS_CASAS = {
    "Grifinória": 937255634024402954,
    "Sonserina": 937254921219211285,
    "Lufa-Lufa": 937255872126648340,
    "Corvinal": 937255410719653919,
}
CORACOES_CASAS = {
    "Grifinória": "❤️",
    "Sonserina": "💚",
    "Lufa-Lufa": "💛",
    "Corvinal": "💙",
}
VALORES_PRESETS = (5, 10, 15, 20, 25)


@dataclass(frozen=True)
class PresetTaca:
    pontos: int
    motivo: str


@dataclass(frozen=True)
class FiguraAutoridade:
    nome: str
    ocupacao: str
    gratificacoes: tuple[PresetTaca, ...]
    penalidades: tuple[PresetTaca, ...]
    nota_10: str = ""
    execucao_perfeita: str = ""


@dataclass
class AcontecimentoTaca:
    identificador: str
    tipo: str
    autoridade: str
    personagem: str
    casa: str
    pontos: int
    motivo: str
    moderador_id: int
    criado_em: str
    usuario_id: int = 0
    categoria: str = ""
    detalhes: str = ""
    punicao: str = ""


@dataclass
class EstadoTaca:
    pontuacoes: dict[str, int] = field(default_factory=lambda: {casa: 0 for casa in CASAS})
    historico: list[AcontecimentoTaca] = field(default_factory=list)

    def markdown(self) -> str:
        linhas_pontuacao = "\n".join(
            f"- {casa}: {self.pontuacoes.get(casa, 0)}"
            for casa in CASAS
        )
        linhas_historico = "\n".join(
            f"- {json.dumps(asdict(item), ensure_ascii=False, separators=(',', ':'))}"
            for item in self.historico
        ) or "- --"
        return (
            "# Taça das Casas\n\n"
            f"Pontuação:\n{linhas_pontuacao}\n\n"
            f"Histórico:\n{linhas_historico}\n"
        )


def _validar_presets(nome: str, rotulo: str, presets: list[PresetTaca]) -> None:
    contagem = Counter(item.pontos for item in presets)
    esperado = {valor: 2 for valor in VALORES_PRESETS}
    if len(presets) != 10 or contagem != esperado:
        raise ValueError(
            f"{nome} precisa ter exatamente 10 {rotulo}, com dois presets por valor."
        )


def _validar_catalogo_em_edicao(
    nome: str,
    rotulo: str,
    presets: list[PresetTaca],
) -> bool:
    contagem = Counter(item.pontos for item in presets)
    valores_invalidos = set(contagem) - set(VALORES_PRESETS)
    if valores_invalidos or any(quantidade > 2 for quantidade in contagem.values()):
        raise ValueError(f"{nome} possui {rotulo} inválidas na ficha.")
    return len(presets) == 10 and all(contagem[valor] == 2 for valor in VALORES_PRESETS)


def _carregar_autoridades_das_fichas() -> list[FiguraAutoridade]:
    from utils.fichas import FichaPersonagem

    autoridades: list[tuple[int, FiguraAutoridade]] = []
    for arquivo in PASTA_AUTORIDADES.glob("*.md"):
        ficha = FichaPersonagem.carregar(arquivo)
        informacoes = {
            normalizar_rotulo(item["titulo"]): item["descricao"]
            for item in ficha.informacoes
        }
        ocupacao = informacoes.get("cargo", informacoes.get("ocupacao", "")).strip()
        nota_10 = ficha.nota_10_autoridade.strip()
        execucao_perfeita = ficha.execucao_perfeita_autoridade.strip()
        gratificacoes = [
            PresetTaca(int(item["pontos"]), item["motivo"])
            for item in ficha.gratificacoes_autoridade
        ]
        penalidades = [
            PresetTaca(int(item["pontos"]), item["motivo"])
            for item in ficha.penalidades_autoridade
        ]
        gratificacoes_completas = _validar_catalogo_em_edicao(
            ficha.nome,
            "gratificações",
            gratificacoes,
        )
        penalidades_completas = _validar_catalogo_em_edicao(
            ficha.nome,
            "penalidades",
            penalidades,
        )
        if not gratificacoes_completas or not penalidades_completas:
            # A edição é feita uma categoria por vez. A autoridade só entra
            # nos comandos da Taça quando os dois catálogos estiverem completos.
            continue
        _validar_presets(ficha.nome, "gratificações", gratificacoes)
        _validar_presets(ficha.nome, "penalidades", penalidades)
        if not ocupacao:
            raise ValueError(f"{ficha.nome} precisa possuir a informação Cargo.")
        autoridades.append(
            (
                ficha.ordem_autoridade,
                FiguraAutoridade(
                    nome=ficha.nome,
                    ocupacao=ocupacao,
                    gratificacoes=tuple(gratificacoes),
                    penalidades=tuple(penalidades),
                    nota_10=nota_10,
                    execucao_perfeita=execucao_perfeita,
                ),
            )
        )
    autoridades.sort(key=lambda item: (item[0] or 9999, item[1].nome.casefold()))
    return [autoridade for _, autoridade in autoridades]


def carregar_autoridades() -> list[FiguraAutoridade]:
    if not PASTA_AUTORIDADES.is_dir():
        raise ValueError("A pasta de fichas das Figuras de Autoridade não foi encontrada.")
    autoridades = _carregar_autoridades_das_fichas()
    if not autoridades:
        raise ValueError("Nenhuma ficha de Figura de Autoridade válida foi encontrada.")
    return autoridades


def listar_personagens_por_casa() -> dict[str, list[str]]:
    resultado: dict[str, list[str]] = {}
    for casa in CASAS:
        pasta = PASTA_FICHAS / PASTAS_CASAS[casa]
        resultado[casa] = (
            sorted((arquivo.stem for arquivo in pasta.glob("*.md")), key=str.casefold)
            if pasta.is_dir()
            else []
        )
    return resultado


def sortear_acontecimento(
    *,
    gerador: random.Random | None = None,
    moderador_id: int = 0,
    autoridades: list[FiguraAutoridade] | None = None,
    personagens: dict[str, list[str]] | None = None,
) -> AcontecimentoTaca:
    sorteio = gerador or random.SystemRandom()
    catalogo = autoridades or carregar_autoridades()
    fichas = personagens or listar_personagens_por_casa()
    casas_disponiveis = [casa for casa in CASAS if fichas.get(casa)]
    if not casas_disponiveis:
        raise ValueError("Nenhuma das quatro casas possui uma ficha elegível para o sorteio.")

    casa = sorteio.choice(casas_disponiveis)
    personagem = sorteio.choice(fichas[casa])
    autoridade = sorteio.choice(catalogo)
    tipo = sorteio.choice(("gratificacao", "penalidade"))
    opcoes = autoridade.gratificacoes if tipo == "gratificacao" else autoridade.penalidades
    preset = sorteio.choice(opcoes)
    sinal = 1 if tipo == "gratificacao" else -1
    instante = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return AcontecimentoTaca(
        identificador=f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}",
        tipo=tipo,
        autoridade=autoridade.nome,
        personagem=personagem,
        casa=casa,
        pontos=sinal * preset.pontos,
        motivo=preset.motivo,
        moderador_id=moderador_id,
        criado_em=instante,
    )


def carregar_estado_taca(caminho: Path | None = None) -> EstadoTaca:
    origem = caminho or ARQUIVO_TACA
    if not origem.is_file():
        return EstadoTaca()
    entrada = interpretar_markdown(origem.read_text(encoding="utf-8-sig"))
    campos = {normalizar_rotulo(chave): valor for chave, valor in entrada.campos.items()}
    pontuacoes = {casa: 0 for casa in CASAS}
    for linha in campos.get("pontuacao", "").splitlines():
        conteudo = linha.strip().removeprefix("- ").strip()
        if ":" not in conteudo:
            continue
        nome, valor = conteudo.rsplit(":", 1)
        casa = next((item for item in CASAS if normalizar_rotulo(item) == normalizar_rotulo(nome)), None)
        if casa is not None:
            try:
                pontuacoes[casa] = int(valor.strip())
            except ValueError:
                continue

    historico: list[AcontecimentoTaca] = []
    for linha in campos.get("historico", "").splitlines():
        conteudo = linha.strip().removeprefix("- ").strip()
        if conteudo in {"", "--"}:
            continue
        try:
            dados = json.loads(conteudo)
            historico.append(AcontecimentoTaca(**dados))
        except (json.JSONDecodeError, TypeError, KeyError):
            continue
    return EstadoTaca(pontuacoes=pontuacoes, historico=historico)


def salvar_estado_taca(estado: EstadoTaca, caminho: Path | None = None) -> Path:
    destino = caminho or ARQUIVO_TACA
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".md.tmp")
    temporario.write_text(estado.markdown(), encoding="utf-8", newline="\n")
    temporario.replace(destino)
    return destino


def aplicar_acontecimento(estado: EstadoTaca, acontecimento: AcontecimentoTaca) -> None:
    if acontecimento.casa not in CASAS:
        raise ValueError("Casa inválida no acontecimento da Taça.")
    estado.pontuacoes[acontecimento.casa] = (
        estado.pontuacoes.get(acontecimento.casa, 0) + acontecimento.pontos
    )
    estado.historico.append(acontecimento)


def texto_acontecimento(acontecimento: AcontecimentoTaca) -> str:
    cargo = CARGOS_CASAS[acontecimento.casa]
    valor = abs(acontecimento.pontos)
    if acontecimento.pontos > 0:
        return (
            f"**{acontecimento.autoridade}** concedeu a **{acontecimento.personagem}** "
            f"*{valor} pontos* para a <@&{cargo}> por {acontecimento.motivo}."
        )
    return (
        f"**{acontecimento.autoridade}** retirou de **{acontecimento.personagem}** "
        f"*{valor} pontos* da <@&{cargo}> por {acontecimento.motivo}."
    )
CATEGORIAS_GRATIFICACAO = (
    ("evolucao_pessoal", "Evolução pessoal", 5),
    ("desempenho_academico", "Desempenho acadêmico", 10),
    ("desempenho_coletivo", "Desempenho coletivo", 15),
    ("situacoes_complicadas", "Situações complicadas", 20),
    ("conquistas", "Conquistas", 25),
)

CATEGORIAS_PENALIDADE_AUTORIDADE = (
    ("deslize", "Deslize disciplinar", 5, "−5 pontos"),
    ("leve_1", "Infração leve — 1ª ocorrência", 10, "−10 pontos"),
    ("leve_2", "Infração leve — 2ª ocorrência", 15, "−15 pontos"),
    (
        "leve_3_grave_1",
        "Infração leve — 3ª ocorrência / grave — 1ª",
        20,
        "−20 pontos",
    ),
    (
        "grave_2_3",
        "Infração grave — 2ª/3ª ocorrência",
        25,
        "−25 ou −30 pontos",
    ),
)
