from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from utils.biblioteca import interpretar_markdown, normalizar_rotulo


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_FICHAS = RAIZ_PROJETO / "biblioteca" / "fichas"
PASTA_CONFIGURACOES = PASTA_FICHAS / "configurações"
PASTA_CASAS = PASTA_CONFIGURACOES / "Casas de Hogwarts"
PASTA_NUCLEOS = PASTA_CONFIGURACOES / "Núcleos de Varinha"
ORDEM_PASTAS_FICHA = (
    "Players",
    "NPCs",
    "Grifinória",
    "Sonserina",
    "Lufa-Lufa",
    "Corvinal",
    "Criaturas",
    "Figuras de Autoridade",
)
EMOJIS_PASTAS_FICHA = {
    "Players": "👤",
    "NPCs": "👥",
    "Grifinória": "❤️",
    "Sonserina": "💚",
    "Lufa-Lufa": "💛",
    "Corvinal": "💙",
    "Criaturas": "🦇",
    "Figuras de Autoridade": "📋",
}
GRUPOS_FICHA = tuple(
    pasta for pasta in ORDEM_PASTAS_FICHA if pasta != "Criaturas"
)
GRUPOS_ALFABETICOS_FICHAS = (
    "AB", "CD", "EF", "GH", "IJ", "KL", "MN", "OP", "QR", "ST", "UV", "WXYZ",
)
CASAS_HOGWARTS = ("Grifinória", "Sonserina", "Lufa-Lufa", "Corvinal")

ATRIBUTOS = (
    "Força",
    "Destreza",
    "Constituição",
    "Inteligência",
    "Sabedoria",
    "Carisma",
)
REDUCOES_DIFICULDADE = ("Intermediário", "Avançado")

PERICIAS = (
    "Atletismo",
    "Luta",
    "Reflexo",
    "Acrobacia",
    "Pontaria",
    "Esgrima",
    "Furtividade",
    "Iniciativa",
    "Montar",
    "Crime",
    "Prestidigitação",
    "Ciência",
    "Investigação",
    "Medicina",
    "Tática",
    "Tecnologia",
    "Armas de Fogo",
    "Adestramento",
    "Sobrevivência",
    "Rastreamento",
    "Intuição",
    "Percepção",
    "Vontade",
    "Sorte",
    "Artes",
    "Persuasão",
    "Enganação",
    "Intimidação",
    "Fortitude",
)

ATRIBUTOS_POR_PERICIA: dict[str, tuple[str, ...]] = {
    "Atletismo": ("Força", "Destreza"),
    "Luta": ("Força", "Destreza"),
    "Reflexo": ("Destreza",),
    "Acrobacia": ("Destreza",),
    "Pontaria": ("Destreza",),
    "Esgrima": ("Destreza",),
    "Furtividade": ("Destreza",),
    "Iniciativa": ("Destreza",),
    "Montar": ("Destreza",),
    "Crime": ("Destreza",),
    "Prestidigitação": ("Destreza",),
    "Ciência": ("Inteligência",),
    "Investigação": ("Inteligência",),
    "Medicina": ("Inteligência",),
    "Tática": ("Inteligência",),
    "Tecnologia": ("Inteligência",),
    "Armas de Fogo": ("Inteligência", "Sabedoria"),
    "Adestramento": ("Sabedoria",),
    "Sobrevivência": ("Sabedoria",),
    "Rastreamento": ("Sabedoria",),
    "Intuição": ("Sabedoria",),
    "Percepção": ("Sabedoria",),
    "Vontade": ("Sabedoria",),
    "Sorte": ("Carisma",),
    "Artes": ("Carisma",),
    "Persuasão": ("Carisma",),
    "Enganação": ("Carisma",),
    "Intimidação": ("Carisma",),
    "Fortitude": ("Constituição",),
}

GRUPOS_PERICIAS = (
    ("Força e Destreza", ("Força", "Destreza")),
    ("Inteligência e Sabedoria", ("Inteligência", "Sabedoria")),
    ("Carisma e Constituição", ("Carisma", "Constituição")),
)


def paginas_pericias(pericias: Iterable[str] = PERICIAS) -> list[tuple[str, list[str]]]:
    disponiveis = set(pericias)
    paginas: list[tuple[str, list[str]]] = []
    for rotulo, atributos in GRUPOS_PERICIAS:
        itens = [
            pericia
            for pericia in PERICIAS
            if pericia in disponiveis
            and any(atributo in atributos for atributo in ATRIBUTOS_POR_PERICIA[pericia])
        ]
        if itens:
            paginas.append((rotulo, itens))
    return paginas

SIGLAS_ATRIBUTOS = {
    "Força": "FOR",
    "Destreza": "DES",
    "Constituição": "CON",
    "Inteligência": "INT",
    "Sabedoria": "SAB",
    "Carisma": "CAR",
}

APTIDOES = (
    "Defesa contra Arte das Trevas",
    "Transfiguração",
    "Encantamentos",
    "Duelos",
    "Poções",
    "Herbologia",
    "História da Magia",
    "Astronomia",
    "Runas Antigas",
    "Estudo dos Trouxas",
    "Adivinhação",
    "Aritmância",
    "Trato de Criaturas Mágicas",
    "Alquimia",
    "Estudos Antigos",
    "Quadribol",
    "Vôo",
    "Arte das Trevas",
)


def modificador(valor: int) -> int:
    return (valor - 10) // 2


def formatar_bonus(valor: int) -> str:
    return f"{valor:+d}"


def bonus_pericia(
    nome: str,
    treinamento: int,
    atributos: dict[str, int],
) -> tuple[int, ...]:
    relacionados = ATRIBUTOS_POR_PERICIA[nome]
    return tuple(treinamento + modificador(atributos[atributo]) for atributo in relacionados)


def _linhas_mapa(valores: dict[str, int], ordem: Iterable[str]) -> str:
    return "\n".join(f"- {nome}: {valores.get(nome, 0)}" for nome in ordem)


def _linhas_lista(valores: Iterable[str]) -> str:
    itens = [valor.strip() for valor in valores if valor.strip()]
    return "\n".join(f"- {valor}" for valor in itens) if itens else "- --"


def _mapa_inteiros(texto: str) -> dict[str, int]:
    resultado: dict[str, int] = {}
    for linha in texto.splitlines():
        linha = linha.strip().removeprefix("- ").strip()
        if ":" not in linha:
            continue
        nome, valor = linha.rsplit(":", 1)
        try:
            resultado[nome.strip()] = int(valor.strip())
        except ValueError:
            continue
    return resultado


def _lista(texto: str) -> list[str]:
    return [
        linha.strip().removeprefix("- ").strip()
        for linha in texto.splitlines()
        if linha.strip().removeprefix("- ").strip() not in {"", "--"}
    ]


def _linhas_registros(registros: Iterable[dict[str, str]]) -> str:
    itens = [
        f"- {json.dumps(registro, ensure_ascii=False, separators=(',', ':'))}"
        for registro in registros
    ]
    return "\n".join(itens) if itens else "- --"


def _registros(
    texto: str,
    campos_obrigatorios: tuple[str, ...],
    campos_opcionais: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    registros: list[dict[str, str]] = []
    for linha in texto.splitlines():
        conteudo = linha.strip().removeprefix("- ").strip()
        if conteudo in {"", "--"}:
            continue
        try:
            registro = json.loads(conteudo)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(registro, dict):
            continue
        normalizado = {
            campo: str(registro.get(campo, "")).strip()
            for campo in (*campos_obrigatorios, *campos_opcionais)
        }
        if all(normalizado[campo] for campo in campos_obrigatorios):
            registros.append(normalizado)
    return registros


def _registros_livres(texto: str) -> list[dict[str, str]]:
    registros: list[dict[str, str]] = []
    for linha in texto.splitlines():
        conteudo = linha.strip().removeprefix("- ").strip()
        if conteudo in {"", "--"}:
            continue
        try:
            registro = json.loads(conteudo)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(registro, dict):
            registros.append({str(chave): str(valor) for chave, valor in registro.items()})
    return registros


def _registros_imagens(texto: str) -> list[dict[str, str]]:
    resultado: list[dict[str, str]] = []
    for registro in _registros(texto, (), ("titulo", "arquivo", "url")):
        referencia = registro.get("arquivo") or registro.get("url")
        if not referencia:
            continue
        item = {"titulo": registro.get("titulo", "")}
        item["arquivo" if registro.get("arquivo") else "url"] = referencia
        resultado.append(item)
    return resultado


def _inteiro(campos: dict[str, str], rotulo: str, padrao: int) -> int:
    try:
        return int(campos.get(normalizar_rotulo(rotulo), str(padrao)).strip())
    except ValueError:
        return padrao


def nome_com_estado_pv(nome: str, pv: int) -> str:
    if pv < 0 and not nome.casefold().startswith("(morrendo) "):
        return f"(morrendo) {nome}"
    return nome


@dataclass
class FichaPersonagem:
    nome: str
    grupo: str
    casa: str
    heranca: str
    nucleo: str
    titular_id: int = 0
    mensagem_discord_id: int = 0
    mensagem_discord_parte_2_id: int = 0
    mensagem_discord_parte_3_id: int = 0
    mensagem_narrativa_discord_id: int = 0
    mensagem_time_discord_id: int = 0
    nivel: int = 1
    xp: int = 300
    alma: int = 100
    pv: int = 20
    ph: int = 5
    idade: str = "--"
    altura: str = "--"
    ano: str = "--"
    familiar: str = "--"
    patronum: str = "--"
    classe_social: str = "Média"
    rolagem_social: int = 1
    modificador_social: int = 0
    galeoes: int = 10
    pontos_atributo_disponiveis: int = 0
    atributos: dict[str, int] = field(default_factory=lambda: {nome: 10 for nome in ATRIBUTOS})
    pericias: dict[str, int] = field(default_factory=lambda: {nome: 0 for nome in PERICIAS})
    aptidoes: dict[str, int] = field(default_factory=lambda: {nome: 0 for nome in APTIDOES})
    evolucao_heranca: int = 0
    escolha_experiencia_alquimica: str = ""
    bonus_atributos_temporarios: dict[str, int] = field(
        default_factory=lambda: {nome: 0 for nome in ATRIBUTOS}
    )
    reducoes_dificuldade_heranca: dict[str, int] = field(
        default_factory=lambda: {nome: 0 for nome in REDUCOES_DIFICULDADE}
    )
    origens_magicas: list[str] = field(default_factory=list)
    especializacoes: list[str] = field(default_factory=list)
    efeitos_habilidades_ativos: list[dict[str, str]] = field(default_factory=list)
    informacoes: list[dict[str, str]] = field(default_factory=list)
    itens: list[dict[str, str]] = field(default_factory=list)
    feiticos_favoritos: list[dict[str, str]] = field(default_factory=list)
    pocoes_favoritas: list[dict[str, str]] = field(default_factory=list)
    imagens: list[dict[str, str]] = field(default_factory=list)
    ordem_autoridade: int = 0
    sobre_narrativo: str = ""
    nota_10_autoridade: str = ""
    execucao_perfeita_autoridade: str = ""
    gratificacoes_autoridade: list[dict[str, str]] = field(default_factory=list)
    penalidades_autoridade: list[dict[str, str]] = field(default_factory=list)
    tipo_npc: str = ""
    especie_npc: str = ""
    faixa_tamanho_npc: str = ""
    anos_pos_vida: int = 0
    manifestacao_paranormal: int = 0
    armas_npc: list[dict[str, str]] = field(default_factory=list)
    ataques_npc: list[dict[str, str]] = field(default_factory=list)
    habilidades_npc: list[dict[str, str]] = field(default_factory=list)
    fraquezas_npc: list[dict[str, str]] = field(default_factory=list)
    resistencias_npc: list[dict[str, str]] = field(default_factory=list)

    def markdown(self) -> str:
        campos = [
            ("Tipo de ficha", self.grupo),
            ("Idade", self.idade),
            ("Altura", self.altura),
            ("Casa", self.casa),
            ("Herança Sanguínea", self.heranca),
            ("Núcleo de Varinha", self.nucleo),
            ("Ano", self.ano),
            ("Nível", str(self.nivel)),
            ("XP disponível", str(self.xp)),
            ("Familiar", self.familiar),
            ("Patronum", self.patronum),
            ("Pontos de Vida", str(self.pv)),
            ("Pontos de Habilidade", str(self.ph)),
            ("Alma", str(self.alma)),
            ("Classe Social", self.classe_social),
            ("Rolagem de Classe Social", str(self.rolagem_social)),
            ("Modificador de Classe Social", str(self.modificador_social)),
            ("Galeões", str(self.galeoes)),
            ("Pontos de Atributo disponíveis", str(self.pontos_atributo_disponiveis)),
            ("Atributos", _linhas_mapa(self.atributos, ATRIBUTOS)),
            ("Perícias", _linhas_mapa(self.pericias, PERICIAS)),
            ("Aptidões", _linhas_mapa(self.aptidoes, APTIDOES)),
            ("Evolução da Herança Sanguínea", str(self.evolucao_heranca)),
            ("Escolha da Experiência Alquímica", self.escolha_experiencia_alquimica or "--"),
            (
                "Bônus temporários de Atributo",
                _linhas_mapa(self.bonus_atributos_temporarios, ATRIBUTOS),
            ),
            (
                "Reduções de Dificuldade da Herança",
                _linhas_mapa(self.reducoes_dificuldade_heranca, REDUCOES_DIFICULDADE),
            ),
            ("Origens Mágicas", _linhas_lista(self.origens_magicas)),
            ("Especializações", _linhas_lista(self.especializacoes)),
            ("Efeitos de Habilidades Ativos", _linhas_registros(self.efeitos_habilidades_ativos)),
            ("Informações", _linhas_registros(self.informacoes)),
            ("Itens", _linhas_registros(self.itens)),
            ("Feitiços favoritos", _linhas_registros(self.feiticos_favoritos)),
            ("Imagens", _linhas_registros(self.imagens)),
        ]
        if self.tipo_npc:
            campos.extend(
                [
                    ("Tipo de NPC", self.tipo_npc),
                    ("Espécie do NPC", self.especie_npc or "--"),
                    ("Faixa de tamanho do NPC", self.faixa_tamanho_npc or "--"),
                    ("Anos no pós-vida", str(self.anos_pos_vida)),
                    ("Manifestação Paranormal", str(self.manifestacao_paranormal)),
                    ("Armas do NPC", _linhas_registros(self.armas_npc)),
                    ("Ataques do NPC", _linhas_registros(self.ataques_npc)),
                    ("Habilidades do NPC", _linhas_registros(self.habilidades_npc)),
                    ("Fraquezas do NPC", _linhas_registros(self.fraquezas_npc)),
                    ("Resistências do NPC", _linhas_registros(self.resistencias_npc)),
                ]
            )
        if self.grupo == "Figuras de Autoridade" or self.ordem_autoridade:
            campos.extend(
                [
                    ("Ordem da Autoridade", str(self.ordem_autoridade)),
                    ("Sobre Narrativo", self.sobre_narrativo or "--"),
                    ("Nota 10 da Autoridade", self.nota_10_autoridade or "--"),
                    (
                        "Execução Perfeita da Autoridade",
                        self.execucao_perfeita_autoridade or "--",
                    ),
                    (
                        "Gratificações da Autoridade",
                        _linhas_registros(self.gratificacoes_autoridade),
                    ),
                    (
                        "Penalidades da Autoridade",
                        _linhas_registros(self.penalidades_autoridade),
                    ),
                ]
            )
        metadados: list[tuple[str, str]] = []
        if self.titular_id:
            metadados.append(("Titular do Discord", str(self.titular_id)))
        if self.mensagem_discord_id:
            metadados.append(("Mensagem da Ficha no Discord", str(self.mensagem_discord_id)))
        if self.mensagem_discord_parte_2_id:
            metadados.append(
                ("Mensagem da Ficha Parte 2 no Discord", str(self.mensagem_discord_parte_2_id))
            )
        if self.mensagem_discord_parte_3_id:
            metadados.append(
                ("Mensagem da Ficha Parte 3 no Discord", str(self.mensagem_discord_parte_3_id))
            )
        if self.mensagem_narrativa_discord_id:
            metadados.append(
                ("Mensagem Narrativa no Discord", str(self.mensagem_narrativa_discord_id))
            )
        if self.mensagem_time_discord_id:
            metadados.append(("Mensagem do Time no Discord", str(self.mensagem_time_discord_id)))
        campos[1:1] = metadados
        partes = [f"# {self.nome}"]
        partes.extend(f"{rotulo}:\n{valor}" for rotulo, valor in campos)
        return "\n\n".join(partes).rstrip() + "\n"

    @classmethod
    def carregar(cls, caminho: Path) -> FichaPersonagem:
        entrada = interpretar_markdown(caminho.read_text(encoding="utf-8-sig"))
        campos = {
            normalizar_rotulo(rotulo): valor.strip()
            for rotulo, valor in entrada.campos.items()
        }
        atributos = {nome: 10 for nome in ATRIBUTOS}
        atributos.update(_mapa_inteiros(campos.get("atributos", "")))
        pericias = {nome: 0 for nome in PERICIAS}
        pericias.update(_mapa_inteiros(campos.get("pericias", "")))
        aptidoes = {nome: 0 for nome in APTIDOES}
        aptidoes.update(_mapa_inteiros(campos.get("aptidoes", "")))
        bonus_atributos_temporarios = {nome: 0 for nome in ATRIBUTOS}
        bonus_atributos_temporarios.update(
            {
                nome: valor
                for nome, valor in _mapa_inteiros(
                    campos.get("bonus temporarios de atributo", "")
                ).items()
                if nome in ATRIBUTOS and valor > 0
            }
        )
        reducoes_dificuldade_heranca = {
            nome: 0 for nome in REDUCOES_DIFICULDADE
        }
        reducoes_dificuldade_heranca.update(
            {
                nome: valor
                for nome, valor in _mapa_inteiros(
                    campos.get("reducoes de dificuldade da heranca", "")
                ).items()
                if nome in REDUCOES_DIFICULDADE and valor > 0
            }
        )
        ficha = cls(
            nome=entrada.titulo or caminho.stem,
            grupo=campos.get("tipo de ficha", caminho.parent.name),
            casa=campos.get("casa", "--"),
            heranca=campos.get("heranca sanguinea", "--"),
            nucleo=campos.get("nucleo de varinha", "--"),
            titular_id=_inteiro(campos, "Titular do Discord", 0),
            mensagem_discord_id=_inteiro(campos, "Mensagem da Ficha no Discord", 0),
            mensagem_discord_parte_2_id=_inteiro(
                campos, "Mensagem da Ficha Parte 2 no Discord", 0
            ),
            mensagem_discord_parte_3_id=_inteiro(
                campos, "Mensagem da Ficha Parte 3 no Discord", 0
            ),
            mensagem_narrativa_discord_id=_inteiro(
                campos, "Mensagem Narrativa no Discord", 0
            ),
            mensagem_time_discord_id=_inteiro(campos, "Mensagem do Time no Discord", 0),
            nivel=_inteiro(campos, "Nível", 1),
            xp=_inteiro(campos, "XP disponível", 0),
            alma=_inteiro(campos, "Alma", 100),
            pv=_inteiro(campos, "Pontos de Vida", 10),
            ph=_inteiro(campos, "Pontos de Habilidade", 5),
            idade=campos.get("idade", "--"),
            altura=campos.get("altura", "--"),
            ano=campos.get("ano", "--"),
            familiar=campos.get("familiar", "--"),
            patronum=campos.get("patronum", "--"),
            classe_social=campos.get("classe social", "Média"),
            rolagem_social=_inteiro(campos, "Rolagem de Classe Social", 1),
            modificador_social=_inteiro(campos, "Modificador de Classe Social", 0),
            galeoes=_inteiro(campos, "Galeões", 10),
            pontos_atributo_disponiveis=_inteiro(campos, "Pontos de Atributo disponíveis", 0),
            atributos=atributos,
            pericias=pericias,
            aptidoes=aptidoes,
            evolucao_heranca=_inteiro(campos, "Evolução da Herança Sanguínea", 0),
            escolha_experiencia_alquimica=(
                ""
                if campos.get("escolha da experiencia alquimica", "--") == "--"
                else campos.get("escolha da experiencia alquimica", "")
            ),
            bonus_atributos_temporarios=bonus_atributos_temporarios,
            reducoes_dificuldade_heranca=reducoes_dificuldade_heranca,
            origens_magicas=_lista(campos.get("origens magicas", "")),
            especializacoes=_lista(campos.get("especializacoes", "")),
            efeitos_habilidades_ativos=_registros(
                campos.get("efeitos de habilidades ativos", ""),
                ("nome", "efeito"),
                ("duracao",),
            ),
            informacoes=_registros(
                campos.get("informacoes", ""),
                ("titulo", "descricao"),
            ),
            itens=_registros_livres(campos.get("itens", "")),
            feiticos_favoritos=_registros(
                campos.get("feiticos favoritos", ""),
                ("nome", "categoria", "descricao"),
            ),
            pocoes_favoritas=_registros(
                campos.get("pocoes favoritas", ""),
                ("nome", "categoria", "descricao"),
            ),
            imagens=_registros_imagens(campos.get("imagens", "")),
            ordem_autoridade=_inteiro(campos, "Ordem da Autoridade", 0),
            sobre_narrativo=campos.get("sobre narrativo", "").strip().removeprefix("--"),
            nota_10_autoridade=campos.get("nota 10 da autoridade", "").strip().removeprefix("--"),
            execucao_perfeita_autoridade=campos.get(
                "execucao perfeita da autoridade", ""
            ).strip().removeprefix("--"),
            gratificacoes_autoridade=_registros(
                campos.get("gratificacoes da autoridade", ""),
                ("pontos", "motivo"),
            ),
            penalidades_autoridade=_registros(
                campos.get("penalidades da autoridade", ""),
                ("pontos", "motivo"),
            ),
            tipo_npc=campos.get("tipo de npc", "").strip().removeprefix("--"),
            especie_npc=campos.get("especie do npc", "").strip().removeprefix("--"),
            faixa_tamanho_npc=campos.get("faixa de tamanho do npc", "").strip().removeprefix("--"),
            anos_pos_vida=_inteiro(campos, "Anos no pós-vida", 0),
            manifestacao_paranormal=_inteiro(campos, "Manifestação Paranormal", 0),
            armas_npc=_registros_livres(campos.get("armas do npc", "")),
            ataques_npc=_registros_livres(campos.get("ataques do npc", "")),
            habilidades_npc=_registros_livres(campos.get("habilidades do npc", "")),
            fraquezas_npc=_registros_livres(campos.get("fraquezas do npc", "")),
            resistencias_npc=_registros_livres(campos.get("resistencias do npc", "")),
        )
        # Migração transparente: poções destacadas pelo modelo antigo passam a
        # integrar o inventário e deixam de ser uma seção paralela da ficha.
        nomes_itens = {
            (normalizar_rotulo(item.get("categoria", "")), normalizar_rotulo(item.get("nome", "")))
            for item in ficha.itens
        }
        for pocao in ficha.pocoes_favoritas:
            chave = (normalizar_rotulo("Poções"), normalizar_rotulo(pocao.get("nome", "")))
            if chave in nomes_itens:
                continue
            ficha.itens.append(
                {
                    "categoria": "Poções",
                    "nome": pocao.get("nome", "Poção"),
                    "quantidade": "1",
                    "unidade": "frasco",
                    "descricao": pocao.get("descricao", ""),
                }
            )
            nomes_itens.add(chave)
        ficha.pocoes_favoritas = []
        sincronizar_campos_base(ficha)
        return ficha


def _valor_informacao(ficha: FichaPersonagem, *titulos: str) -> str:
    procurados = {normalizar_rotulo(titulo) for titulo in titulos}
    for informacao in ficha.informacoes:
        if normalizar_rotulo(informacao.get("titulo", "")) in procurados:
            return informacao.get("descricao", "").strip()
    return ""


def _definir_informacao_base(
    ficha: FichaPersonagem,
    titulo: str,
    valor: str,
    *aliases: str,
) -> None:
    procurados = {normalizar_rotulo(titulo), *(normalizar_rotulo(alias) for alias in aliases)}
    correspondentes = [
        informacao
        for informacao in ficha.informacoes
        if normalizar_rotulo(informacao.get("titulo", "")) in procurados
    ]
    if correspondentes:
        principal = correspondentes[0]
        principal["titulo"] = titulo
        principal["descricao"] = valor
        ficha.informacoes = [
            informacao
            for informacao in ficha.informacoes
            if informacao is principal or informacao not in correspondentes[1:]
        ]
        return
    ficha.informacoes.append({"titulo": titulo, "descricao": valor})


def npc_nao_bruxo(ficha: FichaPersonagem) -> bool:
    return (
        ficha.grupo == "NPCs"
        and ficha.tipo_npc not in {"", "Bruxo(a)"}
    )


def titulos_informacoes_obrigatorias(ficha: FichaPersonagem) -> tuple[str, ...]:
    titulos = ["Altura e Idade"]
    if ficha.grupo in CASAS_HOGWARTS:
        titulos.insert(0, "Cursando")
    if not npc_nao_bruxo(ficha):
        titulos.extend(("Familiar", "Patrono"))
    return tuple(titulos)


def informacao_obrigatoria(ficha: FichaPersonagem, titulo: str) -> bool:
    procurado = normalizar_rotulo(titulo)
    return any(
        normalizar_rotulo(obrigatorio) == procurado
        for obrigatorio in titulos_informacoes_obrigatorias(ficha)
    )


def ordenar_informacoes_ficha(ficha: FichaPersonagem) -> None:
    """Mantém campos estruturais no começo e Sobre sempre depois deles."""
    prioridade = {
        normalizar_rotulo("Cursando"): 0,
        normalizar_rotulo("Altura e Idade"): 1,
    }
    ficha.informacoes = [
        informacao
        for _, informacao in sorted(
            enumerate(ficha.informacoes),
            key=lambda item: (
                10_000
                if normalizar_rotulo(item[1].get("titulo", ""))
                == normalizar_rotulo("Sobre")
                else prioridade.get(
                    normalizar_rotulo(item[1].get("titulo", "")),
                    item[0] + 2,
                ),
                item[0],
            ),
        )
    ]


def sincronizar_campos_base(ficha: FichaPersonagem) -> None:
    """Mantém os campos estruturais e a embed Informações usando a mesma fonte."""
    cursando_registrado = _valor_informacao(ficha, "Cursando")
    if normalizar_rotulo(cursando_registrado) in {"completo", "ensino completo"}:
        ficha.ano = "Ensino Completo"
        _definir_informacao_base(ficha, "Cursando", "Ensino Completo")
    cursando = _valor_informacao(ficha, "Cursando")
    if cursando not in {"", "--"}:
        ficha.ano = cursando
    if ficha.grupo in CASAS_HOGWARTS:
        _definir_informacao_base(ficha, "Cursando", ficha.ano or "--")

    altura_idade = _valor_informacao(ficha, "Altura e Idade")
    if not altura_idade:
        altura_idade = "--"
    _definir_informacao_base(ficha, "Altura e Idade", altura_idade)

    # Migra a antiga informação de vassoura para o inventário. O nome é
    # somente uma referência: os dados mecânicos continuam vindo do catálogo.
    vassoura = _valor_informacao(ficha, "Vassoura")
    if vassoura not in {"", "--"}:
        for item in ficha.itens:
            if (
                normalizar_rotulo(item.get("categoria", ""))
                == normalizar_rotulo("Variados")
                and normalizar_rotulo(item.get("tipo", ""))
                == normalizar_rotulo("Vassoura")
            ):
                item["equipada"] = "Não"
        existente = next(
            (
                item
                for item in ficha.itens
                if normalizar_rotulo(item.get("categoria", ""))
                == normalizar_rotulo("Variados")
                and normalizar_rotulo(item.get("tipo", ""))
                == normalizar_rotulo("Vassoura")
                and normalizar_rotulo(item.get("nome", ""))
                == normalizar_rotulo(vassoura)
            ),
            None,
        )
        if existente is None:
            ficha.itens.append(
                {
                    "categoria": "Variados",
                    "nome": vassoura,
                    "quantidade": "1",
                    "tipo": "Vassoura",
                    "equipada": "Sim",
                    "descricao": "Vassoura de Quadribol vinculada ao catálogo oficial.",
                }
            )
        else:
            existente["equipada"] = "Sim"
        ficha.informacoes = [
            informacao
            for informacao in ficha.informacoes
            if normalizar_rotulo(informacao.get("titulo", ""))
            != normalizar_rotulo("Vassoura")
        ]

    if npc_nao_bruxo(ficha):
        ficha.informacoes = [
            informacao
            for informacao in ficha.informacoes
            if not (
                normalizar_rotulo(informacao.get("titulo", ""))
                in {normalizar_rotulo("Familiar"), normalizar_rotulo("Patrono"), normalizar_rotulo("Patronum")}
                and informacao.get("descricao", "").strip() in {"", "--"}
            )
        ]
    else:
        familiar = _valor_informacao(ficha, "Familiar")
        if familiar not in {"", "--"}:
            ficha.familiar = familiar
        _definir_informacao_base(ficha, "Familiar", ficha.familiar or "--")

        patrono = _valor_informacao(ficha, "Patrono", "Patronum")
        if patrono not in {"", "--"}:
            ficha.patronum = patrono
        _definir_informacao_base(ficha, "Patrono", ficha.patronum or "--", "Patronum")

    ordenar_informacoes_ficha(ficha)


def sangue_puro_desbloqueado(ficha: FichaPersonagem, evolucao: int) -> bool:
    return (
        normalizar_rotulo(ficha.heranca) == normalizar_rotulo("Sangue Puro")
        and ficha.evolucao_heranca >= evolucao
    )


def atributos_efetivos(ficha: FichaPersonagem) -> dict[str, int]:
    return {
        nome: ficha.atributos.get(nome, 10)
        + max(0, ficha.bonus_atributos_temporarios.get(nome, 0))
        for nome in ATRIBUTOS
    }


@dataclass(frozen=True)
class ReferenciaFicha:
    nome: str
    grupo: str
    caminho: Path


def paginas_fichas_alfabeticas(
    referencias: Iterable[ReferenciaFicha],
) -> list[tuple[str, list[ReferenciaFicha]]]:
    itens = sorted(referencias, key=lambda item: item.nome.casefold())
    paginas: list[tuple[str, list[ReferenciaFicha]]] = []
    for grupo in GRUPOS_ALFABETICOS_FICHAS:
        agrupadas = [
            item
            for item in itens
            if (normalizar_rotulo(item.nome)[:1].upper() or "#") in grupo
        ]
        lotes = [
            agrupadas[indice:indice + 25]
            for indice in range(0, len(agrupadas), 25)
        ] or [[]]
        for indice, lote in enumerate(lotes):
            rotulo = (
                grupo
                if len(lotes) == 1
                else f"{grupo} — {indice + 1}/{len(lotes)}"
            )
            paginas.append((rotulo, lote))
    return paginas


def _nome_arquivo_canonico(nome: str) -> str:
    return re.sub(
        r"#U([0-9a-fA-F]{4})",
        lambda match: chr(int(match.group(1), 16)),
        nome,
    )


def listar_fichas(termo: str = "") -> list[ReferenciaFicha]:
    """Lista fichas válidas diretamente do disco, sem cache e sem duplicatas de nome quebrado."""
    fichas_por_chave: dict[tuple[str, str], ReferenciaFicha] = {}
    for grupo in GRUPOS_FICHA:
        pasta = PASTA_FICHAS / grupo
        if not pasta.is_dir():
            continue
        for arquivo in pasta.glob("*.md"):
            try:
                entrada = interpretar_markdown(
                    arquivo.read_text(encoding="utf-8-sig")
                )
                campos = {
                    normalizar_rotulo(rotulo): valor.strip()
                    for rotulo, valor in entrada.campos.items()
                }
            except (OSError, UnicodeError):
                continue

            tipo = campos.get(normalizar_rotulo("Tipo de ficha"), "")
            if normalizar_rotulo(tipo) != normalizar_rotulo(grupo):
                continue

            nome = entrada.titulo or _nome_arquivo_canonico(arquivo.stem)
            chave = (normalizar_rotulo(grupo), normalizar_rotulo(nome))
            referencia = ReferenciaFicha(nome, grupo, arquivo)
            existente = fichas_por_chave.get(chave)
            if existente is None:
                fichas_por_chave[chave] = referencia
                continue

            # Se houver a cópia correta e a cópia antiga com #Uxxxx, prefere a correta.
            existente_quebrado = "#U" in existente.caminho.name
            atual_quebrado = "#U" in arquivo.name
            if existente_quebrado and not atual_quebrado:
                fichas_por_chave[chave] = referencia

    fichas = sorted(
        fichas_por_chave.values(),
        key=lambda item: (item.nome.casefold(), item.grupo.casefold()),
    )
    termo_normalizado = normalizar_rotulo(termo)
    if not termo_normalizado:
        return fichas
    return [
        item for item in fichas
        if termo_normalizado in normalizar_rotulo(item.nome)
    ]

def encontrar_ficha(valor: str) -> ReferenciaFicha | None:
    valor_normalizado = normalizar_rotulo(valor)
    for ficha in listar_fichas():
        relativo = ficha.caminho.relative_to(PASTA_FICHAS).as_posix()
        if normalizar_rotulo(relativo) == valor_normalizado:
            return ficha
    correspondencias = [
        ficha for ficha in listar_fichas() if normalizar_rotulo(ficha.nome) == valor_normalizado
    ]
    return correspondencias[0] if len(correspondencias) == 1 else None


def caminho_nova_ficha(grupo: str, nome: str) -> Path:
    if grupo not in GRUPOS_FICHA:
        raise ValueError("Grupo de ficha inválido.")
    if not nome.strip() or any(caractere in nome for caractere in '<>:"/\\|?*\r\n'):
        raise ValueError("Nome de ficha inválido.")
    pasta = (PASTA_FICHAS / grupo).resolve()
    destino = (pasta / f"{nome.strip()}.md").resolve()
    destino.relative_to(PASTA_FICHAS.resolve())
    return destino


def salvar_ficha(ficha: FichaPersonagem, caminho: Path, *, nova: bool = False) -> None:
    sincronizar_campos_base(ficha)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if nova:
        with caminho.open("x", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write(ficha.markdown())
        return
    temporario = caminho.with_suffix(".md.tmp")
    temporario.write_text(ficha.markdown(), encoding="utf-8", newline="\n")
    temporario.replace(caminho)


def listar_casas() -> list[str]:
    if not PASTA_CASAS.is_dir():
        return []
    return sorted((arquivo.stem for arquivo in PASTA_CASAS.glob("*.md")), key=str.casefold)


def pericias_da_casa(casa: str) -> list[str]:
    arquivo = next(
        (item for item in PASTA_CASAS.glob("*.md") if normalizar_rotulo(item.stem) == normalizar_rotulo(casa)),
        None,
    )
    if arquivo is None:
        return []
    entrada = interpretar_markdown(arquivo.read_text(encoding="utf-8-sig"))
    campos = {normalizar_rotulo(k): v for k, v in entrada.campos.items()}
    return _lista(campos.get("pericias da casa", ""))


def listar_nucleos() -> list[str]:
    if not PASTA_NUCLEOS.is_dir():
        return []
    return sorted((arquivo.stem for arquivo in PASTA_NUCLEOS.glob("*.md")), key=str.casefold)


def dados_nucleo(nome: str) -> tuple[dict[str, int], int, int]:
    arquivo = next(
        (item for item in PASTA_NUCLEOS.glob("*.md") if normalizar_rotulo(item.stem) == normalizar_rotulo(nome)),
        None,
    )
    if arquivo is None:
        return {}, 0, 0
    entrada = interpretar_markdown(arquivo.read_text(encoding="utf-8-sig"))
    campos = {normalizar_rotulo(k): v.strip() for k, v in entrada.campos.items()}
    bonus = _mapa_inteiros(campos.get("bonus", ""))
    escolhas = _inteiro(campos, "Quantidade de escolhas", 0)
    bonus_escolha = _inteiro(campos, "Bônus por escolha", 0)
    return bonus, escolhas, bonus_escolha


def resumo_bonus_nucleo(nome: str) -> str:
    bonus, escolhas, bonus_escolha = dados_nucleo(nome)
    partes = [f"+{valor} em {aptidao}" for aptidao, valor in bonus.items()]
    if escolhas and bonus_escolha:
        substantivo = "aptidão mágica" if escolhas == 1 else "aptidões mágicas"
        partes.append(
            f"+{bonus_escolha} em {escolhas} {substantivo} à escolha"
        )
    return " • ".join(partes) or "Sem bônus cadastrado"
