from __future__ import annotations

import json
import re
import shutil
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from comandos.executar import criar_embeds_entrada
from utils.biblioteca import interpretar_markdown
from utils.feiticos_combate import (
    ACUMULOS,
    ALCANCES,
    ALVOS,
    ATIVACOES,
    MIRAS,
    MOMENTOS_CONTRA_FEITICO,
    MOMENTOS_DEFESA,
    RESPOSTAS,
    TIPOS_ACAO,
    TIPOS_EFEITO,
    UNIDADES_DURACAO,
    contra_feiticos_de,
    descricao_publica,
    extrair_perfil,
    linha_duracao,
    limpar_mecanicas_legadas,
    normalizar_perfil,
    pendencias,
    perfil_vazio,
    salvar_revisao,
)
from utils.publicacao_fichas import (
    ErroPublicacaoFicha,
    carregar_destinos_fichas,
    publicar_ou_atualizar_ficha,
)
from utils.biblioteca import normalizar_rotulo


PASTA_FEITICOS = Path("biblioteca") / "feitiços"
PASTA_CONTROLE = Path("biblioteca") / "combates"
ARQUIVO_RASCUNHOS = PASTA_CONTROLE / "revisao-feiticos-rascunhos.json"
PASTA_BACKUPS = PASTA_CONTROLE / "backups" / "revisao-feiticos"
COR_REVISAO = 0x3B82F6
TEMPO_FLUXO = 30 * 60
LIMITE_SELETOR = 25


def arquivos_categoria(categoria: str) -> list[Path]:
    pasta = PASTA_FEITICOS / categoria
    return sorted(pasta.rglob("*.md"), key=lambda item: item.stem.casefold())


def classificacao_revisao(arquivo: Path) -> tuple[str, str]:
    try:
        entrada = interpretar_markdown(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "Classificação", "Sem classificação"
    informado = entrada.campos.get("Ano de desbloqueio", "").strip()
    correspondencia = re.search(r"\b([1-7])\s*[º°]?\s*Ano\b", informado, re.IGNORECASE)
    if correspondencia:
        return "Ano", f"{correspondencia.group(1)}º Ano"
    if informado:
        return "Ano", informado
    vertente = entrada.campos.get("Vertente", "").strip()
    if vertente:
        return "Vertente", vertente
    return "Classificação", "Sem classificação"


def grupos_revisao(arquivos: list[Path]) -> list[tuple[str, str, list[Path]]]:
    grupos: dict[tuple[str, str], list[Path]] = {}
    for arquivo in arquivos:
        grupos.setdefault(classificacao_revisao(arquivo), []).append(arquivo)

    def ordem(item: tuple[tuple[str, str], list[Path]]) -> tuple[int, str]:
        tipo, rotulo = item[0]
        correspondencia = re.fullmatch(r"([1-7])º Ano", rotulo)
        return (
            int(correspondencia.group(1)) if correspondencia else 99,
            f"{tipo} {rotulo}".casefold(),
        )

    return [
        (tipo, rotulo, fichas)
        for (tipo, rotulo), fichas in sorted(grupos.items(), key=ordem)
    ]


def revisao_concluida(arquivo: Path) -> bool:
    try:
        perfil = extrair_perfil(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return bool(
        perfil
        and perfil.get("estado") == "completa"
        and not pendencias(perfil)
    )


def proxima_ficha_pendente(sessao: SessaoFeitico) -> Path | None:
    grupos = grupos_revisao(arquivos_categoria(sessao.categoria))
    if not grupos:
        return None

    chave_atual = classificacao_revisao(sessao.arquivo)
    indice_grupo = next(
        (indice for indice, (tipo, rotulo, _) in enumerate(grupos) if (tipo, rotulo) == chave_atual),
        0,
    )
    grupos_ordenados = grupos[indice_grupo:] + grupos[:indice_grupo]

    for indice, (tipo, rotulo, arquivos) in enumerate(grupos_ordenados):
        candidatos = arquivos
        if indice == 0 and (tipo, rotulo) == chave_atual:
            try:
                indice_atual = arquivos.index(sessao.arquivo)
            except ValueError:
                indice_atual = -1
            if indice_atual >= 0:
                candidatos = arquivos[indice_atual + 1 :] + arquivos[:indice_atual]

        for arquivo in candidatos:
            if arquivo != sessao.arquivo and not revisao_concluida(arquivo):
                return arquivo
    return None


def _ler_json(caminho: Path) -> dict[str, Any]:
    if not caminho.exists():
        return {}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _salvar_json(caminho: Path, dados: dict[str, Any]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporario.replace(caminho)


def chave_arquivo(caminho: Path) -> str:
    return caminho.resolve().relative_to(PASTA_FEITICOS.resolve()).as_posix()


@dataclass
class SessaoFeitico:
    arquivo: Path
    categoria: str
    perfil: dict[str, Any]
    descricao: str

    @classmethod
    def carregar(cls, arquivo: Path, categoria: str) -> "SessaoFeitico":
        conteudo = arquivo.read_text(encoding="utf-8")
        entrada = interpretar_markdown(conteudo)
        rascunhos = _ler_json(ARQUIVO_RASCUNHOS)
        rascunho = rascunhos.get(chave_arquivo(arquivo), {})
        perfil = normalizar_perfil(
            rascunho.get("perfil") if isinstance(rascunho, dict) else None
        )
        if not rascunho:
            perfil = normalizar_perfil(extrair_perfil(conteudo) or perfil_vazio())
        descricao = (
            str(rascunho.get("descricao", ""))
            if isinstance(rascunho, dict) and rascunho.get("descricao")
            else limpar_mecanicas_legadas(entrada.descricao)
        )
        return cls(arquivo, categoria, perfil, descricao)

    def salvar_rascunho(self) -> None:
        dados = _ler_json(ARQUIVO_RASCUNHOS)
        dados[chave_arquivo(self.arquivo)] = {
            "perfil": self.perfil,
            "descricao": self.descricao,
        }
        _salvar_json(ARQUIVO_RASCUNHOS, dados)

    def remover_rascunho(self) -> None:
        dados = _ler_json(ARQUIVO_RASCUNHOS)
        dados.pop(chave_arquivo(self.arquivo), None)
        _salvar_json(ARQUIVO_RASCUNHOS, dados)


def criar_backup(sessao: SessaoFeitico) -> None:
    destino = PASTA_BACKUPS / chave_arquivo(sessao.arquivo)
    if destino.exists():
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sessao.arquivo, destino)


def destino_revisao(sessao: SessaoFeitico) -> tuple[int | None, str]:
    """Resolve a thread oficial correspondente à ficha revisada."""
    tipo, chave = classificacao_revisao(sessao.arquivo)
    secao = sessao.categoria
    if secao.casefold() == "dcat":
        secao = "Defesa Contra Arte das Trevas"
    if secao.casefold() == "trevas":
        secao = "Arte das Trevas"
    if tipo.casefold() == "ano":
        chave = chave
    destinos = carregar_destinos_fichas()
    return destinos.get((normalizar_rotulo(secao), normalizar_rotulo(chave))), secao


async def sincronizar_publicacao_feitico(
    cliente, sessao: SessaoFeitico, *, criar_se_ausente: bool = True
) -> bool:
    """Atualiza a publicação existente da ficha, ou cria-a se ainda não existir."""
    thread_id, _ = destino_revisao(sessao)
    if thread_id is None:
        return False
    entrada = interpretar_markdown(sessao.arquivo.read_text(encoding="utf-8"))
    entrada.descricao = sessao.descricao
    entrada.perfil_combate = normalizar_perfil(sessao.perfil)
    embeds = criar_embeds_entrada(entrada, "feitico", sessao.arquivo.stem)
    canal = cliente.get_channel(thread_id) or await cliente.fetch_channel(thread_id)
    estava_arquivada = bool(getattr(canal, "archived", False))
    if estava_arquivada and hasattr(canal, "edit"):
        await canal.edit(archived=False)
    try:
        mensagem_id = 0
        if hasattr(canal, "history"):
            async for mensagem in canal.history(limit=None):
                titulo = mensagem.embeds[0].title if mensagem.embeds else ""
                if (titulo or "").casefold() == sessao.arquivo.stem.casefold() or sessao.arquivo.stem.casefold() in (mensagem.content or "").casefold():
                    mensagem_id = mensagem.id
                    break
        if not mensagem_id and not criar_se_ausente:
            return False
        await publicar_ou_atualizar_ficha(
            cliente, thread_id, embeds[:10], mensagem_id=mensagem_id,
            conteudo="", anexos=(),
        )
    finally:
        if estava_arquivada and hasattr(canal, "edit"):
            await canal.edit(archived=True)
    return True


async def sincronizar_feiticos_completos(cliente) -> list[str]:
    """Sincroniza todas as fichas já marcadas como completas."""
    atualizados: list[str] = []
    for categoria in (item.name for item in PASTA_FEITICOS.iterdir() if item.is_dir()):
        for arquivo in arquivos_categoria(categoria):
            try:
                conteudo = arquivo.read_text(encoding="utf-8")
                perfil = extrair_perfil(conteudo)
                if not perfil or perfil.get("estado") != "completa":
                    continue
                entrada = interpretar_markdown(conteudo)
                sessao = SessaoFeitico(
                    arquivo, categoria, perfil,
                    limpar_mecanicas_legadas(entrada.descricao),
                )
                if await sincronizar_publicacao_feitico(
                    cliente, sessao, criar_se_ausente=False
                ):
                    atualizados.append(arquivo.stem)
            except (OSError, ValueError, json.JSONDecodeError, discord.HTTPException, ErroPublicacaoFicha):
                continue
    return atualizados


def reconciliar_vinculos_contrafeitico() -> int:
    """Unifica relações antigas e grava os dois lados do vínculo."""
    perfis: dict[str, tuple[Path, dict[str, Any], str, str]] = {}
    for arquivo in PASTA_FEITICOS.rglob("*.md"):
        try:
            conteudo = arquivo.read_text(encoding="utf-8")
            perfil = extrair_perfil(conteudo)
            if not perfil:
                continue
            entrada = interpretar_markdown(conteudo)
            perfis[arquivo.stem.casefold()] = (
                arquivo,
                perfil,
                arquivo.stem,
                limpar_mecanicas_legadas(entrada.descricao),
            )
        except (OSError, ValueError, json.JSONDecodeError):
            continue

    relacoes: set[tuple[str, str]] = set()
    for chave, (_, perfil, nome, _) in perfis.items():
        for contra_nome in _nomes_contramagia(perfil, "propria"):
            contra = perfis.get(contra_nome.casefold())
            if contra:
                relacoes.add((chave, contra[2].casefold()))
        for alvo_nome in _nomes_contramagia(perfil, "alvos"):
            alvo = perfis.get(alvo_nome.casefold())
            if alvo:
                relacoes.add((alvo_nome.casefold(), chave))

    atualizados = 0
    for chave, (arquivo, perfil, nome, descricao) in perfis.items():
        contras = sorted(
            (perfis[contra][2] for alvo, contra in relacoes if alvo == chave),
            key=str.casefold,
        )
        alvos = sorted(
            (perfis[alvo][2] for alvo, contra in relacoes if contra == chave),
            key=str.casefold,
        )
        contra = perfil.setdefault("contra_feitico", {})
        tipos = perfil.setdefault("tipos", [])
        tipo_auto = bool(contra.get("tipo_automatico"))
        if (
            perfil.get("contramagia", []) == contras
            and contra.get("feiticos", []) == alvos
            and (not alvos or "Contra-feitiço" in tipos)
            and (alvos or not tipo_auto)
        ):
            continue
        entrada = SessaoFeitico(
            arquivo, arquivo.relative_to(PASTA_FEITICOS).parts[0], perfil, descricao
        )
        criar_backup(entrada)
        perfil["contramagia"] = contras
        contra["feiticos"] = alvos
        if alvos:
            contra["habilitado"] = True
            if "Contra-feitiço" not in tipos:
                tipos.append("Contra-feitiço")
                contra["tipo_automatico"] = True
        elif tipo_auto:
            perfil["tipos"] = [tipo for tipo in tipos if tipo != "Contra-feitiço"]
            contra["tipo_automatico"] = False
            contra["habilitado"] = False
            contra["momento"] = ""
        elif "Contra-feitiço" not in tipos:
            contra["habilitado"] = False
            contra["momento"] = ""
        perfil = normalizar_perfil(perfil)
        salvar_revisao(arquivo, perfil, descricao)
        atualizados += 1
    return atualizados


async def sincronizar_vinculos_contrafeitico(
    cliente, sessao_atual: SessaoFeitico, perfil_anterior: dict[str, Any]
) -> None:
    """Mantém sincronizados os dois lados do vínculo entre contra-feitiços."""
    anterior = normalizar_perfil(perfil_anterior)
    atual = normalizar_perfil(sessao_atual.perfil)
    contra_anterior = set(_nomes_contramagia(anterior, "propria"))
    contra_atual = set(_nomes_contramagia(atual, "propria"))
    contra_atual_normalizados = {nome.casefold() for nome in contra_atual}
    alvos_anteriores = set(_nomes_contramagia(anterior, "alvos"))
    alvos_atuais = set(_nomes_contramagia(atual, "alvos"))
    alvos_atuais_normalizados = {nome.casefold() for nome in alvos_atuais}
    nome_atual = sessao_atual.arquivo.stem

    arquivos_por_nome = {
        arquivo.stem.casefold(): arquivo for arquivo in PASTA_FEITICOS.rglob("*.md")
    }

    async def atualizar_perfil_relacionado(arquivo: Path, alterar) -> None:
        try:
            conteudo = arquivo.read_text(encoding="utf-8")
            perfil = extrair_perfil(conteudo)
            if not perfil:
                return
            entrada = interpretar_markdown(conteudo)
            categoria = arquivo.relative_to(PASTA_FEITICOS).parts[0]
            sessao = SessaoFeitico(
                arquivo, categoria, perfil, limpar_mecanicas_legadas(entrada.descricao)
            )
            if not alterar(perfil):
                return
            criar_backup(sessao)
            salvar_revisao(arquivo, perfil, sessao.descricao)
            if perfil.get("estado") == "completa":
                sessao.perfil = perfil
                await sincronizar_publicacao_feitico(
                    cliente, sessao, criar_se_ausente=False
                )
        except (OSError, ValueError, json.JSONDecodeError, discord.HTTPException, ErroPublicacaoFicha):
            return

    # Alterar a lista de contra-feitiços deste feitiço atualiza os feitiços
    # escolhidos: eles passam a registrar que anulam este feitiço.
    if contra_anterior != contra_atual:
        for nome in contra_anterior | contra_atual:
            arquivo = arquivos_por_nome.get(nome.casefold())
            if not arquivo or arquivo.resolve() == sessao_atual.arquivo.resolve():
                continue

            def atualizar_alvos(perfil, nome=nome):
                contra = perfil.setdefault("contra_feitico", {})
                existentes = _nomes_contramagia(perfil, "alvos")
                atualizados = [item for item in existentes if item.casefold() != nome_atual.casefold()]
                if nome.casefold() in contra_atual_normalizados:
                    atualizados.append(nome_atual)
                atualizados = list(dict.fromkeys(atualizados))
                if atualizados == existentes:
                    return False
                contra["feiticos"] = atualizados
                tipos = perfil.setdefault("tipos", [])
                if atualizados and "Contra-feitiço" not in tipos:
                    tipos.append("Contra-feitiço")
                    contra["tipo_automatico"] = True
                elif not atualizados and contra.get("tipo_automatico"):
                    perfil["tipos"] = [tipo for tipo in tipos if tipo != "Contra-feitiço"]
                    contra["tipo_automatico"] = False
                contra["habilitado"] = bool(atualizados) or "Contra-feitiço" in perfil.get("tipos", [])
                if not contra["habilitado"]:
                    contra["momento"] = ""
                return True

            await atualizar_perfil_relacionado(arquivo, atualizar_alvos)

    # Alterar a lista de feitiços anulados por este atualiza, por sua vez,
    # a lista de contra-feitiços dos feitiços escolhidos.
    if alvos_anteriores != alvos_atuais:
        for nome in alvos_anteriores | alvos_atuais:
            arquivo = arquivos_por_nome.get(nome.casefold())
            if not arquivo or arquivo.resolve() == sessao_atual.arquivo.resolve():
                continue

            def atualizar_contramagia(perfil):
                existentes = _nomes_contramagia(perfil, "propria")
                atualizados = [item for item in existentes if item.casefold() != nome_atual.casefold()]
                if nome.casefold() in alvos_atuais_normalizados:
                    atualizados.append(nome_atual)
                atualizados = list(dict.fromkeys(atualizados))
                if atualizados == existentes:
                    return False
                perfil["contramagia"] = atualizados
                perfil["respostas"] = [
                    item for item in perfil.get("respostas", [])
                    if item != "Contra-feitiço" or atualizados
                ]
                perfil.update(normalizar_perfil(perfil))
                return True

            await atualizar_perfil_relacionado(arquivo, atualizar_contramagia)


def embed_painel(titulo: str, descricao: str = "") -> discord.Embed:
    return discord.Embed(title=titulo, description=descricao, color=COR_REVISAO)


def resumo_perfil(sessao: SessaoFeitico) -> discord.Embed:
    perfil = normalizar_perfil(sessao.perfil)
    faltas = pendencias(perfil)
    duracao = perfil.get("duracao", {})
    texto_duracao = linha_duracao(perfil) or "--"
    for prefixo in ("Duração: ",):
        if texto_duracao.startswith(prefixo):
            texto_duracao = texto_duracao[len(prefixo):]
            break
    embed = embed_painel(
        f"Revisão — {sessao.arquivo.stem}",
        (sessao.descricao[:1200] + ("…" if len(sessao.descricao) > 1200 else "")) or "--",
    )
    embed.add_field(
        name="Base",
        value=(
            f"Mira: **{perfil.get('mira') or '--'}**\n"
            f"Ação: **{perfil.get('tipo_acao') or '--'}**\n"
            f"Ativação: **{perfil.get('ativacao') or '--'}**"
        ),
        inline=True,
    )
    embed.add_field(
        name="Duração e tipos",
        value=(
            f"Duração: **{texto_duracao}**\n"
            f"Tipos: **{', '.join(perfil.get('tipos', [])) or '--'}**"
        ),
        inline=True,
    )
    alvo = perfil.get("alvo") or "--"
    detalhe_alvo = (
        perfil.get("area", "")
        if alvo == "Área"
        else perfil.get("detalhes_alvo", "")
    )
    embed.add_field(
        name="Alcance e alvo",
        value=(
            f"Alcance: **{perfil.get('alcance') or '--'}**"
            + (f" — {perfil.get('detalhes_alcance')}" if perfil.get("detalhes_alcance") else "")
            + f"\nAlvo: **{alvo}**"
            + (f" — {detalhe_alvo}" if detalhe_alvo else "")
        ),
        inline=False,
    )
    embed.add_field(
        name="Regras universais",
        value=(
            f"Resposta: **{', '.join(perfil.get('respostas', [])) or '--'}**\n"
            f"Acúmulo: **{perfil.get('acumulo') or '--'}**\n"
            f"Encerramento: **{perfil.get('encerramento') or '--'}**\n"
            f"Contra-feitiços deste feitiço: **{', '.join(perfil.get('contramagia', [])) or '--'}**\n"
            f"Este feitiço é contra-feitiço de: **{', '.join(contra_feiticos_de(sessao.arquivo.stem)) or '--'}**"
        )[:1024],
        inline=False,
    )
    embed.add_field(
        name="Situação",
        value=("✅ Pronto para salvar" if not faltas else "Pendente: " + ", ".join(faltas)),
        inline=False,
    )
    return embed


class ViewPrivada(discord.ui.View):
    def __init__(self, usuario_id: int):
        super().__init__(timeout=TEMPO_FLUXO)
        self.usuario_id = usuario_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message(
            "Somente quem iniciou esta revisão pode usar os controles.", ephemeral=True
        )
        return False

    async def on_error(self, interaction, error, item):
        traceback.print_exception(type(error), error, error.__traceback__)
        mensagem = "Não consegui avançar esta etapa. A revisão foi mantida como rascunho."
        if interaction.response.is_done():
            await interaction.followup.send(mensagem, ephemeral=True)
        else:
            await interaction.response.send_message(mensagem, ephemeral=True)


class CategoriasRevisaoView(ViewPrivada):
    def __init__(self, usuario_id: int):
        super().__init__(usuario_id)
        categorias = sorted(
            [item.name for item in PASTA_FEITICOS.iterdir() if item.is_dir()],
            key=str.casefold,
        )
        seletor = discord.ui.Select(
            placeholder="Escolha a categoria",
            options=[
                discord.SelectOption(
                    label=categoria,
                    value=categoria,
                    description=self._progresso(categoria),
                )
                for categoria in categorias[:25]
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    @staticmethod
    def _progresso(categoria: str) -> str:
        arquivos = arquivos_categoria(categoria)
        completos = 0
        for arquivo in arquivos:
            if revisao_concluida(arquivo):
                completos += 1
        return f"{completos}/{len(arquivos)} revisados"

    async def selecionar(self, interaction: discord.Interaction) -> None:
        categoria = self.seletor.values[0]
        view = SelecionarFeiticoRevisaoView(self.usuario_id, categoria)
        await interaction.response.edit_message(
            content=None,
            embed=view.embed_lista(),
            view=view,
        )


class SelecionarFeiticoRevisaoView(ViewPrivada):
    def __init__(self, usuario_id: int, categoria: str, ano: int = 0, pagina: int = 0):
        super().__init__(usuario_id)
        self.categoria = categoria
        self.anos = grupos_revisao(arquivos_categoria(categoria))
        self.ano = max(0, min(ano, len(self.anos) - 1))
        self.tipo_grupo, self.rotulo_ano, arquivos_ano = self.anos[self.ano]
        self.paginas = [
            arquivos_ano[indice : indice + LIMITE_SELETOR]
            for indice in range(0, len(arquivos_ano), LIMITE_SELETOR)
        ] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        self.arquivos = self.paginas[self.pagina]
        anos = discord.ui.Select(
            placeholder=f"{self.tipo_grupo} — {self.rotulo_ano}"[:150],
            options=[
                discord.SelectOption(
                    label=rotulo[:100],
                    value=str(indice),
                    default=indice == self.ano,
                )
                for indice, (_, rotulo, _) in enumerate(self.anos)
            ],
            row=0,
        )
        anos.callback = self.selecionar_ano
        self.seletor_anos = anos
        self.add_item(anos)
        if self.arquivos:
            fichas = discord.ui.Select(
                placeholder="Escolha o feitiço",
                options=[
                    discord.SelectOption(
                    label=self._rotulo_ficha(arquivo)[:100],
                        value=str(indice),
                        description=self._situacao(arquivo),
                    )
                    for indice, arquivo in enumerate(self.arquivos)
                ],
                row=1,
            )
            fichas.callback = self.selecionar_ficha
            self.fichas = fichas
            self.add_item(fichas)
        if len(self.paginas) > 1:
            anterior = discord.ui.Button(
                label="Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == 0,
                row=2,
            )
            anterior.callback = self.pagina_anterior
            self.add_item(anterior)
            proxima = discord.ui.Button(
                label="Próxima",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == len(self.paginas) - 1,
                row=2,
            )
            proxima.callback = self.proxima_pagina
            self.add_item(proxima)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    def embed_lista(self) -> discord.Embed:
        sufixo = (
            f" — página {self.pagina + 1}/{len(self.paginas)}"
            if len(self.paginas) > 1
            else ""
        )
        lista = "\n".join(
            f"• {self._rotulo_ficha(arquivo)}" for arquivo in self.arquivos
        )
        return embed_painel(
            f"Revisar feitiços — {self.categoria} — {self.rotulo_ano}",
            f"{lista}\n\nSelecione abaixo qual feitiço deseja revisar.{sufixo}",
        )

    @staticmethod
    def _situacao(arquivo: Path) -> str:
        rascunho = chave_arquivo(arquivo) in _ler_json(ARQUIVO_RASCUNHOS)
        if revisao_concluida(arquivo):
            return "Revisão completa"
        try:
            perfil = extrair_perfil(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            perfil = None
        if perfil and perfil.get("estado") == "completa":
            return "Revisão incompleta"
        return "Rascunho salvo" if rascunho else "Não revisado"

    @classmethod
    def _rotulo_ficha(cls, arquivo: Path) -> str:
        situacao = cls._situacao(arquivo)
        indicador = {
            "Revisão completa": "✅ ",
            "Revisão incompleta": "⚠️ ",
            "Rascunho salvo": "⚠️ ",
        }.get(situacao, "")
        return f"{indicador}{arquivo.stem}"

    async def selecionar_ano(self, interaction: discord.Interaction) -> None:
        ano = int(self.seletor_anos.values[0])
        view = SelecionarFeiticoRevisaoView(self.usuario_id, self.categoria, ano)
        await interaction.response.edit_message(
            embed=view.embed_lista(),
            view=view,
        )

    async def pagina_anterior(self, interaction: discord.Interaction) -> None:
        view = SelecionarFeiticoRevisaoView(
            self.usuario_id, self.categoria, self.ano, self.pagina - 1
        )
        await interaction.response.edit_message(embed=view.embed_lista(), view=view)

    async def proxima_pagina(self, interaction: discord.Interaction) -> None:
        view = SelecionarFeiticoRevisaoView(
            self.usuario_id, self.categoria, self.ano, self.pagina + 1
        )
        await interaction.response.edit_message(embed=view.embed_lista(), view=view)

    async def selecionar_ficha(self, interaction: discord.Interaction) -> None:
        arquivo = self.arquivos[int(self.fichas.values[0])]
        sessao = SessaoFeitico.carregar(arquivo, self.categoria)
        await interaction.response.edit_message(
            content=None,
            embed=resumo_perfil(sessao),
            view=EditorFeiticoView(self.usuario_id, sessao),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None,
            embed=embed_painel(
                "Revisar feitiços",
                "Escolha uma categoria. O progresso é salvo por ficha.",
            ),
            view=CategoriasRevisaoView(self.usuario_id),
        )


class EditorFeiticoView(ViewPrivada):
    def __init__(self, usuario_id: int, sessao: SessaoFeitico):
        super().__init__(usuario_id)
        self.sessao = sessao
        for label, callback, row in (
            ("Manifestação, ação e ativação", self.base, 0),
            ("Duração, alcance e alvo", self.duracao, 0),
            ("Tipos", self.tipos, 0),
            ("Regras universais", self.regras, 1),
            ("Mecânicas", self.efeitos, 1),
            ("Defesa e contra-feitiço", self.defesa, 1),
            ("Descrição", self.descricao, 2),
            ("Prévia", self.previa, 2),
            ("Salvar e próximo", self.salvar, 4),
        ):
            botao = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.success if label == "Salvar e próximo" else discord.ButtonStyle.secondary,
                row=row,
            )
            botao.callback = callback
            self.add_item(botao)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    def atualizar_rascunho(self) -> None:
        self.sessao.perfil = normalizar_perfil(self.sessao.perfil)
        self.sessao.salvar_rascunho()

    async def base(self, interaction):
        await interaction.response.edit_message(
            embed=embed_painel("Manifestação, ação e ativação", "Defina como a magia se manifesta e quanto do turno ela consome."),
            view=BaseFeiticoView(self.usuario_id, self.sessao),
        )

    async def duracao(self, interaction):
        await interaction.response.edit_message(
            embed=resumo_duracao_alvo(self.sessao),
            view=DuracaoAlvoView(self.usuario_id, self.sessao),
        )

    async def tipos(self, interaction):
        await interaction.response.edit_message(
            embed=embed_painel("Tipos do feitiço", "Marque todos os tipos aplicáveis. As próximas perguntas dependem desta escolha."),
            view=TiposFeiticoView(self.usuario_id, self.sessao),
        )

    async def regras(self, interaction):
        await interaction.response.edit_message(
            embed=resumo_regras_universais(self.sessao),
            view=RegrasUniversaisView(self.usuario_id, self.sessao),
        )

    async def efeitos(self, interaction):
        await interaction.response.edit_message(
            embed=resumo_efeitos(self.sessao),
            view=EfeitosFeiticoView(self.usuario_id, self.sessao),
        )

    async def defesa(self, interaction):
        await interaction.response.edit_message(
            embed=resumo_defesa_contra(self.sessao),
            view=DefesaContraView(self.usuario_id, self.sessao),
        )

    async def descricao(self, interaction):
        if len(self.sessao.descricao) > 4000:
            await interaction.response.edit_message(
                embed=embed_painel(
                    "Descrição extensa",
                    "Esta descrição excede o limite do formulário do Discord e será preservada integralmente. Sistemas extensos serão revisados por subefeitos.",
                ),
                view=EditorFeiticoView(self.usuario_id, self.sessao),
            )
            return
        await interaction.response.send_modal(DescricaoFeiticoModal(self.usuario_id, self.sessao))

    async def previa(self, interaction):
        entrada = interpretar_markdown(self.sessao.arquivo.read_text(encoding="utf-8"))
        entrada.descricao = self.sessao.descricao
        entrada.perfil_combate = normalizar_perfil(self.sessao.perfil)
        embeds = criar_embeds_entrada(entrada, "feitico", self.sessao.arquivo.stem)
        await interaction.response.edit_message(
            content=None,
            embeds=embeds[:10],
            view=ConfirmarPreviaFeiticoView(self.usuario_id, self.sessao),
        )

    async def finalizar_revisao(self, interaction):
        faltas = pendencias(self.sessao.perfil)
        if faltas:
            await interaction.response.edit_message(
                embed=embed_painel(
                    "Revisão incompleta",
                    "Preencha antes de salvar: " + ", ".join(faltas),
                ),
                view=EditorFeiticoView(self.usuario_id, self.sessao),
            )
            return
        await interaction.response.defer()
        perfil_anterior = extrair_perfil(self.sessao.arquivo.read_text(encoding="utf-8")) or {}
        criar_backup(self.sessao)
        self.sessao.perfil = normalizar_perfil(self.sessao.perfil)
        self.sessao.perfil["estado"] = "completa"
        self.sessao.perfil["revisado_em"] = datetime.now().isoformat(timespec="seconds")
        salvar_revisao(self.sessao.arquivo, self.sessao.perfil, self.sessao.descricao)
        self.sessao.remover_rascunho()
        try:
            await sincronizar_vinculos_contrafeitico(
                interaction.client, self.sessao, perfil_anterior
            )
            await sincronizar_publicacao_feitico(interaction.client, self.sessao)
        except (ErroPublicacaoFicha, discord.HTTPException):
            # A ficha local continua salva; informamos na tela para que a
            # publicação possa ser tentada novamente.
            await interaction.edit_original_response(
                embed=embed_painel("Ficha salva; publicação pendente", "A versão local foi atualizada, mas a thread oficial não respondeu. Tente a prévia novamente."),
                view=EditorFeiticoView(self.usuario_id, self.sessao),
            )
            return
        proximo = proxima_ficha_pendente(self.sessao)
        if proximo is None:
            await interaction.edit_original_response(
                embed=embed_painel(
                    "Revisar feitiços",
                    f"Categoria **{self.sessao.categoria}** concluída. Escolha outra categoria.",
                ),
                view=CategoriasRevisaoView(self.usuario_id),
            )
            return
        proxima_sessao = SessaoFeitico.carregar(proximo, self.sessao.categoria)
        await interaction.edit_original_response(
            embed=resumo_perfil(proxima_sessao),
            view=EditorFeiticoView(self.usuario_id, proxima_sessao),
        )

    async def salvar(self, interaction):
        await self.finalizar_revisao(interaction)

    async def voltar(self, interaction):
        self.atualizar_rascunho()
        await interaction.response.edit_message(
            embed=embed_painel(f"Revisar feitiços — {self.sessao.categoria}", "Escolha outra ficha ou retome este rascunho depois."),
            view=SelecionarFeiticoRevisaoView(self.usuario_id, self.sessao.categoria),
        )


class ConfirmarPreviaFeiticoView(ViewPrivada):
    def __init__(self, usuario_id, sessao):
        super().__init__(usuario_id)
        self.sessao = sessao
        confirmar = discord.ui.Button(label="Confirmar e atualizar thread", style=discord.ButtonStyle.success, row=3)
        confirmar.callback = self.confirmar
        self.add_item(confirmar)
        voltar = discord.ui.Button(label="Voltar ao editor", style=discord.ButtonStyle.secondary, row=3)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def confirmar(self, interaction):
        editor = EditorFeiticoView(self.usuario_id, self.sessao)
        await editor.finalizar_revisao(interaction)

    async def voltar(self, interaction):
        await interaction.response.edit_message(content=None, embed=resumo_perfil(self.sessao), view=EditorFeiticoView(self.usuario_id, self.sessao))


class VoltarEditorView(ViewPrivada):
    def __init__(self, usuario_id, sessao):
        super().__init__(usuario_id)
        self.sessao = sessao
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def voltar(self, interaction):
        await interaction.response.edit_message(
            content=None,
            embed=resumo_perfil(self.sessao),
            view=EditorFeiticoView(self.usuario_id, self.sessao),
        )


class BaseFeiticoView(ViewPrivada):
    def __init__(self, usuario_id, sessao):
        super().__init__(usuario_id)
        self.sessao = sessao
        perfil = sessao.perfil
        self.mira = self._select("Forma de manifestação", MIRAS, perfil.get("mira", ""), 0)
        self.acao = self._select("Tipo de ação", TIPOS_ACAO, perfil.get("tipo_acao", ""), 1)
        self.ativacao = self._select("Ativação", ATIVACOES, perfil.get("ativacao", ""), 2)
        continuar = discord.ui.Button(label="Confirmar", style=discord.ButtonStyle.success, row=4)
        continuar.callback = self.confirmar
        self.add_item(continuar)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    def _select(self, placeholder, valores, atual, row):
        seletor = discord.ui.Select(
            placeholder=placeholder,
            options=[discord.SelectOption(label=v, value=v, default=v == atual) for v in valores],
            row=row,
        )
        seletor.callback = self.registrar_selecao
        self.add_item(seletor)
        return seletor

    async def registrar_selecao(self, interaction):
        await interaction.response.defer()

    async def confirmar(self, interaction):
        if not self.mira.values or not self.acao.values or not self.ativacao.values:
            await interaction.response.edit_message(
                embed=embed_painel("Campos obrigatórios", "Escolha a mira, a ação e a ativação."),
                view=self,
            )
            return
        self.sessao.perfil.update(
            {"mira": self.mira.values[0], "tipo_acao": self.acao.values[0], "ativacao": self.ativacao.values[0]}
        )
        self.sessao.perfil = normalizar_perfil(self.sessao.perfil)
        self.sessao.salvar_rascunho()
        await self.voltar(interaction)

    async def voltar(self, interaction):
        await interaction.response.edit_message(
            embed=resumo_perfil(self.sessao), view=EditorFeiticoView(self.usuario_id, self.sessao)
        )


class TiposFeiticoView(ViewPrivada):
    def __init__(self, usuario_id, sessao):
        super().__init__(usuario_id)
        self.sessao = sessao
        atuais = set(sessao.perfil.get("tipos", []))
        self.seletor = discord.ui.Select(
            placeholder="Tipos aplicáveis",
            min_values=1,
            max_values=len(TIPOS_EFEITO),
            options=[discord.SelectOption(label=v, value=v, default=v in atuais) for v in TIPOS_EFEITO],
        )
        self.seletor.callback = self.registrar_selecao
        self.add_item(self.seletor)
        confirmar = discord.ui.Button(label="Confirmar", style=discord.ButtonStyle.success, row=4)
        confirmar.callback = self.confirmar
        self.add_item(confirmar)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def registrar_selecao(self, interaction):
        await interaction.response.defer()

    async def confirmar(self, interaction):
        self.sessao.perfil["tipos"] = list(self.seletor.values)
        self.sessao.salvar_rascunho()
        await self.voltar(interaction)

    async def voltar(self, interaction):
        await interaction.response.edit_message(embed=resumo_perfil(self.sessao), view=EditorFeiticoView(self.usuario_id, self.sessao))


def resumo_duracao_alvo(sessao: SessaoFeitico) -> discord.Embed:
    perfil = normalizar_perfil(sessao.perfil)
    duracao = perfil.get("duracao", {})
    alcance = sessao.perfil.get("alcance") or "--"
    detalhes_alcance = sessao.perfil.get("detalhes_alcance", "")
    alvo = sessao.perfil.get("alvo") or "--"
    detalhes_alvo = (
        sessao.perfil.get("area", "")
        if alvo == "Área"
        else sessao.perfil.get("detalhes_alvo", "")
    )
    linhas = [
        f"**{linha_duracao(perfil) or duracao.get('unidade') or '--'}**",
        f"Alcance: **{alcance}**" + (f" — {detalhes_alcance}" if detalhes_alcance else ""),
        f"Alvo: **{alvo}**" + (f" — {detalhes_alvo}" if detalhes_alvo else ""),
    ]
    if perfil.get("mira") == "Especial":
        linhas.append(
            "Manifestação especial: **"
            f"{perfil.get('detalhes_mira') or '--'}**"
        )
    if perfil.get("ativacao") == "Preparada":
        linhas.append(f"Gatilho: **{perfil.get('gatilho') or '--'}**")
    avisos = [falta for falta in pendencias(perfil) if any(
        termo in falta for termo in ("duração", "quantidade da duração", "alcance", "alvo", "área", "manifestação")
    )]
    if avisos:
        linhas.append("**Pendente:** " + ", ".join(avisos))
    return embed_painel(
        "Duração, alcance e alvo",
        "\n".join(linhas)
        + "\n\nEscolha as opções nos menus e use o botão para medidas, restrições e condições especiais.",
    )


class DuracaoAlvoView(ViewPrivada):
    def __init__(self, usuario_id, sessao):
        super().__init__(usuario_id)
        self.sessao = sessao
        duracao = sessao.perfil.get("duracao", {})
        atual = duracao.get("unidade", "")
        self.unidade = discord.ui.Select(
            placeholder="Escolha a duração",
            options=[
                discord.SelectOption(
                    label={"Minuto": "Minutos", "Hora": "Horas", "Dia": "Dias"}.get(unidade, unidade),
                    value=unidade,
                    default=unidade == atual,
                )
                for unidade in UNIDADES_DURACAO
            ],
            row=0,
        )
        self.unidade.callback = self.selecionar_unidade
        self.add_item(self.unidade)
        alcance_atual = sessao.perfil.get("alcance", "")
        self.alcance = discord.ui.Select(
            placeholder="Escolha o alcance",
            options=[
                discord.SelectOption(
                    label=alcance,
                    value=alcance,
                    default=alcance == alcance_atual,
                )
                for alcance in ALCANCES
            ],
            row=1,
        )
        self.alcance.callback = self.selecionar_alcance
        self.add_item(self.alcance)
        alvo_atual = sessao.perfil.get("alvo", "")
        self.alvo = discord.ui.Select(
            placeholder="Escolha o tipo de alvo",
            options=[
                discord.SelectOption(
                    label=alvo,
                    value=alvo,
                    default=alvo == alvo_atual,
                )
                for alvo in ALVOS
            ],
            row=2,
        )
        self.alvo.callback = self.selecionar_alvo
        self.add_item(self.alvo)
        if atual and atual != "Instantâneo":
            duracao_btn = discord.ui.Button(label="Detalhes da duração", style=discord.ButtonStyle.primary, row=3)
            duracao_btn.callback = self.editar_duracao
            self.add_item(duracao_btn)
        detalhes = discord.ui.Button(
            label="Detalhes de alcance e alvo",
            style=discord.ButtonStyle.primary,
            row=3,
        )
        detalhes.callback = self.detalhes
        self.add_item(detalhes)
        if sessao.perfil.get("ativacao") == "Preparada":
            gatilho = discord.ui.Button(
                label="Gatilho",
                style=discord.ButtonStyle.secondary,
                row=3,
            )
            gatilho.callback = self.gatilho
            self.add_item(gatilho)
        confirmar = discord.ui.Button(label="Confirmar", style=discord.ButtonStyle.success, row=4)
        confirmar.callback = self.confirmar
        self.add_item(confirmar)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar_unidade(self, interaction):
        duracao = self.sessao.perfil.setdefault("duracao", {})
        unidade = self.unidade.values[0]
        duracao["unidade"] = unidade
        if unidade == "Instantâneo":
            duracao.update(valor="", especial="", fora_combate="", em_combate="")
        elif unidade == "Especial":
            duracao["valor"] = ""
        else:
            duracao.update(especial="", fora_combate="", em_combate="")
        self.sessao.salvar_rascunho()
        await interaction.response.edit_message(
            embed=resumo_duracao_alvo(self.sessao),
            view=DuracaoAlvoView(self.usuario_id, self.sessao),
        )

    async def selecionar_alcance(self, interaction):
        self.sessao.perfil["alcance"] = self.alcance.values[0]
        self.sessao.perfil = normalizar_perfil(self.sessao.perfil)
        self.sessao.salvar_rascunho()
        await interaction.response.edit_message(
            embed=resumo_duracao_alvo(self.sessao),
            view=DuracaoAlvoView(self.usuario_id, self.sessao),
        )

    async def selecionar_alvo(self, interaction):
        self.sessao.perfil["alvo"] = self.alvo.values[0]
        self.sessao.perfil = normalizar_perfil(self.sessao.perfil)
        self.sessao.salvar_rascunho()
        await interaction.response.edit_message(
            embed=resumo_duracao_alvo(self.sessao),
            view=DuracaoAlvoView(self.usuario_id, self.sessao),
        )

    async def detalhes(self, interaction):
        await interaction.response.send_modal(DetalhesDuracaoModal(self.usuario_id, self.sessao))

    async def editar_duracao(self, interaction):
        await interaction.response.send_modal(DuracaoModal(self.usuario_id, self.sessao))

    async def gatilho(self, interaction):
        await interaction.response.send_modal(GatilhoPreparadoModal(self.usuario_id, self.sessao))

    async def confirmar(self, interaction):
        self.sessao.salvar_rascunho()
        await self.voltar(interaction)

    async def voltar(self, interaction):
        await interaction.response.edit_message(
            embed=resumo_perfil(self.sessao),
            view=EditorFeiticoView(self.usuario_id, self.sessao),
        )


class DuracaoModal(discord.ui.Modal, title="Detalhes da duração"):
    def __init__(self, usuario_id, sessao):
        super().__init__()
        self.usuario_id, self.sessao = usuario_id, sessao
        duracao = sessao.perfil.get("duracao", {})
        self.especial = duracao.get("unidade") == "Especial"
        if self.especial:
            self.descricao = discord.ui.TextInput(
                label="Duração especial (Opcional)", required=False,
                placeholder="Ex.: varia conforme a situação.",
                default=duracao.get("especial", ""), max_length=300,
            )
            self.fora = discord.ui.TextInput(
                label="Fora de combate (Opcional)", required=False,
                placeholder="Ex.: 8 horas", default=duracao.get("fora_combate", ""), max_length=100,
            )
            self.combate = discord.ui.TextInput(
                label="Em combate (Opcional)", required=False,
                placeholder="Ex.: 3 rodadas", default=duracao.get("em_combate", ""), max_length=100,
            )
            for item in (self.descricao, self.fora, self.combate):
                self.add_item(item)
        else:
            unidade = str(duracao.get("unidade", "duração")).casefold()
            self.valor = discord.ui.TextInput(
                label="Quantidade (Obrigatório)", required=True,
                placeholder=f"Ex.: 2 {unidade} ou 1d4+2 {unidade}.",
                default=duracao.get("valor", ""), max_length=50,
            )
            self.add_item(self.valor)

    async def on_submit(self, interaction):
        duracao = self.sessao.perfil.setdefault("duracao", {})
        if self.especial:
            duracao["especial"] = str(self.descricao).strip()
            duracao["fora_combate"] = str(self.fora).strip()
            duracao["em_combate"] = str(self.combate).strip()
        else:
            duracao["valor"] = str(self.valor).strip()
        self.sessao.perfil = normalizar_perfil(self.sessao.perfil)
        self.sessao.salvar_rascunho()
        await interaction.response.edit_message(
            embed=resumo_duracao_alvo(self.sessao),
            view=DuracaoAlvoView(self.usuario_id, self.sessao),
        )


class DetalhesDuracaoModal(discord.ui.Modal, title="Duração, alcance e alvo"):
    def __init__(self, usuario_id, sessao):
        super().__init__()
        self.usuario_id, self.sessao = usuario_id, sessao
        self.detalhes_alcance = discord.ui.TextInput(
            label="Detalhes (Opcional)",
            required=False,
            placeholder="Ex.: 12 metros, mesma sala ou sem atravessar paredes.",
            default=sessao.perfil.get("detalhes_alcance", ""),
            max_length=300,
        )
        alvo = sessao.perfil.get("alvo", "")
        self.detalhes_alvo = discord.ui.TextInput(
            label=(
                "Dimensões da área (Obrigatório)"
                if alvo == "Área"
                else "Detalhes do alvo (Obrigatório)"
                if alvo == "Especial"
                else "Detalhes (Opcional)"
            ),
            required=alvo in {"Área", "Especial"},
            placeholder=(
                "Ex.: círculo de 6 m; atinge aliados e adversários."
                if alvo == "Área"
                else "Ex.: somente seres vivos ou até três criaturas."
            ),
            default=(
                sessao.perfil.get("area", "")
                if alvo == "Área"
                else sessao.perfil.get("detalhes_alvo", "")
            ),
            max_length=500,
        )
        itens = [self.detalhes_alcance, self.detalhes_alvo]
        if sessao.perfil.get("mira") == "Especial":
            self.detalhes_mira = discord.ui.TextInput(
                label="Manifestação especial (Obrigatório)",
                required=True,
                placeholder="Ex.: exige conhecer o nome verdadeiro do alvo.",
                default=sessao.perfil.get("detalhes_mira", ""),
                max_length=500,
            )
            itens.append(self.detalhes_mira)
        for item in itens:
            self.add_item(item)

    async def on_submit(self, interaction):
        self.sessao.perfil["detalhes_alcance"] = str(self.detalhes_alcance).strip()
        if self.sessao.perfil.get("alvo") == "Área":
            self.sessao.perfil["area"] = str(self.detalhes_alvo).strip()
        else:
            self.sessao.perfil["detalhes_alvo"] = str(self.detalhes_alvo).strip()
        if hasattr(self, "detalhes_mira"):
            self.sessao.perfil["detalhes_mira"] = str(self.detalhes_mira).strip()
        self.sessao.perfil = normalizar_perfil(self.sessao.perfil)
        self.sessao.salvar_rascunho()
        await interaction.response.edit_message(
            embed=resumo_duracao_alvo(self.sessao),
            view=DuracaoAlvoView(self.usuario_id, self.sessao),
        )


class GatilhoPreparadoModal(discord.ui.Modal, title="Gatilho da magia preparada"):
    def __init__(self, usuario_id, sessao):
        super().__init__()
        self.usuario_id, self.sessao = usuario_id, sessao
        self.texto = discord.ui.TextInput(
            label="Gatilho (Obrigatório)",
            style=discord.TextStyle.paragraph,
            default=sessao.perfil.get("gatilho", ""),
            placeholder="Ex.: quando alguém atravessar a porta marcada.",
            max_length=300,
        )
        self.add_item(self.texto)

    async def on_submit(self, interaction):
        self.sessao.perfil["gatilho"] = str(self.texto).strip()
        self.sessao.salvar_rascunho()
        await interaction.response.edit_message(
            embed=resumo_duracao_alvo(self.sessao),
            view=DuracaoAlvoView(self.usuario_id, self.sessao),
        )


def resumo_regras_universais(sessao: SessaoFeitico) -> discord.Embed:
    perfil = sessao.perfil
    contramagias = _nomes_contramagia(perfil, "propria")
    return embed_painel(
        "Regras universais",
        (
            f"Resposta do alvo: **{', '.join(perfil.get('respostas', [])) or '--'}**\n"
            f"Contra-feitiços associados: **{', '.join(contramagias) or '--'}**\n"
            f"Acúmulo: **{perfil.get('acumulo') or '--'}**\n"
            f"Interrupção ou encerramento: **{perfil.get('encerramento') or '--'}**\n\n"
            "Escolha a forma de encerramento. Condição específica abre um campo próprio."
        ),
    )


class RegrasUniversaisView(ViewPrivada):
    def __init__(self, usuario_id, sessao):
        super().__init__(usuario_id)
        self.sessao = sessao
        respostas_atuais = set(sessao.perfil.get("respostas", []))
        self.respostas = discord.ui.Select(
            placeholder="Como o alvo pode responder?",
            min_values=1,
            max_values=len(RESPOSTAS),
            options=[
                discord.SelectOption(label=opcao, value=opcao, default=opcao in respostas_atuais)
                for opcao in RESPOSTAS
            ],
            row=0,
        )
        self.respostas.callback = self.selecionar_respostas
        self.add_item(self.respostas)
        atual = sessao.perfil.get("acumulo", "")
        self.acumulo = discord.ui.Select(
            placeholder="Como efeitos repetidos se acumulam?",
            options=[
                discord.SelectOption(label=opcao, value=opcao, default=opcao == atual)
                for opcao in ACUMULOS
            ],
            row=1,
        )
        self.acumulo.callback = self.selecionar_acumulo
        self.add_item(self.acumulo)
        opcoes_encerramento = (
            "Uso único (instantâneo)", "Sustentado", "Duração definida",
            "Preparado", "Até o fim da cena", "Proteção com PV",
            "Condição específica",
        )
        atual = sessao.perfil.get("encerramento_tipo", "")
        self.encerramento = discord.ui.Select(
            placeholder="Como o efeito se encerra?",
            options=[
                discord.SelectOption(label=opcao, value=opcao, default=opcao == atual)
                for opcao in opcoes_encerramento
            ],
            row=2,
        )
        self.encerramento.callback = self.selecionar_encerramento
        self.add_item(self.encerramento)
        escolher_contramagias = discord.ui.Button(
            label="Contra-feitiços associados",
            style=discord.ButtonStyle.primary,
            row=3,
        )
        escolher_contramagias.callback = self.escolher_contramagias
        self.add_item(escolher_contramagias)
        if _nomes_contramagia(sessao.perfil, "propria"):
            limpar_contramagias = discord.ui.Button(
                label="Limpar contra-feitiços",
                style=discord.ButtonStyle.danger,
                row=3,
            )
            limpar_contramagias.callback = self.limpar_contramagias
            self.add_item(limpar_contramagias)
        confirmar = discord.ui.Button(label="Confirmar", style=discord.ButtonStyle.success, row=4)
        confirmar.callback = self.confirmar
        self.add_item(confirmar)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def atualizar(self, interaction):
        self.sessao.perfil = normalizar_perfil(self.sessao.perfil)
        self.sessao.salvar_rascunho()
        await interaction.response.edit_message(
            embed=resumo_regras_universais(self.sessao),
            view=RegrasUniversaisView(self.usuario_id, self.sessao),
        )

    async def selecionar_respostas(self, interaction):
        self.sessao.perfil["respostas"] = list(self.respostas.values)
        await self.atualizar(interaction)

    async def selecionar_acumulo(self, interaction):
        self.sessao.perfil["acumulo"] = self.acumulo.values[0]
        await self.atualizar(interaction)

    async def selecionar_encerramento(self, interaction):
        tipo = self.encerramento.values[0]
        if tipo == "Condição específica":
            await interaction.response.send_modal(CondicaoEncerramentoModal(self.usuario_id, self.sessao))
            return
        frases = {
            "Uso único (instantâneo)": "O feitiço é de uso único: seu efeito se resolve imediatamente após a execução e não permanece ativo.",
            "Sustentado": "O efeito permanece ativo enquanto for sustentado. Ele se encerra quando o conjurador o desfaz ou perde a concentração.",
            "Duração definida": "O efeito se encerra quando a duração indicada se esgota.",
            "Preparado": "A magia permanece preparada até que o gatilho seja ativado ou o conjurador a desfaça.",
            "Até o fim da cena": "O efeito permanece ativo até o fim da cena, salvo se for desfeito antes por outra condição.",
            "Proteção com PV": "O efeito se encerra quando sua duração termina, quando o conjurador o desfaz ou quando a proteção perde todos os seus PV.",
        }
        self.sessao.perfil["encerramento_tipo"] = tipo
        self.sessao.perfil["encerramento"] = frases[tipo]
        self.sessao.salvar_rascunho()
        await interaction.response.edit_message(embed=resumo_regras_universais(self.sessao), view=RegrasUniversaisView(self.usuario_id, self.sessao))

    async def confirmar(self, interaction):
        self.sessao.perfil = normalizar_perfil(self.sessao.perfil)
        if not self.sessao.perfil.get("respostas"):
            await interaction.response.edit_message(
                embed=embed_painel(
                    "Resposta do alvo obrigatória",
                    "Escolha pelo menos uma resposta do alvo antes de confirmar estas regras.",
                ),
                view=RegrasUniversaisView(self.usuario_id, self.sessao),
            )
            return
        self.sessao.salvar_rascunho()
        await self.voltar(interaction)

    async def escolher_contramagias(self, interaction):
        await interaction.response.edit_message(
            embed=embed_painel(
                "Contra-feitiços associados",
                f"{_estado_selecao_contramagia(self.sessao, None, 'propria')}\nSelecione um ou mais feitiços que anulam este feitiço.",
            ),
            view=SeletorContramagiaCategoriaView(self.usuario_id, self.sessao),
        )

    async def limpar_contramagias(self, interaction):
        await interaction.response.edit_message(
            embed=embed_painel(
                "Limpar contra-feitiços",
                f"{_estado_selecao_contramagia(self.sessao, None, 'propria')}\nSelecione quais vínculos deseja remover.",
            ),
            view=LimparContramagiasView(self.usuario_id, self.sessao),
        )

    async def voltar(self, interaction):
        await interaction.response.edit_message(
            embed=resumo_perfil(self.sessao),
            view=EditorFeiticoView(self.usuario_id, self.sessao),
        )


class CondicaoEncerramentoModal(discord.ui.Modal, title="Condição específica de encerramento"):
    def __init__(self, usuario_id, sessao):
        super().__init__()
        self.usuario_id, self.sessao = usuario_id, sessao
        self.texto = discord.ui.TextInput(
            label="Condição de encerramento (Obrigatório)",
            style=discord.TextStyle.paragraph,
            default=sessao.perfil.get("encerramento", ""),
            placeholder="Ex.: termina quando o alvo passar em um teste de Fortitude.",
            max_length=800,
        )
        self.add_item(self.texto)

    async def on_submit(self, interaction):
        self.sessao.perfil["encerramento_tipo"] = "Condição específica"
        self.sessao.perfil["encerramento"] = str(self.texto).strip()
        self.sessao.salvar_rascunho()
        await interaction.response.edit_message(
            embed=resumo_regras_universais(self.sessao),
            view=RegrasUniversaisView(self.usuario_id, self.sessao),
        )


def resumo_efeitos(sessao: SessaoFeitico) -> discord.Embed:
    tipos = sessao.perfil.get("tipos", [])
    return embed_painel(
        "Mecânicas",
        (
            f"Tipos escolhidos: **{', '.join(tipos) or '--'}**\n"
            "Registre apenas os valores mecânicos aplicáveis. A descrição do feitiço já explica seus efeitos."
        ),
    )


class EfeitosFeiticoView(ViewPrivada):
    def __init__(self, usuario_id, sessao):
        super().__init__(usuario_id)
        self.sessao = sessao
        tipos = set(sessao.perfil.get("tipos", []))
        botoes: list[tuple[str, Any]] = []
        if "Dano" in tipos:
            botoes.append(("Dano", self.dano))
        if "Cura" in tipos:
            botoes.append(("Cura", self.cura))
        if "Proteção" in tipos:
            botoes.append(("Proteção", self.protecao))
        if "Contra-feitiço" in tipos:
            botoes.append(("Contra-feitiço", self.contra_feitico))
        for indice, (label, callback) in enumerate(botoes):
            botao = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                row=indice // 4,
            )
            botao.callback = callback
            self.add_item(botao)
        confirmar = discord.ui.Button(label="Confirmar", style=discord.ButtonStyle.success, row=4)
        confirmar.callback = self.confirmar
        self.add_item(confirmar)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def dano(self, interaction): await interaction.response.send_modal(DanoModal(self.usuario_id, self.sessao))
    async def cura(self, interaction): await interaction.response.send_modal(CuraModal(self.usuario_id, self.sessao))
    async def protecao(self, interaction): await interaction.response.send_modal(ProtecaoModal(self.usuario_id, self.sessao))
    async def contra_feitico(self, interaction):
        self.sessao.perfil.setdefault("contra_feitico", {})["habilitado"] = True
        await interaction.response.edit_message(
            embed=embed_painel(
                "Escolher feitiço anulado",
                "Selecione na biblioteca o feitiço que esta magia consegue anular.",
            ),
            view=SeletorContramagiaCategoriaView(self.usuario_id, self.sessao, "alvos"),
        )
    async def confirmar(self, interaction):
        self.sessao.salvar_rascunho()
        await self.voltar(interaction)

    async def voltar(self, interaction): await interaction.response.edit_message(embed=resumo_perfil(self.sessao), view=EditorFeiticoView(self.usuario_id, self.sessao))


class DanoModal(discord.ui.Modal, title="Dano"):
    def __init__(self, usuario_id, sessao):
        super().__init__(); self.usuario_id, self.sessao = usuario_id, sessao; dano=sessao.perfil.get("dano",{})
        self.inicial=discord.ui.TextInput(label="Dano inicial (Opcional)",required=False,default=dano.get("inicial",""),placeholder="Ex.: 2d6+2")
        self.tipo_inicial=discord.ui.TextInput(label="Tipo do dano inicial (Opcional)",required=False,default=dano.get("tipo_inicial",""),placeholder="Ex.: ígneo")
        self.sustentado=discord.ui.TextInput(label="Dano sustentado (Opcional)",required=False,default=dano.get("sustentado",""),placeholder="Ex.: +2")
        self.tipo_sustentado=discord.ui.TextInput(label="Tipo do dano sustentado (Opcional)",required=False,default=dano.get("tipo_sustentado",""),placeholder="Ex.: elétrico")
        self.frequencia=discord.ui.TextInput(label="Frequência sustentada (Opcional)",required=False,default=dano.get("frequencia",""),placeholder="Ex.: por turno")
        for item in (self.inicial,self.tipo_inicial,self.sustentado,self.tipo_sustentado,self.frequencia):self.add_item(item)
    async def on_submit(self,interaction):
        self.sessao.perfil["dano"]={"inicial":str(self.inicial).strip(),"tipo_inicial":str(self.tipo_inicial).strip(),"sustentado":str(self.sustentado).strip(),"tipo_sustentado":str(self.tipo_sustentado).strip(),"frequencia":str(self.frequencia).strip()}
        self.sessao.salvar_rascunho();await interaction.response.edit_message(embed=resumo_perfil(self.sessao),view=EditorFeiticoView(self.usuario_id,self.sessao))


class CuraModal(discord.ui.Modal, title="Cura"):
    def __init__(self,usuario_id,sessao):
        super().__init__();self.usuario_id,self.sessao=usuario_id,sessao;cura=sessao.perfil.get("cura",{})
        self.formula=discord.ui.TextInput(label="Fórmula de cura (Obrigatório)",default=cura.get("formula",""),placeholder="Ex.: 3d6 + Bônus de Medicina de Cura")
        self.recurso=discord.ui.TextInput(label="Recurso recuperado (Obrigatório)",default=cura.get("recurso","vida"),placeholder="Ex.: vida, alma ou PH")
        self.frequencia=discord.ui.TextInput(label="Frequência (Opcional)",required=False,default=cura.get("frequencia",""),placeholder="Ex.: por turno sustentado")
        for item in (self.formula,self.recurso,self.frequencia):self.add_item(item)
    async def on_submit(self,interaction):
        self.sessao.perfil["cura"]={"formula":str(self.formula).strip(),"recurso":str(self.recurso).strip(),"frequencia":str(self.frequencia).strip()}
        self.sessao.salvar_rascunho();await interaction.response.edit_message(embed=resumo_perfil(self.sessao),view=EditorFeiticoView(self.usuario_id,self.sessao))


class ProtecaoModal(discord.ui.Modal, title="Proteção"):
    def __init__(self,usuario_id,sessao):
        super().__init__();self.usuario_id,self.sessao=usuario_id,sessao;protecao=sessao.perfil.get("protecao",{})
        self.pv=discord.ui.TextInput(label="PV da proteção (Opcional)",required=False,default=protecao.get("pv",""),placeholder="Ex.: 4")
        self.cobertura=discord.ui.TextInput(label="Cobertura da proteção (Obrigatório)",style=discord.TextStyle.paragraph,default=protecao.get("cobertura",""),placeholder="Ex.: protege contra fogo e impactos físicos.",max_length=800)
        self.reducao=discord.ui.TextInput(label="Absorção ou redução (Opcional)",required=False,default=protecao.get("reducao",""),placeholder="Ex.: reduz 2 de dano ígneo.",max_length=300)
        for item in (self.pv,self.cobertura,self.reducao):self.add_item(item)
    async def on_submit(self,interaction):
        self.sessao.perfil["protecao"]={"pv":str(self.pv).strip(),"cobertura":str(self.cobertura).strip(),"reducao":str(self.reducao).strip()}
        self.sessao.salvar_rascunho();await interaction.response.edit_message(embed=resumo_perfil(self.sessao),view=EditorFeiticoView(self.usuario_id,self.sessao))


def _momento_contra_atual(sessao: SessaoFeitico) -> str:
    contra = sessao.perfil.get("contra_feitico", {})
    if not contra.get("habilitado"):
        return "Não se aplica"
    if not contra.get("momento"):
        return "Pendente de configuração"
    momento = contra.get("momento", "")
    conversoes = {
        "Reação": "Reação imediata",
        "Antecipada": "Defesa preparada",
        "Ambas": "Reação imediata e defesa preparada",
    }
    momento = conversoes.get(momento, momento)
    return momento if momento in MOMENTOS_CONTRA_FEITICO else "Não se aplica"


def _grupos_contramagia(categoria: str) -> list[tuple[str, str, list[Path]]]:
    return grupos_revisao(arquivos_categoria(categoria))


@dataclass
class EstadoSelecaoContramagia:
    destino: str
    nomes: list[str]
    originais: list[str]
    referencias: dict[str, list[str]] | None = None


def _nomes_contramagia(perfil: dict[str, Any], destino: str) -> list[str]:
    if destino == "propria":
        nomes = perfil.get("contramagia", [])
    else:
        contra = perfil.get("contra_feitico") or {}
        nomes = contra.get("feiticos", []) if isinstance(contra, dict) else []
    if isinstance(nomes, str):
        nomes = [nomes] if nomes.strip() else []
    return list(dict.fromkeys(str(nome).strip() for nome in nomes if str(nome).strip()))


def _estado_selecao_contramagia(
    sessao: SessaoFeitico,
    estado: EstadoSelecaoContramagia | None,
    destino: str,
) -> str:
    defesa = sessao.perfil.get("defesa") or {}
    defesa_atual = defesa.get("momento") or "Não é defesa"
    if estado is not None:
        nomes = estado.nomes
        pendente = nomes != estado.originais
    else:
        nomes = _nomes_contramagia(sessao.perfil, destino)
        pendente = False
    contra_atual = ", ".join(nomes) or "--"
    if pendente:
        contra_atual += " (pendente)"
    return f"**Defesa:** {defesa_atual}\n**Contra-feitiço:** {contra_atual}"


def _referencias_contramagia() -> dict[str, list[str]]:
    referencias: dict[str, set[str]] = {}

    def registrar(nome_ficha: str, perfil: dict[str, Any]) -> None:
        for nome_contra in _nomes_contramagia(perfil, "propria"):
            if nome_contra.casefold() != nome_ficha.casefold():
                referencias.setdefault(nome_contra.casefold(), set()).add(nome_ficha)

    for arquivo in PASTA_FEITICOS.rglob("*.md"):
        try:
            perfil = extrair_perfil(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if perfil:
            registrar(arquivo.stem, perfil)

    for chave, rascunho in _ler_json(ARQUIVO_RASCUNHOS).items():
        if not isinstance(rascunho, dict) or not isinstance(rascunho.get("perfil"), dict):
            continue
        registrar(Path(chave).stem, normalizar_perfil(rascunho["perfil"]))
    return {chave: sorted(nomes, key=str.casefold) for chave, nomes in referencias.items()}


def _confirmar_selecao_contramagia(sessao: SessaoFeitico, estado: EstadoSelecaoContramagia) -> None:
    if estado.destino == "propria":
        sessao.perfil["contramagia"] = list(estado.nomes)
    else:
        contra = sessao.perfil.setdefault("contra_feitico", {})
        contra["habilitado"] = True
        contra["feiticos"] = list(estado.nomes)
    sessao.perfil = normalizar_perfil(sessao.perfil)
    sessao.salvar_rascunho()


async def _retornar_da_selecao_contramagia(interaction, sessao: SessaoFeitico, destino: str) -> None:
    if destino == "propria":
        embed = resumo_regras_universais(sessao)
        view = RegrasUniversaisView(interaction.user.id, sessao)
    else:
        embed = resumo_defesa_contra(sessao)
        view = DefesaContraView(interaction.user.id, sessao)
    await interaction.response.edit_message(embed=embed, view=view)


class SeletorContramagiaCategoriaView(ViewPrivada):
    def __init__(self, usuario_id: int, sessao: SessaoFeitico, destino: str = "propria", estado: EstadoSelecaoContramagia | None = None):
        super().__init__(usuario_id)
        self.sessao, self.destino = sessao, destino
        self.estado = estado or EstadoSelecaoContramagia(
            destino, _nomes_contramagia(sessao.perfil, destino), _nomes_contramagia(sessao.perfil, destino)
        )
        categorias = sorted((p.name for p in PASTA_FEITICOS.iterdir() if p.is_dir()), key=str.casefold)
        opcoes = [
            discord.SelectOption(label=nome[:100], value=nome)
            for nome in categorias[:24]
        ]
        if destino == "propria":
            opcoes.insert(0, discord.SelectOption(label="Nenhum", value="__nenhum__"))
        seletor = discord.ui.Select(
            placeholder="Escolha a categoria do contra-feitiço",
            options=opcoes,
            row=0,
        )
        seletor.callback = self.selecionar
        self.add_item(seletor)
        confirmar = discord.ui.Button(label="Confirmar", style=discord.ButtonStyle.success, row=3)
        confirmar.callback = self.confirmar
        self.add_item(confirmar)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction):
        categoria = interaction.data["values"][0]
        if categoria == "__nenhum__":
            self.estado.nomes = []
            await interaction.response.edit_message(
                embed=embed_painel(
                    "Contra-feitiços associados",
                    f"{_estado_selecao_contramagia(self.sessao, self.estado, self.destino)}\nNenhum contra-feitiço selecionado. Confirme para salvar.",
                ),
                view=self,
            )
            return
        grupos = _grupos_contramagia(categoria)
        view = SeletorContramagiaGrupoView(self.usuario_id, self.sessao, categoria, self.destino, self.estado)
        texto = f"{_estado_selecao_contramagia(self.sessao, self.estado, self.destino)}\nCategoria: **{categoria}**\nEscolha o ano de desbloqueio ou a subcategoria."
        if not grupos:
            texto = f"Não há feitiços disponíveis na categoria **{categoria}**."
        await interaction.response.edit_message(embed=embed_painel("Escolher contra-feitiço", texto), view=view)

    async def voltar(self, interaction):
        await _retornar_da_selecao_contramagia(interaction, self.sessao, self.destino)

    async def confirmar(self, interaction):
        _confirmar_selecao_contramagia(self.sessao, self.estado)
        await _retornar_da_selecao_contramagia(interaction, self.sessao, self.destino)


class SeletorContramagiaGrupoView(ViewPrivada):
    def __init__(self, usuario_id: int, sessao: SessaoFeitico, categoria: str, destino: str = "propria", estado: EstadoSelecaoContramagia | None = None):
        super().__init__(usuario_id)
        self.sessao, self.categoria, self.destino = sessao, categoria, destino
        self.estado = estado or EstadoSelecaoContramagia(
            destino, _nomes_contramagia(sessao.perfil, destino), _nomes_contramagia(sessao.perfil, destino)
        )
        self.grupos = _grupos_contramagia(categoria)
        if self.grupos:
            seletor = discord.ui.Select(
                placeholder="Ano de desbloqueio ou subcategoria",
                options=[discord.SelectOption(label=(rotulo if tipo == "Ano" else f"{tipo}: {rotulo}")[:100], value=str(i)) for i, (tipo, rotulo, _) in enumerate(self.grupos[:25])],
                row=0,
            )
            seletor.callback = self.selecionar
            self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)
        confirmar = discord.ui.Button(label="Confirmar", style=discord.ButtonStyle.success, row=3)
        confirmar.callback = self.confirmar
        self.add_item(confirmar)

    async def selecionar(self, interaction):
        grupo = self.grupos[int(interaction.data["values"][0])]
        view = SeletorContramagiaFeiticoView(self.usuario_id, self.sessao, self.categoria, grupo, self.destino, estado=self.estado)
        await interaction.response.edit_message(embed=embed_painel("Escolher contra-feitiço", f"{_estado_selecao_contramagia(self.sessao, self.estado, self.destino)}\nCategoria: **{self.categoria}**\n{grupo[0]}: **{grupo[1]}**\nSelecione um ou mais feitiços."), view=view)

    async def voltar(self, interaction):
        await interaction.response.edit_message(embed=embed_painel("Escolher contra-feitiço", "Escolha primeiro a categoria."), view=SeletorContramagiaCategoriaView(self.usuario_id, self.sessao, self.destino, self.estado))

    async def confirmar(self, interaction):
        _confirmar_selecao_contramagia(self.sessao, self.estado)
        await _retornar_da_selecao_contramagia(interaction, self.sessao, self.destino)


class SeletorContramagiaFeiticoView(ViewPrivada):
    def __init__(self, usuario_id: int, sessao: SessaoFeitico, categoria: str, grupo, destino: str = "propria", pagina: int = 0, estado: EstadoSelecaoContramagia | None = None):
        super().__init__(usuario_id)
        self.sessao, self.categoria, self.grupo, self.destino = sessao, categoria, grupo, destino
        self.estado = estado or EstadoSelecaoContramagia(
            destino, _nomes_contramagia(sessao.perfil, destino), _nomes_contramagia(sessao.perfil, destino)
        )
        self.paginas = [grupo[2][i:i + LIMITE_SELETOR] for i in range(0, len(grupo[2]), LIMITE_SELETOR)] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        arquivos = self.paginas[self.pagina]
        if self.estado.referencias is None:
            self.estado.referencias = _referencias_contramagia()
        referencias = self.estado.referencias
        if arquivos:
            seletor = discord.ui.Select(
                placeholder="Selecione um ou mais feitiços",
                min_values=0,
                max_values=len(arquivos),
                options=[
                    discord.SelectOption(
                        label=arquivo.stem[:100],
                        value=arquivo.stem,
                        description=(
                            "Já é contra-feitiço de: "
                            + ", ".join(referencias.get(arquivo.stem.casefold(), []))
                        )[:100] or None,
                        default=arquivo.stem in self.estado.nomes,
                    )
                    for arquivo in arquivos
                ],
                row=0,
            )
            seletor.callback = self.selecionar
            self.add_item(seletor)
        if len(self.paginas) > 1:
            anterior = discord.ui.Button(label="Anterior", style=discord.ButtonStyle.secondary, disabled=self.pagina == 0, row=2)
            anterior.callback = self.pagina_anterior
            self.add_item(anterior)
            proxima = discord.ui.Button(label="Próxima", style=discord.ButtonStyle.secondary, disabled=self.pagina == len(self.paginas) - 1, row=2)
            proxima.callback = self.proxima_pagina
            self.add_item(proxima)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)
        confirmar = discord.ui.Button(label="Confirmar", style=discord.ButtonStyle.success, row=3)
        confirmar.callback = self.confirmar
        self.add_item(confirmar)

    async def selecionar(self, interaction):
        valores = set(interaction.data.get("values", []))
        escopo = {arquivo.stem for arquivo in self.paginas[self.pagina]}
        self.estado.nomes = [
            nome for nome in self.estado.nomes if nome not in escopo
        ] + [arquivo.stem for arquivo in self.paginas[self.pagina] if arquivo.stem in valores]
        view = SeletorContramagiaFeiticoView(
            self.usuario_id, self.sessao, self.categoria, self.grupo, self.destino,
            self.pagina, self.estado,
        )
        referencias = self.estado.referencias or {}
        avisos = [
            f"{nome}: já é contra-feitiço de {', '.join(referencias[nome.casefold()])}."
            for nome in self.estado.nomes
            if nome.casefold() in referencias
        ]
        texto = _estado_selecao_contramagia(self.sessao, self.estado, self.destino)
        if avisos:
            texto += "\n\n**Vínculos existentes:**\n" + "\n".join(avisos)
        await interaction.response.edit_message(embed=embed_painel("Escolher contra-feitiço", texto), view=view)

    async def pagina_anterior(self, interaction):
        await self._trocar_pagina(interaction, self.pagina - 1)

    async def proxima_pagina(self, interaction):
        await self._trocar_pagina(interaction, self.pagina + 1)

    async def _trocar_pagina(self, interaction, pagina):
        view = SeletorContramagiaFeiticoView(self.usuario_id, self.sessao, self.categoria, self.grupo, self.destino, pagina, self.estado)
        await interaction.response.edit_message(
            embed=embed_painel(
                "Escolher contra-feitiço",
                _estado_selecao_contramagia(self.sessao, self.estado, self.destino),
            ),
            view=view,
        )

    async def voltar(self, interaction):
        await interaction.response.edit_message(embed=embed_painel("Escolher contra-feitiço", f"{_estado_selecao_contramagia(self.sessao, self.estado, self.destino)}\nCategoria: **{self.categoria}**\nEscolha o ano de desbloqueio ou a subcategoria."), view=SeletorContramagiaGrupoView(self.usuario_id, self.sessao, self.categoria, self.destino, self.estado))

    async def confirmar(self, interaction):
        _confirmar_selecao_contramagia(self.sessao, self.estado)
        await _retornar_da_selecao_contramagia(interaction, self.sessao, self.destino)


def resumo_defesa_contra(sessao: SessaoFeitico) -> discord.Embed:
    defesa = sessao.perfil.get("defesa") or {}
    contra = sessao.perfil.get("contra_feitico", {})
    return embed_painel(
        "Defesa e contra-feitiço",
        (
            f"Defesa: **{defesa.get('momento') or 'Não é defesa'}** — {', '.join(defesa.get('propriedades', [])) or 'sem propriedades específicas'}\n"
            f"Uso como contra-feitiço: **{_momento_contra_atual(sessao)}**\n"
            f"Feitiços anulados por este: **{', '.join(contra.get('feiticos', [])) or '--'}**\n\n"
            f"Este feitiço é contra-feitiço de: **{', '.join(contra_feiticos_de(sessao.arquivo.stem)) or '--'}**\n\n"
            "Escolha os momentos nos menus. Selecione os nomes dos feitiços diretamente na biblioteca."
        ),
    )


class DefesaContraView(ViewPrivada):
    def __init__(self,usuario_id,sessao):
        super().__init__(usuario_id)
        self.sessao = sessao
        defesa = sessao.perfil.get("defesa", {})
        momento_atual = defesa.get("momento", "Não é defesa")
        self.momento = discord.ui.Select(
            placeholder="Quando pode ser usado como defesa?",
            options=[
                discord.SelectOption(label=opcao, value=opcao, default=opcao == momento_atual)
                for opcao in MOMENTOS_DEFESA
            ],
            row=0,
        )
        self.momento.callback = self.selecionar_momento
        self.add_item(self.momento)
        contra_atual = _momento_contra_atual(sessao)
        self.momento_contra = discord.ui.Select(
            placeholder="Como funciona contra outro feitiço?",
            options=[
                discord.SelectOption(label=opcao, value=opcao, default=opcao == contra_atual)
                for opcao in MOMENTOS_CONTRA_FEITICO
            ],
            row=1,
        )
        self.momento_contra.callback = self.selecionar_momento_contra
        self.add_item(self.momento_contra)
        if momento_atual != "Não é defesa":
            detalhes_defesa = discord.ui.Button(label="Detalhes da defesa", style=discord.ButtonStyle.primary, row=2)
            detalhes_defesa.callback = self.detalhes_defesa
            self.add_item(detalhes_defesa)
        if contra_atual != "Não se aplica":
            escolher_alvos = discord.ui.Button(label="Feitiços que ele anula", style=discord.ButtonStyle.primary, row=3)
            escolher_alvos.callback = self.escolher_alvos
            self.add_item(escolher_alvos)
        confirmar = discord.ui.Button(label="Confirmar", style=discord.ButtonStyle.success, row=4)
        confirmar.callback = self.confirmar
        self.add_item(confirmar)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def atualizar(self, interaction):
        self.sessao.salvar_rascunho()
        await interaction.response.edit_message(
            embed=resumo_defesa_contra(self.sessao),
            view=DefesaContraView(self.usuario_id, self.sessao),
        )

    async def selecionar_momento(self, interaction):
        self.sessao.perfil.setdefault("defesa", {})["momento"] = self.momento.values[0]
        await self.atualizar(interaction)

    async def selecionar_momento_contra(self, interaction):
        momento = self.momento_contra.values[0]
        contra = self.sessao.perfil.setdefault("contra_feitico", {})
        contra["habilitado"] = momento != "Não se aplica"
        contra["momento"] = "" if momento == "Não se aplica" else momento
        if momento == "Não se aplica":
            contra["feiticos"] = []
        await self.atualizar(interaction)

    async def detalhes_defesa(self, interaction):
        await interaction.response.send_modal(DetalhesDefesaModal(self.usuario_id, self.sessao))

    async def escolher_alvos(self, interaction):
        await interaction.response.edit_message(
            embed=embed_painel(
                "Escolher feitiço anulado",
                f"{_estado_selecao_contramagia(self.sessao, None, 'alvos')}\nSelecione na biblioteca os feitiços que esta magia consegue anular.",
            ),
            view=SeletorContramagiaCategoriaView(self.usuario_id, self.sessao, "alvos"),
        )

    async def confirmar(self, interaction):
        self.sessao.salvar_rascunho()
        await self.voltar(interaction)

    async def voltar(self, interaction):
        await interaction.response.edit_message(
            embed=resumo_perfil(self.sessao),
            view=EditorFeiticoView(self.usuario_id, self.sessao),
        )


class LimparContramagiasView(ViewPrivada):
    def __init__(self, usuario_id: int, sessao: SessaoFeitico, selecionados: list[str] | None = None, pagina: int = 0):
        super().__init__(usuario_id)
        self.sessao = sessao
        self.selecionados = list(selecionados or [])
        existentes = _nomes_contramagia(sessao.perfil, "propria")
        self.paginas = [existentes[i:i + LIMITE_SELETOR] for i in range(0, len(existentes), LIMITE_SELETOR)] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        opcoes = self.paginas[self.pagina]
        seletor = discord.ui.Select(
            placeholder="Selecione os vínculos para remover",
            min_values=0,
            max_values=len(opcoes),
            options=[
                discord.SelectOption(label=nome[:100], value=nome, default=nome in self.selecionados)
                for nome in opcoes
            ],
            row=0,
        )
        seletor.callback = self.selecionar
        self.add_item(seletor)
        if len(self.paginas) > 1:
            anterior = discord.ui.Button(label="Anterior", style=discord.ButtonStyle.secondary, disabled=self.pagina == 0, row=2)
            anterior.callback = self.pagina_anterior
            self.add_item(anterior)
            proxima = discord.ui.Button(label="Próxima", style=discord.ButtonStyle.secondary, disabled=self.pagina == len(self.paginas) - 1, row=2)
            proxima.callback = self.proxima_pagina
            self.add_item(proxima)
        confirmar = discord.ui.Button(label="Confirmar limpeza", style=discord.ButtonStyle.danger, disabled=not self.selecionados, row=3)
        confirmar.callback = self.confirmar
        self.add_item(confirmar)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
        voltar.callback = self.voltar
        self.add_item(voltar)

    def resumo_status(self) -> str:
        defesa = self.sessao.perfil.get("defesa") or {}
        atuais = _nomes_contramagia(self.sessao.perfil, "propria")
        restantes = [nome for nome in atuais if nome not in set(self.selecionados)]
        texto_contra = ", ".join(restantes) or "--"
        if self.selecionados:
            texto_contra += " (pendente)"
        return f"**Defesa:** {defesa.get('momento') or 'Não é defesa'}\n**Contra-feitiço:** {texto_contra}"

    async def selecionar(self, interaction):
        escopo = set(self.paginas[self.pagina])
        valores = set(interaction.data.get("values", []))
        self.selecionados = [nome for nome in self.selecionados if nome not in escopo]
        self.selecionados.extend(nome for nome in self.paginas[self.pagina] if nome in valores)
        texto = (
            f"{self.resumo_status()}\n"
            f"Remover: **{', '.join(self.selecionados) or '--'}**"
        )
        await interaction.response.edit_message(
            embed=embed_painel("Limpar contra-feitiço", texto),
            view=LimparContramagiasView(self.usuario_id, self.sessao, self.selecionados, self.pagina),
        )

    async def pagina_anterior(self, interaction):
        await self.ir_para_pagina(interaction, self.pagina - 1)

    async def proxima_pagina(self, interaction):
        await self.ir_para_pagina(interaction, self.pagina + 1)

    async def ir_para_pagina(self, interaction, pagina):
        view = LimparContramagiasView(self.usuario_id, self.sessao, self.selecionados, pagina)
        texto = (
            f"{view.resumo_status()}\n"
            f"Remover: **{', '.join(self.selecionados) or '--'}**\n"
            f"Página {view.pagina + 1}/{len(view.paginas)}."
        )
        await interaction.response.edit_message(embed=embed_painel("Limpar contra-feitiço", texto), view=view)

    async def confirmar(self, interaction):
        removidos = set(self.selecionados)
        self.sessao.perfil["contramagia"] = [
            nome for nome in _nomes_contramagia(self.sessao.perfil, "propria")
            if nome not in removidos
        ]
        self.sessao.salvar_rascunho()
        await interaction.response.edit_message(
            embed=resumo_regras_universais(self.sessao),
            view=RegrasUniversaisView(self.usuario_id, self.sessao),
        )

    async def voltar(self, interaction):
        await interaction.response.edit_message(
            embed=resumo_regras_universais(self.sessao),
            view=RegrasUniversaisView(self.usuario_id, self.sessao),
        )


class DetalhesDefesaModal(discord.ui.Modal, title="Detalhes da defesa"):
    def __init__(self, usuario_id, sessao):
        super().__init__()
        self.usuario_id, self.sessao = usuario_id, sessao
        defesa = sessao.perfil.get("defesa", {})
        self.ocasioes = discord.ui.TextInput(
            label="Ataques que bloqueia (Obrigatório)",
            style=discord.TextStyle.paragraph,
            default=", ".join(defesa.get("propriedades", [])) or defesa.get("ocasioes", ""),
            placeholder="Ex.: lampejos, fogo ou dano corpóreo.",
            max_length=900,
        )
        self.ajuste = discord.ui.TextInput(
            label="Aumento de CD se for reação (Opcional)",
            required=False,
            default=str(defesa.get("ajuste_cd_reacao", 0)),
            placeholder="Ex.: 4; use 0 se não houver aumento.",
        )
        self.add_item(self.ocasioes)
        self.add_item(self.ajuste)

    async def on_submit(self,interaction):
        try:
            ajuste=int(str(self.ajuste).strip() or 0)
        except ValueError:
            await interaction.response.send_message("O aumento de CD precisa ser um número inteiro.",ephemeral=True);return
        propriedades=[item.strip() for item in str(self.ocasioes).split(",") if item.strip()]
        self.sessao.perfil["defesa"].update({"ajuste_cd_reacao":ajuste,"ocasioes":str(self.ocasioes).strip(),"propriedades":propriedades})
        self.sessao.salvar_rascunho()
        await interaction.response.edit_message(embed=resumo_defesa_contra(self.sessao),view=DefesaContraView(self.usuario_id,self.sessao))


class DescricaoFeiticoModal(discord.ui.Modal, title="Descrição"):
    def __init__(self,usuario_id,sessao):
        super().__init__();self.usuario_id,self.sessao=usuario_id,sessao
        self.texto=discord.ui.TextInput(label="Descrição narrativa (Obrigatório)",style=discord.TextStyle.paragraph,default=sessao.descricao,placeholder="Ex.: uma descrição narrativa do feitiço, sem dano, duração ou regras.",max_length=4000)
        self.add_item(self.texto)
    async def on_submit(self,interaction):
        self.sessao.descricao=str(self.texto).strip();self.sessao.salvar_rascunho();await interaction.response.edit_message(embed=resumo_perfil(self.sessao),view=EditorFeiticoView(self.usuario_id,self.sessao))


class RevisarFeiticos(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="revisar-feiticos", description="Revisa as mecânicas de combate das fichas de feitiço.")
    @app_commands.default_permissions(manage_guild=True)
    async def revisar_feiticos(self, interaction: discord.Interaction) -> None:
        if not interaction.permissions.manage_guild:
            await interaction.response.send_message("Somente a moderação pode revisar a biblioteca de feitiços.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=embed_painel("Revisar feitiços", "Escolha uma categoria. O progresso é salvo por ficha."),
            view=CategoriasRevisaoView(interaction.user.id),
            ephemeral=True,
        )
