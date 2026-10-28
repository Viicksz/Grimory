from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
PASTA = RAIZ / "biblioteca" / "quadribol" / "vassouras"

# Somente o modelo final de uma linha pode chegar a +2, e apenas em sua
# especialidade principal. Todos os demais bônus fixos param em +1. Não há +3.
BONUS_PROGRESSIVOS: dict[str, dict[str, str]] = {
    "Cavalier Sabre": {"bonus de pontaria:": "2"},
    "Cleansweep 11": {"bonus de voo:": "2"},
    "Comet 290": {"bonus de reflexo:": "2"},
    "Estrela Cadente Série III": {"bonus de voo:": "2"},
    "Firebolt Suprema": {"bonus de voo:": "2"},
    "Nimbus 2001": {"bonus de voo:": "2"},
    "Oakshaft 79": {"bonus de fortitude:": "2"},
    "Swiftstick Ultra": {"bonus de reflexo:": "2"},
    "Yajirushi Caçadora": {"bonus de pontaria:": "2"},
}

CONTROLE_DE_TRAJETORIA_FINAL = {
    "Bluebottle Vento de Cauda",
    "Onda Aérea Platina",
    "Stormrider Tufão",
}

PONTARIA_DIRETA = {
    "Cavalier Adaga": "1",
    "Cavalier Espadim": "1",
    "Cavalier Espadim: Garanhão do Inverno": "1",
    "Cavalier Sabre": "2",
    "Cleansweep 11": "1",
    "Oakshaft 79": "1",
    "Stormrider Ciclone": "1",
    "Stormrider Furacão": "2",
    "Yajirushi Arqueiro": "1",
    "Yajirushi Caçadora": "2",
}

PONTARIA_SITUACIONAL = {
    "Thunderbolt VII",
    "Thunderbolt X",
    "Thunderbolt X: Rabo-córneo",
}

FORTITUDE_DA_VASSOURA = {
    "Cavalier Adaga": 1,
    "Stormrider Tempestade de Areia": 2,
}

CONTROLE_DE_TRAJETORIA = {
    "Bluebottle Vento de Cauda": 2,
    "Cavalier Adaga": 1,
    "Cavalier Espadim": 1,
    "Cavalier Espadim: Garanhão do Inverno": 1,
    "Cavalier Sabre": 1,
    "Cleansweep 5": 1,
    "Comet 260": 1,
    "Comet 290": 1,
    "Onda Aérea Ouro": 2,
    "Onda Aérea Platina": 2,
    "Stormrider Ciclone": 1,
    "Stormrider Furacão": 2,
    "Stormrider Tempestade de Areia": 1,
    "Stormrider Tufão": 2,
    "Yajirushi Arqueiro": 2,
    "Yajirushi Caçadora": 2,
}


def normalizar(texto: str) -> str:
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caractere)
    ).casefold().strip()


def titulo(texto: str, arquivo: Path) -> str:
    encontrado = re.search(r"(?m)^#\s+(.+?)\s*$", texto)
    return encontrado.group(1).strip() if encontrado else arquivo.stem


def campos_numericos(linhas: list[str]) -> dict[str, int]:
    resultado: dict[str, int] = {}
    for indice, linha in enumerate(linhas[:-1]):
        rotulo = normalizar(linha)
        if rotulo.startswith("bonus de ") and rotulo.endswith(":"):
            valor = linhas[indice + 1].strip().lower().removeprefix("+")
            if valor.isdigit():
                resultado[rotulo] = int(valor)
    return resultado


def bonus_da_especificacao(
    nome: str,
    texto: str,
    bonus: dict[str, int],
) -> str:
    regra = normalizar(texto)
    if "pontaria" in regra:
        if (
            nome in PONTARIA_SITUACIONAL
            or "redirecionar contra um adversario" in regra
            or "rebater a goles em direcao a um aliado" in regra
        ):
            return "+1d4"
        return f"+{bonus.get('bonus de pontaria:', 1)}"
    if "reflexo para defender os aros" in regra:
        return f"+{bonus.get('bonus de reflexo:', 1)}"
    if re.fullmatch(r".*reflexo para esquivar\.?", regra):
        return f"+{bonus.get('bonus de reflexo:', 1)}"
    if ("voo geral" in regra or "voo gerais" in regra) and not any(
        termo in regra for termo in ("durante", "sob", "quando", "apos")
    ):
        return f"+{bonus.get('bonus de voo:', 1)}"
    if re.fullmatch(r".*fortitude\.?", regra):
        return f"+{bonus.get('bonus de fortitude:', 1)}"
    if "fortitude da vassoura" in regra:
        return "+1"
    if "controle de trajetoria" in regra and not any(
        termo in regra for termo in ("apos", "clima", "chuva", "vento", "poeira")
    ):
        return "+2" if nome in CONTROLE_DE_TRAJETORIA_FINAL else "+1"
    if "controle fino de trajetoria" in regra and nome.startswith("Yajirushi"):
        return "+1"
    if "voo para controle de impulso" in regra:
        return "+1"
    if "voo envolvendo velocidade em linha reta" in regra:
        return "+1"
    return "+1d4"


def normalizar_arquivo(arquivo: Path, texto: str) -> str:
    nome = titulo(texto, arquivo)
    linhas = texto.replace("1d4+1", "1d4").splitlines()
    substituicoes = BONUS_PROGRESSIVOS.get(nome, {})

    for indice, linha in enumerate(linhas[:-1]):
        rotulo = normalizar(linha)
        if rotulo == "bonus de pontaria:" and nome in PONTARIA_SITUACIONAL:
            linhas[indice + 1] = "1d4"
        elif rotulo.startswith("bonus de ") and rotulo.endswith(":"):
            atual = linhas[indice + 1].strip().lower().removeprefix("+")
            desejado = substituicoes.get(rotulo, atual)
            if rotulo == "bonus de pontaria:" and nome in PONTARIA_DIRETA:
                desejado = substituicoes.get(rotulo, PONTARIA_DIRETA[nome])
            if desejado.isdigit():
                limite = 2 if rotulo in substituicoes else 1
                linhas[indice + 1] = str(min(int(desejado), limite))

    bonus = campos_numericos(linhas)
    resultado: list[str] = []
    for linha in linhas:
        encontrado = re.match(
            r"^(\s*-\s*)\+(?:\d+|1d4)\s+em testes(.*)$",
            linha,
            re.IGNORECASE,
        )
        if encontrado:
            prefixo, restante = encontrado.groups()
            valor = bonus_da_especificacao(nome, restante, bonus)
            linha = f"{prefixo}{valor} em testes{restante}"
        resultado.append(linha)
    return "\n".join(resultado) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    argumentos = parser.parse_args()
    alterados = 0
    linhas_alteradas = 0
    for arquivo in sorted(PASTA.glob("*.md")):
        anterior = arquivo.read_text(encoding="utf-8-sig")
        novo = normalizar_arquivo(arquivo, anterior)
        if novo == anterior:
            continue
        alterados += 1
        diferencas = [
            (indice, antes, depois)
            for indice, (antes, depois) in enumerate(
                zip(anterior.splitlines(), novo.splitlines(), strict=False), start=1
            )
            if antes != depois
        ]
        linhas_alteradas += len(diferencas)
        if argumentos.verbose:
            print(arquivo.name)
            for indice, antes, depois in diferencas:
                print(f"  {indice}: {antes!r} -> {depois!r}")
        if argumentos.apply:
            arquivo.write_text(novo, encoding="utf-8", newline="\n")
    modo = "aplicados" if argumentos.apply else "previstos"
    print(f"{alterados} arquivos e {linhas_alteradas} ajustes {modo}.")


if __name__ == "__main__":
    main()
