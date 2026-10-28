from __future__ import annotations

from collections import defaultdict
from typing import Any

from utils.biblioteca import normalizar_rotulo


HERANCAS_ENTRE_MUNDOS = {
    normalizar_rotulo("Meio-Sangue"),
    normalizar_rotulo("Nascido-Trouxa"),
    normalizar_rotulo("Sangue Puro"),
}


def possui(nomes: list[str], procurado: str) -> bool:
    alvo = normalizar_rotulo(procurado)
    return any(normalizar_rotulo(nome) == alvo for nome in nomes)


def heranca_desbloqueada(ficha: Any, evolucao: int) -> bool:
    return (
        normalizar_rotulo(ficha.heranca) in HERANCAS_ENTRE_MUNDOS
        and ficha.evolucao_heranca >= evolucao
    )


def bonus_pericias_passivos(ficha: Any) -> dict[str, int]:
    """Bônus sempre ativos; efeitos condicionais não entram no total da ficha."""
    return {}


def bonus_aptidoes_passivos(ficha: Any) -> dict[str, int]:
    bonus: defaultdict[str, int] = defaultdict(int)
    if possui(ficha.origens_magicas, "Sacrifício à Mimir"):
        bonus["Runas Antigas"] += 2
    return dict(bonus)


def aptidao_efetiva(ficha: Any, nome: str) -> int:
    return ficha.aptidoes.get(nome, 0) + bonus_aptidoes_passivos(ficha).get(nome, 0)


def desconto_aptidao(ficha: Any) -> int:
    return 10 if heranca_desbloqueada(ficha, 2) else 0


def desconto_nivel(ficha: Any) -> int:
    return 25 if heranca_desbloqueada(ficha, 4) else 0


def custo_heranca_com_alquimia(ficha: Any, custo: int) -> int:
    if normalizar_rotulo(getattr(ficha, "escolha_experiencia_alquimica", "")) == normalizar_rotulo("Herança Sanguínea"):
        return max(0, custo // 2)
    return custo


def bonus_xp_evento(ficha: Any, categoria: str) -> int:
    return 0


def resumo_automaticos(ficha: Any) -> list[str]:
    linhas: list[str] = []
    pericias = bonus_pericias_passivos(ficha)
    if pericias:
        linhas.append(
            "**Perícias passivas:** "
            + ", ".join(f"{nome} +{valor}" for nome, valor in pericias.items())
        )
    aptidoes = bonus_aptidoes_passivos(ficha)
    if aptidoes:
        linhas.append(
            "**Aptidões passivas:** "
            + ", ".join(f"{nome} +{valor}" for nome, valor in aptidoes.items())
        )
    if desconto_aptidao(ficha):
        linhas.append("**Aprimorar aptidões:** -10 XP em cada compra.")
    if desconto_nivel(ficha):
        linhas.append("**Subir de nível:** -25 XP em todos os próximos níveis.")
    escolha_alquimia = getattr(ficha, "escolha_experiencia_alquimica", "")
    if normalizar_rotulo(escolha_alquimia) == normalizar_rotulo("Herança Sanguínea"):
        linhas.append("**Evoluções da Herança pela Alquimia:** metade do custo em cada evolução.")
    elif normalizar_rotulo(escolha_alquimia) == normalizar_rotulo("Origem Mágica"):
        linhas.append("**Experiência Alquímica:** Origem Mágica adquirida pela metade do custo.")
    return linhas


EFEITOS_CONDICIONAIS = {
    "Maledictus": "+1d6 em uma perícia condizente com o animal da transfiguração.",
    "Meio-Banshee": "Não sofre penalidades ao usar Artes das Trevas.",
    "Parte-Vampiro": "+1d4 em Atletismo, Reflexo e Acrobacia.",
    "Sangue de Gigante": "+4 em força bruta ou nas resistências descritas pela Herança.",
    "Sangue Veela": "+4 em Persuasão ao seduzir um personagem.",
    "Licantropia": "+4 em Percepção exclusivamente para escutar e farejar.",
    "Maestro": "Soma Carisma em feitiços dos anos liberados pela habilidade usada.",
    "Metamorfomagia": "+2 em dados de Força ao assumir um físico apropriado.",
    "Bom de Briga": "+2 em Luta corpo a corpo desarmada e um ataque extra como ação bônus.",
    "Brutamontes": "+4 em força bruta e em resistências descritas pela especialização.",
    "Curandeiro(a) e/ou Medibruxo(a)": "Pode usar Sabedoria em Medicina e adicionar cura por PH gasto.",
    "Detetive": "Pode usar Inteligência em Persuasão durante debate ou interrogatório.",
    "Duelista Exímio": "+2 em um teste de ataque, esquiva ou contra-ataque no duelo.",
    "Estereótipo da Popularidade": "+2 em Carisma para convencer alguém a proteger ou ajudar.",
    "Gênio Alquímico": "+2 na criação de qualquer poção.",
    "Guardião": "+2 ao duelar contra criaturas ou bruxos das trevas enquanto Alma for 75% ou mais.",
    "Mestre Espadachim": "+2 para defender ou esquivar golpes ao antecipá-los.",
    "Poeta // Artista": "+4 para tranquilizar e acolher alguém.",
    "Prodígio do Quadribol": "+2 nos testes correspondentes à posição jogada.",
    "Sedutor": "+4 em Persuasão ao seduzir um personagem.",
    "Soldado": "+2 em Vontade ou Iniciativa e uso de Força depois de um desafio.",
}


def resumo_condicionais(ficha: Any) -> list[str]:
    nomes = [ficha.heranca, *ficha.origens_magicas, *ficha.especializacoes]
    return [
        f"**{nome}**: {EFEITOS_CONDICIONAIS[nome]}"
        for nome in EFEITOS_CONDICIONAIS
        if possui(nomes, nome)
    ]
