from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from comandos.adicionar import (
    ErroConteudo,
    montar_markdown,
    validar_embeds,
    validar_nome,
)
from comandos.executar import criar_embeds_entrada
from comandos.ficha import (
    nome_mestria_feitico,
    sincronizar_publicacao_personagem,
    texto_guia_descricao,
)
from comandos.ficha_criaturas import (
    ACOES,
    ALCANCES,
    ALVOS,
    CATEGORIAS_EFEITO,
    DESCRICOES_ALCANCES,
    DESCRICOES_ALVOS,
    RECARGAS,
    RESISTENCIAS,
    RESOLUCOES,
    ROLAGENS_ATAQUE,
    TIPOS_FRAQUEZA,
    TIPOS_RESISTENCIA,
    montar_embeds_criatura as montar_embeds_ficha_criatura,
)
from comandos.habilidades import formatar_cabecalho_habilidade, montar_embeds_habilidade
from comandos.interagir import formatar_cabecalho_thread, montar_embeds_criatura
from comandos.preparar import interpretar_pocao, montar_embeds_pocao
from comandos.remover import (
    ItemRemovivel,
    PASTA_BIBLIOTECA,
    classificar_item,
    encontrar_thread_id,
    escrever_atomico,
    localizar_mensagens,
    obter_thread,
)
from utils.biblioteca import interpretar_markdown, normalizar_rotulo
from utils.fichas import (
    GRUPOS_ALFABETICOS_FICHAS,
    FichaPersonagem,
    ReferenciaFicha,
    listar_fichas,
    salvar_ficha,
)
from utils.publicacao_narrativa import destino_narrativo_grupo
from utils.fichas_criaturas import (
    FichaCriatura,
    ReferenciaFichaCriatura,
    efeito_condicao,
    efeito_dano,
    listar_fichas_criaturas,
    salvar_ficha_criatura,
)
from utils.publicacao_fichas import (
    ErroPublicacaoFicha,
    cabecalho_criatura,
    destino_criatura,
    publicar_ou_atualizar_ficha,
)


TEMPO_EDICAO = 30 * 60
RAIZES_BIBLIOTECA_EDITAVEIS = (
    PASTA_BIBLIOTECA / "feitiços",
    PASTA_BIBLIOTECA / "runas",
    PASTA_BIBLIOTECA / "bindrunes",
    PASTA_BIBLIOTECA / "poções",
    PASTA_BIBLIOTECA / "criaturas",
    PASTA_BIBLIOTECA / "Habilidades",
)
CATEGORIAS_EDITAVEIS = (
    "Feitiços",
    "Poções",
    "Criaturas",
    "Habilidades",
    "Descrição de Personagens",
)
EMOJIS_CATEGORIAS_EDITAR = {
    "Feitiços": "🪄",
    "Poções": "🧪",
    "Criaturas": "🐾",
    "Habilidades": "💡",
    "Descrição de Personagens": "📖",
}
SUBCATEGORIAS_HABILIDADES = (
    "Herança Sanguínea",
    "Origem Mágica",
    "Especialização",
)
SECOES_REGISTROS_CRIATURA = {
    "armas",
    "ataques nao magicos",
    "habilidades",
    "fraquezas",
    "resistencias",
}


def listar_itens_biblioteca() -> list[ItemRemovivel]:
    """Catálogo próprio do /edit; não depende do que o /remove permite apagar."""
    itens: list[ItemRemovivel] = []
    for raiz in RAIZES_BIBLIOTECA_EDITAVEIS:
        if not raiz.is_dir():
            continue
        for arquivo in raiz.rglob("*.md"):
            if not arquivo.is_file():
                continue
            relativo = arquivo.relative_to(PASTA_BIBLIOTECA)
            if (
                relativo.parts[0] == "fichas"
                and len(relativo.parts) > 1
                and normalizar_rotulo(relativo.parts[1]) == "configuracoes"
            ):
                continue
            itens.append(classificar_item(arquivo))
    return sorted(itens, key=lambda item: (item.nome.casefold(), item.categoria.casefold()))


def resolver_item_biblioteca(
    valor: str,
) -> tuple[ItemRemovivel | None, list[ItemRemovivel]]:
    procurado = valor.strip().replace("\\", "/")
    itens = listar_itens_biblioteca()
    por_identificador = [
        item
        for item in itens
        if item.identificador.casefold() == procurado.casefold()
    ]
    if por_identificador:
        return por_identificador[0], []
    chave = normalizar_rotulo(procurado)
    por_nome = [
        item
        for item in itens
        if normalizar_rotulo(item.nome) == chave
        or normalizar_rotulo(item.titulo) == chave
    ]
    return (por_nome[0], []) if len(por_nome) == 1 else (None, por_nome)


def itens_da_categoria(categoria: str) -> list[ItemRemovivel]:
    chave = normalizar_rotulo(categoria)
    return [
        item
        for item in listar_itens_biblioteca()
        if normalizar_rotulo(categoria_editavel_item(item)) == chave
    ]


def tipo_principal_item(item: ItemRemovivel) -> str:
    raiz = item.identificador.split("/", 1)[0]
    if raiz in {"feitiços", "runas", "bindrunes"}:
        return "Feitiços"
    if raiz == "poções":
        return "Poções"
    if raiz == "criaturas":
        return "Criaturas"
    if raiz == "Habilidades":
        return "Habilidades"
    return ""


def itens_do_tipo_principal(tipo: str) -> list[ItemRemovivel]:
    chave = normalizar_rotulo(tipo)
    return [
        item
        for item in listar_itens_biblioteca()
        if normalizar_rotulo(tipo_principal_item(item)) == chave
    ]


def paginas_alfabeticas_editaveis(
    itens: list[ItemRemovivel],
) -> list[tuple[str, list[ItemRemovivel]]]:
    paginas: list[tuple[str, list[ItemRemovivel]]] = []
    ordenados = sorted(itens, key=lambda item: item.nome.casefold())
    for grupo in GRUPOS_ALFABETICOS_FICHAS:
        agrupados = [
            item
            for item in ordenados
            if (normalizar_rotulo(item.nome)[:1].upper() or "#") in grupo
        ]
        lotes = [agrupados[i:i + 25] for i in range(0, len(agrupados), 25)] or [[]]
        for indice, lote in enumerate(lotes):
            rotulo = grupo if len(lotes) == 1 else f"{grupo} — {indice + 1}/{len(lotes)}"
            paginas.append((rotulo, lote))
    return paginas


def categorias_feiticos() -> list[str]:
    return sorted(
        {categoria_editavel_item(item) for item in itens_do_tipo_principal("Feitiços")},
        key=str.casefold,
    )


def divisoes_itens(tipo: str, categoria: str = "") -> list[str]:
    itens = itens_do_tipo_principal(tipo)
    if categoria:
        chave = normalizar_rotulo(categoria)
        itens = [
            item for item in itens
            if normalizar_rotulo(categoria_editavel_item(item)) == chave
        ]
    return sorted({item.chave_thread or "Sem classificação" for item in itens}, key=str.casefold)


def itens_filtrados_edicao(
    tipo: str,
    categoria: str = "",
    divisao: str = "",
) -> list[ItemRemovivel]:
    itens = itens_do_tipo_principal(tipo)
    if categoria:
        chave = normalizar_rotulo(categoria)
        itens = [
            item for item in itens
            if normalizar_rotulo(categoria_editavel_item(item)) == chave
        ]
    if divisao:
        chave = normalizar_rotulo(divisao)
        itens = [
            item for item in itens
            if normalizar_rotulo(item.chave_thread or "Sem classificação") == chave
        ]
    return sorted(itens, key=lambda item: item.nome.casefold())


def categoria_editavel_item(item: ItemRemovivel) -> str:
    partes = item.identificador.split("/")
    if partes and partes[0] == "fichas":
        if len(partes) > 1 and partes[1] == "Criaturas":
            return "Fichas de Criatura"
        return "Fichas de Personagem"
    return item.categoria


def _substituir_nome_lista(
    valores: list[str],
    antigo: str,
    novo: str,
) -> bool:
    alterou = False
    chave_antiga = normalizar_rotulo(antigo)
    for indice, valor in enumerate(valores):
        if normalizar_rotulo(valor) != chave_antiga:
            continue
        valores[indice] = novo
        alterou = True
    return alterou


def _descricao_favorito_atualizada(
    item: ItemRemovivel,
    markdown: str,
    nome: str,
) -> str:
    entrada = interpretar_markdown(markdown)
    campos = {
        normalizar_rotulo(rotulo): valor.strip()
        for rotulo, valor in entrada.campos.items()
    }
    raiz = item.identificador.split("/", 1)[0]
    if raiz in {"runas", "bindrunes"}:
        texto = campos.get(normalizar_rotulo("Capacidades Mágicas"), "")
    elif raiz == "poções":
        texto = campos.get(normalizar_rotulo("Efeito"), "")
    else:
        texto = entrada.descricao
    return texto_guia_descricao(texto, nome)


def propagar_edicao_fichas(
    item: ItemRemovivel,
    novo_nome: str,
    markdown: str,
    referencias: list[ReferenciaFicha] | None = None,
) -> list[Path]:
    """Atualiza referências ao item e retorna as fichas que precisam republicação."""
    antigo_nome = item.titulo or item.nome
    chave_antiga = normalizar_rotulo(antigo_nome)
    raiz = item.identificador.split("/", 1)[0]
    referencias = listar_fichas() if referencias is None else referencias
    afetadas: list[Path] = []
    descricao_favorito = (
        _descricao_favorito_atualizada(item, markdown, novo_nome)
        if raiz in {"feitiços", "runas", "bindrunes", "poções"}
        else ""
    )

    for referencia in referencias:
        ficha = FichaPersonagem.carregar(referencia.caminho)
        menciona = False
        alterou = False

        if raiz == "Habilidades":
            categoria = normalizar_rotulo(item.categoria)
            if categoria == normalizar_rotulo("Herança Sanguínea"):
                if normalizar_rotulo(ficha.heranca) == chave_antiga:
                    menciona = True
                    if ficha.heranca != novo_nome:
                        ficha.heranca = novo_nome
                        alterou = True
            elif categoria == normalizar_rotulo("Origem Mágica"):
                menciona = any(
                    normalizar_rotulo(valor) == chave_antiga
                    for valor in ficha.origens_magicas
                )
                alterou |= _substituir_nome_lista(
                    ficha.origens_magicas, antigo_nome, novo_nome
                )
            elif categoria == normalizar_rotulo("Especialização"):
                menciona = any(
                    normalizar_rotulo(valor) == chave_antiga
                    for valor in ficha.especializacoes
                )
                alterou |= _substituir_nome_lista(
                    ficha.especializacoes, antigo_nome, novo_nome
                )
        elif raiz in {"feitiços", "runas", "bindrunes"}:
            mestria_antiga = nome_mestria_feitico(antigo_nome)
            mestria_nova = nome_mestria_feitico(novo_nome)
            if any(
                normalizar_rotulo(valor) == normalizar_rotulo(mestria_antiga)
                for valor in ficha.especializacoes
            ):
                menciona = True
                alterou |= _substituir_nome_lista(
                    ficha.especializacoes, mestria_antiga, mestria_nova
                )
            for registro in ficha.feiticos_favoritos:
                if normalizar_rotulo(registro.get("nome", "")) != chave_antiga:
                    continue
                menciona = True
                if registro.get("nome") != novo_nome:
                    registro["nome"] = novo_nome
                    alterou = True
                if registro.get("categoria") != item.categoria:
                    registro["categoria"] = item.categoria
                    alterou = True
                if registro.get("descricao") != descricao_favorito:
                    registro["descricao"] = descricao_favorito
                    alterou = True
        elif raiz == "poções":
            for registro in ficha.pocoes_favoritas:
                if normalizar_rotulo(registro.get("nome", "")) != chave_antiga:
                    continue
                menciona = True
                if registro.get("nome") != novo_nome:
                    registro["nome"] = novo_nome
                    alterou = True
                if registro.get("descricao") != descricao_favorito:
                    registro["descricao"] = descricao_favorito
                    alterou = True

        for efeito in ficha.efeitos_habilidades_ativos:
            for chave, valor in tuple(efeito.items()):
                if normalizar_rotulo(valor) != chave_antiga:
                    continue
                menciona = True
                efeito[chave] = novo_nome
                alterou = True

        if menciona:
            afetadas.append(referencia.caminho)
        if alterou:
            salvar_ficha(ficha, referencia.caminho)
    return afetadas


def propagar_edicao_fichas_criaturas(
    item: ItemRemovivel,
    novo_nome: str,
    referencias: list[ReferenciaFichaCriatura] | None = None,
) -> list[Path]:
    if item.identificador.split("/", 1)[0] != "criaturas":
        return []
    referencias = listar_fichas_criaturas() if referencias is None else referencias
    antigo_nome = item.titulo or item.nome
    chave_antiga = normalizar_rotulo(antigo_nome)
    afetadas: list[Path] = []
    for referencia in referencias:
        ficha = FichaCriatura.carregar(referencia.caminho)
        if normalizar_rotulo(ficha.origem_biblioteca) != chave_antiga:
            continue
        afetadas.append(referencia.caminho)
        if ficha.origem_biblioteca != novo_nome:
            ficha.origem_biblioteca = novo_nome
            salvar_ficha_criatura(ficha, referencia.caminho)
    return afetadas


def registros_da_secao(valor: str) -> list[dict[str, str]]:
    registros: list[dict[str, str]] = []
    for linha in valor.splitlines():
        conteudo = linha.strip().removeprefix("- ").strip()
        if not conteudo or conteudo == "--":
            continue
        try:
            registro = json.loads(conteudo)
        except json.JSONDecodeError as erro:
            raise ValueError("Esta seção possui um registro antigo inválido e não pode ser editada com segurança.") from erro
        if not isinstance(registro, dict):
            raise ValueError("Esta seção possui um registro que não é um item válido.")
        registros.append({str(chave): str(valor) for chave, valor in registro.items()})
    return registros


def serializar_registros(registros: list[dict[str, str]]) -> str:
    if not registros:
        return "- --"
    return "\n".join(
        f"- {json.dumps(registro, ensure_ascii=False, separators=(',', ':'))}"
        for registro in registros
    )


def eh_ficha_criatura(sessao: "SessaoEdicao") -> bool:
    partes = sessao.item.identificador.split("/")
    return len(partes) > 1 and partes[0] == "fichas" and partes[1] == "Criaturas"


def valor_secao(documento: "DocumentoEditavel", rotulo: str) -> str:
    chave = normalizar_rotulo(rotulo)
    return next((valor for nome, valor in documento.secoes if normalizar_rotulo(nome) == chave), "")


@dataclass
class DocumentoEditavel:
    titulo: str
    secoes: list[tuple[str, str]]

    def markdown(self) -> str:
        return montar_markdown(self.titulo, self.secoes)


@dataclass
class SessaoEdicao:
    usuario_id: int
    item: ItemRemovivel
    documento: DocumentoEditavel
    conteudo_original: str
    thread_id: int | None
    mensagem_id: int | None
    conteudo_publicacao_original: str = ""
    embeds_publicados_originais: list[dict] | None = None
    imagem_publicada: str = ""


def ler_documento(conteudo: str, nome_padrao: str) -> DocumentoEditavel:
    linhas = conteudo.splitlines()
    titulo = nome_padrao
    inicio = 0
    for indice, linha in enumerate(linhas):
        if linha.strip().startswith("# "):
            titulo = linha.strip().removeprefix("# ").strip()
            inicio = indice + 1
            break

    secoes: list[tuple[str, str]] = []
    rotulo: str | None = None
    valores: list[str] = []

    def concluir() -> None:
        nonlocal rotulo, valores
        if rotulo is not None:
            secoes.append((rotulo, "\n".join(valores).strip()))
        rotulo = None
        valores = []

    for linha in linhas[inicio:]:
        limpa = linha.strip()
        eh_rotulo = (
            limpa.endswith(":")
            and limpa[:-1].strip()
            and limpa[0] not in "#>*_-`"
            and len(limpa) <= 100
        )
        if eh_rotulo:
            concluir()
            rotulo = limpa[:-1].strip()
            continue
        if rotulo is not None:
            valores.append(linha)
    concluir()

    if not secoes:
        raise ValueError("Este arquivo não possui seções reconhecíveis para edição segura.")
    return DocumentoEditavel(titulo, secoes)


def chave_habilidade(item: ItemRemovivel) -> str:
    pasta = item.arquivo.parent.name
    mapa = {
        "heranca sanguinea": "heranca_sanguinea",
        "origem magica": "origem_magica",
        "especializacao": "especializacao",
    }
    try:
        return mapa[normalizar_rotulo(pasta)]
    except KeyError as erro:
        raise ValueError("Categoria de habilidade desconhecida.") from erro


def renderizar_documento(
    sessao: SessaoEdicao,
) -> tuple[str, list[discord.Embed]]:
    markdown = sessao.documento.markdown()
    entrada = interpretar_markdown(markdown)
    partes = sessao.item.identificador.split("/")
    raiz = partes[0]

    if raiz == "feitiços":
        tipo = "bindruna" if partes[0] == "bindrunes" else "feitico"
        embeds = criar_embeds_entrada(entrada, tipo, sessao.documento.titulo)
    elif raiz == "runas":
        embeds = criar_embeds_entrada(entrada, "runa", sessao.documento.titulo)
    elif raiz == "bindrunes":
        embeds = criar_embeds_entrada(entrada, "bindruna", sessao.documento.titulo)
    elif raiz == "poções":
        entrada_pocao, tempo, rendimento = interpretar_pocao(markdown)
        embeds = montar_embeds_pocao(
            entrada_pocao,
            sessao.documento.titulo,
            tempo,
            rendimento,
        )
    elif raiz == "criaturas":
        campos = {normalizar_rotulo(k): v for k, v in entrada.campos.items()}
        imagem = campos.get("imagem", "")
        if not imagem.startswith(("http://", "https://", "attachment://")):
            imagem = sessao.imagem_publicada or "attachment://criatura.png"
        embeds = montar_embeds_criatura(entrada, sessao.documento.titulo, imagem)
    elif raiz == "Habilidades":
        embeds = montar_embeds_habilidade(entrada, chave_habilidade(sessao.item))
    elif raiz == "fichas" and len(partes) > 1 and partes[1] == "Criaturas":
        temporaria = FichaCriatura.de_markdown(markdown, sessao.item.arquivo)
        embeds = montar_embeds_ficha_criatura(temporaria)
    else:
        raise ValueError("Esse tipo de item não possui renderizador de edição.")

    validar_embeds(embeds)
    return markdown, embeds


def conteudo_publicacao(sessao: SessaoEdicao) -> str:
    novo_nome = sessao.documento.titulo
    antigo_nome = sessao.item.titulo or sessao.item.nome
    if sessao.conteudo_publicacao_original:
        return sessao.conteudo_publicacao_original.replace(antigo_nome, novo_nome, 1)

    partes = sessao.item.identificador.split("/")
    if partes[0] == "criaturas":
        entrada = interpretar_markdown(sessao.documento.markdown())
        campos = {normalizar_rotulo(k): v for k, v in entrada.campos.items()}
        return formatar_cabecalho_thread(
            novo_nome,
            campos.get("periculosidade", partes[1] if len(partes) > 1 else ""),
        )
    if partes[0] == "Habilidades":
        categoria = partes[1]
        return formatar_cabecalho_habilidade(novo_nome, categoria)
    return ""


class ViewEdicao(discord.ui.View):
    def __init__(self, sessao: SessaoEdicao):
        super().__init__(timeout=TEMPO_EDICAO)
        self.sessao = sessao

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.sessao.usuario_id:
            return True
        await interaction.response.send_message(
            "Somente quem iniciou este `/edit` pode usar os controles.",
            ephemeral=True,
        )
        return False


def embed_editor(sessao: SessaoEdicao) -> discord.Embed:
    embed = discord.Embed(
        title="✏️ Editar item",
        description=(
            f"**{sessao.documento.titulo}** — {sessao.item.categoria}\n"
            "Escolha uma seção para alterar. Nada será salvo antes da prévia e da confirmação."
        ),
    )
    embed.add_field(name="Seções", value=str(len(sessao.documento.secoes)), inline=True)
    embed.add_field(name="Arquivo", value=f"`{sessao.item.identificador}`", inline=False)
    return embed


class EditorItemView(ViewEdicao):
    def __init__(self, sessao: SessaoEdicao, pagina: int = 0):
        super().__init__(sessao)
        paginas = [sessao.documento.secoes[i:i + 25] for i in range(0, len(sessao.documento.secoes), 25)]
        self.paginas = paginas
        self.pagina = max(0, min(pagina, len(paginas) - 1))
        inicio = self.pagina * 25
        seletor = discord.ui.Select(
            placeholder=f"Seção — página {self.pagina + 1}/{len(paginas)}",
            options=[
                discord.SelectOption(
                    label=rotulo[:100],
                    value=str(inicio + indice),
                    description=(valor.replace("\n", " ")[:100] or "Seção vazia"),
                )
                for indice, (rotulo, valor) in enumerate(paginas[self.pagina])
            ],
            row=0,
        )
        seletor.callback = self.editar_secao
        self.seletor = seletor
        self.add_item(seletor)

        renomear = discord.ui.Button(label="Renomear", style=discord.ButtonStyle.secondary, row=1)
        renomear.callback = self.renomear
        self.add_item(renomear)
        previa = discord.ui.Button(label="Prévia", style=discord.ButtonStyle.success, emoji="✅", row=1)
        previa.callback = self.previa
        self.add_item(previa)
        cancelar = discord.ui.Button(label="Cancelar", style=discord.ButtonStyle.danger, row=1)
        cancelar.callback = self.cancelar
        self.add_item(cancelar)
        if len(paginas) > 1:
            anterior = discord.ui.Button(label="Anterior", style=discord.ButtonStyle.secondary, disabled=self.pagina == 0, row=2)
            proxima = discord.ui.Button(label="Próxima", style=discord.ButtonStyle.secondary, disabled=self.pagina == len(paginas) - 1, row=2)
            anterior.callback = self.anterior
            proxima.callback = self.proxima
            self.add_item(anterior)
            self.add_item(proxima)

    async def editar_secao(self, interaction: discord.Interaction) -> None:
        indice = int(self.seletor.values[0])
        rotulo, valor = self.sessao.documento.secoes[indice]
        if eh_ficha_criatura(self.sessao) and normalizar_rotulo(rotulo) in SECOES_REGISTROS_CRIATURA:
            try:
                registros = registros_da_secao(valor)
            except ValueError as erro:
                await interaction.response.send_message(str(erro), ephemeral=True)
                return
            if not registros:
                await interaction.response.send_message(
                    f"A seção **{rotulo}** ainda não possui itens para editar.",
                    ephemeral=True,
                )
                return
            await interaction.response.edit_message(
                embed=embed_lista_registros(rotulo, registros),
                view=ListaRegistrosView(self.sessao, indice, registros),
            )
            return
        if len(valor) > 4000:
            await interaction.response.send_message(
                f"A seção **{rotulo}** excede 4.000 caracteres e precisa ser dividida antes da edição pelo Discord.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(EditarSecaoModal(self.sessao, indice))

    async def renomear(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RenomearItemModal(self.sessao))

    async def previa(self, interaction: discord.Interaction) -> None:
        try:
            _, embeds = renderizar_documento(self.sessao)
        except (ValueError, ErroConteudo, OSError) as erro:
            await interaction.response.send_message(f"Não consegui montar a prévia: {erro}", ephemeral=True)
            return
        embeds = [discord.Embed.from_dict(embed.to_dict()) for embed in embeds]
        embeds[0].set_author(name="✏️ Prévia da edição • Confira antes de salvar")
        await interaction.response.edit_message(
            content=conteudo_publicacao(self.sessao) or None,
            embeds=embeds,
            view=ConfirmarEdicaoView(self.sessao),
        )

    async def cancelar(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(
            content=None,
            embed=discord.Embed(title="Edição cancelada", description="Nenhuma alteração foi salva."),
            view=None,
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=EditorItemView(self.sessao, self.pagina - 1))

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=EditorItemView(self.sessao, self.pagina + 1))


class EditarSecaoModal(discord.ui.Modal):
    def __init__(self, sessao: SessaoEdicao, indice: int):
        rotulo, valor = sessao.documento.secoes[indice]
        super().__init__(title=f"Editar — {rotulo}"[:45])
        self.sessao = sessao
        self.indice = indice
        self.valor = discord.ui.TextInput(
            label=rotulo[:45],
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=4000,
            default=valor or None,
        )
        self.add_item(self.valor)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        rotulo, _ = self.sessao.documento.secoes[self.indice]
        self.sessao.documento.secoes[self.indice] = (rotulo, str(self.valor.value).strip())
        await interaction.response.edit_message(embed=embed_editor(self.sessao), view=EditorItemView(self.sessao))


def nome_registro(registro: dict[str, str], indice: int) -> str:
    return registro.get("nome") or registro.get("categoria") or f"Item {indice + 1}"


def embed_lista_registros(rotulo: str, registros: list[dict[str, str]]) -> discord.Embed:
    return discord.Embed(
        title=f"✏️ {rotulo}",
        description=(
            "Escolha o item que deseja editar. Cada campo será apresentado separadamente; "
            "não é necessário alterar o código interno.\n\n"
            + "\n".join(f"- **{nome_registro(registro, indice)}**" for indice, registro in enumerate(registros))
        ),
    )


def opcoes_campo_registro(rotulo: str, campo: str) -> dict[str, str]:
    secao = normalizar_rotulo(rotulo)
    chave = normalizar_rotulo(campo)
    if chave in {"tipo de acao", "acao"}:
        return {
            "Completa": "Consome as ações padrão e de movimento do turno.",
            "Padrão": "Executa a principal ação da criatura no turno.",
            "Movimento": "Usa a ação destinada a movimento ou reposicionamento.",
            "Livre": "Não consome as ações principais do turno.",
            "Bônus": "Ação rápida adicional permitida pela mecânica.",
            "Reação": "Usada em resposta a um gatilho fora do turno.",
        }
    if chave == "rolagem de ataque":
        return dict(ROLAGENS_ATAQUE)
    if chave == "categoria" and secao in {"fraquezas", "resistencias"}:
        return {valor: f"Aplica esta característica a efeitos de {valor}." for valor in CATEGORIAS_EFEITO}
    if chave == "tipo" and secao == "fraquezas":
        return dict(TIPOS_FRAQUEZA)
    if chave == "tipo" and secao == "resistencias":
        return dict(TIPOS_RESISTENCIA)
    if chave == "tipo" and secao == "habilidades":
        return {
            "Passiva": "Permanece ativa sem exigir uma ativação.",
            "Ativa": "Precisa ser ativada pela criatura.",
            "Reação": "É ativada em resposta a um gatilho.",
        }
    if chave == "modo do custo":
        return {
            "Por ativação": "Paga o custo sempre que a habilidade for ativada.",
            "Por rodada sustentada": "Paga o custo a cada rodada mantida.",
            "Por acúmulo": "Cada pagamento concede um acúmulo do efeito.",
            "Sem custo": "Não consome PH para funcionar.",
        }
    if chave in {"alcance", "alcance/alvo"}:
        return {valor: "Define até onde o efeito pode alcançar." for valor in ALCANCES}
    if chave == "alvo":
        return dict(DESCRICOES_ALVOS)
    if chave in {"resistencia", "teste de resistencia"}:
        return {
            valor: {
                "Reflexo": "Permite esquivar ou escapar de restrições.",
                "Fortitude": "Permite defender ou resistir a impactos físicos.",
                "Vontade": "Permite resistir a efeitos mentais e de controle.",
                "Nenhuma": "O efeito não concede um teste de resistência.",
            }.get(valor, "Define o teste usado para resistir.")
            for valor in RESISTENCIAS
        }
    if chave == "resolucao":
        return {valor: "Define como a habilidade acerta ou produz seu efeito." for valor in RESOLUCOES}
    if chave == "recarga":
        return {valor: "Define quando a habilidade ou ataque poderá ser usado novamente." for valor in RECARGAS}
    return {}


class ListaRegistrosView(ViewEdicao):
    def __init__(self, sessao: SessaoEdicao, indice_secao: int, registros: list[dict[str, str]]):
        super().__init__(sessao)
        self.indice_secao = indice_secao
        self.registros = registros
        rotulo, _ = sessao.documento.secoes[indice_secao]
        self.rotulo = rotulo
        seletor = discord.ui.Select(
            placeholder=f"Escolha em {rotulo}"[:150],
            options=[
                discord.SelectOption(
                    label=nome_registro(registro, indice)[:100],
                    value=str(indice),
                    description=(registro.get("descrição") or registro.get("efeito") or registro.get("dano") or "Editar este item")[:100],
                )
                for indice, registro in enumerate(registros[:25])
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar às seções", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        indice = int(self.seletor.values[0])
        await interaction.response.edit_message(
            embed=embed_registro(self.rotulo, self.registros[indice]),
            view=RegistroView(self.sessao, self.indice_secao, self.registros, indice),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(embed=embed_editor(self.sessao), view=EditorItemView(self.sessao))


def embed_registro(rotulo: str, registro: dict[str, str]) -> discord.Embed:
    embed = discord.Embed(
        title=f"✏️ {registro.get('nome') or registro.get('categoria') or rotulo}",
        description="Escolha abaixo qual campo deseja modificar.",
    )
    for campo, valor in registro.items():
        embed.add_field(name=campo.replace("_", " ").capitalize(), value=valor or "--", inline=False)
    return embed


class RegistroView(ViewEdicao):
    def __init__(self, sessao: SessaoEdicao, indice_secao: int, registros: list[dict[str, str]], indice_registro: int):
        super().__init__(sessao)
        self.indice_secao = indice_secao
        self.registros = registros
        self.indice_registro = indice_registro
        self.rotulo = sessao.documento.secoes[indice_secao][0]
        registro = registros[indice_registro]
        seletor = discord.ui.Select(
            placeholder="Escolha o campo para editar",
            options=[
                discord.SelectOption(label=campo.replace("_", " ").capitalize()[:100], value=campo, description=(valor or "Campo vazio")[:100])
                for campo, valor in list(registro.items())[:25]
            ],
        )
        seletor.callback = self.selecionar_campo
        self.seletor = seletor
        self.add_item(seletor)
        excluir = discord.ui.Button(label="Excluir item", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
        excluir.callback = self.excluir
        self.add_item(excluir)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    def sincronizar(self) -> None:
        rotulo, _ = self.sessao.documento.secoes[self.indice_secao]
        self.sessao.documento.secoes[self.indice_secao] = (rotulo, serializar_registros(self.registros))

    async def selecionar_campo(self, interaction: discord.Interaction) -> None:
        campo = self.seletor.values[0]
        opcoes = opcoes_campo_registro(self.rotulo, campo)
        if opcoes:
            await interaction.response.edit_message(
                embed=discord.Embed(title=f"Editar {campo}", description="Escolha o novo valor. As descrições indicam o efeito de cada opção."),
                view=CampoOpcoesView(self.sessao, self.indice_secao, self.registros, self.indice_registro, campo, opcoes),
            )
            return
        await interaction.response.send_modal(
            EditarCampoRegistroModal(self.sessao, self.indice_secao, self.registros, self.indice_registro, campo)
        )

    async def excluir(self, interaction: discord.Interaction) -> None:
        self.registros.pop(self.indice_registro)
        self.sincronizar()
        if self.registros:
            await interaction.response.edit_message(embed=embed_lista_registros(self.rotulo, self.registros), view=ListaRegistrosView(self.sessao, self.indice_secao, self.registros))
        else:
            await interaction.response.edit_message(embed=embed_editor(self.sessao), view=EditorItemView(self.sessao))

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(embed=embed_lista_registros(self.rotulo, self.registros), view=ListaRegistrosView(self.sessao, self.indice_secao, self.registros))


class EditarCampoRegistroModal(discord.ui.Modal):
    def __init__(self, sessao: SessaoEdicao, indice_secao: int, registros: list[dict[str, str]], indice_registro: int, campo: str):
        super().__init__(title=f"Editar — {campo}"[:45])
        self.sessao = sessao
        self.indice_secao = indice_secao
        self.registros = registros
        self.indice_registro = indice_registro
        self.campo = campo
        atual = registros[indice_registro].get(campo, "")
        self.valor = discord.ui.TextInput(
            label=campo.replace("_", " ")[:45],
            style=discord.TextStyle.paragraph if len(atual) > 100 or campo in {"descrição", "efeito", "dano ou efeito"} else discord.TextStyle.short,
            required=False,
            max_length=1000,
            default=atual or None,
        )
        self.add_item(self.valor)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.registros[self.indice_registro][self.campo] = str(self.valor.value).strip()
        rotulo, _ = self.sessao.documento.secoes[self.indice_secao]
        self.sessao.documento.secoes[self.indice_secao] = (rotulo, serializar_registros(self.registros))
        await interaction.response.edit_message(
            embed=embed_registro(rotulo, self.registros[self.indice_registro]),
            view=RegistroView(self.sessao, self.indice_secao, self.registros, self.indice_registro),
        )


class CampoOpcoesView(ViewEdicao):
    def __init__(self, sessao: SessaoEdicao, indice_secao: int, registros: list[dict[str, str]], indice_registro: int, campo: str, opcoes: dict[str, str]):
        super().__init__(sessao)
        self.indice_secao = indice_secao
        self.registros = registros
        self.indice_registro = indice_registro
        self.campo = campo
        seletor = discord.ui.Select(
            placeholder=f"Novo valor de {campo}"[:150],
            options=[discord.SelectOption(label=valor[:100], value=valor, description=descricao[:100]) for valor, descricao in list(opcoes.items())[:25]],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        novo_valor = self.seletor.values[0]
        registro = self.registros[self.indice_registro]
        registro[self.campo] = novo_valor
        rotulo, _ = self.sessao.documento.secoes[self.indice_secao]
        secao = normalizar_rotulo(rotulo)
        if normalizar_rotulo(self.campo) == "tipo" and secao in {"fraquezas", "resistencias"}:
            fraqueza = secao == "fraquezas"
            perigo = valor_secao(self.sessao.documento, "Periculosidade")
            if novo_valor in {"Aumento de Dano Sofrido", "Redução de Dano Sofrido"}:
                registro["efeito"] = efeito_dano(perigo, fraqueza)
            elif novo_valor == "Imunidade a efeito":
                registro["efeito"] = "É completamente imune ao efeito e não realiza teste."
            else:
                registro["efeito"] = efeito_condicao(fraqueza)
        self.sessao.documento.secoes[self.indice_secao] = (rotulo, serializar_registros(self.registros))
        await interaction.response.edit_message(
            embed=embed_registro(rotulo, self.registros[self.indice_registro]),
            view=RegistroView(self.sessao, self.indice_secao, self.registros, self.indice_registro),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        rotulo = self.sessao.documento.secoes[self.indice_secao][0]
        await interaction.response.edit_message(
            embed=embed_registro(rotulo, self.registros[self.indice_registro]),
            view=RegistroView(self.sessao, self.indice_secao, self.registros, self.indice_registro),
        )


class RenomearItemModal(discord.ui.Modal):
    def __init__(self, sessao: SessaoEdicao):
        super().__init__(title="Renomear item")
        self.sessao = sessao
        self.nome = discord.ui.TextInput(label="Nome", max_length=100, default=sessao.documento.titulo)
        self.add_item(self.nome)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            self.sessao.documento.titulo = validar_nome(str(self.nome.value))
        except ErroConteudo as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await interaction.response.edit_message(embed=embed_editor(self.sessao), view=EditorItemView(self.sessao))


class ConfirmarEdicaoView(ViewEdicao):
    def __init__(self, sessao: SessaoEdicao):
        super().__init__(sessao)
        self.concluido = False

    @discord.ui.button(label="Salvar alterações", style=discord.ButtonStyle.success, emoji="✅")
    async def salvar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.concluido:
            await interaction.response.send_message("Esta edição já foi encerrada.", ephemeral=True)
            return
        await interaction.response.defer()
        atual, ambiguos = resolver_item_biblioteca(self.sessao.item.identificador)
        if atual is None or ambiguos or not atual.arquivo.is_file():
            await interaction.edit_original_response(content="O item mudou ou não existe mais. Recomece o `/edit`.", embeds=[], view=None)
            return
        conteudo_atual = atual.arquivo.read_text(encoding="utf-8-sig")
        if conteudo_atual != self.sessao.conteudo_original:
            await interaction.edit_original_response(content="O item foi alterado durante a edição. Nada foi salvo; recomece o `/edit`.", embeds=[], view=None)
            return
        try:
            markdown, embeds = renderizar_documento(self.sessao)
            nome = validar_nome(self.sessao.documento.titulo)
            destino = atual.arquivo.with_name(f"{nome}.md")
            if destino.resolve() != atual.arquivo.resolve() and destino.exists():
                raise ValueError("Já existe outro item com esse nome nessa categoria.")
            mensagens = await localizar_mensagens(interaction.client, atual, self.sessao.thread_id)
            ids = [mensagem.id for mensagem in mensagens]
            esperados = [self.sessao.mensagem_id] if self.sessao.mensagem_id else []
            if ids != esperados:
                raise ValueError("A publicação mudou durante a edição. Recomece o `/edit`.")
        except (ValueError, ErroConteudo, OSError) as erro:
            await interaction.edit_original_response(content=f"Não foi possível salvar: {erro}", embeds=[], view=None)
            return

        nova_mensagem = None
        escrever_atomico(destino, markdown)
        try:
            publicacao = conteudo_publicacao(self.sessao) or None
            if mensagens:
                await mensagens[0].edit(content=publicacao, embeds=embeds)
            elif self.sessao.thread_id is not None:
                canal = await obter_thread(interaction.client, self.sessao.thread_id)
                nova_mensagem = await canal.send(
                    content=publicacao,
                    embeds=embeds,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            if destino.resolve() != atual.arquivo.resolve():
                atual.arquivo.unlink()
        except (OSError, discord.HTTPException) as erro:
            if destino.resolve() != atual.arquivo.resolve():
                destino.unlink(missing_ok=True)
            escrever_atomico(atual.arquivo, self.sessao.conteudo_original)
            if mensagens and self.sessao.embeds_publicados_originais is not None:
                try:
                    await mensagens[0].edit(
                        content=self.sessao.conteudo_publicacao_original or None,
                        embeds=[
                            discord.Embed.from_dict(dados)
                            for dados in self.sessao.embeds_publicados_originais
                        ],
                    )
                except discord.HTTPException:
                    pass
            if nova_mensagem is not None:
                try:
                    await nova_mensagem.delete()
                except discord.HTTPException:
                    pass
            await interaction.edit_original_response(
                content=f"A atualização falhou e o arquivo original foi restaurado: {erro}",
                embeds=[],
                view=None,
            )
            return

        fichas_afetadas: list[Path] = []
        criaturas_afetadas: list[Path] = []
        falha_propagacao = ""
        try:
            fichas_afetadas = propagar_edicao_fichas(
                atual,
                nome,
                markdown,
            )
            for caminho_ficha in fichas_afetadas:
                ficha = FichaPersonagem.carregar(caminho_ficha)
                await sincronizar_publicacao_personagem(
                    interaction,
                    ficha,
                    caminho_ficha,
                )
            criaturas_afetadas = propagar_edicao_fichas_criaturas(atual, nome)
            for caminho_criatura in criaturas_afetadas:
                ficha_criatura = FichaCriatura.carregar(caminho_criatura)
                if not ficha_criatura.mensagem_discord_id:
                    continue
                mensagem_criatura = await publicar_ou_atualizar_ficha(
                    interaction.client,
                    destino_criatura(),
                    montar_embeds_ficha_criatura(ficha_criatura),
                    ficha_criatura.mensagem_discord_id,
                    cabecalho_criatura(
                        ficha_criatura.nome,
                        ficha_criatura.periculosidade,
                    ),
                )
                if ficha_criatura.mensagem_discord_id != mensagem_criatura.id:
                    ficha_criatura.mensagem_discord_id = mensagem_criatura.id
                    salvar_ficha_criatura(ficha_criatura, caminho_criatura)
        except (ErroPublicacaoFicha, OSError, ValueError, discord.HTTPException) as erro:
            falha_propagacao = str(erro)

        self.concluido = True
        self.stop()
        total_fichas = len(fichas_afetadas) + len(criaturas_afetadas)
        resumo_fichas = (
            f" **{total_fichas} ficha(s)** relacionada(s) também foram atualizadas."
            if total_fichas
            else ""
        )
        if falha_propagacao:
            resumo_fichas += (
                " ⚠️ A biblioteca foi salva, mas a propagação para as fichas falhou: "
                + falha_propagacao
            )
        await interaction.edit_original_response(
            content=(
                f"✅ **{nome}** foi atualizado na biblioteca"
                + (" e no Discord." if self.sessao.thread_id else ".")
                + resumo_fichas
            ),
            embeds=[],
            view=None,
        )

    @discord.ui.button(label="Voltar à edição", style=discord.ButtonStyle.secondary)
    async def voltar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content=None, embed=embed_editor(self.sessao), view=EditorItemView(self.sessao))

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger)
    async def cancelar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=None, embed=discord.Embed(title="Edição cancelada", description="Nenhuma alteração foi salva."), view=None)


class ViewNavegacaoEditar(discord.ui.View):
    def __init__(self, cog: "Editar", usuario_id: int):
        super().__init__(timeout=TEMPO_EDICAO)
        self.cog = cog
        self.usuario_id = usuario_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message(
            "Somente quem iniciou este `/edit` pode usar os controles.",
            ephemeral=True,
        )
        return False


def embed_navegacao(titulo: str, descricao: str) -> discord.Embed:
    return discord.Embed(title=f"✏️ {titulo}", description=descricao)


def rotulo_thread_narrativa(ficha: FichaPersonagem) -> str:
    if ficha.grupo == "Figuras de Autoridade":
        return "Figuras de Autoridade"
    if ficha.grupo == "NPCs":
        return "NPCs Gerais"
    return ficha.casa if ficha.grupo == "Players" else ficha.grupo


def fichas_narrativas_por_thread() -> dict[str, list[ReferenciaFicha]]:
    grupos: dict[str, list[ReferenciaFicha]] = {}
    for referencia in listar_fichas():
        ficha = FichaPersonagem.carregar(referencia.caminho)
        if destino_narrativo_grupo(ficha.grupo, ficha.casa) is None:
            continue
        grupos.setdefault(rotulo_thread_narrativa(ficha), []).append(referencia)
    for referencias in grupos.values():
        referencias.sort(key=lambda ref: ref.nome.casefold())
    return dict(sorted(grupos.items(), key=lambda item: item[0].casefold()))


def campos_descricao_narrativa(ficha: FichaPersonagem) -> list[tuple[str, str]]:
    informacoes = {
        normalizar_rotulo(item.get("titulo", "")): item.get("descricao", "").strip()
        for item in ficha.informacoes
    }
    if ficha.grupo == "Figuras de Autoridade":
        return [
            ("Cargo", informacoes.get("cargo", "")),
            ("Valores", informacoes.get("valores", "")),
            ("Personalidade", informacoes.get("personalidade", "")),
            ("Sobre", ficha.sobre_narrativo.strip() or informacoes.get("sobre", "")),
        ]
    if ficha.grupo == "NPCs":
        return [("Sobre", informacoes.get("sobre", ""))]
    altura_idade = informacoes.get("altura e idade", "")
    if not altura_idade and ficha.altura != "--" and ficha.idade != "--":
        altura_idade = f"{ficha.altura} com {ficha.idade} Anos"
    return [
        ("Cursando", informacoes.get("cursando", "") or ficha.ano),
        ("Altura e Idade", altura_idade),
    ]


def definir_campo_narrativo(ficha: FichaPersonagem, titulo: str, valor: str) -> None:
    if titulo == "Sobre" and ficha.grupo == "Figuras de Autoridade":
        ficha.sobre_narrativo = valor
        return
    chave = normalizar_rotulo(titulo)
    for informacao in ficha.informacoes:
        if normalizar_rotulo(informacao.get("titulo", "")) == chave:
            informacao["titulo"] = titulo
            informacao["descricao"] = valor
            return
    ficha.informacoes.append({"titulo": titulo, "descricao": valor})


class CategoriasEditarView(ViewNavegacaoEditar):
    def __init__(self, cog: "Editar", usuario_id: int):
        super().__init__(cog, usuario_id)
        tipos = list(CATEGORIAS_EDITAVEIS)
        if not fichas_narrativas_por_thread():
            tipos.remove("Descrição de Personagens")
        seletor = discord.ui.Select(
            placeholder="Categoria da Biblioteca",
            options=[
                discord.SelectOption(
                    label=tipo,
                    value=tipo,
                    emoji=EMOJIS_CATEGORIAS_EDITAR[tipo],
                    description={
                        "Feitiços": "Feitiços, Runas e Bindrunes organizados por categoria.",
                        "Poções": "Poções organizadas pelo ano de desbloqueio.",
                        "Criaturas": "Criaturas organizadas por periculosidade.",
                        "Habilidades": "Heranças, Origens Mágicas e Especializações.",
                        "Descrição de Personagens": "Campos das fichas narrativas publicadas nas threads.",
                    }[tipo],
                )
                for tipo in tipos
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        tipo = self.seletor.values[0]
        if tipo == "Habilidades":
            view = SubcategoriasEditarView(self.cog, self.usuario_id, tipo, SUBCATEGORIAS_HABILIDADES)
            texto = "Escolha a categoria da habilidade e depois a habilidade."
        elif tipo == "Feitiços":
            view = SubcategoriasEditarView(self.cog, self.usuario_id, tipo, categorias_feiticos())
            texto = "Escolha a categoria, o ano de desbloqueio e depois o feitiço."
        elif tipo in {"Poções", "Criaturas"}:
            view = DivisoesEditarView(self.cog, self.usuario_id, tipo)
            texto = (
                "Escolha o ano de desbloqueio e depois a poção."
                if tipo == "Poções"
                else "Escolha a periculosidade e depois a faixa alfabética."
            )
        else:
            view = ThreadsNarrativasEditarView(self.cog, self.usuario_id)
            texto = "Escolha a thread e depois o personagem pela faixa alfabética."
        await interaction.response.edit_message(
            embed=embed_navegacao(f"Editar — {tipo}", texto),
            view=view,
        )


class SubcategoriasEditarView(ViewNavegacaoEditar):
    def __init__(self, cog: "Editar", usuario_id: int, tipo: str, categorias) -> None:
        super().__init__(cog, usuario_id)
        self.tipo = tipo
        seletor = discord.ui.Select(
            placeholder="Categoria",
            options=[discord.SelectOption(label=valor, value=valor) for valor in categorias],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar às categorias", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        categoria = self.seletor.values[0]
        if self.tipo == "Feitiços":
            view = DivisoesEditarView(self.cog, self.usuario_id, self.tipo, categoria)
            descricao = "Escolha o ano de desbloqueio e depois o feitiço."
            if normalizar_rotulo(categoria) == normalizar_rotulo("Arte das Trevas"):
                descricao = "Escolha a vertente de Arte das Trevas e depois o feitiço."
        else:
            itens = itens_filtrados_edicao(self.tipo, categoria)
            view = ItensEditarAlfabeticosView(self.cog, self.usuario_id, self.tipo, categoria, "", itens)
            descricao = "Escolha a faixa alfabética e depois a habilidade."
        await interaction.response.edit_message(
            embed=embed_navegacao(f"Editar — {categoria}", descricao),
            view=view,
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_navegacao("Editar item", "Escolha primeiro a categoria da biblioteca."),
            view=CategoriasEditarView(self.cog, self.usuario_id),
        )


class DivisoesEditarView(ViewNavegacaoEditar):
    def __init__(self, cog: "Editar", usuario_id: int, tipo: str, categoria: str = "") -> None:
        super().__init__(cog, usuario_id)
        self.tipo = tipo
        self.categoria = categoria
        rotulo = "Periculosidade" if tipo == "Criaturas" else "Ano de desbloqueio"
        if normalizar_rotulo(categoria) == normalizar_rotulo("Arte das Trevas"):
            rotulo = "Vertente de Arte das Trevas"
        seletor = discord.ui.Select(
            placeholder=rotulo,
            options=[discord.SelectOption(label=valor, value=valor) for valor in divisoes_itens(tipo, categoria)],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        divisao = self.seletor.values[0]
        itens = itens_filtrados_edicao(self.tipo, self.categoria, divisao)
        await interaction.response.edit_message(
            embed=embed_navegacao(f"Editar — {divisao}", "Escolha a faixa alfabética e depois o item."),
            view=ItensEditarAlfabeticosView(
                self.cog, self.usuario_id, self.tipo, self.categoria, divisao, itens
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        if self.categoria:
            categorias = categorias_feiticos() if self.tipo == "Feitiços" else SUBCATEGORIAS_HABILIDADES
            view = SubcategoriasEditarView(self.cog, self.usuario_id, self.tipo, categorias)
        else:
            view = CategoriasEditarView(self.cog, self.usuario_id)
        await interaction.response.edit_message(
            embed=embed_navegacao("Editar item", "Escolha novamente uma opção."),
            view=view,
        )


class ItensEditarAlfabeticosView(ViewNavegacaoEditar):
    def __init__(self, cog: "Editar", usuario_id: int, tipo: str, categoria: str, divisao: str, itens: list[ItemRemovivel], pagina: int | None = None) -> None:
        super().__init__(cog, usuario_id)
        self.tipo, self.categoria, self.divisao, self.itens_disponiveis = tipo, categoria, divisao, itens
        self.paginas = paginas_alfabeticas_editaveis(itens)
        if pagina is None:
            pagina = next((i for i, (_, lote) in enumerate(self.paginas) if lote), 0)
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        rotulo, lote = self.paginas[self.pagina]
        faixas = discord.ui.Select(
            placeholder=f"Faixa alfabética — {rotulo}",
            options=[
                discord.SelectOption(label=nome, value=str(i), description=f"{len(valores)} item(ns)." if valores else "Faixa reservada para itens futuros.", default=i == self.pagina)
                for i, (nome, valores) in enumerate(self.paginas)
            ], row=0,
        )
        faixas.callback = self.selecionar_faixa
        self.faixas = faixas
        self.add_item(faixas)
        if lote:
            itens_select = discord.ui.Select(
                placeholder=f"Itens — {rotulo}",
                options=[discord.SelectOption(label=item.nome[:100], value=item.identificador, description=item.categoria[:100]) for item in lote],
                row=1,
            )
            itens_select.callback = self.selecionar_item
            self.itens_select = itens_select
            self.add_item(itens_select)
        voltar = discord.ui.Button(label="Voltar", style=discord.ButtonStyle.secondary, row=2)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar_faixa(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=ItensEditarAlfabeticosView(
            self.cog, self.usuario_id, self.tipo, self.categoria, self.divisao,
            self.itens_disponiveis, int(self.faixas.values[0])
        ))

    async def selecionar_item(self, interaction: discord.Interaction) -> None:
        encontrado, _ = resolver_item_biblioteca(self.itens_select.values[0])
        if encontrado is None:
            await interaction.response.send_message("Esse item não foi encontrado na biblioteca.", ephemeral=True)
            return
        await self.cog.abrir_item(interaction, encontrado)

    async def voltar(self, interaction: discord.Interaction) -> None:
        if self.divisao:
            view = DivisoesEditarView(self.cog, self.usuario_id, self.tipo, self.categoria)
        elif self.categoria:
            categorias = categorias_feiticos() if self.tipo == "Feitiços" else SUBCATEGORIAS_HABILIDADES
            view = SubcategoriasEditarView(self.cog, self.usuario_id, self.tipo, categorias)
        else:
            view = CategoriasEditarView(self.cog, self.usuario_id)
        await interaction.response.edit_message(
            embed=embed_navegacao("Editar item", "Escolha novamente uma opção."), view=view
        )


def paginas_referencias_narrativas(referencias: list[ReferenciaFicha]):
    paginas = []
    for grupo in GRUPOS_ALFABETICOS_FICHAS:
        lote = [ref for ref in referencias if (normalizar_rotulo(ref.nome)[:1].upper() or "#") in grupo]
        paginas.append((grupo, lote))
    return paginas


class ThreadsNarrativasEditarView(ViewNavegacaoEditar):
    def __init__(self, cog: "Editar", usuario_id: int) -> None:
        super().__init__(cog, usuario_id)
        grupos = fichas_narrativas_por_thread()
        seletor = discord.ui.Select(
            placeholder="Thread do personagem",
            options=[discord.SelectOption(label=nome, value=nome, description=f"{len(refs)} personagem(ns).") for nome, refs in grupos.items()],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar às categorias", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        thread = self.seletor.values[0]
        referencias = fichas_narrativas_por_thread()[thread]
        await interaction.response.edit_message(
            embed=embed_navegacao(f"Descrição de Personagens — {thread}", "Escolha a faixa alfabética e depois o personagem."),
            view=PersonagensNarrativosEditarView(self.cog, self.usuario_id, thread, referencias),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_navegacao("Editar item", "Escolha primeiro a categoria da biblioteca."),
            view=CategoriasEditarView(self.cog, self.usuario_id),
        )


class PersonagensNarrativosEditarView(ViewNavegacaoEditar):
    def __init__(self, cog: "Editar", usuario_id: int, thread: str, referencias: list[ReferenciaFicha], pagina: int | None = None) -> None:
        super().__init__(cog, usuario_id)
        self.thread, self.referencias = thread, referencias
        self.paginas = paginas_referencias_narrativas(referencias)
        if pagina is None:
            pagina = next((i for i, (_, lote) in enumerate(self.paginas) if lote), 0)
        self.pagina = pagina
        rotulo, lote = self.paginas[pagina]
        faixas = discord.ui.Select(
            placeholder=f"Faixa alfabética — {rotulo}",
            options=[discord.SelectOption(label=nome, value=str(i), description=f"{len(valores)} personagem(ns)." if valores else "Faixa reservada para personagens futuros.", default=i == pagina) for i, (nome, valores) in enumerate(self.paginas)], row=0,
        )
        faixas.callback = self.selecionar_faixa
        self.faixas = faixas
        self.add_item(faixas)
        if lote:
            personagens = discord.ui.Select(
                placeholder=f"Personagens — {rotulo}",
                options=[discord.SelectOption(label=ref.nome[:100], value=str(i)) for i, ref in enumerate(lote)], row=1,
            )
            personagens.callback = self.selecionar_personagem
            self.personagens = personagens
            self.lote = lote
            self.add_item(personagens)
        voltar = discord.ui.Button(label="Voltar às threads", style=discord.ButtonStyle.secondary, row=2)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar_faixa(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=PersonagensNarrativosEditarView(
            self.cog, self.usuario_id, self.thread, self.referencias, int(self.faixas.values[0])
        ))

    async def selecionar_personagem(self, interaction: discord.Interaction) -> None:
        referencia = self.lote[int(self.personagens.values[0])]
        await interaction.response.edit_message(
            embed=embed_navegacao(f"Descrição — {referencia.nome}", "Escolha o campo narrativo que deseja modificar."),
            view=CamposNarrativosEditarView(self.cog, self.usuario_id, referencia, self.thread),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_navegacao("Descrição de Personagens", "Escolha a thread do personagem."),
            view=ThreadsNarrativasEditarView(self.cog, self.usuario_id),
        )


class CamposNarrativosEditarView(ViewNavegacaoEditar):
    def __init__(self, cog: "Editar", usuario_id: int, referencia: ReferenciaFicha, thread: str) -> None:
        super().__init__(cog, usuario_id)
        self.referencia, self.thread = referencia, thread
        ficha = FichaPersonagem.carregar(referencia.caminho)
        self.campos = campos_descricao_narrativa(ficha)
        seletor = discord.ui.Select(
            placeholder="Campo narrativo",
            options=[discord.SelectOption(label=titulo, value=str(i), description=(valor.replace("\n", " ")[:100] or "Campo vazio")) for i, (titulo, valor) in enumerate(self.campos)],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar aos personagens", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        titulo, valor = self.campos[int(self.seletor.values[0])]
        await interaction.response.send_modal(EditarDescricaoNarrativaModal(
            self.cog, self.usuario_id, self.referencia, self.thread, titulo, valor
        ))

    async def voltar(self, interaction: discord.Interaction) -> None:
        referencias = fichas_narrativas_por_thread().get(self.thread, [])
        await interaction.response.edit_message(
            embed=embed_navegacao(f"Descrição de Personagens — {self.thread}", "Escolha a faixa alfabética e depois o personagem."),
            view=PersonagensNarrativosEditarView(self.cog, self.usuario_id, self.thread, referencias),
        )


class EditarDescricaoNarrativaModal(discord.ui.Modal):
    def __init__(self, cog: "Editar", usuario_id: int, referencia: ReferenciaFicha, thread: str, titulo: str, valor: str) -> None:
        super().__init__(title=f"Editar — {titulo}"[:45])
        self.cog, self.usuario_id, self.referencia, self.thread, self.titulo = cog, usuario_id, referencia, thread, titulo
        self.valor = discord.ui.TextInput(
            label=titulo[:45], style=discord.TextStyle.paragraph, required=False,
            max_length=4000 if titulo == "Sobre" else 1024, default=valor or None,
        )
        self.add_item(self.valor)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        ficha = FichaPersonagem.carregar(self.referencia.caminho)
        definir_campo_narrativo(ficha, self.titulo, str(self.valor).strip())
        salvar_ficha(ficha, self.referencia.caminho)
        await sincronizar_publicacao_personagem(interaction, ficha, self.referencia.caminho)
        await interaction.edit_original_response(
            embed=embed_navegacao(f"Descrição — {ficha.nome}", f"✅ **{self.titulo}** foi atualizado na ficha e na publicação narrativa."),
            view=CamposNarrativosEditarView(self.cog, self.usuario_id, self.referencia, self.thread),
        )


class Editar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="edit", description="Edita um item existente usando sua estrutura e prévia próprias.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def editar(self, interaction: discord.Interaction) -> None:
        membro = interaction.user
        if not isinstance(membro, discord.Member) or not membro.guild_permissions.manage_guild:
            await interaction.response.send_message("Você precisa da permissão **Gerenciar servidor** para usar `/edit`.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=embed_navegacao("Editar item", "Escolha primeiro a categoria da biblioteca."),
            view=CategoriasEditarView(self, membro.id),
            ephemeral=True,
        )

    async def abrir_item(self, interaction: discord.Interaction, encontrado: ItemRemovivel) -> None:
        await interaction.response.defer()
        conteudo = encontrado.arquivo.read_text(encoding="utf-8-sig")
        try:
            documento = ler_documento(conteudo, encontrado.nome)
            thread_id = encontrar_thread_id(encontrado)
            mensagens = await localizar_mensagens(self.bot, encontrado, thread_id)
        except (ValueError, OSError, RuntimeError) as erro:
            await interaction.edit_original_response(
                content=f"Não consegui abrir o editor: {erro}", embed=None, view=None
            )
            return
        if len(mensagens) > 1:
            await interaction.edit_original_response(
                content="Há mais de uma publicação correspondente; a edição foi bloqueada para evitar alterar a mensagem errada.",
                embed=None,
                view=None,
            )
            return
        mensagem = mensagens[0] if mensagens else None
        sessao = SessaoEdicao(
            usuario_id=membro.id,
            item=encontrado,
            documento=documento,
            conteudo_original=conteudo,
            thread_id=thread_id,
            mensagem_id=mensagem.id if mensagem else None,
            conteudo_publicacao_original=mensagem.content if mensagem else "",
            embeds_publicados_originais=[embed.to_dict() for embed in mensagem.embeds] if mensagem else None,
            imagem_publicada=next(
                (
                    embed.image.url
                    for embed in mensagem.embeds
                    if embed.image and embed.image.url
                ),
                "",
            ) if mensagem else "",
        )
        await interaction.edit_original_response(
            content=None,
            embed=embed_editor(sessao),
            view=EditorItemView(sessao),
        )
