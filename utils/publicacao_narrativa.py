from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import discord

from utils.biblioteca import interpretar_markdown, normalizar_rotulo
from utils.fichas import FichaPersonagem, PASTA_FICHAS, nome_com_estado_pv, salvar_ficha
from utils.midia import AnexoLocal, aplicar_imagem, referencia_imagem, resolver_anexo
from utils.publicacao_fichas import (
    ErroPublicacaoFicha,
    carregar_destinos_fichas,
    publicar_ou_atualizar_ficha,
)


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
ARQUIVO_CONFIGURACAO = RAIZ_PROJETO / "biblioteca" / "modelos" / "publicacao-narrativa.md"
ARQUIVO_FILA = RAIZ_PROJETO / "exports" / "publicacoes_narrativas" / "fila.json"
CASAS_HOGWARTS = ("Grifinória", "Sonserina", "Lufa-Lufa", "Corvinal")
GRUPOS_ALUNOS = (*CASAS_HOGWARTS, "Players")
GRUPOS_NARRATIVOS = (*GRUPOS_ALUNOS, "NPCs", "Figuras de Autoridade")
COR_NARRATIVA = 0x665544
COR_AUTORIDADE = 0xB6923C
COR_TIME = 0x7A5C1E


@dataclass(frozen=True)
class ConfiguracaoNarrativa:
    ativa: bool = False
    intervalo_minutos: int = 10


@dataclass
class EntradaNarrativa:
    tipo: str
    nome: str
    grupo: str
    caminho: Path
    destino_id: int | None
    conteudo: str
    embeds: list[discord.Embed] = field(default_factory=list)
    anexos: list[AnexoLocal] = field(default_factory=list)
    pendencias: list[str] = field(default_factory=list)

    @property
    def pronta(self) -> bool:
        return self.destino_id is not None and not self.pendencias and bool(self.embeds)

    def dados(self) -> dict[str, object]:
        return {
            "tipo": self.tipo,
            "nome": self.nome,
            "grupo": self.grupo,
            "arquivo": self.caminho.relative_to(RAIZ_PROJETO).as_posix(),
            "destino_id": self.destino_id,
            "conteudo": self.conteudo,
            "pronta": self.pronta,
            "pendencias": self.pendencias,
            "embeds": [embed.to_dict() for embed in self.embeds],
            "anexos": [
                {"arquivo": anexo.caminho.relative_to(RAIZ_PROJETO).as_posix(), "nome": anexo.nome}
                for anexo in self.anexos
            ],
        }


@dataclass(frozen=True)
class ResultadoSincronizacaoNarrativa:
    mensagem_narrativa_id: int
    mensagem_time_id: int
    pendencias: tuple[str, ...] = ()


def carregar_configuracao_narrativa() -> ConfiguracaoNarrativa:
    if not ARQUIVO_CONFIGURACAO.is_file():
        return ConfiguracaoNarrativa()
    entrada = interpretar_markdown(ARQUIVO_CONFIGURACAO.read_text(encoding="utf-8-sig"))
    campos = {normalizar_rotulo(k): v.strip() for k, v in entrada.campos.items()}
    ativa = normalizar_rotulo(campos.get("ativa", "nao")) in {"sim", "ativa", "true", "1"}
    try:
        intervalo = max(1, int(campos.get("intervalo em minutos", "10")))
    except ValueError:
        intervalo = 10
    return ConfiguracaoNarrativa(ativa=ativa, intervalo_minutos=intervalo)


def _destino(secao: str, chave: str) -> int | None:
    return carregar_destinos_fichas().get((normalizar_rotulo(secao), normalizar_rotulo(chave)))


def destino_narrativo_grupo(grupo: str, casa: str) -> int | None:
    if grupo == "Figuras de Autoridade":
        chave = "Figuras de Autoridade"
    elif grupo == "NPCs":
        chave = "NPCs Gerais"
    else:
        chave = casa if grupo == "Players" else grupo
    return _destino("Publicações Narrativas", chave)


def destino_narrativo(ficha: FichaPersonagem) -> int | None:
    return destino_narrativo_grupo(ficha.grupo, ficha.casa)


def destino_time(casa: str) -> int | None:
    return _destino("Times de Quadribol", casa)


def _informacao(ficha: FichaPersonagem, titulo: str) -> str:
    procurado = normalizar_rotulo(titulo)
    for item in ficha.informacoes:
        if normalizar_rotulo(item.get("titulo", "")) == procurado:
            valor = item.get("descricao", "").strip()
            return "" if valor == "--" else valor
    return ""


def _imagem(ficha: FichaPersonagem) -> str:
    for item in ficha.imagens:
        referencia = referencia_imagem(item)
        if referencia and referencia != "--":
            return referencia
    return ""


def _cabecalho(nome: str, subtitulo: str, emoji: str = "👤") -> str:
    return (
        f"## ══════◄••{emoji}••►══════\n"
        f"## {nome}\n"
        f"_{subtitulo}_\n"
        f"## ══════◄••{emoji}••►══════"
    )


def _adicionar_imagem_ou_pendencia(
    embed: discord.Embed,
    ficha: FichaPersonagem,
    pendencias: list[str],
    anexos: list[AnexoLocal],
) -> None:
    imagem = _imagem(ficha)
    if imagem:
        anexo = aplicar_imagem(embed, imagem, f"aparencia-{ficha.nome}")
        if anexo is not None:
            anexos.append(anexo)
    else:
        pendencias.append("imagem do personagem")


def montar_entrada_aluno(ficha: FichaPersonagem, caminho: Path) -> EntradaNarrativa:
    pendencias: list[str] = []
    anexos: list[AnexoLocal] = []
    altura_idade = _informacao(ficha, "Altura e Idade")
    if not altura_idade and ficha.altura != "--" and ficha.idade != "--":
        altura_idade = f"{ficha.altura} com {ficha.idade} Anos"
    cursando = _informacao(ficha, "Cursando")
    if not cursando and ficha.ano != "--":
        cursando = ficha.ano
    if not altura_idade:
        pendencias.append("Altura e Idade")
    if ficha.grupo in CASAS_HOGWARTS and not cursando:
        pendencias.append("Cursando")
    nome_exibicao = nome_com_estado_pv(ficha.nome, ficha.pv)
    embed = discord.Embed(title=nome_exibicao, color=COR_NARRATIVA)
    _adicionar_imagem_ou_pendencia(embed, ficha, pendencias, anexos)
    if ficha.grupo in CASAS_HOGWARTS or cursando:
        embed.add_field(name="Cursando", value=cursando or "--", inline=True)
    embed.add_field(name="Altura e Idade", value=altura_idade or "--", inline=True)
    casa = ficha.casa if ficha.grupo == "Players" else ficha.grupo
    destino = destino_narrativo(ficha)
    if destino is None:
        pendencias.append(f"thread narrativa da {casa}")
    return EntradaNarrativa(
        tipo="aluno",
        nome=ficha.nome,
        grupo=casa,
        caminho=caminho,
        destino_id=destino,
        conteudo=_cabecalho(nome_exibicao, f"Aluno • {casa}"),
        embeds=[embed],
        anexos=anexos,
        pendencias=pendencias,
    )


def montar_entrada_autoridade(ficha: FichaPersonagem, caminho: Path) -> EntradaNarrativa:
    pendencias: list[str] = []
    anexos: list[AnexoLocal] = []
    nome_exibicao = nome_com_estado_pv(ficha.nome, ficha.pv)
    embed = discord.Embed(title=nome_exibicao, color=COR_AUTORIDADE)
    _adicionar_imagem_ou_pendencia(embed, ficha, pendencias, anexos)
    altura_idade = _informacao(ficha, "Altura e Idade")
    if not altura_idade:
        pendencias.append("Altura e Idade")
    embed.add_field(name="Altura e Idade", value=altura_idade or "--", inline=False)
    for titulo in ("Cargo", "Valores", "Personalidade"):
        valor = _informacao(ficha, titulo)
        if not valor:
            pendencias.append(titulo)
        embed.add_field(name=titulo, value=valor or "--", inline=False)
    sobre = ficha.sobre_narrativo.strip() or _informacao(ficha, "Sobre")
    if sobre:
        embed_sobre = discord.Embed(title="Sobre", description=sobre, color=COR_AUTORIDADE)
        embeds = [embed, embed_sobre]
    else:
        embeds = [embed]
    return EntradaNarrativa(
        tipo="autoridade",
        nome=ficha.nome,
        grupo=ficha.grupo,
        caminho=caminho,
        destino_id=destino_narrativo(ficha),
        conteudo=_cabecalho(nome_exibicao, "Figura de Autoridade", "📚"),
        embeds=embeds,
        anexos=anexos,
        pendencias=pendencias,
    )


def montar_entrada_npc(ficha: FichaPersonagem, caminho: Path) -> EntradaNarrativa:
    pendencias: list[str] = []
    anexos: list[AnexoLocal] = []
    nome_exibicao = nome_com_estado_pv(ficha.nome, ficha.pv)
    embed = discord.Embed(title=nome_exibicao, color=COR_NARRATIVA)
    _adicionar_imagem_ou_pendencia(embed, ficha, pendencias, anexos)
    altura_idade = _informacao(ficha, "Altura e Idade")
    if not altura_idade:
        pendencias.append("Altura e Idade")
    embed.add_field(name="Altura e Idade", value=altura_idade or "--", inline=False)
    sobre = _informacao(ficha, "Sobre")
    if sobre:
        embeds = [embed, discord.Embed(title="Sobre", description=sobre, color=COR_NARRATIVA)]
    else:
        embeds = [embed]
    return EntradaNarrativa(
        tipo="npc",
        nome=ficha.nome,
        grupo=ficha.grupo,
        caminho=caminho,
        destino_id=destino_narrativo(ficha),
        conteudo=_cabecalho(nome_exibicao, "NPC"),
        embeds=embeds,
        anexos=anexos,
        pendencias=pendencias,
    )


def montar_entrada_time(ficha: FichaPersonagem, caminho: Path) -> EntradaNarrativa | None:
    posicao = _informacao(ficha, "Jogador de Quadribol")
    if not posicao:
        return None
    situacao = _informacao(ficha, "Situação no time")
    from utils.quadribol import obter_vassoura_ficha

    nome_vassoura = obter_vassoura_ficha(ficha)
    pendencias: list[str] = []
    if not situacao:
        pendencias.append("Situação no time")
    if not nome_vassoura:
        pendencias.append("Vassoura")
    imagem_jogador = _imagem(ficha)
    if not imagem_jogador:
        pendencias.append("foto do jogador")
    embeds: list[discord.Embed] = []
    anexos: list[AnexoLocal] = []
    if nome_vassoura:
        from utils.quadribol import encontrar_vassoura, modelo_vassoura_da_descricao

        vassoura = encontrar_vassoura(modelo_vassoura_da_descricao(nome_vassoura))
        if vassoura is None:
            pendencias.append(f"cadastro da vassoura {nome_vassoura}")
        else:
            if not vassoura.imagem_url:
                pendencias.append(f"foto da vassoura {vassoura.nome}")
            if situacao:
                from comandos.quadribol import embed_jogador_time

                jogador = embed_jogador_time(ficha, posicao, situacao, vassoura)
                if imagem_jogador:
                    anexo = aplicar_imagem(jogador, imagem_jogador, f"jogador-{ficha.nome}")
                    if anexo is not None:
                        anexos.append(anexo)
                embeds.append(jogador)
                vassoura_embed = discord.Embed(title=f"🧹 {vassoura.nome}", color=COR_TIME)
                if vassoura.imagem_url:
                    anexo = aplicar_imagem(
                        vassoura_embed, vassoura.imagem_url, f"vassoura-{vassoura.nome}"
                    )
                    if anexo is not None:
                        anexos.append(anexo)
                embeds.append(vassoura_embed)
    destino = destino_time(ficha.casa)
    if destino is None:
        pendencias.append(f"thread do time da {ficha.casa}")
    nome_exibicao = nome_com_estado_pv(ficha.nome, ficha.pv)
    return EntradaNarrativa(
        tipo="time",
        nome=ficha.nome,
        grupo=ficha.casa,
        caminho=caminho,
        destino_id=destino,
        conteudo=_cabecalho(nome_exibicao, f"Equipe da {ficha.casa}", "🏆"),
        embeds=embeds,
        anexos=anexos,
        pendencias=pendencias,
    )


def montar_entradas_ficha(ficha: FichaPersonagem, caminho: Path) -> list[EntradaNarrativa]:
    if ficha.grupo == "Figuras de Autoridade":
        entradas = [montar_entrada_autoridade(ficha, caminho)]
    elif ficha.grupo == "NPCs":
        entradas = [montar_entrada_npc(ficha, caminho)]
    elif ficha.grupo in GRUPOS_ALUNOS:
        entradas = [montar_entrada_aluno(ficha, caminho)]
    else:
        return []
    if ficha.grupo in GRUPOS_ALUNOS:
        time = montar_entrada_time(ficha, caminho)
        if time is not None:
            entradas.append(time)
    return entradas


def preparar_fila_narrativa(destino: Path = ARQUIVO_FILA) -> dict[str, object]:
    entradas: list[EntradaNarrativa] = []
    for grupo in GRUPOS_NARRATIVOS:
        pasta = PASTA_FICHAS / grupo
        if not pasta.is_dir():
            continue
        for caminho in sorted(pasta.glob("*.md"), key=lambda p: normalizar_rotulo(p.stem)):
            ficha = FichaPersonagem.carregar(caminho)
            entradas.extend(montar_entradas_ficha(ficha, caminho))
    configuracao = carregar_configuracao_narrativa()
    dados: dict[str, object] = {
        "publicacao_ativa": configuracao.ativa,
        "intervalo_minutos": configuracao.intervalo_minutos,
        "aviso": "Esta fila não publica nada sozinha. Requer autorização explícita.",
        "quantidade": len(entradas),
        "prontas": sum(entrada.pronta for entrada in entradas),
        "pendentes": sum(not entrada.pronta for entrada in entradas),
        "entradas": [entrada.dados() for entrada in entradas],
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dados


async def publicar_fila_narrativa(cliente: discord.Client) -> tuple[int, int]:
    """Publica a fila pronta respeitando o intervalo; nunca é chamada automaticamente."""
    configuracao = carregar_configuracao_narrativa()
    if not configuracao.ativa:
        raise ErroPublicacaoFicha(
            "A publicação narrativa está bloqueada. Ative-a somente após autorização explícita."
        )
    entradas: list[EntradaNarrativa] = []
    for grupo in GRUPOS_NARRATIVOS:
        pasta = PASTA_FICHAS / grupo
        if not pasta.is_dir():
            continue
        for caminho in sorted(pasta.glob("*.md"), key=lambda p: normalizar_rotulo(p.stem)):
            ficha = FichaPersonagem.carregar(caminho)
            entradas.extend(entrada for entrada in montar_entradas_ficha(ficha, caminho) if entrada.pronta)
    publicadas = 0
    for indice, entrada in enumerate(entradas):
        ficha = FichaPersonagem.carregar(entrada.caminho)
        mensagem_id = (
            ficha.mensagem_time_discord_id
            if entrada.tipo == "time"
            else ficha.mensagem_narrativa_discord_id
        )
        mensagem = await publicar_ou_atualizar_ficha(
            cliente,
            entrada.destino_id or 0,
            entrada.embeds,
            mensagem_id,
            entrada.conteudo,
            anexos=entrada.anexos,
        )
        if entrada.tipo == "time":
            ficha.mensagem_time_discord_id = mensagem.id
        else:
            ficha.mensagem_narrativa_discord_id = mensagem.id
        salvar_ficha(ficha, entrada.caminho)
        publicadas += 1
        if indice < len(entradas) - 1:
            await asyncio.sleep(configuracao.intervalo_minutos * 60)
    return publicadas, len(entradas)


async def sincronizar_publicacoes_narrativas(
    cliente: discord.Client,
    ficha: FichaPersonagem,
    caminho: Path,
) -> ResultadoSincronizacaoNarrativa:
    configuracao = carregar_configuracao_narrativa()
    if not configuracao.ativa:
        return ResultadoSincronizacaoNarrativa(
            ficha.mensagem_narrativa_discord_id,
            ficha.mensagem_time_discord_id,
        )
    mensagem_narrativa_id = ficha.mensagem_narrativa_discord_id
    mensagem_time_id = ficha.mensagem_time_discord_id
    pendencias: list[str] = []
    for entrada in montar_entradas_ficha(ficha, caminho):
        if not entrada.pronta:
            pendencias.extend(f"{entrada.tipo}: {item}" for item in entrada.pendencias)
            continue
        identificador_atual = mensagem_time_id if entrada.tipo == "time" else mensagem_narrativa_id
        mensagem = await publicar_ou_atualizar_ficha(
            cliente,
            entrada.destino_id or 0,
            entrada.embeds,
            identificador_atual,
            entrada.conteudo,
            anexos=entrada.anexos,
        )
        if entrada.tipo == "time":
            mensagem_time_id = mensagem.id
        else:
            mensagem_narrativa_id = mensagem.id
    return ResultadoSincronizacaoNarrativa(
        mensagem_narrativa_id,
        mensagem_time_id,
        tuple(pendencias),
    )
