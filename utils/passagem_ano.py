from __future__ import annotations

import hashlib
import json
import re
import shutil
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from utils.biblioteca import normalizar_rotulo
from utils.fichas import (
    FichaPersonagem,
    PASTA_FICHAS,
    listar_fichas,
    modificador,
    salvar_ficha,
)
from utils.taca import ARQUIVO_TACA, CASAS, EstadoTaca, carregar_estado_taca, salvar_estado_taca


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_BACKUPS = RAIZ_PROJETO / "arquivo" / "passagens-de-ano"
GRUPOS_ALUNOS = (*CASAS, "Players")
PADRAO_ANO = re.compile(r"^\s*([1-7])\s*[º°oª]?\s*ano\s*$", re.IGNORECASE)
PADRAO_IDADE_COMPOSTA = re.compile(r"(\bcom\s+)(\d+)(\s+anos?\b)", re.IGNORECASE)
PADRAO_IDADE_SIMPLES = re.compile(r"^(\s*)(\d+)(\s*(?:anos?)?\s*)$", re.IGNORECASE)
ENSINO_COMPLETO = "Ensino Completo"


@dataclass(frozen=True)
class MudancaFicha:
    caminho: Path
    caminho_novo: Path | None
    nome: str
    grupo: str
    grupo_novo: str
    nivel_anterior: int
    nivel_novo: int
    idade_anterior: str = ""
    idade_nova: str = ""
    ano_anterior: str = ""
    ano_novo: str = ""
    posicao_quadribol: str = ""
    situacao_time: str = ""

    @property
    def aluno(self) -> bool:
        return self.grupo in GRUPOS_ALUNOS

    @property
    def concluiu(self) -> bool:
        correspondencia = PADRAO_ANO.fullmatch(self.ano_anterior)
        return (
            correspondencia is not None
            and int(correspondencia.group(1)) == 7
            and self.ano_novo == ENSINO_COMPLETO
        )

    @property
    def caminho_atual(self) -> Path:
        return self.caminho_novo or self.caminho


@dataclass(frozen=True)
class PreviaPassagemAno:
    token: str
    mudancas: tuple[MudancaFicha, ...]
    pontuacoes_taca: dict[str, int]
    historico_taca: int

    @property
    def alunos(self) -> tuple[MudancaFicha, ...]:
        return tuple(item for item in self.mudancas if item.aluno)

    @property
    def concluintes(self) -> tuple[MudancaFicha, ...]:
        return tuple(item for item in self.mudancas if item.concluiu)


def _informacao(ficha: FichaPersonagem, titulo: str) -> str:
    procurado = normalizar_rotulo(titulo)
    for item in ficha.informacoes:
        if normalizar_rotulo(item.get("titulo", "")) == procurado:
            return item.get("descricao", "").strip()
    return ""


def _definir_informacao(ficha: FichaPersonagem, titulo: str, valor: str) -> None:
    procurado = normalizar_rotulo(titulo)
    for item in ficha.informacoes:
        if normalizar_rotulo(item.get("titulo", "")) == procurado:
            item["descricao"] = valor
            return
    ficha.informacoes.append({"titulo": titulo, "descricao": valor})


def avancar_ano(valor: str) -> str:
    if normalizar_rotulo(valor) in {"completo", "ensino completo"}:
        return ENSINO_COMPLETO
    correspondencia = PADRAO_ANO.fullmatch(valor)
    if correspondencia is None:
        raise ValueError(f"Ano cursando inválido: {valor or '--'}")
    ano = int(correspondencia.group(1))
    return ENSINO_COMPLETO if ano == 7 else f"{ano + 1}°Ano"


def aumentar_idade_composta(valor: str) -> str:
    correspondencia = PADRAO_IDADE_COMPOSTA.search(valor)
    if correspondencia is None:
        raise ValueError(f"Altura e Idade inválidas: {valor or '--'}")
    idade = int(correspondencia.group(2)) + 1
    return valor[: correspondencia.start(2)] + str(idade) + valor[correspondencia.end(2) :]


def aumentar_idade_simples(valor: str) -> str:
    correspondencia = PADRAO_IDADE_SIMPLES.fullmatch(valor)
    if correspondencia is None:
        raise ValueError(f"Idade inválida: {valor or '--'}")
    return f"{correspondencia.group(1)}{int(correspondencia.group(2)) + 1}{correspondencia.group(3)}"


def aplicar_passagem_ficha(ficha: FichaPersonagem) -> MudancaFicha:
    anterior = deepcopy(ficha)
    idade_anterior = ""
    idade_nova = ""
    ano_anterior = ""
    ano_novo = ""
    posicao_quadribol = _informacao(ficha, "Jogador de Quadribol")
    situacao_time = _informacao(ficha, "Situação no time")
    if ficha.grupo in GRUPOS_ALUNOS:
        idade_anterior = _informacao(ficha, "Altura e Idade")
        ano_anterior = _informacao(ficha, "Cursando")
        idade_nova = aumentar_idade_composta(idade_anterior)
        ano_novo = avancar_ano(ano_anterior)
        _definir_informacao(ficha, "Altura e Idade", idade_nova)
        _definir_informacao(ficha, "Cursando", ano_novo)
        if ficha.idade.strip() not in {"", "--"}:
            ficha.idade = aumentar_idade_simples(ficha.idade)
        ficha.ano = ano_novo
        if ano_novo == ENSINO_COMPLETO:
            ficha.grupo = "NPCs"
            # A formatura libera a vaga e encerra o vínculo com o time, mas a
            # vassoura continua sendo propriedade do personagem no inventário.
            campos_time = {
                normalizar_rotulo("Jogador de Quadribol"),
                normalizar_rotulo("Situação no time"),
            }
            ficha.informacoes = [
                informacao
                for informacao in ficha.informacoes
                if normalizar_rotulo(informacao.get("titulo", ""))
                not in campos_time
            ]

    ficha.nivel += 1
    ficha.pontos_atributo_disponiveis += 2
    ficha.pv += 5 + modificador(ficha.atributos["Constituição"])
    ficha.ph += 2 + modificador(ficha.atributos["Sabedoria"])
    return MudancaFicha(
        caminho=Path(),
        caminho_novo=None,
        nome=ficha.nome,
        grupo=anterior.grupo,
        grupo_novo=ficha.grupo,
        nivel_anterior=anterior.nivel,
        nivel_novo=ficha.nivel,
        idade_anterior=idade_anterior,
        idade_nova=idade_nova,
        ano_anterior=ano_anterior,
        ano_novo=ano_novo,
        posicao_quadribol=posicao_quadribol,
        situacao_time=situacao_time,
    )


def caminhos_fichas_ativas() -> list[Path]:
    return [referencia.caminho for referencia in listar_fichas()]


def token_estado(caminhos: list[Path], caminho_taca: Path = ARQUIVO_TACA) -> str:
    digest = hashlib.sha256()
    for caminho in sorted(caminhos, key=lambda item: item.as_posix().casefold()):
        digest.update(caminho.resolve().as_posix().encode("utf-8"))
        digest.update(caminho.read_bytes())
    digest.update(caminho_taca.resolve().as_posix().encode("utf-8"))
    digest.update(caminho_taca.read_bytes() if caminho_taca.is_file() else b"")
    return digest.hexdigest()


def preparar_passagem_ano(
    caminhos: list[Path] | None = None,
    caminho_taca: Path = ARQUIVO_TACA,
    pasta_fichas: Path = PASTA_FICHAS,
) -> PreviaPassagemAno:
    arquivos = caminhos or caminhos_fichas_ativas()
    mudancas: list[MudancaFicha] = []
    for caminho in arquivos:
        ficha = FichaPersonagem.carregar(caminho)
        mudanca = aplicar_passagem_ficha(ficha)
        caminho_novo: Path | None = None
        if mudanca.concluiu:
            try:
                caminho.resolve().relative_to(pasta_fichas.resolve())
            except ValueError:
                pass
            else:
                caminho_novo = pasta_fichas / "NPCs" / caminho.name
        mudancas.append(
            MudancaFicha(
                **{
                    **asdict(mudanca),
                    "caminho": caminho,
                    "caminho_novo": caminho_novo,
                }
            )
        )
    taca = carregar_estado_taca(caminho_taca)
    return PreviaPassagemAno(
        token=token_estado(arquivos, caminho_taca),
        mudancas=tuple(mudancas),
        pontuacoes_taca=dict(taca.pontuacoes),
        historico_taca=len(taca.historico),
    )


def executar_passagem_ano(
    previa: PreviaPassagemAno,
    *,
    caminho_taca: Path = ARQUIVO_TACA,
    pasta_backups: Path = PASTA_BACKUPS,
) -> Path:
    caminhos = [item.caminho for item in previa.mudancas]
    if token_estado(caminhos, caminho_taca) != previa.token:
        raise ValueError("As fichas ou a Taça mudaram depois da prévia. Abra o comando novamente.")
    instante = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup = pasta_backups / instante
    while backup.exists():
        backup = backup.with_name(backup.name + "-1")
    backup.mkdir(parents=True)
    copias: list[tuple[Path, Path]] = []
    movidos: list[tuple[Path, Path]] = []
    for indice, caminho in enumerate(caminhos):
        copia = backup / "fichas" / f"{indice:03d}-{caminho.name}"
        copia.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(caminho, copia)
        copias.append((caminho, copia))
    if caminho_taca.is_file():
        copia_taca = backup / "taca" / caminho_taca.name
        copia_taca.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(caminho_taca, copia_taca)
        copias.append((caminho_taca, copia_taca))
    try:
        for mudanca in previa.mudancas:
            caminho = mudanca.caminho
            destino = mudanca.caminho_atual
            if destino != caminho and destino.exists():
                raise FileExistsError(
                    f"Já existe uma ficha de NPC com o nome {destino.stem}."
                )
            ficha = FichaPersonagem.carregar(caminho)
            aplicar_passagem_ficha(ficha)
            salvar_ficha(ficha, caminho)
            if destino != caminho:
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(caminho), str(destino))
                movidos.append((caminho, destino))
        salvar_estado_taca(EstadoTaca(), caminho_taca)
        resumo = {
            "executada_em": datetime.now().isoformat(timespec="seconds"),
            "fichas": len(previa.mudancas),
            "alunos": len(previa.alunos),
            "concluintes": [item.nome for item in previa.concluintes],
            "pontuacao_anterior": previa.pontuacoes_taca,
            "historico_anterior": previa.historico_taca,
        }
        (backup / "resumo.json").write_text(
            json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception:
        for original, destino in reversed(movidos):
            if destino.exists():
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destino), str(original))
        for original, copia in copias:
            shutil.copy2(copia, original)
        raise
    return backup
