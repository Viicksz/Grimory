from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from utils.biblioteca import interpretar_markdown, normalizar_rotulo
from utils.fichas import PERICIAS, modificador


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_CRIATURAS = RAIZ_PROJETO / "biblioteca" / "criaturas"
PASTA_FICHAS_CRIATURAS = RAIZ_PROJETO / "biblioteca" / "fichas" / "Criaturas"
PERICULOSIDADES = ("X", "XX", "XXX", "XXXX", "XXXXX")
ATRIBUTOS_CRIATURA = (
    "Força", "Destreza", "Constituição", "Inteligência",
    "Sabedoria", "Carisma", "Magia",
)
PONTOS_ATRIBUTO = {"X": 10, "XX": 14, "XXX": 18, "XXXX": 22, "XXXXX": 26}
XP_PERICIAS = {"X": 150, "XX": 200, "XXX": 300, "XXXX": 400, "XXXXX": 600}
BASES_TAMANHO = {
    "Menos de 50 cm": 5,
    "Menos de 1 m": 10,
    "De 1 m a 2 m": 20,
    "De 2 m a 3 m": 30,
    "De 3 m a 4 m": 40,
    "De 4 m a 5 m": 50,
    "De 5 m a 10 m": 60,
    "Acima de 10 m": 70,
}
RANKS_PERICIA_CRIATURA = {0: "Inexperiente", 2: "Treinada", 4: "Expert", 6: "Mestre"}
CUSTO_TOTAL_RANK = {0: 0, 2: 50, 4: 150, 6: 300}


def nivel_periculosidade(periculosidade: str) -> int:
    if periculosidade not in PERICULOSIDADES:
        raise ValueError("Periculosidade inválida.")
    return len(periculosidade)


def _linhas_mapa(valores: dict[str, int], ordem: Iterable[str]) -> str:
    return "\n".join(f"- {nome}: {valores.get(nome, 0)}" for nome in ordem)


def _mapa_inteiros(texto: str) -> dict[str, int]:
    resultado: dict[str, int] = {}
    for linha in texto.splitlines():
        linha = linha.strip().removeprefix("- ").strip()
        if ":" not in linha:
            continue
        nome, valor = linha.rsplit(":", 1)
        try:
            resultado[nome.strip()] = int(valor.strip())
        except ValueError:
            pass
    return resultado


def _linhas_registros(registros: Iterable[dict[str, str]]) -> str:
    itens = [f"- {json.dumps(item, ensure_ascii=False, separators=(',', ':'))}" for item in registros]
    return "\n".join(itens) if itens else "- --"


def _registros(texto: str) -> list[dict[str, str]]:
    resultado: list[dict[str, str]] = []
    for linha in texto.splitlines():
        conteudo = linha.strip().removeprefix("- ").strip()
        if conteudo in {"", "--"}:
            continue
        try:
            item = json.loads(conteudo)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(item, dict):
            resultado.append({str(k): str(v) for k, v in item.items()})
    return resultado


@dataclass
class ReferenciaCriatura:
    nome: str
    periculosidade: str
    classificacao: str
    caminho: Path
    imagem: str = ""
    aptidoes: str = ""


def listar_criaturas_lore(termo: str = "") -> list[ReferenciaCriatura]:
    busca = normalizar_rotulo(termo)
    resultado: list[ReferenciaCriatura] = []
    for perigo in PERICULOSIDADES:
        pasta = PASTA_CRIATURAS / perigo
        if not pasta.is_dir():
            continue
        for caminho in pasta.glob("*.md"):
            if busca and busca not in normalizar_rotulo(caminho.stem):
                continue
            entrada = interpretar_markdown(caminho.read_text(encoding="utf-8-sig"))
            campos = {normalizar_rotulo(k): v.strip() for k, v in entrada.campos.items()}
            resultado.append(ReferenciaCriatura(
                nome=entrada.titulo or caminho.stem,
                periculosidade=campos.get("periculosidade", perigo),
                classificacao=campos.get("classificacao", "--"),
                caminho=caminho,
                imagem=campos.get("imagem", ""),
                aptidoes=campos.get("aptidoes", ""),
            ))
    return sorted(resultado, key=lambda item: item.nome.casefold())


@dataclass
class FichaCriatura:
    nome: str
    classificacao: str
    periculosidade: str
    tamanho: str
    faixa_tamanho: str
    origem_biblioteca: str = "Nova criatura"
    imagem: str = ""
    titular_id: int = 0
    mensagem_discord_id: int = 0
    atributos: dict[str, int] = field(default_factory=lambda: {nome: 10 for nome in ATRIBUTOS_CRIATURA})
    pericias: dict[str, int] = field(default_factory=lambda: {nome: 0 for nome in PERICIAS})
    armas_naturais: list[dict[str, str]] = field(default_factory=list)
    ataques: list[dict[str, str]] = field(default_factory=list)
    habilidades: list[dict[str, str]] = field(default_factory=list)
    fraquezas: list[dict[str, str]] = field(default_factory=list)
    resistencias: list[dict[str, str]] = field(default_factory=list)

    @property
    def nivel(self) -> int:
        return nivel_periculosidade(self.periculosidade)

    @property
    def pv(self) -> int:
        constituicao = self.atributos["Constituição"]
        return (
            BASES_TAMANHO[self.faixa_tamanho]
            + constituicao
            + modificador(constituicao) * self.nivel
        )

    @property
    def ph(self) -> int:
        calculado = (5 + modificador(self.atributos["Magia"])) * self.nivel
        return max(self.nivel, calculado)

    @property
    def mana(self) -> int:
        """Compatibilidade temporária com integrações antigas; PH é o nome oficial."""
        return self.ph

    @property
    def pontos_atributo_restantes(self) -> int:
        usados = sum(valor - 10 for valor in self.atributos.values())
        return PONTOS_ATRIBUTO[self.periculosidade] - usados

    @property
    def xp_pericias_restante(self) -> int:
        gasto = sum(CUSTO_TOTAL_RANK.get(valor, 0) for valor in self.pericias.values())
        return XP_PERICIAS[self.periculosidade] - gasto

    def markdown(self) -> str:
        campos = [
            ("Tipo de ficha", "Criatura"),
            ("Classificação", self.classificacao),
            ("Periculosidade", self.periculosidade),
            ("Tamanho", self.tamanho),
            ("Faixa de tamanho", self.faixa_tamanho),
            ("Origem da ficha", self.origem_biblioteca),
            ("Imagem", self.imagem or "--"),
            ("Atributos", _linhas_mapa(self.atributos, ATRIBUTOS_CRIATURA)),
            ("Perícias", _linhas_mapa(self.pericias, PERICIAS)),
            ("Armas", _linhas_registros(self.armas_naturais)),
            ("Ataques não mágicos", _linhas_registros(self.ataques)),
            ("Habilidades", _linhas_registros(self.habilidades)),
            ("Fraquezas", _linhas_registros(self.fraquezas)),
            ("Resistências", _linhas_registros(self.resistencias)),
        ]
        if self.titular_id:
            campos.insert(1, ("Criador no Discord", str(self.titular_id)))
        if self.mensagem_discord_id:
            indice = 2 if self.titular_id else 1
            campos.insert(indice, ("Mensagem da Ficha no Discord", str(self.mensagem_discord_id)))
        partes = [f"# {self.nome}"]
        partes.extend(f"{rotulo}:\n{valor}" for rotulo, valor in campos)
        return "\n\n".join(partes).rstrip() + "\n"

    @classmethod
    def de_markdown(cls, conteudo: str, caminho: Path | None = None) -> "FichaCriatura":
        entrada = interpretar_markdown(conteudo)
        campos = {normalizar_rotulo(k): v.strip() for k, v in entrada.campos.items()}
        perigo_padrao = caminho.parent.name if caminho is not None else "X"
        perigo = campos.get("periculosidade", perigo_padrao)
        atributos = {nome: 10 for nome in ATRIBUTOS_CRIATURA}
        atributos.update(_mapa_inteiros(campos.get("atributos", "")))
        pericias = {nome: 0 for nome in PERICIAS}
        pericias.update(_mapa_inteiros(campos.get("pericias", "")))
        try:
            titular = int(campos.get("criador no discord", "0"))
        except ValueError:
            titular = 0
        try:
            mensagem_discord_id = int(campos.get("mensagem da ficha no discord", "0"))
        except ValueError:
            mensagem_discord_id = 0
        return cls(
            nome=entrada.titulo or caminho.stem,
            classificacao=campos.get("classificacao", "--"),
            periculosidade=perigo,
            tamanho=campos.get("tamanho", "--"),
            faixa_tamanho=campos.get("faixa de tamanho", "Menos de 1 m"),
            origem_biblioteca=campos.get("origem da ficha", "Nova criatura"),
            imagem=campos.get("imagem", "").removeprefix("--"),
            titular_id=titular,
            mensagem_discord_id=mensagem_discord_id,
            atributos=atributos,
            pericias=pericias,
            armas_naturais=_registros(campos.get("armas", campos.get("armas naturais", ""))),
            ataques=_registros(campos.get("ataques nao magicos", "")),
            habilidades=_registros(campos.get("habilidades", "")),
            fraquezas=_registros(campos.get("fraquezas", "")),
            resistencias=_registros(campos.get("resistencias", "")),
        )

    @classmethod
    def carregar(cls, caminho: Path) -> "FichaCriatura":
        return cls.de_markdown(
            caminho.read_text(encoding="utf-8-sig"),
            caminho,
        )


@dataclass(frozen=True)
class ReferenciaFichaCriatura:
    nome: str
    periculosidade: str
    caminho: Path


def listar_fichas_criaturas(termo: str = "") -> list[ReferenciaFichaCriatura]:
    busca = normalizar_rotulo(termo)
    resultado: list[ReferenciaFichaCriatura] = []
    for perigo in PERICULOSIDADES:
        pasta = PASTA_FICHAS_CRIATURAS / perigo
        if not pasta.is_dir():
            continue
        for caminho in pasta.glob("*.md"):
            if busca and busca not in normalizar_rotulo(caminho.stem):
                continue
            resultado.append(ReferenciaFichaCriatura(caminho.stem, perigo, caminho))
    return sorted(resultado, key=lambda item: item.nome.casefold())


def encontrar_ficha_criatura(valor: str) -> ReferenciaFichaCriatura | None:
    alvo = normalizar_rotulo(valor)
    for item in listar_fichas_criaturas():
        relativo = item.caminho.relative_to(PASTA_FICHAS_CRIATURAS).as_posix()
        if normalizar_rotulo(relativo) == alvo:
            return item
    iguais = [item for item in listar_fichas_criaturas() if normalizar_rotulo(item.nome) == alvo]
    return iguais[0] if len(iguais) == 1 else None


def caminho_nova_ficha_criatura(perigo: str, nome: str) -> Path:
    nivel_periculosidade(perigo)
    if not nome.strip() or any(c in nome for c in '<>:"/\\|?*\r\n'):
        raise ValueError("Nome de criatura inválido.")
    pasta = (PASTA_FICHAS_CRIATURAS / perigo).resolve()
    destino = (pasta / f"{nome.strip()}.md").resolve()
    destino.relative_to(PASTA_FICHAS_CRIATURAS.resolve())
    return destino


def salvar_ficha_criatura(ficha: FichaCriatura, caminho: Path, *, nova: bool = False) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if nova:
        with caminho.open("x", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write(ficha.markdown())
        return
    temporario = caminho.with_suffix(".md.tmp")
    temporario.write_text(ficha.markdown(), encoding="utf-8", newline="\n")
    temporario.replace(caminho)


def efeito_dano(perigo: str, fraqueza: bool) -> str:
    nivel = nivel_periculosidade(perigo)
    if fraqueza:
        return {
            1: "Recebe +2 de dano.",
            2: "Recebe +4 de dano.",
            3: "Recebe metade do dano adicional (total ×1,5).",
            4: "Recebe o dobro dos dados de dano.",
            5: "Recebe o dobro do resultado final do dano.",
        }[nivel]
    return {
        1: "Reduz 2 de dano.",
        2: "Reduz 4 de dano.",
        3: "Reduz um quarto do dano.",
        4: "Recebe metade do dano.",
        5: "É imune ao dano.",
    }[nivel]


def efeito_condicao(fraqueza: bool) -> str:
    return "Possui desvantagem no teste para resistir." if fraqueza else "Possui vantagem no teste para resistir."


PASSOS_DANO = (
    "1d2", "1d4", "1d6", "1d8", "1d10", "1d12",
    *(passo for quantidade in range(2, 31) for passo in (f"{quantidade}d6", f"{quantidade}d8")),
)


def tamanho_em_metros(tamanho: str) -> float:
    texto = tamanho.strip().casefold().replace(",", ".")
    correspondencia = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(cm|m)?", texto)
    if correspondencia is None:
        raise ValueError("Informe uma medida válida, como 50, 0,50, 289 cm ou 2,89 m.")
    valor = float(correspondencia.group(1))
    if valor <= 0:
        raise ValueError("O tamanho exato deve ser maior que zero.")
    unidade = correspondencia.group(2)
    if unidade == "cm":
        return valor / 100
    if unidade == "m":
        return valor
    numero_original = correspondencia.group(1)
    return valor if "." in numero_original else valor / 100


def normalizar_tamanho(tamanho: str) -> str:
    metros = tamanho_em_metros(tamanho)
    valor = metros * 100 if metros < 1 else metros
    unidade = "cm" if metros < 1 else "m"
    numero = f"{valor:.4f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{numero} {unidade}"


def tamanho_pertence_a_faixa(tamanho: str, faixa: str) -> bool:
    metros = tamanho_em_metros(tamanho)
    limites = {
        "Menos de 50 cm": lambda valor: valor < 0.5,
        "Menos de 1 m": lambda valor: 0.5 <= valor < 1,
        "De 1 m a 2 m": lambda valor: 1 <= valor <= 2,
        "De 2 m a 3 m": lambda valor: 2 <= valor <= 3,
        "De 3 m a 4 m": lambda valor: 3 <= valor <= 4,
        "De 4 m a 5 m": lambda valor: 4 <= valor <= 5,
        "De 5 m a 10 m": lambda valor: 5 <= valor <= 10,
        "Acima de 10 m": lambda valor: valor > 10,
    }
    if faixa not in limites:
        raise ValueError("A faixa de tamanho escolhida é inválida.")
    return limites[faixa](metros)


def validar_e_normalizar_tamanho(tamanho: str, faixa: str) -> str:
    normalizado = normalizar_tamanho(tamanho)
    if not tamanho_pertence_a_faixa(normalizado, faixa):
        raise ValueError(f"O tamanho **{normalizado}** não pertence à faixa **{faixa}**. Corrija a medida antes de continuar.")
    return normalizado


def passos_dano_por_tamanho(tamanho: str) -> int:
    metros = tamanho_em_metros(tamanho)
    if metros <= 2:
        return 0
    if metros <= 4:
        return 1
    if metros <= 6:
        return 2
    if metros <= 8:
        return 3
    if metros <= 10:
        return 4
    return 5


def avancar_passo_dano(dano_base: str, passos: int) -> str:
    correspondencia = re.fullmatch(r"\s*(\d+d\d+)(.*)", dano_base, re.IGNORECASE)
    if correspondencia is None:
        raise ValueError("O dano-base deve começar com um passo válido, como 1d6 ou 1d6+Força.")
    dado = correspondencia.group(1).casefold()
    if dado not in PASSOS_DANO:
        raise ValueError("O dado informado não pertence à tabela de passos de dano.")
    indice = PASSOS_DANO.index(dado) + passos
    if indice >= len(PASSOS_DANO):
        raise ValueError("O dano ultrapassou a tabela de passos disponível.")
    return f"{PASSOS_DANO[indice]}{correspondencia.group(2)}"


def dano_arma_natural(dano_base: str, perigo: str, tamanho: str) -> str:
    passos = nivel_periculosidade(perigo) - 1 + passos_dano_por_tamanho(tamanho)
    return avancar_passo_dano(dano_base, passos)


def somar_atributo_ao_dano(dano: str, atributos: dict[str, int]) -> str:
    """Troca Força/Destreza no dano pelo modificador atual da criatura.

    FOR e DES continuam aceitos para manter compatibilidade com registros antigos.
    """
    partes = re.split(r"\s+e\s+", dano.strip(), flags=re.IGNORECASE)
    if len(partes) > 1:
        return " e ".join(somar_atributo_ao_dano(parte, atributos) for parte in partes)
    correspondencia = re.fullmatch(
        r"\s*(\d+d\d+)\s*\+\s*(FOR(?:ÇA)?|DES(?:TREZA)?)(?:\s*[×x]\s*(\d+))?\s*",
        dano,
        re.IGNORECASE,
    )
    if correspondencia is None:
        return dano.strip()
    atributo_bruto = normalizar_rotulo(correspondencia.group(2))
    atributo = "Força" if atributo_bruto in {"for", "forca"} else "Destreza"
    multiplicador = int(correspondencia.group(3) or "1")
    bonus = modificador(atributos.get(atributo, 10)) * multiplicador
    origem = atributo if multiplicador == 1 else f"{atributo} ×{multiplicador}"
    sinal = f"+{bonus}" if bonus >= 0 else str(bonus)
    return f"{correspondencia.group(1).lower()}{sinal} ({origem})"
