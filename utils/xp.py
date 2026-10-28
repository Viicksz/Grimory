from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from utils.biblioteca import interpretar_markdown, normalizar_rotulo


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_CONTAS_XP = RAIZ_PROJETO / "biblioteca" / "banco de xp"


@dataclass
class ContaXP:
    nome: str
    titular_id: int
    xp: int = 0

    def markdown(self) -> str:
        return (
            f"# {self.nome}\n\n"
            f"Titular do Discord:\n{self.titular_id}\n\n"
            f"XP disponível:\n{self.xp}\n"
        )

    @classmethod
    def carregar(cls, caminho: Path) -> ContaXP:
        entrada = interpretar_markdown(caminho.read_text(encoding="utf-8-sig"))
        campos = {
            normalizar_rotulo(rotulo): valor.strip()
            for rotulo, valor in entrada.campos.items()
        }
        try:
            titular_id = int(campos.get("titular do discord", ""))
            xp = int(campos.get("xp disponivel", "0"))
        except ValueError as erro:
            raise ValueError("A conta possui dados inválidos.") from erro
        return cls(
            nome=entrada.titulo or caminho.stem,
            titular_id=titular_id,
            xp=xp,
        )


@dataclass(frozen=True)
class ReferenciaContaXP:
    nome: str
    titular_id: int
    caminho: Path


def _nome_seguro(nome: str) -> str:
    nome = nome.strip()
    if not nome or any(caractere in nome for caractere in '<>:"/\\|?*\r\n'):
        raise ValueError("Nome de conta inválido.")
    return nome


def listar_contas_xp(termo: str = "") -> list[ReferenciaContaXP]:
    termo_normalizado = normalizar_rotulo(termo)
    if not PASTA_CONTAS_XP.is_dir():
        return []
    contas: list[ReferenciaContaXP] = []
    for arquivo in PASTA_CONTAS_XP.glob("*.md"):
        try:
            conta = ContaXP.carregar(arquivo)
        except (OSError, ValueError):
            continue
        if termo_normalizado and termo_normalizado not in normalizar_rotulo(conta.nome):
            continue
        contas.append(ReferenciaContaXP(conta.nome, conta.titular_id, arquivo))
    return sorted(contas, key=lambda item: item.nome.casefold())


def encontrar_conta_xp(nome: str) -> ReferenciaContaXP | None:
    nome_normalizado = normalizar_rotulo(nome)
    return next(
        (
            conta
            for conta in listar_contas_xp()
            if normalizar_rotulo(conta.nome) == nome_normalizado
        ),
        None,
    )


def encontrar_conta_do_titular(titular_id: int) -> ReferenciaContaXP | None:
    return next(
        (conta for conta in listar_contas_xp() if conta.titular_id == titular_id),
        None,
    )


def caminho_nova_conta_xp(nome: str) -> Path:
    nome = _nome_seguro(nome)
    destino = (PASTA_CONTAS_XP / f"{nome}.md").resolve()
    destino.relative_to(PASTA_CONTAS_XP.resolve())
    return destino


def salvar_conta_xp(conta: ContaXP, caminho: Path, *, nova: bool = False) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if nova:
        with caminho.open("x", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write(conta.markdown())
        return
    temporario = caminho.with_suffix(".md.tmp")
    temporario.write_text(conta.markdown(), encoding="utf-8", newline="\n")
    temporario.replace(caminho)
