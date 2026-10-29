from __future__ import annotations

import json
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any


INICIO_BLOCO = "<!-- GRIMORY_COMBATE"
FIM_BLOCO = "GRIMORY_COMBATE -->"
PADRAO_BLOCO = re.compile(
    rf"\n?{re.escape(INICIO_BLOCO)}\s*\n(?P<json>.*?)\n{re.escape(FIM_BLOCO)}\n?",
    re.DOTALL,
)

MIRAS = ("Lampejo", "Campo de Visão", "Intuição", "Contato", "Pessoal", "Especial")
ALCANCES = ("Pessoal", "Contato", "Curto", "Médio", "Longo", "Campo de Visão", "Especial")
ALVOS = ("Pessoal", "Criatura", "Objeto", "Ponto", "Múltiplos", "Área", "Especial")
TIPOS_ACAO = ("Livre", "Movimento", "Padrão", "Completa", "Reação")
ATIVACOES = ("Instantânea", "Sustentada", "Preparada")
UNIDADES_DURACAO = ("Instantâneo", "Turno", "Rodada", "Minuto", "Cena")
TIPOS_EFEITO = (
    "Dano",
    "Cura",
    "Proteção",
    "Buff",
    "Debuff",
    "Controle",
    "Invocação",
    "Transformação",
    "Utilidade",
    "Contra-feitiço",
)
MOMENTOS_DEFESA = ("Não é defesa", "Antecipada", "Reação", "Ambas")
MOMENTOS_CONTRA_FEITICO = (
    "Não se aplica",
    "Reação imediata",
    "Defesa preparada",
    "Reação imediata e defesa preparada",
    "Reversão ou tratamento",
)
RESPOSTAS = (
    "Nenhuma",
    "Esquiva",
    "Defesa",
    "Contra-feitiço",
    "Vontade",
    "Fortitude",
    "Reflexo",
    "Especial",
)
ACUMULOS = ("Não acumula", "Acumula", "Substitui o anterior", "Especial")


def perfil_vazio() -> dict[str, Any]:
    return {
        "versao": 2,
        "estado": "rascunho",
        "mira": "",
        "detalhes_mira": "",
        "tipo_acao": "",
        "ativacao": "",
        "gatilho": "",
        "duracao": {"valor": "", "unidade": ""},
        "alcance": "",
        "detalhes_alcance": "",
        "alvo": "",
        "detalhes_alvo": "",
        "area": "",
        "tipos": [],
        "respostas": [],
        "acumulo": "",
        "encerramento": "",
        "encerramento_tipo": "",
        "contramagia": "",
        "concentracao": {
            "exigida": False,
            "pericia": "Vontade",
            "cd": "Mesma CD do feitiço",
            "gatilho": "Sempre que houver uma distração",
        },
        "protecao": {"pv": "", "cobertura": "", "reducao": ""},
        "dano": {
            "inicial": "",
            "tipo_inicial": "",
            "sustentado": "",
            "tipo_sustentado": "",
            "frequencia": "",
        },
        "cura": {"formula": "", "recurso": "", "frequencia": ""},
        "defesa": {
            "momento": "Não é defesa",
            "ajuste_cd_reacao": 0,
            "ocasioes": "",
            "propriedades": [],
        },
        "contra_feitico": {
            "habilitado": False,
            "momento": "",
            "feiticos": [],
            "propriedades": [],
            "resultado": "",
        },
    }


def normalizar_perfil(dados: dict[str, Any] | None) -> dict[str, Any]:
    perfil = perfil_vazio()
    if not dados:
        return perfil
    for chave, valor in dados.items():
        if chave in perfil and isinstance(perfil[chave], dict) and isinstance(valor, dict):
            perfil[chave].update(deepcopy(valor))
        else:
            perfil[chave] = deepcopy(valor)
    perfil["versao"] = 2
    # Descrições narrativas de efeitos duplicam a descrição principal do feitiço.
    perfil.pop("efeitos", None)

    mira = str(perfil.get("mira", "")).strip()
    if mira and mira not in MIRAS:
        if not perfil.get("detalhes_mira"):
            perfil["detalhes_mira"] = mira
        perfil["mira"] = "Especial"

    alcance = str(perfil.get("alcance", "")).strip()
    if alcance and alcance not in ALCANCES:
        if not perfil.get("detalhes_alcance"):
            perfil["detalhes_alcance"] = alcance
        perfil["alcance"] = "Especial"

    alvo = str(perfil.get("alvo", "")).strip()
    area = str(perfil.get("area", "")).strip()
    if area and not alvo:
        perfil["alvo"] = "Área"
    elif alvo and alvo not in ALVOS:
        if not perfil.get("detalhes_alvo"):
            perfil["detalhes_alvo"] = alvo
        perfil["alvo"] = "Especial"
    ativacao = perfil.get("ativacao")
    sustentada = ativacao == "Sustentada"
    perfil["concentracao"].update(
        {
            "exigida": sustentada,
            "pericia": "Vontade",
            "cd": "Mesma CD do feitiço",
            "gatilho": "Sempre que houver uma distração",
        }
    )
    # A resposta é uma escolha do mestre.  Esquiva/Reflexo podem ser
    # sugeridos pela interface, mas nunca devem ser inseridos ou removidos
    # automaticamente conforme a forma de manifestação.
    respostas = [item for item in perfil.get("respostas", []) if item in RESPOSTAS]
    if len(respostas) > 1:
        respostas = [item for item in respostas if item != "Nenhuma"]
    perfil["respostas"] = respostas
    return perfil


def extrair_perfil(conteudo: str) -> dict[str, Any] | None:
    encontrado = PADRAO_BLOCO.search(conteudo)
    if encontrado is None:
        return None
    dados = json.loads(encontrado.group("json"))
    if not isinstance(dados, dict):
        raise ValueError("O bloco técnico de combate precisa conter um objeto JSON.")
    return normalizar_perfil(dados)


def remover_bloco(conteudo: str) -> str:
    return PADRAO_BLOCO.sub("\n", conteudo, count=1).strip() + "\n"


def aplicar_perfil(conteudo: str, perfil: dict[str, Any]) -> str:
    base = remover_bloco(conteudo).rstrip()
    bloco = (
        f"{INICIO_BLOCO}\n"
        f"{json.dumps(normalizar_perfil(perfil), ensure_ascii=False, indent=2)}\n"
        f"{FIM_BLOCO}"
    )
    linhas = base.splitlines()
    indice_titulo = next(
        (indice for indice, linha in enumerate(linhas) if linha.startswith("# ")),
        None,
    )
    if indice_titulo is None:
        return f"{bloco}\n\n{base}\n"
    linhas[indice_titulo + 1:indice_titulo + 1] = ["", bloco]
    return "\n".join(linhas).rstrip() + "\n"


def escrever_atomico(caminho: Path, conteudo: str) -> None:
    caminho = caminho.resolve()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    descritor, temporario = tempfile.mkstemp(
        prefix=f".{caminho.name}.", suffix=".tmp", dir=caminho.parent
    )
    os.close(descritor)
    temporario_path = Path(temporario)
    try:
        temporario_path.write_text(conteudo, encoding="utf-8", newline="\n")
        os.replace(temporario_path, caminho)
    finally:
        temporario_path.unlink(missing_ok=True)


def salvar_perfil(caminho: Path, perfil: dict[str, Any]) -> None:
    conteudo = caminho.read_text(encoding="utf-8")
    escrever_atomico(caminho, aplicar_perfil(conteudo, perfil))


PADRAO_MECANICA_LEGADA = re.compile(
    r"^\*\*(?:"
    r"(?:PV\s*:.*)|"
    r"(?:Rea[cç][aã]o)|"
    r"(?:Instant[aâ]neo)|"
    r"(?:Dura[cç][aã]o\b.*)|"
    r"(?:.*\b\d*d\d+(?:\s*[+\-]\s*[^ ]+)?\s+de\s+(?:dano|cura).*)|"
    r"(?:.*\bdano\b.*por\s+(?:turno|rodada).*)|"
    r"(?:quando\s+conjurado\s+como\s+rea[cç][aã]o.*)"
    r")\.?\*\*$",
    re.IGNORECASE,
)


def limpar_mecanicas_legadas(descricao: str) -> str:
    linhas = [
        linha
        for linha in descricao.splitlines()
        if not PADRAO_MECANICA_LEGADA.match(linha.strip())
    ]
    return "\n".join(linhas).strip()


def substituir_descricao(conteudo: str, descricao: str) -> str:
    linhas = conteudo.splitlines()
    inicio = next(
        (
            indice
            for indice, linha in enumerate(linhas)
            if linha.strip().casefold() in {"descrição:", "descricao:"}
        ),
        None,
    )
    if inicio is None:
        raise ValueError("A ficha não possui o campo Descrição.")
    fim = len(linhas)
    for indice in range(inicio + 1, len(linhas)):
        linha = linhas[indice].strip()
        if linha.endswith(":") and not linha.startswith(("**", "`", "_")):
            fim = indice
            break
    novas = linhas[: inicio + 1] + descricao.strip().splitlines() + [""] + linhas[fim:]
    return "\n".join(novas).rstrip() + "\n"


def salvar_revisao(caminho: Path, perfil: dict[str, Any], descricao: str) -> None:
    conteudo = caminho.read_text(encoding="utf-8")
    conteudo = remover_bloco(conteudo)
    conteudo = substituir_descricao(conteudo, descricao)
    escrever_atomico(caminho, aplicar_perfil(conteudo, perfil))


def _plural(valor: str, unidade: str) -> str:
    if not valor or valor == "1":
        return unidade.casefold()
    mapa = {
        "Turno": "turnos",
        "Rodada": "rodadas",
        "Minuto": "minutos",
        "Cena": "cenas",
    }
    return mapa.get(unidade, unidade.casefold())


def linha_duracao(perfil: dict[str, Any]) -> str:
    ativacao = perfil.get("ativacao", "")
    duracao = perfil.get("duracao", {})
    unidade = str(duracao.get("unidade", ""))
    valor = str(duracao.get("valor", "")).strip()
    if ativacao == "Instantânea" or unidade == "Instantâneo":
        return "Instantâneo."
    if unidade == "Cena":
        return f"Duração de {valor + ' ' if valor else ''}{_plural(valor, unidade)}."
    if unidade:
        quantidade = valor or "1"
        return f"Duração de {quantidade} {_plural(quantidade, unidade)}."
    return ""


def linhas_publicas(perfil_original: dict[str, Any] | None) -> list[str]:
    perfil = normalizar_perfil(perfil_original)
    linhas: list[str] = []
    if perfil.get("mira"):
        mira = str(perfil["mira"])
        detalhes = str(perfil.get("detalhes_mira", "")).strip()
        linhas.append(
            f"Tipo de Feitiço: {mira} — {detalhes}."
            if detalhes
            else f"Tipo de Feitiço: {mira}."
        )
    if perfil.get("alcance"):
        alcance = str(perfil["alcance"])
        detalhes = str(perfil.get("detalhes_alcance", "")).strip()
        linhas.append(
            f"Alcance: {alcance} — {detalhes}."
            if detalhes
            else f"Alcance: {alcance}."
        )
    if perfil.get("alvo"):
        alvo = str(perfil["alvo"])
        detalhes = (
            str(perfil.get("area", "")).strip()
            if alvo == "Área"
            else str(perfil.get("detalhes_alvo", "")).strip()
        )
        linhas.append(
            f"Alvo: {alvo} — {detalhes}." if detalhes else f"Alvo: {alvo}."
        )
    ativacao = str(perfil.get("ativacao", "")).strip()
    if ativacao:
        linhas.append(f"Tempo de Execução: {ativacao}.")
    duracao = linha_duracao(perfil)
    # Instantânea já está representada pelo tempo de execução; para as
    # demais ativações, a duração continua aparecendo separadamente.
    if duracao and duracao.casefold() != "instantâneo.":
        linhas.append(duracao)
    contramagia = str(perfil.get("contramagia", "")).strip()
    if contramagia:
        linhas.append(f"Contra-feitiço: {contramagia}.")
    protecao = perfil.get("protecao", {})
    if protecao.get("pv"):
        linhas.append(f"PV: {str(protecao['pv']).rstrip('.')}.")
    if protecao.get("cobertura"):
        linhas.append(f"Cobertura: {str(protecao['cobertura']).strip().rstrip('.')}.")
    dano = perfil.get("dano", {})
    danos: list[str] = []
    if dano.get("inicial"):
        tipo = f" {dano.get('tipo_inicial', '').strip()}" if dano.get("tipo_inicial") else ""
        danos.append(f"{dano['inicial']} de dano{tipo}")
    if dano.get("sustentado"):
        tipo = f" {dano.get('tipo_sustentado', '').strip()}" if dano.get("tipo_sustentado") else ""
        frequencia = str(dano.get("frequencia", "turno")).strip() or "turno"
        danos.append(f"{dano['sustentado']} de dano{tipo} por {frequencia} sustentado")
    if danos:
        linhas.append(", ".join(danos) + ".")
    cura = perfil.get("cura", {})
    if cura.get("formula"):
        recurso = str(cura.get("recurso", "vida")).strip() or "vida"
        frequencia = str(cura.get("frequencia", "")).strip()
        sufixo = f" por {frequencia}" if frequencia else ""
        linhas.append(f"{cura['formula']} de recuperação de {recurso}{sufixo}.")
    return linhas


def descricao_publica(descricao: str, perfil: dict[str, Any] | None) -> str:
    linhas = linhas_publicas(perfil)
    if not linhas:
        return descricao.strip()
    mira, *mecanicas = linhas
    # Mantém a leitura natural: mira, alcance/alvo/duração, resumo do efeito
    # e só então o texto narrativo original.
    partes = [f"`{mira}`"]
    partes.extend(f"`{linha}`" for linha in mecanicas)
    if descricao.strip():
        partes.append(descricao.strip())
    return "\n".join(parte for parte in partes if parte)


def pendencias(perfil_original: dict[str, Any] | None) -> list[str]:
    perfil = normalizar_perfil(perfil_original)
    faltas = []
    for chave, rotulo in (
        ("mira", "forma de mira"),
        ("alcance", "alcance"),
        ("alvo", "tipo de alvo"),
        ("tipo_acao", "tipo de ação"),
        ("ativacao", "ativação"),
        ("tipos", "tipo de efeito"),
        ("respostas", "resistência ou reação"),
        ("acumulo", "acúmulo"),
        ("encerramento", "interrupção ou encerramento"),
        ("contramagia", "contra-feitiço deste feitiço"),
    ):
        if not perfil.get(chave):
            faltas.append(rotulo)
    if perfil.get("mira") == "Especial" and not perfil.get("detalhes_mira"):
        faltas.append("condição especial da manifestação")
    if perfil.get("alcance") == "Especial" and not perfil.get("detalhes_alcance"):
        faltas.append("condição especial do alcance")
    if perfil.get("alvo") == "Especial" and not perfil.get("detalhes_alvo"):
        faltas.append("condição especial do alvo")
    if perfil.get("alvo") == "Área" and not perfil.get("area"):
        faltas.append("dimensões e afetados da área")
    if perfil.get("ativacao") == "Preparada" and not perfil.get("gatilho"):
        faltas.append("gatilho da magia preparada")
    if perfil.get("ativacao") != "Instantânea":
        duracao = perfil.get("duracao", {})
        if not duracao.get("unidade"):
            faltas.append("duração")
    if "Dano" in perfil.get("tipos", []) and not perfil.get("dano", {}).get("inicial") and not perfil.get("dano", {}).get("sustentado"):
        faltas.append("dano")
    if "Cura" in perfil.get("tipos", []) and not perfil.get("cura", {}).get("formula"):
        faltas.append("cura")
    if "Proteção" in perfil.get("tipos", []) and not any(perfil.get("protecao", {}).values()):
        faltas.append("proteção")
    defesa = perfil.get("defesa", {})
    if defesa.get("momento") in {"Antecipada", "Reação", "Ambas"} and not (
        defesa.get("propriedades") or defesa.get("ocasioes")
    ):
        faltas.append("ocasiões da defesa")
    contra = perfil.get("contra_feitico", {})
    contra_selecionado = "Contra-feitiço" in perfil.get("tipos", [])
    if contra_selecionado and not (contra.get("habilitado") and contra.get("momento")):
        faltas.append("modo de uso do contra-feitiço")
    if contra.get("habilitado") or contra_selecionado:
        if not contra.get("feiticos"):
            faltas.append("feitiço anulado selecionado na biblioteca")
    return faltas
