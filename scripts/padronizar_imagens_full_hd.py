from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import date
from pathlib import Path

from PIL import Image, ImageFilter


RAIZ = Path(__file__).resolve().parents[1]
PASTA_EXPORTACAO = RAIZ / "exports" / "padronizacao_full_hd"
PASTA_BACKUP = RAIZ / "arquivo" / "backups-markdown-full-hd" / date.today().isoformat()
MENOR_MINIMO = 1080
MAIOR_MINIMO = 1920
LIMITE_DISCORD = 25 * 1024 * 1024
PADRAO_REFERENCIA = re.compile(
    r"biblioteca/(?:fichas/imagens|quadribol/vassouras/imagens)/[^\s\"')]+",
    re.IGNORECASE,
)


def sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def dimensoes_destino(largura: int, altura: int) -> tuple[int, int]:
    # Ampliar uma imagem pequena não cria detalhes e a conversão posterior pode
    # suavizar o original. As fichas agora preservam sempre a resolução nativa.
    return largura, altura


def referencias_ativas() -> tuple[set[str], list[Path]]:
    arquivos = [
        *sorted((RAIZ / "biblioteca" / "fichas").rglob("*.md")),
        *sorted((RAIZ / "biblioteca" / "quadribol" / "vassouras").rglob("*.md")),
    ]
    referencias: set[str] = set()
    usados: list[Path] = []
    for caminho in arquivos:
        if "Criaturas" in caminho.parts:
            continue
        texto = caminho.read_text(encoding="utf-8-sig")
        encontradas = set(PADRAO_REFERENCIA.findall(texto))
        if encontradas:
            referencias.update(encontradas)
            usados.append(caminho)
    return referencias, usados


def gerar_full_hd(referencia: str) -> dict[str, object]:
    origem = (RAIZ / referencia).resolve()
    origem.relative_to(RAIZ)
    if not origem.is_file():
        raise FileNotFoundError(referencia)
    with Image.open(origem) as imagem_aberta:
        imagem_aberta.load()
        largura, altura = imagem_aberta.size
        nova_largura, nova_altura = dimensoes_destino(largura, altura)
        if (nova_largura, nova_altura) == (largura, altura):
            return {
                "origem": referencia,
                "arquivo": referencia,
                "antes": [largura, altura],
                "depois": [largura, altura],
                "alterada": False,
                "bytes": origem.stat().st_size,
                "sha256": sha256(origem),
            }

        destino = origem.parent / "full-hd" / f"{origem.stem}-full-hd.webp"
        destino.parent.mkdir(parents=True, exist_ok=True)
        possui_alpha = imagem_aberta.mode in {"RGBA", "LA"} or (
            imagem_aberta.mode == "P" and "transparency" in imagem_aberta.info
        )
        imagem = imagem_aberta.convert("RGBA" if possui_alpha else "RGB")
        imagem = imagem.resize((nova_largura, nova_altura), Image.Resampling.LANCZOS)
        imagem = imagem.filter(ImageFilter.UnsharpMask(radius=1.2, percent=75, threshold=3))
        opcoes = {"format": "WEBP", "method": 6}
        if possui_alpha:
            opcoes["lossless"] = True
        else:
            opcoes["quality"] = 94
        imagem.save(destino, **opcoes)
        if destino.stat().st_size > LIMITE_DISCORD:
            raise ValueError(f"{destino.name} ultrapassou 25 MB.")
        relativo = destino.relative_to(RAIZ).as_posix()
        return {
            "origem": referencia,
            "arquivo": relativo,
            "antes": [largura, altura],
            "depois": [nova_largura, nova_altura],
            "alterada": True,
            "bytes": destino.stat().st_size,
            "sha256": sha256(destino),
        }


def aplicar_referencias(registros: list[dict[str, object]], arquivos: list[Path]) -> int:
    substituicoes = {
        str(registro["origem"]): str(registro["arquivo"])
        for registro in registros
        if registro["alterada"]
    }
    alterados = 0
    for caminho in arquivos:
        texto = caminho.read_text(encoding="utf-8-sig")
        novo = texto
        for origem, destino in substituicoes.items():
            novo = novo.replace(origem, destino)
        if novo == texto:
            continue
        backup = PASTA_BACKUP / caminho.relative_to(RAIZ)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(caminho, backup)
        caminho.write_text(novo, encoding="utf-8", newline="\n")
        alterados += 1
    return alterados


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aplicar", action="store_true")
    args = parser.parse_args()
    referencias, arquivos = referencias_ativas()
    registros: list[dict[str, object]] = []
    falhas: list[dict[str, str]] = []
    for referencia in sorted(referencias):
        try:
            registros.append(gerar_full_hd(referencia))
        except (OSError, ValueError) as erro:
            falhas.append({"arquivo": referencia, "erro": str(erro)})
    PASTA_EXPORTACAO.mkdir(parents=True, exist_ok=True)
    (PASTA_EXPORTACAO / "manifesto.json").write_text(
        json.dumps(registros, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (PASTA_EXPORTACAO / "falhas.json").write_text(
        json.dumps(falhas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_alterados = aplicar_referencias(registros, arquivos) if args.aplicar else 0
    print(f"REFERENCIAS={len(referencias)}")
    print(f"GERADAS={sum(bool(item['alterada']) for item in registros)}")
    print(f"JA_FULL_HD={sum(not bool(item['alterada']) for item in registros)}")
    print(f"FALHAS={len(falhas)}")
    print(f"MARKDOWN_ALTERADOS={markdown_alterados}")
    print(f"APLICADO={args.aplicar}")


if __name__ == "__main__":
    main()
