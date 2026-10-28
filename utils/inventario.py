from __future__ import annotations

from collections.abc import Iterable

import discord

from utils.biblioteca import PASTA_BIBLIOTECA, normalizar_rotulo


CATEGORIAS_ITENS = (
    "Dinheiro",
    "Ingredientes",
    "Poções",
    "Alimentos",
    "Armas",
    "Variados",
)

EMOJIS_ITENS = {
    "Dinheiro": "💰",
    "Ingredientes": "🪶",
    "Poções": "🧪",
    "Alimentos": "🥧",
    "Armas": "🗡️",
    "Variados": "🧭",
}

MOEDAS = ("Galeão(ões)", "Sicle(s)", "Nuque(s)")
TIPOS_INGREDIENTE = ("Líquido", "Sólido")
UNIDADES_INGREDIENTE = ("ml", "unidade", "g", "kg")
ARQUIVO_INGREDIENTES = PASTA_BIBLIOTECA / "ingredientes" / "Ingredientes de Poções.md"
GRUPOS_INGREDIENTES_APRESENTACAO = (
    ("Líquidos, Essências e Extratos", "💧"),
    ("Plantas, Ervas e Flores", "🌿"),
    ("Fungos e Organismos Mágicos", "🍄"),
    ("Répteis e Anfíbios", "🐍"),
    ("Partes de Animais Comuns", "🦇"),
    ("Partes de Criaturas Mágicas", "🐉"),
    ("Insetos e Pequenas Criaturas", "🐌"),
    ("Penas e Materiais Leves", "🪶"),
    ("Minerais, Pós e Substâncias", "🪨"),
    ("Ingredientes Raros e Nobres", "🦄"),
)
TIPOS_ALIMENTO = (
    "Vegetais",
    "Frutas",
    "Enlatados",
    "Refeições",
    "Bebidas",
    "Doces",
    "Salgados",
)
def inteiro_positivo(valor: str | int, padrao: int = 1) -> int:
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        return padrao
    return max(0, numero)


def ingredientes_oficiais_por_grupo() -> dict[str, list[str]]:
    grupos: dict[str, list[str]] = {}
    if not ARQUIVO_INGREDIENTES.is_file():
        return grupos
    grupo = "Outros ingredientes"
    for linha in ARQUIVO_INGREDIENTES.read_text(encoding="utf-8-sig").splitlines():
        if linha.startswith("## "):
            grupo = linha.removeprefix("## ").strip()
            grupos.setdefault(grupo, [])
        elif linha.startswith("- "):
            grupos.setdefault(grupo, []).append(linha.removeprefix("- ").strip())
    return {nome: itens for nome, itens in grupos.items() if itens}


def emoji_grupo_ingredientes(rotulo: str) -> str:
    return next(
        (
            emoji
            for nome, emoji in GRUPOS_INGREDIENTES_APRESENTACAO
            if rotulo.startswith(nome)
        ),
        "📦",
    )


def unidade_ingrediente_oficial(nome: str, grupo: str = "") -> tuple[str, str]:
    chave = normalizar_rotulo(nome)
    grupo_normalizado = normalizar_rotulo(grupo)
    termos_liquidos = (
        "agua",
        "sangue",
        "seiva",
        "muco",
        "veneno",
        "urina",
        "meleca",
        "lagrima",
        "suco",
        "mercurio",
        "vinagre",
        "oleo",
        "essencia",
        "infusao",
        "orvalho",
    )
    if "liquidos" in grupo_normalizado or any(
        termo in chave for termo in termos_liquidos
    ):
        return "Líquido", "ml"
    if " po" in f" {chave}" or chave.startswith("po de"):
        return "Sólido", "g"
    return "Sólido", "unidade"


def nome_moeda(item: dict[str, str]) -> str:
    return item.get("tipo") or item.get("nome") or "Galeão(ões)"


def eh_galeao(item: dict[str, str]) -> bool:
    return (
        normalizar_rotulo(item.get("categoria", "")) == normalizar_rotulo("Dinheiro")
        and normalizar_rotulo(nome_moeda(item)).startswith("gale")
    )


def metadados_galeoes(ficha) -> dict[str, str] | None:
    return next((item for item in ficha.itens if eh_galeao(item)), None)


def itens_exibidos(ficha) -> list[dict[str, str]]:
    itens = [dict(item) for item in ficha.itens if not eh_galeao(item)]
    if ficha.galeoes > 0:
        metadados = metadados_galeoes(ficha) or {}
        itens.insert(
            0,
            {
                "categoria": "Dinheiro",
                "nome": "Galeão(ões)",
                "tipo": "Galeão(ões)",
                "quantidade": str(ficha.galeoes),
                "_origem": "galeoes",
                **({"imagem": metadados["imagem"]} if metadados.get("imagem") else {}),
            },
        )
    return itens


def plural_unidade(unidade: str, quantidade: int) -> str:
    if quantidade == 1:
        return {
            "unidade": "unidade",
            "frasco": "frasco",
            "Galeão(ões)": "Galeão",
            "Sicle(s)": "Sicle",
            "Nuque(s)": "Nuque",
        }.get(unidade, unidade)
    return {
        "unidade": "unidades",
        "frasco": "frascos",
        "Galeão(ões)": "Galeões",
        "Sicle(s)": "Sicles",
        "Nuque(s)": "Nuques",
    }.get(unidade, unidade)


def formatar_item(item: dict[str, str]) -> str:
    def com_imagem(texto: str) -> str:
        imagem = item.get("imagem", "").strip()
        if not imagem:
            return texto
        if imagem.startswith(("http://", "https://")):
            return f"{texto}\n> [📷 Ver imagem]({imagem})"
        return f"{texto}\n> 📷 Foto cadastrada"

    categoria = item.get("categoria", "Variados")
    nome = item.get("nome", "Item")
    quantidade = inteiro_positivo(item.get("quantidade", "1"))
    if categoria == "Dinheiro":
        moeda = nome_moeda(item)
        return com_imagem(f"» **{quantidade}** {plural_unidade(moeda, quantidade)}")
    if categoria == "Ingredientes":
        unidade = plural_unidade(item.get("unidade", "unidade"), quantidade)
        return com_imagem(f"» **{nome}** — {quantidade} {unidade}")
    if categoria == "Alimentos":
        tipo = f" *{item['tipo']}*" if item.get("tipo") else ""
        return com_imagem(f"» **{nome}**{tipo} — {quantidade}x")
    if categoria == "Variados":
        if normalizar_rotulo(item.get("tipo", "")) == normalizar_rotulo("Vassoura"):
            # A ficha guarda somente o nome do modelo. Os dados mecânicos são
            # consultados no catálogo para que qualquer ajuste oficial apareça
            # automaticamente em todos os inventários.
            from utils.quadribol import encontrar_vassoura

            vassoura = encontrar_vassoura(nome)
            if vassoura is not None:
                bonus = [
                    f"Vôo {vassoura.bonus_voo:+d}",
                    f"Reflexo {vassoura.bonus_reflexo:+d}",
                    f"Fortitude {vassoura.bonus_fortitude:+d}",
                ]
                if vassoura.dado_bonus_pontaria:
                    pontaria = f"Pontaria +{vassoura.dado_bonus_pontaria}"
                    if vassoura.uso_bonus_pontaria:
                        pontaria += f" em {vassoura.uso_bonus_pontaria}"
                    bonus.append(pontaria)
                elif vassoura.bonus_pontaria or vassoura.uso_bonus_pontaria:
                    pontaria = f"Pontaria {vassoura.bonus_pontaria:+d}"
                    if vassoura.uso_bonus_pontaria:
                        pontaria += f" em {vassoura.uso_bonus_pontaria}"
                    bonus.append(pontaria)

                estado = " • *Equipada*" if normalizar_rotulo(item.get("equipada", "")) == normalizar_rotulo("Sim") else ""
                linhas = [
                    f"» **{nome}** — {quantidade}x{estado}",
                    f"> **PV:** {vassoura.vida_maxima}",
                    f"> **Velocidade:** {vassoura.velocidade or '--'}",
                    f"> **Bônus:** {' • '.join(bonus)}",
                ]
                if vassoura.especificacoes:
                    linhas.append("> **Especificações:**")
                    linhas.extend(f"> » {texto}" for texto in vassoura.especificacoes)
                return com_imagem("\n".join(linhas))
        descricao = item.get("descricao", "").strip()
        linha = f"» **{nome}** — {quantidade}x"
        return com_imagem(f"{linha}\n> {descricao}" if descricao else linha)
    if categoria == "Poções":
        return com_imagem(f"» **{nome}** — {quantidade}x")
    if categoria == "Armas":
        partes = [f"» **{nome}**"]
        if item.get("tipo"):
            partes.append(f"*{item['tipo']}*")
        if item.get("dano"):
            partes.append(f"`{item['dano']}`")
        if item.get("critico"):
            critico = item["critico"].strip()
            if not normalizar_rotulo(critico).startswith("crit"):
                critico = f"crit. {critico}"
            partes.append(f"`{critico}`")
        if quantidade > 1:
            partes.append(f"— {quantidade}x")
        return com_imagem(" ".join(partes))
    return com_imagem(f"» **{nome}** — {quantidade}x")


def montar_embed_itens(ficha) -> discord.Embed:
    embed = discord.Embed(title="🎒 Itens")
    itens = itens_exibidos(ficha)
    for categoria in CATEGORIAS_ITENS:
        registros = [item for item in itens if item.get("categoria") == categoria]
        if not registros:
            continue
        partes: list[str] = []
        atual = ""
        for linha in (formatar_item(item) for item in registros):
            candidato = f"{atual}\n{linha}".strip()
            if atual and len(candidato) > 1024:
                partes.append(atual)
                atual = linha
            else:
                atual = candidato
        if atual:
            partes.append(atual)
        for parte in partes:
            embed.add_field(
                name=f"{EMOJIS_ITENS[categoria]} {categoria}",
                value=parte,
                inline=False,
            )
    if not embed.fields:
        embed.description = "--"
    return embed


def somar_item(ficha, novo: dict[str, str]) -> None:
    quantidade = inteiro_positivo(novo.get("quantidade", "1"))
    if quantidade <= 0:
        raise ValueError("A quantidade precisa ser maior que zero.")
    novo = {str(chave): str(valor).strip() for chave, valor in novo.items()}
    novo["quantidade"] = str(quantidade)
    if eh_galeao(novo):
        ficha.galeoes += quantidade
        imagem = novo.get("imagem", "").strip()
        if imagem:
            metadados = metadados_galeoes(ficha)
            if metadados is None:
                ficha.itens.append(
                    {
                        "categoria": "Dinheiro",
                        "nome": "Galeão(ões)",
                        "tipo": "Galeão(ões)",
                        "quantidade": "0",
                        "imagem": imagem,
                    }
                )
            else:
                metadados["imagem"] = imagem
        return
    for item in ficha.itens:
        mesma_categoria = normalizar_rotulo(item.get("categoria", "")) == normalizar_rotulo(novo.get("categoria", ""))
        mesmo_nome = normalizar_rotulo(item.get("nome", "")) == normalizar_rotulo(novo.get("nome", ""))
        mesma_unidade = normalizar_rotulo(item.get("unidade", "")) == normalizar_rotulo(novo.get("unidade", ""))
        mesmo_tipo = normalizar_rotulo(item.get("tipo", "")) == normalizar_rotulo(novo.get("tipo", ""))
        if mesma_categoria and mesmo_nome and mesma_unidade and mesmo_tipo:
            item["quantidade"] = str(inteiro_positivo(item.get("quantidade", "0"), 0) + quantidade)
            for chave, valor in novo.items():
                if chave != "quantidade" and valor:
                    item[chave] = valor
            return
    ficha.itens.append(novo)


def consumir_item(ficha, categoria: str, nome: str, quantidade: int = 1) -> int:
    """Consome uma quantidade do inventário e retorna o saldo restante."""
    quantidade = inteiro_positivo(quantidade, 0)
    if quantidade <= 0:
        raise ValueError("A quantidade consumida precisa ser maior que zero.")
    categoria_alvo = normalizar_rotulo(categoria)
    nome_alvo = normalizar_rotulo(nome)
    for indice, item in enumerate(ficha.itens):
        if (
            normalizar_rotulo(item.get("categoria", "")) != categoria_alvo
            or normalizar_rotulo(item.get("nome", "")) != nome_alvo
        ):
            continue
        atual = inteiro_positivo(item.get("quantidade", "0"), 0)
        if atual < quantidade:
            raise ValueError(f"O inventário não possui {quantidade}x {nome}.")
        restante = atual - quantidade
        if restante:
            item["quantidade"] = str(restante)
        else:
            ficha.itens.pop(indice)
        return restante
    raise ValueError(f"O inventário não possui {nome} na categoria {categoria}.")


def substituir_item(ficha, indice: int, novo: dict[str, str]) -> None:
    if indice < 0 or indice >= len(ficha.itens):
        raise ValueError("O item não está mais disponível no inventário.")
    quantidade = inteiro_positivo(novo.get("quantidade", "1"))
    if quantidade <= 0:
        raise ValueError("A quantidade precisa ser maior que zero.")
    ficha.itens[indice] = {
        str(chave): str(valor).strip() for chave, valor in novo.items()
    }
    ficha.itens[indice]["quantidade"] = str(quantidade)


def remover_item(ficha, indice: int | str) -> dict[str, str]:
    if indice == "galeoes":
        removido = {
            "categoria": "Dinheiro",
            "nome": "Galeão(ões)",
            "quantidade": str(ficha.galeoes),
        }
        ficha.galeoes = 0
        ficha.itens = [item for item in ficha.itens if not eh_galeao(item)]
        return removido
    posicao = int(indice)
    if posicao < 0 or posicao >= len(ficha.itens):
        raise ValueError("O item não está mais disponível no inventário.")
    return ficha.itens.pop(posicao)


def indices_categoria(ficha, categoria: str) -> list[tuple[int | str, dict[str, str]]]:
    resultado: list[tuple[int | str, dict[str, str]]] = []
    if categoria == "Dinheiro" and ficha.galeoes > 0:
        metadados = metadados_galeoes(ficha) or {}
        resultado.append(
            (
                "galeoes",
                {
                    "categoria": "Dinheiro",
                    "nome": "Galeão(ões)",
                    "tipo": "Galeão(ões)",
                    "quantidade": str(ficha.galeoes),
                    **({"imagem": metadados["imagem"]} if metadados.get("imagem") else {}),
                },
            )
        )
    resultado.extend(
        (indice, item)
        for indice, item in enumerate(ficha.itens)
        if item.get("categoria") == categoria and not eh_galeao(item)
    )
    return resultado
