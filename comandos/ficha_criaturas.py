from __future__ import annotations

import asyncio
import math
import re
import traceback
from pathlib import Path

import discord

from utils.biblioteca import normalizar_rotulo
from utils.fichas import ATRIBUTOS_POR_PERICIA, PERICIAS, SIGLAS_ATRIBUTOS, formatar_bonus, modificador, paginas_pericias
from utils.fichas_criaturas import (
    ATRIBUTOS_CRIATURA,
    BASES_TAMANHO,
    CUSTO_TOTAL_RANK,
    PASTA_CRIATURAS,
    PASTA_FICHAS_CRIATURAS,
    PERICULOSIDADES,
    PONTOS_ATRIBUTO,
    RANKS_PERICIA_CRIATURA,
    XP_PERICIAS,
    FichaCriatura,
    ReferenciaCriatura,
    avancar_passo_dano,
    caminho_nova_ficha_criatura,
    dano_arma_natural,
    efeito_condicao,
    efeito_dano,
    listar_criaturas_lore,
    listar_fichas_criaturas,
    nivel_periculosidade,
    salvar_ficha_criatura,
    somar_atributo_ao_dano,
    tamanho_em_metros,
    validar_e_normalizar_tamanho,
)
from utils.publicacao_fichas import (
    ErroPublicacaoFicha,
    cabecalho_criatura,
    destino_criatura,
    publicar_ou_atualizar_ficha,
)


TEMPO_FLUXO = 30 * 60
LOCKS_CRIATURA: dict[Path, asyncio.Lock] = {}
ATRIBUTO_MAXIMO_CRIATURA = 30
GRUPOS_ALFABETICOS_CRIATURAS = (
    "AB", "CD", "EF", "GH", "IJ", "KL", "MN", "OP", "QR", "ST", "UV", "WXYZ",
)
CLASSIFICACOES = ("Fera", "Ser", "Ser semi-humano", "Espírito")
DESCRICOES_CLASSIFICACAO = {
    "Fera": "Criatura de natureza predominantemente animal.",
    "Ser": "Criatura inteligente reconhecida como um ser.",
    "Ser semi-humano": "Criatura humanoide com características não humanas.",
    "Espírito": "Entidade espiritual ou incorpórea.",
}
DESCRICOES_FAIXA_TAMANHO = {
    "Menos de 50 cm": ("Informe uma medida inferior a 50 cm.", "Ex.: 20 cm"),
    "Menos de 1 m": ("Informe uma medida entre 50 cm e menos de 1 m.", "Ex.: 80 cm"),
    "De 1 m a 2 m": ("Informe uma medida entre 1 m e 2 m.", "Ex.: 1,70 m"),
    "De 2 m a 3 m": ("Informe uma medida entre 2 m e 3 m.", "Ex.: 2,50 m"),
    "De 3 m a 4 m": ("Informe uma medida entre 3 m e 4 m.", "Ex.: 3,60 m"),
    "De 4 m a 5 m": ("Informe uma medida entre 4 m e 5 m.", "Ex.: 4,30 m"),
    "De 5 m a 10 m": ("Informe uma medida entre 5 m e 10 m.", "Ex.: 7 m"),
    "Acima de 10 m": ("Informe uma medida superior a 10 m.", "Ex.: 15 m"),
}
ARMAS_NATURAIS = {
    "Punhos": {"tipo de dano": "Concussivo", "dano-base": "1d4+Força", "crítico": "x2"},
    "Presas": {"tipo de dano": "Perfurante", "dano-base": "1d6+Força", "crítico": "x2"},
    "Bico": {"tipo de dano": "Perfurante", "dano-base": "1d6+Força", "crítico": "x2"},
    "Garras": {"tipo de dano": "Perfurante/Cortante", "dano-base": "1d6+Força", "crítico": "x2"},
    "Cauda": {"tipo de dano": "Concussivo", "dano-base": "1d10+Força", "crítico": "x2"},
    "Chifre": {"tipo de dano": "Perfurante", "dano-base": "1d10+Força", "crítico": "x2"},
    "Ferrão": {"tipo de dano": "Perfurante", "dano-base": "1d12+Força", "crítico": "x3"},
}
ARMAS_SIMPLES = {
    "Adaga": {"tipo de dano": "Perfurante", "dano": "1d4+Força", "crítico": "19"},
    "Machadinha": {"tipo de dano": "Cortante", "dano": "1d6+Destreza", "crítico": "x3", "alcance": "3 m"},
    "Clava": {"tipo de dano": "Concussivo", "dano": "1d6+Força", "crítico": "x2"},
    "Lança": {"tipo de dano": "Perfurante", "dano": "1d6+Força", "crítico": "x2", "alcance": "6 m"},
    "Martelo": {"tipo de dano": "Concussivo", "dano": "1d6+Força", "crítico": "x2", "alcance": "6 m"},
}
ARMAS_MARCIAIS = {
    "Espada Curta": {"tipo de dano": "Perfurante", "dano": "1d4+Força", "crítico": "19"},
    "Espada Longa": {"tipo de dano": "Cortante", "dano": "1d8+Destreza", "crítico": "19"},
    "Espada Grande": {"tipo de dano": "Cortante", "dano": "2d6+Destreza", "crítico": "19"},
    "Machado de Batalha": {"tipo de dano": "Cortante", "dano": "1d8+Destreza", "crítico": "x3"},
    "Martelo de Guerra": {"tipo de dano": "Concussivo", "dano": "1d8+Força", "crítico": "x3"},
    "Maça": {"tipo de dano": "Concussivo", "dano": "1d8+Força", "crítico": "x2"},
    "Foice": {"tipo de dano": "Cortante", "dano": "2d4+Destreza", "crítico": "x4"},
    "Arco Curto": {"tipo de dano": "Perfurante", "dano": "1d6+Destreza", "crítico": "x3", "alcance": "12 m"},
    "Arco Longo": {"tipo de dano": "Perfurante", "dano": "1d8+Destreza", "crítico": "x3", "alcance": "24 m"},
    "Besta Leve": {"tipo de dano": "Perfurante", "dano": "1d8+Destreza", "crítico": "19", "alcance": "18 m"},
    "Besta Pesada": {"tipo de dano": "Perfurante", "dano": "2d6+Destreza", "crítico": "19", "alcance": "27 m"},
}
ARMAS_EXOTICAS = {
    "Neko-te": {"tipo de dano": "Cortante", "dano": "1d4+Força", "crítico": "19"},
    "Wakisashi": {"tipo de dano": "Cortante", "dano": "1d8+Destreza", "crítico": "19"},
    "Chicote": {"tipo de dano": "Cortante", "dano": "1d6+Destreza", "crítico": "x2"},
    "Katana": {"tipo de dano": "Cortante", "dano": "1d10+Destreza", "crítico": "19"},
    "Espada de duas Lâminas": {"tipo de dano": "Cortante", "dano": "1d8+Destreza e 1d8+Destreza", "crítico": "19"},
}
ARMAS_DE_FOGO = {
    "Pistola": {"tipo de dano": "Perfurante", "dano": "1d12", "crítico": "18", "alcance": "12 m"},
    "Revólver": {"tipo de dano": "Perfurante", "dano": "2d6", "crítico": "19 x3", "alcance": "18 m"},
    "Fuzil de caça": {"tipo de dano": "Perfurante", "dano": "2d8", "crítico": "19 x3", "alcance": "30 m"},
    "Submetralhadora": {"tipo de dano": "Perfurante", "dano": "2d6", "crítico": "19 x3", "alcance curto": "15 m", "rajada": "30 m"},
    "Fuzil de assalto": {"tipo de dano": "Perfurante", "dano": "3d6", "crítico": "19 x3", "alcance curto": "24 m", "rajada": "60 m"},
    "Fuzil de precisão": {"tipo de dano": "Perfurante", "dano": "3d6", "crítico": "19 x3", "alcance": "120 m"},
    "Metralhadora": {"tipo de dano": "Perfurante", "dano": "3d8", "crítico": "19 x3", "alcance curto": "30 m", "rajada": "60 m"},
    "Espingarda": {"tipo de dano": "Perfurante", "dano": "4d6", "crítico": "x3", "alcance efetivo": "9 m", "dispersão": "18 m"},
    "Granada": {"tipo de dano": "Explosivo", "dano": "4d6", "crítico": "x3", "raio de explosão": "3 m", "alcance": "12 m"},
}
ARMAS_POR_TIPO = {
    "Armas Naturais": ARMAS_NATURAIS,
    "Armas Simples": ARMAS_SIMPLES,
    "Armas Marciais": ARMAS_MARCIAIS,
    "Armas Exóticas": ARMAS_EXOTICAS,
    "Armas de Fogo": ARMAS_DE_FOGO,
}
DESCRICOES_TIPOS_ARMAS = {
    "Armas Naturais": "O dano aumenta conforme a periculosidade e o tamanho.",
    "Armas Simples": "Armas comuns com dano fixo conforme a tabela.",
    "Armas Marciais": "Armas de combate com dano fixo conforme a tabela.",
    "Armas Exóticas": "Armas incomuns com dano fixo conforme a tabela.",
    "Armas de Fogo": "Armas de alcance com dano fixo conforme a tabela.",
}
DESCRICOES_ATAQUES = {
    "Emboscada": "Realizado a partir de furtividade ou surpresa.",
    "Bote": "Avanço curto e repentino.",
    "Investida": "Percorre uma distância razoável e ataca usando impulso.",
    "Derrubar": "Manobra voltada a deixar o alvo caído.",
    "Arremesso": "Lança um alvo, objeto ou arma.",
    "Pisotear": "Ataque de criaturas grandes contra alvos menores e caídos.",
    "Varredura": "Golpe utilizando um de seus membros em um arco amplo.",
    "Coice": "Golpe poderoso utilizando patas, cascos ou membros traseiros.",
    "Agarrão": "Prende um alvo, restringindo seus movimentos.",
    "Constrição": "Comprime um alvo agarrado.",
    "Ataques Múltiplos": "Permite executar mais de um golpe com uma de suas armas.",
    "Ataque Venenoso": "Utiliza veneno junto de um ataque.",
    "Ataque Ácido": "Utiliza uma substância ácida junto de um ataque.",
    "Personalizado": "Crie um ataque que ainda não está entre os presets.",
}
ATAQUES = tuple(DESCRICOES_ATAQUES)
CATEGORIAS_EFEITO = ("Cortante", "Perfurante", "Concussivo", "Fogo", "Frio", "Eletricidade", "Ácido", "Veneno", "Sônico", "Psíquico", "Magia", "Condições mentais", "Transfiguração", "Personalizada")
DESCRICOES_CATEGORIAS_EFEITO = {
    "Cortante": "Golpes que cortam, rasgam ou dilaceram.",
    "Perfurante": "Golpes que perfuram, atravessam ou penetram.",
    "Concussivo": "Impactos, colisões e golpes de esmagamento.",
    "Fogo": "Chamas, calor intenso e efeitos incendiários.",
    "Frio": "Gelo, congelamento e temperaturas extremas.",
    "Eletricidade": "Choques, raios e descargas elétricas.",
    "Ácido": "Substâncias corrosivas e efeitos ácidos.",
    "Veneno": "Toxinas, peçonhas e substâncias venenosas.",
    "Sônico": "Ondas sonoras, estrondos e vibrações.",
    "Psíquico": "Danos e efeitos que atingem diretamente a mente.",
    "Magia": "Feitiços e outros efeitos de natureza mágica.",
    "Condições mentais": "Medo, controle, confusão e efeitos emocionais.",
    "Transfiguração": "Alterações mágicas de forma ou matéria.",
    "Personalizada": "Registre uma categoria não contemplada pelos presets.",
}
TIPOS_FRAQUEZA = {
    "Aumento de Dano Sofrido": "Aumenta o dano recebido desta categoria conforme a periculosidade.",
    "Desvantagem em testes de resistência": "Aplica desvantagem nos testes para resistir aos efeitos desta categoria.",
}
TIPOS_RESISTENCIA = {
    "Redução de Dano Sofrido": "Reduz o dano recebido desta categoria conforme a periculosidade.",
    "Vantagem em testes de resistência": "Concede vantagem nos testes para resistir aos efeitos desta categoria.",
    "Imunidade a efeito": "Ignora completamente o efeito desta categoria, sem realizar teste.",
}
ACOES = ("Completa", "Padrão", "Movimento", "Livre", "Bônus", "Reação")
ATIVACOES_HABILIDADE = {
    "Passiva": "Permanece ativa sem precisar ser acionada pela criatura.",
    "Ativa": "A criatura decide ativá-la durante o próprio turno.",
    "Reação": "É ativada em resposta a um gatilho ou acontecimento.",
}
CUSTOS_PH_HABILIDADE = {
    str(custo): "Não consome PH." if custo == 0 else f"Consome {custo} PH conforme a mecânica escolhida."
    for custo in range(0, 11, 2)
}
ACOES_HABILIDADE = ACOES
DESCRICOES_ACOES_HABILIDADE = {
    "Completa": "Consome as ações padrão e de movimento do turno.",
    "Padrão": "Consome a ação principal do turno.",
    "Movimento": "Consome a ação de deslocamento do turno.",
    "Livre": "Pode ser realizada sem consumir as ações principais do turno.",
    "Bônus": "Usa uma ativação breve adicional no turno.",
    "Reação": "Ocorre em resposta a um gatilho fora ou dentro do turno.",
}
ROLAGENS_ATAQUE = {
    "Força": "Atributo • Usa o modificador de Força.",
    "Destreza": "Atributo • Usa o modificador de Destreza.",
    "Atletismo": "Perícia de Força • Usa o bônus total de Atletismo.",
    "Luta": "Perícia de Força ou Destreza • Usa o melhor modificador.",
    "Pontaria": "Perícia de Destreza • Usa o bônus total de Pontaria.",
    "Esgrima": "Perícia de Destreza • Usa o bônus total de Esgrima.",
    "Fortitude": "Perícia de Constituição • Usa o bônus total de Fortitude.",
    "Furtividade": "Perícia de Destreza • Usa o bônus total de Furtividade.",
}
ALCANCES = ("Pessoal", "Toque", "Adjacente", "Campo de Visão", "Especial")
DESCRICOES_ALCANCES = {
    "Pessoal": "Afeta somente a própria criatura.",
    "Toque": "Exige contato direto com o alvo.",
    "Adjacente": "Alcança um alvo imediatamente ao lado.",
    "Campo de Visão": "Alcança um alvo que a criatura consiga enxergar.",
    "Especial": "O alcance é definido pela descrição da habilidade.",
}
ALVOS = ("Pessoal", "Individual", "Área", "Campo de Visão", "Especial")
DESCRICOES_ALVOS = {
    "Pessoal": "A habilidade afeta somente quem a utiliza.",
    "Individual": "Afeta uma única criatura; use a habilidade novamente para atingir outro alvo.",
    "Área": "Afeta qualquer criatura dentro do raio calculado pelo tamanho e pela periculosidade.",
    "Campo de Visão": "Afeta todas as criaturas permitidas que estejam no campo de visão.",
    "Especial": "Quem é afetado fica definido pela descrição da habilidade.",
}
DURACOES = ("Instantâneo", "Turno", "Rodada", "Sustentado")
DADOS_EFEITO = ("d4", "d6", "d8", "d10", "d12")
CATEGORIAS_ROLAGEM_ACERTO = ("Magia", "Perícia")
CATEGORIAS_MODIFICADOR_EFEITO = ("Nulo", "Modificador", "Perícia", "Personalizado")
TIPOS_DANO_HABILIDADE = (
    "Nenhum",
    "Cortante",
    "Perfurante",
    "Concussivo",
    "Explosivo",
    "Fogo",
    "Frio",
    "Eletricidade",
    "Ácido",
    "Veneno",
    "Sônico",
    "Psíquico",
    "Magia",
    "Sufocante",
)
DESCRICOES_TIPOS_DANO_HABILIDADE = {
    "Nenhum": "A habilidade não causa dano direto.",
    "Cortante": "Corta, rasga ou dilacera o alvo.",
    "Perfurante": "Perfura, atravessa ou penetra o alvo.",
    "Concussivo": "Causa impacto, colisão ou esmagamento.",
    "Explosivo": "Causa dano por explosão e onda de choque.",
    "Fogo": "Causa queimaduras por calor ou chamas.",
    "Frio": "Causa dano por gelo ou temperatura extrema.",
    "Eletricidade": "Causa dano por descarga elétrica.",
    "Ácido": "Corrói o alvo com substância ácida.",
    "Veneno": "Causa dano por toxina ou envenenamento.",
    "Sônico": "Causa dano por som, vibração ou pressão.",
    "Psíquico": "Agride diretamente a mente do alvo.",
    "Magia": "Causa dano de energia mágica sem outro tipo específico.",
    "Sufocante": "Causa dano por asfixia ou falta de ar.",
}
TIPOS_EFEITO_HABILIDADE = {
    "Ofensivo": "Causa dano ao alvo.",
    "Defensivo": "Reduz dano, concede resistência ou proteção.",
    "Suporte": "Cura, fortalece ou auxilia o usuário e seus aliados.",
    "Debilitante": "Enfraquece o alvo, reduz atributos ou aplica penalidades.",
    "Controle Mental": "Altera ou restringe as ações do alvo.",
    "Controle de Terreno": "Cria obstáculos, áreas perigosas ou modifica o ambiente.",
    "Manipulação": "Controla recursos, energia, gravidade, tempo, espaço, mente, sombras ou luz.",
    "Invocação": "Cria ou convoca criaturas, objetos e estruturas.",
    "Transformação": "Altera forma, tamanho ou natureza do usuário, objeto ou alvo.",
    "Detecção": "Revela informações, presenças, magia, rastros ou fraquezas.",
    "Utilitário": "Produz efeitos sem foco direto em combate, como voo ou camuflagem.",
}
NECESSITA_ROLAGEM_EFEITO = ("Sim", "Não")
MODOS_CUSTO_HABILIDADE = ("Ativação", "Turno/Rodada Sustentada", "Acúmulo", "Sem Custo")
RESOLUCOES = ("Teste Oposto", "Efeito Mágico Direto", "Automática", "Pessoal")
RESISTENCIAS = ("Reflexo", "Fortitude", "Vontade", "Nenhuma")
RECARGAS = ("Padrão da periculosidade", "Sem recarga", "Uma vez por combate", "Uma vez por cena", "Uma vez por dia", "Personalizada")


def painel(titulo: str, descricao: str) -> discord.Embed:
    return discord.Embed(title=titulo, description=descricao)


def opcoes(valores, descricoes: dict[str, str] | None = None):
    return [discord.SelectOption(label=v[:100], value=v, description=(descricoes or {}).get(v, "")[:100] or None) for v in valores]


def paginas_criaturas_alfabeticas(itens) -> list[tuple[str, list]]:
    itens = list(itens)
    paginas: list[tuple[str, list]] = []
    for grupo in GRUPOS_ALFABETICOS_CRIATURAS:
        criaturas = [
            item for item in itens
            if (normalizar_rotulo(item.nome)[:1].upper() or "#") in grupo
        ]
        lotes = [criaturas[indice:indice + 25] for indice in range(0, len(criaturas), 25)] or [[]]
        for indice, lote in enumerate(lotes):
            rotulo = grupo if len(lotes) == 1 else f"{grupo} — {indice + 1}/{len(lotes)}"
            paginas.append((rotulo, lote))
    return paginas


def duracao_por_magia(ficha: FichaCriatura, unidade: str) -> str:
    if unidade in {"Instantâneo", "Sustentado"}:
        return unidade
    quantidade = max(1, 1 + modificador(ficha.atributos["Magia"]))
    nome = "turno" if unidade == "Turno" else "rodada"
    return f"{quantidade} {nome}(s)"


def recarga_padrao(perigo: str) -> str:
    return f"{6 - nivel_periculosidade(perigo)} rodada(s)"


def cd_magica(ficha: FichaCriatura) -> int:
    return 5 + 3 * (ficha.nivel - 1) + modificador(ficha.atributos["Magia"])


def cd_atributo(ficha: FichaCriatura, atributo: str) -> int:
    return 5 + 3 * (ficha.nivel - 1) + modificador(ficha.atributos[atributo])


def multiplicar_dados(dano: str, multiplicador: int) -> str:
    correspondencia = re.fullmatch(r"(\d+)d(\d+)(.*)", dano, re.IGNORECASE)
    if correspondencia is None:
        raise ValueError("O dano da arma não pode ser multiplicado automaticamente.")
    quantidade = int(correspondencia.group(1)) * multiplicador
    sufixo = correspondencia.group(3).strip()
    atributo = re.fullmatch(r"\+\s*(FOR(?:ÇA)?|DES(?:TREZA)?)", sufixo, re.IGNORECASE)
    if atributo:
        nome = "Força" if normalizar_rotulo(atributo.group(1)) in {"for", "forca"} else "Destreza"
        sufixo = f"+{nome}×{multiplicador}"
    return f"{quantidade}d{correspondencia.group(2)}{sufixo}"


def dado_pisotear(tamanho: str) -> str:
    metros = tamanho_em_metros(tamanho)
    passos = 0 if metros <= 1 else math.ceil((metros - 1) / 2)
    return avancar_passo_dano("1d4", passos)


def multiplicar_quantidade_dados(dano: str, quantidade: int) -> str:
    correspondencia = re.fullmatch(r"(\d+)d(\d+)", dano, re.IGNORECASE)
    if correspondencia is None:
        raise ValueError("O dado de Pisotear não pôde ser calculado.")
    return f"{int(correspondencia.group(1)) * quantidade}d{correspondencia.group(2)}"


def raio_habilidade_metros(ficha: FichaCriatura) -> float:
    bonus_magia = max(0, modificador(ficha.atributos["Magia"]))
    return (tamanho_em_metros(ficha.tamanho) + bonus_magia) * ficha.nivel


def formatar_medida_metros(metros: float) -> str:
    return f"{metros:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def alcance_calculado(ficha: FichaCriatura) -> str:
    return f"Até {formatar_medida_metros(raio_habilidade_metros(ficha))} m"


def alcances_habilidade(ficha: FichaCriatura) -> tuple[str, ...]:
    return (*ALCANCES[:3], alcance_calculado(ficha), *ALCANCES[3:])


def area_padrao(ficha: FichaCriatura) -> str:
    medida = formatar_medida_metros(raio_habilidade_metros(ficha))
    return f"Qualquer criatura numa área de {medida} m de raio ([tamanho exato + modificador de Magia] × periculosidade)."


def bonus_escolha_criatura(ficha: FichaCriatura, escolha: str) -> int:
    if escolha in ATRIBUTOS_CRIATURA:
        return modificador(ficha.atributos[escolha])
    if escolha in PERICIAS:
        atributo = max(
            modificador(ficha.atributos.get(nome, 10))
            for nome in ATRIBUTOS_POR_PERICIA[escolha]
        )
        return ficha.pericias.get(escolha, 0) + atributo
    raise ValueError("A rolagem ou o modificador escolhido é inválido.")


def escolha_com_bonus(ficha: FichaCriatura, escolha: str) -> str:
    return f"{escolha} {formatar_bonus(bonus_escolha_criatura(ficha, escolha))}"


def escolha_registrada_base(valor: str) -> str:
    if valor.startswith("Personalizado "):
        return valor
    escolhas = (*ATRIBUTOS_CRIATURA, *PERICIAS)
    return next((nome for nome in escolhas if valor == nome or valor.startswith(f"{nome} ")), valor)


def duracao_registrada_base(valor: str) -> str:
    if valor in {"Instantâneo", "Sustentado"}:
        return valor
    if "turno" in valor.casefold():
        return "Turno"
    if "rodada" in valor.casefold():
        return "Rodada"
    return ""


def interpretar_modificador_personalizado(valor: str) -> int:
    conteudo = str(valor).strip().replace(" ", "")
    if not re.fullmatch(r"[+-]?\d+", conteudo):
        raise ValueError("Informe um número inteiro, como +2, 5 ou -3.")
    numero = int(conteudo)
    if abs(numero) > 9999:
        raise ValueError("O valor personalizado deve ficar entre -9999 e +9999.")
    return numero


def atualizar_efeito_calculado(item: dict[str, str], ficha: FichaCriatura, modificador_escolhido: str) -> None:
    quantidade = item.get("número de dados", "1")
    dado = item.get("dado de efeito", "d4")
    if modificador_escolhido == "Nulo":
        item["modificador de efeito"] = "Nulo"
        item["efeito calculado"] = f"{quantidade}{dado}"
        return
    if modificador_escolhido.startswith("Personalizado "):
        bonus = interpretar_modificador_personalizado(
            modificador_escolhido.removeprefix("Personalizado ")
        )
        formatado = formatar_bonus(bonus)
        item["modificador de efeito"] = f"Personalizado {formatado}"
        item["efeito calculado"] = f"{quantidade}{dado}{formatado} (Personalizado)"
        return
    bonus = bonus_escolha_criatura(ficha, modificador_escolhido)
    item["modificador de efeito"] = escolha_com_bonus(ficha, modificador_escolhido)
    item["efeito calculado"] = f"{quantidade}{dado}{formatar_bonus(bonus)} ({modificador_escolhido})"


def configurar_tipo_efeito(
    item: dict[str, str],
    tipo: str,
    necessita_rolagem: str,
    tipo_dano: str = "Nenhum",
) -> None:
    item["tipo de efeito"] = tipo
    item["tipo de dano"] = tipo_dano
    item["necessita de rolagem"] = necessita_rolagem
    if necessita_rolagem == "Não":
        for campo in ("dado de efeito", "número de dados", "modificador de efeito", "efeito calculado"):
            item.pop(campo, None)


def resumo_efeito_habilidade(item: dict[str, str]) -> str:
    linhas = [
        f"Tipo de efeito: {item.get('tipo de efeito', '--')}.",
        f"Tipo de dano: {item.get('tipo de dano', 'Nenhum')}.",
        f"Ativação: {item.get('tipo de ativação', '--')}; ação: {item.get('tipo de ação', '--')}.",
        f"Alcance: {item.get('alcance', '--')}; alvo: {item.get('alvo', '--')}.",
        f"Duração: {item.get('duração', '--')}; recarga: {item.get('recarga', '--')}.",
        f"Custo: {item.get('mecânica de custo', '--')}",
        f"Acerto: {item.get('rolagem de acerto', '--')}; resistência: {item.get('rolagem de resistência', '--')}; reação: {item.get('rolagem de reação', '--')}.",
    ]
    if item.get("necessita de rolagem") == "Sim" and item.get("efeito calculado"):
        linhas.append(f"Rolagem de efeito: {item['efeito calculado']}.")
    else:
        linhas.append("Não necessita de rolagem de efeito.")
    return "\n".join(linhas)


def aplicar_modo_custo(item: dict[str, str], ficha: FichaCriatura, modo: str) -> None:
    custo = "0" if modo == "Sem Custo" else item.get("custo de PH", item.pop("custo de Mana", "0"))
    item["custo de PH"] = custo
    item["modo de custo"] = modo
    if modo == "Ativação":
        item["mecânica de custo"] = f"Custa {custo} PH por ativação."
    elif modo == "Turno/Rodada Sustentada":
        item["mecânica de custo"] = f"Custa {custo} PH por turno ou rodada sustentada e termina se perder a concentração."
    elif modo == "Acúmulo":
        item["mecânica de custo"] = f"A cada {custo} PH, recebe um acúmulo do mesmo efeito. Limite de {1+ficha.nivel} acúmulos; todos começam e terminam juntos."
    else:
        item["mecânica de custo"] = "Sem custo de PH."


class ViewCriatura(discord.ui.View):
    def __init__(self, usuario_id: int):
        super().__init__(timeout=TEMPO_FLUXO)
        self.usuario_id = usuario_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message("Somente quem abriu esta ficha pode usar os controles.", ephemeral=True)
        return False

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ) -> None:
        traceback.print_exception(type(error), error, error.__traceback__)
        mensagem = "Não consegui avançar esta etapa. Tente selecionar a opção novamente."
        if interaction.response.is_done():
            await interaction.followup.send(mensagem, ephemeral=True)
        else:
            await interaction.response.send_message(mensagem, ephemeral=True)


def formatar_registro(item: dict[str, str]) -> str:
    titulo = item.get("nome") or item.get("categoria") or "Item"
    eh_habilidade = "tipo de ativação" in item
    rotulos = {
        "alcance/alvo": "Alcance/Alvo",
        "tipo de ativação": "Tipo de Ativação",
        "tipo de ação": "Tipo de Ação",
        "custo de ph": "Custo de PH",
        "custo de mana": "Custo de PH",
        "modo de custo": "Modo de Custo",
        "rolagem de acerto": "Rolagem de Acerto",
        "rolagem de resistência": "Rolagem de Resistência",
        "rolagem de reação": "Rolagem de Reação",
        "tipo de dano": "Tipo de Dano",
        "cd mágica": "CD Mágica",
        "cd do efeito": "CD do Efeito",
        "dado de efeito": "Dado de Efeito",
        "número de dados": "Número de Dados",
        "modificador de efeito": "Modificador de Efeito",
        "efeito calculado": "Efeito Calculado",
        "rolagem de efeito": "Rolagem de Efeito",
    }
    ocultos = {"nome", "categoria"}
    if eh_habilidade:
        ocultos.update({"descrição", "efeito", "custo de PH", "custo de Mana", "modo de custo", "dado de efeito", "número de dados", "modificador de efeito", "efeito calculado"})
    detalhes = [f"**{rotulos.get(k.casefold(), k.replace('_', ' ').capitalize())}:** {v}" for k, v in item.items() if k not in ocultos and v]
    if eh_habilidade and item.get("efeito calculado"):
        detalhes.append(f"**Rolagem de Efeito:** {item['efeito calculado']}")
    if item.get("categoria") and item.get("nome"):
        detalhes.insert(0, f"**Categoria:** {item['categoria']}")
    cabecalho = f"**{titulo}**"
    if eh_habilidade and item.get("descrição"):
        cabecalho += f"\n*{item['descrição']}*"
    if eh_habilidade and item.get("efeito"):
        efeito = str(item["efeito"]).replace("`", "'").replace("\r", " ").replace("\n", " ")
        cabecalho += f"\n`{efeito}`"
    return cabecalho + ("\n" + "\n".join(detalhes) if detalhes else "")


def montar_embeds_habilidades(itens: list[dict[str, str]]) -> list[discord.Embed]:
    if not itens:
        return [discord.Embed(title="✨ Habilidades", description="--")]
    rotulos = {
        "tipo de ativação": "Tipo de Ativação",
        "tipo de ação": "Tipo de Ação",
        "mecânica de custo": "Mecânica de Custo",
        "rolagem de acerto": "Rolagem de Acerto",
        "rolagem de resistência": "Rolagem de Resistência",
        "rolagem de reação": "Rolagem de Reação",
        "cd mágica": "CD Mágica",
        "tipo de efeito": "Tipo de Efeito",
        "tipo de dano": "Tipo de Dano",
        "necessita de rolagem": "Necessita de Rolagem",
    }
    ocultos = {"nome", "descrição", "efeito", "custo de PH", "custo de Mana", "modo de custo", "dado de efeito", "número de dados", "modificador de efeito", "efeito calculado"}
    embeds=[];embed=discord.Embed(title="✨ Habilidades")
    for item in itens:
        descricao = f"*{item.get('descrição','--')}*"
        if item.get("efeito"):
            efeito = str(item["efeito"]).replace("`", "'").replace("\r", " ").replace("\n", " ")
            descricao += f"\n`{efeito}`"
        campos=[(item.get("nome","Habilidade"),descricao,False)]
        campos.extend((rotulos.get(chave.casefold(),chave.replace("_"," ").title()),str(valor),True) for chave,valor in item.items() if chave not in ocultos and valor)
        if item.get("efeito calculado"):
            campos.append(("Rolagem de Efeito",str(item["efeito calculado"]),True))
        if len(embed.fields)+len(campos)>25 and embed.fields:
            embeds.append(embed);embed=discord.Embed(title="✨ Habilidades")
        for nome,valor,inline in campos:
            embed.add_field(name=nome,value=valor,inline=inline)
    embeds.append(embed)
    return embeds


def montar_embeds_criatura(ficha: FichaCriatura) -> list[discord.Embed]:
    identidade = discord.Embed(description=f"## 🐾 {ficha.nome}")
    identidade.add_field(name="Classificação", value=ficha.classificacao, inline=True)
    identidade.add_field(name="Periculosidade", value=ficha.periculosidade, inline=True)
    identidade.add_field(name="Tamanho", value=ficha.tamanho, inline=True)
    identidade.add_field(name="Origem da ficha", value=ficha.origem_biblioteca, inline=False)

    estatisticas = discord.Embed(title="📊 Estatísticas")
    estatisticas.add_field(name="Pontos de Vida", value=str(ficha.pv), inline=True)
    estatisticas.add_field(name="Pontos de Habilidade", value=str(ficha.ph), inline=True)

    atributos = discord.Embed(title="📌 Atributos", description="\n".join(
        f"> *{nome}: {ficha.atributos[nome]} {formatar_bonus(modificador(ficha.atributos[nome]))}*"
        for nome in ATRIBUTOS_CRIATURA
    ))
    pericias_treinadas = [(nome, rank) for nome, rank in ficha.pericias.items() if rank]
    pericias = discord.Embed(title="📌 Perícias", description="\n".join(
        f"> ***{nome}: {formatar_bonus(rank + max(modificador(ficha.atributos.get(a, 10)) for a in ATRIBUTOS_POR_PERICIA[nome]))} ({RANKS_PERICIA_CRIATURA[rank]})***"
        for nome, rank in pericias_treinadas
    ) or "--")

    secoes = [
        ("🗡️ Armas", ficha.armas_naturais),
        ("⚔️ Ataques", ficha.ataques),
        ("💔 Fraquezas", ficha.fraquezas),
        ("🛡️ Resistências", ficha.resistencias),
    ]
    embeds = [identidade, estatisticas, atributos, pericias]
    for titulo, itens in secoes[:2]:
        embeds.append(discord.Embed(title=titulo, description="\n\n".join(formatar_registro(i) for i in itens) or "--"))
    embeds.extend(montar_embeds_habilidades(ficha.habilidades))
    for titulo, itens in secoes[2:]:
        embeds.append(discord.Embed(title=titulo, description="\n\n".join(formatar_registro(i) for i in itens) or "--"))
    return embeds


async def sincronizar_publicacao_criatura(i: discord.Interaction, ficha: FichaCriatura, caminho: Path) -> None:
    try:
        mensagem = await publicar_ou_atualizar_ficha(
            i.client,
            destino_criatura(),
            montar_embeds_criatura(ficha),
            ficha.mensagem_discord_id,
            cabecalho_criatura(ficha.nome, ficha.periculosidade),
        )
        if ficha.mensagem_discord_id != mensagem.id:
            lock=LOCKS_CRIATURA.setdefault(caminho.resolve(),asyncio.Lock())
            async with lock:
                atual=FichaCriatura.carregar(caminho)
                atual.mensagem_discord_id=mensagem.id
                salvar_ficha_criatura(atual,caminho)
            ficha.mensagem_discord_id=mensagem.id
            if getattr(ficha,"_caminho_edicao",None) is not None:
                ficha._conteudo_original_edicao=caminho.read_text(encoding="utf-8-sig")
    except (ErroPublicacaoFicha,OSError,ValueError) as erro:
        await i.followup.send(f"A ficha foi salva, mas não consegui sincronizar sua mensagem na thread: {erro}",ephemeral=True)


def validar_ficha(ficha: FichaCriatura) -> None:
    embeds = montar_embeds_criatura(ficha)
    if len(embeds) > 10 or sum(len(embed) for embed in embeds) > 6000:
        raise ValueError("A ficha ultrapassa o limite de exibição do Discord. Encurte as descrições.")


class FonteCriaturaView(ViewCriatura):
    def __init__(self, usuario_id: int):
        super().__init__(usuario_id)

    @discord.ui.button(label="Escolher da biblioteca", style=discord.ButtonStyle.primary, emoji="📚")
    async def biblioteca(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.edit_message(embed=painel("📚 Biblioteca de Criaturas", "Escolha a espécie que servirá de base."), view=EscolherLoreView(self.usuario_id, 0))

    @discord.ui.button(label="Criar uma nova", style=discord.ButtonStyle.secondary, emoji="➕")
    async def nova(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.edit_message(
            embed=painel(
                "⚠️ Periculosidade",
                "Escolha primeiro o nível de periculosidade da nova criatura.",
            ),
            view=PericulosidadeNovaCriaturaView(self.usuario_id),
        )


class ConsultaPericulosidadeCriaturaView(ViewCriatura):
    def __init__(self, usuario_id: int):
        super().__init__(usuario_id)
        referencias = listar_fichas_criaturas()
        contagens = {
            perigo: sum(item.periculosidade == perigo for item in referencias)
            for perigo in PERICULOSIDADES
        }
        seletor = discord.ui.Select(
            placeholder="Escolha a periculosidade",
            options=[
                discord.SelectOption(
                    label=perigo,
                    value=perigo,
                    description=(
                        f"{contagens[perigo]} ficha(s) disponível(is)."
                        if contagens[perigo]
                        else "Categoria reservada; ainda não possui fichas."
                    ),
                )
                for perigo in PERICULOSIDADES
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        perigo = self.seletor.values[0]
        paginas = paginas_criaturas_alfabeticas(
            item
            for item in listar_fichas_criaturas()
            if item.periculosidade == perigo
        )
        primeira_preenchida = next(
            (indice for indice, (_, itens) in enumerate(paginas) if itens),
            0,
        )
        await interaction.response.edit_message(
            embed=painel(
                f"🔎 Criaturas {perigo}",
                "Escolha a faixa alfabética e, em seguida, a ficha.",
            ),
            view=ConsultaAlfabeticaCriaturaView(
                self.usuario_id,
                perigo,
                primeira_preenchida,
            ),
        )


class ConsultaAlfabeticaCriaturaView(ViewCriatura):
    def __init__(self, usuario_id: int, perigo: str, pagina: int):
        super().__init__(usuario_id)
        self.perigo = perigo
        self.paginas = paginas_criaturas_alfabeticas(
            item
            for item in listar_fichas_criaturas()
            if item.periculosidade == perigo
        )
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        rotulo, referencias = self.paginas[self.pagina]
        self.referencias = referencias

        faixas = discord.ui.Select(
            placeholder=f"Faixa alfabética — {rotulo}",
            options=[
                discord.SelectOption(
                    label=rotulo_pagina,
                    value=str(indice),
                    description=(
                        f"{len(itens)} ficha(s) nesta faixa."
                        if itens
                        else "Faixa reservada para fichas futuras."
                    ),
                    default=indice == self.pagina,
                )
                for indice, (rotulo_pagina, itens) in enumerate(self.paginas)
            ],
            row=0,
        )
        faixas.callback = self.selecionar_faixa
        self.faixas = faixas
        self.add_item(faixas)

        if referencias:
            fichas = discord.ui.Select(
                placeholder=f"Criaturas — {rotulo}",
                options=[
                    discord.SelectOption(
                        label=referencia.nome[:100],
                        value=str(indice),
                        description=f"Periculosidade {referencia.periculosidade}",
                    )
                    for indice, referencia in enumerate(referencias)
                ],
                row=1,
            )
            fichas.callback = self.selecionar_ficha
            self.fichas = fichas
            self.add_item(fichas)

        voltar = discord.ui.Button(
            label="Voltar às periculosidades",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar_faixa(self, interaction: discord.Interaction) -> None:
        pagina = int(self.faixas.values[0])
        rotulo, itens = self.paginas[pagina]
        await interaction.response.edit_message(
            embed=painel(
                f"🔎 Criaturas {self.perigo} — {rotulo}",
                (
                    "Escolha uma ficha nesta faixa."
                    if itens
                    else "Esta faixa ainda não possui fichas. Escolha outra faixa."
                ),
            ),
            view=ConsultaAlfabeticaCriaturaView(
                self.usuario_id,
                self.perigo,
                pagina,
            ),
        )

    async def selecionar_ficha(self, interaction: discord.Interaction) -> None:
        referencia = self.referencias[int(self.fichas.values[0])]
        if not referencia.caminho.is_file():
            await interaction.response.send_message(
                "A ficha escolhida não está mais disponível na biblioteca.",
                ephemeral=True,
            )
            return
        ficha = FichaCriatura.carregar(referencia.caminho)
        ficha._caminho_edicao = referencia.caminho.resolve()
        ficha._conteudo_original_edicao = referencia.caminho.read_text(
            encoding="utf-8-sig"
        )
        await interaction.response.edit_message(
            embeds=montar_embeds_criatura(ficha),
            view=EditorCriaturaView(self.usuario_id, ficha),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=painel(
                "🔎 Consultar criatura",
                "Escolha primeiro a periculosidade da ficha.",
            ),
            view=ConsultaPericulosidadeCriaturaView(self.usuario_id),
        )


class EscolherLoreView(ViewCriatura):
    def __init__(self, usuario_id: int, pagina: int):
        super().__init__(usuario_id)
        todas = listar_criaturas_lore()
        self.paginas = paginas_criaturas_alfabeticas(todas)
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        rotulo_pagina, itens_pagina = self.paginas[self.pagina]
        opcoes_pagina = [
            discord.SelectOption(label=i.nome, value=i.caminho.relative_to(PASTA_CRIATURAS).as_posix(), description=f"{i.classificacao} • {i.periculosidade}")
            for i in itens_pagina
        ] or [discord.SelectOption(label="Nenhuma criatura nesta faixa", value="__vazio__", description="Esta página está reservada para criaturas futuras.")]
        seletor = discord.ui.Select(
            placeholder=f"Espécies — {rotulo_pagina}",
            options=opcoes_pagina,
            disabled=not itens_pagina,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        anterior = discord.ui.Button(label="Anterior", style=discord.ButtonStyle.secondary, disabled=self.pagina == 0, row=1)
        proxima = discord.ui.Button(label="Próxima", style=discord.ButtonStyle.secondary, disabled=self.pagina == len(self.paginas) - 1, row=1)
        anterior.callback = self.anterior
        proxima.callback = self.proxima
        self.add_item(anterior); self.add_item(proxima)

    async def anterior(self, interaction):
        await interaction.response.edit_message(view=EscolherLoreView(self.usuario_id, self.pagina - 1))

    async def proxima(self, interaction):
        await interaction.response.edit_message(view=EscolherLoreView(self.usuario_id, self.pagina + 1))

    async def selecionar(self, interaction):
        if self.seletor.values[0] == "__vazio__":
            await interaction.response.defer()
            return
        caminho = PASTA_CRIATURAS / Path(self.seletor.values[0])
        referencia = next((i for i in listar_criaturas_lore() if i.caminho == caminho), None)
        if referencia is None:
            await interaction.response.send_message("A espécie não está mais na biblioteca.", ephemeral=True); return
        await interaction.response.edit_message(
            embed=painel(
                "📏 Faixa de tamanho",
                f"Escolha a base de tamanho para **{referencia.nome}**. Ela será usada no cálculo dos Pontos de Vida.",
            ),
            view=FaixaTamanhoBibliotecaView(self.usuario_id, referencia, self.pagina),
        )


class FaixaTamanhoBibliotecaView(ViewCriatura):
    def __init__(self, usuario_id: int, referencia: ReferenciaCriatura, pagina_origem: int):
        super().__init__(usuario_id)
        self.referencia = referencia
        self.pagina_origem = pagina_origem
        seletor = discord.ui.Select(
            placeholder="Escolha a faixa de tamanho",
            options=[
                discord.SelectOption(
                    label=faixa,
                    value=faixa,
                    description=f"{descricao} Base de {BASES_TAMANHO[faixa]} PV.",
                )
                for faixa, (descricao, _) in DESCRICOES_FAIXA_TAMANHO.items()
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            TamanhoCriaturaModal(self.usuario_id, self.referencia, self.seletor.values[0])
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=painel("📚 Biblioteca de Criaturas", "Escolha a espécie que servirá de base."),
            view=EscolherLoreView(self.usuario_id, self.pagina_origem),
        )


class TamanhoCriaturaModal(discord.ui.Modal):
    def __init__(self, usuario_id: int, referencia: ReferenciaCriatura, faixa: str):
        super().__init__(title="Tamanho da criatura")
        self.usuario_id = usuario_id
        self.referencia = referencia
        self.faixa = faixa
        descricao, exemplo = DESCRICOES_FAIXA_TAMANHO[faixa]
        self.tamanho = discord.ui.TextInput(
            label=f"Tamanho exato — {faixa}"[:45],
            placeholder=f"{descricao} {exemplo}"[:100],
            max_length=50,
        )
        self.add_item(self.tamanho)

    async def on_submit(self, interaction):
        try:
            tamanho = validar_e_normalizar_tamanho(str(self.tamanho.value), self.faixa)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.defer()
        ficha = FichaCriatura(
            self.referencia.nome,
            self.referencia.classificacao,
            self.referencia.periculosidade,
            tamanho,
            self.faixa,
            f"Biblioteca — {self.referencia.nome}",
            self.referencia.imagem,
            self.usuario_id,
        )
        await interaction.edit_original_response(
            embed=embed_atributos(ficha),
            view=AtributosCriaturaView(self.usuario_id, ficha, self.referencia.aptidoes),
        )


class PericulosidadeNovaCriaturaView(ViewCriatura):
    def __init__(self, usuario_id: int):
        super().__init__(usuario_id)
        seletor = discord.ui.Select(
            placeholder="Escolha a periculosidade",
            options=[
                discord.SelectOption(
                    label=perigo,
                    value=perigo,
                    description=(
                        f"{PONTOS_ATRIBUTO[perigo]} pontos de atributo • "
                        f"{XP_PERICIAS[perigo]} XP em perícias"
                    ),
                )
                for perigo in PERICULOSIDADES
            ],
            row=0,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        perigo = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=painel(
                "🐾 Classificação",
                f"Periculosidade escolhida: **{perigo}**. Agora escolha a classificação.",
            ),
            view=ClassificacaoNovaCriaturaView(self.usuario_id, perigo),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=painel(
                "🐾 Criar ficha de criatura",
                "Escolha uma espécie da biblioteca ou crie uma criatura que ainda não existe no RPG.",
            ),
            view=FonteCriaturaView(self.usuario_id),
        )


class ClassificacaoNovaCriaturaView(ViewCriatura):
    def __init__(self, usuario_id: int, perigo: str):
        super().__init__(usuario_id)
        self.perigo = perigo
        seletor = discord.ui.Select(
            placeholder="Escolha a classificação",
            options=[
                discord.SelectOption(
                    label=classificacao,
                    value=classificacao,
                    description=DESCRICOES_CLASSIFICACAO[classificacao],
                )
                for classificacao in CLASSIFICACOES
            ],
            row=0,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        classificacao = self.seletor.values[0]
        await interaction.response.defer()
        await interaction.edit_original_response(
            embed=painel(
                "📏 Faixa de tamanho",
                "Escolha a faixa usada como base no cálculo dos Pontos de Vida.",
            ),
            view=FaixaNovaCriaturaView(
                self.usuario_id,
                self.perigo,
                classificacao,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=painel("⚠️ Periculosidade", "Escolha o nível de periculosidade da nova criatura."),
            view=PericulosidadeNovaCriaturaView(self.usuario_id),
        )


class FaixaNovaCriaturaView(ViewCriatura):
    def __init__(self, usuario_id: int, perigo: str, classificacao: str):
        super().__init__(usuario_id)
        self.perigo = perigo
        self.classificacao = classificacao
        seletor = discord.ui.Select(
            placeholder="Escolha a faixa de tamanho",
            options=[
                discord.SelectOption(
                    label=faixa,
                    value=faixa,
                    description=f"{descricao} Base de {BASES_TAMANHO[faixa]} PV.",
                )
                for faixa, (descricao, _) in DESCRICOES_FAIXA_TAMANHO.items()
            ],
            row=0,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            DadosNovaCriaturaModal(
                self.usuario_id,
                self.perigo,
                self.classificacao,
                self.seletor.values[0],
            )
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=painel("🐾 Classificação", "Escolha a classificação da nova criatura."),
            view=ClassificacaoNovaCriaturaView(self.usuario_id, self.perigo),
        )


class DadosNovaCriaturaModal(discord.ui.Modal):
    def __init__(
        self,
        usuario_id: int,
        perigo: str,
        classificacao: str,
        faixa: str,
    ):
        super().__init__(title="Criar uma nova criatura")
        self.usuario_id = usuario_id
        self.perigo = perigo
        self.classificacao = classificacao
        self.faixa = faixa
        descricao, exemplo = DESCRICOES_FAIXA_TAMANHO[faixa]
        self.nome = discord.ui.TextInput(label="Nome", max_length=100)
        self.tamanho = discord.ui.TextInput(
            label=f"Tamanho exato — {faixa}"[:45],
            placeholder=f"{descricao} {exemplo}"[:100],
            max_length=50,
        )
        self.add_item(self.nome)
        self.add_item(self.tamanho)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            tamanho = validar_e_normalizar_tamanho(str(self.tamanho.value), self.faixa)
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        # Confirma o envio do modal antes de montar a próxima tela. Assim, o
        # Discord fecha a caixa imediatamente mesmo quando a edição demora.
        await interaction.response.defer()
        ficha = FichaCriatura(
            str(self.nome.value).strip(),
            self.classificacao,
            self.perigo,
            tamanho,
            self.faixa,
            "Nova criatura",
            "",
            self.usuario_id,
        )
        await interaction.edit_original_response(
            embed=embed_atributos(ficha),
            view=AtributosCriaturaView(self.usuario_id, ficha),
        )


def embed_atributos(ficha):
    return painel("📌 Atributos", f"Você pode reduzir atributos até 4 para liberar pontos. O máximo é {ATRIBUTO_MAXIMO_CRIATURA}.\n\n" + "\n".join(
        f"> **{n}:** {ficha.atributos[n]} {formatar_bonus(modificador(ficha.atributos[n]))}" for n in ATRIBUTOS_CRIATURA
    ) + f"\n\n**Pontos restantes:** {ficha.pontos_atributo_restantes}\n**PV atual:** {ficha.pv} • **PH atual:** {ficha.ph}")


class BotaoAtributoCriatura(discord.ui.Button):
    def __init__(self, atributo, delta, row):
        super().__init__(label=f"{atributo} {'+' if delta > 0 else '−'}", style=discord.ButtonStyle.secondary, row=row)
        self.atributo = atributo; self.delta = delta

    async def callback(self, interaction):
        view = self.view
        atual = view.ficha.atributos[self.atributo]
        novo = atual + self.delta
        if novo < 4 or novo > ATRIBUTO_MAXIMO_CRIATURA or (self.delta > 0 and view.ficha.pontos_atributo_restantes <= 0):
            await interaction.response.send_message("Esse ajuste ultrapassa os limites disponíveis.", ephemeral=True); return
        view.ficha.atributos[self.atributo] = novo
        view.atualizar()
        await interaction.response.edit_message(embed=embed_atributos(view.ficha), view=view)


class AtributosCriaturaView(ViewCriatura):
    def __init__(self, usuario_id, ficha, referencia=""):
        super().__init__(usuario_id); self.ficha = ficha; self.referencia = referencia
        for i, nome in enumerate(ATRIBUTOS_CRIATURA):
            self.add_item(BotaoAtributoCriatura(nome, 1, i // 2)); self.add_item(BotaoAtributoCriatura(nome, -1, i // 2))
        confirmar = discord.ui.Button(label="Confirmar atributos", style=discord.ButtonStyle.success, row=4)
        confirmar.callback = self.confirmar; self.confirmar_botao = confirmar; self.add_item(confirmar); self.atualizar()

    def atualizar(self):
        for item in self.children:
            if isinstance(item, BotaoAtributoCriatura):
                valor = self.ficha.atributos[item.atributo]
                item.disabled = valor >= ATRIBUTO_MAXIMO_CRIATURA if item.delta > 0 else valor <= 4
                if item.delta > 0 and self.ficha.pontos_atributo_restantes <= 0: item.disabled = True
        self.confirmar_botao.disabled = self.ficha.pontos_atributo_restantes != 0

    async def confirmar(self, interaction):
        texto = f"Distribua **{XP_PERICIAS[self.ficha.periculosidade]} XP** entre as perícias. Treinada 50 XP, Expert 150 XP total e Mestre 300 XP total."
        if self.referencia:
            texto += f"\n\n**Aptidões da biblioteca para consulta:**\n{self.referencia[:1000]}"
        await interaction.response.edit_message(embed=painel("📌 Perícias", texto), view=PericiasCriaturaView(self.usuario_id, self.ficha, 0, self.referencia))


class PericiasCriaturaView(ViewCriatura):
    def __init__(self, usuario_id, ficha, pagina, referencia=""):
        super().__init__(usuario_id); self.ficha=ficha; self.referencia=referencia
        paginas=paginas_pericias(); self.paginas=paginas; self.pagina=max(0,min(pagina,len(paginas)-1))
        rotulo_pagina,pericias_pagina=paginas[self.pagina]
        self.pericia=None; self.rank=None
        sp=discord.ui.Select(placeholder=f"Perícias — {rotulo_pagina}", options=opcoes(pericias_pagina), row=0)
        sr=discord.ui.Select(placeholder="Graduação", options=[discord.SelectOption(label=n, value=str(r), description=f"{CUSTO_TOTAL_RANK[r]} XP total") for r,n in RANKS_PERICIA_CRIATURA.items() if r], row=1)
        sp.callback=self.sel_pericia; sr.callback=self.sel_rank; self.sp=sp; self.sr=sr; self.add_item(sp); self.add_item(sr)
        comprar=discord.ui.Button(label="Aplicar graduação",style=discord.ButtonStyle.primary,row=2); comprar.callback=self.comprar; self.add_item(comprar)
        finalizar=discord.ui.Button(label="Finalizar perícias",style=discord.ButtonStyle.success,row=2); finalizar.callback=self.finalizar; self.add_item(finalizar)
        anterior=discord.ui.Button(label="Anterior",style=discord.ButtonStyle.secondary,disabled=self.pagina==0,row=3); anterior.callback=self.anterior; self.add_item(anterior)
        proxima=discord.ui.Button(label="Próxima",style=discord.ButtonStyle.secondary,disabled=self.pagina==len(paginas)-1,row=3); proxima.callback=self.proxima; self.add_item(proxima)
        limpar=discord.ui.Button(label="Limpar perícias",style=discord.ButtonStyle.danger,row=3); limpar.callback=self.limpar; self.add_item(limpar)

    async def sel_pericia(self, interaction): self.pericia=self.sp.values[0]; await interaction.response.defer()
    async def sel_rank(self, interaction): self.rank=int(self.sr.values[0]); await interaction.response.defer()
    async def anterior(self, interaction): await interaction.response.edit_message(view=PericiasCriaturaView(self.usuario_id,self.ficha,self.pagina-1,self.referencia))
    async def proxima(self, interaction): await interaction.response.edit_message(view=PericiasCriaturaView(self.usuario_id,self.ficha,self.pagina+1,self.referencia))
    async def limpar(self, interaction):
        self.ficha.pericias={n:0 for n in PERICIAS}; await interaction.response.edit_message(embed=painel("📌 Perícias",f"Perícias limpas. **{self.ficha.xp_pericias_restante} XP restantes.**"),view=PericiasCriaturaView(self.usuario_id,self.ficha,self.pagina,self.referencia))
    async def comprar(self, interaction):
        if self.pericia is None or self.rank is None:
            await interaction.response.send_message("Escolha a perícia e a graduação.",ephemeral=True); return
        atual=self.ficha.pericias[self.pericia]; diferenca=CUSTO_TOTAL_RANK[self.rank]-CUSTO_TOTAL_RANK[atual]
        if diferenca < 0:
            await interaction.response.send_message("Use Limpar perícias para refazer a distribuição.",ephemeral=True); return
        if diferenca > self.ficha.xp_pericias_restante:
            await interaction.response.send_message("O orçamento de XP de perícias é insuficiente.",ephemeral=True); return
        self.ficha.pericias[self.pericia]=self.rank
        treinadas=", ".join(f"{n} ({RANKS_PERICIA_CRIATURA[r]})" for n,r in self.ficha.pericias.items() if r) or "--"
        await interaction.response.edit_message(embed=painel("📌 Perícias",f"**XP restante:** {self.ficha.xp_pericias_restante}\n**Treinadas:** {treinadas}"),view=PericiasCriaturaView(self.usuario_id,self.ficha,self.pagina,self.referencia))
    async def finalizar(self, interaction):
        await interaction.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))


def embed_editor(ficha):
    return painel("🧰 Montagem da ficha", f"**{ficha.nome} • {ficha.periculosidade}**\nAdicione armas, ataques, habilidades, fraquezas e resistências. Quando terminar, confira a prévia.\n\nArmas: {len(ficha.armas_naturais)} • Ataques: {len(ficha.ataques)} • Habilidades: {len(ficha.habilidades)} • Fraquezas: {len(ficha.fraquezas)} • Resistências: {len(ficha.resistencias)}")


class EditorCriaturaView(ViewCriatura):
    def __init__(self, usuario_id, ficha):
        super().__init__(usuario_id); self.ficha=ficha

    @discord.ui.button(label="Armas",style=discord.ButtonStyle.secondary,emoji="🗡️")
    async def arma(self,interaction,_): await interaction.response.edit_message(embed=painel("🗡️ Armas","Adicione, modifique ou remova armas desta criatura."),view=GerenciarRegistrosCriaturaView(self.usuario_id,self.ficha,"arma"))
    @discord.ui.button(label="Ataque",style=discord.ButtonStyle.secondary,emoji="⚔️")
    async def ataque(self,interaction,_): await interaction.response.edit_message(embed=painel("⚔️ Ataques","Adicione, modifique ou remova ataques desta criatura."),view=GerenciarRegistrosCriaturaView(self.usuario_id,self.ficha,"ataque"))
    @discord.ui.button(label="Habilidade",style=discord.ButtonStyle.secondary,emoji="✨")
    async def habilidade(self,interaction,_):
        await interaction.response.edit_message(
            embed=painel(
                "✨ Habilidades",
                "Adicione, modifique ou remova habilidades desta criatura.",
            ),
            view=GerenciarHabilidadesCriaturaView(self.usuario_id,self.ficha),
        )
    @discord.ui.button(label="Fraqueza",style=discord.ButtonStyle.secondary,emoji="💔")
    async def fraqueza(self,interaction,_): await interaction.response.edit_message(embed=painel("💔 Fraqueza","Escolha a categoria e depois o aumento de dano ou a desvantagem aplicável."),view=CategoriaEfeitoView(self.usuario_id,self.ficha,True))
    @discord.ui.button(label="Resistência",style=discord.ButtonStyle.secondary,emoji="🛡️")
    async def resistencia(self,interaction,_): await interaction.response.edit_message(embed=painel("🛡️ Resistência","Escolha a categoria e depois a redução de dano, vantagem ou imunidade aplicável."),view=CategoriaEfeitoView(self.usuario_id,self.ficha,False))
    @discord.ui.button(label="Prévia",style=discord.ButtonStyle.success,emoji="✅",row=1)
    async def previa(self,interaction,_):
        try: validar_ficha(self.ficha)
        except ValueError as erro: await interaction.response.send_message(str(erro),ephemeral=True); return
        await interaction.response.edit_message(embeds=montar_embeds_criatura(self.ficha),view=ConfirmarCriaturaView(self.usuario_id,self.ficha))


def limpar_contexto_edicao_habilidade(ficha: FichaCriatura) -> None:
    for atributo in ("_habilidade_indice_edicao", "_habilidade_original_edicao"):
        if hasattr(ficha, atributo):
            delattr(ficha, atributo)


def registrar_habilidade_criatura(
    ficha: FichaCriatura, item: dict[str, str]
) -> None:
    indice = getattr(ficha, "_habilidade_indice_edicao", None)
    original = getattr(ficha, "_habilidade_original_edicao", None)
    if indice is None:
        ficha.habilidades.append(item)
    elif indice >= len(ficha.habilidades) or ficha.habilidades[indice] != original:
        raise ValueError(
            "A habilidade original mudou durante a edição. Abra novamente o editor "
            "para evitar sobrescrever alterações."
        )
    else:
        ficha.habilidades[indice] = item
    limpar_contexto_edicao_habilidade(ficha)


class GerenciarHabilidadesCriaturaView(ViewCriatura):
    def __init__(self, usuario_id: int, ficha: FichaCriatura):
        super().__init__(usuario_id)
        self.ficha = ficha
        adicionar = discord.ui.Button(
            label="Adicionar", style=discord.ButtonStyle.success, emoji="➕"
        )
        modificar = discord.ui.Button(
            label="Modificar", style=discord.ButtonStyle.secondary, emoji="✏️"
        )
        remover = discord.ui.Button(
            label="Remover", style=discord.ButtonStyle.danger, emoji="🗑️"
        )
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary)
        modificar.disabled = not ficha.habilidades
        remover.disabled = not ficha.habilidades
        adicionar.callback = self.adicionar
        modificar.callback = self.modificar
        remover.callback = self.remover
        voltar.callback = self.voltar
        for botao in (adicionar, modificar, remover, voltar):
            self.add_item(botao)

    async def adicionar(self, interaction: discord.Interaction) -> None:
        limpar_contexto_edicao_habilidade(self.ficha)
        await interaction.response.edit_message(
            embed=painel(
                "✨ Configurar habilidade",
                "Escolha o tipo de ativação e o tipo de ação.",
            ),
            view=ConfiguracaoHabilidadeView(self.usuario_id, self.ficha),
        )

    async def modificar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=painel(
                "✏️ Modificar habilidade",
                "Escolha a habilidade que será refeita no criador completo.",
            ),
            view=SelecionarHabilidadeCriaturaView(
                self.usuario_id, self.ficha, "modificar"
            ),
        )

    async def remover(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=painel(
                "🗑️ Remover habilidade",
                "Escolha a habilidade que deseja remover.",
            ),
            view=SelecionarHabilidadeCriaturaView(
                self.usuario_id, self.ficha, "remover"
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        limpar_contexto_edicao_habilidade(self.ficha)
        await interaction.response.edit_message(
            embed=embed_editor(self.ficha),
            view=EditorCriaturaView(self.usuario_id, self.ficha),
        )


class SelecionarHabilidadeCriaturaView(ViewCriatura):
    def __init__(
        self,
        usuario_id: int,
        ficha: FichaCriatura,
        acao: str,
        pagina: int = 0,
    ):
        super().__init__(usuario_id)
        self.ficha = ficha
        self.acao = acao
        self.paginas = [
            list(range(indice, min(indice + 25, len(ficha.habilidades))))
            for indice in range(0, len(ficha.habilidades), 25)
        ] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        indices = self.paginas[self.pagina]
        seletor = discord.ui.Select(
            placeholder=f"Habilidades — página {self.pagina + 1}/{len(self.paginas)}",
            options=[
                discord.SelectOption(
                    label=ficha.habilidades[indice].get("nome", "Habilidade")[:100],
                    value=str(indice),
                    description=ficha.habilidades[indice].get("tipo de efeito", "")[:100] or None,
                )
                for indice in indices
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        if len(self.paginas) > 1:
            anterior = discord.ui.Button(
                label="Anterior", style=discord.ButtonStyle.secondary,
                disabled=self.pagina == 0, row=1,
            )
            proxima = discord.ui.Button(
                label="Próxima", style=discord.ButtonStyle.secondary,
                disabled=self.pagina == len(self.paginas) - 1, row=1,
            )
            anterior.callback = self.anterior
            proxima.callback = self.proxima
            self.add_item(anterior)
            self.add_item(proxima)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=2)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        indice = int(self.seletor.values[0])
        original = dict(self.ficha.habilidades[indice])
        if self.acao == "modificar":
            self.ficha._habilidade_indice_edicao = indice
            self.ficha._habilidade_original_edicao = original
            await interaction.response.edit_message(
                embed=painel(
                    "✨ Configurar habilidade",
                    "Revise o tipo de ativação e o tipo de ação.",
                ),
                view=ConfiguracaoHabilidadeView(
                    self.usuario_id,
                    self.ficha,
                    original.get("tipo de ativação", ""),
                    original.get("tipo de ação", ""),
                    dict(original),
                ),
            )
            return
        await interaction.response.edit_message(
            embed=painel(
                "🗑️ Confirmar remoção",
                f"Remover **{original.get('nome', 'Habilidade')}** desta ficha?",
            ),
            view=ConfirmarRemocaoHabilidadeCriaturaView(
                self.usuario_id, self.ficha, indice, original
            ),
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=SelecionarHabilidadeCriaturaView(
                self.usuario_id, self.ficha, self.acao, self.pagina - 1
            )
        )

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=SelecionarHabilidadeCriaturaView(
                self.usuario_id, self.ficha, self.acao, self.pagina + 1
            )
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=painel(
                "✨ Habilidades",
                "Adicione, modifique ou remova habilidades desta criatura.",
            ),
            view=GerenciarHabilidadesCriaturaView(self.usuario_id, self.ficha),
        )


class ConfirmarRemocaoHabilidadeCriaturaView(ViewCriatura):
    def __init__(
        self,
        usuario_id: int,
        ficha: FichaCriatura,
        indice: int,
        original: dict[str, str],
    ):
        super().__init__(usuario_id)
        self.ficha = ficha
        self.indice = indice
        self.original = original

    @discord.ui.button(label="Remover", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def remover(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if (
            self.indice >= len(self.ficha.habilidades)
            or self.ficha.habilidades[self.indice] != self.original
        ):
            await interaction.response.send_message(
                "A lista de habilidades mudou. Abra novamente o editor.", ephemeral=True
            )
            return
        self.ficha.habilidades.pop(self.indice)
        limpar_contexto_edicao_habilidade(self.ficha)
        await interaction.response.edit_message(
            embed=embed_editor(self.ficha),
            view=EditorCriaturaView(self.usuario_id, self.ficha),
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=painel(
                "✨ Habilidades",
                "Adicione, modifique ou remova habilidades desta criatura.",
            ),
            view=GerenciarHabilidadesCriaturaView(self.usuario_id, self.ficha),
        )


def registros_criatura(ficha: FichaCriatura, tipo: str) -> list[dict[str, str]]:
    return ficha.armas_naturais if tipo == "arma" else ficha.ataques


def limpar_contexto_edicao_registro_criatura(ficha: FichaCriatura, tipo: str) -> None:
    for sufixo in ("indice_edicao", "original_edicao"):
        atributo = f"_{tipo}_{sufixo}"
        if hasattr(ficha, atributo):
            delattr(ficha, atributo)


def registrar_item_criatura(
    ficha: FichaCriatura, tipo: str, item: dict[str, str]
) -> None:
    destino = registros_criatura(ficha, tipo)
    indice = getattr(ficha, f"_{tipo}_indice_edicao", None)
    original = getattr(ficha, f"_{tipo}_original_edicao", None)
    if indice is None:
        destino.append(item)
    elif indice >= len(destino) or destino[indice] != original:
        raise ValueError(
            f"O registro de {tipo} mudou durante a edição. Abra novamente o editor."
        )
    else:
        destino[indice] = item
    limpar_contexto_edicao_registro_criatura(ficha, tipo)


class GerenciarRegistrosCriaturaView(ViewCriatura):
    def __init__(self, usuario_id: int, ficha: FichaCriatura, tipo: str):
        super().__init__(usuario_id);self.ficha=ficha;self.tipo=tipo
        destino=registros_criatura(ficha,tipo)
        adicionar=discord.ui.Button(label="Adicionar",style=discord.ButtonStyle.success,emoji="➕")
        modificar=discord.ui.Button(label="Modificar",style=discord.ButtonStyle.secondary,emoji="✏️",disabled=not destino)
        remover=discord.ui.Button(label="Remover",style=discord.ButtonStyle.danger,emoji="🗑️",disabled=not destino)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary)
        adicionar.callback=self.adicionar;modificar.callback=self.modificar;remover.callback=self.remover;voltar.callback=self.voltar
        for botao in (adicionar,modificar,remover,voltar):self.add_item(botao)

    async def adicionar(self,i):
        limpar_contexto_edicao_registro_criatura(self.ficha,self.tipo)
        if self.tipo=="arma":
            await i.response.edit_message(embed=painel("🗡️ Armas","Escolha primeiro o tipo de arma que deseja adicionar."),view=TipoArmaView(self.usuario_id,self.ficha));return
        await i.response.edit_message(embed=painel("⚔️ Ataque não mágico","Escolha um preset ou crie um ataque do zero."),view=EscolhaNomeItemView(self.usuario_id,self.ficha,"ataque",ATAQUES))

    async def modificar(self,i):
        await i.response.edit_message(
            embed=painel(f"✏️ Modificar {self.tipo}",f"Escolha {('a arma' if self.tipo=='arma' else 'o ataque')} que deseja alterar."),
            view=SelecionarRegistroCriaturaView(self.usuario_id,self.ficha,self.tipo,"modificar"),
        )

    async def remover(self,i):
        await i.response.edit_message(
            embed=painel(f"🗑️ Remover {self.tipo}",f"Escolha {('a arma' if self.tipo=='arma' else 'o ataque')} que deseja remover."),
            view=SelecionarRegistroCriaturaView(self.usuario_id,self.ficha,self.tipo,"remover"),
        )

    async def voltar(self,i):
        limpar_contexto_edicao_registro_criatura(self.ficha,self.tipo)
        await i.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))


class SelecionarRegistroCriaturaView(ViewCriatura):
    def __init__(self,usuario_id,ficha,tipo,acao,pagina=0):
        super().__init__(usuario_id);self.ficha=ficha;self.tipo=tipo;self.acao=acao
        destino=registros_criatura(ficha,tipo)
        self.paginas=[list(range(n,min(n+25,len(destino)))) for n in range(0,len(destino),25)] or [[]]
        self.pagina=max(0,min(pagina,len(self.paginas)-1));indices=self.paginas[self.pagina]
        seletor=discord.ui.Select(
            placeholder=f"{('Armas' if tipo=='arma' else 'Ataques')} — página {self.pagina+1}/{len(self.paginas)}",
            options=[discord.SelectOption(label=destino[n].get("nome",tipo.title())[:100],value=str(n),description=(destino[n].get("categoria") or destino[n].get("tipo de ação") or "")[:100] or None) for n in indices],
        )
        seletor.callback=self.selecionar;self.seletor=seletor;self.add_item(seletor)
        if len(self.paginas)>1:
            anterior=discord.ui.Button(label="Anterior",style=discord.ButtonStyle.secondary,disabled=self.pagina==0,row=1)
            proxima=discord.ui.Button(label="Próxima",style=discord.ButtonStyle.secondary,disabled=self.pagina==len(self.paginas)-1,row=1)
            anterior.callback=self.anterior;proxima.callback=self.proxima;self.add_item(anterior);self.add_item(proxima)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=2);voltar.callback=self.voltar;self.add_item(voltar)

    async def selecionar(self,i):
        indice=int(self.seletor.values[0]);destino=registros_criatura(self.ficha,self.tipo);original=dict(destino[indice])
        if self.acao=="remover":
            await i.response.edit_message(embed=painel("🗑️ Confirmar remoção",f"Remover **{original.get('nome',self.tipo.title())}** desta ficha?"),view=ConfirmarRemocaoRegistroCriaturaView(self.usuario_id,self.ficha,self.tipo,indice,original));return
        setattr(self.ficha,f"_{self.tipo}_indice_edicao",indice);setattr(self.ficha,f"_{self.tipo}_original_edicao",original)
        if self.tipo=="arma":
            await i.response.send_modal(EditarArmaCriaturaModal(self.usuario_id,self.ficha,original));return
        await i.response.edit_message(
            embed=painel(f"⚔️ Configurar {original.get('nome','Ataque')}","Revise o tipo de ação e a rolagem de ataque."),
            view=ConfiguracaoAtaqueView(self.usuario_id,self.ficha,original.get("nome","Personalizado"),original.get("tipo de ação",""),original.get("rolagem de ataque",""),original),
        )

    async def anterior(self,i):await i.response.edit_message(view=SelecionarRegistroCriaturaView(self.usuario_id,self.ficha,self.tipo,self.acao,self.pagina-1))
    async def proxima(self,i):await i.response.edit_message(view=SelecionarRegistroCriaturaView(self.usuario_id,self.ficha,self.tipo,self.acao,self.pagina+1))
    async def voltar(self,i):await i.response.edit_message(embed=painel("🧰 Gerenciar registros","Escolha o que deseja fazer."),view=GerenciarRegistrosCriaturaView(self.usuario_id,self.ficha,self.tipo))


class ConfirmarRemocaoRegistroCriaturaView(ViewCriatura):
    def __init__(self,usuario_id,ficha,tipo,indice,original):
        super().__init__(usuario_id);self.ficha=ficha;self.tipo=tipo;self.indice=indice;self.original=original
    @discord.ui.button(label="Remover",style=discord.ButtonStyle.danger,emoji="🗑️")
    async def remover(self,i,_):
        destino=registros_criatura(self.ficha,self.tipo)
        if self.indice>=len(destino) or destino[self.indice]!=self.original:
            await i.response.send_message("A lista mudou. Abra novamente o editor.",ephemeral=True);return
        destino.pop(self.indice);limpar_contexto_edicao_registro_criatura(self.ficha,self.tipo)
        await i.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))
    @discord.ui.button(label="Cancelar",style=discord.ButtonStyle.secondary)
    async def cancelar(self,i,_):await i.response.edit_message(embed=painel("🧰 Gerenciar registros","Escolha o que deseja fazer."),view=GerenciarRegistrosCriaturaView(self.usuario_id,self.ficha,self.tipo))


class EditarArmaCriaturaModal(discord.ui.Modal):
    def __init__(self,usuario_id,ficha,item):
        super().__init__(title="Modificar arma");self.usuario_id=usuario_id;self.ficha=ficha;self.item=dict(item)
        self.nome=discord.ui.TextInput(label="Nome",default=item.get("nome",""),max_length=100)
        self.tipo_dano=discord.ui.TextInput(label="Tipo de dano",default=item.get("tipo de dano",""),max_length=100)
        self.dano=discord.ui.TextInput(label="Dano",default=item.get("dano",item.get("dano-base","")),max_length=100)
        self.critico=discord.ui.TextInput(label="Efeito de crítico",default=item.get("crítico",""),max_length=30)
        self.descricao=discord.ui.TextInput(label="Descrição",default=item.get("descrição",""),style=discord.TextStyle.paragraph,required=False,max_length=800)
        for campo in (self.nome,self.tipo_dano,self.dano,self.critico,self.descricao):self.add_item(campo)
    async def on_submit(self,i):
        self.item.update({"nome":str(self.nome.value).strip(),"tipo de dano":str(self.tipo_dano.value).strip(),"dano":somar_atributo_ao_dano(str(self.dano.value).strip(),self.ficha.atributos),"crítico":str(self.critico.value).strip()})
        descricao=str(self.descricao.value).strip()
        if descricao:self.item["descrição"]=descricao
        else:self.item.pop("descrição",None)
        try:registrar_item_criatura(self.ficha,"arma",self.item)
        except ValueError as erro:await i.response.send_message(str(erro),ephemeral=True);return
        await i.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))


class TipoArmaView(ViewCriatura):
    def __init__(self,usuario_id,ficha):
        super().__init__(usuario_id);self.ficha=ficha
        seletor=discord.ui.Select(placeholder="Tipo de arma",options=opcoes(tuple(ARMAS_POR_TIPO),DESCRICOES_TIPOS_ARMAS),row=0)
        seletor.callback=self.selecionar;self.seletor=seletor;self.add_item(seletor)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=1);voltar.callback=self.voltar;self.add_item(voltar)
    async def selecionar(self,i):
        tipo=self.seletor.values[0]
        await i.response.edit_message(embed=painel(f"🗡️ {tipo}","Escolha uma arma da tabela ou crie uma personalizada."),view=ArmaView(self.usuario_id,self.ficha,tipo))
    async def voltar(self,i): await i.response.edit_message(embed=painel("🗡️ Armas","Adicione, modifique ou remova armas desta criatura."),view=GerenciarRegistrosCriaturaView(self.usuario_id,self.ficha,"arma"))


class ArmaView(ViewCriatura):
    def __init__(self,usuario_id,ficha,tipo_arma):
        super().__init__(usuario_id);self.ficha=ficha;self.tipo_arma=tipo_arma;armas=ARMAS_POR_TIPO[tipo_arma]
        descricoes={nome:self.descricao_opcao(dados) for nome,dados in armas.items()}
        descricoes["Personalizada"]="Crie uma arma desta categoria que ainda não está nos presets."
        seletor=discord.ui.Select(placeholder="Escolha a arma",options=opcoes(tuple(armas)+("Personalizada",),descricoes),row=0)
        seletor.callback=self.selecionar;self.seletor=seletor;self.add_item(seletor)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=1);voltar.callback=self.voltar;self.add_item(voltar)
    def descricao_opcao(self, dados):
        alcance=dados.get("alcance") or dados.get("alcance curto") or dados.get("alcance efetivo")
        dano=dados.get("dano-base",dados.get("dano"))
        if dano:
            dano=somar_atributo_ao_dano(dano,self.ficha.atributos)
        texto=f"{dados['tipo de dano']} • {dano} • crítico {dados['crítico']}"
        return f"{texto} • {alcance}" if alcance else texto
    async def selecionar(self,i):
        nome=self.seletor.values[0]
        if nome=="Personalizada":
            await i.response.send_modal(ArmaPersonalizadaModal(self.usuario_id,self.ficha,self.tipo_arma));return
        dados=dict(ARMAS_POR_TIPO[self.tipo_arma][nome])
        if self.tipo_arma=="Armas Naturais":
            try: dados["dano"]=dano_arma_natural(dados.pop("dano-base"),self.ficha.periculosidade,self.ficha.tamanho)
            except ValueError as erro: await i.response.send_message(str(erro),ephemeral=True);return
        dados["dano"]=somar_atributo_ao_dano(dados["dano"],self.ficha.atributos)
        registrar_item_criatura(self.ficha,"arma",{"nome":nome,"categoria":self.tipo_arma,**dados})
        await i.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))
    async def voltar(self,i): await i.response.edit_message(embed=painel("🗡️ Armas","Escolha primeiro o tipo de arma que deseja adicionar."),view=TipoArmaView(self.usuario_id,self.ficha))


class ArmaPersonalizadaModal(discord.ui.Modal):
    def __init__(self,usuario_id,ficha,tipo_arma):
        super().__init__(title="Criar arma personalizada");self.usuario_id=usuario_id;self.ficha=ficha;self.tipo_arma=tipo_arma
        self.nome=discord.ui.TextInput(label="Nome",max_length=100)
        self.tipo_dano=discord.ui.TextInput(label="Tipo de dano",max_length=100)
        self.dano_base=discord.ui.TextInput(label="Dano-base",placeholder="Ex.: 1d6+Força ou 1d6+Destreza",max_length=50)
        self.critico=discord.ui.TextInput(label="Efeito de crítico",placeholder="Ex.: x2",max_length=30)
        self.descricao=discord.ui.TextInput(label="Descrição",style=discord.TextStyle.paragraph,required=False,max_length=800)
        for campo in (self.nome,self.tipo_dano,self.dano_base,self.critico,self.descricao):self.add_item(campo)
    async def on_submit(self,i):
        dano=str(self.dano_base.value).strip()
        if self.tipo_arma=="Armas Naturais":
            try: dano=dano_arma_natural(dano,self.ficha.periculosidade,self.ficha.tamanho)
            except ValueError as erro: await i.response.send_message(str(erro),ephemeral=True);return
        dano=somar_atributo_ao_dano(dano,self.ficha.atributos)
        item={"nome":str(self.nome.value).strip(),"categoria":self.tipo_arma,"tipo de dano":str(self.tipo_dano.value).strip(),"dano":dano,"crítico":str(self.critico.value).strip()}
        descricao=str(self.descricao.value).strip()
        if descricao:item["descrição"]=descricao
        registrar_item_criatura(self.ficha,"arma",item)
        await i.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))


ATAQUES_COM_ARMA = {
    "Emboscada", "Bote", "Investida", "Varredura",
    "Ataques Múltiplos", "Ataque Venenoso", "Ataque Ácido",
}


def armas_disponiveis(ficha: FichaCriatura, *, somente_naturais: bool = False):
    resultado = []
    for indice, arma in enumerate(ficha.armas_naturais):
        categoria = arma.get("categoria", "Armas Naturais")
        if somente_naturais and categoria != "Armas Naturais":
            continue
        resultado.append((indice, arma))
    return resultado


def item_ataque_preset(
    ficha: FichaCriatura,
    nome: str,
    *,
    arma: dict[str, str] | None = None,
    patas: int | None = None,
    rolagem_variavel: str | None = None,
) -> dict[str, str]:
    nivel = ficha.nivel
    mod_forca = modificador(ficha.atributos["Força"])
    mod_destreza = modificador(ficha.atributos["Destreza"])
    recarga = recarga_padrao(ficha.periculosidade)
    descricao = DESCRICOES_ATAQUES[nome]
    acao = "Completa"
    rolagem = "--"
    efeito = "--"
    resistencia = "Nenhum"
    duracao = "Instantâneo"
    dano_da_arma = (
        somar_atributo_ao_dano(arma.get("dano", "--"), ficha.atributos)
        if arma else None
    )

    if nome == "Emboscada":
        rolagem = "Furtividade"
        dano = dano_da_arma or "Escolha uma arma."
        efeito = (
            f"{dano}. Um alvo surpreendido sofre penalidade de {mod_destreza} no teste "
            "para esquivar ou defender."
        )
    elif nome == "Bote":
        rolagem = "Destreza"
        dano = dano_da_arma or "Escolha uma arma."
        efeito = f"{dano} + {2 * nivel} de dano bônus."
    elif nome == "Investida":
        rolagem = "Atletismo"
        dano = dano_da_arma or "Escolha uma arma."
        bonus = avancar_passo_dano("1d6", nivel - 1)
        efeito = f"{dano} + {bonus} de dano bônus."
    elif nome == "Derrubar":
        rolagem = "Fortitude"
        cd = cd_atributo(ficha, "Força")
        efeito = (
            "Em caso de falha, o alvo gasta uma Ação Completa para recuperar a postura e os sentidos "
            "no próximo turno. Em caso de sucesso, perde somente a Ação de Movimento."
        )
        resistencia = f"Fortitude contra CD {cd}."
        duracao = "1 rodada"
    elif nome == "Arremesso":
        rolagem = "Atletismo"
        tamanho = math.floor(tamanho_em_metros(ficha.tamanho) + 0.5)
        efeito = f"{tamanho + mod_forca} de dano concussivo ({tamanho} pelo tamanho + {mod_forca} de Força)."
    elif nome == "Pisotear":
        acao = "Movimento"
        rolagem = "Atletismo"
        if patas is None:
            efeito = "Escolha quantas patas participarão do ataque."
        else:
            dado = dado_pisotear(ficha.tamanho)
            efeito = f"{multiplicar_quantidade_dados(dado, patas)}{formatar_bonus(mod_forca)} de dano com {patas} pata(s)."
    elif nome == "Varredura":
        acao = "Movimento"
        rolagem = "Luta com o maior bônus entre Força e Destreza"
        efeito = dano_da_arma or "Escolha uma arma natural."
    elif nome == "Coice":
        acao = "Padrão"
        rolagem = "Força"
        punhos = dano_arma_natural("1d4+Força", ficha.periculosidade, ficha.tamanho)
        efeito = somar_atributo_ao_dano(multiplicar_dados(punhos, 2), ficha.atributos)
    elif nome == "Agarrão":
        rolagem = "Destreza"
        cd = cd_atributo(ficha, "Força")
        efeito = (
            "O alvo fica restrito a ações livres. Uma tentativa de escape custa uma Ação de Movimento; "
            "se falhar, permanece impedido de usar a Ação Padrão."
        )
        resistencia = f"Destreza, Acrobacia ou Atletismo contra CD {cd}."
        duracao = "Até escapar"
    elif nome == "Constrição":
        acao = "Padrão"
        rolagem = "Força"
        cd = cd_atributo(ficha, "Força")
        dano = max(1, mod_forca * nivel)
        efeito = f"{dano} de dano concussivo/sufocante por rodada contra um alvo previamente agarrado."
        resistencia = f"Destreza, Acrobacia ou Atletismo contra CD {cd}."
        duracao = "Até escapar"
    elif nome == "Ataques Múltiplos":
        rolagem = "Luta com modificador de Destreza"
        dano = dano_da_arma or "Escolha uma arma."
        efeito = (
            f"Até {1 + nivel} golpes com a arma escolhida, causando {dano} por acerto. "
            "Cada golpe exige uma rolagem de ataque e uma rolagem de dano separadas."
        )
    elif nome in {"Ataque Venenoso", "Ataque Ácido"}:
        rolagem = rolagem_variavel or "Escolha Luta ou Pontaria."
        tipo = "venenoso" if nome == "Ataque Venenoso" else "ácido"
        dano = dano_da_arma or "Escolha uma arma."
        efeito = (
            f"{dano} + {2 * nivel} de dano {tipo}; depois, +{nivel} de dano {tipo} por turno durante "
            "2 turnos. Um novo acerto do mesmo tipo apenas renova a duração, sem acumular o efeito."
        )
        duracao = "2 turnos"

    return {
        "nome": nome,
        "descrição": descricao,
        "tipo de ação": acao,
        "rolagem de ataque": rolagem,
        "dano ou efeito": efeito,
        "teste de resistência": resistencia,
        "duração": duracao,
        "recarga": recarga,
    }


def embed_configuracao_preset(item: dict[str, str]) -> discord.Embed:
    embed = discord.Embed(title=f"⚔️ Configurar {item['nome']}")
    for campo in (
        "descrição", "tipo de ação", "rolagem de ataque", "dano ou efeito",
        "teste de resistência", "duração", "recarga",
    ):
        embed.add_field(name=campo.capitalize(), value=item[campo], inline=False)
    return embed


class ConfiguracaoPresetAtaqueView(ViewCriatura):
    def __init__(self, usuario_id, ficha, nome):
        super().__init__(usuario_id);self.ficha=ficha;self.nome=nome;self.arma=None;self.patas=None;self.rolagem_variavel=None
        linha = 0
        if nome in ATAQUES_COM_ARMA:
            armas = armas_disponiveis(ficha, somente_naturais=nome == "Varredura")
            if armas:
                seletor_arma = discord.ui.Select(
                    placeholder="Arma utilizada",
                    options=[
                        discord.SelectOption(
                            label=arma.get("nome", "Arma")[:100],
                            value=str(indice),
                            description=f"{arma.get('categoria', 'Armas Naturais')} • {arma.get('dano', '--')}"[:100],
                        )
                        for indice, arma in armas[:25]
                    ],
                    row=linha,
                )
                seletor_arma.callback=self.selecionar_arma;self.seletor_arma=seletor_arma;self.add_item(seletor_arma);linha+=1
        if nome == "Pisotear":
            seletor_patas=discord.ui.Select(placeholder="Quantidade de patas",options=opcoes(tuple(str(n) for n in range(1,11))),row=linha)
            seletor_patas.callback=self.selecionar_patas;self.seletor_patas=seletor_patas;self.add_item(seletor_patas);linha+=1
        if nome in {"Ataque Venenoso", "Ataque Ácido"}:
            seletor_rolagem=discord.ui.Select(placeholder="Rolagem do ataque",options=opcoes(("Luta","Pontaria"),ROLAGENS_ATAQUE),row=linha)
            seletor_rolagem.callback=self.selecionar_rolagem;self.seletor_rolagem=seletor_rolagem;self.add_item(seletor_rolagem);linha+=1
        adicionar=discord.ui.Button(label="Adicionar ataque",style=discord.ButtonStyle.success,row=linha);adicionar.callback=self.adicionar;self.add_item(adicionar)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=linha);voltar.callback=self.voltar;self.add_item(voltar)

    def item(self):
        return item_ataque_preset(self.ficha,self.nome,arma=self.arma,patas=self.patas,rolagem_variavel=self.rolagem_variavel)

    async def atualizar(self,i): await i.response.edit_message(embed=embed_configuracao_preset(self.item()),view=self)
    async def selecionar_arma(self,i): self.arma=self.ficha.armas_naturais[int(self.seletor_arma.values[0])];await self.atualizar(i)
    async def selecionar_patas(self,i): self.patas=int(self.seletor_patas.values[0]);await self.atualizar(i)
    async def selecionar_rolagem(self,i): self.rolagem_variavel=self.seletor_rolagem.values[0];await self.atualizar(i)
    async def adicionar(self,i):
        if self.nome in ATAQUES_COM_ARMA and self.arma is None:
            await i.response.send_message("Escolha a arma utilizada. Se nenhuma estiver disponível, adicione uma arma à ficha primeiro.",ephemeral=True);return
        if self.nome=="Pisotear" and self.patas is None:
            await i.response.send_message("Escolha a quantidade de patas utilizada.",ephemeral=True);return
        if self.nome in {"Ataque Venenoso","Ataque Ácido"} and self.rolagem_variavel is None:
            await i.response.send_message("Escolha Luta ou Pontaria para a rolagem do ataque.",ephemeral=True);return
        registrar_item_criatura(self.ficha,"ataque",self.item())
        await i.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))
    async def voltar(self,i):
        await i.response.edit_message(embed=painel("⚔️ Ataque não mágico","Escolha um preset ou crie um ataque do zero."),view=EscolhaNomeItemView(self.usuario_id,self.ficha,"ataque",ATAQUES))


class EscolhaNomeItemView(ViewCriatura):
    def __init__(self,usuario_id,ficha,tipo,valores):
        super().__init__(usuario_id);self.ficha=ficha;self.tipo=tipo
        descricoes=DESCRICOES_ATAQUES if tipo=="ataque" else None
        s=discord.ui.Select(placeholder="Escolha uma opção",options=opcoes(valores,descricoes));s.callback=self.selecionar;self.s=s;self.add_item(s)
        v=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=1);v.callback=self.voltar;self.add_item(v)
    async def selecionar(self,i):
        nome=self.s.values[0]
        if self.tipo=="ataque" and nome!="Personalizado":
            view=ConfiguracaoPresetAtaqueView(self.usuario_id,self.ficha,nome)
            await i.response.edit_message(embed=embed_configuracao_preset(view.item()),view=view);return
        await i.response.edit_message(
            embed=painel(
                f"⚔️ Configurar {nome}",
                "Escolha o tipo de ação e a rolagem usada pela criatura para acertar o ataque.",
            ),
            view=ConfiguracaoAtaqueView(self.usuario_id,self.ficha,nome),
        )
    async def voltar(self,i):
        if self.tipo=="ataque":
            await i.response.edit_message(embed=painel("⚔️ Ataques","Adicione, modifique ou remova ataques desta criatura."),view=GerenciarRegistrosCriaturaView(self.usuario_id,self.ficha,"ataque"));return
        await i.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))


class ConfiguracaoAtaqueView(ViewCriatura):
    def __init__(self,usuario_id,ficha,nome,acao_atual="",rolagem_atual="",item=None):
        super().__init__(usuario_id);self.ficha=ficha;self.nome=nome;self.acao=acao_atual;self.rolagem=rolagem_atual;self.item=dict(item or {})
        acao=discord.ui.Select(placeholder="Tipo de ação",options=[discord.SelectOption(label=v,value=v,default=v==acao_atual) for v in ACOES],row=0)
        rolagem=discord.ui.Select(placeholder="Rolagem de ataque",options=[discord.SelectOption(label=v,value=v,description=ROLAGENS_ATAQUE[v],default=v==rolagem_atual) for v in ROLAGENS_ATAQUE],row=1)
        acao.callback=self.selecionar_acao;rolagem.callback=self.selecionar_rolagem
        self.acao_select=acao;self.rolagem_select=rolagem;self.add_item(acao);self.add_item(rolagem)
        continuar=discord.ui.Button(label="Continuar",style=discord.ButtonStyle.primary,row=2);continuar.callback=self.continuar;self.add_item(continuar)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=2);voltar.callback=self.voltar;self.add_item(voltar)

    async def selecionar_acao(self,i): self.acao=self.acao_select.values[0];await i.response.defer()
    async def selecionar_rolagem(self,i): self.rolagem=self.rolagem_select.values[0];await i.response.defer()
    async def continuar(self,i):
        if not self.acao or not self.rolagem:
            await i.response.send_message("Escolha o tipo de ação e a rolagem de ataque.",ephemeral=True);return
        await i.response.send_modal(AtaqueModal(self.usuario_id,self.ficha,self.nome,self.acao,self.rolagem,self.item))
    async def voltar(self,i):
        if self.item:
            limpar_contexto_edicao_registro_criatura(self.ficha,"ataque")
            await i.response.edit_message(embed=painel("⚔️ Ataques","Adicione, modifique ou remova ataques desta criatura."),view=GerenciarRegistrosCriaturaView(self.usuario_id,self.ficha,"ataque"));return
        await i.response.edit_message(
            embed=painel("⚔️ Ataque não mágico","Escolha um preset ou crie um ataque do zero."),
            view=EscolhaNomeItemView(self.usuario_id,self.ficha,"ataque",ATAQUES),
        )


class AtaqueModal(discord.ui.Modal):
    def __init__(self,usuario_id,ficha,nome,acao,rolagem,item=None):
        super().__init__(title="Detalhes do ataque não mágico");self.usuario_id=usuario_id;self.ficha=ficha;self.acao=acao;self.rolagem=rolagem;self.item=dict(item or {})
        self.nome=discord.ui.TextInput(label="Nome",default=self.item.get("nome", "" if nome=="Personalizado" else nome),max_length=100)
        self.dano=discord.ui.TextInput(label="Dano ou efeito",default=self.item.get("dano ou efeito",""),placeholder="Ex.: 1d6+Força ou descreva o efeito",style=discord.TextStyle.paragraph,max_length=1000)
        self.descricao=discord.ui.TextInput(label="Descrição mecânica",default=self.item.get("descrição",""),style=discord.TextStyle.paragraph,max_length=900)
        for x in (self.nome,self.dano,self.descricao):self.add_item(x)
    async def on_submit(self,i):
        dano_ou_efeito=somar_atributo_ao_dano(str(self.dano.value).strip(),self.ficha.atributos)
        item=dict(self.item);item.update({"nome":str(self.nome.value).strip(),"descrição":str(self.descricao.value).strip(),"tipo de ação":self.acao,"rolagem de ataque":self.rolagem,"dano ou efeito":dano_ou_efeito})
        await i.response.send_message(embed=painel("⚔️ Resistência ao ataque","O ataque é rolado pela criatura; o alvo usa Reflexo para esquivar ou Fortitude para defender. Escolha se houver um efeito secundário."),view=SequenciaItemView(self.usuario_id,self.ficha,item,"ataque",0),ephemeral=True)


class ConfiguracaoHabilidadeView(ViewCriatura):
    def __init__(self,usuario_id,ficha,ativacao="",acao="",item=None):
        super().__init__(usuario_id);self.ficha=ficha;self.ativacao=ativacao;self.acao=acao;self.item=dict(item or {})
        ativacao_select=discord.ui.Select(
            placeholder="Tipo de Ativação",
            options=[discord.SelectOption(label=valor,value=valor,description=descricao,default=valor==ativacao) for valor,descricao in ATIVACOES_HABILIDADE.items()],
            row=0,
        )
        acao_select=discord.ui.Select(
            placeholder="Tipo de Ação",
            options=[discord.SelectOption(label=valor,value=valor,description=DESCRICOES_ACOES_HABILIDADE[valor],default=valor==acao) for valor in ACOES_HABILIDADE],
            row=1,
        )
        ativacao_select.callback=self.selecionar_ativacao;acao_select.callback=self.selecionar_acao
        self.ativacao_select=ativacao_select;self.acao_select=acao_select;self.add_item(ativacao_select);self.add_item(acao_select)
        continuar=discord.ui.Button(label="Continuar",style=discord.ButtonStyle.primary,row=2);continuar.callback=self.continuar;self.add_item(continuar)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=2);voltar.callback=self.voltar;self.add_item(voltar)

    async def selecionar_ativacao(self,i):
        ativacao=self.ativacao_select.values[0]
        acao="Reação" if ativacao=="Reação" else ("" if self.acao=="Reação" else self.acao)
        await i.response.edit_message(view=ConfiguracaoHabilidadeView(self.usuario_id,self.ficha,ativacao,acao,self.item))
    async def selecionar_acao(self,i): await i.response.edit_message(view=ConfiguracaoHabilidadeView(self.usuario_id,self.ficha,self.ativacao,self.acao_select.values[0],self.item))
    async def continuar(self,i):
        if not self.ativacao or not self.acao:
            await i.response.send_message("Escolha o tipo de ativação e o tipo de ação.",ephemeral=True);return
        if self.ativacao=="Reação" and self.acao!="Reação":
            await i.response.send_message("Uma habilidade de reação deve usar o tipo de ação **Reação**.",ephemeral=True);return
        if self.ativacao=="Ativa" and self.acao=="Reação":
            await i.response.send_message("Use o tipo de ativação **Reação** para esse tipo de ação.",ephemeral=True);return
        item=dict(self.item);item["tipo de ativação"]=self.ativacao;item["tipo de ação"]=self.acao
        recarga=item.get("recarga","")
        if recarga==recarga_padrao(self.ficha.periculosidade):recarga="Padrão da periculosidade"
        await i.response.edit_message(
            embed=painel("✨ Alcance, Alvo, Duração e Recarga","Defina onde, quem, por quanto tempo e com que frequência a habilidade atua."),
            view=AlcanceHabilidadeView(
                self.usuario_id,self.ficha,item,item.get("alcance",""),item.get("alvo",""),
                duracao_registrada_base(item.get("duração","")),recarga,
            ),
        )
    async def voltar(self,i):
        limpar_contexto_edicao_habilidade(self.ficha)
        await i.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))


class AlcanceHabilidadeView(ViewCriatura):
    def __init__(self,usuario_id,ficha,item,alcance="",alvo="",duracao="",recarga=""):
        super().__init__(usuario_id);self.ficha=ficha;self.item=item;self.alcance=alcance;self.alvo=alvo;self.duracao=duracao;self.recarga=recarga
        seletores=[]
        alcance_dinamico=alcance_calculado(ficha)
        descricoes_alcance={**DESCRICOES_ALCANCES,alcance_dinamico:f"Alcança um alvo a até {formatar_medida_metros(raio_habilidade_metros(ficha))} m de distância."}
        for linha,(rotulo,valores,descricoes,atual) in enumerate((("Alcance",alcances_habilidade(ficha),descricoes_alcance,alcance),("Alvo",ALVOS,DESCRICOES_ALVOS,alvo),("Duração",DURACOES,{},duracao),("Recarga",RECARGAS,{},recarga))):
            descr=dict(descricoes)
            if rotulo=="Duração":
                descr={"Instantâneo":"O efeito termina imediatamente.","Turno":f"Dura {duracao_por_magia(ficha,'Turno')}.","Rodada":f"Dura {duracao_por_magia(ficha,'Rodada')}.","Sustentado":"Permanece enquanto a criatura mantiver a concentração."}
            elif rotulo=="Recarga":
                descr={"Padrão da periculosidade":f"Pode ser usada novamente após {recarga_padrao(ficha.periculosidade)}.","Sem recarga":"Pode ser usada novamente sem esperar rodadas.","Uma vez por combate":"Só pode ser usada uma vez em cada combate.","Uma vez por cena":"Só pode ser usada uma vez em cada cena.","Uma vez por dia":"Só pode ser usada uma vez por dia.","Personalizada":"A limitação de uso fica definida na descrição."}
            seletor=discord.ui.Select(placeholder=rotulo,options=[discord.SelectOption(label=v,value=v,description=descr.get(v),default=v==atual) for v in valores],row=linha)
            seletores.append(seletor);self.add_item(seletor)
        self.alcance_select,self.alvo_select,self.duracao_select,self.recarga_select=seletores
        self.alcance_select.callback=self.selecionar_alcance;self.alvo_select.callback=self.selecionar_alvo;self.duracao_select.callback=self.selecionar_duracao;self.recarga_select.callback=self.selecionar_recarga
        continuar=discord.ui.Button(label="Continuar",style=discord.ButtonStyle.primary,row=4);continuar.callback=self.continuar;self.add_item(continuar)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=4);voltar.callback=self.voltar;self.add_item(voltar)
    async def selecionar_alcance(self,i): await i.response.edit_message(view=AlcanceHabilidadeView(self.usuario_id,self.ficha,self.item,self.alcance_select.values[0],self.alvo,self.duracao,self.recarga))
    async def selecionar_alvo(self,i): await i.response.edit_message(view=AlcanceHabilidadeView(self.usuario_id,self.ficha,self.item,self.alcance,self.alvo_select.values[0],self.duracao,self.recarga))
    async def selecionar_duracao(self,i): await i.response.edit_message(view=AlcanceHabilidadeView(self.usuario_id,self.ficha,self.item,self.alcance,self.alvo,self.duracao_select.values[0],self.recarga))
    async def selecionar_recarga(self,i): await i.response.edit_message(view=AlcanceHabilidadeView(self.usuario_id,self.ficha,self.item,self.alcance,self.alvo,self.duracao,self.recarga_select.values[0]))
    async def continuar(self,i):
        if not self.alcance or not self.alvo or not self.duracao or not self.recarga:
            await i.response.send_message("Escolha o alcance, o alvo, a duração e a recarga.",ephemeral=True);return
        self.item["alcance"]=self.alcance;self.item["alvo"]=self.alvo;self.item["duração"]=duracao_por_magia(self.ficha,self.duracao)
        self.item["recarga"]=recarga_padrao(self.ficha.periculosidade) if self.recarga=="Padrão da periculosidade" else self.recarga
        if self.alvo=="Área":self.item["área"]=area_padrao(self.ficha)
        else:self.item.pop("área",None)
        if self.item.get("tipo de ativação")=="Passiva":
            self.item.pop("custo de Mana",None);self.item["custo de PH"]="0"
            aplicar_modo_custo(self.item,self.ficha,"Sem Custo")
            await i.response.edit_message(
                embed=painel("✨ Rolagens","Escolha as rolagens de acerto, resistência e reação."),
                view=RolagensHabilidadeView(
                    self.usuario_id,self.ficha,self.item,
                    escolha_registrada_base(self.item.get("rolagem de acerto","")),
                    self.item.get("rolagem de resistência",""),
                    self.item.get("rolagem de reação",""),
                ),
            )
            return
        await i.response.edit_message(
            embed=painel("✨ Modo de Custo e Custo de PH","Escolha como o custo é aplicado; o valor em PH só será solicitado quando necessário."),
            view=CustoHabilidadeView(
                self.usuario_id,self.ficha,self.item,
                self.item.get("custo de PH",self.item.get("custo de Mana","")),
                self.item.get("modo de custo",""),
            ),
        )
    async def voltar(self,i): await i.response.edit_message(embed=painel("✨ Configurar habilidade","Escolha o tipo de ativação e o tipo de ação."),view=ConfiguracaoHabilidadeView(self.usuario_id,self.ficha,self.item["tipo de ativação"],self.item["tipo de ação"],self.item))


class CustoHabilidadeView(ViewCriatura):
    def __init__(self,usuario_id,ficha,item,custo="",modo=""):
        super().__init__(usuario_id);self.ficha=ficha;self.item=item;self.custo=custo;self.modo=modo
        descricoes={"Ativação":"O custo é pago sempre que a habilidade é ativada.","Turno/Rodada Sustentada":"O custo é pago a cada turno ou rodada sustentada.","Acúmulo":f"Cada pagamento concede um acúmulo; limite de {1+ficha.nivel}.","Sem Custo":"A habilidade não consome PH e define o custo automaticamente como 0."}
        modo_select=discord.ui.Select(placeholder="Modo de Custo",options=[discord.SelectOption(label=v,value=v,description=descricoes[v],default=v==modo) for v in MODOS_CUSTO_HABILIDADE],row=0)
        modo_select.callback=self.selecionar_modo;self.modo_select=modo_select;self.add_item(modo_select)
        self.custo_select=None
        if modo and modo!="Sem Custo":
            custo_select=discord.ui.Select(placeholder="Custo de PH",options=[discord.SelectOption(label=f"{v} PH",value=v,description=d,default=v==custo) for v,d in CUSTOS_PH_HABILIDADE.items()],row=1)
            custo_select.callback=self.selecionar_custo;self.custo_select=custo_select;self.add_item(custo_select)
        continuar=discord.ui.Button(label="Continuar",style=discord.ButtonStyle.primary,row=2);continuar.callback=self.continuar;self.add_item(continuar)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=2);voltar.callback=self.voltar;self.add_item(voltar)
    async def selecionar_custo(self,i): await i.response.edit_message(view=CustoHabilidadeView(self.usuario_id,self.ficha,self.item,self.custo_select.values[0],self.modo))
    async def selecionar_modo(self,i):
        modo=self.modo_select.values[0]
        custo="0" if modo=="Sem Custo" else ("" if self.modo=="Sem Custo" else self.custo)
        await i.response.edit_message(view=CustoHabilidadeView(self.usuario_id,self.ficha,self.item,custo,modo))
    async def continuar(self,i):
        if not self.modo:
            await i.response.send_message("Escolha o modo de custo.",ephemeral=True);return
        if self.modo!="Sem Custo" and not self.custo:
            await i.response.send_message("Escolha o custo de PH.",ephemeral=True);return
        self.item.pop("custo de Mana", None);self.item["custo de PH"]="0" if self.modo=="Sem Custo" else self.custo;aplicar_modo_custo(self.item,self.ficha,self.modo)
        await i.response.edit_message(
            embed=painel("✨ Rolagens","Escolha as rolagens de acerto, resistência e reação."),
            view=RolagensHabilidadeView(
                self.usuario_id,self.ficha,self.item,
                escolha_registrada_base(self.item.get("rolagem de acerto","")),
                self.item.get("rolagem de resistência",""),
                self.item.get("rolagem de reação",""),
            ),
        )
    async def voltar(self,i):
        recarga=self.item.get("recarga","")
        if recarga==recarga_padrao(self.ficha.periculosidade):recarga="Padrão da periculosidade"
        await i.response.edit_message(embed=painel("✨ Alcance, Alvo, Duração e Recarga","Revise onde, quem, por quanto tempo e com que frequência a habilidade atua."),view=AlcanceHabilidadeView(self.usuario_id,self.ficha,self.item,self.item.get("alcance",""),self.item.get("alvo",""),duracao_registrada_base(self.item.get("duração","")),recarga))


class HabilidadeBasicaModal(discord.ui.Modal):
    def __init__(self,usuario_id,ficha,item):
        super().__init__(title="Criar habilidade");self.usuario_id=usuario_id;self.ficha=ficha;self.item=item
        self.nome=discord.ui.TextInput(label="Nome",default=item.get("nome",""),max_length=100)
        self.descricao=discord.ui.TextInput(label="Descrição",default=item.get("descrição",""),style=discord.TextStyle.paragraph,max_length=1500)
        self.efeito=discord.ui.TextInput(label="Efeito",default=item.get("efeito",resumo_efeito_habilidade(item)),style=discord.TextStyle.paragraph,max_length=1500)
        self.add_item(self.nome);self.add_item(self.descricao);self.add_item(self.efeito)
    async def on_submit(self,i):
        self.item["nome"]=str(self.nome.value).strip();self.item["descrição"]=str(self.descricao.value).strip();self.item["efeito"]=str(self.efeito.value).strip()
        try:
            registrar_habilidade_criatura(self.ficha,self.item)
        except ValueError as erro:
            await i.response.send_message(
                str(erro),
                ephemeral=True,
            )
            return
        await i.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))


class TipoEfeitoHabilidadeView(ViewCriatura):
    def __init__(self,usuario_id,ficha,item,tipo="",necessita_rolagem="",tipo_dano=""):
        super().__init__(usuario_id);self.ficha=ficha;self.item=item;self.tipo=tipo;self.necessita_rolagem=necessita_rolagem;self.tipo_dano=tipo_dano
        tipo_select=discord.ui.Select(placeholder="Tipo de Efeito",options=[discord.SelectOption(label=v,value=v,description=d[:100],default=v==tipo) for v,d in TIPOS_EFEITO_HABILIDADE.items()],row=0)
        rolagem_select=discord.ui.Select(placeholder="Necessita de Rolagem",options=[discord.SelectOption(label=v,value=v,description="Abre a configuração dos dados do efeito." if v=="Sim" else "Pula e descarta os dados de rolagem do efeito.",default=v==necessita_rolagem) for v in NECESSITA_ROLAGEM_EFEITO],row=1)
        dano_select=discord.ui.Select(placeholder="Tipo de Dano",options=[discord.SelectOption(label=v,value=v,description=DESCRICOES_TIPOS_DANO_HABILIDADE[v][:100],default=v==tipo_dano) for v in TIPOS_DANO_HABILIDADE],row=2)
        tipo_select.callback=self.selecionar_tipo;rolagem_select.callback=self.selecionar_rolagem;dano_select.callback=self.selecionar_dano
        self.tipo_select=tipo_select;self.rolagem_select=rolagem_select;self.dano_select=dano_select
        self.add_item(tipo_select);self.add_item(rolagem_select);self.add_item(dano_select)
        continuar=discord.ui.Button(label="Continuar",style=discord.ButtonStyle.primary,row=3);continuar.callback=self.continuar;self.add_item(continuar)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=3);voltar.callback=self.voltar;self.add_item(voltar)
    async def selecionar_tipo(self,i):await i.response.edit_message(view=TipoEfeitoHabilidadeView(self.usuario_id,self.ficha,self.item,self.tipo_select.values[0],self.necessita_rolagem,self.tipo_dano))
    async def selecionar_rolagem(self,i):await i.response.edit_message(view=TipoEfeitoHabilidadeView(self.usuario_id,self.ficha,self.item,self.tipo,self.rolagem_select.values[0],self.tipo_dano))
    async def selecionar_dano(self,i):await i.response.edit_message(view=TipoEfeitoHabilidadeView(self.usuario_id,self.ficha,self.item,self.tipo,self.necessita_rolagem,self.dano_select.values[0]))
    async def continuar(self,i):
        if not self.tipo or not self.necessita_rolagem or not self.tipo_dano:
            await i.response.send_message("Escolha o tipo de efeito, o tipo de dano e se ele necessita de rolagem.",ephemeral=True);return
        configurar_tipo_efeito(self.item,self.tipo,self.necessita_rolagem,self.tipo_dano)
        if self.necessita_rolagem=="Não":
            await i.response.send_modal(HabilidadeBasicaModal(self.usuario_id,self.ficha,self.item));return
        await i.response.edit_message(
            embed=painel("✨ Efeito da Habilidade","Escolha o dado, o número de dados e o modificador do efeito."),
            view=EfeitoHabilidadeView(
                self.usuario_id,self.ficha,self.item,
                self.item.get("dado de efeito",""),
                self.item.get("número de dados",""),
                escolha_registrada_base(self.item.get("modificador de efeito","")),
            ),
        )
    async def voltar(self,i):await i.response.edit_message(embed=painel("✨ Rolagens","Revise as rolagens da habilidade."),view=RolagensHabilidadeView(self.usuario_id,self.ficha,self.item,escolha_registrada_base(self.item.get("rolagem de acerto","")),self.item.get("rolagem de resistência",""),self.item.get("rolagem de reação","")))


class RolagensHabilidadeView(ViewCriatura):
    def __init__(self,usuario_id,ficha,item,acerto="",resistencia="",reacao=""):
        super().__init__(usuario_id);self.ficha=ficha;self.item=item;self.acerto=acerto;self.resistencia=resistencia;self.reacao=reacao
        acerto_select=discord.ui.Select(
            placeholder=f"Rolagem de Acerto{f': {acerto}' if acerto and acerto!='Magia' else ''}",
            options=[discord.SelectOption(label=v,value=v,description=(f"Usa Magia {formatar_bonus(modificador(ficha.atributos['Magia']))}." if v=="Magia" else "Abre as perícias organizadas por atributos."),default=v==acerto) for v in CATEGORIAS_ROLAGEM_ACERTO],
            row=0,
        )
        resistencia_select=discord.ui.Select(placeholder="Rolagem de Resistência",options=opcoes(RESISTENCIAS,{"Reflexo":"Para esquivar ou escapar de restrições.","Fortitude":"Para defender ou resistir a impactos físicos.","Vontade":"Para resistir a efeitos mentais e de controle.","Nenhuma":"O efeito não permite teste de resistência."}),row=1)
        reacao_descr={"Teste Oposto":"Compara a rolagem da criatura com a reação do alvo.","Efeito Mágico Direto":f"O alvo reage contra CD {cd_magica(ficha)}.","Automática":"O efeito acontece automaticamente quando ativado.","Pessoal":"A habilidade afeta o próprio usuário sem oposição."}
        reacao_select=discord.ui.Select(placeholder="Rolagem de Reação",options=[discord.SelectOption(label=v,value=v,description=reacao_descr[v],default=v==reacao) for v in RESOLUCOES],row=2)
        for opcao in resistencia_select.options:opcao.default=opcao.value==resistencia
        acerto_select.callback=self.selecionar_acerto;resistencia_select.callback=self.selecionar_resistencia;reacao_select.callback=self.selecionar_reacao
        self.acerto_select=acerto_select;self.resistencia_select=resistencia_select;self.reacao_select=reacao_select
        self.add_item(acerto_select);self.add_item(resistencia_select);self.add_item(reacao_select)
        continuar=discord.ui.Button(label="Continuar",style=discord.ButtonStyle.primary,row=3);continuar.callback=self.continuar;self.add_item(continuar)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=3);voltar.callback=self.voltar;self.add_item(voltar)
    async def selecionar_acerto(self,i):
        valor=self.acerto_select.values[0]
        if valor=="Perícia":
            estado={"resistencia":self.resistencia,"reacao":self.reacao}
            await i.response.edit_message(embed=painel("🎯 Rolagem de Acerto","Escolha a perícia usada para acertar."),view=EscolhaPericiaNovaHabilidadeView(self.usuario_id,self.ficha,self.item,"acerto",estado));return
        await i.response.edit_message(view=RolagensHabilidadeView(self.usuario_id,self.ficha,self.item,valor,self.resistencia,self.reacao))
    async def selecionar_resistencia(self,i): await i.response.edit_message(view=RolagensHabilidadeView(self.usuario_id,self.ficha,self.item,self.acerto,self.resistencia_select.values[0],self.reacao))
    async def selecionar_reacao(self,i): await i.response.edit_message(view=RolagensHabilidadeView(self.usuario_id,self.ficha,self.item,self.acerto,self.resistencia,self.reacao_select.values[0]))
    async def continuar(self,i):
        if not self.acerto or not self.resistencia or not self.reacao:
            await i.response.send_message("Escolha as três rolagens.",ephemeral=True);return
        self.item["rolagem de acerto"]=escolha_com_bonus(self.ficha,self.acerto)
        self.item["rolagem de resistência"]=self.resistencia;self.item["rolagem de reação"]=self.reacao
        if self.reacao=="Efeito Mágico Direto":self.item["CD mágica"]=str(cd_magica(self.ficha))
        else:self.item.pop("CD mágica",None)
        await i.response.edit_message(embed=painel("✨ Tipo de Efeito","Classifique o efeito, escolha o tipo de dano e informe se ele necessita de uma rolagem própria."),view=TipoEfeitoHabilidadeView(self.usuario_id,self.ficha,self.item,self.item.get("tipo de efeito",""),self.item.get("necessita de rolagem",""),self.item.get("tipo de dano","Nenhum")))
    async def voltar(self,i):
        if self.item.get("tipo de ativação")=="Passiva":
            recarga=self.item.get("recarga","")
            if recarga==recarga_padrao(self.ficha.periculosidade):recarga="Padrão da periculosidade"
            await i.response.edit_message(embed=painel("✨ Alcance, Alvo, Duração e Recarga","Revise onde, quem, por quanto tempo e com que frequência a habilidade atua."),view=AlcanceHabilidadeView(self.usuario_id,self.ficha,self.item,self.item.get("alcance",""),self.item.get("alvo",""),duracao_registrada_base(self.item.get("duração","")),recarga))
            return
        await i.response.edit_message(embed=painel("✨ Modo de Custo e Custo de PH","Revise o modo e o custo da habilidade."),view=CustoHabilidadeView(self.usuario_id,self.ficha,self.item,self.item.get("custo de PH",self.item.get("custo de Mana","")),self.item.get("modo de custo","")))


class EscolhaPericiaNovaHabilidadeView(ViewCriatura):
    def __init__(self,usuario_id,ficha,item,contexto,estado,pagina=0):
        super().__init__(usuario_id);self.ficha=ficha;self.item=item;self.contexto=contexto;self.estado=estado;self.paginas=paginas_pericias();self.pagina=max(0,min(pagina,len(self.paginas)-1))
        rotulo,valores=self.paginas[self.pagina]
        seletor=discord.ui.Select(placeholder=f"Perícias — {rotulo}",options=[discord.SelectOption(label=v,value=v,description=f"Bônus atual: {formatar_bonus(bonus_escolha_criatura(ficha,v))}") for v in valores],row=0)
        seletor.callback=self.selecionar;self.seletor=seletor;self.add_item(seletor)
        anterior=discord.ui.Button(label="Anterior",style=discord.ButtonStyle.secondary,disabled=self.pagina==0,row=1);anterior.callback=self.anterior;self.add_item(anterior)
        proxima=discord.ui.Button(label="Próxima",style=discord.ButtonStyle.secondary,disabled=self.pagina==len(self.paginas)-1,row=1);proxima.callback=self.proxima;self.add_item(proxima)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=1);voltar.callback=self.voltar;self.add_item(voltar)
    def nova(self,pagina):return EscolhaPericiaNovaHabilidadeView(self.usuario_id,self.ficha,self.item,self.contexto,self.estado,pagina)
    async def selecionar(self,i):
        valor=self.seletor.values[0]
        if self.contexto=="acerto":view=RolagensHabilidadeView(self.usuario_id,self.ficha,self.item,valor,self.estado.get("resistencia",""),self.estado.get("reacao",""))
        else:view=EfeitoHabilidadeView(self.usuario_id,self.ficha,self.item,self.estado.get("dado",""),self.estado.get("numero",""),valor)
        await i.response.edit_message(embed=painel("✨ Configurar habilidade","Continue preenchendo os campos."),view=view)
    async def anterior(self,i):await i.response.edit_message(view=self.nova(self.pagina-1))
    async def proxima(self,i):await i.response.edit_message(view=self.nova(self.pagina+1))
    async def voltar(self,i):
        view=RolagensHabilidadeView(self.usuario_id,self.ficha,self.item,"",self.estado.get("resistencia",""),self.estado.get("reacao","")) if self.contexto=="acerto" else EfeitoHabilidadeView(self.usuario_id,self.ficha,self.item,self.estado.get("dado",""),self.estado.get("numero",""),"")
        await i.response.edit_message(embed=painel("✨ Configurar habilidade","Escolha novamente a categoria."),view=view)


class EscolhaAtributoNovoEfeitoView(ViewCriatura):
    def __init__(self,usuario_id,ficha,item,dado,numero):
        super().__init__(usuario_id);self.ficha=ficha;self.item=item;self.dado=dado;self.numero=numero
        seletor=discord.ui.Select(placeholder="Modificador de Efeito",options=[discord.SelectOption(label=v,value=v,description=f"Modificador atual: {formatar_bonus(modificador(ficha.atributos[v]))}") for v in ATRIBUTOS_CRIATURA])
        seletor.callback=self.selecionar;self.seletor=seletor;self.add_item(seletor)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=1);voltar.callback=self.voltar;self.add_item(voltar)
    async def selecionar(self,i):await i.response.edit_message(embed=painel("✨ Efeito da Habilidade","Revise os dados do efeito."),view=EfeitoHabilidadeView(self.usuario_id,self.ficha,self.item,self.dado,self.numero,self.seletor.values[0]))
    async def voltar(self,i):await i.response.edit_message(embed=painel("✨ Efeito da Habilidade","Escolha novamente a categoria do modificador."),view=EfeitoHabilidadeView(self.usuario_id,self.ficha,self.item,self.dado,self.numero,""))


class ModificadorPersonalizadoModal(discord.ui.Modal):
    def __init__(self,usuario_id,ficha,item,dado="",numero="",tipo="",etapa=-1):
        super().__init__(title="Modificador personalizado")
        self.usuario_id=usuario_id;self.ficha=ficha;self.item=item;self.dado=dado;self.numero=numero;self.tipo=tipo;self.etapa=etapa
        atual=item.get("modificador de efeito","")
        if atual.startswith("Personalizado "):atual=atual.removeprefix("Personalizado ")
        else:atual=""
        self.valor=discord.ui.TextInput(
            label="Valor somativo puro",
            placeholder="Ex.: +2, 5 ou -3",
            default=atual or None,
            min_length=1,
            max_length=8,
        )
        self.add_item(self.valor)

    async def on_submit(self,i):
        try:bonus=interpretar_modificador_personalizado(str(self.valor.value))
        except ValueError as erro:
            await i.response.send_message(str(erro),ephemeral=True);return
        escolha=f"Personalizado {formatar_bonus(bonus)}"
        if self.etapa>=0:
            sequencia=SequenciaItemView(self.usuario_id,self.ficha,self.item,self.tipo,self.etapa)
            await sequencia.registrar_e_avancar(i,escolha);return
        await i.response.edit_message(
            embed=painel("✨ Efeito da Habilidade",f"O valor {formatar_bonus(bonus)} será somado diretamente à rolagem de efeito."),
            view=EfeitoHabilidadeView(self.usuario_id,self.ficha,self.item,self.dado,self.numero,escolha),
        )


class EfeitoHabilidadeView(ViewCriatura):
    def __init__(self,usuario_id,ficha,item,dado="",numero="",modificador_efeito=""):
        super().__init__(usuario_id);self.ficha=ficha;self.item=item;self.dado=dado;self.numero=numero;self.modificador_efeito=modificador_efeito
        dado_select=discord.ui.Select(placeholder="Dado de Efeito",options=[discord.SelectOption(label=v,value=v,description=f"Usa {v} como dado-base.",default=v==dado) for v in DADOS_EFEITO],row=0)
        numeros=tuple(str(n) for n in range(1,2*ficha.nivel+1));numero_select=discord.ui.Select(placeholder="Número de Dados",options=[discord.SelectOption(label=v,value=v,description=f"Rola {v} dado(s); limite: {2*ficha.nivel}.",default=v==numero) for v in numeros],row=1)
        modificador_select=discord.ui.Select(placeholder=f"Modificador de Efeito{f': {modificador_efeito}' if modificador_efeito not in {'','Nulo'} else ''}",options=opcoes(CATEGORIAS_MODIFICADOR_EFEITO,{"Nulo":"Não soma modificador ao efeito.","Modificador":"Abre os modificadores dos atributos.","Perícia":"Abre as perícias organizadas por atributos.","Personalizado":"Informe um valor numérico somado diretamente ao efeito."}),row=2)
        for opcao in modificador_select.options:opcao.default=opcao.value==modificador_efeito
        dado_select.callback=self.selecionar_dado;numero_select.callback=self.selecionar_numero;modificador_select.callback=self.selecionar_modificador
        self.dado_select=dado_select;self.numero_select=numero_select;self.modificador_select=modificador_select;self.add_item(dado_select);self.add_item(numero_select);self.add_item(modificador_select)
        concluir=discord.ui.Button(label="Continuar",style=discord.ButtonStyle.primary,row=3);concluir.callback=self.concluir;self.add_item(concluir)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=3);voltar.callback=self.voltar;self.add_item(voltar)
    async def selecionar_dado(self,i):await i.response.edit_message(view=EfeitoHabilidadeView(self.usuario_id,self.ficha,self.item,self.dado_select.values[0],self.numero,self.modificador_efeito))
    async def selecionar_numero(self,i):await i.response.edit_message(view=EfeitoHabilidadeView(self.usuario_id,self.ficha,self.item,self.dado,self.numero_select.values[0],self.modificador_efeito))
    async def selecionar_modificador(self,i):
        valor=self.modificador_select.values[0]
        if valor=="Perícia":
            await i.response.edit_message(embed=painel("🎲 Modificador de Efeito","Escolha a perícia somada ao efeito."),view=EscolhaPericiaNovaHabilidadeView(self.usuario_id,self.ficha,self.item,"efeito",{"dado":self.dado,"numero":self.numero}));return
        if valor=="Modificador":
            await i.response.edit_message(embed=painel("🎲 Modificador de Efeito","Escolha o atributo somado ao efeito."),view=EscolhaAtributoNovoEfeitoView(self.usuario_id,self.ficha,self.item,self.dado,self.numero));return
        if valor=="Personalizado":
            await i.response.send_modal(ModificadorPersonalizadoModal(self.usuario_id,self.ficha,self.item,self.dado,self.numero));return
        await i.response.edit_message(view=EfeitoHabilidadeView(self.usuario_id,self.ficha,self.item,self.dado,self.numero,valor))
    async def concluir(self,i):
        if not self.dado or not self.numero or not self.modificador_efeito:
            await i.response.send_message("Escolha o dado, o número de dados e o modificador de efeito.",ephemeral=True);return
        self.item["dado de efeito"]=self.dado;self.item["número de dados"]=self.numero
        try: atualizar_efeito_calculado(self.item,self.ficha,self.modificador_efeito)
        except ValueError as erro:
            await i.response.send_message(str(erro),ephemeral=True);return
        await i.response.send_modal(HabilidadeBasicaModal(self.usuario_id,self.ficha,self.item))
    async def voltar(self,i):await i.response.edit_message(embed=painel("✨ Tipo de Efeito","Revise a classificação, o tipo de dano e a necessidade de rolagem."),view=TipoEfeitoHabilidadeView(self.usuario_id,self.ficha,self.item,self.item.get("tipo de efeito",""),self.item.get("necessita de rolagem",""),self.item.get("tipo de dano","Nenhum")))


class EscolhaPericiaHabilidadeView(ViewCriatura):
    def __init__(self,usuario_id,ficha,item,tipo,etapa,finalidade,pagina=0):
        super().__init__(usuario_id);self.ficha=ficha;self.item=item;self.tipo=tipo;self.etapa=etapa;self.finalidade=finalidade
        self.paginas=paginas_pericias();self.pagina=max(0,min(pagina,len(self.paginas)-1))
        rotulo,valores=self.paginas[self.pagina]
        seletor=discord.ui.Select(
            placeholder=f"Perícias — {rotulo}",
            options=[
                discord.SelectOption(label=nome,value=nome,description=f"Bônus atual: {formatar_bonus(bonus_escolha_criatura(ficha,nome))}")
                for nome in valores
            ],
            row=0,
        )
        seletor.callback=self.selecionar;self.seletor=seletor;self.add_item(seletor)
        anterior=discord.ui.Button(label="Anterior",style=discord.ButtonStyle.secondary,disabled=self.pagina==0,row=1);anterior.callback=self.anterior;self.add_item(anterior)
        proxima=discord.ui.Button(label="Próxima",style=discord.ButtonStyle.secondary,disabled=self.pagina==len(self.paginas)-1,row=1);proxima.callback=self.proxima;self.add_item(proxima)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=1);voltar.callback=self.voltar;self.add_item(voltar)

    async def selecionar(self,i):
        sequencia=SequenciaItemView(self.usuario_id,self.ficha,self.item,self.tipo,self.etapa)
        await sequencia.registrar_e_avancar(i,self.seletor.values[0])
    async def anterior(self,i): await i.response.edit_message(view=EscolhaPericiaHabilidadeView(self.usuario_id,self.ficha,self.item,self.tipo,self.etapa,self.finalidade,self.pagina-1))
    async def proxima(self,i): await i.response.edit_message(view=EscolhaPericiaHabilidadeView(self.usuario_id,self.ficha,self.item,self.tipo,self.etapa,self.finalidade,self.pagina+1))
    async def voltar(self,i): await i.response.edit_message(embed=painel("⚙️ Configuração",f"**{self.item['nome']}**\nEscolha novamente a categoria de {self.finalidade}."),view=SequenciaItemView(self.usuario_id,self.ficha,self.item,self.tipo,self.etapa))


class EscolhaAtributoEfeitoView(ViewCriatura):
    def __init__(self,usuario_id,ficha,item,tipo,etapa):
        super().__init__(usuario_id);self.ficha=ficha;self.item=item;self.tipo=tipo;self.etapa=etapa
        seletor=discord.ui.Select(
            placeholder="Modificador de atributo",
            options=[
                discord.SelectOption(label=nome,value=nome,description=f"Modificador atual: {formatar_bonus(modificador(ficha.atributos[nome]))}")
                for nome in ATRIBUTOS_CRIATURA
            ],
        )
        seletor.callback=self.selecionar;self.seletor=seletor;self.add_item(seletor)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=1);voltar.callback=self.voltar;self.add_item(voltar)

    async def selecionar(self,i):
        sequencia=SequenciaItemView(self.usuario_id,self.ficha,self.item,self.tipo,self.etapa)
        await sequencia.registrar_e_avancar(i,self.seletor.values[0])
    async def voltar(self,i): await i.response.edit_message(embed=painel("⚙️ Configuração",f"**{self.item['nome']}**\nEscolha novamente a categoria do modificador."),view=SequenciaItemView(self.usuario_id,self.ficha,self.item,self.tipo,self.etapa))


class SequenciaItemView(ViewCriatura):
    def __init__(self,usuario_id,ficha,item,tipo,etapa):
        super().__init__(usuario_id);self.ficha=ficha;self.item=item;self.tipo=tipo;self.etapa=etapa
        if tipo=="ataque":
            etapas=[("teste de resistência",RESISTENCIAS),("duração",DURACOES),("recarga",RECARGAS)]
        else:
            etapas=[("modo do custo",("Por ativação","Por rodada sustentada","Por acúmulo","Sem custo")),("alcance",ALCANCES),("alvo",ALVOS),("rolagem de acerto",CATEGORIAS_ROLAGEM_ACERTO),("tipo de dano",TIPOS_DANO_HABILIDADE),("dado de efeito",DADOS_EFEITO),("número de dados",tuple(str(numero) for numero in range(1,2*ficha.nivel+1))),("modificador de efeito",CATEGORIAS_MODIFICADOR_EFEITO),("resolução",RESOLUCOES),("resistência",RESISTENCIAS),("duração",DURACOES),("recarga",RECARGAS)]
            if item.get("tipo de ativação")=="Passiva": etapas=[e for e in etapas if e[0] not in {"modo do custo","resistência","recarga"}]
        self.etapas=etapas
        nome,valores=etapas[etapa]
        descr={
            "Reflexo":"Para esquivar ou escapar de efeitos que restringem movimento.","Fortitude":"Para defender ou resistir a impactos e efeitos físicos.","Vontade":"Para resistir a efeitos mentais e de controle.",
            "Ataque oposto":"A criatura ataca; o alvo esquiva com Reflexo ou defende com Fortitude.","Efeito mágico direto":f"O alvo testa contra CD {cd_magica(ficha)}.",
            "Por acúmulo":f"Limite de {1+ficha.nivel} acúmulos; todos começam e terminam juntos.","Padrão da periculosidade":f"{recarga_padrao(ficha.periculosidade)}.",
            "Instantâneo":"O efeito acontece e termina imediatamente.",
            "Turno":f"Dura {duracao_por_magia(ficha,'Turno')}: 1 + modificador de Magia.",
            "Rodada":f"Dura {duracao_por_magia(ficha,'Rodada')}: 1 + modificador de Magia.",
            "Magia":f"Usa o modificador de Magia: {formatar_bonus(modificador(ficha.atributos['Magia']))}.",
            "Perícia":"Abre as perícias organizadas pelos atributos relacionados.",
            "Nulo":"Nenhum modificador será somado ao efeito.",
            "Modificador":"Escolha um atributo; o modificador dele será somado ao efeito.",
            "Personalizado":"Informe um valor numérico somado diretamente ao efeito.",
            **{dado:f"Usa {dado} como dado-base do efeito." for dado in DADOS_EFEITO},
            **{str(numero):f"Rola {numero} dado(s); limite desta criatura: {2*ficha.nivel}." for numero in range(1,2*ficha.nivel+1)},
            **DESCRICOES_ALCANCES,
            **DESCRICOES_ALVOS,
            **DESCRICOES_TIPOS_DANO_HABILIDADE,
        }
        s=discord.ui.Select(placeholder=f"Escolha: {nome}",options=opcoes(valores,descr));s.callback=self.selecionar;self.s=s;self.nome_etapa=nome;self.add_item(s)

    async def selecionar(self,i):
        valor=self.s.values[0]
        if self.nome_etapa=="rolagem de acerto" and valor=="Perícia":
            await i.response.edit_message(embed=painel("🎯 Rolagem de Acerto","Escolha a perícia usada para acertar."),view=EscolhaPericiaHabilidadeView(self.usuario_id,self.ficha,self.item,self.tipo,self.etapa,"Rolagem de Acerto"));return
        if self.nome_etapa=="modificador de efeito" and valor=="Perícia":
            await i.response.edit_message(embed=painel("🎲 Modificador de Efeito","Escolha a perícia somada ao efeito."),view=EscolhaPericiaHabilidadeView(self.usuario_id,self.ficha,self.item,self.tipo,self.etapa,"Modificador de Efeito"));return
        if self.nome_etapa=="modificador de efeito" and valor=="Modificador":
            await i.response.edit_message(embed=painel("🎲 Modificador de Efeito","Escolha o atributo cujo modificador será somado ao efeito."),view=EscolhaAtributoEfeitoView(self.usuario_id,self.ficha,self.item,self.tipo,self.etapa));return
        if self.nome_etapa=="modificador de efeito" and valor=="Personalizado":
            await i.response.send_modal(ModificadorPersonalizadoModal(self.usuario_id,self.ficha,self.item,tipo=self.tipo,etapa=self.etapa));return
        await self.registrar_e_avancar(i,valor)

    async def registrar_e_avancar(self,i,valor):
        if self.nome_etapa=="recarga" and valor=="Padrão da periculosidade": valor=recarga_padrao(self.ficha.periculosidade)
        if self.nome_etapa=="duração": valor=duracao_por_magia(self.ficha,valor)
        if self.nome_etapa=="rolagem de acerto": self.item[self.nome_etapa]=escolha_com_bonus(self.ficha,valor)
        elif self.nome_etapa=="modificador de efeito": atualizar_efeito_calculado(self.item,self.ficha,valor)
        else:self.item[self.nome_etapa]=valor
        if self.nome_etapa=="modo do custo":
            custo=self.item.get("custo de PH",self.item.get("custo de Mana","0"))
            if valor=="Por ativação": self.item["mecânica de custo"]=f"Custa {custo} PH por ativação."
            elif valor=="Por rodada sustentada": self.item["mecânica de custo"]=f"Custa {custo} PH por rodada sustentada e termina se perder a concentração."
            elif valor=="Por acúmulo": self.item["mecânica de custo"]=f"A cada {custo} PH, recebe um acúmulo do mesmo efeito. Limite de {1+self.ficha.nivel} acúmulos; todos começam e terminam juntos."
            else:self.item["mecânica de custo"]="Sem custo de PH."
        if self.nome_etapa=="resolução" and valor=="Efeito mágico direto": self.item["CD mágica"]=str(cd_magica(self.ficha))
        if self.nome_etapa=="alvo" and valor=="Área": self.item["área"]=area_padrao(self.ficha)
        proxima=self.etapa+1
        if proxima<len(self.etapas):
            await i.response.edit_message(embed=painel("⚙️ Configuração",f"**{self.item['nome']}**\nEtapa {proxima+1}/{len(self.etapas)}."),view=SequenciaItemView(self.usuario_id,self.ficha,self.item,self.tipo,proxima));return
        if self.tipo=="ataque":registrar_item_criatura(self.ficha,"ataque",self.item)
        else:self.ficha.habilidades.append(self.item)
        await i.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))


class CategoriaEfeitoView(ViewCriatura):
    def __init__(self,usuario_id,ficha,fraqueza):
        super().__init__(usuario_id);self.ficha=ficha;self.fraqueza=fraqueza
        s=discord.ui.Select(placeholder="Categoria",options=opcoes(CATEGORIAS_EFEITO,DESCRICOES_CATEGORIAS_EFEITO));s.callback=self.sel;self.s=s;self.add_item(s)
        v=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=1);v.callback=self.voltar;self.add_item(v)
    async def sel(self,i):
        orientacao = "Escolha como esta categoria aumenta o dano sofrido ou dificulta testes de resistência." if self.fraqueza else "Escolha como esta categoria reduz o dano sofrido, facilita testes ou concede imunidade."
        await i.response.edit_message(embed=painel("Aplicação",orientacao),view=TipoEfeitoView(self.usuario_id,self.ficha,self.fraqueza,self.s.values[0]))
    async def voltar(self,i): await i.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))


class TipoEfeitoView(ViewCriatura):
    def __init__(self,usuario_id,ficha,fraqueza,categoria):
        super().__init__(usuario_id);self.ficha=ficha;self.fraqueza=fraqueza;self.categoria=categoria
        tipos = TIPOS_FRAQUEZA if fraqueza else TIPOS_RESISTENCIA
        s=discord.ui.Select(placeholder="Escolha a aplicação",options=opcoes(tuple(tipos),tipos));s.callback=self.sel;self.s=s;self.add_item(s)
    async def sel(self,i):
        tipo=self.s.values[0]
        if tipo in {"Aumento de Dano Sofrido","Redução de Dano Sofrido"}: efeito=efeito_dano(self.ficha.periculosidade,self.fraqueza)
        elif tipo=="Imunidade a efeito": efeito="É completamente imune ao efeito e não realiza teste."
        else: efeito=efeito_condicao(self.fraqueza)
        destino=self.ficha.fraquezas if self.fraqueza else self.ficha.resistencias
        destino.append({"categoria":self.categoria,"tipo":tipo,"efeito":efeito})
        await i.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))


class ConfirmarCriaturaView(ViewCriatura):
    def __init__(self,usuario_id,ficha):
        super().__init__(usuario_id);self.ficha=ficha;self.concluido=False
        if getattr(ficha,"_caminho_edicao",None) is not None:
            self.concluir.label="Salvar alterações"
    @discord.ui.button(label="Concluir ficha",style=discord.ButtonStyle.success,emoji="✅")
    async def concluir(self,i,_):
        if self.concluido: await i.response.send_message("Esta operação já foi encerrada.",ephemeral=True);return
        caminho_edicao=getattr(self.ficha,"_caminho_edicao",None)
        try:
            if caminho_edicao is None:
                caminho=caminho_nova_ficha_criatura(self.ficha.periculosidade,self.ficha.nome)
                if caminho.exists(): raise ValueError("Já existe uma ficha de criatura com esse nome nessa periculosidade.")
                validar_ficha(self.ficha);salvar_ficha_criatura(self.ficha,caminho,nova=True)
            else:
                caminho=Path(caminho_edicao).resolve()
                lock=LOCKS_CRIATURA.setdefault(caminho,asyncio.Lock())
                async with lock:
                    if not caminho.is_file():
                        raise ValueError("A ficha original não existe mais.")
                    original=getattr(self.ficha,"_conteudo_original_edicao",None)
                    if original is None or caminho.read_text(encoding="utf-8-sig") != original:
                        raise ValueError("A ficha foi alterada durante esta edição. Consulte-a novamente para evitar sobrescrever mudanças.")
                    validar_ficha(self.ficha);salvar_ficha_criatura(self.ficha,caminho)
                    self.ficha._conteudo_original_edicao=caminho.read_text(encoding="utf-8-sig")
        except (OSError,ValueError) as erro: await i.response.send_message(f"Não foi possível salvar: {erro}",ephemeral=True);return
        self.concluido=True;self.stop()
        view=EditorCriaturaView(self.usuario_id,self.ficha) if caminho_edicao is not None else None
        await i.response.edit_message(embeds=montar_embeds_criatura(self.ficha),view=view)
        await sincronizar_publicacao_criatura(i,self.ficha,caminho)
    @discord.ui.button(label="Voltar à edição",style=discord.ButtonStyle.secondary)
    async def voltar(self,i,_): await i.response.edit_message(embed=embed_editor(self.ficha),view=EditorCriaturaView(self.usuario_id,self.ficha))
    @discord.ui.button(label="Cancelar",style=discord.ButtonStyle.danger,emoji="🗑️")
    async def cancelar(self,i,_):
        self.stop()
        editando=getattr(self.ficha,"_caminho_edicao",None) is not None
        titulo="Edição cancelada" if editando else "Criação cancelada"
        await i.response.edit_message(embed=painel(titulo,"Nenhuma alteração foi salva." if editando else "Nenhuma ficha foi salva."),view=None)


async def iniciar_criacao(interaction):
    await interaction.response.send_message(embed=painel("🐾 Criar ficha de criatura","Escolha uma espécie da biblioteca ou crie uma criatura que ainda não existe no RPG."),view=FonteCriaturaView(interaction.user.id),ephemeral=True)


async def consultar(interaction):
    await interaction.response.send_message(
        embed=painel(
            "🔎 Consultar criatura",
            "Escolha primeiro a periculosidade da ficha.",
        ),
        view=ConsultaPericulosidadeCriaturaView(interaction.user.id),
        ephemeral=True,
    )
