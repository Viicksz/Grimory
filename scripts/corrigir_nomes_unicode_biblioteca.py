from __future__ import annotations

import re
from pathlib import Path


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_BIBLIOTECA = RAIZ_PROJETO / "biblioteca"


def decodificar_nome_unicode(nome: str) -> str:
    def substituir(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))

    return re.sub(r"#U([0-9a-fA-F]{4})", substituir, nome)


def mesclar_diretorios(origem: Path, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)

    for item in list(origem.iterdir()):
        alvo = destino / decodificar_nome_unicode(item.name)

        if item.is_dir():
            if alvo.exists() and alvo.is_dir():
                mesclar_diretorios(item, alvo)
                if item.exists() and not any(item.iterdir()):
                    item.rmdir()
            elif not alvo.exists():
                item.rename(alvo)
            continue

        if alvo.exists():
            try:
                iguais = item.read_bytes() == alvo.read_bytes()
            except OSError:
                iguais = False

            if iguais:
                item.unlink()
        else:
            item.rename(alvo)

    if origem.exists() and origem != destino and not any(origem.iterdir()):
        origem.rmdir()


def corrigir_nomes_unicode_biblioteca() -> None:
    if not PASTA_BIBLIOTECA.is_dir():
        return

    for caminho in sorted(
        PASTA_BIBLIOTECA.rglob("*"),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        novo_nome = decodificar_nome_unicode(caminho.name)

        if novo_nome == caminho.name or not caminho.exists():
            continue

        destino = caminho.with_name(novo_nome)

        try:
            if caminho.is_dir() and destino.exists() and destino.is_dir():
                mesclar_diretorios(caminho, destino)
            elif caminho.is_file() and destino.exists() and destino.is_file():
                if caminho.read_bytes() == destino.read_bytes():
                    caminho.unlink()
            elif not destino.exists():
                caminho.rename(destino)
        except OSError as erro:
            print(f"[AVISO] Não foi possível corrigir o nome {caminho.name}: {erro}")


if __name__ == "__main__":
    corrigir_nomes_unicode_biblioteca()
