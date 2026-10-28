from __future__ import annotations

import asyncio
import re
import secrets
from functools import lru_cache
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from comandos.habilidades import (
    CATEGORIAS_HABILIDADE,
    carregar_habilidade,
    custo_xp_habilidade,
    listar_habilidades,
)
from comandos.preparar import interpretar_pocao
from comandos import ficha_criaturas
from utils.biblioteca import BibliotecaCategoria, interpretar_markdown, normalizar_rotulo
from utils.efeitos_habilidades import (
    aptidao_efetiva,
    bonus_aptidoes_passivos,
    bonus_pericias_passivos,
    custo_heranca_com_alquimia,
    desconto_aptidao,
    desconto_nivel,
    heranca_desbloqueada,
    possui,
    resumo_automaticos,
    resumo_condicionais,
)
from utils.fichas import (
    APTIDOES,
    ATRIBUTOS,
    ATRIBUTOS_POR_PERICIA,
    EMOJIS_PASTAS_FICHA,
    GRUPOS_ALFABETICOS_FICHAS,
    GRUPOS_FICHA,
    ORDEM_PASTAS_FICHA,
    PERICIAS,
    REDUCOES_DIFICULDADE,
    SIGLAS_ATRIBUTOS,
    FichaPersonagem,
    bonus_pericia,
    atributos_efetivos,
    caminho_nova_ficha,
    dados_nucleo,
    encontrar_ficha,
    formatar_bonus,
    listar_casas,
    listar_fichas,
    listar_nucleos,
    modificador,
    informacao_obrigatoria,
    nome_com_estado_pv,
    paginas_fichas_alfabeticas,
    paginas_pericias,
    pericias_da_casa,
    resumo_bonus_nucleo,
    salvar_ficha,
    sangue_puro_desbloqueado,
    sincronizar_campos_base,
)
from utils.fichas_criaturas import normalizar_tamanho, tamanho_em_metros
from utils.inventario import montar_embed_itens
from utils.publicacao_fichas import (
    ErroPublicacaoFicha,
    cabecalho_personagem,
    cabecalho_personagem_parte_2,
    destino_personagem,
    excede_limite_mensagem,
    excluir_publicacao_ficha,
    publicar_ou_atualizar_ficha,
)
from utils.publicacao_narrativa import sincronizar_publicacoes_narrativas
from utils.midia import (
    AnexoLocal,
    aplicar_imagem,
    criar_arquivos_discord,
    referencia_imagem,
    resolver_anexo,
    salvar_upload_ficha,
)
from utils.taca import (
    CATEGORIAS_GRATIFICACAO,
    CATEGORIAS_PENALIDADE_AUTORIDADE,
)


TEMPO_FLUXO = 20 * 60
PONTOS_ATRIBUTO_INICIAIS = 14
ATRIBUTO_MINIMO_PERSONAGEM = 4
XP_INICIAL = 300
NIVEL_INICIAL_MINIMO = 1
NIVEL_INICIAL_MAXIMO = 10
TIPOS_NPC = (
    "Bruxo(a)",
    "Humano/Trouxa",
    "Semi-Humano",
    "Espírito",
)
RANKS_PERICIA = (0, 2, 4, 6)
CUSTOS_RANK = {2: 50, 4: 100, 6: 150}
NOMES_RANK = {0: "Inexperiente", 2: "Treinada", 4: "Expert", 6: "Mestre"}
CASAS = ("Grifinória", "Sonserina", "Lufa-Lufa", "Corvinal")
CLASSES_SOCIAIS = {"Pobre": 0, "Média": 10, "Alta": 25, "Prestígio": 50}
LOCKS_FICHA: dict[Path, asyncio.Lock] = {}
TAREFAS_SINCRONIZACAO_PENDENTE: dict[Path, asyncio.Task[None]] = {}
BIBLIOTECA_FEITICOS = BibliotecaCategoria("feitiços")
BIBLIOTECA_RUNAS = BibliotecaCategoria("runas")
BIBLIOTECA_BINDRUNES = BibliotecaCategoria("bindrunes")
BIBLIOTECA_POCOES = BibliotecaCategoria("poções")


def classe_social_por_total(total: int) -> tuple[str, int]:
    if total <= 0:
        return "Pobre", 0
    if total <= 2:
        return "Média", 10
    if total <= 4:
        return "Alta", 25
    return "Prestígio", 50


@dataclass(frozen=True)
class ReferenciaFeiticoFicha:
    nome: str
    categoria: str
    caminho: Path


@dataclass(frozen=True)
class ReferenciaPocaoFicha:
    nome: str
    categoria: str
    caminho: Path


def texto_guia_descricao(texto: str, fallback: str) -> str:
    limpo = re.sub(r"[*_`]+", "", texto)
    limpo = re.sub(r"\s+", " ", limpo).strip()
    return (limpo or fallback)[:1024]


def exemplo_descricao_feitico(referencia: ReferenciaFeiticoFicha) -> str:
    if not referencia.caminho.is_file():
        return referencia.nome[:100]
    entrada = interpretar_markdown(
        referencia.caminho.read_text(encoding="utf-8-sig")
    )
    campos = {
        normalizar_rotulo(rotulo): valor.strip()
        for rotulo, valor in entrada.campos.items()
    }
    if normalizar_rotulo(referencia.categoria) in {
        normalizar_rotulo("Runas Antigas"),
        normalizar_rotulo("Bindrunes"),
    }:
        sugestao = campos.get(normalizar_rotulo("Capacidades Mágicas"), "")
    else:
        sugestao = entrada.descricao
    return texto_guia_descricao(sugestao, referencia.nome)


def exemplo_descricao_pocao(referencia: ReferenciaPocaoFicha) -> str:
    if not referencia.caminho.is_file():
        return referencia.nome[:100]
    entrada, _, _ = interpretar_pocao(
        referencia.caminho.read_text(encoding="utf-8-sig")
    )
    return texto_guia_descricao(
        entrada.campos.get(normalizar_rotulo("Efeito"), ""),
        referencia.nome,
    )


@lru_cache(maxsize=1)
def _indice_feiticos_ficha() -> tuple[ReferenciaFeiticoFicha, ...]:
    # A biblioteca de feitiços tem centenas de arquivos. Ler e interpretar todos
    # a cada clique deixava os menus perceptivelmente lentos. O índice é montado
    # uma vez por execução do bot; alterações nas fichas não invalidam esse índice.
    referencias: list[ReferenciaFeiticoFicha] = []
    fontes = (
        (BIBLIOTECA_FEITICOS, ""),
        (BIBLIOTECA_RUNAS, "Runas Antigas"),
        (BIBLIOTECA_BINDRUNES, "Bindrunes"),
    )
    for biblioteca, categoria_forcada in fontes:
        for caminho in biblioteca.listar_arquivos():
            entrada = interpretar_markdown(caminho.read_text(encoding="utf-8-sig"))
            campos = {
                normalizar_rotulo(rotulo): valor.strip()
                for rotulo, valor in entrada.campos.items()
            }
            categoria_entrada = categoria_forcada or campos.get("categoria", "")
            if not categoria_entrada:
                continue
            referencias.append(
                ReferenciaFeiticoFicha(
                    nome=entrada.titulo or caminho.stem,
                    categoria=categoria_entrada,
                    caminho=caminho,
                )
            )
    return tuple(sorted(referencias, key=lambda item: item.nome.casefold()))


def listar_feiticos_ficha(categoria: str = "") -> list[ReferenciaFeiticoFicha]:
    categoria_normalizada = normalizar_rotulo(categoria)
    referencias = _indice_feiticos_ficha()
    if not categoria_normalizada:
        return list(referencias)
    return [
        item for item in referencias
        if normalizar_rotulo(item.categoria) == categoria_normalizada
    ]


def listar_categorias_feiticos_ficha() -> list[str]:
    categorias: dict[str, str] = {}
    for referencia in listar_feiticos_ficha():
        categorias.setdefault(normalizar_rotulo(referencia.categoria), referencia.categoria)
    return sorted(categorias.values(), key=str.casefold)


@lru_cache(maxsize=None)
def subgrupo_feitico_ficha(referencia: ReferenciaFeiticoFicha) -> str:
    """Retorna o agrupamento usado apenas na navegação do botão Feitiço."""
    categoria = normalizar_rotulo(referencia.categoria)

    if categoria == normalizar_rotulo("Bindrunes"):
        return "Bindrunes"

    if categoria == normalizar_rotulo("Runas Antigas"):
        try:
            texto = referencia.caminho.read_text(encoding="utf-8-sig")
        except OSError:
            return ""
        texto_norm = normalizar_rotulo(texto)
        for nome in (
            "Primeiro Ætt de Freyr",
            "Segundo Ætt de Heimdall",
            "Terceiro Ætt de Tyr",
        ):
            if normalizar_rotulo(nome) in texto_norm:
                return nome
        return ""

    if categoria == normalizar_rotulo("Arte das Trevas"):
        try:
            entrada = interpretar_markdown(
                referencia.caminho.read_text(encoding="utf-8-sig")
            )
        except OSError:
            return ""
        campos = {
            normalizar_rotulo(rotulo): valor.strip()
            for rotulo, valor in entrada.campos.items()
        }
        return campos.get(normalizar_rotulo("Vertente"), "")

    try:
        entrada = interpretar_markdown(
            referencia.caminho.read_text(encoding="utf-8-sig")
        )
    except OSError:
        return ""
    campos = {
        normalizar_rotulo(rotulo): valor.strip()
        for rotulo, valor in entrada.campos.items()
    }
    ano = campos.get(normalizar_rotulo("Ano de desbloqueio"), "")
    # Aceita pequenas variações já existentes na biblioteca (ex.: 1°Ano ou
    # "1º Ano, com reforço...") sem criar categorias extras no menu.
    correspondencia = re.search(r"([1-7])\s*[º°]?\s*ano", ano, re.IGNORECASE)
    return f"{correspondencia.group(1)}º Ano" if correspondencia else ""


def referencias_categoria_menu_ficha(categoria: str) -> list[ReferenciaFeiticoFicha]:
    if normalizar_rotulo(categoria) == normalizar_rotulo("Runas Antigas"):
        referencias = listar_feiticos_ficha("Runas Antigas") + listar_feiticos_ficha("Bindrunes")
        return sorted(referencias, key=lambda item: item.nome.casefold())
    return listar_feiticos_ficha(categoria)


def subgrupos_categoria_ficha(categoria: str, referencias: list[ReferenciaFeiticoFicha]) -> list[str]:
    categoria_norm = normalizar_rotulo(categoria)
    presentes = {
        normalizar_rotulo(grupo): grupo
        for referencia in referencias
        if (grupo := subgrupo_feitico_ficha(referencia))
    }

    if categoria_norm == normalizar_rotulo("Runas Antigas"):
        ordem = [
            "Primeiro Ætt de Freyr",
            "Segundo Ætt de Heimdall",
            "Terceiro Ætt de Tyr",
            "Bindrunes",
        ]
    elif categoria_norm == normalizar_rotulo("Arte das Trevas"):
        ordem = [
            "Maldições",
            "Necromancia",
            "Magia Ritualística",
            "Alquimia Sombria",
            "Magia de Controle",
            "Magia de Destruição",
            "Magia de Ilusão",
        ]
    else:
        ordem = [f"{ano}º Ano" for ano in range(1, 8)]

    return [nome for nome in ordem if normalizar_rotulo(nome) in presentes]


def listar_pocoes_ficha(categoria: str = "") -> list[ReferenciaPocaoFicha]:
    categoria_normalizada = normalizar_rotulo(categoria)
    referencias: list[ReferenciaPocaoFicha] = []
    for caminho in BIBLIOTECA_POCOES.listar_arquivos():
        entrada, _, _ = interpretar_pocao(caminho.read_text(encoding="utf-8-sig"))
        categoria_entrada = caminho.parent.name
        if (
            categoria_normalizada
            and normalizar_rotulo(categoria_entrada) != categoria_normalizada
        ):
            continue
        referencias.append(
            ReferenciaPocaoFicha(
                nome=entrada.titulo or caminho.stem,
                categoria=categoria_entrada,
                caminho=caminho,
            )
        )
    return sorted(referencias, key=lambda item: item.nome.casefold())


def listar_categorias_pocoes_ficha() -> list[str]:
    categorias = {referencia.categoria for referencia in listar_pocoes_ficha()}

    def chave(categoria: str) -> tuple[int, str]:
        numero = re.search(r"\d+", categoria)
        return (int(numero.group()) if numero else 99, categoria.casefold())

    return sorted(categorias, key=chave)


@dataclass
class SessaoFicha:
    usuario_id: int
    titular_id: int = 0
    nome: str = ""
    grupo: str = ""
    nivel: int = 1
    heranca: str = ""
    casa: str = ""
    nucleo: str = ""
    atributos: dict[str, int] = field(default_factory=lambda: {nome: 10 for nome in ATRIBUTOS})
    pericia_casa: str = ""
    pericias_livres: list[str] = field(default_factory=list)
    aptidoes_nucleo: list[str] = field(default_factory=list)
    rolagem_social: int = 0
    modificador_social: int = 0
    classe_social: str = ""
    galeoes: int = 0
    tipo_npc: str = ""
    especie_npc: str = ""
    tamanho_npc: str = ""
    faixa_tamanho_npc: str = ""
    anos_pos_vida: int = 0


def embed_painel(titulo: str, descricao: str) -> discord.Embed:
    return discord.Embed(title=titulo, description=descricao)


def opcoes_texto(valores: list[str] | tuple[str, ...]) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=valor,
            value=valor,
            emoji=EMOJIS_PASTAS_FICHA.get(valor),
        )
        for valor in valores
    ]


def faixa_tamanho_automatica(tamanho: str) -> str:
    metros = tamanho_em_metros(tamanho)
    if metros < 0.5:
        return "Menos de 50 cm"
    if metros < 1:
        return "Menos de 1 m"
    if metros <= 2:
        return "De 1 m a 2 m"
    if metros <= 3:
        return "De 2 m a 3 m"
    if metros <= 4:
        return "De 3 m a 4 m"
    if metros <= 5:
        return "De 4 m a 5 m"
    if metros <= 10:
        return "De 5 m a 10 m"
    return "Acima de 10 m"


def npc_nao_magico(sessao: SessaoFicha) -> bool:
    return sessao.grupo == "NPCs" and sessao.tipo_npc not in {"", "Bruxo(a)"}


def opcoes_nucleos() -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=nome,
            value=nome,
            description=resumo_bonus_nucleo(nome)[:100],
        )
        for nome in listar_nucleos()
    ]


def bonus_aptidoes_heranca(nome_heranca: str) -> dict[str, int]:
    entrada = carregar_habilidade("heranca_sanguinea", nome_heranca)
    if entrada is None:
        return {}

    campos = {
        normalizar_rotulo(rotulo): valor
        for rotulo, valor in entrada.campos.items()
    }
    habilidade_inicial = campos.get("habilidade inicial", "")
    bonus: dict[str, int] = {}
    for aptidao in APTIDOES:
        correspondencia = re.search(
            rf"\+(\d+)\s+em\s+{re.escape(aptidao)}(?=\s+e\s+\+\d+\s+em|[.;]|$)",
            habilidade_inicial,
            flags=re.IGNORECASE,
        )
        if correspondencia:
            bonus[aptidao] = int(correspondencia.group(1))
    return bonus


def pontos_criacao_por_nivel(nivel: int) -> int:
    if not NIVEL_INICIAL_MINIMO <= nivel <= NIVEL_INICIAL_MAXIMO:
        raise ValueError(
            f"O nível inicial deve estar entre {NIVEL_INICIAL_MINIMO} "
            f"e {NIVEL_INICIAL_MAXIMO}."
        )
    return PONTOS_ATRIBUTO_INICIAIS + 2 * max(nivel - 1, 0)


def pv_ph_criacao_por_nivel(
    nivel: int,
    constituicao: int,
    sabedoria: int,
) -> tuple[int, int]:
    niveis_adicionais = max(nivel - 1, 0)
    pv = (
        10
        + constituicao
        + niveis_adicionais * (5 + modificador(constituicao))
    )
    ph = (
        sabedoria // 2
        + niveis_adicionais * (2 + modificador(sabedoria))
    )
    return pv, ph


def ficha_da_sessao(sessao: SessaoFicha) -> FichaPersonagem:
    pericias = {nome: 0 for nome in PERICIAS}
    for nome in [sessao.pericia_casa, *sessao.pericias_livres]:
        if nome:
            pericias[nome] = 2

    aptidoes = {nome: 0 for nome in APTIDOES}
    if not npc_nao_magico(sessao):
        bonus, _, bonus_escolha = dados_nucleo(sessao.nucleo)
        for nome, valor in bonus.items():
            if nome in aptidoes:
                aptidoes[nome] += valor
        for nome in sessao.aptidoes_nucleo:
            aptidoes[nome] += bonus_escolha
        for nome, valor in bonus_aptidoes_heranca(sessao.heranca).items():
            aptidoes[nome] += valor

    constituicao = sessao.atributos["Constituição"]
    sabedoria = sessao.atributos["Sabedoria"]
    pv, ph = pv_ph_criacao_por_nivel(sessao.nivel, constituicao, sabedoria)
    espirito = sessao.tipo_npc == "Espírito"
    habilidades_npc: list[dict[str, str]] = []
    if espirito:
        habilidades_npc = [
            {
                "nome": "Intangibilidade — Passivo",
                "descrição": (
                    "O espírito não possui corpo físico e atravessa matéria comum. "
                    "Não possui Pontos de Vida; todo dano que realmente o alcance é aplicado à Alma."
                ),
            },
            {
                "nome": "Manifestação Paranormal — Passivo",
                "descrição": (
                    f"Possui Manifestação Paranormal +{sessao.anos_pos_vida}, recebendo +1 a cada aniversário de morte. "
                    "Para causar impacto no mundo físico, rola 1d20 + Manifestação Paranormal contra dificuldade 15. "
                    "Em caso de sucesso, cada 3 pontos acima de 15 aumenta em um grau a força da manifestação."
                ),
            },
        ]
    ficha = FichaPersonagem(
        nome=sessao.nome,
        grupo=sessao.grupo,
        casa=sessao.casa,
        heranca=sessao.heranca,
        nucleo=sessao.nucleo,
        titular_id=sessao.titular_id or sessao.usuario_id,
        nivel=sessao.nivel,
        xp=XP_INICIAL,
        alma=100,
        pv=0 if espirito else pv,
        ph=ph,
        classe_social=sessao.classe_social,
        rolagem_social=sessao.rolagem_social,
        modificador_social=sessao.modificador_social,
        galeoes=sessao.galeoes,
        atributos=dict(sessao.atributos),
        pericias=pericias,
        aptidoes=aptidoes,
        tipo_npc=sessao.tipo_npc,
        especie_npc=sessao.especie_npc,
        faixa_tamanho_npc=sessao.faixa_tamanho_npc,
        anos_pos_vida=sessao.anos_pos_vida,
        manifestacao_paranormal=sessao.anos_pos_vida,
        habilidades_npc=habilidades_npc,
    )
    if sessao.grupo == "Figuras de Autoridade":
        ordens = [
            FichaPersonagem.carregar(referencia.caminho).ordem_autoridade
            for referencia in listar_fichas()
            if referencia.grupo == "Figuras de Autoridade"
        ]
        ficha.ordem_autoridade = max(ordens, default=0) + 1
        ficha.informacoes = [
            {"titulo": "Cargo", "descricao": "--"},
            {"titulo": "Valores", "descricao": "--"},
            {"titulo": "Personalidade", "descricao": "--"},
        ]
    elif sessao.grupo in CASAS:
        ficha.informacoes = [
            {"titulo": "Cursando", "descricao": "--"},
            {"titulo": "Altura e Idade", "descricao": "--"},
        ]
    elif sessao.grupo == "Players":
        ficha.informacoes = [
            {"titulo": "Altura e Idade", "descricao": "--"},
        ]
    elif sessao.grupo == "NPCs" and sessao.tipo_npc:
        ficha.altura = sessao.tamanho_npc or "--"
        ficha.informacoes = [
            {"titulo": "Altura e Idade", "descricao": "--"},
            {"titulo": "Sobre", "descricao": "--"},
        ]
    sincronizar_campos_base(ficha)
    return ficha


def formatar_linha_pericia(ficha: FichaPersonagem, nome: str) -> str:
    atributos = ATRIBUTOS_POR_PERICIA[nome]
    siglas = "/".join(SIGLAS_ATRIBUTOS[atributo] for atributo in atributos)
    treinamento = ficha.pericias.get(nome, 0)
    bonus_habilidade = bonus_pericias_passivos(ficha).get(nome, 0)
    totais = tuple(
        total + bonus_habilidade
        for total in bonus_pericia(nome, treinamento, atributos_efetivos(ficha))
    )
    valores = "/".join(formatar_bonus(total) for total in totais)
    origem_bonus = f" (+{bonus_habilidade} de habilidade)" if bonus_habilidade else ""
    linha = f"({siglas}) {nome}: {valores}{origem_bonus}"
    if treinamento in (2, 4, 6):
        return f"> ***{linha} ({NOMES_RANK[treinamento]})***"
    return f"> *{linha}*"


def rotulo_evolucao_heranca(evolucao: int) -> str:
    rotulos = {
        0: "Inicial Passiva",
        1: "Primeira Desbloqueada",
        2: "Segunda Desbloqueada",
        3: "Terceira Desbloqueada",
        4: "Quarta Desbloqueada",
    }
    return rotulos.get(evolucao, "Totalmente Desbloqueada")


def custo_aprimorar_aptidao(
    ficha: FichaPersonagem,
    alvo: int,
    nome: str = "",
) -> int:
    alvo_efetivo = alvo + bonus_aptidoes_passivos(ficha).get(nome, 0)
    return max(0, 20 * alvo_efetivo - desconto_aptidao(ficha))


def custo_subir_nivel(ficha: FichaPersonagem) -> int:
    return max(0, 50 * (ficha.nivel + 1) - desconto_nivel(ficha))


def custo_subir_niveis(ficha: FichaPersonagem, quantidade: int) -> int:
    """Calcula o custo acumulado de várias subidas consecutivas."""
    if quantidade < 1:
        raise ValueError("A quantidade de níveis deve ser maior que zero.")
    return sum(
        max(0, 50 * (ficha.nivel + indice) - desconto_nivel(ficha))
        for indice in range(1, quantidade + 1)
    )


def custo_aprimorar_aptidoes(
    ficha: FichaPersonagem,
    nome: str,
    quantidade: int,
) -> int:
    """Soma o custo de cada ponto, respeitando a progressão da aptidão."""
    if quantidade < 1:
        raise ValueError("A quantidade deve ser maior que zero.")
    atual = ficha.aptidoes.get(nome, 0)
    return sum(
        custo_aprimorar_aptidao(ficha, atual + indice, nome)
        for indice in range(1, quantidade + 1)
    )


def resumo_efeitos_heranca(ficha: FichaPersonagem) -> str:
    linhas: list[str] = []
    bonus = [
        f"{nome} +{valor}"
        for nome, valor in ficha.bonus_atributos_temporarios.items()
        if valor > 0
    ]
    if bonus:
        linhas.append("🔥 **Atributos temporários:** " + ", ".join(bonus))
    reducoes = [
        f"{nome} ×{quantidade}"
        for nome, quantidade in ficha.reducoes_dificuldade_heranca.items()
        if quantidade > 0
    ]
    if reducoes:
        linhas.append("🪄 **Reduções de dificuldade:** " + ", ".join(reducoes))
    return "\n".join(linhas)


def aplicar_mecanica_sangue_puro(
    ficha: FichaPersonagem,
    acao: str,
    item: str = "",
) -> tuple[int, str]:
    if normalizar_rotulo(ficha.heranca) != normalizar_rotulo("Sangue Puro"):
        raise ValueError("Esta ficha não possui a Herança Sanguínea Sangue Puro.")

    if acao == "maestria":
        if not sangue_puro_desbloqueado(ficha, 1):
            raise ValueError("A Primeira Evolução de Sangue Puro ainda não foi desbloqueada.")
        ficha.xp += 2
        return 0, "A maestria com resultado 18 ou maior concedeu **+2 XP**."

    if acao == "atributo":
        if not sangue_puro_desbloqueado(ficha, 3):
            raise ValueError("A Terceira Evolução de Sangue Puro ainda não foi desbloqueada.")
        if item not in ATRIBUTOS:
            raise ValueError("Escolha um atributo válido.")
        custo = 10
        if ficha.xp < custo:
            raise ValueError(f"XP insuficiente: esta ativação custa {custo} XP.")
        ficha.xp -= custo
        ficha.bonus_atributos_temporarios[item] = (
            ficha.bonus_atributos_temporarios.get(item, 0) + 2
        )
        return custo, f"{item} recebeu **+2** até o fim da cena."

    if acao == "reducao":
        if not sangue_puro_desbloqueado(ficha, 5):
            raise ValueError("A Última Evolução de Sangue Puro ainda não foi desbloqueada.")
        custos = {"Intermediário": 5, "Avançado": 10}
        if item not in custos:
            raise ValueError("Escolha uma dificuldade válida.")
        custo = custos[item]
        if ficha.xp < custo:
            raise ValueError(f"XP insuficiente: esta redução custa {custo} XP.")
        ficha.xp -= custo
        ficha.reducoes_dificuldade_heranca[item] = (
            ficha.reducoes_dificuldade_heranca.get(item, 0) + 1
        )
        return custo, f"Uma redução para feitiço **{item}** foi preparada."

    if acao == "consumir_reducao":
        if item not in REDUCOES_DIFICULDADE:
            raise ValueError("Escolha uma dificuldade válida.")
        quantidade = ficha.reducoes_dificuldade_heranca.get(item, 0)
        if quantidade <= 0:
            raise ValueError("A ficha não possui essa redução preparada.")
        ficha.reducoes_dificuldade_heranca[item] = quantidade - 1
        return 0, f"Uma redução de dificuldade **{item}** foi consumida."

    if acao == "encerrar_cena":
        if not any(ficha.bonus_atributos_temporarios.values()):
            raise ValueError("A ficha não possui bônus temporários ativos.")
        ficha.bonus_atributos_temporarios = {nome: 0 for nome in ATRIBUTOS}
        return 0, "Os bônus temporários de atributo foram encerrados."

    raise ValueError("Mecânica de Sangue Puro desconhecida.")


def aplicar_mecanica_heranca(
    ficha: FichaPersonagem,
    acao: str,
    item: str = "",
) -> tuple[int, str]:
    """Executa as evoluções que realmente alteram a ficha ou seus recursos."""
    heranca = normalizar_rotulo(ficha.heranca)
    if heranca == normalizar_rotulo("Sangue Puro"):
        return aplicar_mecanica_sangue_puro(ficha, acao, item)
    if heranca not in {
        normalizar_rotulo("Meio-Sangue"),
        normalizar_rotulo("Nascido-Trouxa"),
    }:
        raise ValueError("Esta Herança Sanguínea não possui uma mecânica de ficha automática.")

    if acao == "evento":
        if not heranca_desbloqueada(ficha, 1):
            raise ValueError("A Primeira Evolução ainda não foi desbloqueada.")
        ficha.xp += 2
        motivo = (
            "o sucesso crítico em uma ação"
            if heranca == normalizar_rotulo("Meio-Sangue")
            else "a ação de natureza trouxa"
        )
        return 0, f"Foi registrado {motivo}, concedendo **+2 XP**."

    if acao in {"atributo", "encerrar_cena"}:
        if acao == "atributo":
            if not heranca_desbloqueada(ficha, 3):
                raise ValueError("A Terceira Evolução ainda não foi desbloqueada.")
            if item not in ATRIBUTOS:
                raise ValueError("Escolha um atributo válido.")
            if ficha.xp < 10:
                raise ValueError("XP insuficiente: esta ativação custa 10 XP.")
            ficha.xp -= 10
            ficha.bonus_atributos_temporarios[item] = (
                ficha.bonus_atributos_temporarios.get(item, 0) + 2
            )
            return 10, f"{item} recebeu **+2** até o fim da cena."
        if not any(ficha.bonus_atributos_temporarios.values()):
            raise ValueError("A ficha não possui bônus temporários ativos.")
        ficha.bonus_atributos_temporarios = {nome: 0 for nome in ATRIBUTOS}
        return 0, "Os bônus temporários de atributo foram encerrados."

    if acao == "catalisador":
        if heranca != normalizar_rotulo("Meio-Sangue") or not heranca_desbloqueada(ficha, 5):
            raise ValueError("A Última Evolução de Meio-Sangue ainda não foi desbloqueada.")
        if ficha.xp < 5:
            raise ValueError("XP insuficiente: esta ativação custa 5 XP.")
        ficha.xp -= 5
        ficha.efeitos_habilidades_ativos.append(
            {
                "nome": "Catalisador Temporário",
                "efeito": "Um objeto não mágico funciona como catalisador.",
                "duracao": "1d4+1 rodadas",
            }
        )
        return 5, "O **Catalisador Temporário** foi registrado por **1d4+1 rodadas**."

    if acao == "especializacao_improvisada":
        if heranca != normalizar_rotulo("Nascido-Trouxa") or not heranca_desbloqueada(ficha, 5):
            raise ValueError("A Última Evolução de Nascido-Trouxa ainda não foi desbloqueada.")
        if not item:
            raise ValueError("Escolha a Especialização usada.")
        if ficha.xp < 5:
            raise ValueError("XP insuficiente: esta ativação custa 5 XP.")
        ficha.xp -= 5
        ficha.efeitos_habilidades_ativos.append(
            {
                "nome": f"Especialização improvisada — {item}",
                "efeito": "Pode usar a Especialização sem cumprir seus requisitos.",
                "duracao": "Uso atual",
            }
        )
        return 5, f"O uso de **{item}** sem requisitos foi registrado."

    if acao == "encerrar_efeito":
        if not ficha.efeitos_habilidades_ativos:
            raise ValueError("A ficha não possui efeitos de habilidade ativos.")
        removido = ficha.efeitos_habilidades_ativos.pop(int(item))
        return 0, f"O efeito **{removido['nome']}** foi encerrado."

    raise ValueError("Mecânica de Herança Sanguínea desconhecida.")


def embed_mecanicas_heranca(ficha: FichaPersonagem) -> discord.Embed:
    if normalizar_rotulo(ficha.heranca) == normalizar_rotulo("Sangue Puro"):
        return embed_mecanicas_sangue_puro(ficha)
    linhas = [
        f"**XP disponível:** {ficha.xp}",
        f"**Evolução:** {rotulo_evolucao_heranca(ficha.evolucao_heranca)}",
    ]
    if heranca_desbloqueada(ficha, 1):
        evento = (
            "sucesso crítico em uma ação"
            if normalizar_rotulo(ficha.heranca) == normalizar_rotulo("Meio-Sangue")
            else "ação de natureza trouxa"
        )
        linhas.append(f"**Primeira Evolução:** +2 XP ao registrar {evento}.")
    if heranca_desbloqueada(ficha, 3):
        linhas.append("**Terceira Evolução:** 10 XP por +2 cumulativo em um atributo durante a cena.")
    if heranca_desbloqueada(ficha, 5):
        linhas.append(
            "**Última Evolução:** 5 XP para criar um catalisador temporário."
            if normalizar_rotulo(ficha.heranca) == normalizar_rotulo("Meio-Sangue")
            else "**Última Evolução:** 5 XP para usar uma Especialização sem seus requisitos."
        )
    return embed_painel(f"🧬 {ficha.heranca}", "\n".join(linhas))


def embed_mecanicas_sangue_puro(ficha: FichaPersonagem) -> discord.Embed:
    linhas = [
        f"**XP disponível:** {ficha.xp}",
        f"**Evolução:** {rotulo_evolucao_heranca(ficha.evolucao_heranca)}",
    ]
    if sangue_puro_desbloqueado(ficha, 1):
        linhas.append(
            "**Primeira Evolução:** registre +2 XP após executar um feitiço "
            "com maestria e obter resultado 18 ou maior."
        )
    if sangue_puro_desbloqueado(ficha, 3):
        linhas.append(
            "**Terceira Evolução:** gaste 10 XP para conceder +2 cumulativo "
            "a um atributo durante a cena."
        )
    if sangue_puro_desbloqueado(ficha, 5):
        linhas.append(
            "**Última Evolução:** prepare uma redução de dificuldade por "
            "5 XP para feitiços Intermediários ou 10 XP para Avançados."
        )
    ativos = resumo_efeitos_heranca(ficha)
    if ativos:
        linhas.extend(("", ativos))
    return embed_painel("🧬 Sangue Puro", "\n".join(linhas))


def total_evolucoes_heranca(nome: str) -> int:
    entrada = carregar_habilidade("heranca_sanguinea", nome)
    if entrada is None:
        return 0
    campos = {
        normalizar_rotulo(rotulo): valor
        for rotulo, valor in entrada.campos.items()
    }
    evolucoes = campos.get(normalizar_rotulo("Evoluções"), "")
    return sum(
        1
        for linha in evolucoes.splitlines()
        if linha.lstrip().startswith("**")
        and "evolucao" in normalizar_rotulo(linha)
    )


def habilidade_ja_possuida(possuidas: list[str], nome: str) -> bool:
    nome_normalizado = normalizar_rotulo(nome)
    return any(
        normalizar_rotulo(possuida) == nome_normalizado
        for possuida in possuidas
    )


MODELO_MESTRIA_FEITICO = "Mestria em (Nome do Feitiço)"


def nome_mestria_feitico(nome_feitico: str) -> str:
    return f"Mestria em {nome_feitico.strip()}"


def nome_feitico_da_mestria(nome: str) -> str:
    prefixo = normalizar_rotulo("Mestria em ")
    normalizado = normalizar_rotulo(nome)
    if not normalizado.startswith(prefixo):
        return ""
    if normalizado == normalizar_rotulo(MODELO_MESTRIA_FEITICO):
        return ""
    return nome[len("Mestria em "):].strip()


def listar_feiticos_mestria(ficha: FichaPersonagem | None = None) -> list[ReferenciaFeiticoFicha]:
    pasta_feiticos = BIBLIOTECA_FEITICOS.pasta.resolve()
    referencias = [
        referencia
        for referencia in listar_feiticos_ficha()
        if pasta_feiticos in referencia.caminho.resolve().parents
    ]
    if ficha is None:
        return referencias
    dominados = {
        normalizar_rotulo(nome_feitico_da_mestria(nome))
        for nome in ficha.especializacoes
        if nome_feitico_da_mestria(nome)
    }
    return [
        referencia
        for referencia in referencias
        if normalizar_rotulo(referencia.nome) not in dominados
    ]


@lru_cache(maxsize=None)
def ano_desbloqueio_mestria(referencia: ReferenciaFeiticoFicha) -> str:
    try:
        entrada = interpretar_markdown(
            referencia.caminho.read_text(encoding="utf-8-sig")
        )
    except OSError:
        return "Sem ano definido"
    campos = {
        normalizar_rotulo(rotulo): valor.strip()
        for rotulo, valor in entrada.campos.items()
    }
    ano = campos.get(normalizar_rotulo("Ano de desbloqueio"), "")
    correspondencia = re.search(r"([1-7])\s*[º°]?\s*ano", ano, re.IGNORECASE)
    if correspondencia:
        return f"{correspondencia.group(1)}º Ano"
    return ano or "Sem ano definido"


def categorias_mestria(referencias: list[ReferenciaFeiticoFicha]) -> list[str]:
    categorias: dict[str, str] = {}
    for referencia in referencias:
        categorias.setdefault(
            normalizar_rotulo(referencia.categoria),
            referencia.categoria,
        )
    return sorted(categorias.values(), key=str.casefold)


def anos_mestria(
    categoria: str,
    referencias: list[ReferenciaFeiticoFicha],
) -> list[str]:
    divisoes: dict[str, str] = {}
    arte_das_trevas = normalizar_rotulo(categoria) == normalizar_rotulo(
        "Arte das Trevas"
    )
    for referencia in referencias:
        if normalizar_rotulo(referencia.categoria) != normalizar_rotulo(categoria):
            continue
        divisao = (
            referencia.caminho.parent.name
            if arte_das_trevas
            else ano_desbloqueio_mestria(referencia)
        )
        divisoes.setdefault(normalizar_rotulo(divisao), divisao)

    if arte_das_trevas:
        return sorted(divisoes.values(), key=str.casefold)

    def ordem(ano: str) -> tuple[int, str]:
        correspondencia = re.match(r"([1-7])º Ano$", ano)
        if correspondencia:
            return int(correspondencia.group(1)), ""
        if normalizar_rotulo(ano) == normalizar_rotulo("Sem ano definido"):
            return 99, ""
        return 98, normalizar_rotulo(ano)

    return sorted(divisoes.values(), key=ordem)


def divisao_mestria(
    referencia: ReferenciaFeiticoFicha,
    categoria: str,
) -> str:
    if normalizar_rotulo(categoria) == normalizar_rotulo("Arte das Trevas"):
        return referencia.caminho.parent.name
    return ano_desbloqueio_mestria(referencia)


def rotulo_divisao_mestria(categoria: str) -> str:
    if normalizar_rotulo(categoria) == normalizar_rotulo("Arte das Trevas"):
        return "Categoria de Arte das Trevas"
    return "Ano de desbloqueio"


def referencia_feitico_mestria(nome: str) -> ReferenciaFeiticoFicha | None:
    alvo = normalizar_rotulo(nome)
    return next(
        (
            referencia
            for referencia in listar_feiticos_mestria()
            if normalizar_rotulo(referencia.nome) == alvo
        ),
        None,
    )


def habilidades_disponiveis_mercado(
    ficha: FichaPersonagem,
    categoria: str,
) -> list[str]:
    possuidas = (
        ficha.origens_magicas
        if categoria == "origem_magica"
        else ficha.especializacoes
    )
    disponiveis = []
    for nome in listar_habilidades(categoria, limite=None):
        if categoria == "especializacao" and normalizar_rotulo(nome) == normalizar_rotulo(MODELO_MESTRIA_FEITICO):
            if listar_feiticos_mestria(ficha):
                disponiveis.append(nome)
            continue
        if not habilidade_ja_possuida(possuidas, nome):
            disponiveis.append(nome)
    return disponiveis


def _campos_habilidade(entrada) -> dict[str, str]:
    return {
        normalizar_rotulo(rotulo): valor.strip()
        for rotulo, valor in entrada.campos.items()
    }


def _normalizar_ph_texto(texto: str) -> str:
    return re.sub(
        r"\b(\d+)\s*PH\b",
        lambda correspondencia: f"{correspondencia.group(1)}ph",
        texto.strip(),
        flags=re.IGNORECASE,
    )


def _maiuscula_inicial_descricao(texto: str) -> str:
    """Inicia cada linha textual com maiúscula sem alterar custos como `2ph`."""
    linhas: list[str] = []
    for linha in texto.splitlines():
        correspondencia = re.match(
            r"^(?P<prefixo>\s*(?:[>*_`~-]+\s*)*)(?P<letra>[a-zà-ÿ])",
            linha,
        )
        if correspondencia:
            inicio, fim = correspondencia.span("letra")
            linha = linha[:inicio] + linha[inicio:fim].upper() + linha[fim:]
        linhas.append(linha)
    return "\n".join(linhas)


def _remover_marcador_passivo_inicial(texto: str) -> str:
    return re.sub(
        r"^\s*(?:\*\*)?passiv[oa](?:\*\*)?\s*(?:[.:—-]\s*)?",
        "",
        texto,
        count=1,
        flags=re.IGNORECASE,
    ).strip()


def _blocos_titulados_habilidade(texto: str) -> list[tuple[str, str]]:
    padrao = re.compile(
        r"(?ms)^\*\*(?P<titulo>.+?):\*\*\s*(?P<conteudo>.*?)(?=^\*\*.+?:\*\*|\Z)"
    )
    return [
        (
            _normalizar_ph_texto(correspondencia.group("titulo")),
            _normalizar_ph_texto(correspondencia.group("conteudo")),
        )
        for correspondencia in padrao.finditer(texto.strip())
    ]


def _titulo_subhabilidade_origem(titulo: str) -> str:
    """Usa travessão para separar nome, estágio, custo e mecânica no título."""
    return re.sub(r"\s*//\s*", " — ", _normalizar_ph_texto(titulo)).strip()


def _dividir_valor_campo(texto: str, limite: int = 1024) -> list[str]:
    restante = _normalizar_ph_texto(texto)
    partes: list[str] = []
    while len(restante) > limite:
        corte = restante.rfind("\n\n", 0, limite + 1)
        if corte <= 0:
            corte = restante.rfind("\n", 0, limite + 1)
        if corte <= 0:
            corte = restante.rfind(" ", 0, limite + 1)
        if corte <= 0:
            corte = limite
        partes.append(restante[:corte].strip())
        restante = restante[corte:].strip()
    if restante:
        partes.append(restante)
    return partes


def _adicionar_campo_efeito(
    embed: discord.Embed,
    nome: str,
    valor: str,
) -> None:
    valor = _maiuscula_inicial_descricao(valor)
    citacao = "\n".join(
        f"> {linha}"
        for linha in _normalizar_ph_texto(valor).splitlines()
        if linha.strip()
    )
    for parte in _dividir_valor_campo(citacao, 1022):
        # Quando o corte acontece no meio de uma linha muito longa, a nova
        # parcela também precisa começar como citação.
        if not parte.startswith(">"):
            parte = f"> {parte}"
        # O Discord exige valores de campo com até 1.024 caracteres. Quando um
        # efeito é maior, repetimos o mesmo título sem poluir o nome com
        # “continuação”; a ordem dos campos já deixa a leitura evidente.
        embed.add_field(name=nome[:256], value=parte, inline=False)


def _fragmentar_embed_de_ficha(
    embed: discord.Embed,
    *,
    limite: int = 5900,
) -> list[discord.Embed]:
    """Quebra uma seção grande sem alterar seu título ou a ordem dos campos."""
    descricoes = [embed.description] if embed.description else [None]
    if embed.description and len(embed.description) > 4096:
        descricoes = _dividir_valor_campo(embed.description, 4000)

    partes: list[discord.Embed] = [
        discord.Embed(title=embed.title, description=descricao, color=embed.color)
        for descricao in descricoes
    ]
    atual = partes[-1]
    for campo in embed.fields:
        tamanho_campo = len(campo.name) + len(campo.value)
        if atual.fields and (
            len(atual.fields) >= 25 or len(atual) + tamanho_campo > limite
        ):
            atual = discord.Embed(title=embed.title, color=embed.color)
            partes.append(atual)
        atual.add_field(
            name=campo.name,
            value=campo.value,
            inline=campo.inline,
        )
    return partes


def adicionar_efeitos_habilidades(
    embed: discord.Embed,
    ficha: FichaPersonagem,
) -> None:
    heranca = carregar_habilidade("heranca_sanguinea", ficha.heranca)
    if heranca is not None:
        campos = _campos_habilidade(heranca)
        inicial = campos.get(normalizar_rotulo("Habilidade Inicial"), "")
        if inicial:
            _adicionar_campo_efeito(
                embed,
                f"🧬 {ficha.heranca} — Habilidade Inicial — Passivo",
                _remover_marcador_passivo_inicial(inicial),
            )
        evolucoes = _blocos_titulados_habilidade(
            campos.get(normalizar_rotulo("Evoluções"), "")
        )
        for titulo, efeito in evolucoes[: ficha.evolucao_heranca]:
            _adicionar_campo_efeito(
                embed,
                f"🧬 {ficha.heranca} — {titulo}",
                efeito,
            )

    for nome in ficha.origens_magicas:
        origem = carregar_habilidade("origem_magica", nome)
        if origem is None:
            continue
        campos = _campos_habilidade(origem)
        habilidades = campos.get(normalizar_rotulo("Habilidades"), "")
        blocos = _blocos_titulados_habilidade(habilidades)
        if blocos:
            for titulo, efeito in blocos:
                _adicionar_campo_efeito(
                    embed,
                    f"✨ {nome} — {_titulo_subhabilidade_origem(titulo)}",
                    efeito,
                )
        elif habilidades:
            # Compatibilidade com uma eventual origem antiga sem subtítulos.
            _adicionar_campo_efeito(embed, f"✨ {nome}", habilidades)

    for nome in ficha.especializacoes:
        modelo = MODELO_MESTRIA_FEITICO if nome_feitico_da_mestria(nome) else nome
        especializacao = carregar_habilidade("especializacao", modelo)
        if especializacao is None:
            continue
        campos = _campos_habilidade(especializacao)
        efeito = especializacao.descricao.strip()
        custo_ph = campos.get(normalizar_rotulo("Custo de PH"), "")
        if custo_ph:
            efeito += f"\n**Custo de PH:** {_normalizar_ph_texto(custo_ph)}"
        if efeito:
            _adicionar_campo_efeito(embed, f"🎓 {nome}", efeito)


def categorias_presets_autoridade(
    tipo: str,
) -> tuple[tuple[str, str, int, str], ...]:
    if tipo == "gratificacoes":
        return tuple(
            (identificador, nome, pontos, f"+{pontos} pontos")
            for identificador, nome, pontos in CATEGORIAS_GRATIFICACAO
        )
    if tipo == "penalidades":
        return CATEGORIAS_PENALIDADE_AUTORIDADE
    raise ValueError("Tipo de catálogo de autoridade inválido.")


def catalogo_autoridade_completo(registros: list[dict[str, str]]) -> bool:
    return all(
        sum(registro.get("pontos") == str(pontos) for registro in registros) == 2
        for pontos in (5, 10, 15, 20, 25)
    ) and len(registros) == 10


def validar_url_imagem_ficha(url: str) -> str:
    url = url.strip()
    analisada = urlparse(url)
    if analisada.scheme not in {"http", "https"} or not analisada.netloc:
        raise ValueError("Informe um link de imagem válido iniciado por http:// ou https://.")
    if len(url) > 2048:
        raise ValueError("O link da imagem ultrapassa 2.048 caracteres.")
    return url


def _prefixo_imagem_ficha(
    nome_ficha: str,
    imagem: dict[str, str],
    indice: int,
) -> str:
    titulo = imagem.get("titulo", "").strip() or f"aparencia-{indice}"
    return f"aparencia-{nome_ficha}-{indice}-{titulo}"


def linhas_imagens_ficha(
    imagens: list[dict[str, str]],
    nome_ficha: str,
) -> str:
    linhas = []
    for indice, imagem in enumerate(imagens, start=1):
        titulo = imagem.get("titulo", "").strip() or f"Aparência {indice}"
        referencia = referencia_imagem(imagem)
        destino = referencia
        if referencia and not referencia.startswith(("http://", "https://")):
            # Imagens locais só ficam disponíveis como attachment durante o
            # envio e o Discord não transforma `attachment://...` em link de
            # Markdown. A imagem principal é renderizada na embed; as demais
            # permanecem identificadas pelo título e podem ser abertas pelo
            # painel Imagem, evitando links quebrados no texto.
            destino = ""
        linhas.append(f"[{titulo}]({destino})" if destino else titulo)
    return "\n".join(linhas)


def anexos_ficha(ficha: FichaPersonagem) -> list[AnexoLocal]:
    anexos: list[AnexoLocal] = []
    # Uma única imagem é renderizada na publicação. As aparências secundárias
    # continuam registradas e acessíveis pelo painel Imagem, sem gerar
    # previews soltos de anexos no Discord.
    for indice, imagem in enumerate(ficha.imagens[:1], start=1):
        anexo = resolver_anexo(
            referencia_imagem(imagem),
            _prefixo_imagem_ficha(ficha.nome, imagem, indice),
        )
        if anexo is not None:
            anexos.append(anexo)
    return anexos


def embed_presets_autoridade(
    titulo: str,
    registros: list[dict[str, str]],
    tipo: str,
) -> discord.Embed:
    embed = discord.Embed(title=titulo)
    if not registros:
        embed.description = "Configuração pendente."
        return embed
    for _, categoria, pontos, faixa in categorias_presets_autoridade(tipo):
        motivos = [
            registro["motivo"]
            for registro in registros
            if registro.get("pontos") == str(pontos)
        ]
        if motivos:
            embed.add_field(
                name=f"{categoria} — {faixa}",
                value="\n".join(f"» {motivo}" for motivo in motivos),
                inline=False,
            )
    return embed


def montar_embeds_ficha(
    ficha: FichaPersonagem,
    *,
    apenas_aparencia_atual: bool = False,
) -> list[discord.Embed]:
    npc_alternativo = ficha.grupo == "NPCs" and ficha.tipo_npc not in {"", "Bruxo(a)"}
    espirito = ficha.tipo_npc == "Espírito"
    nome_identidade = ficha.nome if espirito else nome_com_estado_pv(ficha.nome, ficha.pv)
    identidade = discord.Embed(description=f"## 👤 {nome_identidade}")
    identidade.add_field(
        name="Tipo",
        value=(f"NPC • {ficha.tipo_npc}" if ficha.tipo_npc else ficha.grupo),
        inline=False,
    )
    if not espirito:
        identidade.add_field(
            name="Classe Social",
            value=f"{ficha.classe_social} — {ficha.galeoes} Galeões",
            inline=False,
        )
    if npc_alternativo:
        if ficha.especie_npc:
            identidade.add_field(name="Espécie", value=ficha.especie_npc, inline=True)
        identidade.add_field(name="Tamanho", value=ficha.altura, inline=True)
        identidade.add_field(name="Faixa de tamanho", value=ficha.faixa_tamanho_npc or "--", inline=True)
        if espirito:
            identidade.add_field(name="Anos no pós-vida", value=str(ficha.anos_pos_vida), inline=True)
            identidade.add_field(name="Manifestação Paranormal", value=f"+{ficha.manifestacao_paranormal}", inline=True)
    else:
        identidade.add_field(name="Casa", value=ficha.casa, inline=True)
        identidade.add_field(name="Herança Sanguínea", value=ficha.heranca, inline=True)
        identidade.add_field(name="Núcleo de Varinha", value=ficha.nucleo, inline=True)
    identidade.add_field(name="Lvl", value=str(ficha.nivel), inline=True)
    identidade.add_field(name="XP", value=str(ficha.xp), inline=True)
    if ficha.imagens:
        aplicar_imagem(
            identidade,
            referencia_imagem(ficha.imagens[0]),
            _prefixo_imagem_ficha(ficha.nome, ficha.imagens[0], 1),
        )
        identidade.add_field(
            name="Aparência",
            # Apenas a primeira imagem é renderizada, mas todas permanecem
            # listadas para que as aparências secundárias não desapareçam.
            value=linhas_imagens_ficha(ficha.imagens, ficha.nome),
            inline=False,
        )

    informacoes = discord.Embed(title="📋 Informações")
    if ficha.informacoes:
        informacoes_ordenadas = list(ficha.informacoes)
        ficha_de_aluno = ficha.grupo in (*CASAS, "Players")
        prioridade_informacoes = {
            normalizar_rotulo("Altura e Idade"): 1,
            normalizar_rotulo("Sobre"): 10_000,
        }
        if ficha.grupo in CASAS:
            prioridade_informacoes[normalizar_rotulo("Cursando")] = 0
        informacoes_ordenadas = [
            informacao
            for _, informacao in sorted(
                enumerate(informacoes_ordenadas),
                key=lambda item: (
                    prioridade_informacoes.get(
                        normalizar_rotulo(item[1].get("titulo", "")),
                        item[0] + 2,
                    ),
                    item[0],
                ),
            )
        ]
        for informacao in informacoes_ordenadas:
            descricao_informacao = informacao["descricao"]
            if normalizar_rotulo(informacao["titulo"]) == normalizar_rotulo("Vassoura"):
                # A ficha guarda a referência legível, mas o catálogo de vassouras
                # continua sendo a fonte do bônus exibido.
                from utils.quadribol import (
                    descricao_vassoura,
                    encontrar_vassoura,
                    modelo_vassoura_da_descricao,
                )

                modelo = encontrar_vassoura(
                    modelo_vassoura_da_descricao(descricao_informacao)
                )
                if modelo is not None:
                    descricao_informacao = descricao_vassoura(modelo)
            informacoes.add_field(
                name=informacao["titulo"],
                value=descricao_informacao,
                inline=(
                    ficha_de_aluno
                    and normalizar_rotulo(informacao["titulo"])
                    in {
                        normalizar_rotulo("Cursando"),
                        normalizar_rotulo("Altura e Idade"),
                    }
                ),
            )
    else:
        informacoes.description = "--"
    if ficha.grupo == "Figuras de Autoridade":
        catalogo_completo = (
            catalogo_autoridade_completo(ficha.gratificacoes_autoridade)
            and catalogo_autoridade_completo(ficha.penalidades_autoridade)
        )
        informacoes.add_field(
            name="Taça das Casas",
            value=(
                "Ativa — gratificações e penalidades configuradas."
                if catalogo_completo
                else "Pendente — não participa dos comandos da Taça."
            ),
            inline=False,
        )

    estatisticas = discord.Embed(title="📊 Estatísticas")
    if not espirito:
        estatisticas.add_field(name="Pontos de Vida", value=str(ficha.pv), inline=True)
    estatisticas.add_field(name="Pontos de Habilidade", value=str(ficha.ph), inline=True)
    estatisticas.add_field(name="Alma", value=f"{ficha.alma}%", inline=True)

    atributos = discord.Embed(
        title="📌 Atributos",
        description=(
            f"**Pontos de atributo disponíveis:** {ficha.pontos_atributo_disponiveis}\n\n"
            + "\n".join(
                (
                    f"> *{nome}: {ficha.atributos[nome]} "
                    f"{formatar_bonus(modificador(ficha.atributos[nome]))}*"
                    + (
                        f" **(+{ficha.bonus_atributos_temporarios.get(nome, 0)} temporário → "
                        f"{atributos_efetivos(ficha)[nome]} "
                        f"{formatar_bonus(modificador(atributos_efetivos(ficha)[nome]))})**"
                        if ficha.bonus_atributos_temporarios.get(nome, 0) > 0
                        else ""
                    )
                )

                for nome in ATRIBUTOS
            )
        ),
    )
    pericias = discord.Embed(
        title="📌 Perícias",
        description="\n".join(
            formatar_linha_pericia(ficha, nome)
            for nome in PERICIAS
        ),
    )
    aptidoes = discord.Embed(
        title="📖 Aptidões",
        description="\n".join(
            (
                f"> *{nome}: {formatar_bonus(aptidao_efetiva(ficha, nome))}*"
                + (
                    f" **(+{bonus_aptidoes_passivos(ficha).get(nome, 0)} de habilidade)**"
                    if bonus_aptidoes_passivos(ficha).get(nome, 0)
                    else ""
                )
            )
            for nome in APTIDOES
        ),
    )
    automaticos = resumo_automaticos(ficha)
    efeitos_ativos = [
        f"**{efeito['nome']}:** {efeito['efeito']}"
        + (f" — {efeito.get('duracao', '')}" if efeito.get("duracao") else "")
        for efeito in ficha.efeitos_habilidades_ativos
    ]
    habilidades = discord.Embed(
        title="💡 Habilidades",
        description=(
            f"> 🧬 **Evoluções de Herança:** {rotulo_evolucao_heranca(ficha.evolucao_heranca)}\n"
            + "> ✨ **Origens Mágicas:** "
            + (", ".join(ficha.origens_magicas) or "--")
            + "\n> 🎓 **Especializações:** "
            + (", ".join(ficha.especializacoes) or "--")
            + (
                "\n> " + resumo_efeitos_heranca(ficha).replace("\n", "\n> ")
                if resumo_efeitos_heranca(ficha)
                else ""
            )
            + (
                "\n\n> " + "\n> ".join(
                    f"⚙️ {efeito}" for efeito in automaticos
                )
                if automaticos else ""
            )
            + (
                "\n\n> ⏳ **Efeitos ativos**\n> " + "\n> ".join(efeitos_ativos)
                if efeitos_ativos else ""
            )
        ),
    )
    adicionar_efeitos_habilidades(habilidades, ficha)

    def embed_registros_npc(titulo: str, registros: list[dict[str, str]]) -> discord.Embed:
        return discord.Embed(
            title=titulo,
            description="\n\n".join(
                ficha_criaturas.formatar_registro(registro) for registro in registros
            ) or "--",
        )

    if npc_alternativo:
        habilidades = embed_registros_npc("💡 Habilidades", ficha.habilidades_npc)
    itens_partes = _fragmentar_embed_de_ficha(montar_embed_itens(ficha))
    feiticos = discord.Embed(title="🪄 Feitiços")
    if ficha.feiticos_favoritos:
        for feitico in ficha.feiticos_favoritos:
            feiticos.add_field(
                name=f"{feitico['nome']} ({feitico['categoria']})",
                value=feitico["descricao"],
                inline=False,
            )
    else:
        feiticos.description = "--"

    if ficha.grupo == "Figuras de Autoridade":
        feiticos.title = "📚 Grimório Pessoal"

    habilidades_partes = (
        []
        if npc_alternativo and not ficha.habilidades_npc
        else _fragmentar_embed_de_ficha(habilidades)
    )
    feiticos_partes = [] if npc_alternativo else _fragmentar_embed_de_ficha(feiticos)
    embeds = [
        identidade,
        informacoes,
    ]
    embeds.extend(itens_partes)
    embeds.extend([estatisticas, atributos, pericias])
    if not npc_alternativo:
        embeds.append(aptidoes)
    if npc_alternativo:
        for titulo, registros in (
            ("🗡️ Armas", ficha.armas_npc),
            ("⚔️ Ataques", ficha.ataques_npc),
        ):
            if registros:
                embeds.append(embed_registros_npc(titulo, registros))
    embeds.extend(habilidades_partes)
    if npc_alternativo:
        for titulo, registros in (
            ("💔 Fraquezas", ficha.fraquezas_npc),
            ("🛡️ Resistências", ficha.resistencias_npc),
        ):
            if registros:
                embeds.append(embed_registros_npc(titulo, registros))
    embeds.extend(feiticos_partes)
    return embeds


def _grupo_organizacao_embed(embed: discord.Embed) -> int:
    """Classifica as embeds nos blocos visuais definidos para a ficha.

    0: identidade, informações e itens
    1: estatísticas, atributos e perícias
    2: aptidões, habilidades e blocos mecânicos de NPCs
    3: feitiços ou Grimório Pessoal
    """
    titulo = embed.title or ""
    if titulo in {"🪄 Feitiços", "📚 Grimório Pessoal"}:
        return 3
    if titulo in {"📊 Estatísticas", "📌 Atributos", "📌 Perícias"}:
        return 1
    if titulo in {"Identidade", "📋 Informações", "🎒 Itens"} or not titulo:
        return 0
    return 2


def dividir_embeds_publicacao_personagem(
    ficha: FichaPersonagem,
    *,
    apenas_aparencia_atual: bool = True,
) -> tuple[list[discord.Embed], list[discord.Embed], list[discord.Embed]]:
    """Divide a ficha em até três mensagens ordenadas por blocos naturais.

    Cada embed continua inteira e na posição original. A divisão prioriza os
    limites Identidade/Itens » Estatísticas/Perícias » Aptidões/Habilidades
    » Grimório. Se um desses blocos sozinho for grande demais, a quebra ocorre
    dentro dele, isolando preferencialmente a parte com mais caracteres.
    """
    embeds = montar_embeds_ficha(
        ficha,
        apenas_aparencia_atual=apenas_aparencia_atual,
    )

    if not excede_limite_mensagem(embeds):
        return embeds, [], []

    for quantidade in (2, 3):
        partes = _melhor_particao_de_mensagem(embeds, quantidade)
        if partes is not None:
            partes += [[] for _ in range(3 - len(partes))]
            return partes[0], partes[1], partes[2]
    raise ValueError(
        "A ficha exige mais de três mensagens mesmo após separar suas embeds."
    )


def _melhor_particao_de_mensagem(
    embeds: list[discord.Embed],
    quantidade: int,
) -> list[list[discord.Embed]] | None:
    """Encontra uma divisão contígua nos limites naturais da ficha."""
    from itertools import combinations

    if quantidade < 1 or len(embeds) < quantidade:
        return None
    melhor: tuple[tuple[int, int, int, int], list[list[discord.Embed]]] | None = None
    for cortes in combinations(range(1, len(embeds)), quantidade - 1):
        limites = (0, *cortes, len(embeds))
        partes = [embeds[inicio:fim] for inicio, fim in zip(limites, limites[1:])]
        if any(excede_limite_mensagem(parte) for parte in partes):
            continue
        tamanhos = [sum(len(embed) for embed in parte) for parte in partes]
        cortes_internos = sum(
            _grupo_organizacao_embed(embeds[corte - 1])
            == _grupo_organizacao_embed(embeds[corte])
            for corte in cortes
        )
        pontuacao = (
            cortes_internos,
            max(tamanhos),
            max(tamanhos) - min(tamanhos),
            sum(tamanhos),
        )
        if melhor is None or pontuacao < melhor[0]:
            melhor = pontuacao, partes
    return melhor[1] if melhor else None


def dividir_embeds_ficha_interacao(
    ficha: FichaPersonagem,
) -> tuple[list[discord.Embed], list[discord.Embed], list[discord.Embed]]:
    """Usa exatamente a mesma divisão da publicação também no /ficha consultar."""
    embeds = montar_embeds_ficha(ficha)
    if not excede_limite_mensagem(embeds):
        return embeds, [], []
    return dividir_embeds_publicacao_personagem(
        ficha, apenas_aparencia_atual=False
    )


def montar_embeds_ficha_interacao(ficha: FichaPersonagem) -> list[discord.Embed]:
    principal, _, _ = dividir_embeds_ficha_interacao(ficha)
    return principal


def quantidade_partes_publicacao(ficha: FichaPersonagem) -> int:
    """Retorna quantas mensagens a ficha precisa na thread com a regra atual."""
    principal, parte_2, parte_3 = dividir_embeds_publicacao_personagem(ficha)
    return 1 + int(bool(parte_2)) + int(bool(parte_3))


def quantidade_partes_registradas(ficha: FichaPersonagem) -> int:
    """Retorna quantas mensagens da publicação atual estão registradas na ficha."""
    if not ficha.mensagem_discord_id:
        return 0
    return (
        1
        + int(bool(ficha.mensagem_discord_parte_2_id))
        + int(bool(ficha.mensagem_discord_parte_3_id))
    )


async def publicacao_precisa_migrar_layout(
    cliente: discord.Client,
    ficha: FichaPersonagem,
    principal: list[discord.Embed],
    parte_2: list[discord.Embed],
    parte_3: list[discord.Embed],
) -> bool:
    """Confere não só a quantidade, mas o CONTEÚDO de cada parte já publicada.

    Isso pega mudanças de regra como:
    antigo: principal | Grimório
    novo:   principal | Habilidades + Grimório

    Mesmo sendo 2 mensagens nos dois casos, o layout mudou e precisa ser
    recriado uma única vez.
    """
    if not ficha.mensagem_discord_id:
        return False

    destino = destino_personagem(ficha.grupo)
    canal = cliente.get_channel(destino)
    if canal is None:
        try:
            canal = await cliente.fetch_channel(destino)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return True
    if not hasattr(canal, "fetch_message"):
        return True

    esperadas = [
        (ficha.mensagem_discord_id, principal),
        (ficha.mensagem_discord_parte_2_id, parte_2),
        (ficha.mensagem_discord_parte_3_id, parte_3),
    ]

    for mensagem_id, embeds_esperados in esperadas:
        if not embeds_esperados:
            if mensagem_id:
                return True
            continue
        if not mensagem_id:
            return True
        try:
            mensagem = await canal.fetch_message(mensagem_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return True

        titulos_atuais = [embed.title or "" for embed in mensagem.embeds]
        titulos_esperados = [embed.title or "" for embed in embeds_esperados]
        if titulos_atuais != titulos_esperados:
            return True

    return False


async def localizar_parte_2_existente(
    cliente: discord.Client,
    thread_id: int,
    ficha: FichaPersonagem,
) -> int:
    """Tenta recuperar a antiga mensagem de Grimório quando o ID não foi salvo.

    Versões antigas do Grimory publicavam uma segunda mensagem sem persistir o
    ID dela na ficha. Procuramos logo após a mensagem principal e reutilizamos a
    primeira publicação do próprio bot que contenha o embed `Grimório Pessoal`.
    """
    if ficha.mensagem_discord_parte_2_id or not ficha.mensagem_discord_id:
        return ficha.mensagem_discord_parte_2_id
    canal = cliente.get_channel(thread_id)
    if canal is None:
        try:
            canal = await cliente.fetch_channel(thread_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return 0
    if not hasattr(canal, "fetch_message") or not hasattr(canal, "history"):
        return 0
    try:
        principal = await canal.fetch_message(ficha.mensagem_discord_id)
        async for mensagem in canal.history(limit=8, after=principal, oldest_first=True):
            # Ao alcançar a próxima ficha publicada pelo bot, encerramos a busca.
            if (
                getattr(cliente, "user", None)
                and mensagem.author.id == cliente.user.id
                and "_Ficha de Personagem •" in (mensagem.content or "")
            ):
                break
            if getattr(cliente, "user", None) and mensagem.author.id != cliente.user.id:
                continue
            if (mensagem.content or "").strip() == f"## {ficha.nome} parte 2":
                return mensagem.id
            if any(embed.title == "📚 Grimório Pessoal" for embed in mensagem.embeds):
                return mensagem.id
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        return 0
    return 0


async def publicar_personagem_em_partes(
    cliente: discord.Client,
    ficha: FichaPersonagem,
) -> tuple[
    discord.Message,
    discord.Message | None,
    discord.Message | None,
]:
    destino = destino_personagem(ficha.grupo)
    principal, parte_2, parte_3 = dividir_embeds_publicacao_personagem(ficha)

    quantidade_necessaria = 1 + bool(parte_2) + bool(parte_3)
    quantidade_registrada = (
        1
        + bool(ficha.mensagem_discord_parte_2_id)
        + bool(ficha.mensagem_discord_parte_3_id)
        if ficha.mensagem_discord_id
        else 0
    )

    # Se a ficha passou a exigir mais mensagens do que a publicação atualmente
    # registrada, recria SOMENTE a publicação dessa ficha uma única vez.
    # Os novos IDs são persistidos logo depois por sincronizar_publicacao_personagem.
    transicionando = bool(
        ficha.mensagem_discord_id
        and quantidade_necessaria > quantidade_registrada
    )

    principal_id = ficha.mensagem_discord_id
    parte_2_id = ficha.mensagem_discord_parte_2_id
    parte_3_id = ficha.mensagem_discord_parte_3_id

    if transicionando:
        for mensagem_id in (principal_id, parte_2_id, parte_3_id):
            if mensagem_id:
                await excluir_publicacao_ficha(
                    cliente,
                    destino,
                    mensagem_id,
                )
        principal_id = 0
        parte_2_id = 0
        parte_3_id = 0

    mensagem_principal = await publicar_ou_atualizar_ficha(
        cliente,
        destino,
        principal,
        principal_id,
        cabecalho_personagem(
            nome_com_estado_pv(ficha.nome, ficha.pv),
            ficha.grupo,
        ),
        anexos=anexos_ficha(ficha),
    )

    mensagem_parte_2: discord.Message | None = None
    if parte_2:
        mensagem_parte_2 = await publicar_ou_atualizar_ficha(
            cliente,
            destino,
            parte_2,
            parte_2_id,
            cabecalho_personagem_parte_2(ficha.nome),
        )
    elif parte_2_id:
        await excluir_publicacao_ficha(cliente, destino, parte_2_id)

    mensagem_parte_3: discord.Message | None = None
    if parte_3:
        mensagem_parte_3 = await publicar_ou_atualizar_ficha(
            cliente,
            destino,
            parte_3,
            parte_3_id,
            "",
        )
    elif parte_3_id:
        await excluir_publicacao_ficha(cliente, destino, parte_3_id)

    return mensagem_principal, mensagem_parte_2, mensagem_parte_3


def limite_temporario_de_edicoes(erro: BaseException) -> bool:
    atual: BaseException | None = erro
    visitados: set[int] = set()
    while atual is not None and id(atual) not in visitados:
        visitados.add(id(atual))
        if getattr(atual, "code", None) == 30046 or "30046" in str(atual):
            return True
        atual = atual.__cause__ or atual.__context__
    return False


async def sincronizar_publicacao_pendente(
    cliente: discord.Client,
    caminho: Path,
) -> None:
    # O código 30046 usa uma janela de uma hora para mensagens antigas.
    # Esperar um pouco além dela evita novas tentativas que só prolongariam o bloqueio.
    for espera in (65 * 60, 30 * 60, 60 * 60):
        await asyncio.sleep(espera)
        try:
            ficha = FichaPersonagem.carregar(caminho)
            await publicar_personagem_em_partes(
                cliente,
                ficha,
            )
            return
        except (ErroPublicacaoFicha, OSError, ValueError) as erro:
            if not limite_temporario_de_edicoes(erro):
                return


def agendar_sincronizacao_pendente(
    cliente: discord.Client,
    caminho: Path,
) -> None:
    chave = caminho.resolve()
    existente = TAREFAS_SINCRONIZACAO_PENDENTE.get(chave)
    if existente is not None and not existente.done():
        return
    tarefa = asyncio.create_task(sincronizar_publicacao_pendente(cliente, caminho))
    TAREFAS_SINCRONIZACAO_PENDENTE[chave] = tarefa

    def limpar(_: asyncio.Task[None]) -> None:
        if TAREFAS_SINCRONIZACAO_PENDENTE.get(chave) is tarefa:
            TAREFAS_SINCRONIZACAO_PENDENTE.pop(chave, None)

    tarefa.add_done_callback(limpar)


async def sincronizar_publicacao_personagem(
    interaction: discord.Interaction,
    ficha: FichaPersonagem,
    caminho: Path,
) -> None:
    try:
        mensagem, mensagem_parte_2, mensagem_parte_3 = (
            await publicar_personagem_em_partes(interaction.client, ficha)
        )
        parte_2_id = mensagem_parte_2.id if mensagem_parte_2 else 0
        parte_3_id = mensagem_parte_3.id if mensagem_parte_3 else 0
        if (
            ficha.mensagem_discord_id != mensagem.id
            or ficha.mensagem_discord_parte_2_id != parte_2_id
            or ficha.mensagem_discord_parte_3_id != parte_3_id
        ):
            lock = LOCKS_FICHA.setdefault(caminho.resolve(), asyncio.Lock())
            async with lock:
                atual = FichaPersonagem.carregar(caminho)
                atual.mensagem_discord_id = mensagem.id
                atual.mensagem_discord_parte_2_id = parte_2_id
                atual.mensagem_discord_parte_3_id = parte_3_id
                salvar_ficha(atual, caminho)
            ficha.mensagem_discord_id = mensagem.id
            ficha.mensagem_discord_parte_2_id = parte_2_id
            ficha.mensagem_discord_parte_3_id = parte_3_id
    except (ErroPublicacaoFicha, OSError, ValueError) as erro:
        if limite_temporario_de_edicoes(erro):
            agendar_sincronizacao_pendente(interaction.client, caminho)
            await interaction.followup.send(
                "A ficha foi salva. O Discord atingiu o limite temporário de edições "
                "de mensagens antigas; a publicação na thread será atualizada "
                "automaticamente quando esse limite for liberado.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"A ficha foi salva, mas não consegui sincronizar sua mensagem na thread: {erro}",
                ephemeral=True,
            )
    try:
        resultado = await sincronizar_publicacoes_narrativas(
            interaction.client,
            ficha,
            caminho,
        )
        ids_alterados = (
            ficha.mensagem_narrativa_discord_id != resultado.mensagem_narrativa_id
            or ficha.mensagem_time_discord_id != resultado.mensagem_time_id
        )
        if ids_alterados:
            lock = LOCKS_FICHA.setdefault(caminho.resolve(), asyncio.Lock())
            async with lock:
                atual = FichaPersonagem.carregar(caminho)
                atual.mensagem_narrativa_discord_id = resultado.mensagem_narrativa_id
                atual.mensagem_time_discord_id = resultado.mensagem_time_id
                salvar_ficha(atual, caminho)
            ficha.mensagem_narrativa_discord_id = resultado.mensagem_narrativa_id
            ficha.mensagem_time_discord_id = resultado.mensagem_time_id
        if resultado.pendencias:
            await interaction.followup.send(
                "A ficha foi salva, mas a versão narrativa aguarda: "
                + "; ".join(resultado.pendencias),
                ephemeral=True,
            )
    except (ErroPublicacaoFicha, OSError, ValueError) as erro:
        await interaction.followup.send(
            f"A ficha foi salva, mas não consegui sincronizar sua versão narrativa: {erro}",
            ephemeral=True,
        )


def validar_tamanho_ficha(ficha: FichaPersonagem) -> None:
    embeds = montar_embeds_ficha(ficha)
    dividir_embeds_publicacao_personagem(ficha, apenas_aparencia_atual=False)
    for embed in embeds:
        if len(embed.fields) > 25:
            raise ValueError(
                f"A embed {embed.title or 'sem título'} ultrapassou o limite de 25 campos."
            )
        for campo in embed.fields:
            if len(campo.value) > 1024:
                raise ValueError(
                    f"O campo {campo.name} ultrapassou o limite de 1.024 caracteres."
                )


class ViewAutor(discord.ui.View):
    def __init__(self, usuario_id: int):
        super().__init__(timeout=TEMPO_FLUXO)
        self.usuario_id = usuario_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message(
            "Somente quem abriu este `/ficha` pode usar estes controles.",
            ephemeral=True,
        )
        return False


class CriarFichaModal(discord.ui.Modal):
    def __init__(self, usuario_id: int, grupo: str = ""):
        super().__init__(title="Criar ficha — informe o nome")
        self.usuario_id = usuario_id
        self.grupo = grupo
        self.nome = discord.ui.TextInput(label="Nome da ficha", max_length=100)
        self.add_item(self.nome)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        nome = str(self.nome.value).strip()
        if not nome:
            await interaction.response.send_message(
                "Informe um nome para criar a ficha.",
                ephemeral=True,
            )
            return

        sessao = SessaoFicha(usuario_id=self.usuario_id, nome=nome, grupo=self.grupo)
        if not self.grupo:
            await interaction.response.send_message(
                embed=embed_painel("➕ Criar ficha", "Escolha onde esta ficha será organizada."),
                view=SelecaoCriacaoView(sessao, "grupo", opcoes_texto(GRUPOS_FICHA)),
                ephemeral=True,
            )
            return

        if self.grupo == "NPCs":
            await interaction.response.edit_message(
                embed=embed_painel(
                    "👥 Tipo de NPC",
                    "Escolha qual estrutura de ficha será usada para este NPC.",
                ),
                view=SelecaoCriacaoView(
                    sessao,
                    "tipo_npc",
                    [
                        discord.SelectOption(
                            label=tipo,
                            value=tipo,
                            description={
                                "Bruxo(a)": "Usa a ficha mágica padrão com Herança, Casa, Núcleo e Aptidões.",
                                "Humano/Trouxa": "Usa nível, atributos, perícias, PH e recursos físicos sem magia.",
                                "Semi-Humano": "Usa a ficha humanoide e registra sua espécie e características raciais.",
                                "Espírito": "Usa Alma, PH, Intangibilidade e Manifestação Paranormal.",
                            }[tipo],
                        )
                        for tipo in TIPOS_NPC
                    ],
                ),
            )
            return

        if self.grupo == "Players":
            await interaction.response.edit_message(
                embed=embed_painel(
                    "👤 Titular da ficha",
                    "Selecione o membro que será dono da ficha e poderá acessá-la nos comandos pessoais.",
                ),
                view=TitularPlayerView(sessao),
            )
            return

        await mostrar_niveis_criacao(interaction, sessao)


async def mostrar_niveis_criacao(
    interaction: discord.Interaction,
    sessao: SessaoFicha,
) -> None:
    titular = (
        f"\n\n**Titular:** <@{sessao.titular_id}>"
        if sessao.grupo == "Players" and sessao.titular_id
        else ""
    )
    await interaction.response.edit_message(
        embed=embed_painel(
            "🔢 Nível inicial",
            f"Escolha o nível em que o personagem começará.{titular}",
        ),
        view=SelecaoCriacaoView(
            sessao,
            "nivel",
            [
                discord.SelectOption(
                    label=f"Nível {nivel}",
                    value=str(nivel),
                    description=f"{pontos_criacao_por_nivel(nivel)} pontos para distribuir nos atributos",
                )
                for nivel in range(NIVEL_INICIAL_MINIMO, NIVEL_INICIAL_MAXIMO + 1)
            ],
        ),
    )


class TitularPlayerView(ViewAutor):
    def __init__(self, sessao: SessaoFicha):
        super().__init__(sessao.usuario_id)
        self.sessao = sessao
        seletor = discord.ui.UserSelect(
            placeholder="Selecione o titular da ficha",
            min_values=1,
            max_values=1,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        titular = self.seletor.values[0]
        self.sessao.titular_id = int(titular.id)
        await mostrar_niveis_criacao(interaction, self.sessao)


class DetalhesNPCModal(discord.ui.Modal):
    def __init__(self, sessao: SessaoFicha):
        super().__init__(title=f"Criar NPC — {sessao.tipo_npc}"[:45])
        self.sessao = sessao
        self.tamanho = discord.ui.TextInput(
            label="Tamanho exato",
            placeholder="Ex.: 1,78 m, 178 ou 178 cm",
            max_length=30,
        )
        self.add_item(self.tamanho)
        self.especie = None
        self.anos = None
        if sessao.tipo_npc == "Semi-Humano":
            self.especie = discord.ui.TextInput(
                label="Espécie",
                placeholder="Ex.: Veela",
                max_length=100,
            )
            self.add_item(self.especie)
        if sessao.tipo_npc == "Espírito":
            self.anos = discord.ui.TextInput(
                label="Anos no pós-vida",
                placeholder="Cada aniversário concede +1 de Manifestação Paranormal",
                max_length=5,
            )
            self.add_item(self.anos)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            tamanho = normalizar_tamanho(str(self.tamanho.value))
            faixa = faixa_tamanho_automatica(tamanho)
            anos = 0
            if self.anos is not None:
                anos = int(str(self.anos.value).strip())
                if anos < 0:
                    raise ValueError("Os anos no pós-vida não podem ser negativos.")
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        self.sessao.tamanho_npc = tamanho
        self.sessao.faixa_tamanho_npc = faixa
        self.sessao.anos_pos_vida = anos
        if self.especie is not None:
            self.sessao.especie_npc = str(self.especie.value).strip()
            if not self.sessao.especie_npc:
                await interaction.response.send_message("Informe a espécie do NPC semi-humano.", ephemeral=True)
                return
        await interaction.response.edit_message(
            embed=embed_atributos(
                self.sessao,
                pontos_criacao_por_nivel(self.sessao.nivel),
            ),
            view=AtributosCriacaoView(self.sessao),
        )


class SelecaoCriacaoView(ViewAutor):
    def __init__(self, sessao: SessaoFicha, etapa: str, opcoes: list[discord.SelectOption]):
        super().__init__(sessao.usuario_id)
        self.sessao = sessao
        self.etapa = etapa
        seletor = discord.ui.Select(placeholder="Escolha uma opção", options=opcoes)
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        valor = self.seletor.values[0]
        if self.etapa == "grupo":
            self.sessao.grupo = valor
            if valor == "NPCs":
                await interaction.response.edit_message(
                    embed=embed_painel(
                        "👥 Tipo de NPC",
                        "Escolha qual estrutura de ficha será usada para este NPC.",
                    ),
                    view=SelecaoCriacaoView(
                        self.sessao,
                        "tipo_npc",
                        [
                            discord.SelectOption(
                                label=tipo,
                                value=tipo,
                                description={
                                    "Bruxo(a)": "Usa a ficha mágica padrão com Herança, Casa, Núcleo e Aptidões.",
                                    "Humano/Trouxa": "Usa nível, atributos, perícias, PH e recursos físicos sem magia.",
                                    "Semi-Humano": "Usa a ficha humanoide e registra sua espécie e características raciais.",
                                    "Espírito": "Usa Alma, PH, Intangibilidade e Manifestação Paranormal.",
                                }[tipo],
                            )
                            for tipo in TIPOS_NPC
                        ],
                    ),
                )
                return
            if valor == "Players":
                await interaction.response.edit_message(
                    embed=embed_painel(
                        "👤 Titular da ficha",
                        "Selecione o membro que será dono da ficha e poderá acessá-la nos comandos pessoais.",
                    ),
                    view=TitularPlayerView(self.sessao),
                )
                return
            await self.mostrar_niveis(interaction)
            return
        if self.etapa == "tipo_npc":
            self.sessao.tipo_npc = valor
            await self.mostrar_niveis(interaction)
            return
        if self.etapa == "nivel":
            self.sessao.nivel = int(valor)
            if npc_nao_magico(self.sessao):
                await interaction.response.send_modal(DetalhesNPCModal(self.sessao))
                return
            herancas = listar_habilidades("heranca_sanguinea")
            if not herancas:
                await interaction.response.send_message("A biblioteca não possui Heranças Sanguíneas.", ephemeral=True)
                return
            await interaction.response.edit_message(
                embed=embed_painel("🧬 Herança Sanguínea", "Escolha a herança do personagem."),
                view=SelecaoCriacaoView(self.sessao, "heranca", opcoes_texto(herancas)),
            )
            return
        if self.etapa == "heranca":
            self.sessao.heranca = valor
            if self.sessao.grupo in CASAS:
                self.sessao.casa = self.sessao.grupo
                await self.mostrar_nucleos(interaction)
            else:
                await interaction.response.edit_message(
                    embed=embed_painel("🏰 Casa de Hogwarts", "Escolha a Casa do personagem."),
                    view=SelecaoCriacaoView(self.sessao, "casa", opcoes_texto(listar_casas())),
                )
            return
        if self.etapa == "casa":
            self.sessao.casa = valor
            await self.mostrar_nucleos(interaction)
            return
        self.sessao.nucleo = valor
        pontos_criacao = pontos_criacao_por_nivel(self.sessao.nivel)
        await interaction.response.edit_message(
            embed=embed_atributos(self.sessao, pontos_criacao),
            view=AtributosCriacaoView(self.sessao),
        )

    async def mostrar_niveis(self, interaction: discord.Interaction) -> None:
        await mostrar_niveis_criacao(interaction, self.sessao)

    async def mostrar_nucleos(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel("🪄 Núcleo de Varinha", "Escolha o núcleo da varinha."),
            view=SelecaoCriacaoView(self.sessao, "nucleo", opcoes_nucleos()),
        )


def embed_atributos(sessao: SessaoFicha, restantes: int) -> discord.Embed:
    pontos_criacao = pontos_criacao_por_nivel(sessao.nivel)
    return embed_painel(
        "📌 Atributos",
        "Use os botões para distribuir os pontos. Cada ponto retirado de um atributo fica disponível para outro. "
        f"O valor mínimo é {ATRIBUTO_MINIMO_PERSONAGEM}; após concluir a ficha, esta distribuição não poderá ser revertida."
        f"\n\n**Nível inicial:** {sessao.nivel}"
        f"\n**Pontos de criação:** {pontos_criacao}\n\n"
        + "\n".join(
            f"> **{nome}:** {sessao.atributos[nome]} {formatar_bonus(modificador(sessao.atributos[nome]))}"
            for nome in ATRIBUTOS
        )
        + f"\n\n**Pontos restantes:** {restantes}",
    )


def atributo_por_nome(valor: str) -> str:
    chave = normalizar_rotulo(valor)
    for atributo in ATRIBUTOS:
        if normalizar_rotulo(atributo) == chave:
            return atributo
    raise ValueError("Escolha um atributo válido: Força, Destreza, Constituição, Inteligência, Sabedoria ou Carisma.")


class QuantidadeAtributoModal(discord.ui.Modal, title="Distribuir atributos"):
    def __init__(self, view, atributo: str):
        super().__init__()
        self.view_origem = view
        self.atributo_escolhido = atributo
        self.quantidade = discord.ui.TextInput(
            label="Valor",
            placeholder=self._placeholder(view),
            required=True,
            max_length=4,
        )
        self.add_item(self.quantidade)

    @staticmethod
    def _placeholder(view) -> str:
        return f"Entre -6 e {max(0, view.restantes)}."

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            atributo = self.atributo_escolhido
            delta = int(str(self.quantidade.value).strip())
            if delta == 0:
                raise ValueError("Informe uma quantidade diferente de zero.")
            view = self.view_origem
            async with view.bloqueio_atributos:
                if isinstance(view, AtributosCriacaoView):
                    atual = view.sessao.atributos[atributo]
                    minimo = ATRIBUTO_MINIMO_PERSONAGEM
                elif isinstance(view, AtributosMercadoView):
                    atual = view.ficha.atributos[atributo]
                    minimo = (
                        ATRIBUTO_MINIMO_PERSONAGEM
                        if view.configuracao_inicial_autoridade
                        else view.originais[atributo]
                    )
                else:
                    raise ValueError("Esta distribuição de atributos não está mais disponível.")
                if delta > 0 and delta > view.restantes:
                    raise ValueError(f"Você possui apenas {view.restantes} ponto(s) restante(s).")
                if delta < 0 and atual + delta < minimo:
                    raise ValueError(f"O atributo não pode ficar abaixo de {minimo}.")
                if isinstance(view, AtributosCriacaoView):
                    view.sessao.atributos[atributo] = atual + delta
                else:
                    view.ficha.atributos[atributo] = atual + delta
                view.restantes -= delta
                view.atualizar_botoes()
                embed = (
                    embed_atributos(view.sessao, view.restantes)
                    if isinstance(view, AtributosCriacaoView)
                    else embed_atributos_mercado(
                        view.ficha,
                        view.restantes,
                        nivel_destino=view.nivel_destino,
                        custo_nivel=view.custo_nivel,
                    )
                )
                await interaction.edit_original_response(embed=embed, view=view)
        except (TypeError, ValueError) as erro:
            await interaction.followup.send(str(erro), ephemeral=True)


class BotaoAtributo(discord.ui.Button):
    def __init__(self, atributo: str, delta: int, row: int):
        super().__init__(label=atributo, style=discord.ButtonStyle.secondary, row=row)
        self.atributo = atributo
        # Mantido como metadado de compatibilidade para integrações antigas;
        # o valor real agora é informado pelo modal.
        self.delta = -1

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, AtributosCriacaoView):
            await interaction.response.defer()
            return
        await interaction.response.send_modal(
            QuantidadeAtributoModal(view, self.atributo)
        )


class AtributosCriacaoView(ViewAutor):
    def __init__(self, sessao: SessaoFicha):
        super().__init__(sessao.usuario_id)
        self.sessao = sessao
        self.bloqueio_atributos = asyncio.Lock()
        self.restantes = pontos_criacao_por_nivel(sessao.nivel) - sum(
            valor - 10 for valor in sessao.atributos.values()
        )
        for indice, atributo in enumerate(ATRIBUTOS):
            self.add_item(BotaoAtributo(atributo, 0, indice // 2))
        confirmar = discord.ui.Button(label="Confirmar atributos", style=discord.ButtonStyle.success, row=3)
        confirmar.callback = self.confirmar
        self.confirmar_botao = confirmar
        self.add_item(confirmar)
        self.atualizar_botoes()

    def atualizar_botoes(self) -> None:
        for item in self.children:
            if isinstance(item, BotaoAtributo):
                item.disabled = False
        self.confirmar_botao.disabled = self.restantes != 0

    async def confirmar(self, interaction: discord.Interaction) -> None:
        if npc_nao_magico(self.sessao):
            await interaction.response.edit_message(
                embed=embed_painel(
                    "📌 Perícias treinadas",
                    "Escolha a primeira de duas perícias treinadas.",
                ),
                view=PericiaLivreView(self.sessao, 0),
            )
            return
        opcoes = pericias_da_casa(self.sessao.casa)
        if len(opcoes) != 2:
            await interaction.response.send_message("A Casa não possui exatamente duas perícias cadastradas.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=embed_painel("📌 Perícia da Casa", "Escolha uma das duas perícias recebidas gratuitamente."),
            view=PericiaCasaView(self.sessao, opcoes_texto(opcoes)),
        )


class PericiaCasaView(ViewAutor):
    def __init__(self, sessao: SessaoFicha, opcoes: list[discord.SelectOption]):
        super().__init__(sessao.usuario_id)
        self.sessao = sessao
        seletor = discord.ui.Select(placeholder="Escolha a perícia da Casa", options=opcoes)
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        self.sessao.pericia_casa = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=embed_painel("📌 Perícias treinadas", "Escolha a primeira de duas perícias adicionais."),
            view=PericiaLivreView(self.sessao, 0),
        )


class PericiaLivreView(ViewAutor):
    def __init__(self, sessao: SessaoFicha, pagina: int):
        super().__init__(sessao.usuario_id)
        self.sessao = sessao
        disponiveis = [
            nome for nome in PERICIAS
            if nome != sessao.pericia_casa and nome not in sessao.pericias_livres
        ]
        self.paginas = paginas_pericias(disponiveis)
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        rotulo_pagina, pericias_pagina = self.paginas[self.pagina]
        seletor = discord.ui.Select(
            placeholder=f"Perícias — {rotulo_pagina}",
            options=opcoes_texto(pericias_pagina),
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        if len(self.paginas) > 1:
            anterior = discord.ui.Button(label="Anterior", style=discord.ButtonStyle.secondary, disabled=self.pagina == 0, row=1)
            proxima = discord.ui.Button(label="Próxima", style=discord.ButtonStyle.secondary, disabled=self.pagina == len(self.paginas) - 1, row=1)
            anterior.callback = self.anterior
            proxima.callback = self.proxima
            self.add_item(anterior)
            self.add_item(proxima)

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=PericiaLivreView(self.sessao, self.pagina - 1))

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=PericiaLivreView(self.sessao, self.pagina + 1))

    async def selecionar(self, interaction: discord.Interaction) -> None:
        self.sessao.pericias_livres.append(self.seletor.values[0])
        if len(self.sessao.pericias_livres) < 2:
            await interaction.response.edit_message(
                embed=embed_painel("📌 Perícias treinadas", "Escolha a segunda perícia adicional."),
                view=PericiaLivreView(self.sessao, 0),
            )
            return
        if self.sessao.tipo_npc == "Espírito":
            self.sessao.classe_social = "--"
            self.sessao.galeoes = 0
            ficha = ficha_da_sessao(self.sessao)
            await interaction.response.edit_message(
                embeds=montar_embeds_ficha(ficha),
                view=ConfirmarFichaView(self.sessao),
            )
            return
        if npc_nao_magico(self.sessao):
            await mostrar_rolagem_social(interaction, self.sessao)
            return
        _, escolhas, _ = dados_nucleo(self.sessao.nucleo)
        if escolhas:
            await interaction.response.edit_message(
                embed=embed_painel("🪄 Aptidões do Núcleo", f"Escolha {escolhas} aptidões mágicas diferentes."),
                view=AptidoesNucleoView(self.sessao, escolhas),
            )
        else:
            await mostrar_rolagem_social(interaction, self.sessao)


class AptidoesNucleoView(ViewAutor):
    def __init__(self, sessao: SessaoFicha, quantidade: int):
        super().__init__(sessao.usuario_id)
        self.sessao = sessao
        self.quantidade = quantidade
        seletor = discord.ui.Select(
            placeholder=f"Escolha {quantidade} aptidões",
            options=opcoes_texto(APTIDOES),
            min_values=quantidade,
            max_values=quantidade,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        self.sessao.aptidoes_nucleo = list(self.seletor.values)
        await mostrar_rolagem_social(interaction, self.sessao)


async def mostrar_rolagem_social(interaction: discord.Interaction, sessao: SessaoFicha) -> None:
    await interaction.response.edit_message(
        embed=embed_painel(
            "💰 Classe Social",
            "A criação mecânica foi concluída. Faça a rolagem de classe social antes de salvar a ficha.",
        ),
        view=RolagemSocialView(sessao),
    )


class RolagemSocialView(ViewAutor):
    def __init__(self, sessao: SessaoFicha):
        super().__init__(sessao.usuario_id)
        self.sessao = sessao
        seletor = discord.ui.Select(
            placeholder="Ou escolha a classe social",
            options=[
                discord.SelectOption(
                    label=classe,
                    value=classe,
                    description=f"Inicia com {galeoes} Galeões",
                )
                for classe, galeoes in CLASSES_SOCIAIS.items()
            ],
            row=0,
        )
        seletor.callback = self.escolher
        self.seletor = seletor
        self.add_item(seletor)

    async def escolher(self, interaction: discord.Interaction) -> None:
        classe = self.seletor.values[0]
        self.sessao.rolagem_social = 0
        self.sessao.modificador_social = 0
        self.sessao.classe_social = classe
        self.sessao.galeoes = CLASSES_SOCIAIS[classe]
        ficha = ficha_da_sessao(self.sessao)
        embeds = montar_embeds_ficha(ficha)
        embeds[0].set_author(name=f"Classe Social escolhida: {classe}")
        await interaction.response.edit_message(
            embeds=embeds,
            view=ConfirmarFichaView(self.sessao),
        )

    @discord.ui.button(label="Rolar 1d6", style=discord.ButtonStyle.primary, emoji="🎲", row=1)
    async def rolar(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        rolagem = secrets.randbelow(6) + 1
        penalidade = -1 if normalizar_rotulo(self.sessao.heranca) == "nascido-trouxa" else 0
        total = rolagem + penalidade
        classe, galeoes = classe_social_por_total(total)
        self.sessao.rolagem_social = rolagem
        self.sessao.modificador_social = penalidade
        self.sessao.classe_social = classe
        self.sessao.galeoes = galeoes
        ficha = ficha_da_sessao(self.sessao)
        embeds = montar_embeds_ficha(ficha)
        embeds[0].set_author(name=f"🎲 Classe Social: {rolagem}{formatar_bonus(penalidade)} → {classe}")
        await interaction.response.edit_message(
            embeds=embeds,
            view=ConfirmarFichaView(self.sessao),
        )


class ConfirmarFichaView(ViewAutor):
    def __init__(self, sessao: SessaoFicha):
        super().__init__(sessao.usuario_id)
        self.sessao = sessao
        self.concluido = False

    @discord.ui.button(label="Concluir ficha", style=discord.ButtonStyle.success, emoji="✅")
    async def concluir(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        if self.concluido:
            await interaction.response.send_message("Esta criação já foi encerrada.", ephemeral=True)
            return
        try:
            caminho = caminho_nova_ficha(self.sessao.grupo, self.sessao.nome)
            if caminho.exists():
                await interaction.response.send_message("Já existe uma ficha com esse nome nesse grupo.", ephemeral=True)
                return
            ficha = ficha_da_sessao(self.sessao)
            salvar_ficha(ficha, caminho, nova=True)
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(f"Não foi possível salvar a ficha: {erro}", ephemeral=True)
            return
        self.concluido = True
        self.stop()
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, caminho),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, caminho)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def cancelar(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            embed=embed_painel("🗑️ Criação cancelada", "Nenhuma ficha foi salva."),
            view=None,
        )


def custo_pericia(atual: int, alvo: int) -> int:
    return sum(CUSTOS_RANK[rank] for rank in RANKS_PERICIA if atual < rank <= alvo)


class FichaAtualView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__(usuario_id)
        self.caminho = caminho
        ficha = FichaPersonagem.carregar(caminho)
        npc_alternativo = ficha.grupo == "NPCs" and ficha.tipo_npc not in {"", "Bruxo(a)"}
        if npc_alternativo:
            for item in list(self.children):
                if isinstance(item, discord.ui.Button) and item.label in {
                    "Feitiço", "Modificar Feitiço"
                }:
                    self.remove_item(item)
                elif isinstance(item, discord.ui.Button) and item.label in {
                    "Imagem", "Info", "Modificar Info"
                }:
                    self.remove_item(item)
                    item.row = 2
                    self.add_item(item)
                elif isinstance(item, discord.ui.Button) and item.label in {
                    "Item", "Modificar Item"
                }:
                    self.remove_item(item)
                    item.row = 3
                    self.add_item(item)
            habilidades_npc = discord.ui.Button(
                label="Habilidades",
                style=discord.ButtonStyle.secondary,
                emoji="✨",
                row=1,
            )
            habilidades_npc.callback = self.gerenciar_habilidades_npc
            armas_npc = discord.ui.Button(
                label="Armas", style=discord.ButtonStyle.secondary, emoji="🗡️", row=1
            )
            ataques_npc = discord.ui.Button(
                label="Ataques", style=discord.ButtonStyle.secondary, emoji="⚔️", row=1
            )
            armas_npc.callback = self.gerenciar_armas_npc
            ataques_npc.callback = self.gerenciar_ataques_npc
            self.add_item(armas_npc)
            self.add_item(ataques_npc)
            self.add_item(habilidades_npc)
        if ficha.grupo == "Figuras de Autoridade":
            gratificacoes = discord.ui.Button(
                label="Gratificações",
                style=discord.ButtonStyle.secondary,
                emoji="🏆",
                row=0,
            )
            penalidades = discord.ui.Button(
                label="Penalidades",
                style=discord.ButtonStyle.secondary,
                emoji="⚠️",
                row=0,
            )
            gratificacoes.callback = self.editar_gratificacoes
            penalidades.callback = self.editar_penalidades
            self.add_item(gratificacoes)
            self.add_item(penalidades)

    @discord.ui.button(label="Imagem", style=discord.ButtonStyle.secondary, emoji="🖼️", row=1)
    async def gerenciar_imagens(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🖼️ Imagens",
                "Escolha se deseja adicionar ou remover uma imagem da ficha.",
            ),
            view=ImagemFichaView(
                self.usuario_id,
                self.caminho,
            ),
        )

    async def abrir_editor_presets(
        self,
        interaction: discord.Interaction,
        tipo: str,
    ) -> None:
        titulo = "Gratificações" if tipo == "gratificacoes" else "Penalidades"
        ficha = FichaPersonagem.carregar(self.caminho)
        registros = (
            ficha.gratificacoes_autoridade
            if tipo == "gratificacoes"
            else ficha.penalidades_autoridade
        )
        await interaction.response.edit_message(
            embed=embed_presets_autoridade(
                f"{'\ud83c\udfc6' if tipo == 'gratificacoes' else '\u26a0\ufe0f'} {titulo}",
                registros,
                tipo,
            ),
            view=PresetsAutoridadeView(
                self.usuario_id,
                self.caminho,
                tipo,
            ),
        )

    async def editar_gratificacoes(self, interaction: discord.Interaction) -> None:
        await self.abrir_editor_presets(interaction, "gratificacoes")

    async def editar_penalidades(self, interaction: discord.Interaction) -> None:
        await self.abrir_editor_presets(interaction, "penalidades")

    async def gerenciar_habilidades_npc(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "✨ Habilidades do NPC",
                "Adicione, modifique ou remova habilidades registradas nesta ficha.",
            ),
            view=GerenciarHabilidadesNPCView(self.usuario_id, self.caminho),
        )

    async def gerenciar_armas_npc(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel("🗡️ Armas do NPC","Adicione, modifique ou remova armas desta ficha."),
            view=GerenciarCombateNPCView(self.usuario_id,self.caminho,"arma"),
        )

    async def gerenciar_ataques_npc(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel("⚔️ Ataques do NPC","Adicione, modifique ou remova ataques desta ficha."),
            view=GerenciarCombateNPCView(self.usuario_id,self.caminho,"ataque"),
        )

    async def mecanicas_heranca(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_mecanicas_heranca(ficha),
            view=MecanicasSanguePuroView(
                self.usuario_id,
                self.caminho,
                ficha,
            ),
        )

    @discord.ui.button(label="Mercado de XP", style=discord.ButtonStyle.primary, emoji="🛒", row=0)
    async def mercado(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "🛒 Mercado de XP",
                f"**{ficha.nome}** possui **{ficha.xp} XP** disponível. Escolha o que deseja adquirir.",
            ),
            view=MercadoXPView(self.usuario_id, self.caminho),
            attachments=[],
        )

    @discord.ui.button(label="Info", style=discord.ButtonStyle.secondary, emoji="ℹ️", row=1)
    async def info(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            InformacaoFichaModal(self.usuario_id, self.caminho)
        )

    @discord.ui.button(label="Modificar Info", style=discord.ButtonStyle.secondary, emoji="✏️", row=1)
    async def modificar_info(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        if not ficha.informacoes:
            await interaction.response.send_message(
                "A ficha ainda não possui informações para modificar.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "📋 Modificar informação",
                "Escolha a informação que deseja modificar ou excluir.",
            ),
            view=EscolhaInformacaoFichaView(
                self.usuario_id,
                self.caminho,
                ficha.informacoes,
            ),
        )

    @discord.ui.button(label="Item", style=discord.ButtonStyle.secondary, emoji="🎒", row=2)
    async def adicionar_item(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        from comandos.inventario import TipoItemView

        await interaction.response.edit_message(
            embed=embed_painel(
                "🎒 Guardar item",
                "Escolha o tipo do item que será adicionado ao inventário.",
            ),
            view=TipoItemView(self.usuario_id, self.caminho),
            attachments=[],
        )

    @discord.ui.button(label="Modificar Item", style=discord.ButtonStyle.secondary, emoji="✏️", row=2)
    async def modificar_item(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        from comandos.inventario import CategoriasInventarioView

        ficha = FichaPersonagem.carregar(self.caminho)
        if not ficha.itens and ficha.galeoes <= 0:
            await interaction.response.send_message(
                "A ficha ainda não possui itens para modificar.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "✏️ Modificar item",
                "Escolha a categoria e depois o item que deseja alterar ou excluir.",
            ),
            view=CategoriasInventarioView(
                self.usuario_id,
                self.caminho,
                modo="gerenciar",
            ),
            attachments=[],
        )

    @discord.ui.button(label="Feitiço", style=discord.ButtonStyle.secondary, emoji="📥", row=3)
    async def adicionar_feitico(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        categorias = listar_categorias_feiticos_ficha()
        if not categorias:
            await interaction.response.send_message(
                "A biblioteca não possui feitiços válidos para selecionar.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "🪄 Feitiços",
                "Escolha a categoria do feitiço que deseja destacar na ficha.",
            ),
            view=CategoriaFeiticoFichaView(
                self.usuario_id,
                self.caminho,
                categorias,
            ),
        )

    @discord.ui.button(label="Modificar Feitiço", style=discord.ButtonStyle.secondary, emoji="✏️", row=3)
    async def modificar_feitico(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        if not ficha.feiticos_favoritos:
            await interaction.response.send_message(
                "A ficha ainda não possui feitiços para modificar.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "🪄 Modificar feitiço",
                "Escolha o feitiço que deseja modificar ou excluir.",
            ),
            view=EscolhaFeiticoSalvoFichaView(
                self.usuario_id,
                self.caminho,
                ficha.feiticos_favoritos,
            ),
        )

    async def adicionar_pocao(self, interaction: discord.Interaction) -> None:
        categorias = listar_categorias_pocoes_ficha()
        if not categorias:
            await interaction.response.send_message(
                "A biblioteca não possui poções válidas para selecionar.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "🧪 Poções",
                "Escolha o ano da poção que deseja destacar na ficha.",
            ),
            view=CategoriaPocaoFichaView(
                self.usuario_id,
                self.caminho,
                categorias,
            ),
        )

    async def modificar_pocao(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        if not ficha.pocoes_favoritas:
            await interaction.response.send_message(
                "A ficha ainda não possui poções para modificar.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "🧪 Modificar poção",
                "Escolha a poção que deseja modificar ou excluir.",
            ),
            view=EscolhaPocaoSalvaFichaView(
                self.usuario_id,
                self.caminho,
                ficha.pocoes_favoritas,
            ),
        )


RECARGAS_HABILIDADE_NPC = (
    "Sem recarga",
    "Uma vez por combate",
    "Uma vez por cena",
    "Uma vez por dia",
    "Personalizada",
)
ROLAGENS_REACAO_HABILIDADE_NPC = (
    "Teste Oposto",
    "Efeito Direto",
    "Automática",
    "Pessoal",
)
CATEGORIAS_ACERTO_HABILIDADE_NPC = ("Atributo", "Perícia", "Nenhuma")
NUMEROS_DADOS_HABILIDADE_NPC = tuple(str(numero) for numero in range(1, 11))


def bonus_escolha_habilidade_npc(ficha: FichaPersonagem, escolha: str) -> int:
    if escolha in ATRIBUTOS:
        return modificador(atributos_efetivos(ficha)[escolha])
    if escolha in PERICIAS:
        return max(
            bonus_pericia(escolha, ficha.pericias.get(escolha, 0), atributos_efetivos(ficha))
        )
    if escolha in {"", "Nulo", "Nenhuma"}:
        return 0
    raise ValueError("O atributo ou a perícia da habilidade é inválido.")


def escolha_habilidade_npc_com_bonus(ficha: FichaPersonagem, escolha: str) -> str:
    return f"{escolha} {formatar_bonus(bonus_escolha_habilidade_npc(ficha, escolha))}"


def escolha_habilidade_npc_base(valor: str) -> str:
    return next(
        (
            nome
            for nome in (*ATRIBUTOS, *PERICIAS, "Nulo", "Nenhuma")
            if valor == nome or valor.startswith(f"{nome} ")
        ),
        valor,
    )


def categoria_escolha_habilidade_npc(valor: str) -> str:
    base = escolha_habilidade_npc_base(valor)
    if base in ATRIBUTOS:
        return "Atributo"
    if base in PERICIAS:
        return "Perícia"
    if base == "Nenhuma":
        return "Nenhuma"
    return ""


def aplicar_modo_custo_habilidade_npc(item: dict[str, str]) -> None:
    modo = item.get("modo de custo", "")
    custo = "0" if modo == "Sem Custo" else item.get("custo de PH", "0")
    item["custo de PH"] = custo
    if modo == "Ativação":
        item["mecânica de custo"] = f"Custa {custo} PH por ativação."
    elif modo == "Turno/Rodada Sustentada":
        item["mecânica de custo"] = (
            f"Custa {custo} PH por turno ou rodada sustentada e termina "
            "quando a concentração for perdida."
        )
    elif modo == "Acúmulo":
        item["mecânica de custo"] = (
            f"A cada {custo} PH, recebe um acúmulo do mesmo efeito. "
            "Os acúmulos começam e terminam juntos."
        )
    else:
        item["mecânica de custo"] = "Sem custo de PH."


def atualizar_efeito_habilidade_npc(
    ficha: FichaPersonagem,
    item: dict[str, str],
    modificador_efeito: str,
) -> None:
    dado = item.get("dado de efeito", "")
    numero = item.get("número de dados", "")
    base = escolha_habilidade_npc_base(modificador_efeito)
    bonus = bonus_escolha_habilidade_npc(ficha, base)
    item["modificador de efeito"] = (
        "Nulo" if base == "Nulo" else escolha_habilidade_npc_com_bonus(ficha, base)
    )
    sufixo = "" if base == "Nulo" else formatar_bonus(bonus)
    item["efeito calculado"] = f"{numero}{dado}{sufixo}" + (
        "" if base == "Nulo" else f" ({base})"
    )
    if item.get("rolagem de reação") == "Efeito Direto":
        item["CD do efeito"] = str(10 + ficha.nivel // 2 + bonus)
    else:
        item.pop("CD do efeito", None)


def bonus_cd_habilidade_npc(ficha: FichaPersonagem, item: dict[str, str]) -> int:
    modificador_efeito = escolha_habilidade_npc_base(
        item.get("modificador de efeito", "")
    )
    if modificador_efeito in (*ATRIBUTOS, *PERICIAS):
        return bonus_escolha_habilidade_npc(ficha, modificador_efeito)
    acerto = escolha_habilidade_npc_base(item.get("rolagem de acerto", ""))
    return bonus_escolha_habilidade_npc(ficha, acerto)


def opcoes_habilidade_npc(
    valores: tuple[str, ...] | list[str],
    descricoes: dict[str, str] | None = None,
    atual: str = "",
) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=valor[:100],
            value=valor,
            description=(descricoes or {}).get(valor, "")[:100] or None,
            default=valor == atual,
        )
        for valor in valores
    ]


def embed_gerenciar_habilidades_npc(ficha: FichaPersonagem) -> discord.Embed:
    nomes = "\n".join(
        f"• {item.get('nome', 'Habilidade')}" for item in ficha.habilidades_npc
    ) or "A ficha ainda não possui habilidades personalizadas."
    return embed_painel("✨ Habilidades do NPC", nomes)


def registros_combate_npc(ficha: FichaPersonagem, tipo: str) -> list[dict[str, str]]:
    return ficha.armas_npc if tipo == "arma" else ficha.ataques_npc


async def gravar_registro_combate_npc(
    caminho: Path,
    tipo: str,
    item: dict[str, str] | None,
    indice: int | None = None,
    original: dict[str, str] | None = None,
) -> FichaPersonagem:
    lock=LOCKS_FICHA.setdefault(caminho.resolve(),asyncio.Lock())
    async with lock:
        ficha=FichaPersonagem.carregar(caminho)
        if ficha.grupo!="NPCs" or ficha.tipo_npc in {"","Bruxo(a)"}:
            raise ValueError("Esta ficha não usa armas e ataques de NPC alternativo.")
        destino=registros_combate_npc(ficha,tipo)
        if indice is None:
            if item is None:raise ValueError("O novo registro não foi informado.")
            destino.append(item)
        else:
            if indice>=len(destino) or destino[indice]!=(original or {}):
                raise ValueError("O registro mudou durante a edição. Consulte a ficha novamente.")
            if item is None:destino.pop(indice)
            else:destino[indice]=item
        validar_tamanho_ficha(ficha)
        ficha._conteudo_original_registro_combate = caminho.read_text(encoding="utf-8-sig")
    return ficha


async def concluir_registro_combate_npc(interaction,usuario_id,caminho,ficha):
    lock=LOCKS_FICHA.setdefault(caminho.resolve(),asyncio.Lock())
    async with lock:
        if caminho.read_text(encoding="utf-8-sig") != getattr(
            ficha,"_conteudo_original_registro_combate",""
        ):
            await interaction.response.send_message(
                "A ficha mudou durante a edição. Consulte-a novamente para evitar sobrescrever alterações.",
                ephemeral=True,
            )
            return
        salvar_ficha(ficha,caminho)
    await interaction.response.edit_message(
        embeds=montar_embeds_ficha_interacao(ficha),
        view=FichaAtualView(usuario_id,caminho),
        attachments=criar_arquivos_discord(anexos_ficha(ficha)),
    )
    await sincronizar_publicacao_personagem(interaction,ficha,caminho)


class GerenciarCombateNPCView(ViewAutor):
    def __init__(self,usuario_id,caminho,tipo):
        super().__init__(usuario_id);self.caminho=caminho;self.tipo=tipo
        ficha=FichaPersonagem.carregar(caminho);destino=registros_combate_npc(ficha,tipo)
        adicionar=discord.ui.Button(label="Adicionar",style=discord.ButtonStyle.success,emoji="➕")
        modificar=discord.ui.Button(label="Modificar",style=discord.ButtonStyle.secondary,emoji="✏️",disabled=not destino)
        remover=discord.ui.Button(label="Remover",style=discord.ButtonStyle.danger,emoji="🗑️",disabled=not destino)
        voltar=discord.ui.Button(label="Voltar à ficha",style=discord.ButtonStyle.secondary)
        adicionar.callback=self.adicionar;modificar.callback=self.modificar;remover.callback=self.remover;voltar.callback=self.voltar
        for botao in (adicionar,modificar,remover,voltar):self.add_item(botao)
    async def adicionar(self,i):
        if self.tipo=="arma":
            await i.response.edit_message(embed=embed_painel("🗡️ Tipo de arma","Escolha a categoria da arma."),view=TipoArmaNPCView(self.usuario_id,self.caminho));return
        await i.response.edit_message(embed=embed_painel("⚔️ Ataque do NPC","Escolha um preset ou crie um ataque personalizado."),view=EscolhaAtaqueNPCView(self.usuario_id,self.caminho))
    async def modificar(self,i):
        await i.response.edit_message(embed=embed_painel("✏️ Modificar registro","Escolha o item que deseja alterar."),view=SelecionarCombateNPCView(self.usuario_id,self.caminho,self.tipo,"modificar"))
    async def remover(self,i):
        await i.response.edit_message(embed=embed_painel("🗑️ Remover registro","Escolha o item que deseja remover."),view=SelecionarCombateNPCView(self.usuario_id,self.caminho,self.tipo,"remover"))
    async def voltar(self,i):
        ficha=FichaPersonagem.carregar(self.caminho)
        await i.response.edit_message(embeds=montar_embeds_ficha_interacao(ficha),view=FichaAtualView(self.usuario_id,self.caminho),attachments=criar_arquivos_discord(anexos_ficha(ficha)))


class SelecionarCombateNPCView(ViewAutor):
    def __init__(self,usuario_id,caminho,tipo,acao,pagina=0):
        super().__init__(usuario_id);self.caminho=caminho;self.tipo=tipo;self.acao=acao
        self.registros=list(registros_combate_npc(FichaPersonagem.carregar(caminho),tipo))
        self.paginas=[list(range(n,min(n+25,len(self.registros)))) for n in range(0,len(self.registros),25)] or [[]]
        self.pagina=max(0,min(pagina,len(self.paginas)-1));indices=self.paginas[self.pagina]
        seletor=discord.ui.Select(placeholder=f"{('Armas' if tipo=='arma' else 'Ataques')} — página {self.pagina+1}/{len(self.paginas)}",options=[discord.SelectOption(label=self.registros[n].get("nome",tipo.title())[:100],value=str(n),description=(self.registros[n].get("categoria") or self.registros[n].get("tipo de ação") or "")[:100] or None) for n in indices])
        seletor.callback=self.selecionar;self.seletor=seletor;self.add_item(seletor)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=1);voltar.callback=self.voltar;self.add_item(voltar)
    async def selecionar(self,i):
        indice=int(self.seletor.values[0]);original=dict(self.registros[indice])
        if self.acao=="remover":
            await i.response.edit_message(embed=embed_painel("🗑️ Confirmar remoção",f"Remover **{original.get('nome',self.tipo.title())}** desta ficha?"),view=ConfirmarRemocaoCombateNPCView(self.usuario_id,self.caminho,self.tipo,indice,original));return
        if self.tipo=="arma":await i.response.send_modal(ArmaNPCModal(self.usuario_id,self.caminho,original.get("categoria","Armas Naturais"),original,indice,original));return
        await i.response.edit_message(embed=embed_painel(f"⚔️ Configurar {original.get('nome','Ataque')}","Revise o tipo de ação e a rolagem de ataque."),view=ConfigurarAtaqueNPCView(self.usuario_id,self.caminho,original.get("nome","Personalizado"),original,indice,original))
    async def voltar(self,i):await i.response.edit_message(embed=embed_painel("🧰 Gerenciar registros","Escolha o que deseja fazer."),view=GerenciarCombateNPCView(self.usuario_id,self.caminho,self.tipo))


class ConfirmarRemocaoCombateNPCView(ViewAutor):
    def __init__(self,usuario_id,caminho,tipo,indice,original):
        super().__init__(usuario_id);self.caminho=caminho;self.tipo=tipo;self.indice=indice;self.original=original
    @discord.ui.button(label="Remover",style=discord.ButtonStyle.danger,emoji="🗑️")
    async def remover(self,i,_):
        try:ficha=await gravar_registro_combate_npc(self.caminho,self.tipo,None,self.indice,self.original)
        except ValueError as erro:await i.response.send_message(str(erro),ephemeral=True);return
        await concluir_registro_combate_npc(i,self.usuario_id,self.caminho,ficha)
    @discord.ui.button(label="Cancelar",style=discord.ButtonStyle.secondary)
    async def cancelar(self,i,_):await i.response.edit_message(embed=embed_painel("🧰 Gerenciar registros","Escolha o que deseja fazer."),view=GerenciarCombateNPCView(self.usuario_id,self.caminho,self.tipo))


class TipoArmaNPCView(ViewAutor):
    def __init__(self,usuario_id,caminho):
        super().__init__(usuario_id);self.caminho=caminho
        seletor=discord.ui.Select(placeholder="Tipo de arma",options=ficha_criaturas.opcoes(tuple(ficha_criaturas.ARMAS_POR_TIPO),ficha_criaturas.DESCRICOES_TIPOS_ARMAS));seletor.callback=self.selecionar;self.seletor=seletor;self.add_item(seletor)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=1);voltar.callback=self.voltar;self.add_item(voltar)
    async def selecionar(self,i):
        tipo=self.seletor.values[0]
        await i.response.edit_message(embed=embed_painel(f"🗡️ {tipo}","Escolha uma arma da tabela ou crie uma personalizada."),view=EscolhaArmaNPCView(self.usuario_id,self.caminho,tipo))
    async def voltar(self,i):await i.response.edit_message(embed=embed_painel("🗡️ Armas do NPC","Adicione, modifique ou remova armas desta ficha."),view=GerenciarCombateNPCView(self.usuario_id,self.caminho,"arma"))


class EscolhaArmaNPCView(ViewAutor):
    def __init__(self,usuario_id,caminho,categoria):
        super().__init__(usuario_id);self.caminho=caminho;self.categoria=categoria
        armas=ficha_criaturas.ARMAS_POR_TIPO[categoria]
        descricoes={nome:f"{dados['tipo de dano']} • {dados.get('dano-base',dados.get('dano','--'))} • crítico {dados['crítico']}" for nome,dados in armas.items()};descricoes["Personalizada"]="Crie uma arma que ainda não está na tabela."
        seletor=discord.ui.Select(placeholder="Escolha a arma",options=ficha_criaturas.opcoes(tuple(armas)+("Personalizada",),descricoes));seletor.callback=self.selecionar;self.seletor=seletor;self.add_item(seletor)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=1);voltar.callback=self.voltar;self.add_item(voltar)
    async def selecionar(self,i):
        nome=self.seletor.values[0]
        if nome=="Personalizada":await i.response.send_modal(ArmaNPCModal(self.usuario_id,self.caminho,self.categoria));return
        ficha=FichaPersonagem.carregar(self.caminho);dados=dict(ficha_criaturas.ARMAS_POR_TIPO[self.categoria][nome])
        if self.categoria=="Armas Naturais":
            try:dados["dano"]=ficha_criaturas.dano_arma_natural(dados.pop("dano-base"),"X",ficha.altura)
            except ValueError as erro:await i.response.send_message(str(erro),ephemeral=True);return
        dados["dano"]=ficha_criaturas.somar_atributo_ao_dano(dados["dano"],ficha.atributos)
        item={"nome":nome,"categoria":self.categoria,**dados}
        ficha=await gravar_registro_combate_npc(self.caminho,"arma",item)
        await concluir_registro_combate_npc(i,self.usuario_id,self.caminho,ficha)
    async def voltar(self,i):await i.response.edit_message(embed=embed_painel("🗡️ Tipo de arma","Escolha a categoria da arma."),view=TipoArmaNPCView(self.usuario_id,self.caminho))


class ArmaNPCModal(discord.ui.Modal):
    def __init__(self,usuario_id,caminho,categoria,item=None,indice=None,original=None):
        super().__init__(title="Arma do NPC");self.usuario_id=usuario_id;self.caminho=caminho;self.categoria=categoria;self.item=dict(item or {});self.indice=indice;self.original=dict(original) if original else None
        self.nome=discord.ui.TextInput(label="Nome",default=self.item.get("nome",""),max_length=100)
        self.tipo_dano=discord.ui.TextInput(label="Tipo de dano",default=self.item.get("tipo de dano",""),max_length=100)
        self.dano=discord.ui.TextInput(label="Dano-base" if indice is None else "Dano",default=self.item.get("dano",self.item.get("dano-base","")),placeholder="Ex.: 1d6+Força",max_length=100)
        self.critico=discord.ui.TextInput(label="Efeito de crítico",default=self.item.get("crítico",""),max_length=30)
        self.descricao=discord.ui.TextInput(label="Descrição",default=self.item.get("descrição",""),style=discord.TextStyle.paragraph,required=False,max_length=800)
        for campo in (self.nome,self.tipo_dano,self.dano,self.critico,self.descricao):self.add_item(campo)
    async def on_submit(self,i):
        ficha=FichaPersonagem.carregar(self.caminho);dano=str(self.dano.value).strip()
        if self.indice is None and self.categoria=="Armas Naturais":
            try:dano=ficha_criaturas.dano_arma_natural(dano,"X",ficha.altura)
            except ValueError as erro:await i.response.send_message(str(erro),ephemeral=True);return
        dano=ficha_criaturas.somar_atributo_ao_dano(dano,ficha.atributos)
        item=dict(self.item);item.update({"nome":str(self.nome.value).strip(),"categoria":self.categoria,"tipo de dano":str(self.tipo_dano.value).strip(),"dano":dano,"crítico":str(self.critico.value).strip()})
        descricao=str(self.descricao.value).strip()
        if descricao:item["descrição"]=descricao
        else:item.pop("descrição",None)
        try:ficha=await gravar_registro_combate_npc(self.caminho,"arma",item,self.indice,self.original)
        except ValueError as erro:await i.response.send_message(str(erro),ephemeral=True);return
        await concluir_registro_combate_npc(i,self.usuario_id,self.caminho,ficha)


class EscolhaAtaqueNPCView(ViewAutor):
    def __init__(self,usuario_id,caminho):
        super().__init__(usuario_id);self.caminho=caminho
        seletor=discord.ui.Select(placeholder="Escolha o ataque",options=ficha_criaturas.opcoes(ficha_criaturas.ATAQUES,ficha_criaturas.DESCRICOES_ATAQUES));seletor.callback=self.selecionar;self.seletor=seletor;self.add_item(seletor)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=1);voltar.callback=self.voltar;self.add_item(voltar)
    async def selecionar(self,i):
        nome=self.seletor.values[0]
        await i.response.edit_message(embed=embed_painel(f"⚔️ Configurar {nome}","Escolha o tipo de ação e a rolagem usada para acertar."),view=ConfigurarAtaqueNPCView(self.usuario_id,self.caminho,nome,{"descrição":ficha_criaturas.DESCRICOES_ATAQUES.get(nome,"")}))
    async def voltar(self,i):await i.response.edit_message(embed=embed_painel("⚔️ Ataques do NPC","Adicione, modifique ou remova ataques desta ficha."),view=GerenciarCombateNPCView(self.usuario_id,self.caminho,"ataque"))


class ConfigurarAtaqueNPCView(ViewAutor):
    def __init__(self,usuario_id,caminho,nome,item=None,indice=None,original=None):
        super().__init__(usuario_id);self.caminho=caminho;self.nome=nome;self.item=dict(item or {});self.indice=indice;self.original=dict(original) if original else None
        acao=discord.ui.Select(placeholder="Tipo de ação",options=opcoes_habilidade_npc(list(ficha_criaturas.ACOES),{},self.item.get("tipo de ação","")),row=0)
        rolagem=discord.ui.Select(placeholder="Rolagem de ataque",options=opcoes_habilidade_npc(list(ficha_criaturas.ROLAGENS_ATAQUE),ficha_criaturas.ROLAGENS_ATAQUE,self.item.get("rolagem de ataque","")),row=1)
        acao.callback=self.selecionar_acao;rolagem.callback=self.selecionar_rolagem;self.acao=acao;self.rolagem=rolagem;self.add_item(acao);self.add_item(rolagem)
        continuar=discord.ui.Button(label="Continuar",style=discord.ButtonStyle.primary,row=2);continuar.callback=self.continuar;self.add_item(continuar)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=2);voltar.callback=self.voltar;self.add_item(voltar)
    def nova(self,item):return ConfigurarAtaqueNPCView(self.usuario_id,self.caminho,self.nome,item,self.indice,self.original)
    async def selecionar_acao(self,i):item=dict(self.item);item["tipo de ação"]=self.acao.values[0];await i.response.edit_message(view=self.nova(item))
    async def selecionar_rolagem(self,i):item=dict(self.item);item["rolagem de ataque"]=self.rolagem.values[0];await i.response.edit_message(view=self.nova(item))
    async def continuar(self,i):
        if not self.item.get("tipo de ação") or not self.item.get("rolagem de ataque"):await i.response.send_message("Escolha o tipo de ação e a rolagem de ataque.",ephemeral=True);return
        await i.response.send_modal(AtaqueNPCModal(self.usuario_id,self.caminho,self.nome,self.item,self.indice,self.original))
    async def voltar(self,i):await i.response.edit_message(embed=embed_painel("⚔️ Ataques do NPC","Adicione, modifique ou remova ataques desta ficha."),view=GerenciarCombateNPCView(self.usuario_id,self.caminho,"ataque"))


class AtaqueNPCModal(discord.ui.Modal):
    def __init__(self,usuario_id,caminho,nome,item,indice,original):
        super().__init__(title="Detalhes do ataque");self.usuario_id=usuario_id;self.caminho=caminho;self.item=dict(item);self.indice=indice;self.original=original
        self.nome=discord.ui.TextInput(label="Nome",default=self.item.get("nome",nome if nome!="Personalizado" else ""),max_length=100)
        self.descricao=discord.ui.TextInput(label="Descrição",default=self.item.get("descrição",""),style=discord.TextStyle.paragraph,max_length=900)
        self.efeito=discord.ui.TextInput(label="Dano ou efeito",default=self.item.get("dano ou efeito",""),style=discord.TextStyle.paragraph,max_length=1000)
        for campo in (self.nome,self.descricao,self.efeito):self.add_item(campo)
    async def on_submit(self,i):
        ficha=FichaPersonagem.carregar(self.caminho);item=dict(self.item);item.update({"nome":str(self.nome.value).strip(),"descrição":str(self.descricao.value).strip(),"dano ou efeito":ficha_criaturas.somar_atributo_ao_dano(str(self.efeito.value).strip(),ficha.atributos)})
        await i.response.edit_message(embed=embed_painel("⚔️ Resistência, duração e recarga","Finalize os detalhes mecânicos do ataque."),view=DetalhesAtaqueNPCView(self.usuario_id,self.caminho,item,self.indice,self.original))


class DetalhesAtaqueNPCView(ViewAutor):
    def __init__(self,usuario_id,caminho,item,indice=None,original=None):
        super().__init__(usuario_id);self.caminho=caminho;self.item=dict(item);self.indice=indice;self.original=dict(original) if original else None
        configuracoes=(("teste de resistência","Teste de Resistência",ficha_criaturas.RESISTENCIAS,{"Reflexo":"Para esquivar ou escapar.","Fortitude":"Para defender ou resistir fisicamente.","Vontade":"Para resistir mentalmente.","Nenhuma":"Não aplica efeito secundário resistível."}),("duração","Duração",ficha_criaturas.DURACOES,{}),("recarga","Recarga",RECARGAS_HABILIDADE_NPC,{}))
        self.seletores={}
        for linha,(chave,rotulo,valores,descricoes) in enumerate(configuracoes):
            seletor=discord.ui.Select(placeholder=rotulo,options=opcoes_habilidade_npc(list(valores),descricoes,self.item.get(chave,"")),row=linha);seletor.callback=self.selecionar;self.seletores[chave]=seletor;self.add_item(seletor)
        concluir=discord.ui.Button(label="Concluir",style=discord.ButtonStyle.success,row=3);concluir.callback=self.concluir;self.add_item(concluir)
        voltar=discord.ui.Button(label="Voltar",style=discord.ButtonStyle.secondary,row=3);voltar.callback=self.voltar;self.add_item(voltar)
    async def selecionar(self,i):
        item=dict(self.item)
        for chave,seletor in self.seletores.items():
            if seletor.values:item[chave]=seletor.values[0]
        await i.response.edit_message(view=DetalhesAtaqueNPCView(self.usuario_id,self.caminho,item,self.indice,self.original))
    async def concluir(self,i):
        if not all(self.item.get(chave) for chave in ("teste de resistência","duração","recarga")):await i.response.send_message("Escolha o teste de resistência, a duração e a recarga.",ephemeral=True);return
        try:ficha=await gravar_registro_combate_npc(self.caminho,"ataque",self.item,self.indice,self.original)
        except ValueError as erro:await i.response.send_message(str(erro),ephemeral=True);return
        await concluir_registro_combate_npc(i,self.usuario_id,self.caminho,ficha)
    async def voltar(self,i):await i.response.edit_message(embed=embed_painel(f"⚔️ Configurar {self.item.get('nome','Ataque')}","Revise o tipo de ação e a rolagem de ataque."),view=ConfigurarAtaqueNPCView(self.usuario_id,self.caminho,self.item.get("nome","Personalizado"),self.item,self.indice,self.original))


class GerenciarHabilidadesNPCView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__(usuario_id)
        self.caminho = caminho
        ficha = FichaPersonagem.carregar(caminho)
        adicionar = discord.ui.Button(
            label="Adicionar", style=discord.ButtonStyle.success, emoji="➕"
        )
        modificar = discord.ui.Button(
            label="Modificar", style=discord.ButtonStyle.secondary, emoji="✏️"
        )
        remover = discord.ui.Button(
            label="Remover", style=discord.ButtonStyle.danger, emoji="🗑️"
        )
        voltar = discord.ui.Button(label="Voltar à ficha", style=discord.ButtonStyle.secondary)
        modificar.disabled = not ficha.habilidades_npc
        remover.disabled = not ficha.habilidades_npc
        adicionar.callback = self.adicionar
        modificar.callback = self.modificar
        remover.callback = self.remover
        voltar.callback = self.voltar
        for botao in (adicionar, modificar, remover, voltar):
            self.add_item(botao)

    async def adicionar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "✨ Configurar habilidade",
                "Escolha o tipo de ativação e o tipo de ação.",
            ),
            view=HabilidadeNPCWizardView(
                self.usuario_id, self.caminho, {}, etapa=0
            ),
        )

    async def modificar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "✏️ Modificar habilidade",
                "Escolha a habilidade que será refeita usando o criador completo.",
            ),
            view=SelecionarHabilidadeNPCView(
                self.usuario_id, self.caminho, "modificar", ficha.habilidades_npc
            ),
        )

    async def remover(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "🗑️ Remover habilidade",
                "Escolha a habilidade que deseja remover.",
            ),
            view=SelecionarHabilidadeNPCView(
                self.usuario_id, self.caminho, "remover", ficha.habilidades_npc
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
            attachments=criar_arquivos_discord(anexos_ficha(ficha)),
        )


class SelecionarHabilidadeNPCView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        acao: str,
        habilidades: list[dict[str, str]],
        pagina: int = 0,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.acao = acao
        self.habilidades = habilidades
        self.paginas = [
            list(range(indice, min(indice + 25, len(habilidades))))
            for indice in range(0, len(habilidades), 25)
        ] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        indices = self.paginas[self.pagina]
        seletor = discord.ui.Select(
            placeholder=f"Habilidades — página {self.pagina + 1}/{len(self.paginas)}",
            options=[
                discord.SelectOption(
                    label=habilidades[indice].get("nome", "Habilidade")[:100],
                    value=str(indice),
                    description=habilidades[indice].get("tipo de efeito", "")[:100] or None,
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
        original = dict(self.habilidades[indice])
        if self.acao == "modificar":
            await interaction.response.edit_message(
                embed=embed_painel(
                    "✨ Configurar habilidade",
                    "Revise o tipo de ativação e o tipo de ação.",
                ),
                view=HabilidadeNPCWizardView(
                    self.usuario_id,
                    self.caminho,
                    dict(original),
                    etapa=0,
                    indice_edicao=indice,
                    original=original,
                ),
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "🗑️ Confirmar remoção",
                f"Remover **{original.get('nome', 'Habilidade')}** da ficha?",
            ),
            view=ConfirmarRemocaoHabilidadeNPCView(
                self.usuario_id, self.caminho, indice, original
            ),
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=SelecionarHabilidadeNPCView(
                self.usuario_id, self.caminho, self.acao, self.habilidades, self.pagina - 1
            )
        )

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=SelecionarHabilidadeNPCView(
                self.usuario_id, self.caminho, self.acao, self.habilidades, self.pagina + 1
            )
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_gerenciar_habilidades_npc(ficha),
            view=GerenciarHabilidadesNPCView(self.usuario_id, self.caminho),
        )


class ConfirmarRemocaoHabilidadeNPCView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path, indice: int, original: dict[str, str]):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.indice = indice
        self.original = original

    @discord.ui.button(label="Remover", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def remover(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            ficha = FichaPersonagem.carregar(self.caminho)
            if (
                self.indice >= len(ficha.habilidades_npc)
                or ficha.habilidades_npc[self.indice] != self.original
            ):
                await interaction.response.send_message(
                    "A lista de habilidades mudou. Consulte a ficha novamente.", ephemeral=True
                )
                return
            removida = ficha.habilidades_npc.pop(self.indice)
            salvar_ficha(ficha, self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
            attachments=criar_arquivos_discord(anexos_ficha(ficha)),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_gerenciar_habilidades_npc(ficha),
            view=GerenciarHabilidadesNPCView(self.usuario_id, self.caminho),
        )


class HabilidadeNPCWizardView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        item: dict[str, str],
        *,
        etapa: int,
        indice_edicao: int | None = None,
        original: dict[str, str] | None = None,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.item = dict(item)
        self.etapa = etapa
        self.indice_edicao = indice_edicao
        self.original = dict(original) if original is not None else None
        ficha = FichaPersonagem.carregar(caminho)
        self.ficha = ficha
        if etapa == 0:
            self._montar_ativacao()
        elif etapa == 1:
            self._montar_alcance()
        elif etapa == 2:
            self._montar_custo()
        elif etapa == 3:
            self._montar_rolagens()
        elif etapa == 4:
            self._montar_tipo_efeito()
        else:
            self._montar_dados_efeito()

    def nova(self, etapa: int, item: dict[str, str] | None = None) -> "HabilidadeNPCWizardView":
        return HabilidadeNPCWizardView(
            self.usuario_id,
            self.caminho,
            self.item if item is None else item,
            etapa=etapa,
            indice_edicao=self.indice_edicao,
            original=self.original,
        )

    def _botao_continuar(self, linha: int) -> None:
        continuar = discord.ui.Button(label="Continuar", style=discord.ButtonStyle.primary, row=linha)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=linha)
        continuar.callback = self.continuar
        voltar.callback = self.voltar
        self.add_item(continuar)
        self.add_item(voltar)

    def _montar_ativacao(self) -> None:
        self.ativacao = discord.ui.Select(
            placeholder="Tipo de Ativação",
            options=opcoes_habilidade_npc(
                list(ficha_criaturas.ATIVACOES_HABILIDADE),
                ficha_criaturas.ATIVACOES_HABILIDADE,
                self.item.get("tipo de ativação", ""),
            ),
            row=0,
        )
        self.acao = discord.ui.Select(
            placeholder="Tipo de Ação",
            options=opcoes_habilidade_npc(
                list(ficha_criaturas.ACOES_HABILIDADE),
                ficha_criaturas.DESCRICOES_ACOES_HABILIDADE,
                self.item.get("tipo de ação", ""),
            ),
            row=1,
        )
        self.ativacao.callback = self.selecionar_ativacao
        self.acao.callback = self.selecionar_acao
        self.add_item(self.ativacao)
        self.add_item(self.acao)
        self._botao_continuar(2)

    def _montar_alcance(self) -> None:
        descricoes_duracao = {
            "Instantâneo": "O efeito acontece e termina imediatamente.",
            "Turno": "A quantidade de turnos é definida no campo Efeito.",
            "Rodada": "A quantidade de rodadas é definida no campo Efeito.",
            "Sustentado": "Permanece enquanto a concentração for mantida.",
        }
        descricoes_recarga = {
            "Sem recarga": "Pode ser usada novamente sem esperar rodadas.",
            "Uma vez por combate": "Só pode ser usada uma vez em cada combate.",
            "Uma vez por cena": "Só pode ser usada uma vez em cada cena.",
            "Uma vez por dia": "Só pode ser usada uma vez por dia.",
            "Personalizada": "A limitação fica definida no campo Efeito.",
        }
        configuracoes = (
            ("alcance", "Alcance", ficha_criaturas.ALCANCES, ficha_criaturas.DESCRICOES_ALCANCES),
            ("alvo", "Alvo", ficha_criaturas.ALVOS, ficha_criaturas.DESCRICOES_ALVOS),
            ("duração", "Duração", ficha_criaturas.DURACOES, descricoes_duracao),
            ("recarga", "Recarga", RECARGAS_HABILIDADE_NPC, descricoes_recarga),
        )
        self.seletores_etapa: dict[str, discord.ui.Select] = {}
        for linha, (chave, rotulo, valores, descricoes) in enumerate(configuracoes):
            seletor = discord.ui.Select(
                placeholder=rotulo,
                options=opcoes_habilidade_npc(
                    list(valores), descricoes, self.item.get(chave, "")
                ),
                row=linha,
            )
            seletor.callback = self.selecionar_campo
            self.seletores_etapa[chave] = seletor
            self.add_item(seletor)
        self._botao_continuar(4)

    def _montar_custo(self) -> None:
        descricoes = {
            "Ativação": "O custo é pago sempre que a habilidade é ativada.",
            "Turno/Rodada Sustentada": "O custo é pago a cada turno ou rodada sustentada.",
            "Acúmulo": "Cada pagamento concede um acúmulo do mesmo efeito.",
            "Sem Custo": "A habilidade não consome PH e define o custo automaticamente como 0.",
        }
        self.modo = discord.ui.Select(
            placeholder="Modo de Custo",
            options=opcoes_habilidade_npc(
                list(ficha_criaturas.MODOS_CUSTO_HABILIDADE),
                descricoes,
                self.item.get("modo de custo", ""),
            ),
            row=0,
        )
        self.modo.callback = self.selecionar_modo
        self.add_item(self.modo)
        self.custo = None
        if self.item.get("modo de custo") and self.item.get("modo de custo") != "Sem Custo":
            self.custo = discord.ui.Select(
                placeholder="Custo de PH",
                options=opcoes_habilidade_npc(
                    list(ficha_criaturas.CUSTOS_PH_HABILIDADE),
                    ficha_criaturas.CUSTOS_PH_HABILIDADE,
                    self.item.get("custo de PH", ""),
                ),
                row=1,
            )
            self.custo.callback = self.selecionar_custo
            self.add_item(self.custo)
        self._botao_continuar(2)

    def _montar_rolagens(self) -> None:
        acerto = categoria_escolha_habilidade_npc(self.item.get("rolagem de acerto", ""))
        descricoes_acerto = {
            "Atributo": "Abre os seis atributos da ficha.",
            "Perícia": "Abre as perícias organizadas pelos atributos relacionados.",
            "Nenhuma": "A habilidade não exige uma rolagem para acertar.",
        }
        self.acerto = discord.ui.Select(
            placeholder=(
                "Rolagem de Acerto"
                + (f": {escolha_habilidade_npc_base(self.item.get('rolagem de acerto', ''))}" if acerto else "")
            )[:150],
            options=opcoes_habilidade_npc(
                list(CATEGORIAS_ACERTO_HABILIDADE_NPC), descricoes_acerto, acerto
            ),
            row=0,
        )
        self.resistencia = discord.ui.Select(
            placeholder="Rolagem de Resistência",
            options=opcoes_habilidade_npc(
                list(ficha_criaturas.RESISTENCIAS),
                {
                    "Reflexo": "Para esquivar ou escapar de restrições.",
                    "Fortitude": "Para defender ou resistir a impactos físicos.",
                    "Vontade": "Para resistir a efeitos mentais e de controle.",
                    "Nenhuma": "O efeito não permite teste de resistência.",
                },
                self.item.get("rolagem de resistência", ""),
            ),
            row=1,
        )
        self.reacao = discord.ui.Select(
            placeholder="Rolagem de Reação",
            options=opcoes_habilidade_npc(
                list(ROLAGENS_REACAO_HABILIDADE_NPC),
                {
                    "Teste Oposto": "Compara a rolagem do NPC com a reação do alvo.",
                    "Efeito Direto": "O alvo reage contra a CD calculada pelo nível e modificador.",
                    "Automática": "O efeito acontece automaticamente quando ativado.",
                    "Pessoal": "Afeta o próprio usuário sem oposição.",
                },
                self.item.get("rolagem de reação", ""),
            ),
            row=2,
        )
        self.acerto.callback = self.selecionar_categoria_acerto
        self.resistencia.callback = self.selecionar_resistencia
        self.reacao.callback = self.selecionar_reacao
        self.add_item(self.acerto)
        self.add_item(self.resistencia)
        self.add_item(self.reacao)
        self._botao_continuar(3)

    def _montar_tipo_efeito(self) -> None:
        self.tipo_efeito = discord.ui.Select(
            placeholder="Tipo de Efeito",
            options=opcoes_habilidade_npc(
                list(ficha_criaturas.TIPOS_EFEITO_HABILIDADE),
                ficha_criaturas.TIPOS_EFEITO_HABILIDADE,
                self.item.get("tipo de efeito", ""),
            ),
            row=0,
        )
        self.necessita_rolagem = discord.ui.Select(
            placeholder="Necessita de Rolagem",
            options=opcoes_habilidade_npc(
                list(ficha_criaturas.NECESSITA_ROLAGEM_EFEITO),
                {
                    "Sim": "Abre a configuração dos dados do efeito.",
                    "Não": "Pula e descarta os dados da rolagem do efeito.",
                },
                self.item.get("necessita de rolagem", ""),
            ),
            row=1,
        )
        self.tipo_efeito.callback = self.selecionar_tipo_efeito
        self.necessita_rolagem.callback = self.selecionar_necessita_rolagem
        self.add_item(self.tipo_efeito)
        self.add_item(self.necessita_rolagem)
        self._botao_continuar(2)

    def _montar_dados_efeito(self) -> None:
        modificador_atual = escolha_habilidade_npc_base(
            self.item.get("modificador de efeito", "")
        )
        categoria_modificador = (
            "Nulo"
            if modificador_atual == "Nulo"
            else "Atributo"
            if modificador_atual in ATRIBUTOS
            else "Perícia"
            if modificador_atual in PERICIAS
            else ""
        )
        self.dado = discord.ui.Select(
            placeholder="Dado de Efeito",
            options=opcoes_habilidade_npc(
                list(ficha_criaturas.DADOS_EFEITO),
                {dado: f"Usa {dado} como dado-base." for dado in ficha_criaturas.DADOS_EFEITO},
                self.item.get("dado de efeito", ""),
            ),
            row=0,
        )
        self.numero = discord.ui.Select(
            placeholder="Número de Dados",
            options=opcoes_habilidade_npc(
                list(NUMEROS_DADOS_HABILIDADE_NPC),
                {numero: f"Rola {numero} dado(s); limite: 10." for numero in NUMEROS_DADOS_HABILIDADE_NPC},
                self.item.get("número de dados", ""),
            ),
            row=1,
        )
        self.modificador_efeito = discord.ui.Select(
            placeholder=(
                "Modificador de Efeito"
                + (f": {modificador_atual}" if modificador_atual not in {"", "Nulo"} else "")
            )[:150],
            options=opcoes_habilidade_npc(
                ["Nulo", "Atributo", "Perícia"],
                {
                    "Nulo": "Não soma modificador ao efeito.",
                    "Atributo": "Abre os seis atributos da ficha.",
                    "Perícia": "Abre as perícias organizadas pelos atributos relacionados.",
                },
                categoria_modificador,
            ),
            row=2,
        )
        self.dado.callback = self.selecionar_dado
        self.numero.callback = self.selecionar_numero
        self.modificador_efeito.callback = self.selecionar_categoria_modificador
        self.add_item(self.dado)
        self.add_item(self.numero)
        self.add_item(self.modificador_efeito)
        self._botao_continuar(3)

    async def selecionar_ativacao(self, interaction: discord.Interaction) -> None:
        item = dict(self.item)
        valor = self.ativacao.values[0]
        item["tipo de ativação"] = valor
        if valor == "Reação":
            item["tipo de ação"] = "Reação"
        elif item.get("tipo de ação") == "Reação":
            item.pop("tipo de ação", None)
        await interaction.response.edit_message(view=self.nova(0, item))

    async def selecionar_acao(self, interaction: discord.Interaction) -> None:
        item = dict(self.item)
        item["tipo de ação"] = self.acao.values[0]
        await interaction.response.edit_message(view=self.nova(0, item))

    async def selecionar_campo(self, interaction: discord.Interaction) -> None:
        item = dict(self.item)
        for chave, seletor in self.seletores_etapa.items():
            if seletor.values:
                item[chave] = seletor.values[0]
        await interaction.response.edit_message(view=self.nova(1, item))

    async def selecionar_custo(self, interaction: discord.Interaction) -> None:
        item = dict(self.item)
        item["custo de PH"] = self.custo.values[0]
        await interaction.response.edit_message(view=self.nova(2, item))

    async def selecionar_modo(self, interaction: discord.Interaction) -> None:
        item = dict(self.item)
        modo = self.modo.values[0]
        item["modo de custo"] = modo
        if modo == "Sem Custo":
            item["custo de PH"] = "0"
        elif self.item.get("modo de custo") == "Sem Custo":
            item.pop("custo de PH", None)
        await interaction.response.edit_message(view=self.nova(2, item))

    async def selecionar_categoria_acerto(self, interaction: discord.Interaction) -> None:
        categoria = self.acerto.values[0]
        item = dict(self.item)
        if categoria == "Nenhuma":
            item["rolagem de acerto"] = "Nenhuma"
            await interaction.response.edit_message(view=self.nova(3, item))
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "🎯 Rolagem de Acerto",
                "Escolha o atributo ou a perícia usada para acertar.",
            ),
            view=EscolherBonusHabilidadeNPCView(
                self.usuario_id,
                self.caminho,
                item,
                finalidade="acerto",
                categoria=categoria,
                indice_edicao=self.indice_edicao,
                original=self.original,
            ),
        )

    async def selecionar_resistencia(self, interaction: discord.Interaction) -> None:
        item = dict(self.item)
        item["rolagem de resistência"] = self.resistencia.values[0]
        await interaction.response.edit_message(view=self.nova(3, item))

    async def selecionar_reacao(self, interaction: discord.Interaction) -> None:
        item = dict(self.item)
        item["rolagem de reação"] = self.reacao.values[0]
        if item["rolagem de reação"] != "Efeito Direto":
            item.pop("CD do efeito", None)
        await interaction.response.edit_message(view=self.nova(3, item))

    async def selecionar_tipo_efeito(self, interaction: discord.Interaction) -> None:
        item = dict(self.item)
        item["tipo de efeito"] = self.tipo_efeito.values[0]
        await interaction.response.edit_message(view=self.nova(4, item))

    async def selecionar_necessita_rolagem(self, interaction: discord.Interaction) -> None:
        item = dict(self.item)
        item["necessita de rolagem"] = self.necessita_rolagem.values[0]
        await interaction.response.edit_message(view=self.nova(4, item))

    async def selecionar_dado(self, interaction: discord.Interaction) -> None:
        item = dict(self.item)
        item["dado de efeito"] = self.dado.values[0]
        await interaction.response.edit_message(view=self.nova(5, item))

    async def selecionar_numero(self, interaction: discord.Interaction) -> None:
        item = dict(self.item)
        item["número de dados"] = self.numero.values[0]
        await interaction.response.edit_message(view=self.nova(5, item))

    async def selecionar_categoria_modificador(self, interaction: discord.Interaction) -> None:
        categoria = self.modificador_efeito.values[0]
        item = dict(self.item)
        if categoria == "Nulo":
            item["modificador de efeito"] = "Nulo"
            await interaction.response.edit_message(view=self.nova(5, item))
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "🎲 Modificador de Efeito",
                "Escolha o atributo ou a perícia somada ao efeito.",
            ),
            view=EscolherBonusHabilidadeNPCView(
                self.usuario_id,
                self.caminho,
                item,
                finalidade="efeito",
                categoria=categoria,
                indice_edicao=self.indice_edicao,
                original=self.original,
            ),
        )

    async def continuar(self, interaction: discord.Interaction) -> None:
        item = dict(self.item)
        if self.etapa == 0:
            if not item.get("tipo de ativação") or not item.get("tipo de ação"):
                await interaction.response.send_message(
                    "Escolha o tipo de ativação e o tipo de ação.", ephemeral=True
                )
                return
            if item["tipo de ativação"] == "Reação" and item["tipo de ação"] != "Reação":
                await interaction.response.send_message(
                    "Uma habilidade de reação deve usar a ação Reação.", ephemeral=True
                )
                return
            await interaction.response.edit_message(
                embed=embed_painel(
                    "✨ Alcance, Alvo, Duração e Recarga",
                    "Defina onde, quem, por quanto tempo e com que frequência a habilidade atua.",
                ),
                view=self.nova(1, item),
            )
            return
        if self.etapa == 1:
            faltando = [
                chave for chave in ("alcance", "alvo", "duração", "recarga")
                if not item.get(chave)
            ]
            if faltando:
                await interaction.response.send_message(
                    "Escolha o alcance, o alvo, a duração e a recarga.", ephemeral=True
                )
                return
            if item.get("tipo de ativação") == "Passiva":
                item["modo de custo"] = "Sem Custo"
                item["custo de PH"] = "0"
                aplicar_modo_custo_habilidade_npc(item)
                await interaction.response.edit_message(
                    embed=embed_painel(
                        "✨ Rolagens",
                        "Escolha as rolagens de acerto, resistência e reação.",
                    ),
                    view=self.nova(3, item),
                )
                return
            await interaction.response.edit_message(
                embed=embed_painel(
                    "✨ Modo de Custo e Custo de PH",
                    "Escolha como o custo é aplicado; o valor em PH só será solicitado quando necessário.",
                ),
                view=self.nova(2, item),
            )
            return
        if self.etapa == 2:
            if not item.get("modo de custo"):
                await interaction.response.send_message(
                    "Escolha o modo de custo.", ephemeral=True
                )
                return
            if item["modo de custo"] != "Sem Custo" and not item.get("custo de PH"):
                await interaction.response.send_message(
                    "Escolha o custo de PH.", ephemeral=True
                )
                return
            aplicar_modo_custo_habilidade_npc(item)
            await interaction.response.edit_message(
                embed=embed_painel(
                    "✨ Rolagens",
                    "Escolha as rolagens de acerto, resistência e reação.",
                ),
                view=self.nova(3, item),
            )
            return
        if self.etapa == 3:
            if not all(
                item.get(chave)
                for chave in ("rolagem de acerto", "rolagem de resistência", "rolagem de reação")
            ):
                await interaction.response.send_message(
                    "Escolha as três rolagens.", ephemeral=True
                )
                return
            await interaction.response.edit_message(
                embed=embed_painel(
                    "✨ Tipo de Efeito",
                    "Classifique o efeito e informe se ele necessita de uma rolagem própria.",
                ),
                view=self.nova(4, item),
            )
            return
        if self.etapa == 4:
            if not item.get("tipo de efeito") or not item.get("necessita de rolagem"):
                await interaction.response.send_message(
                    "Escolha o tipo de efeito e se necessita de rolagem.", ephemeral=True
                )
                return
            if item["necessita de rolagem"] == "Não":
                for chave in (
                    "dado de efeito", "número de dados", "modificador de efeito", "efeito calculado"
                ):
                    item.pop(chave, None)
                if item.get("rolagem de reação") == "Efeito Direto":
                    item["CD do efeito"] = str(
                        10 + self.ficha.nivel // 2
                        + bonus_cd_habilidade_npc(self.ficha, item)
                    )
                await interaction.response.send_modal(
                    HabilidadeNPCModalFinal(
                        self.usuario_id, self.caminho, item,
                        self.indice_edicao, self.original,
                    )
                )
                return
            await interaction.response.edit_message(
                embed=embed_painel(
                    "✨ Efeito da Habilidade",
                    "Escolha o dado, o número de dados e o modificador do efeito.",
                ),
                view=self.nova(5, item),
            )
            return
        if not all(
            item.get(chave)
            for chave in ("dado de efeito", "número de dados", "modificador de efeito")
        ):
            await interaction.response.send_message(
                "Escolha o dado, o número de dados e o modificador do efeito.", ephemeral=True
            )
            return
        atualizar_efeito_habilidade_npc(
            self.ficha, item, item["modificador de efeito"]
        )
        await interaction.response.send_modal(
            HabilidadeNPCModalFinal(
                self.usuario_id, self.caminho, item,
                self.indice_edicao, self.original,
            )
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        if self.etapa == 0:
            ficha = FichaPersonagem.carregar(self.caminho)
            await interaction.response.edit_message(
                embed=embed_gerenciar_habilidades_npc(ficha),
                view=GerenciarHabilidadesNPCView(self.usuario_id, self.caminho),
            )
            return
        if self.etapa == 3 and self.item.get("tipo de ativação") == "Passiva":
            await interaction.response.edit_message(
                embed=embed_painel(
                    "✨ Alcance, Alvo, Duração e Recarga",
                    "Revise o alcance, o alvo, a duração e a recarga.",
                ),
                view=self.nova(1),
            )
            return
        titulos = {
            1: ("✨ Configurar habilidade", "Revise o tipo de ativação e o tipo de ação."),
            2: ("✨ Alcance, Alvo, Duração e Recarga", "Revise o alcance, o alvo, a duração e a recarga."),
            3: ("✨ Modo de Custo e Custo de PH", "Revise o modo e o custo da habilidade."),
            4: ("✨ Rolagens", "Revise as rolagens da habilidade."),
            5: ("✨ Tipo de Efeito", "Revise a classificação e a necessidade de rolagem."),
        }
        titulo, descricao = titulos[self.etapa]
        await interaction.response.edit_message(
            embed=embed_painel(titulo, descricao),
            view=self.nova(self.etapa - 1),
        )


class EscolherBonusHabilidadeNPCView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        item: dict[str, str],
        *,
        finalidade: str,
        categoria: str,
        indice_edicao: int | None,
        original: dict[str, str] | None,
        pagina: int = 0,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.item = item
        self.finalidade = finalidade
        self.categoria = categoria
        self.indice_edicao = indice_edicao
        self.original = original
        self.pagina = pagina
        ficha = FichaPersonagem.carregar(caminho)
        self.ficha = ficha
        if categoria == "Atributo":
            self.paginas = [("Atributos", list(ATRIBUTOS))]
        else:
            self.paginas = paginas_pericias()
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        rotulo, valores = self.paginas[self.pagina]
        seletor = discord.ui.Select(
            placeholder=f"{categoria} — {rotulo}",
            options=[
                discord.SelectOption(
                    label=valor,
                    value=valor,
                    description=(
                        f"Bônus atual: {formatar_bonus(bonus_escolha_habilidade_npc(ficha, valor))}"
                    ),
                )
                for valor in valores
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

    def nova(self, pagina: int) -> "EscolherBonusHabilidadeNPCView":
        return EscolherBonusHabilidadeNPCView(
            self.usuario_id, self.caminho, self.item,
            finalidade=self.finalidade, categoria=self.categoria,
            indice_edicao=self.indice_edicao, original=self.original, pagina=pagina,
        )

    def wizard(self, item: dict[str, str]) -> HabilidadeNPCWizardView:
        return HabilidadeNPCWizardView(
            self.usuario_id, self.caminho, item,
            etapa=3 if self.finalidade == "acerto" else 5,
            indice_edicao=self.indice_edicao, original=self.original,
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        escolha = self.seletor.values[0]
        item = dict(self.item)
        if self.finalidade == "acerto":
            item["rolagem de acerto"] = escolha_habilidade_npc_com_bonus(
                self.ficha, escolha
            )
        else:
            item["modificador de efeito"] = escolha_habilidade_npc_com_bonus(
                self.ficha, escolha
            )
        await interaction.response.edit_message(
            embed=embed_painel(
                "✨ Configurar habilidade", "Continue preenchendo os campos."
            ),
            view=self.wizard(item),
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=self.nova(self.pagina - 1))

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=self.nova(self.pagina + 1))

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "✨ Configurar habilidade", "Escolha novamente a categoria."
            ),
            view=self.wizard(dict(self.item)),
        )


class HabilidadeNPCModalFinal(discord.ui.Modal):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        item: dict[str, str],
        indice_edicao: int | None,
        original: dict[str, str] | None,
    ):
        super().__init__(title="Criar habilidade do NPC")
        self.usuario_id = usuario_id
        self.caminho = caminho
        self.item = dict(item)
        self.indice_edicao = indice_edicao
        self.original = dict(original) if original is not None else None
        self.nome = discord.ui.TextInput(
            label="Nome", default=item.get("nome", ""), max_length=100
        )
        self.descricao = discord.ui.TextInput(
            label="Descrição", default=item.get("descrição", ""),
            style=discord.TextStyle.paragraph, max_length=1500,
        )
        self.efeito = discord.ui.TextInput(
            label="Efeito",
            default=item.get("efeito", ficha_criaturas.resumo_efeito_habilidade(item))[:1500],
            style=discord.TextStyle.paragraph,
            max_length=1500,
        )
        self.add_item(self.nome)
        self.add_item(self.descricao)
        self.add_item(self.efeito)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        item = dict(self.item)
        item["nome"] = str(self.nome.value).strip()
        item["descrição"] = str(self.descricao.value).strip()
        item["efeito"] = str(self.efeito.value).strip()
        if not all((item["nome"], item["descrição"], item["efeito"])):
            await interaction.response.send_message(
                "Nome, descrição e efeito são obrigatórios.", ephemeral=True
            )
            return
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            ficha = FichaPersonagem.carregar(self.caminho)
            if ficha.grupo != "NPCs" or ficha.tipo_npc in {"", "Bruxo(a)"}:
                await interaction.response.send_message(
                    "Esta ficha não usa o criador de habilidades de NPC.", ephemeral=True
                )
                return
            if any(
                normalizar_rotulo(registro.get("nome", "")) == normalizar_rotulo(item["nome"])
                and indice != self.indice_edicao
                for indice, registro in enumerate(ficha.habilidades_npc)
            ):
                await interaction.response.send_message(
                    "Já existe uma habilidade com esse nome na ficha.", ephemeral=True
                )
                return
            if self.indice_edicao is None:
                ficha.habilidades_npc.append(item)
            else:
                if (
                    self.indice_edicao >= len(ficha.habilidades_npc)
                    or ficha.habilidades_npc[self.indice_edicao] != self.original
                ):
                    await interaction.response.send_message(
                        "A habilidade mudou durante a edição. Consulte a ficha novamente.",
                        ephemeral=True,
                    )
                    return
                ficha.habilidades_npc[self.indice_edicao] = item
            validar_tamanho_ficha(ficha)
            salvar_ficha(ficha, self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
            attachments=criar_arquivos_discord(anexos_ficha(ficha)),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)


def embed_mecanicas_habilidades(ficha: FichaPersonagem) -> discord.Embed:
    linhas = [f"**XP:** {ficha.xp} | **PH:** {ficha.ph} | **Alma:** {ficha.alma}%"]
    automaticos = resumo_automaticos(ficha)
    condicionais = resumo_condicionais(ficha)
    if automaticos:
        linhas.extend(("", "## Aplicação automática", *automaticos))
    if condicionais:
        linhas.extend(("", "## Aplicação contextual", *condicionais))
    if ficha.efeitos_habilidades_ativos:
        linhas.extend(("", "## Efeitos ativos"))
        linhas.extend(
            f"**{efeito['nome']}:** {efeito['efeito']} — {efeito.get('duracao', '--')}"
            for efeito in ficha.efeitos_habilidades_ativos
        )
    return embed_painel("⚙️ Mecânicas de Habilidades", "\n".join(linhas))


def aplicar_mecanica_habilidade(
    ficha: FichaPersonagem,
    acao: str,
    item: str = "",
) -> str:
    if acao == "xp_para_ph":
        if not possui(ficha.especializacoes, "Hábil e Experiente"):
            raise ValueError("A ficha não possui Hábil e Experiente.")
        if ficha.xp < 10:
            raise ValueError("XP insuficiente: a conversão custa 10 XP.")
        ficha.xp -= 10
        ficha.ph += 1
        return "Foram convertidos **10 XP** em **1 PH excedente**."
    if acao == "alma_contato_visual":
        if not possui(ficha.origens_magicas, "Magia por Contato Visual"):
            raise ValueError("A ficha não possui Magia por Contato Visual.")
        if ficha.ph > 0:
            raise ValueError("A troca por Alma só pode ser usada quando a ficha não possui PH.")
        nivel = int(item)
        if nivel < 1 or nivel > 7:
            raise ValueError("Escolha um nível de feitiço entre 1 e 7.")
        if ficha.alma < nivel:
            raise ValueError("Alma insuficiente para este feitiço.")
        ficha.alma -= nivel
        return f"Foram perdidos permanentemente **{nivel}% de Alma** pelo feitiço de nível {nivel}."
    if acao == "encerrar_efeito":
        indice = int(item)
        if indice < 0 or indice >= len(ficha.efeitos_habilidades_ativos):
            raise ValueError("O efeito escolhido não está mais ativo.")
        efeito = ficha.efeitos_habilidades_ativos.pop(indice)
        return f"O efeito **{efeito['nome']}** foi encerrado."
    raise ValueError("Mecânica de habilidade desconhecida.")


def acoes_ph_habilidade(categoria: str, nome: str) -> list[dict[str, object]]:
    entrada = carregar_habilidade(categoria, nome)
    if entrada is None:
        return []
    campos = {
        normalizar_rotulo(rotulo): valor
        for rotulo, valor in entrada.campos.items()
    }
    acoes: list[dict[str, object]] = []
    if categoria == "heranca_sanguinea":
        inicial = campos.get(normalizar_rotulo("Habilidade Inicial"), "")
        for indice, correspondencia in enumerate(
            re.finditer(
                r"\*\*(?P<custo>\d+\s*ph)\s*:?[\*]*\s*(?P<descricao>.*?)"
                r"(?=\n\s*\*\*|\Z)",
                inicial,
                re.DOTALL | re.IGNORECASE,
            )
        ):
            custos = custos_ph_texto(correspondencia.group("custo"))
            if custos:
                acoes.append(
                    {
                        "nome": f"Habilidade Inicial — {custos[0]}ph",
                        "custos": custos,
                        "custo_texto": correspondencia.group("custo").strip(),
                        "descricao": correspondencia.group("descricao").strip(" :\n"),
                        "evolucao": 0,
                    }
                )
        evolucoes = campos.get(normalizar_rotulo("Evoluções"), "")
        padrao_evolucao = re.compile(
            r"\*\*(?P<nome>[^*\n]+?)\s*[-—]\s*(?P<custo>[^:*]+):\*\*\s*(?P<descricao>.*?)"
            r"(?=\n\n\*\*|\Z)",
            re.DOTALL,
        )
        for numero, correspondencia in enumerate(padrao_evolucao.finditer(evolucoes), 1):
            custos = custos_ph_texto(correspondencia.group("custo"))
            if custos:
                acoes.append(
                    {
                        "nome": correspondencia.group("nome").strip(),
                        "custos": custos,
                        "custo_texto": correspondencia.group("custo").strip(),
                        "descricao": correspondencia.group("descricao").strip(),
                        "evolucao": numero,
                    }
                )
        return acoes
    if categoria == "origem_magica":
        texto = campos.get(normalizar_rotulo("Habilidades"), "")
        padrao = re.compile(
            r"\*\*(?P<nome>[^*\n]+?)\s*//\s*(?P<custo>[^:*]+):\*\*\s*(?P<descricao>.*?)"
            r"(?=\n\n\*\*|\Z)",
            re.DOTALL,
        )
        for correspondencia in padrao.finditer(texto):
            custo_texto = correspondencia.group("custo").strip()
            custos = custos_ph_texto(custo_texto)
            if custos:
                acoes.append(
                    {
                        "nome": correspondencia.group("nome").strip(),
                        "custos": custos,
                        "custo_texto": custo_texto,
                        "descricao": correspondencia.group("descricao").strip(),
                    }
                )
        return acoes
    custo_texto = campos.get(normalizar_rotulo("Custo de PH"), "")
    subacoes = re.compile(
        r"\*\*(?P<nome>[^*\n]+?)\s*//\s*(?P<custo>\d+\s*ph):\*\*\s*(?P<descricao>.*?)"
        r"(?=\n|\Z)",
        re.IGNORECASE,
    )
    for correspondencia in subacoes.finditer(entrada.descricao):
        acoes.append(
            {
                "nome": correspondencia.group("nome").strip(),
                "custos": custos_ph_texto(correspondencia.group("custo")),
                "custo_texto": correspondencia.group("custo").strip(),
                "descricao": correspondencia.group("descricao").strip(),
            }
        )
    if acoes:
        return acoes
    if normalizar_rotulo(nome) == normalizar_rotulo("Mestre Espadachim"):
        correspondencia = re.search(
            r"\*\*(?P<custo>\d+\s*ph):\*\*\s*(?P<descricao>.*)$",
            entrada.descricao,
            re.IGNORECASE | re.DOTALL,
        )
        if correspondencia:
            return [
                {
                    "nome": "Antecipar Golpes",
                    "custos": custos_ph_texto(correspondencia.group("custo")),
                    "custo_texto": correspondencia.group("custo").strip(),
                    "descricao": correspondencia.group("descricao").strip(),
                }
            ]
    custos = custos_ph_texto(custo_texto)
    if custos:
        acoes.append(
            {
                "nome": nome,
                "custos": custos,
                "custo_texto": custo_texto,
                "descricao": entrada.descricao.strip(),
            }
        )
    return acoes


def custos_ph_texto(texto: str) -> list[int]:
    normalizado = normalizar_rotulo(texto)
    encontrados = [int(valor) for valor in re.findall(r"(\d+)\s*ph", normalizado)]
    if not encontrados:
        return []
    if " a " in normalizado and len(encontrados) >= 2:
        inicio, fim = encontrados[0], encontrados[-1]
        passo = 2 if inicio % 2 == 0 and fim % 2 == 0 else 1
        return list(range(inicio, fim + 1, passo))
    return list(dict.fromkeys(encontrados))


def acoes_ph_possuidas(ficha: FichaPersonagem) -> list[tuple[str, str, dict[str, object]]]:
    resultado: list[tuple[str, str, dict[str, object]]] = []
    for categoria, nomes in (
        ("heranca_sanguinea", [ficha.heranca]),
        ("origem_magica", ficha.origens_magicas),
        ("especializacao", ficha.especializacoes),
    ):
        for nome in nomes:
            for acao in acoes_ph_habilidade(categoria, nome):
                if categoria == "heranca_sanguinea" and int(acao.get("evolucao", 0)) > ficha.evolucao_heranca:
                    continue
                resultado.append((categoria, nome, acao))
    return resultado


def aplicar_uso_ph_habilidade(
    ficha: FichaPersonagem,
    categoria: str,
    nome: str,
    nome_acao: str,
    custo: int,
) -> str:
    if categoria == "heranca_sanguinea":
        possuidas = [ficha.heranca]
    elif categoria == "origem_magica":
        possuidas = ficha.origens_magicas
    else:
        possuidas = ficha.especializacoes
    if not possui(possuidas, nome):
        raise ValueError("A ficha não possui mais esta habilidade.")
    acao = next(
        (
            item
            for item in acoes_ph_habilidade(categoria, nome)
            if normalizar_rotulo(str(item["nome"])) == normalizar_rotulo(nome_acao)
        ),
        None,
    )
    if acao is None or custo not in acao["custos"]:
        raise ValueError("A mecânica ou o custo da habilidade mudou na biblioteca.")
    if categoria == "heranca_sanguinea" and int(acao.get("evolucao", 0)) > ficha.evolucao_heranca:
        raise ValueError("Esta evolução da Herança Sanguínea ainda não foi desbloqueada.")
    if ficha.ph < custo:
        raise ValueError(f"PH insuficiente: esta ativação custa {custo}ph e a ficha possui {ficha.ph}ph.")
    ficha.ph -= custo
    if (
        categoria == "especializacao"
        and normalizar_rotulo(nome) == normalizar_rotulo("Prodígio do Quadribol")
    ):
        if any(
            normalizar_rotulo(efeito.get("nome", ""))
            == normalizar_rotulo("Prodígio do Quadribol")
            for efeito in ficha.efeitos_habilidades_ativos
        ):
            ficha.ph += custo
            raise ValueError("Prodígio do Quadribol já está ativo nesta ficha.")
        ficha.efeitos_habilidades_ativos.append(
            {
                "nome": "Prodígio do Quadribol",
                "efeito": "+2 no teste correspondente à posição do jogador.",
                "duracao": "Até encerrar o efeito",
            }
        )
        return (
            f"**Prodígio do Quadribol** consumiu **{custo}ph** e concedeu **+2** "
            "ao teste da posição enquanto estiver ativo."
        )
    if (
        categoria == "especializacao"
        and normalizar_rotulo(nome) == normalizar_rotulo("Devorador de Livros")
    ):
        ficha.xp += 2
        return (
            f"**{nome_acao}** consumiu **{custo}ph** e concedeu **+2 XP** pela aula. "
            f"PH restante: **{ficha.ph}**."
        )
    return f"**{nome_acao}** foi ativada por **{custo}ph**. PH restante: **{ficha.ph}**."


class MecanicasHabilidadesView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path, ficha: FichaPersonagem):
        super().__init__(usuario_id)
        self.caminho = caminho
        if acoes_ph_possuidas(ficha):
            usar = discord.ui.Button(
                label="Usar habilidade",
                style=discord.ButtonStyle.secondary,
                emoji="✨",
                row=0,
            )
            usar.callback = self.usar_habilidade
            self.add_item(usar)
        if possui(ficha.especializacoes, "Hábil e Experiente"):
            converter = discord.ui.Button(
                label="10 XP → 1 PH",
                style=discord.ButtonStyle.secondary,
                emoji="🔄",
                row=0,
            )
            converter.callback = self.converter
            self.add_item(converter)
        if possui(ficha.origens_magicas, "Magia por Contato Visual"):
            contato = discord.ui.Button(
                label="Contato Visual com Alma",
                style=discord.ButtonStyle.secondary,
                emoji="👁️",
                disabled=ficha.ph > 0,
                row=0,
            )
            contato.callback = self.contato_visual
            self.add_item(contato)
        if ficha.efeitos_habilidades_ativos:
            encerrar = discord.ui.Button(
                label="Encerrar efeito",
                style=discord.ButtonStyle.secondary,
                emoji="🏁",
                row=1,
            )
            encerrar.callback = self.encerrar_efeito
            self.add_item(encerrar)
        voltar = discord.ui.Button(label="Voltar à ficha", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def converter(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🔄 Hábil e Experiente",
                "Converter **10 XP** em **1 Ponto de Habilidade excedente**? A conversão não pode ser revertida.",
            ),
            view=ConfirmarMecanicaHabilidadeView(
                self.usuario_id, self.caminho, "xp_para_ph", ""
            ),
        )

    async def usar_habilidade(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "✨ Usar habilidade",
                f"Escolha uma mecânica disponível. **PH atual:** {ficha.ph}.",
            ),
            view=SelecionarUsoHabilidadeView(self.usuario_id, self.caminho, ficha),
        )

    async def contato_visual(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "👁️ No Pain, No Gain",
                "Sem PH, escolha o nível do feitiço. A mesma quantidade será removida permanentemente da Alma.",
            ),
            view=NivelContatoVisualView(self.usuario_id, self.caminho),
        )

    async def encerrar_efeito(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel("🏁 Encerrar efeito", "Escolha o efeito concluído."),
            view=EncerrarEfeitoHabilidadeView(self.usuario_id, self.caminho, ficha),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )


class SelecionarUsoHabilidadeView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        ficha: FichaPersonagem,
        pagina: int = 0,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.acoes = acoes_ph_possuidas(ficha)
        self.paginas = [self.acoes[i:i + 25] for i in range(0, len(self.acoes), 25)] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        inicio = self.pagina * 25
        seletor = discord.ui.Select(
            placeholder=f"Habilidades — página {self.pagina + 1}/{len(self.paginas)}",
            options=[
                discord.SelectOption(
                    label=f"{nome} — {acao['nome']}"[:100],
                    value=str(inicio + indice),
                    description=(
                        ", ".join(f"{custo}ph" for custo in acao["custos"])
                        + " — " + str(acao["descricao"])
                    )[:100],
                )
                for indice, (_, nome, acao) in enumerate(self.paginas[self.pagina])
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
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
        categoria, nome, acao = self.acoes[int(self.seletor.values[0])]
        custos = list(acao["custos"])
        if len(custos) == 1:
            await interaction.response.edit_message(
                embed=embed_confirmar_uso_habilidade(nome, acao, custos[0]),
                view=ConfirmarUsoPHView(
                    self.usuario_id, self.caminho, categoria, nome,
                    str(acao["nome"]), custos[0],
                ),
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                f"✨ {nome} — {acao['nome']}",
                str(acao["descricao"]) + "\n\nEscolha o custo aplicado nesta ativação.",
            ),
            view=SelecionarCustoUsoHabilidadeView(
                self.usuario_id, self.caminho, categoria, nome, acao
            ),
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            view=SelecionarUsoHabilidadeView(self.usuario_id, self.caminho, ficha, self.pagina - 1)
        )

    async def proxima(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            view=SelecionarUsoHabilidadeView(self.usuario_id, self.caminho, ficha, self.pagina + 1)
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_mecanicas_habilidades(ficha),
            view=MecanicasHabilidadesView(self.usuario_id, self.caminho, ficha),
        )


def embed_confirmar_uso_habilidade(
    nome: str,
    acao: dict[str, object],
    custo: int,
) -> discord.Embed:
    return embed_painel(
        f"✨ {nome} — {acao['nome']}",
        str(acao["descricao"])
        + f"\n\nConfirmar o gasto de **{custo}ph**? O gasto será aplicado à ficha.",
    )


class SelecionarCustoUsoHabilidadeView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        categoria: str,
        nome: str,
        acao: dict[str, object],
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.categoria = categoria
        self.nome = nome
        self.acao = acao
        seletor = discord.ui.Select(
            placeholder="Escolha o custo em PH",
            options=[
                discord.SelectOption(label=f"{custo}ph", value=str(custo))
                for custo in acao["custos"]
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        custo = int(self.seletor.values[0])
        await interaction.response.edit_message(
            embed=embed_confirmar_uso_habilidade(self.nome, self.acao, custo),
            view=ConfirmarUsoPHView(
                self.usuario_id, self.caminho, self.categoria, self.nome,
                str(self.acao["nome"]), custo,
            ),
        )


class ConfirmarUsoPHView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        categoria: str,
        nome: str,
        nome_acao: str,
        custo: int,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.categoria = categoria
        self.nome = nome
        self.nome_acao = nome_acao
        self.custo = custo
        self.concluido = False

    @discord.ui.button(label="Confirmar uso", style=discord.ButtonStyle.success, emoji="✅")
    async def confirmar(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        if self.concluido:
            await interaction.response.send_message("Este uso já foi encerrado.", ephemeral=True)
            return
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            ficha = FichaPersonagem.carregar(self.caminho)
            try:
                mensagem = aplicar_uso_ph_habilidade(
                    ficha, self.categoria, self.nome, self.nome_acao, self.custo
                )
            except ValueError as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return
            salvar_ficha(ficha, self.caminho)
        self.concluido = True
        self.stop()
        await interaction.response.edit_message(
            embed=embed_painel("✅ Habilidade ativada", mensagem),
            view=MecanicasHabilidadesView(self.usuario_id, self.caminho, ficha),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary)
    async def voltar(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_mecanicas_habilidades(ficha),
            view=MecanicasHabilidadesView(self.usuario_id, self.caminho, ficha),
        )


class NivelContatoVisualView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__(usuario_id)
        self.caminho = caminho
        seletor = discord.ui.Select(
            placeholder="Escolha o nível do feitiço",
            options=[
                discord.SelectOption(
                    label=f"Nível {nivel}", value=str(nivel),
                    description=f"Perde permanentemente {nivel}% de Alma.",
                )
                for nivel in range(1, 8)
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        nivel = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=embed_painel(
                "👁️ Confirmar perda de Alma",
                f"Conjurar o feitiço de nível **{nivel}** e perder permanentemente **{nivel}% de Alma**?",
            ),
            view=ConfirmarMecanicaHabilidadeView(
                self.usuario_id, self.caminho, "alma_contato_visual", nivel
            ),
        )


class EncerrarEfeitoHabilidadeView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path, ficha: FichaPersonagem):
        super().__init__(usuario_id)
        self.caminho = caminho
        seletor = discord.ui.Select(
            placeholder="Escolha o efeito",
            options=[
                discord.SelectOption(label=efeito["nome"][:100], value=str(indice))
                for indice, efeito in enumerate(ficha.efeitos_habilidades_ativos[:25])
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        indice = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=embed_painel("🏁 Confirmar encerramento", "Remover este efeito ativo da ficha?"),
            view=ConfirmarMecanicaHabilidadeView(
                self.usuario_id, self.caminho, "encerrar_efeito", indice
            ),
        )


class ConfirmarMecanicaHabilidadeView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path, acao: str, item: str):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.acao = acao
        self.item = item
        self.concluido = False

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, emoji="✅")
    async def confirmar(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        if self.concluido:
            await interaction.response.send_message("Esta operação já foi encerrada.", ephemeral=True)
            return
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            ficha = FichaPersonagem.carregar(self.caminho)
            try:
                mensagem = aplicar_mecanica_habilidade(ficha, self.acao, self.item)
            except (ValueError, IndexError) as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return
            salvar_ficha(ficha, self.caminho)
        self.concluido = True
        self.stop()
        await interaction.response.edit_message(
            embed=embed_painel("✅ Mecânica aplicada", mensagem),
            view=MecanicasHabilidadesView(self.usuario_id, self.caminho, ficha),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary)
    async def voltar(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_mecanicas_habilidades(ficha),
            view=MecanicasHabilidadesView(self.usuario_id, self.caminho, ficha),
        )


class MecanicasSanguePuroView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        ficha: FichaPersonagem,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        if heranca_desbloqueada(ficha, 1):
            rotulo_evento = {
                normalizar_rotulo("Sangue Puro"): "Maestria 18+ — +2 XP",
                normalizar_rotulo("Meio-Sangue"): "Crítico +2 XP",
                normalizar_rotulo("Nascido-Trouxa"): "Ação trouxa — +2 XP",
            }[normalizar_rotulo(ficha.heranca)]
            maestria = discord.ui.Button(
                label=rotulo_evento,
                style=discord.ButtonStyle.secondary,
                emoji="✨",
                row=0,
            )
            maestria.callback = self.registrar_maestria
            self.add_item(maestria)
        if heranca_desbloqueada(ficha, 3):
            atributo = discord.ui.Button(
                label="Atributo +2 — 10 XP",
                style=discord.ButtonStyle.secondary,
                emoji="🔥",
                row=1,
            )
            atributo.callback = self.escolher_atributo
            self.add_item(atributo)
        if sangue_puro_desbloqueado(ficha, 5):
            intermediario = discord.ui.Button(
                label="Intermediário — 5 XP",
                style=discord.ButtonStyle.secondary,
                emoji="🪄",
                row=2,
            )
            avancado = discord.ui.Button(
                label="Avançado — 10 XP",
                style=discord.ButtonStyle.secondary,
                emoji="🪄",
                row=2,
            )
            intermediario.callback = self.preparar_intermediario
            avancado.callback = self.preparar_avancado
            self.add_item(intermediario)
            self.add_item(avancado)
        if (
            heranca_desbloqueada(ficha, 5)
            and normalizar_rotulo(ficha.heranca) == normalizar_rotulo("Meio-Sangue")
        ):
            catalisador = discord.ui.Button(
                label="Catalisador — 5 XP",
                style=discord.ButtonStyle.secondary,
                emoji="🪄",
                row=2,
            )
            catalisador.callback = self.preparar_catalisador
            self.add_item(catalisador)
        if (
            heranca_desbloqueada(ficha, 5)
            and normalizar_rotulo(ficha.heranca) == normalizar_rotulo("Nascido-Trouxa")
        ):
            improvisar = discord.ui.Button(
                label="Usar Especialização — 5 XP",
                style=discord.ButtonStyle.secondary,
                emoji="🎓",
                row=2,
            )
            improvisar.callback = self.escolher_especializacao
            self.add_item(improvisar)
        if any(ficha.reducoes_dificuldade_heranca.values()):
            consumir = discord.ui.Button(
                label="Consumir redução",
                style=discord.ButtonStyle.secondary,
                emoji="✅",
                row=3,
            )
            consumir.callback = self.consumir_reducao
            self.add_item(consumir)
        if any(ficha.bonus_atributos_temporarios.values()):
            encerrar = discord.ui.Button(
                label="Encerrar cena",
                style=discord.ButtonStyle.secondary,
                emoji="🏁",
                row=3,
            )
            encerrar.callback = self.encerrar_cena
            self.add_item(encerrar)
        voltar = discord.ui.Button(
            label="Voltar à ficha",
            style=discord.ButtonStyle.secondary,
            row=4,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def registrar_maestria(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        heranca = normalizar_rotulo(ficha.heranca)
        descricoes = {
            normalizar_rotulo("Sangue Puro"): "Confirme que a ficha executou um feitiço com **maestria** e obteve resultado **18 ou maior**.",
            normalizar_rotulo("Meio-Sangue"): "Confirme que a ficha obteve **sucesso crítico em uma ação**.",
            normalizar_rotulo("Nascido-Trouxa"): "Confirme que a ficha executou uma **ação de natureza trouxa**.",
        }
        await interaction.response.edit_message(
            embed=embed_painel(
                "✨ Registrar evento",
                descricoes[heranca] + " A Primeira Evolução concederá **+2 XP**.",
            ),
            view=ConfirmarMecanicaSanguePuroView(
                self.usuario_id,
                self.caminho,
                "maestria" if heranca == normalizar_rotulo("Sangue Puro") else "evento",
                "",
            ),
        )

    async def preparar_catalisador(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🪄 Catalisador Temporário",
                "Gaste **5 XP** para transformar um objeto não mágico em catalisador por **1d4+1 rodadas**.",
            ),
            view=ConfirmarMecanicaSanguePuroView(
                self.usuario_id, self.caminho, "catalisador", ""
            ),
        )

    async def escolher_especializacao(self, interaction: discord.Interaction) -> None:
        nomes = listar_habilidades("especializacao", limite=None)
        await interaction.response.edit_message(
            embed=embed_painel(
                "🎓 Especialização improvisada",
                "Escolha a Especialização usada sem cumprir os requisitos. A ativação custa **5 XP**.",
            ),
            view=SelecionarEspecializacaoImprovisadaView(
                self.usuario_id, self.caminho, nomes, 0
            ),
        )

    async def escolher_atributo(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "🔥 Terceira Evolução",
                "Escolha o atributo que receberá +2 durante a cena. "
                "O bônus é cumulativo e custa 10 XP por ativação.",
            ),
            view=SelecionarAtributoSanguePuroView(
                self.usuario_id,
                self.caminho,
                ficha,
            ),
        )

    async def preparar_intermediario(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🪄 Preparar redução",
                "Gaste **5 XP** para reduzir em um nível a dificuldade de um "
                "feitiço **Intermediário**. A redução ficará registrada até ser consumida.",
            ),
            view=ConfirmarMecanicaSanguePuroView(
                self.usuario_id,
                self.caminho,
                "reducao",
                "Intermediário",
            ),
        )

    async def preparar_avancado(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🪄 Preparar redução",
                "Gaste **10 XP** para reduzir em um nível a dificuldade de um "
                "feitiço **Avançado**. A redução ficará registrada até ser consumida.",
            ),
            view=ConfirmarMecanicaSanguePuroView(
                self.usuario_id,
                self.caminho,
                "reducao",
                "Avançado",
            ),
        )

    async def consumir_reducao(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "✅ Consumir redução",
                "Escolha a redução usada na conjuração. Esta ação não devolve XP.",
            ),
            view=SelecionarReducaoSanguePuroView(
                self.usuario_id,
                self.caminho,
                ficha,
            ),
        )

    async def encerrar_cena(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🏁 Encerrar cena",
                "Todos os bônus temporários de atributo concedidos pela Terceira "
                "Evolução serão removidos.",
            ),
            view=ConfirmarMecanicaSanguePuroView(
                self.usuario_id,
                self.caminho,
                "encerrar_cena",
                "",
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )


class SelecionarEspecializacaoImprovisadaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        nomes: list[str],
        pagina: int,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.nomes = nomes
        self.paginas = [nomes[i:i + 25] for i in range(0, len(nomes), 25)] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        seletor = discord.ui.Select(
            placeholder=f"Especialização — página {self.pagina + 1}/{len(self.paginas)}",
            options=[discord.SelectOption(label=nome[:100], value=nome) for nome in self.paginas[self.pagina]],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
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
        nome = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=embed_painel(
                "🎓 Confirmar Especialização",
                f"Gastar **5 XP** para usar **{nome}** sem cumprir seus requisitos?",
            ),
            view=ConfirmarMecanicaSanguePuroView(
                self.usuario_id, self.caminho, "especializacao_improvisada", nome
            ),
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=SelecionarEspecializacaoImprovisadaView(
                self.usuario_id, self.caminho, self.nomes, self.pagina - 1
            )
        )

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=SelecionarEspecializacaoImprovisadaView(
                self.usuario_id, self.caminho, self.nomes, self.pagina + 1
            )
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_mecanicas_heranca(ficha),
            view=MecanicasSanguePuroView(self.usuario_id, self.caminho, ficha),
        )


class SelecionarAtributoSanguePuroView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        ficha: FichaPersonagem,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        seletor = discord.ui.Select(
            placeholder="Escolha o atributo",
            options=[
                discord.SelectOption(
                    label=nome,
                    value=nome,
                    description=(
                        f"Bônus temporário atual: +{ficha.bonus_atributos_temporarios.get(nome, 0)}"
                    ),
                )
                for nome in ATRIBUTOS
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        atributo = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=embed_painel(
                "🔥 Confirmar Terceira Evolução",
                f"Gastar **10 XP** para conceder **+2 em {atributo}** até o fim "
                "da cena? A compra não poderá ser revertida.",
            ),
            view=ConfirmarMecanicaSanguePuroView(
                self.usuario_id,
                self.caminho,
                "atributo",
                atributo,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_mecanicas_heranca(ficha),
            view=MecanicasSanguePuroView(self.usuario_id, self.caminho, ficha),
        )


class SelecionarReducaoSanguePuroView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        ficha: FichaPersonagem,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        opcoes = [
            discord.SelectOption(
                label=nome,
                value=nome,
                description=f"{ficha.reducoes_dificuldade_heranca.get(nome, 0)} preparada(s)",
            )
            for nome in REDUCOES_DIFICULDADE
            if ficha.reducoes_dificuldade_heranca.get(nome, 0) > 0
        ]
        seletor = discord.ui.Select(
            placeholder="Escolha a redução consumida",
            options=opcoes,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        dificuldade = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=embed_painel(
                "✅ Confirmar consumo",
                f"Consumir uma redução de dificuldade para feitiço **{dificuldade}**?",
            ),
            view=ConfirmarMecanicaSanguePuroView(
                self.usuario_id,
                self.caminho,
                "consumir_reducao",
                dificuldade,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_mecanicas_heranca(ficha),
            view=MecanicasSanguePuroView(self.usuario_id, self.caminho, ficha),
        )


class ConfirmarMecanicaSanguePuroView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        acao: str,
        item: str,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.acao = acao
        self.item = item
        self.concluido = False

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, emoji="✅")
    async def confirmar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        if self.concluido:
            await interaction.response.send_message(
                "Esta operação já foi encerrada.",
                ephemeral=True,
            )
            return
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            try:
                ficha = FichaPersonagem.carregar(self.caminho)
                _, mensagem = aplicar_mecanica_heranca(
                    ficha,
                    self.acao,
                    self.item,
                )
                validar_tamanho_ficha(ficha)
                salvar_ficha(ficha, self.caminho)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return
        self.concluido = True
        self.stop()
        embeds = montar_embeds_ficha(ficha)
        embeds[0].set_footer(text=mensagem)
        await interaction.response.edit_message(
            embeds=embeds,
            view=FichaAtualView(self.usuario_id, self.caminho),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_mecanicas_heranca(ficha),
            view=MecanicasSanguePuroView(self.usuario_id, self.caminho, ficha),
        )


class ImagemFichaView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__(usuario_id)
        self.caminho = caminho
        seletor = discord.ui.Select(
            placeholder="Opções de Imagem",
            options=[
                discord.SelectOption(
                    label="Visualizar",
                    value="visualizar",
                    description="Escolhe qualquer aparência salva para visualizar.",
                    emoji="👁️",
                ),
                discord.SelectOption(
                    label="Adicionar",
                    value="adicionar",
                    description="Envia uma imagem PNG, JPG ou WEBP.",
                    emoji="➕",
                ),
                discord.SelectOption(
                    label="Remover",
                    value="remover",
                    description="Escolhe uma imagem salva para removê-la.",
                    emoji="➖",
                ),
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar à ficha",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        escolha = self.seletor.values[0]
        if escolha == "visualizar":
            ficha = FichaPersonagem.carregar(self.caminho)
            if not ficha.imagens:
                await interaction.response.send_message(
                    "A ficha ainda não possui imagens para visualizar.",
                    ephemeral=True,
                )
                return
            await interaction.response.edit_message(
                embed=embed_painel(
                    "🖼️ Visualizar aparência",
                    "Escolha a aparência que deseja abrir.",
                ),
                view=VisualizarImagemFichaView(
                    self.usuario_id,
                    self.caminho,
                    ficha.imagens,
                ),
                attachments=[],
            )
            return
        if escolha == "adicionar":
            await interaction.response.send_modal(
                AdicionarImagemFichaModal(self.usuario_id, self.caminho)
            )
            return
        ficha = FichaPersonagem.carregar(self.caminho)
        if not ficha.imagens:
            await interaction.response.send_message(
                "A ficha ainda não possui imagens para remover.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "🖼️ Remover imagem",
                "Escolha a imagem que deseja remover da ficha.",
            ),
            view=RemoverImagemFichaView(
                self.usuario_id,
                self.caminho,
                ficha.imagens,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )


class AdicionarImagemFichaModal(discord.ui.Modal):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__(title="Adicionar imagem à ficha")
        self.usuario_id = usuario_id
        self.caminho = caminho
        self.arquivo_imagem = discord.ui.FileUpload(required=True, max_values=1)
        self.titulo_imagem = discord.ui.TextInput(
            label="Título",
            placeholder="Opcional",
            required=False,
            max_length=100,
        )
        self.add_item(
            discord.ui.Label(
                text="Arquivo da imagem",
                description="Envie uma imagem PNG, JPG ou WEBP de até 25 MB.",
                component=self.arquivo_imagem,
            )
        )
        self.add_item(self.titulo_imagem)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        titulo = str(self.titulo_imagem.value).strip()
        upload = self.arquivo_imagem.values[0]
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            try:
                if not self.caminho.is_file():
                    raise ValueError("A ficha não está mais disponível na biblioteca.")
                ficha = FichaPersonagem.carregar(self.caminho)
                if len(ficha.imagens) >= 25:
                    raise ValueError("A ficha já possui o limite de 25 imagens.")
                arquivo = await salvar_upload_ficha(
                    upload, ficha.grupo, ficha.nome, titulo or "aparencia"
                )
                if any(referencia_imagem(imagem) == arquivo for imagem in ficha.imagens):
                    raise ValueError("Essa imagem já foi adicionada à ficha.")
                ficha.imagens.append({"titulo": titulo, "arquivo": arquivo})
                validar_tamanho_ficha(ficha)
                salvar_ficha(ficha, self.caminho)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return

        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
            attachments=criar_arquivos_discord(anexos_ficha(ficha)),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)


class RemoverImagemFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        imagens: list[dict[str, str]],
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.imagens = imagens
        seletor = discord.ui.Select(
            placeholder="Escolha a imagem",
            options=[
                discord.SelectOption(
                    label=(imagem.get("titulo", "").strip() or referencia_imagem(imagem))[:100],
                    value=str(indice),
                    description=(
                        referencia_imagem(imagem)[:100]
                        if imagem.get("titulo", "").strip()
                        else "Imagem sem título."
                    ),
                )
                for indice, imagem in enumerate(imagens)
            ],
        )
        seletor.callback = self.remover
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar às opções de imagem",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def remover(self, interaction: discord.Interaction) -> None:
        imagem_escolhida = self.imagens[int(self.seletor.values[0])]
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            try:
                if not self.caminho.is_file():
                    raise ValueError("A ficha não está mais disponível na biblioteca.")
                ficha = FichaPersonagem.carregar(self.caminho)
                indice = next(
                    (
                        indice
                        for indice, imagem in enumerate(ficha.imagens)
                        if imagem == imagem_escolhida
                    ),
                    None,
                )
                if indice is None:
                    raise ValueError("Essa imagem não está mais disponível na ficha.")
                ficha.imagens.pop(indice)
                validar_tamanho_ficha(ficha)
                salvar_ficha(ficha, self.caminho)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return

        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
            attachments=criar_arquivos_discord(anexos_ficha(ficha)),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🖼️ Imagens",
                "Escolha se deseja visualizar, adicionar ou remover uma imagem da ficha.",
            ),
            view=ImagemFichaView(self.usuario_id, self.caminho),
        )


class VisualizarImagemFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        imagens: list[dict[str, str]],
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.imagens = imagens
        self.seletor = discord.ui.Select(
            placeholder="Escolha uma aparência",
            options=[
                discord.SelectOption(
                    label=(imagem.get("titulo", "").strip() or f"Aparência {indice + 1}")[:100],
                    value=str(indice),
                    description="Abre esta imagem sem alterar a ficha.",
                )
                for indice, imagem in enumerate(imagens)
            ],
        )
        self.seletor.callback = self.visualizar
        self.add_item(self.seletor)
        voltar = discord.ui.Button(
            label="Voltar às opções de imagem",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def visualizar(self, interaction: discord.Interaction) -> None:
        imagem = self.imagens[int(self.seletor.values[0])]
        titulo = imagem.get("titulo", "").strip() or "Aparência"
        embed = discord.Embed(description=f"## 🖼️ {titulo}")
        anexo = aplicar_imagem(
            embed,
            referencia_imagem(imagem),
            f"aparencia-{self.caminho.stem}-{titulo}",
        )
        await interaction.response.edit_message(
            embed=embed,
            view=self,
            attachments=criar_arquivos_discord([anexo] if anexo else []),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🖼️ Imagens",
                "Escolha se deseja visualizar, adicionar ou remover uma imagem da ficha.",
            ),
            view=ImagemFichaView(self.usuario_id, self.caminho),
            attachments=[],
        )


class PresetsAutoridadeView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path, tipo: str):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.tipo = tipo
        modificar = discord.ui.Button(
            label="Modificar",
            style=discord.ButtonStyle.secondary,
            emoji="✏️",
        )
        modificar.callback = self.modificar
        self.add_item(modificar)
        voltar = discord.ui.Button(
            label="Voltar à ficha",
            style=discord.ButtonStyle.secondary,
        )
        voltar.callback = self.voltar_ficha
        self.add_item(voltar)

    async def modificar(self, interaction: discord.Interaction) -> None:
        titulo = "gratificação" if self.tipo == "gratificacoes" else "penalidade"
        await interaction.response.edit_message(
            embed=embed_painel(
                f"✏️ Modificar {titulo}",
                "Escolha a categoria cujos dois acontecimentos deseja modificar.",
            ),
            view=CategoriaPresetAutoridadeView(
                self.usuario_id,
                self.caminho,
                self.tipo,
            ),
        )

    async def voltar_ficha(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )


class CategoriaPresetAutoridadeView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path, tipo: str):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.tipo = tipo
        self.categorias = categorias_presets_autoridade(tipo)
        seletor = discord.ui.Select(
            placeholder="Categoria da gratificação"
            if tipo == "gratificacoes"
            else "Categoria da penalidade",
            options=[
                discord.SelectOption(
                    label=categoria[:100],
                    value=identificador,
                    description=f"Edita os dois acontecimentos de {faixa}."[:100],
                )
                for identificador, categoria, _, faixa in self.categorias
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar à ficha",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar_ficha
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        identificador = self.seletor.values[0]
        _, categoria, pontos, faixa = next(
            item for item in self.categorias if item[0] == identificador
        )
        ficha = FichaPersonagem.carregar(self.caminho)
        registros = (
            ficha.gratificacoes_autoridade
            if self.tipo == "gratificacoes"
            else ficha.penalidades_autoridade
        )
        motivos = [
            registro.get("motivo", "")
            for registro in registros
            if registro.get("pontos") == str(pontos)
        ][:2]
        await interaction.response.send_modal(
            EditarPresetsAutoridadeModal(
                self.usuario_id,
                self.caminho,
                self.tipo,
                categoria,
                pontos,
                faixa,
                motivos,
            )
        )

    async def voltar_ficha(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )


class EditarPresetsAutoridadeModal(discord.ui.Modal):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        tipo: str,
        categoria: str,
        pontos: int,
        faixa: str,
        motivos: list[str],
    ):
        super().__init__(title=f"Editar {categoria}"[:45])
        self.usuario_id = usuario_id
        self.caminho = caminho
        self.tipo = tipo
        self.categoria = categoria
        self.pontos = pontos
        self.faixa = faixa
        atuais = [*motivos, "", ""]
        self.primeiro = discord.ui.TextInput(
            label="Primeiro acontecimento",
            default=atuais[0] or None,
            placeholder="Descreva a primeira situação desta categoria.",
            style=discord.TextStyle.paragraph,
            max_length=450,
        )
        self.segundo = discord.ui.TextInput(
            label="Segundo acontecimento",
            default=atuais[1] or None,
            placeholder="Descreva a segunda situação desta categoria.",
            style=discord.TextStyle.paragraph,
            max_length=450,
        )
        self.add_item(self.primeiro)
        self.add_item(self.segundo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        motivos = [
            str(self.primeiro.value).strip(),
            str(self.segundo.value).strip(),
        ]
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            try:
                if not self.caminho.is_file():
                    raise ValueError("A ficha não está mais disponível na biblioteca.")
                ficha = FichaPersonagem.carregar(self.caminho)
                if ficha.grupo != "Figuras de Autoridade":
                    raise ValueError("Esta ficha não pertence a uma Figura de Autoridade.")
                atributo = (
                    "gratificacoes_autoridade"
                    if self.tipo == "gratificacoes"
                    else "penalidades_autoridade"
                )
                registros = [
                    registro
                    for registro in getattr(ficha, atributo)
                    if registro.get("pontos") != str(self.pontos)
                ]
                registros.extend(
                    {"pontos": str(self.pontos), "motivo": motivo}
                    for motivo in motivos
                )
                registros.sort(key=lambda registro: int(registro["pontos"]))
                setattr(ficha, atributo, registros)
                validar_tamanho_ficha(ficha)
                salvar_ficha(ficha, self.caminho)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return

        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)


class InformacaoFichaModal(discord.ui.Modal):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        *,
        titulo_original: str = "",
        titulo_atual: str = "",
        descricao_atual: str = "",
    ):
        super().__init__(
            title="Modificar informação" if titulo_original else "Adicionar informação"
        )
        self.usuario_id = usuario_id
        self.caminho = caminho
        self.titulo_original = titulo_original
        self.titulo_info = discord.ui.TextInput(
            label="Título",
            default=titulo_atual or None,
            max_length=100,
        )
        self.descricao_info = discord.ui.TextInput(
            label="Descrição",
            default=descricao_atual or None,
            style=discord.TextStyle.paragraph,
            max_length=900,
        )
        self.add_item(self.titulo_info)
        self.add_item(self.descricao_info)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        titulo = str(self.titulo_info.value).strip()
        descricao = str(self.descricao_info.value).strip()
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            try:
                if not self.caminho.is_file():
                    raise ValueError("A ficha não está mais disponível na biblioteca.")
                ficha = FichaPersonagem.carregar(self.caminho)
                if self.titulo_original and informacao_obrigatoria(
                    ficha, self.titulo_original
                ) and normalizar_rotulo(titulo) != normalizar_rotulo(self.titulo_original):
                    raise ValueError(
                        f"{self.titulo_original} é uma informação obrigatória e não pode ser renomeada."
                    )
                existente = None
                if self.titulo_original:
                    existente = next(
                        (
                            informacao
                            for informacao in ficha.informacoes
                            if normalizar_rotulo(informacao["titulo"])
                            == normalizar_rotulo(self.titulo_original)
                        ),
                        None,
                    )
                    if existente is None:
                        raise ValueError("Essa informação não está mais disponível na ficha.")
                    colisao = next(
                        (
                            informacao
                            for informacao in ficha.informacoes
                            if informacao is not existente
                            and normalizar_rotulo(informacao["titulo"])
                            == normalizar_rotulo(titulo)
                        ),
                        None,
                    )
                    if colisao is not None:
                        raise ValueError("Já existe outra informação com esse título.")
                else:
                    existente = next(
                        (
                            informacao
                            for informacao in ficha.informacoes
                            if normalizar_rotulo(informacao["titulo"])
                            == normalizar_rotulo(titulo)
                        ),
                        None,
                    )
                if existente is None:
                    if len(ficha.informacoes) >= 25:
                        raise ValueError("A embed Informações já possui 25 campos.")
                    ficha.informacoes.append(
                        {"titulo": titulo, "descricao": descricao}
                    )
                else:
                    existente["titulo"] = titulo
                    existente["descricao"] = descricao
                validar_tamanho_ficha(ficha)
                salvar_ficha(ficha, self.caminho)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return

        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)


class EscolhaInformacaoFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        informacoes: list[dict[str, str]],
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.informacoes = informacoes
        seletor = discord.ui.Select(
            placeholder="Escolha uma informação",
            options=[
                discord.SelectOption(label=informacao["titulo"][:100], value=str(indice))
                for indice, informacao in enumerate(informacoes)
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar à ficha",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar_ficha
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        informacao = self.informacoes[int(self.seletor.values[0])]
        await interaction.response.edit_message(
            embed=embed_painel(
                f"📋 {informacao['titulo']}",
                informacao["descricao"],
            ),
            view=GerenciarInformacaoFichaView(
                self.usuario_id,
                self.caminho,
                informacao["titulo"],
                informacao["descricao"],
            ),
        )

    async def voltar_ficha(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )


class GerenciarInformacaoFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        titulo: str,
        descricao: str,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.titulo = titulo
        self.descricao = descricao

    @discord.ui.button(label="Modificar", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def modificar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(
            InformacaoFichaModal(
                self.usuario_id,
                self.caminho,
                titulo_original=self.titulo,
                titulo_atual=self.titulo,
                descricao_atual=self.descricao,
            )
        )

    @discord.ui.button(label="Excluir", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def excluir(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🗑️ Excluir informação",
                f"Deseja excluir permanentemente **{self.titulo}** da ficha?",
            ),
            view=ConfirmarExclusaoInformacaoFichaView(
                self.usuario_id,
                self.caminho,
                self.titulo,
                self.descricao,
            ),
        )

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary)
    async def voltar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "📋 Modificar informação",
                "Escolha a informação que deseja modificar ou excluir.",
            ),
            view=EscolhaInformacaoFichaView(
                self.usuario_id,
                self.caminho,
                ficha.informacoes,
            ),
        )


class ConfirmarExclusaoInformacaoFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        titulo: str,
        descricao: str,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.titulo = titulo
        self.descricao = descricao
        self.concluido = False

    @discord.ui.button(label="Confirmar exclusão", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirmar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        if self.concluido:
            await interaction.response.send_message(
                "Esta exclusão já foi encerrada.",
                ephemeral=True,
            )
            return
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            try:
                ficha = FichaPersonagem.carregar(self.caminho)
                if informacao_obrigatoria(ficha, self.titulo):
                    raise ValueError(
                        f"{self.titulo} é uma informação obrigatória e não pode ser excluída."
                    )
                quantidade_anterior = len(ficha.informacoes)
                ficha.informacoes = [
                    informacao
                    for informacao in ficha.informacoes
                    if normalizar_rotulo(informacao["titulo"])
                    != normalizar_rotulo(self.titulo)
                ]
                if len(ficha.informacoes) == quantidade_anterior:
                    raise ValueError("Essa informação não está mais disponível na ficha.")
                salvar_ficha(ficha, self.caminho)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return
        self.concluido = True
        self.stop()
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(f"📋 {self.titulo}", self.descricao),
            view=GerenciarInformacaoFichaView(
                self.usuario_id,
                self.caminho,
                self.titulo,
                self.descricao,
            ),
        )


class CategoriaFeiticoFichaView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path, categorias: list[str]):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.categorias = categorias
        seletor = discord.ui.Select(
            placeholder="Escolha a categoria",
            options=opcoes_texto(categorias),
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar à ficha",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        categoria = self.seletor.values[0]
        referencias = referencias_categoria_menu_ficha(categoria)
        if not referencias:
            await interaction.response.send_message(
                "Essa categoria não possui feitiços válidos na biblioteca.",
                ephemeral=True,
            )
            return
        subgrupos = subgrupos_categoria_ficha(categoria, referencias)
        if not subgrupos:
            await interaction.response.send_message(
                "Essa categoria não possui divisões válidas na biblioteca.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "🪄 Feitiços",
                f"Escolha uma divisão de **{categoria}**.",
            ),
            view=SubgrupoFeiticoFichaView(
                self.usuario_id,
                self.caminho,
                categoria,
                referencias,
                subgrupos,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )


class SubgrupoFeiticoFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        categoria: str,
        referencias: list[ReferenciaFeiticoFicha],
        subgrupos: list[str],
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.categoria = categoria
        self.referencias = referencias
        self.subgrupos = subgrupos
        seletor = discord.ui.Select(
            placeholder="Escolha a divisão",
            options=opcoes_texto(subgrupos),
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar às categorias",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar_categorias
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        subgrupo = self.seletor.values[0]
        referencias = [
            referencia
            for referencia in self.referencias
            if normalizar_rotulo(subgrupo_feitico_ficha(referencia))
            == normalizar_rotulo(subgrupo)
        ]
        if not referencias:
            await interaction.response.send_message(
                "Essa divisão não possui feitiços válidos na biblioteca.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "🪄 Feitiços",
                f"Escolha em **{self.categoria} › {subgrupo}**.",
            ),
            view=EscolhaFeiticoFichaView(
                self.usuario_id,
                self.caminho,
                self.categoria,
                referencias,
                0,
            ),
        )

    async def voltar_categorias(self, interaction: discord.Interaction) -> None:
        categorias = listar_categorias_feiticos_ficha()
        await interaction.response.edit_message(
            embed=embed_painel("🪄 Feitiços", "Escolha a categoria do feitiço."),
            view=CategoriaFeiticoFichaView(
                self.usuario_id,
                self.caminho,
                categorias,
            ),
        )


class EscolhaFeiticoFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        categoria: str,
        referencias: list[ReferenciaFeiticoFicha],
        pagina: int,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.categoria = categoria
        self.referencias = referencias
        self.total_paginas = max(1, (len(referencias) + 24) // 25)
        self.pagina = max(0, min(pagina, self.total_paginas - 1))
        inicio = self.pagina * 25
        itens = referencias[inicio:inicio + 25]
        seletor = discord.ui.Select(
            placeholder=f"Feitiços — página {self.pagina + 1}/{self.total_paginas}",
            options=[
                discord.SelectOption(
                    label=referencia.nome[:100],
                    value=str(inicio + indice),
                )
                for indice, referencia in enumerate(itens)
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        if self.total_paginas > 1:
            anterior = discord.ui.Button(
                label="Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == 0,
                row=1,
            )
            proxima = discord.ui.Button(
                label="Próxima",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == self.total_paginas - 1,
                row=1,
            )
            anterior.callback = self.anterior
            proxima.callback = self.proxima
            self.add_item(anterior)
            self.add_item(proxima)
        voltar = discord.ui.Button(
            label="Voltar às categorias",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        voltar.callback = self.voltar_categorias
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        referencia = self.referencias[int(self.seletor.values[0])]
        ficha = FichaPersonagem.carregar(self.caminho)
        existente = next(
            (
                feitico
                for feitico in ficha.feiticos_favoritos
                if normalizar_rotulo(feitico["nome"])
                == normalizar_rotulo(referencia.nome)
                and normalizar_rotulo(feitico["categoria"])
                == normalizar_rotulo(referencia.categoria)
            ),
            None,
        )
        await interaction.response.send_modal(
            DescricaoFeiticoFichaModal(
                self.usuario_id,
                self.caminho,
                referencia,
                existente["descricao"] if existente else "",
            )
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=EscolhaFeiticoFichaView(
                self.usuario_id,
                self.caminho,
                self.categoria,
                self.referencias,
                self.pagina - 1,
            )
        )

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=EscolhaFeiticoFichaView(
                self.usuario_id,
                self.caminho,
                self.categoria,
                self.referencias,
                self.pagina + 1,
            )
        )

    async def voltar_categorias(self, interaction: discord.Interaction) -> None:
        categorias = listar_categorias_feiticos_ficha()
        await interaction.response.edit_message(
            embed=embed_painel("🪄 Feitiços", "Escolha a categoria do feitiço."),
            view=CategoriaFeiticoFichaView(
                self.usuario_id,
                self.caminho,
                categorias,
            ),
        )


class DescricaoFeiticoFichaModal(discord.ui.Modal):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        referencia: ReferenciaFeiticoFicha,
        descricao_atual: str,
    ):
        super().__init__(
            title="Modificar feitiço" if descricao_atual else "Adicionar feitiço à ficha"
        )
        self.usuario_id = usuario_id
        self.caminho = caminho
        self.referencia = referencia
        self.descricao = discord.ui.TextInput(
            label="Descrição breve",
            placeholder="Edite ou resuma a descrição sugerida.",
            default=descricao_atual or exemplo_descricao_feitico(referencia),
            style=discord.TextStyle.paragraph,
            max_length=1024,
        )
        self.add_item(self.descricao)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        descricao = str(self.descricao.value).strip()
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            try:
                if not self.caminho.is_file():
                    raise ValueError("A ficha não está mais disponível na biblioteca.")
                ficha = FichaPersonagem.carregar(self.caminho)
                existente = next(
                    (
                        feitico
                        for feitico in ficha.feiticos_favoritos
                        if normalizar_rotulo(feitico["nome"])
                        == normalizar_rotulo(self.referencia.nome)
                        and normalizar_rotulo(feitico["categoria"])
                        == normalizar_rotulo(self.referencia.categoria)
                    ),
                    None,
                )
                if existente is None:
                    if len(ficha.feiticos_favoritos) >= 25:
                        raise ValueError("A embed Feitiços já possui 25 campos.")
                    if (
                        ficha.grupo == "Figuras de Autoridade"
                        and len(ficha.feiticos_favoritos) + len(ficha.pocoes_favoritas) >= 25
                    ):
                        raise ValueError("O Grimório Pessoal já possui 25 campos.")
                    ficha.feiticos_favoritos.append(
                        {
                            "nome": self.referencia.nome,
                            "categoria": self.referencia.categoria,
                            "descricao": descricao,
                        }
                    )
                else:
                    existente["descricao"] = descricao
                validar_tamanho_ficha(ficha)
                salvar_ficha(ficha, self.caminho)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return

        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)


class EscolhaFeiticoSalvoFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        feiticos: list[dict[str, str]],
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.feiticos = feiticos
        seletor = discord.ui.Select(
            placeholder="Escolha um feitiço",
            options=[
                discord.SelectOption(
                    label=f"{feitico['nome']} ({feitico['categoria']})"[:100],
                    value=str(indice),
                )
                for indice, feitico in enumerate(feiticos)
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar à ficha",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar_ficha
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        feitico = self.feiticos[int(self.seletor.values[0])]
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🪄 {feitico['nome']} ({feitico['categoria']})",
                feitico["descricao"],
            ),
            view=GerenciarFeiticoFichaView(
                self.usuario_id,
                self.caminho,
                feitico["nome"],
                feitico["categoria"],
                feitico["descricao"],
            ),
        )

    async def voltar_ficha(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )


class GerenciarFeiticoFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        nome: str,
        categoria: str,
        descricao: str,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.nome = nome
        self.categoria = categoria
        self.descricao = descricao

    @discord.ui.button(label="Modificar", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def modificar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(
            DescricaoFeiticoFichaModal(
                self.usuario_id,
                self.caminho,
                ReferenciaFeiticoFicha(self.nome, self.categoria, Path()),
                self.descricao,
            )
        )

    @discord.ui.button(label="Excluir", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def excluir(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🗑️ Excluir feitiço",
                f"Deseja excluir **{self.nome} ({self.categoria})** da ficha?",
            ),
            view=ConfirmarExclusaoFeiticoFichaView(
                self.usuario_id,
                self.caminho,
                self.nome,
                self.categoria,
                self.descricao,
            ),
        )

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary)
    async def voltar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "🪄 Modificar feitiço",
                "Escolha o feitiço que deseja modificar ou excluir.",
            ),
            view=EscolhaFeiticoSalvoFichaView(
                self.usuario_id,
                self.caminho,
                ficha.feiticos_favoritos,
            ),
        )


class ConfirmarExclusaoFeiticoFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        nome: str,
        categoria: str,
        descricao: str,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.nome = nome
        self.categoria = categoria
        self.descricao = descricao
        self.concluido = False

    @discord.ui.button(label="Confirmar exclusão", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirmar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        if self.concluido:
            await interaction.response.send_message(
                "Esta exclusão já foi encerrada.",
                ephemeral=True,
            )
            return
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            try:
                ficha = FichaPersonagem.carregar(self.caminho)
                quantidade_anterior = len(ficha.feiticos_favoritos)
                ficha.feiticos_favoritos = [
                    feitico
                    for feitico in ficha.feiticos_favoritos
                    if not (
                        normalizar_rotulo(feitico["nome"])
                        == normalizar_rotulo(self.nome)
                        and normalizar_rotulo(feitico["categoria"])
                        == normalizar_rotulo(self.categoria)
                    )
                ]
                if len(ficha.feiticos_favoritos) == quantidade_anterior:
                    raise ValueError("Esse feitiço não está mais disponível na ficha.")
                salvar_ficha(ficha, self.caminho)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return
        self.concluido = True
        self.stop()
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🪄 {self.nome} ({self.categoria})",
                self.descricao,
            ),
            view=GerenciarFeiticoFichaView(
                self.usuario_id,
                self.caminho,
                self.nome,
                self.categoria,
                self.descricao,
            ),
        )


class CategoriaPocaoFichaView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path, categorias: list[str]):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.categorias = categorias
        seletor = discord.ui.Select(
            placeholder="Escolha o ano",
            options=opcoes_texto(categorias),
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar à ficha",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        categoria = self.seletor.values[0]
        referencias = listar_pocoes_ficha(categoria)
        if not referencias:
            await interaction.response.send_message(
                "Esse ano não possui poções válidas na biblioteca.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "🧪 Poções",
                f"Escolha uma poção de **{categoria}**.",
            ),
            view=EscolhaPocaoFichaView(
                self.usuario_id,
                self.caminho,
                categoria,
                referencias,
                0,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )


class EscolhaPocaoFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        categoria: str,
        referencias: list[ReferenciaPocaoFicha],
        pagina: int,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.categoria = categoria
        self.referencias = referencias
        self.total_paginas = max(1, (len(referencias) + 24) // 25)
        self.pagina = max(0, min(pagina, self.total_paginas - 1))
        inicio = self.pagina * 25
        itens = referencias[inicio:inicio + 25]
        seletor = discord.ui.Select(
            placeholder=f"Poções — página {self.pagina + 1}/{self.total_paginas}",
            options=[
                discord.SelectOption(
                    label=referencia.nome[:100],
                    value=str(inicio + indice),
                )
                for indice, referencia in enumerate(itens)
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        if self.total_paginas > 1:
            anterior = discord.ui.Button(
                label="Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == 0,
                row=1,
            )
            proxima = discord.ui.Button(
                label="Próxima",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == self.total_paginas - 1,
                row=1,
            )
            anterior.callback = self.anterior
            proxima.callback = self.proxima
            self.add_item(anterior)
            self.add_item(proxima)
        voltar = discord.ui.Button(
            label="Voltar aos anos",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        voltar.callback = self.voltar_categorias
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        referencia = self.referencias[int(self.seletor.values[0])]
        ficha = FichaPersonagem.carregar(self.caminho)
        existente = next(
            (
                pocao
                for pocao in ficha.pocoes_favoritas
                if normalizar_rotulo(pocao["nome"])
                == normalizar_rotulo(referencia.nome)
                and normalizar_rotulo(pocao["categoria"])
                == normalizar_rotulo(referencia.categoria)
            ),
            None,
        )
        await interaction.response.send_modal(
            DescricaoPocaoFichaModal(
                self.usuario_id,
                self.caminho,
                referencia,
                existente["descricao"] if existente else "",
            )
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=EscolhaPocaoFichaView(
                self.usuario_id,
                self.caminho,
                self.categoria,
                self.referencias,
                self.pagina - 1,
            )
        )

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=EscolhaPocaoFichaView(
                self.usuario_id,
                self.caminho,
                self.categoria,
                self.referencias,
                self.pagina + 1,
            )
        )

    async def voltar_categorias(self, interaction: discord.Interaction) -> None:
        categorias = listar_categorias_pocoes_ficha()
        await interaction.response.edit_message(
            embed=embed_painel("🧪 Poções", "Escolha o ano da poção."),
            view=CategoriaPocaoFichaView(
                self.usuario_id,
                self.caminho,
                categorias,
            ),
        )


class DescricaoPocaoFichaModal(discord.ui.Modal):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        referencia: ReferenciaPocaoFicha,
        descricao_atual: str,
    ):
        super().__init__(
            title="Modificar poção" if descricao_atual else "Adicionar poção à ficha"
        )
        self.usuario_id = usuario_id
        self.caminho = caminho
        self.referencia = referencia
        self.descricao = discord.ui.TextInput(
            label="Descrição breve",
            placeholder="Edite ou resuma o efeito sugerido.",
            default=descricao_atual or exemplo_descricao_pocao(referencia),
            style=discord.TextStyle.paragraph,
            max_length=1024,
        )
        self.add_item(self.descricao)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        descricao = str(self.descricao.value).strip()
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            try:
                if not self.caminho.is_file():
                    raise ValueError("A ficha não está mais disponível na biblioteca.")
                ficha = FichaPersonagem.carregar(self.caminho)
                existente = next(
                    (
                        pocao
                        for pocao in ficha.pocoes_favoritas
                        if normalizar_rotulo(pocao["nome"])
                        == normalizar_rotulo(self.referencia.nome)
                        and normalizar_rotulo(pocao["categoria"])
                        == normalizar_rotulo(self.referencia.categoria)
                    ),
                    None,
                )
                if existente is None:
                    if len(ficha.pocoes_favoritas) >= 25:
                        raise ValueError("A embed Poções já possui 25 campos.")
                    if (
                        ficha.grupo == "Figuras de Autoridade"
                        and len(ficha.feiticos_favoritos) + len(ficha.pocoes_favoritas) >= 25
                    ):
                        raise ValueError("O Grimório Pessoal já possui 25 campos.")
                    ficha.pocoes_favoritas.append(
                        {
                            "nome": self.referencia.nome,
                            "categoria": self.referencia.categoria,
                            "descricao": descricao,
                        }
                    )
                else:
                    existente["descricao"] = descricao
                validar_tamanho_ficha(ficha)
                salvar_ficha(ficha, self.caminho)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return

        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)


class EscolhaPocaoSalvaFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        pocoes: list[dict[str, str]],
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.pocoes = pocoes
        seletor = discord.ui.Select(
            placeholder="Escolha uma poção",
            options=[
                discord.SelectOption(
                    label=f"{pocao['nome']} ({pocao['categoria']})"[:100],
                    value=str(indice),
                )
                for indice, pocao in enumerate(pocoes)
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar à ficha",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar_ficha
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        pocao = self.pocoes[int(self.seletor.values[0])]
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🧪 {pocao['nome']} ({pocao['categoria']})",
                pocao["descricao"],
            ),
            view=GerenciarPocaoFichaView(
                self.usuario_id,
                self.caminho,
                pocao["nome"],
                pocao["categoria"],
                pocao["descricao"],
            ),
        )

    async def voltar_ficha(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )


class GerenciarPocaoFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        nome: str,
        categoria: str,
        descricao: str,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.nome = nome
        self.categoria = categoria
        self.descricao = descricao

    @discord.ui.button(label="Modificar", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def modificar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(
            DescricaoPocaoFichaModal(
                self.usuario_id,
                self.caminho,
                ReferenciaPocaoFicha(self.nome, self.categoria, Path()),
                self.descricao,
            )
        )

    @discord.ui.button(label="Excluir", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def excluir(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🗑️ Excluir poção",
                f"Deseja excluir **{self.nome} ({self.categoria})** da ficha?",
            ),
            view=ConfirmarExclusaoPocaoFichaView(
                self.usuario_id,
                self.caminho,
                self.nome,
                self.categoria,
                self.descricao,
            ),
        )

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.secondary)
    async def voltar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "🧪 Modificar poção",
                "Escolha a poção que deseja modificar ou excluir.",
            ),
            view=EscolhaPocaoSalvaFichaView(
                self.usuario_id,
                self.caminho,
                ficha.pocoes_favoritas,
            ),
        )


class ConfirmarExclusaoPocaoFichaView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        nome: str,
        categoria: str,
        descricao: str,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.nome = nome
        self.categoria = categoria
        self.descricao = descricao
        self.concluido = False

    @discord.ui.button(label="Confirmar exclusão", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirmar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        if self.concluido:
            await interaction.response.send_message(
                "Esta exclusão já foi encerrada.",
                ephemeral=True,
            )
            return
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            try:
                ficha = FichaPersonagem.carregar(self.caminho)
                quantidade_anterior = len(ficha.pocoes_favoritas)
                ficha.pocoes_favoritas = [
                    pocao
                    for pocao in ficha.pocoes_favoritas
                    if not (
                        normalizar_rotulo(pocao["nome"])
                        == normalizar_rotulo(self.nome)
                        and normalizar_rotulo(pocao["categoria"])
                        == normalizar_rotulo(self.categoria)
                    )
                ]
                if len(ficha.pocoes_favoritas) == quantidade_anterior:
                    raise ValueError("Essa poção não está mais disponível na ficha.")
                salvar_ficha(ficha, self.caminho)
            except (OSError, ValueError) as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return
        self.concluido = True
        self.stop()
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(
        self,
        interaction: discord.Interaction,
        botao: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🧪 {self.nome} ({self.categoria})",
                self.descricao,
            ),
            view=GerenciarPocaoFichaView(
                self.usuario_id,
                self.caminho,
                self.nome,
                self.categoria,
                self.descricao,
            ),
        )


def campo_essencial_faltando(valor: str) -> bool:
    return normalizar_rotulo(str(valor or "")) in {"", "--"}


class MercadoXPView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__(usuario_id)
        self.caminho = caminho
        ficha = FichaPersonagem.carregar(caminho)
        if ficha.grupo == "NPCs" and ficha.tipo_npc not in {"", "Bruxo(a)"}:
            for item in list(self.children):
                if isinstance(item, discord.ui.Button) and item.label in {
                    "Aptidão Mágica +", "Habilidades"
                }:
                    self.remove_item(item)

        # Figuras de Autoridade antigas podem ter sido importadas sem os dados
        # essenciais da criação. Enquanto algo estiver pendente, a segunda linha
        # do Mercado mostra apenas os atalhos vermelhos necessários; cada botão
        # desaparece assim que o respectivo dado é configurado.
        if ficha.grupo == "Figuras de Autoridade":
            if campo_essencial_faltando(ficha.casa):
                casa = discord.ui.Button(
                    label="Casa",
                    style=discord.ButtonStyle.danger,
                    emoji="🏰",
                    row=1,
                )
                casa.callback = self.configurar_casa
                self.add_item(casa)
            if campo_essencial_faltando(ficha.heranca):
                heranca = discord.ui.Button(
                    label="Herança Sanguínea",
                    style=discord.ButtonStyle.danger,
                    emoji="🧬",
                    row=1,
                )
                heranca.callback = self.configurar_heranca
                self.add_item(heranca)
            if campo_essencial_faltando(ficha.nucleo):
                nucleo = discord.ui.Button(
                    label="Núcleo de Varinha",
                    style=discord.ButtonStyle.danger,
                    emoji="🪄",
                    row=1,
                )
                nucleo.callback = self.configurar_nucleo
                self.add_item(nucleo)
            if ficha.pontos_atributo_disponiveis:
                atributos = discord.ui.Button(
                    label="Atributos",
                    style=discord.ButtonStyle.danger,
                    emoji="📌",
                    row=1,
                )
                atributos.callback = self.atributos
                self.add_item(atributos)
        elif ficha.pontos_atributo_disponiveis:
            atributos = discord.ui.Button(
                label="Atributos",
                style=discord.ButtonStyle.secondary,
                emoji="📌",
                row=1,
            )
            atributos.callback = self.atributos
            self.add_item(atributos)

        voltar = discord.ui.Button(label="Voltar à ficha", style=discord.ButtonStyle.secondary, row=2)
        voltar.callback = self.voltar_ficha
        self.add_item(voltar)

    async def voltar_ficha(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
            attachments=criar_arquivos_discord(anexos_ficha(ficha)),
        )

    @discord.ui.button(label="UP", style=discord.ButtonStyle.primary, emoji="⬆️")
    async def subir_nivel(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        custo = custo_subir_nivel(ficha)
        await interaction.response.edit_message(
            embed=embed_painel("⬆️ Subir de nível", f"Subir para o nível **{ficha.nivel + 1}** custa **{custo} XP**."),
            view=ConfirmarCompraView(self.usuario_id, self.caminho, "nivel", "", 0),
        )

    @discord.ui.button(label="Aptidão Mágica +", style=discord.ButtonStyle.secondary, emoji="✨")
    async def aptidao(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=embed_painel("✨ Aprimorar aptidão", "Escolha a aptidão que receberá o bônus."),
            view=EscolhaAptidaoMercadoView(self.usuario_id, self.caminho),
        )

    @discord.ui.button(label="Perícia", style=discord.ButtonStyle.secondary, emoji="📌")
    async def pericia(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=embed_painel("📌 Aprimorar perícia", "Escolha a perícia desejada."),
            view=EscolhaPericiaMercadoView(self.usuario_id, self.caminho, 0),
        )

    @discord.ui.button(label="Habilidades", style=discord.ButtonStyle.secondary, emoji="💡")
    async def habilidades(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=embed_painel("💡 Comprar habilidade", "Escolha a categoria da habilidade."),
            view=CategoriaHabilidadeMercadoView(self.usuario_id, self.caminho),
        )

    async def configurar_casa(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🏰 Casa de Hogwarts",
                "Escolha a Casa desta Figura de Autoridade. Esta configuração é feita apenas uma vez por este atalho.",
            ),
            view=ConfigurarEssencialAutoridadeView(
                self.usuario_id,
                self.caminho,
                "casa",
            ),
        )

    async def configurar_heranca(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🧬 Herança Sanguínea",
                "Escolha a Herança Sanguínea desta Figura de Autoridade. Os bônus iniciais cadastrados serão aplicados à ficha.",
            ),
            view=ConfigurarEssencialAutoridadeView(
                self.usuario_id,
                self.caminho,
                "heranca",
            ),
        )

    async def configurar_nucleo(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🪄 Núcleo de Varinha",
                "Escolha o Núcleo de Varinha desta Figura de Autoridade. Os bônus cadastrados serão aplicados à ficha.",
            ),
            view=ConfigurarEssencialAutoridadeView(
                self.usuario_id,
                self.caminho,
                "nucleo",
            ),
        )

    async def atributos(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_atributos_mercado(ficha, ficha.pontos_atributo_disponiveis),
            view=AtributosMercadoView(self.usuario_id, self.caminho, ficha),
        )


class ConfigurarEssencialAutoridadeView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path, campo: str):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.campo = campo
        if campo == "casa":
            opcoes = opcoes_texto(listar_casas())
            placeholder = "Escolha a Casa"
        elif campo == "heranca":
            opcoes = opcoes_texto(listar_habilidades("heranca_sanguinea"))
            placeholder = "Escolha a Herança Sanguínea"
        elif campo == "nucleo":
            opcoes = opcoes_nucleos()
            placeholder = "Escolha o Núcleo de Varinha"
        else:
            raise ValueError("Campo essencial de autoridade desconhecido.")

        self.seletor = discord.ui.Select(placeholder=placeholder, options=opcoes)
        self.seletor.callback = self.selecionar
        self.add_item(self.seletor)
        voltar = discord.ui.Button(
            label="Voltar ao Mercado",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "🛒 Mercado de XP",
                f"**{ficha.nome}** possui **{ficha.xp} XP** disponível. Escolha o que deseja adquirir.",
            ),
            view=MercadoXPView(self.usuario_id, self.caminho),
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        valor = self.seletor.values[0]
        ficha = FichaPersonagem.carregar(self.caminho)
        if ficha.grupo != "Figuras de Autoridade":
            await interaction.response.send_message(
                "Esta configuração especial existe apenas para Figuras de Autoridade.",
                ephemeral=True,
            )
            return

        atual = getattr(ficha, self.campo)
        if not campo_essencial_faltando(atual):
            await interaction.response.send_message(
                "Este dado já foi configurado. Abra novamente o Mercado de XP para atualizar os botões.",
                ephemeral=True,
            )
            return

        if self.campo == "casa":
            opcoes = pericias_da_casa(valor)
            if not opcoes:
                await interaction.response.send_message(
                    "Esta Casa não possui Perícias da Casa cadastradas.",
                    ephemeral=True,
                )
                return
            await interaction.response.edit_message(
                embed=embed_painel(
                    "📌 Perícia da Casa",
                    f"Escolha uma das Perícias da **{valor}** para treinar gratuitamente.",
                ),
                view=EscolherPericiaCasaAutoridadeView(
                    self.usuario_id,
                    self.caminho,
                    valor,
                    opcoes,
                ),
            )
            return

        if self.campo == "nucleo":
            _, escolhas, _ = dados_nucleo(valor)
            if escolhas:
                await interaction.response.edit_message(
                    embed=embed_painel(
                        "🪄 Aptidões do Núcleo",
                        f"**{valor}** exige a escolha de **{escolhas}** aptidões mágicas diferentes antes de concluir a configuração.",
                    ),
                    view=EscolherAptidoesNucleoAutoridadeView(
                        self.usuario_id,
                        self.caminho,
                        valor,
                        escolhas,
                    ),
                )
                return

        await salvar_essencial_autoridade(
            interaction,
            self.usuario_id,
            self.caminho,
            self.campo,
            valor,
        )


class EscolherPericiaCasaAutoridadeView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        casa: str,
        pericias: list[str],
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.casa = casa
        self.seletor = discord.ui.Select(
            placeholder="Escolha uma Perícia da Casa",
            options=opcoes_texto(pericias),
        )
        self.seletor.callback = self.selecionar
        self.add_item(self.seletor)

        voltar = discord.ui.Button(
            label="Voltar às Casas",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🏰 Casa de Hogwarts",
                "Escolha a Casa desta Figura de Autoridade.",
            ),
            view=ConfigurarEssencialAutoridadeView(
                self.usuario_id,
                self.caminho,
                "casa",
            ),
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        pericia = self.seletor.values[0]
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            ficha = FichaPersonagem.carregar(self.caminho)
            if ficha.grupo != "Figuras de Autoridade":
                await interaction.response.send_message(
                    "Esta configuração especial existe apenas para Figuras de Autoridade.",
                    ephemeral=True,
                )
                return
            if not campo_essencial_faltando(ficha.casa):
                await interaction.response.send_message(
                    "A Casa desta ficha já foi configurada.",
                    ephemeral=True,
                )
                return
            if pericia not in pericias_da_casa(self.casa):
                await interaction.response.send_message(
                    "Esta perícia não pertence à Casa selecionada.",
                    ephemeral=True,
                )
                return

            ficha.casa = self.casa
            # 'Treinada' usa grau 2 no sistema, igual à criação normal de fichas.
            ficha.pericias[pericia] = max(ficha.pericias.get(pericia, 0), 2)
            salvar_ficha(ficha, self.caminho)

        await interaction.response.edit_message(
            embed=embed_painel(
                "🛒 Mercado de XP",
                f"**{ficha.nome}** possui **{ficha.xp} XP** disponível. Escolha o que deseja adquirir.",
            ),
            view=MercadoXPView(self.usuario_id, self.caminho),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)


class EscolherAptidoesNucleoAutoridadeView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        nucleo: str,
        quantidade: int,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.nucleo = nucleo
        self.quantidade = quantidade
        self.seletor = discord.ui.Select(
            placeholder=f"Escolha {quantidade} aptidões",
            options=opcoes_texto(APTIDOES),
            min_values=quantidade,
            max_values=quantidade,
        )
        self.seletor.callback = self.selecionar
        self.add_item(self.seletor)
        voltar = discord.ui.Button(
            label="Voltar aos Núcleos",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🪄 Núcleo de Varinha",
                "Escolha o Núcleo de Varinha desta Figura de Autoridade.",
            ),
            view=ConfigurarEssencialAutoridadeView(
                self.usuario_id,
                self.caminho,
                "nucleo",
            ),
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        await salvar_essencial_autoridade(
            interaction,
            self.usuario_id,
            self.caminho,
            "nucleo",
            self.nucleo,
            aptidoes_nucleo=list(self.seletor.values),
        )


async def salvar_essencial_autoridade(
    interaction: discord.Interaction,
    usuario_id: int,
    caminho: Path,
    campo: str,
    valor: str,
    *,
    aptidoes_nucleo: list[str] | None = None,
) -> None:
    lock = LOCKS_FICHA.setdefault(caminho.resolve(), asyncio.Lock())
    async with lock:
        ficha = FichaPersonagem.carregar(caminho)
        if ficha.grupo != "Figuras de Autoridade":
            await interaction.response.send_message(
                "Esta configuração especial existe apenas para Figuras de Autoridade.",
                ephemeral=True,
            )
            return
        if not campo_essencial_faltando(getattr(ficha, campo)):
            await interaction.response.send_message(
                "Este dado já foi configurado. Abra novamente o Mercado de XP para atualizar os botões.",
                ephemeral=True,
            )
            return

        if campo == "casa":
            ficha.casa = valor
        elif campo == "heranca":
            ficha.heranca = valor
            for nome, bonus in bonus_aptidoes_heranca(valor).items():
                if nome in ficha.aptidoes:
                    ficha.aptidoes[nome] += bonus
        elif campo == "nucleo":
            ficha.nucleo = valor
            bonus_fixos, escolhas, bonus_escolha = dados_nucleo(valor)
            for nome, bonus in bonus_fixos.items():
                if nome in ficha.aptidoes:
                    ficha.aptidoes[nome] += bonus
            escolhidas = aptidoes_nucleo or []
            if escolhas and len(escolhidas) != escolhas:
                await interaction.response.send_message(
                    f"Este núcleo exige exatamente {escolhas} escolhas de aptidão.",
                    ephemeral=True,
                )
                return
            for nome in escolhidas:
                if nome in ficha.aptidoes:
                    ficha.aptidoes[nome] += bonus_escolha
        else:
            await interaction.response.send_message(
                "Campo essencial desconhecido.",
                ephemeral=True,
            )
            return
        salvar_ficha(ficha, caminho)

    await interaction.response.edit_message(
        embed=embed_painel(
            "🛒 Mercado de XP",
            f"**{ficha.nome}** possui **{ficha.xp} XP** disponível. Escolha o que deseja adquirir.",
        ),
        view=MercadoXPView(usuario_id, caminho),
    )
    await sincronizar_publicacao_personagem(interaction, ficha, caminho)


def embed_atributos_mercado(
    ficha: FichaPersonagem,
    restantes: int,
    *,
    nivel_destino: int | None = None,
    custo_nivel: int = 0,
) -> discord.Embed:
    if nivel_destino is None:
        if (
            ficha.grupo == "Figuras de Autoridade"
            and ficha.pontos_atributo_disponiveis > 0
        ):
            introducao = (
                "Complete a distribuição inicial desta autoridade. É possível reduzir "
                f"atributos até {ATRIBUTO_MINIMO_PERSONAGEM} para transferir os pontos; "
                "depois da confirmação, a distribuição não poderá ser revertida."
            )
        else:
            introducao = "Distribua os pontos recebidos ao subir de nível."
        resumo_subida = ""
    else:
        ganho_pv = 5 + modificador(ficha.atributos["Constituição"])
        ganho_ph = 2 + modificador(ficha.atributos["Sabedoria"])
        introducao = (
            f"Distribua os **2 pontos** antes de concluir a subida para o nível **{nivel_destino}**. "
            "Os modificadores resultantes serão usados nos ganhos deste nível."
        )
        resumo_subida = (
            f"\n\n**Custo da subida:** {custo_nivel} XP"
            f"\n**Ganho deste nível:** +{ganho_pv} PV e +{ganho_ph} PH"
        )
    return embed_painel(
        "📌 Pontos de atributo",
        introducao
        + "\n\n"
        + "\n".join(
            f"> **{nome}:** {ficha.atributos[nome]} {formatar_bonus(modificador(ficha.atributos[nome]))}"
            for nome in ATRIBUTOS
        )
        + f"\n\n**Pontos restantes:** {restantes}"
        + resumo_subida,
    )


class BotaoAtributoMercado(discord.ui.Button):
    def __init__(self, atributo: str, delta: int, row: int):
        super().__init__(label=atributo, style=discord.ButtonStyle.secondary, row=row)
        self.atributo = atributo
        # Compatibilidade com extensões que identificam botões de atributo;
        # não altera a apresentação, que agora usa um botão único por atributo.
        self.delta = -1

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, AtributosMercadoView):
            await interaction.response.defer()
            return
        await interaction.response.send_modal(
            QuantidadeAtributoModal(view, self.atributo)
        )


class AtributosMercadoView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        ficha: FichaPersonagem,
        *,
        nivel_destino: int | None = None,
        custo_nivel: int = 0,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.ficha = ficha
        self.originais = dict(ficha.atributos)
        self.nivel_destino = nivel_destino
        self.custo_nivel = custo_nivel
        self.nivel_original = ficha.nivel
        self.xp_original = ficha.xp
        self.pv_original = ficha.pv
        self.ph_original = ficha.ph
        self.pontos_originais = ficha.pontos_atributo_disponiveis
        self.configuracao_inicial_autoridade = (
            ficha.grupo == "Figuras de Autoridade"
            and ficha.pontos_atributo_disponiveis > 0
        )
        self.pontos_iniciais = 2 if nivel_destino is not None else self.pontos_originais
        self.restantes = self.pontos_iniciais
        self.bloqueio_atributos = asyncio.Lock()
        for indice, atributo in enumerate(ATRIBUTOS):
            self.add_item(BotaoAtributoMercado(atributo, 0, indice // 2))
        confirmar = discord.ui.Button(label="Confirmar atributos", style=discord.ButtonStyle.success, row=3)
        confirmar.callback = self.confirmar
        self.confirmar_botao = confirmar
        self.add_item(confirmar)
        self.atualizar_botoes()

    def atualizar_botoes(self) -> None:
        for item in self.children:
            if isinstance(item, BotaoAtributoMercado):
                minimo = (
                    ATRIBUTO_MINIMO_PERSONAGEM
                    if self.configuracao_inicial_autoridade
                    else self.originais[item.atributo]
                )
                item.disabled = self.restantes == 0 and self.ficha.atributos[item.atributo] <= minimo
        self.confirmar_botao.disabled = self.restantes != 0

    async def confirmar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if self.restantes != 0:
            await interaction.followup.send("Distribua todos os pontos antes de confirmar.", ephemeral=True)
            return
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            atual = FichaPersonagem.carregar(self.caminho)
            ficha_mudou = (
                atual.nivel != self.nivel_original
                or atual.xp != self.xp_original
                or atual.pv != self.pv_original
                or atual.ph != self.ph_original
                or atual.pontos_atributo_disponiveis != self.pontos_originais
                or atual.atributos != self.originais
            )
            if ficha_mudou:
                await interaction.followup.send(
                    "A ficha mudou durante a distribuição. Abra novamente o Mercado de XP.",
                    ephemeral=True,
                )
                return
            atual.atributos = dict(self.ficha.atributos)
            if self.nivel_destino is None:
                if self.configuracao_inicial_autoridade:
                    atual.pv, atual.ph = pv_ph_criacao_por_nivel(
                        atual.nivel,
                        atual.atributos["Constituição"],
                        atual.atributos["Sabedoria"],
                    )
                # Fora da configuração inicial, pontos pendentes não alteram ganhos antigos.
                atual.pontos_atributo_disponiveis = 0
            else:
                custo_atual = custo_subir_nivel(atual)
                if self.nivel_destino != atual.nivel + 1 or self.custo_nivel != custo_atual:
                    await interaction.followup.send(
                        "O custo ou o nível mudou durante a distribuição. Abra novamente o Mercado de XP.",
                        ephemeral=True,
                    )
                    return
                if atual.xp < custo_atual:
                    await interaction.followup.send(
                        f"XP insuficiente: a subida custa **{custo_atual} XP**, mas a ficha possui **{atual.xp} XP**.",
                        ephemeral=True,
                    )
                    return
                atual.xp -= custo_atual
                atual.nivel = self.nivel_destino
                # Os modificadores novos valem para este nível, nunca retroativamente.
                if atual.tipo_npc != "Espírito":
                    atual.pv += 5 + modificador(atual.atributos["Constituição"])
                atual.ph += 2 + modificador(atual.atributos["Sabedoria"])
                atual.pontos_atributo_disponiveis = 0
            salvar_ficha(atual, self.caminho)
        self.stop()
        await interaction.edit_original_response(
            embeds=montar_embeds_ficha(atual),
            view=FichaAtualView(self.usuario_id, self.caminho),
            attachments=criar_arquivos_discord(anexos_ficha(atual)),
        )
        await sincronizar_publicacao_personagem(interaction, atual, self.caminho)


class EscolhaAptidaoMercadoView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__(usuario_id)
        self.caminho = caminho
        seletor = discord.ui.Select(placeholder="Escolha a aptidão", options=opcoes_texto(APTIDOES))
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar ao Mercado",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar_mercado
        self.add_item(voltar)

    async def voltar_mercado(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "🛒 Mercado de XP",
                f"**{ficha.nome}** possui **{ficha.xp} XP** disponível. Escolha o que deseja adquirir.",
            ),
            view=MercadoXPView(self.usuario_id, self.caminho),
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        nome = self.seletor.values[0]
        await interaction.response.send_modal(
            QuantidadeAptidaoModal(self.usuario_id, self.caminho, nome)
        )


class EscolhaPericiaMercadoView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        pagina: int,
        nome: str = "",
        alvo: int = 0,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.nome = nome
        self.alvo = alvo
        self.paginas = paginas_pericias()
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        rotulo_pagina, pericias_pagina = self.paginas[self.pagina]

        ficha = FichaPersonagem.carregar(caminho)
        opcoes_pericia = [
            discord.SelectOption(
                label=pericia,
                value=pericia,
                description=f"Graduação atual: {NOMES_RANK[ficha.pericias.get(pericia, 0)]}",
                default=pericia == nome,
            )
            for pericia in pericias_pagina
        ]
        pericia = discord.ui.Select(
            placeholder=f"Perícias — {rotulo_pagina}",
            options=opcoes_pericia,
            row=0,
        )
        pericia.callback = self.selecionar_pericia
        self.seletor_pericia = pericia
        self.add_item(pericia)

        atual = ficha.pericias.get(nome, 0) if nome else 0
        alvos = [rank for rank in RANKS_PERICIA if rank > atual]
        opcoes_rank = [
            discord.SelectOption(
                label=f"{NOMES_RANK[rank]} ({formatar_bonus(rank)})",
                value=str(rank),
                description=f"Custo da melhoria: {custo_pericia(atual, rank)} XP",
                default=rank == alvo,
            )
            for rank in alvos
        ] or [discord.SelectOption(label="Mestre — graduação máxima", value="maximo")]
        graduacao = discord.ui.Select(
            placeholder="Escolha primeiro uma perícia" if not nome else "Escolha a graduação",
            options=opcoes_rank,
            disabled=not nome or not alvos,
            row=1,
        )
        graduacao.callback = self.selecionar_graduacao
        self.seletor_graduacao = graduacao
        self.add_item(graduacao)

        continuar = discord.ui.Button(
            label="Continuar compra",
            style=discord.ButtonStyle.primary,
            disabled=not nome or not alvo,
            row=2,
        )
        continuar.callback = self.continuar
        self.add_item(continuar)

        anterior = discord.ui.Button(
            label="Anterior",
            style=discord.ButtonStyle.secondary,
            disabled=self.pagina == 0,
            row=2,
        )
        anterior.callback = self.anterior
        self.add_item(anterior)
        proxima = discord.ui.Button(
            label="Próxima",
            style=discord.ButtonStyle.secondary,
            disabled=self.pagina == len(self.paginas) - 1,
            row=2,
        )
        proxima.callback = self.proxima
        self.add_item(proxima)
        voltar = discord.ui.Button(label="Voltar ao Mercado", style=discord.ButtonStyle.secondary, row=3)
        voltar.callback = self.voltar_mercado
        self.add_item(voltar)

    def embed(self) -> discord.Embed:
        ficha = FichaPersonagem.carregar(self.caminho)
        descricao = (
            f"**XP disponível:** {ficha.xp}\n"
            "Escolha a perícia e, logo abaixo, a graduação desejada. "
            "A alteração só será salva depois da confirmação da compra."
        )
        if self.nome:
            atual = ficha.pericias.get(self.nome, 0)
            descricao += f"\n\n**{self.nome}:** {NOMES_RANK[atual]}"
            if self.alvo:
                descricao += (
                    f" → **{NOMES_RANK[self.alvo]}**\n"
                    f"**Custo:** {custo_pericia(atual, self.alvo)} XP"
                )
        return embed_painel("📌 Aprimorar perícia", descricao)

    async def selecionar_pericia(self, interaction: discord.Interaction) -> None:
        nome = self.seletor_pericia.values[0]
        ficha = FichaPersonagem.carregar(self.caminho)
        if ficha.pericias.get(nome, 0) >= 6:
            await interaction.response.send_message("Essa perícia já está no grau Mestre.", ephemeral=True)
            return
        nova_view = EscolhaPericiaMercadoView(self.usuario_id, self.caminho, self.pagina, nome)
        await interaction.response.edit_message(embed=nova_view.embed(), view=nova_view)

    async def selecionar_graduacao(self, interaction: discord.Interaction) -> None:
        alvo = int(self.seletor_graduacao.values[0])
        nova_view = EscolhaPericiaMercadoView(
            self.usuario_id,
            self.caminho,
            self.pagina,
            self.nome,
            alvo,
        )
        await interaction.response.edit_message(embed=nova_view.embed(), view=nova_view)

    async def continuar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        atual = ficha.pericias.get(self.nome, 0)
        if self.alvo not in RANKS_PERICIA or self.alvo <= atual:
            await interaction.response.send_message(
                "A graduação escolhida não está mais disponível. Selecione novamente.",
                ephemeral=True,
            )
            return
        custo = custo_pericia(atual, self.alvo)
        await interaction.response.edit_message(
            embed=embed_painel(
                "📌 Confirmar perícia",
                f"**{self.nome} — {NOMES_RANK[self.alvo]}** custará **{custo} XP**. "
                "Depois de confirmada, a compra não poderá ser revertida.",
            ),
            view=ConfirmarCompraView(
                self.usuario_id,
                self.caminho,
                "pericia",
                self.nome,
                self.alvo,
            ),
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        nova_view = EscolhaPericiaMercadoView(self.usuario_id, self.caminho, self.pagina - 1)
        await interaction.response.edit_message(embed=nova_view.embed(), view=nova_view)

    async def proxima(self, interaction: discord.Interaction) -> None:
        nova_view = EscolhaPericiaMercadoView(self.usuario_id, self.caminho, self.pagina + 1)
        await interaction.response.edit_message(embed=nova_view.embed(), view=nova_view)

    async def voltar_mercado(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "🛒 Mercado de XP",
                f"**{ficha.nome}** possui **{ficha.xp} XP** disponível. Escolha o que deseja adquirir.",
            ),
            view=MercadoXPView(self.usuario_id, self.caminho),
        )


class CategoriaHabilidadeMercadoView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__(usuario_id)
        self.caminho = caminho
        ficha = FichaPersonagem.carregar(caminho)
        categorias_disponiveis = []
        for chave, dados in CATEGORIAS_HABILIDADE.items():
            if chave == "heranca_sanguinea":
                maximo = total_evolucoes_heranca(ficha.heranca)
                disponivel = bool(maximo and ficha.evolucao_heranca < maximo)
            else:
                disponivel = bool(habilidades_disponiveis_mercado(ficha, chave))
            if disponivel:
                categorias_disponiveis.append(
                    discord.SelectOption(label=str(dados["nome"]), value=chave)
                )
        self.seletor: discord.ui.Select | None = None
        if categorias_disponiveis:
            seletor = discord.ui.Select(
                placeholder="Escolha a categoria",
                options=categorias_disponiveis,
            )
            seletor.callback = self.selecionar
            self.seletor = seletor
            self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar ao Mercado",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar_mercado
        self.add_item(voltar)

    async def voltar_mercado(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "🛒 Mercado de XP",
                f"**{ficha.nome}** possui **{ficha.xp} XP** disponível. Escolha o que deseja adquirir.",
            ),
            view=MercadoXPView(self.usuario_id, self.caminho),
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        if self.seletor is None:
            await interaction.response.send_message(
                "A ficha já possui todas as habilidades disponíveis no mercado.",
                ephemeral=True,
            )
            return
        categoria = self.seletor.values[0]
        ficha = FichaPersonagem.carregar(self.caminho)
        if categoria == "heranca_sanguinea":
            maximo = total_evolucoes_heranca(ficha.heranca)
            if not maximo:
                await interaction.response.send_message(
                    "A biblioteca não possui evoluções registradas para essa Herança Sanguínea.",
                    ephemeral=True,
                )
                return
            if ficha.evolucao_heranca >= maximo:
                await interaction.response.send_message(
                    f"A Herança Sanguínea **{ficha.heranca}** já está totalmente desbloqueada.",
                    ephemeral=True,
                )
                return
            entrada = carregar_habilidade(categoria, ficha.heranca)
            custo = custo_xp_habilidade(entrada) if entrada else None
            if custo is None:
                await interaction.response.send_message("O custo dessa Herança não está definido numericamente.", ephemeral=True)
                return
            custo = custo_heranca_com_alquimia(ficha, custo)
            await interaction.response.edit_message(
                embed=embed_painel("🧬 Evoluir Herança", f"A próxima evolução de **{ficha.heranca}** custa **{custo} XP**."),
                view=ConfirmarCompraView(self.usuario_id, self.caminho, "heranca", ficha.heranca, ficha.evolucao_heranca + 1),
            )
            return
        nomes = habilidades_disponiveis_mercado(ficha, categoria)
        if not nomes:
            await interaction.response.send_message(
                "A ficha já possui todas as habilidades disponíveis desta categoria.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel("💡 Escolher habilidade", "O mercado mostra somente o nome e o custo. Consulte `/habilidade` para conhecer seus efeitos."),
            view=EscolhaHabilidadeMercadoView(self.usuario_id, self.caminho, categoria, nomes, 0),
        )


class EscolhaHabilidadeMercadoView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path, categoria: str, nomes: list[str], pagina: int):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.categoria = categoria
        self.nomes = nomes
        self.paginas = [nomes[indice:indice + 25] for indice in range(0, len(nomes), 25)]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        ficha = FichaPersonagem.carregar(caminho)
        opcoes = []
        for nome in self.paginas[self.pagina]:
            entrada = carregar_habilidade(categoria, nome)
            custo = custo_xp_habilidade(entrada) if entrada else None
            descricao = f"{custo} XP" if custo is not None else "Custo variável"
            opcoes.append(discord.SelectOption(label=nome[:100], value=nome, description=descricao))
        seletor = discord.ui.Select(placeholder="Escolha a habilidade", options=opcoes)
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        if len(self.paginas) > 1:
            anterior = discord.ui.Button(label="Anterior", style=discord.ButtonStyle.secondary, disabled=self.pagina == 0, row=1)
            proxima = discord.ui.Button(label="Próxima", style=discord.ButtonStyle.secondary, disabled=self.pagina == len(self.paginas) - 1, row=1)
            anterior.callback = self.anterior
            proxima.callback = self.proxima
            self.add_item(anterior)
            self.add_item(proxima)
        voltar = discord.ui.Button(
            label="Voltar às Categorias",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        voltar.callback = self.voltar_categorias
        self.add_item(voltar)

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=EscolhaHabilidadeMercadoView(self.usuario_id, self.caminho, self.categoria, self.nomes, self.pagina - 1)
        )

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=EscolhaHabilidadeMercadoView(self.usuario_id, self.caminho, self.categoria, self.nomes, self.pagina + 1)
        )

    async def voltar_categorias(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel("💡 Comprar habilidade", "Escolha a categoria da habilidade."),
            view=CategoriaHabilidadeMercadoView(self.usuario_id, self.caminho),
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        nome = self.seletor.values[0]
        ficha = FichaPersonagem.carregar(self.caminho)
        if (
            self.categoria == "especializacao"
            and normalizar_rotulo(nome) == normalizar_rotulo(MODELO_MESTRIA_FEITICO)
        ):
            referencias = listar_feiticos_mestria(ficha)
            if not referencias:
                await interaction.response.send_message(
                    "A ficha já possui Mestria em todos os feitiços disponíveis.",
                    ephemeral=True,
                )
                return
            await interaction.response.edit_message(
                embed=embed_painel(
                    "⚡ Mestria em Feitiço",
                    "Escolha primeiro a categoria, depois a divisão apresentada e, por fim, o feitiço.",
                ),
                view=CategoriaMestriaFeiticoMercadoView(
                    self.usuario_id,
                    self.caminho,
                    referencias,
                ),
            )
            return
        possuidas = (
            ficha.origens_magicas
            if self.categoria == "origem_magica"
            else ficha.especializacoes
        )
        if habilidade_ja_possuida(possuidas, nome):
            await interaction.response.send_message(
                "A ficha já possui essa habilidade.",
                ephemeral=True,
            )
            return
        entrada = carregar_habilidade(self.categoria, nome)
        custo = custo_xp_habilidade(entrada) if entrada else None
        if (
            self.categoria == "origem_magica"
            and normalizar_rotulo(nome) == normalizar_rotulo("Experiência Alquímica")
        ):
            await interaction.response.edit_message(
                embed=embed_painel(
                    "🧪 Experiência Alquímica",
                    "Escolha a situação definida com o mestre. Essa decisão ficará registrada na ficha.",
                ),
                view=EscolhaExperienciaAlquimicaView(
                    self.usuario_id,
                    self.caminho,
                ),
            )
            return
        if custo is None:
            await interaction.response.send_modal(
                CustoVariavelHabilidadeModal(
                    self.usuario_id,
                    self.caminho,
                    self.categoria,
                    nome,
                )
            )
            return
        acao = "origem" if self.categoria == "origem_magica" else "especializacao"
        await interaction.response.edit_message(
            embed=embed_painel("💡 Confirmar habilidade", f"**{nome}** custa **{custo} XP**."),
            view=ConfirmarCompraView(self.usuario_id, self.caminho, acao, nome, 0),
        )


class EscolhaExperienciaAlquimicaView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__(usuario_id)
        self.caminho = caminho
        seletor = discord.ui.Select(
            placeholder="Situação da Experiência Alquímica",
            options=[
                discord.SelectOption(
                    label="Origem Mágica",
                    value="origem",
                    description="Adquire uma Origem Mágica pela metade do custo.",
                    emoji="✨",
                ),
                discord.SelectOption(
                    label="Herança Sanguínea",
                    value="heranca",
                    description="Evolui a Herança pela metade e mantém esse desconto nas próximas evoluções.",
                    emoji="🧬",
                ),
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar às habilidades", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        if possui(ficha.origens_magicas, "Experiência Alquímica"):
            await interaction.response.send_message(
                "A ficha já possui Experiência Alquímica.",
                ephemeral=True,
            )
            return
        if self.seletor.values[0] == "origem":
            nomes = []
            for nome in habilidades_disponiveis_mercado(ficha, "origem_magica"):
                if normalizar_rotulo(nome) == normalizar_rotulo("Experiência Alquímica"):
                    continue
                entrada = carregar_habilidade("origem_magica", nome)
                if entrada is not None and custo_xp_habilidade(entrada) is not None:
                    nomes.append(nome)
            await interaction.response.edit_message(
                embed=embed_painel(
                    "✨ Origem Mágica pela Alquimia",
                    "Escolha a Origem Mágica adquirida. O mercado mostrará o custo original e o valor reduzido pela metade.",
                ),
                view=OrigemExperienciaAlquimicaView(
                    self.usuario_id,
                    self.caminho,
                    nomes,
                    0,
                ),
            )
            return
        entrada = carregar_habilidade("heranca_sanguinea", ficha.heranca)
        custo_original = custo_xp_habilidade(entrada) if entrada else None
        maximo = total_evolucoes_heranca(ficha.heranca)
        if custo_original is None:
            await interaction.response.send_message(
                "O custo da Herança Sanguínea não está definido numericamente.",
                ephemeral=True,
            )
            return
        if not maximo or ficha.evolucao_heranca >= maximo:
            await interaction.response.send_message(
                f"A Herança Sanguínea **{ficha.heranca}** já está totalmente desbloqueada.",
                ephemeral=True,
            )
            return
        custo = max(0, custo_original // 2)
        await interaction.response.edit_message(
            embed=embed_painel(
                "🧬 Herança Sanguínea pela Alquimia",
                f"A próxima evolução de **{ficha.heranca}** custava **{custo_original} XP** e será adquirida por **{custo} XP**. As próximas evoluções também custarão metade.",
            ),
            view=ConfirmarCompraView(
                self.usuario_id,
                self.caminho,
                "experiencia_alquimica_heranca",
                ficha.heranca,
                ficha.evolucao_heranca + 1,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        nomes = habilidades_disponiveis_mercado(ficha, "origem_magica")
        await interaction.response.edit_message(
            embed=embed_painel(
                "💡 Escolher habilidade",
                "O mercado mostra somente o nome e o custo. Consulte `/habilidade` para conhecer seus efeitos.",
            ),
            view=EscolhaHabilidadeMercadoView(
                self.usuario_id,
                self.caminho,
                "origem_magica",
                nomes,
                0,
            ),
        )


class OrigemExperienciaAlquimicaView(ViewAutor):
    def __init__(self, usuario_id: int, caminho: Path, nomes: list[str], pagina: int):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.nomes = nomes
        self.paginas = [nomes[indice:indice + 25] for indice in range(0, len(nomes), 25)] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        itens = self.paginas[self.pagina]
        if itens:
            seletor = discord.ui.Select(
                placeholder=f"Origem Mágica — página {self.pagina + 1}/{len(self.paginas)}",
                options=[
                    discord.SelectOption(
                        label=nome[:100],
                        value=nome[:100],
                        description=self.descricao_custo(nome),
                    )
                    for nome in itens
                ],
            )
            seletor.callback = self.selecionar
            self.seletor = seletor
            self.add_item(seletor)
        if len(self.paginas) > 1:
            anterior = discord.ui.Button(label="Anterior", style=discord.ButtonStyle.secondary, disabled=self.pagina == 0, row=1)
            proxima = discord.ui.Button(label="Próxima", style=discord.ButtonStyle.secondary, disabled=self.pagina == len(self.paginas) - 1, row=1)
            anterior.callback = self.anterior
            proxima.callback = self.proxima
            self.add_item(anterior)
            self.add_item(proxima)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=2)
        voltar.callback = self.voltar
        self.add_item(voltar)

    @staticmethod
    def descricao_custo(nome: str) -> str:
        entrada = carregar_habilidade("origem_magica", nome)
        custo = custo_xp_habilidade(entrada) if entrada else None
        return f"{custo} XP → {max(0, custo // 2)} XP pela Alquimia" if custo is not None else "Custo indisponível"

    async def selecionar(self, interaction: discord.Interaction) -> None:
        nome = self.seletor.values[0]
        entrada = carregar_habilidade("origem_magica", nome)
        custo_original = custo_xp_habilidade(entrada) if entrada else None
        if custo_original is None:
            await interaction.response.send_message(
                "A Origem Mágica escolhida não possui custo numérico.",
                ephemeral=True,
            )
            return
        custo = max(0, custo_original // 2)
        await interaction.response.edit_message(
            embed=embed_painel(
                "✨ Confirmar Experiência Alquímica",
                f"**{nome}** custava **{custo_original} XP** e será adquirida por **{custo} XP** através da Alquimia. Experiência Alquímica também será adicionada à ficha.",
            ),
            view=ConfirmarCompraView(
                self.usuario_id,
                self.caminho,
                "experiencia_alquimica_origem",
                nome,
                0,
            ),
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=OrigemExperienciaAlquimicaView(self.usuario_id, self.caminho, self.nomes, self.pagina - 1))

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=OrigemExperienciaAlquimicaView(self.usuario_id, self.caminho, self.nomes, self.pagina + 1))

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🧪 Experiência Alquímica",
                "Escolha a situação definida com o mestre. Essa decisão ficará registrada na ficha.",
            ),
            view=EscolhaExperienciaAlquimicaView(self.usuario_id, self.caminho),
        )


class CustoVariavelHabilidadeModal(discord.ui.Modal):
    def __init__(self, usuario_id: int, caminho: Path, categoria: str, nome: str):
        super().__init__(title="Definir custo da habilidade")
        self.usuario_id = usuario_id
        self.caminho = caminho
        self.categoria = categoria
        self.nome = nome
        self.custo = discord.ui.TextInput(
            label="Custo final definido pelo mestre em XP",
            placeholder="Informe apenas o valor em XP",
            min_length=1,
            max_length=7,
        )
        self.add_item(self.custo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.usuario_id:
            await interaction.response.send_message(
                "Somente quem iniciou esta compra pode definir o custo.",
                ephemeral=True,
            )
            return
        texto = str(self.custo.value).strip()
        if not texto.isdigit() or int(texto) <= 0:
            await interaction.response.send_message(
                "Informe um custo inteiro maior que zero, usando somente números.",
                ephemeral=True,
            )
            return
        custo = int(texto)
        ficha = FichaPersonagem.carregar(self.caminho)
        possuidas = (
            ficha.origens_magicas
            if self.categoria == "origem_magica"
            else ficha.especializacoes
        )
        if habilidade_ja_possuida(possuidas, self.nome):
            await interaction.response.send_message(
                "A ficha já possui essa habilidade.",
                ephemeral=True,
            )
            return
        acao = "origem" if self.categoria == "origem_magica" else "especializacao"
        await interaction.response.edit_message(
            embed=embed_painel(
                "💡 Confirmar habilidade",
                f"**{self.nome}** possui custo variável. O custo final definido foi **{custo} XP**.",
            ),
            view=ConfirmarCompraView(
                self.usuario_id,
                self.caminho,
                acao,
                self.nome,
                0,
                custo_personalizado=custo,
            ),
        )


class CategoriaMestriaFeiticoMercadoView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        referencias: list[ReferenciaFeiticoFicha],
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.referencias = referencias
        categorias = categorias_mestria(referencias)
        seletor = discord.ui.Select(
            placeholder="Categoria do feitiço",
            options=[
                discord.SelectOption(
                    label=categoria[:100],
                    value=categoria[:100],
                    description=(
                        f"{sum(normalizar_rotulo(ref.categoria) == normalizar_rotulo(categoria) for ref in referencias)} feitiço(s) disponível(is)."
                    )[:100],
                )
                for categoria in categorias
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar às Especializações",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        categoria = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=embed_painel(
                "⚡ Mestria em Feitiço",
                f"Escolha {rotulo_divisao_mestria(categoria).lower()} em **{categoria}**.",
            ),
            view=AnoMestriaFeiticoMercadoView(
                self.usuario_id,
                self.caminho,
                self.referencias,
                categoria,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        nomes = habilidades_disponiveis_mercado(
            FichaPersonagem.carregar(self.caminho), "especializacao"
        )
        await interaction.response.edit_message(
            embed=embed_painel(
                "💡 Escolher habilidade",
                "O mercado mostra somente o nome e o custo. Consulte `/habilidade` para conhecer seus efeitos.",
            ),
            view=EscolhaHabilidadeMercadoView(
                self.usuario_id, self.caminho, "especializacao", nomes, 0
            ),
        )


class AnoMestriaFeiticoMercadoView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        referencias: list[ReferenciaFeiticoFicha],
        categoria: str,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.referencias = referencias
        self.categoria = categoria
        anos = anos_mestria(categoria, referencias)
        rotulo_divisao = rotulo_divisao_mestria(categoria)
        seletor = discord.ui.Select(
            placeholder=rotulo_divisao[:150],
            options=[
                discord.SelectOption(
                    label=ano[:100],
                    value=ano[:100],
                    description=(
                        f"{sum(normalizar_rotulo(ref.categoria) == normalizar_rotulo(categoria) and normalizar_rotulo(divisao_mestria(ref, categoria)) == normalizar_rotulo(ano) for ref in referencias)} feitiço(s) disponível(is)."
                    )[:100],
                )
                for ano in anos
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar às Categorias",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        ano = self.seletor.values[0]
        referencias = [
            referencia
            for referencia in self.referencias
            if normalizar_rotulo(referencia.categoria)
            == normalizar_rotulo(self.categoria)
            and normalizar_rotulo(divisao_mestria(referencia, self.categoria))
            == normalizar_rotulo(ano)
        ]
        await interaction.response.edit_message(
            embed=embed_painel(
                "⚡ Mestria em Feitiço",
                f"Escolha em **{self.categoria} › {ano}**.",
            ),
            view=MestriaFeiticoMercadoView(
                self.usuario_id,
                self.caminho,
                self.referencias,
                self.categoria,
                ano,
                referencias,
                0,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "⚡ Mestria em Feitiço",
                "Escolha a categoria do feitiço.",
            ),
            view=CategoriaMestriaFeiticoMercadoView(
                self.usuario_id,
                self.caminho,
                self.referencias,
            ),
        )


class MestriaFeiticoMercadoView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        todas_referencias: list[ReferenciaFeiticoFicha],
        categoria: str,
        ano: str,
        referencias: list[ReferenciaFeiticoFicha],
        pagina: int,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.todas_referencias = todas_referencias
        self.categoria = categoria
        self.ano = ano
        self.referencias = sorted(referencias, key=lambda item: item.nome.casefold())
        self.total_paginas = max(1, (len(self.referencias) + 24) // 25)
        self.pagina = max(0, min(pagina, self.total_paginas - 1))
        inicio = self.pagina * 25
        itens = self.referencias[inicio:inicio + 25]
        seletor = discord.ui.Select(
            placeholder=f"Feitiços — página {self.pagina + 1}/{self.total_paginas}",
            options=[
                discord.SelectOption(
                    label=referencia.nome[:100],
                    value=str(inicio + indice),
                    description=f"{categoria} • {ano}"[:100],
                )
                for indice, referencia in enumerate(itens)
            ],
        )
        seletor.callback = self.selecionar_feitico
        self.seletor_feitico = seletor
        self.add_item(seletor)
        if self.total_paginas > 1:
            anterior = discord.ui.Button(
                label="Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == 0,
                row=1,
            )
            proxima = discord.ui.Button(
                label="Próxima",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == self.total_paginas - 1,
                row=1,
            )
            anterior.callback = self.anterior
            proxima.callback = self.proxima
            self.add_item(anterior)
            self.add_item(proxima)
        voltar = discord.ui.Button(
            label=(
                "Voltar às Categorias de Trevas"
                if normalizar_rotulo(categoria)
                == normalizar_rotulo("Arte das Trevas")
                else "Voltar aos Anos"
            ),
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar_feitico(self, interaction: discord.Interaction) -> None:
        referencia = self.referencias[int(self.seletor_feitico.values[0])]
        nome_especializacao = nome_mestria_feitico(referencia.nome)
        await interaction.response.edit_message(
            embed=embed_painel(
                "⚡ Confirmar Mestria",
                f"Adquirir **{nome_especializacao}** ({referencia.categoria} • {self.ano}) por **20 XP**?",
            ),
            view=ConfirmarCompraView(
                self.usuario_id,
                self.caminho,
                "especializacao",
                nome_especializacao,
                0,
            ),
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=MestriaFeiticoMercadoView(
                self.usuario_id,
                self.caminho,
                self.todas_referencias,
                self.categoria,
                self.ano,
                self.referencias,
                self.pagina - 1,
            )
        )

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            view=MestriaFeiticoMercadoView(
                self.usuario_id,
                self.caminho,
                self.todas_referencias,
                self.categoria,
                self.ano,
                self.referencias,
                self.pagina + 1,
            )
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "⚡ Mestria em Feitiço",
                f"Escolha {rotulo_divisao_mestria(self.categoria).lower()} em **{self.categoria}**.",
            ),
            view=AnoMestriaFeiticoMercadoView(
                self.usuario_id,
                self.caminho,
                self.todas_referencias,
                self.categoria,
            ),
        )


def _quantidade_modal(valor: str, *, maximo: int = 20) -> int:
    try:
        quantidade = int(str(valor).strip())
    except (TypeError, ValueError) as erro:
        raise ValueError("Informe uma quantidade inteira.") from erro
    if quantidade < 1 or quantidade > maximo:
        raise ValueError(f"A quantidade deve estar entre 1 e {maximo}.")
    return quantidade


class QuantidadeNivelModal(discord.ui.Modal, title="Quantidade de níveis"):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__()
        self.usuario_id = usuario_id
        self.caminho = caminho
        self.quantidade = discord.ui.TextInput(
            label="Quantos níveis deseja subir?",
            placeholder="1",
            required=True,
            max_length=2,
        )
        self.add_item(self.quantidade)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            quantidade = _quantidade_modal(str(self.quantidade.value), maximo=20)
            ficha = FichaPersonagem.carregar(self.caminho)
            custo = custo_subir_niveis(ficha, quantidade)
            if ficha.xp < custo:
                raise ValueError(
                    f"XP insuficiente: **{quantidade} níveis** custam **{custo} XP**, "
                    f"mas a ficha possui **{ficha.xp} XP**."
                )
            await interaction.response.edit_message(
                embed=embed_atributos_mercado(
                    ficha,
                    2 * quantidade,
                    nivel_destino=ficha.nivel + quantidade,
                    custo_nivel=custo,
                    quantidade_niveis=quantidade,
                ),
                view=AtributosMercadoView(
                    self.usuario_id,
                    self.caminho,
                    ficha,
                    nivel_destino=ficha.nivel + quantidade,
                    custo_nivel=custo,
                    quantidade_niveis=quantidade,
                ),
            )
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)


class QuantidadeAptidaoModal(discord.ui.Modal, title="Quantidade de aptidão"):
    def __init__(self, usuario_id: int, caminho: Path, nome: str):
        super().__init__()
        self.usuario_id = usuario_id
        self.caminho = caminho
        self.nome = nome
        self.quantidade = discord.ui.TextInput(
            label=f"Quantos pontos em {nome}?"[:45],
            placeholder="Acima de zero",
            required=True,
            max_length=2,
        )
        self.add_item(self.quantidade)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            quantidade = _quantidade_modal(str(self.quantidade.value), maximo=20)
            ficha = FichaPersonagem.carregar(self.caminho)
            atual = ficha.aptidoes.get(self.nome, 0)
            bonus_passivo = bonus_aptidoes_passivos(ficha).get(self.nome, 0)
            atual_efetivo = atual + bonus_passivo
            custo = custo_aprimorar_aptidoes(ficha, self.nome, quantidade)
            proximo = atual + quantidade
            proximo_efetivo = proximo + bonus_passivo
            desconto = desconto_aptidao(ficha)
            parcelas = []
            for indice in range(1, quantidade + 1):
                grau = atual + indice + bonus_passivo
                parcela = max(0, 20 * grau - desconto)
                parcelas.append(
                    f"20×{grau}"
                    + (f"−{desconto}" if desconto else "")
                    + f"={parcela}"
                )
            if ficha.xp < custo:
                raise ValueError(
                    f"XP insuficiente: **{quantidade} pontos** custam **{custo} XP**, "
                    f"mas a ficha possui **{ficha.xp} XP**."
                )
            descricao_confirmacao = (
                f"**Aptidão:** {self.nome}\n"
                f"**Bônus atual:** {formatar_bonus(atual_efetivo)}\n"
                f"**Bônus escolhido:** +{quantidade}\n"
                f"**Novo bônus:** {formatar_bonus(proximo_efetivo)}\n\n"
                f"**Cálculo:** {' + '.join(parcelas)} = {custo} XP\n"
                + (f"**Desconto aplicado:** −{desconto} XP por ponto\n" if desconto else "")
                + f"**XP disponível:** {ficha.xp} XP\n"
                + f"**Custo total:** {custo} XP\n"
                + f"**Saldo após a compra:** {ficha.xp - custo} XP\n\n"
                + "Depois de confirmada, a compra não poderá ser revertida."
            )
            await interaction.response.edit_message(
                embed=embed_painel(
                    "✨ Confirmar aptidão",
                    descricao_confirmacao,
                ),
                view=ConfirmarCompraView(
                    self.usuario_id,
                    self.caminho,
                    "aptidao",
                    self.nome,
                    proximo,
                    quantidade=quantidade,
                ),
            )
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)


class ConfirmarCompraView(ViewAutor):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        acao: str,
        item: str,
        alvo: int,
        *,
        custo_personalizado: int | None = None,
        quantidade: int = 1,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.acao = acao
        self.item = item
        self.alvo = alvo
        self.custo_personalizado = custo_personalizado
        self.quantidade = quantidade
        self.concluido = False

    @discord.ui.button(label="Confirmar compra", style=discord.ButtonStyle.success, emoji="✅")
    async def confirmar(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        if self.concluido:
            await interaction.response.send_message("Esta compra já foi encerrada.", ephemeral=True)
            return
        if self.acao == "nivel":
            lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
            async with lock:
                ficha = FichaPersonagem.carregar(self.caminho)
                custo = custo_subir_nivel(ficha)
                if ficha.pontos_atributo_disponiveis:
                    await interaction.response.send_message(
                        "Distribua primeiro os pontos de atributo que já estão pendentes na ficha.",
                        ephemeral=True,
                    )
                    return
                if ficha.xp < custo:
                    await interaction.response.send_message(
                        f"XP insuficiente: a subida custa **{custo} XP**, mas a ficha possui **{ficha.xp} XP**.",
                        ephemeral=True,
                    )
                    return
            self.concluido = True
            self.stop()
            await interaction.response.edit_message(
                embed=embed_atributos_mercado(
                    ficha,
                    2,
                    nivel_destino=ficha.nivel + 1,
                    custo_nivel=custo,
                ),
                view=AtributosMercadoView(
                    self.usuario_id,
                    self.caminho,
                    ficha,
                    nivel_destino=ficha.nivel + 1,
                    custo_nivel=custo,
                ),
            )
            return
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            ficha = FichaPersonagem.carregar(self.caminho)
            try:
                custo = aplicar_compra(
                    ficha,
                    self.acao,
                    self.item,
                    self.alvo,
                    custo_personalizado=self.custo_personalizado,
                    quantidade=self.quantidade,
                )
            except ValueError as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return
            if ficha.xp < custo:
                await interaction.response.send_message(
                    f"XP insuficiente: a compra custa **{custo} XP**, mas a ficha possui **{ficha.xp} XP**.",
                    ephemeral=True,
                )
                return
            ficha.xp -= custo
            salvar_ficha(ficha, self.caminho)
        self.concluido = True
        self.stop()
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
            attachments=criar_arquivos_discord(anexos_ficha(ficha)),
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji="❌")
    async def voltar(self, interaction: discord.Interaction, botao: discord.ui.Button) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embed=embed_painel(
                "🛒 Mercado de XP",
                f"**{ficha.nome}** possui **{ficha.xp} XP** disponível. Escolha o que deseja adquirir.",
            ),
            view=MercadoXPView(self.usuario_id, self.caminho),
        )


def aplicar_compra(
    ficha: FichaPersonagem,
    acao: str,
    item: str,
    alvo: int,
    *,
    custo_personalizado: int | None = None,
    quantidade: int = 1,
) -> int:
    if acao == "nivel":
        raise ValueError("Distribua os pontos de atributo antes de concluir a subida de nível.")
    if acao == "aptidao":
        atual = ficha.aptidoes.get(item, 0)
        if quantidade < 1 or alvo != atual + quantidade:
            raise ValueError("A aptidão mudou desde a abertura do mercado. Reabra a compra.")
        custo = custo_aprimorar_aptidoes(ficha, item, quantidade)
        ficha.aptidoes[item] = alvo
        return custo
    if acao == "pericia":
        atual = ficha.pericias.get(item, 0)
        if alvo not in RANKS_PERICIA or alvo <= atual:
            raise ValueError("A graduação escolhida não é mais válida.")
        ficha.pericias[item] = alvo
        return custo_pericia(atual, alvo)
    if acao == "heranca":
        entrada = carregar_habilidade("heranca_sanguinea", ficha.heranca)
        custo = custo_xp_habilidade(entrada) if entrada else None
        if custo is None:
            raise ValueError("O custo da Herança não está definido numericamente.")
        custo = custo_heranca_com_alquimia(ficha, custo)
        maximo = total_evolucoes_heranca(ficha.heranca)
        if not maximo:
            raise ValueError("A biblioteca não possui evoluções registradas para essa Herança Sanguínea.")
        if ficha.evolucao_heranca >= maximo:
            raise ValueError("A Herança Sanguínea já está totalmente desbloqueada.")
        ficha.evolucao_heranca += 1
        return custo
    if acao in {
        "experiencia_alquimica_origem",
        "experiencia_alquimica_heranca",
    }:
        if possui(ficha.origens_magicas, "Experiência Alquímica"):
            raise ValueError("A ficha já possui Experiência Alquímica.")
        if acao == "experiencia_alquimica_origem":
            if normalizar_rotulo(item) == normalizar_rotulo("Experiência Alquímica"):
                raise ValueError("Escolha outra Origem Mágica para receber através da Alquimia.")
            if habilidade_ja_possuida(ficha.origens_magicas, item):
                raise ValueError("A ficha já possui essa Origem Mágica.")
            entrada = carregar_habilidade("origem_magica", item)
            custo_original = custo_xp_habilidade(entrada) if entrada else None
            if custo_original is None:
                raise ValueError("O custo da Origem Mágica escolhida não está definido numericamente.")
            ficha.origens_magicas.extend(["Experiência Alquímica", item])
            ficha.escolha_experiencia_alquimica = "Origem Mágica"
            return max(0, custo_original // 2)
        entrada = carregar_habilidade("heranca_sanguinea", ficha.heranca)
        custo_original = custo_xp_habilidade(entrada) if entrada else None
        maximo = total_evolucoes_heranca(ficha.heranca)
        if custo_original is None:
            raise ValueError("O custo da Herança Sanguínea não está definido numericamente.")
        if not maximo or ficha.evolucao_heranca >= maximo:
            raise ValueError("A Herança Sanguínea já está totalmente desbloqueada.")
        if alvo != ficha.evolucao_heranca + 1:
            raise ValueError("A evolução da Herança mudou desde a abertura da compra.")
        ficha.origens_magicas.append("Experiência Alquímica")
        ficha.escolha_experiencia_alquimica = "Herança Sanguínea"
        ficha.evolucao_heranca += 1
        return max(0, custo_original // 2)
    if acao in {"origem", "especializacao"}:
        categoria = "origem_magica" if acao == "origem" else "especializacao"
        destino = ficha.origens_magicas if acao == "origem" else ficha.especializacoes
        if acao == "origem" and normalizar_rotulo(item) == normalizar_rotulo("Experiência Alquímica"):
            raise ValueError("Escolha primeiro se a Experiência Alquímica será aplicada à Herança Sanguínea ou a outra Origem Mágica.")
        if habilidade_ja_possuida(destino, item):
            raise ValueError("A ficha já possui essa habilidade.")
        nome_modelo = item
        if acao == "especializacao":
            feitico_mestria = nome_feitico_da_mestria(item)
            if feitico_mestria:
                if referencia_feitico_mestria(feitico_mestria) is None:
                    raise ValueError("O feitiço escolhido não está mais disponível na biblioteca.")
                nome_modelo = MODELO_MESTRIA_FEITICO
        entrada = carregar_habilidade(categoria, nome_modelo)
        custo = custo_xp_habilidade(entrada) if entrada else None
        if custo is None:
            if custo_personalizado is None or custo_personalizado <= 0:
                raise ValueError("Informe o custo variável definido pelo mestre.")
            custo = custo_personalizado
        destino.append(item)
        return custo
    raise ValueError("Operação desconhecida no Mercado de XP.")


class ConsultaCategoriaFichaView(ViewAutor):
    def __init__(self, usuario_id: int):
        super().__init__(usuario_id)
        fichas_disponiveis = listar_fichas()
        contagens = {
            grupo: sum(1 for item in fichas_disponiveis if item.grupo == grupo)
            for grupo in GRUPOS_FICHA
        }
        seletor = discord.ui.Select(
            placeholder="Escolha a categoria da ficha",
            options=[
                discord.SelectOption(
                    label=grupo,
                    value=grupo,
                    emoji=EMOJIS_PASTAS_FICHA[grupo],
                    description=(
                        f"{contagens[grupo]} ficha(s) disponível(is)."
                        if contagens[grupo]
                        else "Categoria reservada; ainda não possui fichas."
                    ),
                )
                for grupo in GRUPOS_FICHA
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        grupo = self.seletor.values[0]
        paginas = paginas_fichas_alfabeticas(
            item for item in listar_fichas() if item.grupo == grupo
        )
        primeira_preenchida = next(
            (indice for indice, (_, itens) in enumerate(paginas) if itens),
            0,
        )
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🔎 {grupo}",
                "Escolha a faixa alfabética e, em seguida, a ficha.",
            ),
            view=ConsultaAlfabeticaFichaView(
                self.usuario_id,
                grupo,
                primeira_preenchida,
            ),
        )


class ConsultaAlfabeticaFichaView(ViewAutor):
    def __init__(self, usuario_id: int, grupo: str, pagina: int):
        super().__init__(usuario_id)
        self.grupo = grupo
        self.paginas = paginas_fichas_alfabeticas(
            item for item in listar_fichas() if item.grupo == grupo
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
                placeholder=f"Fichas — {rotulo}",
                options=[
                    discord.SelectOption(
                        label=referencia.nome[:100],
                        value=str(indice),
                    )
                    for indice, referencia in enumerate(referencias)
                ],
                row=1,
            )
            fichas.callback = self.selecionar_ficha
            self.fichas = fichas
            self.add_item(fichas)

        voltar = discord.ui.Button(
            label="Voltar às categorias",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar_faixa(self, interaction: discord.Interaction) -> None:
        pagina = int(self.faixas.values[0])
        rotulo, itens = self.paginas[pagina]
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🔎 {self.grupo} — {rotulo}",
                (
                    "Escolha uma ficha nesta faixa."
                    if itens
                    else "Esta faixa ainda não possui fichas. Escolha outra faixa."
                ),
            ),
            view=ConsultaAlfabeticaFichaView(
                self.usuario_id,
                self.grupo,
                pagina,
            ),
        )

    async def selecionar_ficha(self, interaction: discord.Interaction) -> None:
        # Responde ao Discord imediatamente. Fichas grandes (como a Dra. Muerstein)
        # podem levar mais de 3 segundos para montar imagem + embeds; sem defer,
        # o Discord encerra a interação antes do painel ficar pronto.
        await interaction.response.defer()

        referencia = self.referencias[int(self.fichas.values[0])]
        if not referencia.caminho.is_file():
            await interaction.followup.send(
                "A ficha escolhida não está mais disponível na biblioteca.",
                ephemeral=True,
            )
            return

        try:
            # Sempre relê a versão atual do arquivo no momento do clique.
            ficha = FichaPersonagem.carregar(referencia.caminho)
            principal, parte_2, parte_3 = dividir_embeds_ficha_interacao(ficha)

            await interaction.edit_original_response(
                embeds=principal,
                view=FichaAtualView(self.usuario_id, referencia.caminho),
                attachments=criar_arquivos_discord(anexos_ficha(ficha)),
            )
            if parte_2:
                await interaction.followup.send(
                    embeds=parte_2,
                    ephemeral=True,
                )
            if parte_3:
                await interaction.followup.send(
                    embeds=parte_3,
                    ephemeral=True,
                )

            # Migração automática de layout:
            # abrir /ficha consultar NÃO sincroniza a thread normalmente.
            # Porém, se a regra atual passou a exigir um número diferente de
            # mensagens (ex.: a publicação antiga tinha 2 e agora precisa de 3),
            # fazemos a migração uma única vez: apaga apenas as mensagens
            # registradas dessa ficha, republica no formato novo e salva os IDs.
            partes_necessarias = 1 + int(bool(parte_2)) + int(bool(parte_3))
            partes_registradas = quantidade_partes_registradas(ficha)
            layout_desatualizado = False
            if ficha.mensagem_discord_id:
                layout_desatualizado = await publicacao_precisa_migrar_layout(
                    interaction.client,
                    ficha,
                    principal,
                    parte_2,
                    parte_3,
                )

            if ficha.mensagem_discord_id and (
                partes_necessarias != partes_registradas
                or layout_desatualizado
            ):
                try:
                    await sincronizar_publicacao_personagem(
                        interaction,
                        ficha,
                        referencia.caminho,
                    )
                    motivo = (
                        f"{partes_registradas} -> {partes_necessarias} partes"
                        if partes_registradas != partes_necessarias
                        else "layout das partes mudou"
                    )
                    print(
                        f"[MIGRAÇÃO THREAD] {ficha.nome}: {motivo}."
                    )
                except (ErroPublicacaoFicha, OSError, ValueError) as erro:
                    print(
                        f"[ERRO MIGRAÇÃO THREAD] {referencia.caminho}: {erro!r}"
                    )
                    await interaction.followup.send(
                        "A ficha abriu, mas não consegui migrar a publicação "
                        "antiga da thread para o novo número de partes. "
                        "O erro foi registrado no terminal do Grimory.",
                        ephemeral=True,
                    )
        except Exception as erro:
            print(f"[ERRO /ficha consultar] {referencia.caminho}: {erro!r}")
            await interaction.followup.send(
                f"Não foi possível abrir **{referencia.nome}**. O erro foi registrado no terminal do Grimory.",
                ephemeral=True,
            )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🔎 Consultar ficha",
                "Escolha a pasta em que a ficha está organizada.",
            ),
            view=MenuPastaFichaView(self.usuario_id, "consultar"),
        )


DESCRICOES_PASTAS_FICHA = {
    "NPCs": "Bruxos, humanos, semi-humanos e espíritos.",
    "Figuras de Autoridade": "Professores e demais autoridades do cenário.",
    "Players": "Personagens de jogadores sem pasta de Casa.",
    "Grifinória": "Personagens organizados na Grifinória.",
    "Sonserina": "Personagens organizados na Sonserina.",
    "Lufa-Lufa": "Personagens organizados na Lufa-Lufa.",
    "Corvinal": "Personagens organizados na Corvinal.",
    "Criaturas": "Fichas de combate organizadas por periculosidade.",
}


class MenuAcaoFichaView(ViewAutor):
    def __init__(self, usuario_id: int):
        super().__init__(usuario_id)
        seletor = discord.ui.Select(
            placeholder="Escolha o que deseja fazer",
            options=[
                discord.SelectOption(
                    label="Criar",
                    value="criar",
                    emoji="➕",
                    description="Inicia uma nova ficha na pasta escolhida.",
                ),
                discord.SelectOption(
                    label="Consultar",
                    value="consultar",
                    emoji="🔎",
                    description="Localiza uma ficha já existente na biblioteca.",
                ),
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        acao = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=embed_painel(
                "➕ Criar ficha" if acao == "criar" else "🔎 Consultar ficha",
                "Escolha a pasta. Ela define o tipo de ficha e as próximas etapas.",
            ),
            view=MenuPastaFichaView(self.usuario_id, acao),
        )


class MenuPastaFichaView(ViewAutor):
    def __init__(self, usuario_id: int, acao: str):
        super().__init__(usuario_id)
        self.acao = acao
        grupos = ORDEM_PASTAS_FICHA
        seletor = discord.ui.Select(
            placeholder="Escolha a pasta da ficha",
            options=[
                discord.SelectOption(
                    label=grupo,
                    value=grupo,
                    emoji=EMOJIS_PASTAS_FICHA[grupo],
                    description=DESCRICOES_PASTAS_FICHA[grupo],
                )
                for grupo in grupos
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
        grupo = self.seletor.values[0]
        if self.acao == "criar":
            if grupo == "Criaturas":
                await interaction.response.edit_message(
                    embed=ficha_criaturas.painel(
                        "🐾 Criar ficha de criatura",
                        "Escolha uma espécie da biblioteca ou crie uma criatura que ainda não existe no RPG.",
                    ),
                    view=ficha_criaturas.FonteCriaturaView(self.usuario_id),
                )
                return
            await interaction.response.send_modal(CriarFichaModal(self.usuario_id, grupo))
            return

        if grupo == "Criaturas":
            await interaction.response.edit_message(
                embed=ficha_criaturas.painel(
                    "🔎 Consultar criatura",
                    "Escolha primeiro a periculosidade da ficha.",
                ),
                view=ficha_criaturas.ConsultaPericulosidadeCriaturaView(self.usuario_id),
            )
            return

        paginas = paginas_fichas_alfabeticas(
            item for item in listar_fichas() if item.grupo == grupo
        )
        primeira_preenchida = next(
            (indice for indice, (_, itens) in enumerate(paginas) if itens),
            0,
        )
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🔎 {grupo}",
                "Escolha a faixa alfabética e, em seguida, a ficha.",
            ),
            view=ConsultaAlfabeticaFichaView(self.usuario_id, grupo, primeira_preenchida),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🗂️ Fichas",
                "Escolha se deseja criar uma nova ficha ou consultar a biblioteca.",
            ),
            view=MenuAcaoFichaView(self.usuario_id),
        )


class Ficha(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ficha", description="Cria ou consulta fichas do Grimory.")
    async def ficha(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=embed_painel(
                "🗂️ Fichas",
                "Escolha se deseja criar uma nova ficha ou consultar a biblioteca.",
            ),
            view=MenuAcaoFichaView(interaction.user.id),
            ephemeral=True,
        )
