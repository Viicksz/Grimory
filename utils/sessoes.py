from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_SESSOES = RAIZ_PROJETO / "biblioteca" / "sessões"


@dataclass
class RespostaEncerramento:
    estacao: str
    semana: int
    dia: str
    hora: int
    minuto: int
    periodo: str
    local: str
    acao: str
    objetivo: str
    atualizado_por: int
    atualizado_em: str
    pv: int | None = None
    ph: int | None = None
    ficha: str = ""


@dataclass
class ParticipanteEncerramento:
    usuario_id: int
    nome: str
    resposta: RespostaEncerramento | None = None


@dataclass
class Encerramento:
    identificador: str
    servidor_id: int
    canal_id: int
    moderador_id: int
    criado_em: str
    participantes: dict[int, ParticipanteEncerramento]
    concluido: bool = False
    concluido_em: str = ""
    mensagens_discord: list[int] = field(default_factory=list)
    caminho: Path | None = field(default=None, repr=False, compare=False)

    def markdown(self) -> str:
        dados = {
            "identificador": self.identificador,
            "servidor_id": self.servidor_id,
            "canal_id": self.canal_id,
            "moderador_id": self.moderador_id,
            "criado_em": self.criado_em,
            "concluido": self.concluido,
            "concluido_em": self.concluido_em,
            "mensagens_discord": self.mensagens_discord,
            "participantes": {
                str(usuario_id): asdict(participante)
                for usuario_id, participante in self.participantes.items()
            },
        }
        estado = "Concluído" if self.concluido else "Em preenchimento"
        return (
            "# Última Sessão\n\n"
            f"Estado:\n{estado}\n\n"
            "Dados do encerramento:\n"
            "```json\n"
            f"{json.dumps(dados, ensure_ascii=False, indent=2)}\n"
            "```\n"
        )

    @classmethod
    def carregar(cls, caminho: Path) -> Encerramento:
        texto = caminho.read_text(encoding="utf-8-sig")
        correspondencia = re.search(r"```json\s*(\{.*?\})\s*```", texto, re.DOTALL)
        if not correspondencia:
            raise ValueError(f"Dados do encerramento ausentes em {caminho.name}.")
        try:
            dados = json.loads(correspondencia.group(1))
        except json.JSONDecodeError as erro:
            raise ValueError(f"Dados inválidos em {caminho.name}.") from erro

        participantes: dict[int, ParticipanteEncerramento] = {}
        for chave, registro in dados.get("participantes", {}).items():
            usuario_id = int(chave)
            resposta_dados = registro.get("resposta")
            resposta = (
                RespostaEncerramento(**resposta_dados)
                if isinstance(resposta_dados, dict)
                else None
            )
            participantes[usuario_id] = ParticipanteEncerramento(
                usuario_id=usuario_id,
                nome=str(registro.get("nome", usuario_id)),
                resposta=resposta,
            )

        return cls(
            identificador=str(dados["identificador"]),
            servidor_id=int(dados["servidor_id"]),
            canal_id=int(dados["canal_id"]),
            moderador_id=int(dados["moderador_id"]),
            criado_em=str(dados["criado_em"]),
            participantes=participantes,
            concluido=bool(dados.get("concluido", False)),
            concluido_em=str(dados.get("concluido_em", "")),
            mensagens_discord=[int(valor) for valor in dados.get("mensagens_discord", [])],
            caminho=caminho,
        )


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def novo_encerramento(
    servidor_id: int,
    canal_id: int,
    moderador_id: int,
    participantes: list[tuple[int, str]],
) -> Encerramento:
    instante = datetime.now(timezone.utc)
    identificador = f"{instante:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
    return Encerramento(
        identificador=identificador,
        servidor_id=servidor_id,
        canal_id=canal_id,
        moderador_id=moderador_id,
        criado_em=instante.isoformat(timespec="seconds"),
        participantes={
            usuario_id: ParticipanteEncerramento(usuario_id, nome)
            for usuario_id, nome in participantes
        },
    )


def salvar_encerramento(encerramento: Encerramento) -> Path:
    PASTA_SESSOES.mkdir(parents=True, exist_ok=True)
    caminho = encerramento.caminho or PASTA_SESSOES / f"{encerramento.identificador}.md"
    caminho.resolve().relative_to(PASTA_SESSOES.resolve())
    temporario = caminho.with_suffix(".md.tmp")
    temporario.write_text(encerramento.markdown(), encoding="utf-8", newline="\n")
    temporario.replace(caminho)
    encerramento.caminho = caminho
    return caminho


def listar_encerramentos(servidor_id: int | None = None) -> list[Encerramento]:
    if not PASTA_SESSOES.is_dir():
        return []
    encontrados: list[Encerramento] = []
    for caminho in PASTA_SESSOES.glob("*.md"):
        try:
            encerramento = Encerramento.carregar(caminho)
        except (OSError, ValueError, TypeError, KeyError):
            continue
        if servidor_id is None or encerramento.servidor_id == servidor_id:
            encontrados.append(encerramento)
    return sorted(encontrados, key=lambda item: item.criado_em)


def encerramento_ativo(servidor_id: int) -> Encerramento | None:
    ativos = [item for item in listar_encerramentos(servidor_id) if not item.concluido]
    return ativos[-1] if ativos else None


def ultimo_encerramento_concluido(servidor_id: int) -> Encerramento | None:
    concluidos = [item for item in listar_encerramentos(servidor_id) if item.concluido]
    return concluidos[-1] if concluidos else None
