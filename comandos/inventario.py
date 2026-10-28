from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from comandos.ficha import (
    FichaAtualView,
    LOCKS_FICHA,
    ReferenciaPocaoFicha,
    anexos_ficha,
    criar_arquivos_discord,
    embed_painel,
    exemplo_descricao_pocao,
    listar_categorias_pocoes_ficha,
    listar_pocoes_ficha,
    montar_embeds_ficha_interacao,
    sincronizar_publicacao_personagem,
)
from comandos.executar import GrupoIndice, ItemIndice, criar_embeds_indice, localizar_links_oficiais
from comandos.preparar import interpretar_pocao
from comandos import ficha_criaturas
from utils.biblioteca import normalizar_rotulo
from utils.fichas import (
    FichaPersonagem,
    EMOJIS_PASTAS_FICHA,
    GRUPOS_FICHA,
    bonus_pericia,
    formatar_bonus,
    listar_fichas,
    paginas_fichas_alfabeticas,
    salvar_ficha,
)
from utils.inventario import (
    CATEGORIAS_ITENS,
    EMOJIS_ITENS,
    MOEDAS,
    TIPOS_ALIMENTO,
    TIPOS_INGREDIENTE,
    UNIDADES_INGREDIENTE,
    formatar_item,
    emoji_grupo_ingredientes,
    ingredientes_oficiais_por_grupo,
    indices_categoria,
    inteiro_positivo,
    montar_embed_itens,
    metadados_galeoes,
    remover_item,
    somar_item,
    substituir_item,
    unidade_ingrediente_oficial,
)
from utils.midia import salvar_upload_item


ORIGENS_LOOT = (
    "Furto",
    "Criatura",
    "Ambiente Urbano",
    "Ambiente Selvagem",
)

TIPOS_CRIATURA_LOOT = ("Selvagem", "Domesticada")

DESCRICOES_ALIMENTOS = {
    "Vegetais": "Verduras, raízes e legumes.",
    "Frutas": "Frutas frescas, secas ou preservadas.",
    "Enlatados": "Alimentos conservados em latas ou recipientes.",
    "Refeições": "Pratos prontos ou porções completas.",
    "Bebidas": "Bebidas comuns, mágicas ou não mágicas.",
    "Doces": "Confeitos, sobremesas e guloseimas.",
    "Salgados": "Lanches, massas e petiscos salgados.",
}


class ViewInventario(discord.ui.View):
    def __init__(self, usuario_id: int):
        super().__init__(timeout=900)
        self.usuario_id = usuario_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message(
            "Somente quem abriu este inventário pode usar os controles.",
            ephemeral=True,
        )
        return False


def referencias_permitidas(usuario_id: int, administrador: bool):
    referencias = []
    for referencia in listar_fichas():
        if administrador:
            referencias.append(referencia)
            continue
        try:
            if FichaPersonagem.carregar(referencia.caminho).titular_id == usuario_id:
                referencias.append(referencia)
        except (OSError, ValueError):
            continue
    return referencias


class PastaInventarioView(ViewInventario):
    def __init__(self, usuario_id: int, administrador: bool, acao: str):
        super().__init__(usuario_id)
        self.administrador = administrador
        self.acao = acao
        referencias = referencias_permitidas(usuario_id, administrador)
        contagens = {
            grupo: sum(referencia.grupo == grupo for referencia in referencias)
            for grupo in GRUPOS_FICHA
        }
        seletor = discord.ui.Select(
            placeholder="Escolha a pasta da ficha",
            options=[
                discord.SelectOption(
                    label=grupo,
                    value=grupo,
                    emoji=EMOJIS_PASTAS_FICHA[grupo],
                    description=(
                        f"{contagens[grupo]} ficha(s) disponível(is)."
                        if contagens[grupo]
                        else "Nenhuma ficha disponível para você nesta pasta."
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
        referencias = [
            referencia
            for referencia in referencias_permitidas(self.usuario_id, self.administrador)
            if referencia.grupo == grupo
        ]
        paginas = paginas_fichas_alfabeticas(referencias)
        pagina = next((i for i, (_, itens) in enumerate(paginas) if itens), 0)
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🎒 {grupo}",
                "Escolha a faixa alfabética e depois a ficha.",
            ),
            view=FichaInventarioView(
                self.usuario_id,
                self.administrador,
                self.acao,
                grupo,
                pagina,
            ),
        )


class FichaInventarioView(ViewInventario):
    def __init__(self, usuario_id: int, administrador: bool, acao: str, grupo: str, pagina: int):
        super().__init__(usuario_id)
        self.administrador = administrador
        self.acao = acao
        self.grupo = grupo
        referencias = [
            referencia
            for referencia in referencias_permitidas(usuario_id, administrador)
            if referencia.grupo == grupo
        ]
        self.paginas = paginas_fichas_alfabeticas(referencias)
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        rotulo, self.referencias = self.paginas[self.pagina]
        faixas = discord.ui.Select(
            placeholder=f"Faixa alfabética — {rotulo}",
            options=[
                discord.SelectOption(
                    label=nome,
                    value=str(indice),
                    description=(f"{len(itens)} ficha(s)." if itens else "Faixa reservada."),
                    default=indice == self.pagina,
                )
                for indice, (nome, itens) in enumerate(self.paginas)
            ],
            row=0,
        )
        faixas.callback = self.selecionar_faixa
        self.faixas = faixas
        self.add_item(faixas)
        if self.referencias:
            fichas = discord.ui.Select(
                placeholder=f"Fichas — {rotulo}",
                options=[
                    discord.SelectOption(label=referencia.nome[:100], value=str(indice))
                    for indice, referencia in enumerate(self.referencias)
                ],
                row=1,
            )
            fichas.callback = self.selecionar_ficha
            self.fichas = fichas
            self.add_item(fichas)
        voltar = discord.ui.Button(label="Voltar às pastas", style=discord.ButtonStyle.secondary, row=2)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar_faixa(self, interaction: discord.Interaction) -> None:
        pagina = int(self.faixas.values[0])
        await interaction.response.edit_message(
            view=FichaInventarioView(
                self.usuario_id, self.administrador, self.acao, self.grupo, pagina
            )
        )

    async def selecionar_ficha(self, interaction: discord.Interaction) -> None:
        referencia = self.referencias[int(self.fichas.values[0])]
        if self.acao == "guardar":
            await interaction.response.edit_message(
                embed=embed_painel(
                    "🎒 Guardar item",
                    f"Inventário de **{referencia.nome}**. Escolha o tipo do item.",
                ),
                view=TipoItemView(self.usuario_id, referencia.caminho),
            )
            return
        if self.acao.startswith("loot|"):
            _, origem, *restante = self.acao.split("|")
            subtipo = restante[0] if restante else ""
            ficha = FichaPersonagem.carregar(referencia.caminho)
            await interaction.response.defer()
            await interaction.edit_original_response(
                embed=embed_painel(
                    "🎲 Loot realizado",
                    f"A rolagem de **{ficha.nome}** foi enviada abaixo.",
                ),
                view=None,
            )
            embed, categoria, item = preparar_resultado_loot(ficha, origem, subtipo)
            await interaction.followup.send(
                embed=embed,
                view=RegistrarLootView(
                    self.usuario_id,
                    referencia.caminho,
                    categoria,
                    item,
                ),
            )
            return
        ficha = FichaPersonagem.carregar(referencia.caminho)
        await interaction.response.edit_message(
            embed=montar_embed_itens(ficha),
            view=BolsaView(self.usuario_id, referencia.caminho),
            attachments=[],
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel("🎒 Inventário", "Escolha a pasta da ficha."),
            view=PastaInventarioView(self.usuario_id, self.administrador, self.acao),
        )


@dataclass
class RascunhoItem:
    categoria: str
    nome: str = ""
    dados: dict[str, str] = field(default_factory=dict)
    indice: int | str | None = None

    def registro(self, quantidade: int) -> dict[str, str]:
        return {
            "categoria": self.categoria,
            "nome": self.nome,
            "quantidade": str(quantidade),
            **self.dados,
        }


async def registrar_rascunho_item(
    interaction: discord.Interaction,
    usuario_id: int,
    caminho: Path,
    rascunho: RascunhoItem,
    quantidade: int,
) -> None:
    if not interaction.response.is_done():
        await interaction.response.defer()
    lock = LOCKS_FICHA.setdefault(caminho.resolve(), asyncio.Lock())
    async with lock:
        ficha = FichaPersonagem.carregar(caminho)
        registro = rascunho.registro(quantidade)
        if rascunho.indice == "galeoes":
            ficha.galeoes = quantidade
            metadados = metadados_galeoes(ficha)
            imagem = registro.get("imagem", "").strip()
            if imagem:
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
            elif metadados is not None:
                ficha.itens.remove(metadados)
        elif isinstance(rascunho.indice, int):
            substituir_item(ficha, rascunho.indice, registro)
        else:
            somar_item(ficha, registro)
        salvar_ficha(ficha, caminho)
    await interaction.edit_original_response(
        embed=montar_embed_itens(ficha),
        view=BolsaView(usuario_id, caminho),
        attachments=[],
    )
    await sincronizar_publicacao_personagem(interaction, ficha, caminho)


class ImagemItemView(ViewInventario):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        rascunho: RascunhoItem,
        quantidade_fixa: int | None = None,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.rascunho = rascunho
        self.quantidade_fixa = quantidade_fixa
        possui_imagem = bool(rascunho.dados.get("imagem", "").strip())

        imagem = discord.ui.Button(
            label="Alterar foto" if possui_imagem else "Adicionar foto",
            emoji="📷",
            style=discord.ButtonStyle.primary,
        )
        imagem.callback = self.imagem
        self.add_item(imagem)

        continuar = discord.ui.Button(
            label="Manter foto" if possui_imagem else "Continuar sem foto",
            style=discord.ButtonStyle.secondary,
        )
        continuar.callback = self.continuar
        self.add_item(continuar)

        if possui_imagem:
            remover = discord.ui.Button(
                label="Remover foto",
                emoji="🗑️",
                style=discord.ButtonStyle.danger,
            )
            remover.callback = self.remover
            self.add_item(remover)

    async def imagem(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            ImagemItemModal(
                self.usuario_id,
                self.caminho,
                self.rascunho,
                self.quantidade_fixa,
            )
        )

    async def continuar(self, interaction: discord.Interaction) -> None:
        await self.avancar(interaction)

    async def remover(self, interaction: discord.Interaction) -> None:
        self.rascunho.dados.pop("imagem", None)
        await self.avancar(interaction)

    async def avancar(self, interaction: discord.Interaction) -> None:
        if self.quantidade_fixa is not None:
            self.rascunho.dados.pop("_quantidade_atual", None)
            await registrar_rascunho_item(
                interaction,
                self.usuario_id,
                self.caminho,
                self.rascunho,
                self.quantidade_fixa,
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel(
                "🎒 Quantidade",
                f"Escolha a quantidade de **{self.rascunho.nome}**.",
            ),
            view=QuantidadeItemView(
                self.usuario_id,
                self.caminho,
                self.rascunho,
            ),
        )


class ImagemItemModal(discord.ui.Modal):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        rascunho: RascunhoItem,
        quantidade_fixa: int | None = None,
    ):
        super().__init__(title="Foto do item")
        self.usuario_id = usuario_id
        self.caminho = caminho
        self.rascunho = rascunho
        self.quantidade_fixa = quantidade_fixa
        self.arquivo_imagem = discord.ui.FileUpload(
            required=True,
            max_values=1,
        )
        self.add_item(
            discord.ui.Label(
                text="Arquivo da foto",
                description="Envie uma imagem PNG, JPG ou WEBP de até 25 MB.",
                component=self.arquivo_imagem,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            if not self.caminho.is_file():
                raise ValueError("A ficha não está mais disponível na biblioteca.")
            ficha = FichaPersonagem.carregar(self.caminho)
            self.rascunho.dados["imagem"] = await salvar_upload_item(
                self.arquivo_imagem.values[0],
                ficha.nome,
                self.rascunho.nome,
            )
        except (OSError, ValueError) as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await ImagemItemView(
            self.usuario_id,
            self.caminho,
            self.rascunho,
            self.quantidade_fixa,
        ).avancar(interaction)


async def abrir_etapa_imagem_item(
    interaction: discord.Interaction,
    usuario_id: int,
    caminho: Path,
    rascunho: RascunhoItem,
    quantidade_fixa: int | None = None,
) -> None:
    possui_imagem = bool(rascunho.dados.get("imagem", "").strip())
    await interaction.response.edit_message(
        embed=embed_painel(
            "📷 Foto do item",
            (
                "Este item já possui uma foto. Você pode mantê-la, trocá-la ou removê-la."
                if possui_imagem
                else "Adicione uma foto por link ou continue sem foto. Este campo é opcional."
            ),
        ),
        view=ImagemItemView(
            usuario_id,
            caminho,
            rascunho,
            quantidade_fixa,
        ),
    )


class TipoItemView(ViewInventario):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__(usuario_id)
        self.caminho = caminho
        seletor = discord.ui.Select(
            placeholder="Tipo de item",
            options=[
                discord.SelectOption(
                    label=categoria,
                    value=categoria,
                    emoji=EMOJIS_ITENS[categoria],
                    description={
                        "Dinheiro": "Galeões, Sicles ou Nuques.",
                        "Ingredientes": "Líquidos ou sólidos medidos em ml, unidades, g ou kg.",
                        "Poções": "Frascos de poções carregados pelo personagem.",
                        "Alimentos": "Comidas registradas por unidade.",
                        "Armas": "Armas com tipo de dano, dano-base e crítico.",
                        "Variados": "Objetos que não pertencem às demais categorias.",
                    }[categoria],
                )
                for categoria in CATEGORIAS_ITENS
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(label="Voltar à ficha", style=discord.ButtonStyle.secondary, row=1)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        categoria = self.seletor.values[0]
        rascunho = RascunhoItem(categoria)
        if categoria == "Dinheiro":
            await interaction.response.edit_message(
                embed=embed_painel("💰 Dinheiro", "Escolha o tipo de moeda."),
                view=MoedaItemView(self.usuario_id, self.caminho, rascunho),
            )
            return
        if categoria == "Ingredientes":
            await interaction.response.edit_message(
                embed=embed_painel(
                    "🪶 Categoria do ingrediente",
                    "Escolha uma categoria da biblioteca oficial de ingredientes.",
                ),
                view=CategoriaIngredienteInventarioView(
                    self.usuario_id,
                    self.caminho,
                ),
            )
            return
        if categoria == "Alimentos":
            await interaction.response.edit_message(
                embed=embed_painel("🥧 Alimentos", "Escolha a categoria do alimento."),
                view=TipoAlimentoView(self.usuario_id, self.caminho, rascunho),
            )
            return
        if categoria == "Poções":
            await interaction.response.edit_message(
                embed=embed_painel(
                    "🧪 Ano de desbloqueio",
                    "Escolha o ano para consultar as poções oficiais.",
                ),
                view=AnoPocaoInventarioView(self.usuario_id, self.caminho),
            )
            return
        if categoria == "Armas":
            await interaction.response.edit_message(
                embed=embed_painel(
                    "🗡️ Armas",
                    "Escolha o tipo para consultar as armas oficiais ou use Personalizada.",
                ),
                view=TipoArmaInventarioView(
                    self.usuario_id,
                    self.caminho,
                    rascunho,
                ),
            )
            return
        await interaction.response.send_modal(ItemModal(self.usuario_id, self.caminho, rascunho))

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
            attachments=criar_arquivos_discord(anexos_ficha(ficha)),
        )


def grupo_indice_pocoes(
    ano: str,
    referencias: list[ReferenciaPocaoFicha],
) -> GrupoIndice:
    return GrupoIndice(
        ano,
        [
            ItemIndice(
                referencia.nome,
                interpretar_pocao(
                    referencia.caminho.read_text(encoding="utf-8-sig")
                )[0],
                "pocao",
            )
            for referencia in referencias
        ],
    )


class AnoPocaoInventarioView(ViewInventario):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__(usuario_id)
        self.caminho = caminho
        categorias = listar_categorias_pocoes_ficha()
        seletor = discord.ui.Select(
            placeholder="Ano de desbloqueio",
            options=[
                discord.SelectOption(
                    label=categoria,
                    value=categoria,
                    description=f"{len(listar_pocoes_ficha(categoria))} poção(ões).",
                )
                for categoria in categorias
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar aos tipos",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        ano = self.seletor.values[0]
        referencias = listar_pocoes_ficha(ano)
        if not referencias:
            await interaction.response.send_message(
                "Esse ano não possui poções válidas na biblioteca.",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        grupo = grupo_indice_pocoes(ano, referencias)
        links = await localizar_links_oficiais(interaction.client, "Poções", [grupo])
        links_por_nome = {
            nome: url
            for (grupo_normalizado, nome), url in links.items()
            if grupo_normalizado == normalizar_rotulo(ano)
        }
        view = PocaoInventarioView(
            self.usuario_id,
            self.caminho,
            ano,
            referencias,
            links_por_nome,
            0,
        )
        await interaction.edit_original_response(
            embeds=[view.embed_indice()],
            view=view,
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🎒 Guardar item",
                "Escolha o tipo do item que será adicionado ao inventário.",
            ),
            view=TipoItemView(self.usuario_id, self.caminho),
        )


class PocaoInventarioView(ViewInventario):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        ano: str,
        referencias: list[ReferenciaPocaoFicha],
        links: dict[str, str],
        pagina: int,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.ano = ano
        self.referencias = referencias
        self.links = links
        self.paginas = [
            referencias[indice:indice + 25]
            for indice in range(0, len(referencias), 25)
        ] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        self.itens = self.paginas[self.pagina]
        seletor = discord.ui.Select(
            placeholder=f"Escolha a poção — {self.pagina + 1}/{len(self.paginas)}",
            options=[
                discord.SelectOption(
                    label=referencia.nome[:100],
                    value=str(indice),
                    description=exemplo_descricao_pocao(referencia)[:100],
                )
                for indice, referencia in enumerate(self.itens)
            ],
            row=0,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        if len(self.paginas) > 1:
            anterior = discord.ui.Button(
                label="Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == 0,
                row=1,
            )
            anterior.callback = self.anterior
            self.add_item(anterior)
            proxima = discord.ui.Button(
                label="Próxima",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == len(self.paginas) - 1,
                row=1,
            )
            proxima.callback = self.proxima
            self.add_item(proxima)
        voltar = discord.ui.Button(
            label="Voltar aos anos",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    def embed_indice(self) -> discord.Embed:
        grupo = grupo_indice_pocoes(self.ano, self.itens)
        links = {
            (normalizar_rotulo(self.ano), normalizar_rotulo(item.nome)): self.links[
                normalizar_rotulo(item.nome)
            ]
            for item in self.itens
            if normalizar_rotulo(item.nome) in self.links
        }
        embed = criar_embeds_indice("Poções", [grupo], 0x66F060, links)[0]
        embed.insert_field_at(
            0,
            name="Escolha da poção",
            value=(
                "Clique em um nome para abrir a mensagem oficial ou use o seletor "
                "abaixo para escolher a poção."
            ),
            inline=False,
        )
        if len(self.paginas) > 1:
            embed.set_footer(text=f"Página {self.pagina + 1} de {len(self.paginas)}")
        return embed

    def nova(self, pagina: int) -> "PocaoInventarioView":
        return PocaoInventarioView(
            self.usuario_id,
            self.caminho,
            self.ano,
            self.referencias,
            self.links,
            pagina,
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        referencia = self.itens[int(self.seletor.values[0])]
        rascunho = RascunhoItem(
            "Poções",
            referencia.nome,
            {"ano": referencia.categoria, "unidade": "frasco"},
        )
        await abrir_etapa_imagem_item(
            interaction,
            self.usuario_id,
            self.caminho,
            rascunho,
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        view = self.nova(self.pagina - 1)
        await interaction.response.edit_message(embeds=[view.embed_indice()], view=view)

    async def proxima(self, interaction: discord.Interaction) -> None:
        view = self.nova(self.pagina + 1)
        await interaction.response.edit_message(embeds=[view.embed_indice()], view=view)

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🧪 Ano de desbloqueio",
                "Escolha o ano para consultar as poções oficiais.",
            ),
            view=AnoPocaoInventarioView(self.usuario_id, self.caminho),
        )


class TipoArmaInventarioView(ViewInventario):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        rascunho: RascunhoItem,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.rascunho = rascunho
        seletor = discord.ui.Select(
            placeholder="Tipo de arma",
            options=[
                discord.SelectOption(
                    label=tipo,
                    value=tipo,
                    description=ficha_criaturas.DESCRICOES_TIPOS_ARMAS[tipo][:100],
                )
                for tipo in ficha_criaturas.ARMAS_POR_TIPO
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar aos tipos de item",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        tipo = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=embed_painel(
                f"🗡️ {tipo}",
                "Escolha uma arma oficial ou use Personalizada para preencher os dados manualmente.",
            ),
            view=ArmaInventarioView(
                self.usuario_id,
                self.caminho,
                self.rascunho,
                tipo,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel("🎒 Guardar item", "Escolha o tipo de item."),
            view=TipoItemView(self.usuario_id, self.caminho),
        )


class ArmaInventarioView(ViewInventario):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        rascunho: RascunhoItem,
        tipo_arma: str,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.rascunho = rascunho
        self.tipo_arma = tipo_arma
        armas = ficha_criaturas.ARMAS_POR_TIPO[tipo_arma]
        opcoes = []
        for nome, dados in armas.items():
            dano = dados.get("dano", dados.get("dano-base", "--"))
            opcoes.append(
                discord.SelectOption(
                    label=nome,
                    value=nome,
                    description=(
                        f"{dados.get('tipo de dano', '--')} • {dano} • "
                        f"crítico {dados.get('crítico', '--')}"
                    )[:100],
                )
            )
        opcoes.append(
            discord.SelectOption(
                label="Personalizada",
                value="Personalizada",
                description="Crie uma arma que ainda não existe na tabela oficial.",
            )
        )
        seletor = discord.ui.Select(
            placeholder="Escolha a arma",
            options=opcoes,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar aos tipos de arma",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        nome = self.seletor.values[0]
        if nome == "Personalizada":
            await interaction.response.send_modal(
                ItemModal(
                    self.usuario_id,
                    self.caminho,
                    self.rascunho,
                )
            )
            return
        dados = ficha_criaturas.ARMAS_POR_TIPO[self.tipo_arma][nome]
        self.rascunho.nome = nome
        self.rascunho.dados.update(
            {
                "classe": self.tipo_arma,
                "tipo": dados.get("tipo de dano", ""),
                "dano": dados.get("dano", dados.get("dano-base", "")),
                "critico": dados.get("crítico", ""),
            }
        )
        await abrir_etapa_imagem_item(
            interaction,
            self.usuario_id,
            self.caminho,
            self.rascunho,
            quantidade_fixa=1,
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel("🗡️ Armas", "Escolha o tipo da arma."),
            view=TipoArmaInventarioView(
                self.usuario_id,
                self.caminho,
                self.rascunho,
            ),
        )


class MoedaItemView(ViewInventario):
    def __init__(self, usuario_id: int, caminho: Path, rascunho: RascunhoItem):
        super().__init__(usuario_id)
        self.caminho, self.rascunho = caminho, rascunho
        seletor = discord.ui.Select(
            placeholder="Tipo de moeda",
            options=[discord.SelectOption(label=moeda, value=moeda) for moeda in MOEDAS],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        moeda = self.seletor.values[0]
        self.rascunho.nome = moeda
        self.rascunho.dados["tipo"] = moeda
        await abrir_etapa_imagem_item(
            interaction,
            self.usuario_id,
            self.caminho,
            self.rascunho,
        )


class CategoriaIngredienteInventarioView(ViewInventario):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.grupos = ingredientes_oficiais_por_grupo()
        seletor = discord.ui.Select(
            placeholder="Categoria do ingrediente",
            options=[
                discord.SelectOption(
                    label=grupo[:100],
                    value=grupo,
                    emoji=emoji_grupo_ingredientes(grupo),
                    description=f"{len(ingredientes)} ingrediente(s).",
                )
                for grupo, ingredientes in self.grupos.items()
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        voltar = discord.ui.Button(
            label="Voltar aos tipos",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        grupo = self.seletor.values[0]
        ingredientes = self.grupos.get(grupo, [])
        await interaction.response.edit_message(
            embed=embed_painel(
                "🪶 Ingredientes",
                f"Escolha um ingrediente de **{grupo}**.",
            ),
            view=IngredienteInventarioView(
                self.usuario_id,
                self.caminho,
                grupo,
                ingredientes,
                0,
            ),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🎒 Guardar item",
                "Escolha o tipo do item que será adicionado ao inventário.",
            ),
            view=TipoItemView(self.usuario_id, self.caminho),
        )


class IngredienteInventarioView(ViewInventario):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        grupo: str,
        ingredientes: list[str],
        pagina: int,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.grupo = grupo
        self.ingredientes = ingredientes
        self.paginas = [
            ingredientes[indice:indice + 25]
            for indice in range(0, len(ingredientes), 25)
        ] or [[]]
        self.pagina = max(0, min(pagina, len(self.paginas) - 1))
        self.itens = self.paginas[self.pagina]
        seletor = discord.ui.Select(
            placeholder=f"Ingrediente — {self.pagina + 1}/{len(self.paginas)}",
            options=[
                discord.SelectOption(
                    label=nome[:100],
                    value=str(indice),
                    description=(
                        "Quantidade medida em ml."
                        if unidade_ingrediente_oficial(nome, grupo)[1] == "ml"
                        else f"Quantidade medida em {unidade_ingrediente_oficial(nome, grupo)[1]}."
                    ),
                )
                for indice, nome in enumerate(self.itens)
            ],
            row=0,
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)
        if len(self.paginas) > 1:
            anterior = discord.ui.Button(
                label="Anterior",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == 0,
                row=1,
            )
            anterior.callback = self.anterior
            self.add_item(anterior)
            proxima = discord.ui.Button(
                label="Próxima",
                style=discord.ButtonStyle.secondary,
                disabled=self.pagina == len(self.paginas) - 1,
                row=1,
            )
            proxima.callback = self.proxima
            self.add_item(proxima)
        voltar = discord.ui.Button(
            label="Voltar às categorias",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        voltar.callback = self.voltar
        self.add_item(voltar)

    def nova(self, pagina: int) -> "IngredienteInventarioView":
        return IngredienteInventarioView(
            self.usuario_id,
            self.caminho,
            self.grupo,
            self.ingredientes,
            pagina,
        )

    async def selecionar(self, interaction: discord.Interaction) -> None:
        nome = self.itens[int(self.seletor.values[0])]
        tipo, unidade = unidade_ingrediente_oficial(nome, self.grupo)
        rascunho = RascunhoItem(
            "Ingredientes",
            nome,
            {"grupo": self.grupo, "tipo": tipo, "unidade": unidade},
        )
        await abrir_etapa_imagem_item(
            interaction,
            self.usuario_id,
            self.caminho,
            rascunho,
        )

    async def anterior(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=self.nova(self.pagina - 1))

    async def proxima(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=self.nova(self.pagina + 1))

    async def voltar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "🪶 Categoria do ingrediente",
                "Escolha uma categoria da biblioteca oficial de ingredientes.",
            ),
            view=CategoriaIngredienteInventarioView(
                self.usuario_id,
                self.caminho,
            ),
        )


class TipoAlimentoView(ViewInventario):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        rascunho: RascunhoItem,
        item: dict[str, str] | None = None,
    ):
        super().__init__(usuario_id)
        self.caminho, self.rascunho, self.item = caminho, rascunho, item
        seletor = discord.ui.Select(
            placeholder="Categoria do alimento",
            options=[
                discord.SelectOption(
                    label=tipo,
                    value=tipo,
                    description=DESCRICOES_ALIMENTOS[tipo],
                    default=tipo == (item or {}).get("tipo"),
                )
                for tipo in TIPOS_ALIMENTO
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        self.rascunho.dados["tipo"] = self.seletor.values[0]
        await interaction.response.send_modal(
            ItemModal(self.usuario_id, self.caminho, self.rascunho, self.item)
        )


class ItemModal(discord.ui.Modal):
    def __init__(self, usuario_id: int, caminho: Path, rascunho: RascunhoItem, item: dict[str, str] | None = None):
        super().__init__(title=("Modificar item" if item else "Guardar item"))
        self.usuario_id, self.caminho, self.rascunho = usuario_id, caminho, rascunho
        item = item or {}
        self.nome = discord.ui.TextInput(
            label="Título" if rascunho.categoria == "Variados" else "Nome",
            max_length=100,
            default=item.get("nome", rascunho.nome),
        )
        self.add_item(self.nome)
        self.tipo = self.dano = self.critico = self.descricao = None
        if rascunho.categoria == "Armas":
            self.tipo = discord.ui.TextInput(label="Tipo de dano", placeholder="Ex.: Cortante", max_length=50, default=item.get("tipo", ""))
            self.dano = discord.ui.TextInput(label="Dano", placeholder="Ex.: 1d8+des", max_length=50, default=item.get("dano", ""))
            self.critico = discord.ui.TextInput(label="Crítico", placeholder="Ex.: 19 ou x2", max_length=30, default=item.get("critico", ""))
            self.add_item(self.tipo); self.add_item(self.dano); self.add_item(self.critico)
        elif rascunho.categoria == "Variados":
            self.descricao = discord.ui.TextInput(
                label="Descrição",
                style=discord.TextStyle.paragraph,
                max_length=1000,
                required=False,
                default=item.get("descricao", ""),
            )
            self.add_item(self.descricao)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.rascunho.nome = str(self.nome.value).strip()
        if not self.rascunho.nome:
            await interaction.response.send_message("Informe o nome do item.", ephemeral=True)
            return
        if self.rascunho.categoria == "Armas":
            self.rascunho.dados.update({
                "tipo": str(self.tipo.value).strip(),
                "dano": str(self.dano.value).strip(),
                "critico": str(self.critico.value).strip(),
            })
        elif self.rascunho.categoria == "Variados":
            self.rascunho.dados["descricao"] = str(self.descricao.value).strip()
        if self.rascunho.categoria == "Ingredientes":
            await interaction.response.edit_message(
                embed=embed_painel("🪶 Ingrediente", "Escolha se o ingrediente é líquido ou sólido."),
                view=TipoIngredienteView(self.usuario_id, self.caminho, self.rascunho),
            )
            return
        if self.rascunho.categoria == "Armas":
            quantidade_atual = self.rascunho.dados.pop("_quantidade_atual", "")
            quantidade = inteiro_positivo(quantidade_atual, 1) or 1
            await abrir_etapa_imagem_item(
                interaction,
                self.usuario_id,
                self.caminho,
                self.rascunho,
                quantidade_fixa=quantidade,
            )
            return
        await abrir_etapa_imagem_item(
            interaction,
            self.usuario_id,
            self.caminho,
            self.rascunho,
        )


class TipoIngredienteView(ViewInventario):
    def __init__(self, usuario_id: int, caminho: Path, rascunho: RascunhoItem):
        super().__init__(usuario_id)
        self.caminho, self.rascunho = caminho, rascunho
        seletor = discord.ui.Select(
            placeholder="Estado do ingrediente",
            options=[
                discord.SelectOption(label=tipo, value=tipo, description=("Usa ml." if tipo == "Líquido" else "Usa unidade, g ou kg."))
                for tipo in TIPOS_INGREDIENTE
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        tipo = self.seletor.values[0]
        self.rascunho.dados["tipo"] = tipo
        unidades = ("ml",) if tipo == "Líquido" else ("unidade", "g", "kg")
        await interaction.response.edit_message(
            embed=embed_painel("🪶 Unidade", "Escolha como a quantidade será medida."),
            view=UnidadeIngredienteView(self.usuario_id, self.caminho, self.rascunho, unidades),
        )


class UnidadeIngredienteView(ViewInventario):
    def __init__(self, usuario_id: int, caminho: Path, rascunho: RascunhoItem, unidades):
        super().__init__(usuario_id)
        self.caminho, self.rascunho = caminho, rascunho
        seletor = discord.ui.Select(
            placeholder="Unidade",
            options=[discord.SelectOption(label=unidade, value=unidade) for unidade in unidades],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        self.rascunho.dados["unidade"] = self.seletor.values[0]
        await abrir_etapa_imagem_item(
            interaction,
            self.usuario_id,
            self.caminho,
            self.rascunho,
        )


class QuantidadeItemView(ViewInventario):
    def __init__(self, usuario_id: int, caminho: Path, rascunho: RascunhoItem):
        super().__init__(usuario_id)
        self.caminho, self.rascunho = caminho, rascunho
        atual = rascunho.dados.pop("_quantidade_atual", "")
        definir = discord.ui.Button(
            label=(f"Alterar quantidade atual: {atual}" if atual else "Definir quantidade")[:80],
            style=discord.ButtonStyle.primary,
            emoji="🔢",
        )
        definir.callback = self.definir
        self.add_item(definir)
        self.quantidade_atual = atual

    async def definir(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            QuantidadeItemModal(
                self.usuario_id,
                self.caminho,
                self.rascunho,
                self.quantidade_atual,
            )
        )


def interpretar_quantidade(valor: str) -> int:
    conteudo = str(valor).strip()
    if not conteudo.isdecimal():
        raise ValueError("A quantidade deve ser um número inteiro.")
    quantidade = int(conteudo)
    if quantidade <= 0:
        raise ValueError("A quantidade deve ser maior que zero.")
    return quantidade


class QuantidadeItemModal(discord.ui.Modal):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        rascunho: RascunhoItem,
        quantidade_atual: str = "",
    ):
        super().__init__(title="Definir quantidade")
        self.usuario_id = usuario_id
        self.caminho = caminho
        self.rascunho = rascunho
        if rascunho.categoria == "Dinheiro":
            unidade = rascunho.nome
        elif rascunho.categoria == "Ingredientes":
            unidade = rascunho.dados.get("unidade", "unidades")
        elif rascunho.categoria == "Poções":
            unidade = "frascos"
        else:
            unidade = "unidades"
        self.quantidade = discord.ui.TextInput(
            label=f"Quantidade em {unidade}"[:45],
            placeholder="Informe um número inteiro maior que zero.",
            default=quantidade_atual or None,
            min_length=1,
            max_length=12,
        )
        self.add_item(self.quantidade)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            quantidade = interpretar_quantidade(str(self.quantidade.value))
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return
        await registrar_rascunho_item(
            interaction,
            self.usuario_id,
            self.caminho,
            self.rascunho,
            quantidade,
        )


class BolsaView(ViewInventario):
    def __init__(self, usuario_id: int, caminho: Path):
        super().__init__(usuario_id)
        self.caminho = caminho
        ficha = FichaPersonagem.carregar(caminho)
        remover = discord.ui.Button(
            label="Remover item",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            disabled=not ficha.itens and ficha.galeoes <= 0,
        )
        remover.callback = self.remover
        modificar = discord.ui.Button(
            label="Modificar item",
            style=discord.ButtonStyle.secondary,
            emoji="✏️",
            disabled=not ficha.itens and ficha.galeoes <= 0,
        )
        modificar.callback = self.modificar
        self.add_item(modificar)
        self.add_item(remover)
        voltar = discord.ui.Button(label="Voltar à ficha", style=discord.ButtonStyle.secondary)
        voltar.callback = self.voltar
        self.add_item(voltar)

    async def modificar(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel(
                "✏️ Modificar item",
                "Escolha a categoria e depois o item que deseja alterar.",
            ),
            view=CategoriasInventarioView(
                self.usuario_id,
                self.caminho,
                "gerenciar",
            ),
        )

    async def remover(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel("🗑️ Remover item", "Escolha a categoria do item."),
            view=CategoriasInventarioView(self.usuario_id, self.caminho, "remover"),
        )

    async def voltar(self, interaction: discord.Interaction) -> None:
        ficha = FichaPersonagem.carregar(self.caminho)
        await interaction.response.edit_message(
            embeds=montar_embeds_ficha_interacao(ficha),
            view=FichaAtualView(self.usuario_id, self.caminho),
            attachments=criar_arquivos_discord(anexos_ficha(ficha)),
        )


class CategoriasInventarioView(ViewInventario):
    def __init__(self, usuario_id: int, caminho: Path, modo: str):
        super().__init__(usuario_id)
        self.caminho, self.modo = caminho, modo
        ficha = FichaPersonagem.carregar(caminho)
        categorias = [categoria for categoria in CATEGORIAS_ITENS if indices_categoria(ficha, categoria)]
        seletor = discord.ui.Select(
            placeholder="Categoria do item",
            options=[discord.SelectOption(label=categoria, value=categoria, emoji=EMOJIS_ITENS[categoria]) for categoria in categorias],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        categoria = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=embed_painel(f"{EMOJIS_ITENS[categoria]} {categoria}", "Escolha o item."),
            view=ItensInventarioView(self.usuario_id, self.caminho, self.modo, categoria),
        )


class ItensInventarioView(ViewInventario):
    def __init__(self, usuario_id: int, caminho: Path, modo: str, categoria: str):
        super().__init__(usuario_id)
        self.caminho, self.modo, self.categoria = caminho, modo, categoria
        ficha = FichaPersonagem.carregar(caminho)
        self.itens = indices_categoria(ficha, categoria)
        seletor = discord.ui.Select(
            placeholder="Escolha o item",
            options=[
                discord.SelectOption(label=item.get("nome", "Item")[:100], value=str(indice), description=formatar_item(item)[:100])
                for indice, item in self.itens
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        valor = self.seletor.values[0]
        indice: int | str = "galeoes" if valor == "galeoes" else int(valor)
        item = next(item for posicao, item in self.itens if posicao == indice)
        if self.modo == "remover":
            await interaction.response.edit_message(
                embed=embed_painel("🗑️ Confirmar remoção", f"Remover {formatar_item(item)} do inventário?"),
                view=ConfirmarRemocaoItemView(self.usuario_id, self.caminho, indice),
            )
            return
        await interaction.response.edit_message(
            embed=embed_painel("✏️ Modificar item", formatar_item(item)),
            view=GerenciarItemView(self.usuario_id, self.caminho, indice, item),
        )


class GerenciarItemView(ViewInventario):
    def __init__(self, usuario_id: int, caminho: Path, indice: int | str, item: dict[str, str]):
        super().__init__(usuario_id)
        self.caminho, self.indice, self.item = caminho, indice, item
        alterar = discord.ui.Button(label="Modificar", style=discord.ButtonStyle.secondary, emoji="✏️")
        excluir = discord.ui.Button(label="Excluir", style=discord.ButtonStyle.danger, emoji="🗑️")
        alterar.callback = self.alterar; excluir.callback = self.excluir
        self.add_item(alterar); self.add_item(excluir)

    async def alterar(self, interaction: discord.Interaction) -> None:
        rascunho = RascunhoItem(
            self.item.get("categoria", "Variados"),
            self.item.get("nome", ""),
            {chave: valor for chave, valor in self.item.items() if chave not in {"categoria", "nome", "quantidade"}},
            self.indice,
        )
        rascunho.dados["_quantidade_atual"] = self.item.get("quantidade", "1")
        if self.indice == "galeoes" or rascunho.categoria == "Dinheiro":
            await abrir_etapa_imagem_item(
                interaction,
                self.usuario_id,
                self.caminho,
                rascunho,
            )
            return
        if rascunho.categoria == "Alimentos":
            await interaction.response.edit_message(
                embed=embed_painel("🥧 Alimentos", "Escolha a categoria do alimento."),
                view=TipoAlimentoView(self.usuario_id, self.caminho, rascunho, self.item),
            )
            return
        await interaction.response.send_modal(ItemModal(self.usuario_id, self.caminho, rascunho, self.item))

    async def excluir(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=embed_painel("🗑️ Confirmar remoção", f"Remover {formatar_item(self.item)} do inventário?"),
            view=ConfirmarRemocaoItemView(self.usuario_id, self.caminho, self.indice),
        )


class ConfirmarRemocaoItemView(ViewInventario):
    def __init__(self, usuario_id: int, caminho: Path, indice: int | str):
        super().__init__(usuario_id)
        self.caminho, self.indice = caminho, indice
        confirmar = discord.ui.Button(label="Confirmar remoção", style=discord.ButtonStyle.danger, emoji="🗑️")
        confirmar.callback = self.confirmar
        self.add_item(confirmar)

    async def confirmar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        lock = LOCKS_FICHA.setdefault(self.caminho.resolve(), asyncio.Lock())
        async with lock:
            ficha = FichaPersonagem.carregar(self.caminho)
            remover_item(ficha, self.indice)
            salvar_ficha(ficha, self.caminho)
        await interaction.edit_original_response(
            embed=montar_embed_itens(ficha),
            view=BolsaView(self.usuario_id, self.caminho),
            attachments=[],
        )
        await sincronizar_publicacao_personagem(interaction, ficha, self.caminho)


def _bonus_loot(ficha: FichaPersonagem, origem: str) -> tuple[str, int]:
    if origem in {"Furto", "Ambiente Urbano"}:
        return "Crime", max(bonus_pericia("Crime", ficha.pericias.get("Crime", 0), ficha.atributos))
    if origem == "Ambiente Selvagem":
        return "Sobrevivência", max(
            bonus_pericia("Sobrevivência", ficha.pericias.get("Sobrevivência", 0), ficha.atributos)
        )
    return "Trato de Criaturas Mágicas", ficha.aptidoes.get("Trato de Criaturas Mágicas", 0)


def _categoria_aleatoria_loot(origem: str) -> str:
    if origem == "Furto":
        categoria = secrets.choice(CATEGORIAS_ITENS)
        if categoria == "Alimentos":
            return f"Alimentos — {secrets.choice(TIPOS_ALIMENTO)}"
        return categoria
    if origem == "Criatura":
        return "Ingredientes — Partes de criatura"
    if origem == "Ambiente Urbano":
        # Todas as categorias podem aparecer, mas estas três são mais comuns no meio urbano.
        return secrets.choice((*CATEGORIAS_ITENS, "Dinheiro", "Armas", "Variados"))
    return secrets.choice(("Ingredientes", "Alimentos — Vegetais", "Alimentos — Frutas"))


def _grupo_ingredientes_loot(categoria_encontrada: str) -> str:
    _, _, subtipo = categoria_encontrada.partition(" — ")
    if normalizar_rotulo(subtipo) == normalizar_rotulo("Partes de criatura"):
        return "Partes de Criaturas Mágicas"
    return ""


def _sortear_ingrediente_loot(categoria_encontrada: str) -> dict[str, str] | None:
    grupos = ingredientes_oficiais_por_grupo()
    grupo_desejado = _grupo_ingredientes_loot(categoria_encontrada)
    if grupo_desejado:
        ingredientes = next(
            (
                itens
                for grupo, itens in grupos.items()
                if normalizar_rotulo(grupo) == normalizar_rotulo(grupo_desejado)
            ),
            [],
        )
        grupo_sorteado = grupo_desejado
    else:
        disponiveis = [(grupo, itens) for grupo, itens in grupos.items() if itens]
        if not disponiveis:
            return None
        grupo_sorteado, ingredientes = secrets.choice(disponiveis)
    if not ingredientes:
        return None
    nome = secrets.choice(ingredientes)
    tipo, unidade = unidade_ingrediente_oficial(nome, grupo_sorteado)
    quantidade = secrets.randbelow(4) + 1
    return {
        "categoria": "Ingredientes",
        "nome": nome,
        "quantidade": str(quantidade),
        "tipo": tipo,
        "unidade": unidade,
    }


def _item_especifico_loot(categoria_encontrada: str) -> dict[str, str] | None:
    categoria = categoria_encontrada.partition(" — ")[0]
    if normalizar_rotulo(categoria) == normalizar_rotulo("Ingredientes"):
        return _sortear_ingrediente_loot(categoria_encontrada)
    return None


def preparar_resultado_loot(
    ficha: FichaPersonagem,
    origem: str,
    subtipo: str = "",
) -> tuple[discord.Embed, str, dict[str, str] | None]:
    teste, bonus = _bonus_loot(ficha, origem)
    dados = [secrets.randbelow(20) + 1]
    vantagem = origem == "Criatura" and subtipo == "Domesticada"
    if vantagem:
        dados.append(secrets.randbelow(20) + 1)
    natural = max(dados)
    total = natural + bonus
    origem_exibida = f"{origem} — {subtipo}" if subtipo else origem
    if vantagem:
        expressao = f"2d20 (vantagem: {dados[0]}, {dados[1]}; maior {natural}) {formatar_bonus(bonus)} = **{total}**"
    else:
        expressao = f"1d20 ({natural}) {formatar_bonus(bonus)} = **{total}**"

    embed = discord.Embed(
        title="🎲 Resultado do loot",
        description=(
            "A dificuldade é definida pelo mestre conforme a cena. "
            "O resultado indica o tipo de descoberta; use **Registrar item** "
            "para adicioná-lo diretamente ao inventário."
        ),
    )
    embed.add_field(name="Ficha", value=ficha.nome, inline=True)
    embed.add_field(name="Origem", value=origem_exibida, inline=True)
    embed.add_field(name="Teste", value=teste, inline=True)
    embed.add_field(name="Rolagem", value=expressao, inline=False)
    if total > 20:
        categoria = ""
        item = None
        embed.add_field(
            name="Resultado acima de 20",
            value="🎁 Um item a ser decidido pelo mestre.",
            inline=False,
        )
    else:
        categoria = _categoria_aleatoria_loot(origem)
        item = _item_especifico_loot(categoria)
        embed.add_field(
            name="Categoria encontrada",
            value=categoria,
            inline=False,
        )
        if item is not None:
            embed.add_field(
                name="Item encontrado",
                value=formatar_item(item),
                inline=False,
            )
    return embed, categoria, item


def rolar_loot(ficha: FichaPersonagem, origem: str, subtipo: str = "") -> discord.Embed:
    return preparar_resultado_loot(ficha, origem, subtipo)[0]


def rascunho_categoria_loot(categoria_encontrada: str) -> RascunhoItem | None:
    if not categoria_encontrada:
        return None
    categoria, _, subtipo = categoria_encontrada.partition(" — ")
    categoria = next(
        (
            oficial
            for oficial in CATEGORIAS_ITENS
            if normalizar_rotulo(oficial) == normalizar_rotulo(categoria)
        ),
        "",
    )
    if not categoria:
        return None
    dados = {"tipo": subtipo} if categoria == "Alimentos" and subtipo else {}
    return RascunhoItem(categoria, dados=dados)


class RegistrarLootView(ViewInventario):
    def __init__(
        self,
        usuario_id: int,
        caminho: Path,
        categoria_encontrada: str,
        item: dict[str, str] | None = None,
    ):
        super().__init__(usuario_id)
        self.caminho = caminho
        self.categoria_encontrada = categoria_encontrada
        self.item = dict(item) if item is not None else None
        registrar = discord.ui.Button(
            label="Registrar item",
            emoji="🎒",
            style=discord.ButtonStyle.success,
        )
        registrar.callback = self.registrar
        self.add_item(registrar)
        descartar = discord.ui.Button(
            label="Descartar",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
        )
        descartar.callback = self.descartar
        self.add_item(descartar)

    async def descartar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await interaction.delete_original_response()

    async def registrar(self, interaction: discord.Interaction) -> None:
        if self.item is not None:
            quantidade = inteiro_positivo(self.item.get("quantidade", "1"), 1) or 1
            rascunho = RascunhoItem(
                self.item.get("categoria", "Variados"),
                self.item.get("nome", "Item"),
                {
                    chave: valor
                    for chave, valor in self.item.items()
                    if chave not in {"categoria", "nome", "quantidade"}
                },
            )
            await abrir_etapa_imagem_item(
                interaction,
                self.usuario_id,
                self.caminho,
                rascunho,
                quantidade_fixa=quantidade,
            )
            return
        rascunho = rascunho_categoria_loot(self.categoria_encontrada)
        if rascunho is None:
            await interaction.response.edit_message(
                embed=embed_painel(
                    "🎒 Registrar loot",
                    "Escolha o tipo do item definido pelo mestre.",
                ),
                view=TipoItemView(self.usuario_id, self.caminho),
            )
            return
        if rascunho.categoria == "Dinheiro":
            await interaction.response.edit_message(
                embed=embed_painel("💰 Dinheiro", "Escolha o tipo de moeda encontrado."),
                view=MoedaItemView(self.usuario_id, self.caminho, rascunho),
            )
            return
        if rascunho.categoria == "Armas":
            await interaction.response.edit_message(
                embed=embed_painel(
                    "🗡️ Arma encontrada",
                    "Escolha o tipo para consultar as armas oficiais ou use Personalizada.",
                ),
                view=TipoArmaInventarioView(
                    self.usuario_id,
                    self.caminho,
                    rascunho,
                ),
            )
            return
        if rascunho.categoria == "Poções":
            await interaction.response.edit_message(
                embed=embed_painel(
                    "🧪 Ano de desbloqueio",
                    "Escolha o ano para consultar as poções oficiais encontradas.",
                ),
                view=AnoPocaoInventarioView(self.usuario_id, self.caminho),
            )
            return
        if rascunho.categoria == "Alimentos" and not rascunho.dados.get("tipo"):
            await interaction.response.edit_message(
                embed=embed_painel("🥧 Alimento encontrado", "Escolha a categoria do alimento."),
                view=TipoAlimentoView(self.usuario_id, self.caminho, rascunho),
            )
            return
        await interaction.response.send_modal(
            ItemModal(self.usuario_id, self.caminho, rascunho)
        )


class TipoCriaturaLootView(ViewInventario):
    def __init__(self, usuario_id: int, administrador: bool):
        super().__init__(usuario_id)
        self.administrador = administrador
        seletor = discord.ui.Select(
            placeholder="Tipo de criatura",
            options=[
                discord.SelectOption(
                    label="Selvagem",
                    value="Selvagem",
                    description="Concede ingredientes de animais com rolagem normal.",
                ),
                discord.SelectOption(
                    label="Domesticada",
                    value="Domesticada",
                    description="Concede ingredientes de animais e vantagem no teste.",
                ),
            ],
        )
        seletor.callback = self.selecionar
        self.seletor = seletor
        self.add_item(seletor)

    async def selecionar(self, interaction: discord.Interaction) -> None:
        subtipo = self.seletor.values[0]
        await interaction.response.edit_message(
            embed=embed_painel(
                "🐾 Loot de criatura",
                f"Criatura **{subtipo.lower()}**. Escolha a pasta da ficha que fará o teste.",
            ),
            view=PastaInventarioView(
                self.usuario_id,
                self.administrador,
                f"loot|Criatura|{subtipo}",
            ),
        )


class Inventario(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="guardar", description="Adiciona um item ao inventário de uma ficha.")
    async def guardar(self, interaction: discord.Interaction) -> None:
        administrador = bool(interaction.permissions.manage_guild)
        await interaction.response.send_message(
            embed=embed_painel("🎒 Guardar", "Escolha a pasta da ficha que receberá o item."),
            view=PastaInventarioView(interaction.user.id, administrador, "guardar"),
            ephemeral=True,
        )

    @app_commands.command(name="bolcetinha", description="Abre o inventário de uma ficha.")
    async def bolcetinha(self, interaction: discord.Interaction) -> None:
        administrador = bool(interaction.permissions.manage_guild)
        await interaction.response.send_message(
            embed=embed_painel("🎒 Bolcetinha", "Escolha a pasta da ficha cujo inventário deseja abrir."),
            view=PastaInventarioView(interaction.user.id, administrador, "bolsa"),
            ephemeral=True,
        )

    @app_commands.command(name="loot", description="Realiza uma tentativa de loot conforme sua origem.")
    @app_commands.describe(
        origem="Escolha entre Furto, Criatura, Ambiente Urbano ou Ambiente Selvagem"
    )
    @app_commands.choices(
        origem=[app_commands.Choice(name=origem, value=origem) for origem in ORIGENS_LOOT]
    )
    async def loot(self, interaction: discord.Interaction, origem: str) -> None:
        origem = next(
            (oficial for oficial in ORIGENS_LOOT if normalizar_rotulo(oficial) == normalizar_rotulo(origem)),
            "",
        )
        if not origem:
            await interaction.response.send_message(
                "Essa origem de loot não está disponível.",
                ephemeral=True,
            )
            return
        administrador = bool(interaction.permissions.manage_guild)
        if origem == "Criatura":
            await interaction.response.send_message(
                embed=embed_painel(
                    "🐾 Loot de criatura",
                    "Escolha se a criatura é selvagem ou domesticada.",
                ),
                view=TipoCriaturaLootView(interaction.user.id, administrador),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=embed_painel(
                "🎲 Loot",
                f"Origem: **{origem}**. Escolha a pasta da ficha que fará o teste.",
            ),
            view=PastaInventarioView(interaction.user.id, administrador, f"loot|{origem}|"),
            ephemeral=True,
        )
