from __future__ import annotations

from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands


COR_AJUDA = 0x5865F2


@dataclass(frozen=True)
class ComandoAjuda:
    uso: str
    explicacao: str
    administrativo: bool = False


@dataclass(frozen=True)
class CategoriaAjuda:
    chave: str
    nome: str
    emoji: str
    cor: int
    resumo: str
    comandos: tuple[ComandoAjuda, ...]


CATEGORIAS_AJUDA: tuple[CategoriaAjuda, ...] = (
    CategoriaAjuda(
        chave="consultas",
        nome="Consultas",
        emoji="🔎",
        cor=0x3498DB,
        resumo=(
            "Comandos para localizar e consultar conteúdos oficiais da biblioteca do "
            "Grimory sem alterar os arquivos cadastrados."
        ),
        comandos=(
            ComandoAjuda(
                "/habilidade categoria: nome:",
                "Consulta a ficha de uma habilidade oficial. Primeiro escolha entre "
                "Herança Sanguínea, Origem Mágica ou Especialização; depois selecione o nome sugerido.",
            ),
            ComandoAjuda(
                "/interagir criatura:",
                "Abre a ficha completa de uma criatura mágica cadastrada, incluindo sua imagem e "
                "as informações de interação e manejo.",
            ),
            ComandoAjuda(
                "/preparar nome:",
                "Mostra a receita completa de uma poção: apresentação, ingredientes, modo de preparo, "
                "efeitos e demais dados. Também permite consultar o índice de Poções.",
            ),
            ComandoAjuda(
                "/executar nome:",
                "Exibe as informações necessárias para executar um feitiço, uma arte das trevas, "
                "uma runa ou uma bindrune. Ao escolher uma categoria, os nomes do índice se tornam "
                "links para as mensagens oficiais; o campo também oferece sugestões da biblioteca.",
            ),
        ),
    ),
    CategoriaAjuda(
        chave="dados",
        nome="Rolagens e dados",
        emoji="🎲",
        cor=0xE67E22,
        resumo=(
            "Ferramentas para realizar rolagens durante cenas, aulas, duelos e outras ações do jogo."
        ),
        comandos=(
            ComandoAjuda(
                "/rolar dado:",
                "Realiza rolagens simples, expressões com modificadores e repetições. Exemplos: "
                "`d20`, `1d4+1`, `d20+d6+5` e `2#d20+5`.",
            ),
        ),
    ),
    CategoriaAjuda(
        chave="fichas",
        nome="Fichas",
        emoji="🧙",
        cor=0x9B59B6,
        resumo=(
            "Criação, consulta e gerenciamento das fichas de personagens e das fichas de combate "
            "de criaturas. Os formulários conduzem cada etapa e mostram uma prévia antes de salvar."
        ),
        comandos=(
            ComandoAjuda(
                "/ficha",
                "Abre o painel unificado. Primeiro escolha **Criar** ou **Consultar** e depois a pasta. "
                "A pasta encaminha o fluxo para personagens, NPCs, Figuras de Autoridade, Casas ou "
                "Criaturas. Na criação, os formulários conduzem as etapas; na consulta, a ficha é "
                "localizada pelas divisões da biblioteca e abre seus controles disponíveis.",
            ),
        ),
    ),
    CategoriaAjuda(
        chave="xp",
        nome="Banco de XP",
        emoji="💰",
        cor=0xF1C40F,
        resumo=(
            "Comandos para abrir e consultar contas, receber XP por ações válidas e usar recursos "
            "ligados à Herança Sanguínea. As opções exibidas respeitam a ficha e a permissão de quem usa."
        ),
        comandos=(
            ComandoAjuda(
                "/abrir-conta nome:",
                "Abre sua conta pessoal no Banco de XP. Cada usuário pode possuir uma conta, e o nome "
                "escolhido precisa ser único.",
            ),
            ComandoAjuda(
                "/conta nome:",
                "Consulta o saldo e os dados de uma conta. Jogadores veem apenas a própria conta; "
                "administradores podem consultar todas.",
            ),
            ComandoAjuda(
                "/xp",
                "Abre o painel de XP. Jogadores encontram as opções de Herança Sanguínea e Aula ou "
                "Treino; administradores também podem registrar Side-Quest, Arco de Campanha, Crédito e Débito.",
            ),
            ComandoAjuda(
                "/gringots",
                "Abre o painel monetário para creditar ou debitar Galeões, Sicles e Nuques no inventário "
                "de uma ficha. Administradores podem movimentar fichas disponíveis; jogadores usam as próprias.",
            ),
        ),
    ),
    CategoriaAjuda(
        chave="inventario",
        nome="Itens e loot",
        emoji="🎒",
        cor=0xA67C52,
        resumo=(
            "Inventários vinculados às fichas e rolagens de loot conforme a origem narrativa."
        ),
        comandos=(
            ComandoAjuda(
                "/guardar",
                "Escolhe a pasta e a ficha, define o tipo do item, preenche seu nome e detalhes e "
                "seleciona a quantidade. O inventário e a publicação da ficha são atualizados juntos.",
            ),
            ComandoAjuda(
                "/bolcetinha",
                "Abre somente o inventário da ficha escolhida. O painel permite consultar as categorias "
                "e remover itens, refletindo a alteração na ficha publicada.",
            ),
            ComandoAjuda(
                "/loot origem:",
                "Escolhe Furto, Criatura, Ambiente Urbano ou Ambiente Selvagem, seleciona a ficha e "
                "rola Crime, Trato de Criaturas Mágicas ou Sobrevivência. Criaturas domesticadas dão "
                "vantagem; resultados acima de 20 concedem um item decidido pelo mestre.",
            ),
        ),
    ),
    CategoriaAjuda(
        chave="combate",
        nome="Combate",
        emoji="⚔️",
        cor=0x992D22,
        resumo=(
            "Condução de combates entre Aliados e Oponentes com iniciativa, turnos, "
            "rolagens e recursos temporários integrados às fichas de personagens e criaturas."
        ),
        comandos=(
            ComandoAjuda(
                "/combate",
                "Abre um campo de batalha persistente, permite adicionar fichas às duas equipes, "
                "controlar PV, PH e turnos, realizar rolagens internas ou externas e encerrar a cena.",
                administrativo=True,
            ),
        ),
    ),
    CategoriaAjuda(
        chave="quadribol",
        nome="Quadribol",
        emoji="🧹",
        cor=0x2ECC71,
        resumo=(
            "Consulta e administração do sistema de Quadribol: catálogo de vassouras, escalações, "
            "inscrição de jogadores e condução das partidas."
        ),
        comandos=(
            ComandoAjuda(
                "/vassouras",
                "Abre o catálogo de vassouras e permite consultar as fichas completas por linha e modelo.",
            ),
            ComandoAjuda(
                "/manobras",
                "Consulta as manobras de Quadribol ou abre o painel para criar e publicar uma nova manobra.",
            ),
            ComandoAjuda(
                "/time",
                "Abre o painel para consultar uma das quatro Casas ou um Time Amador, ou criar um "
                "novo time com sua escalação de sete jogadores.",
            ),
            ComandoAjuda(
                "/quadribol",
                "Inicia uma Partida Oficial entre Casas ou uma Partida Amistosa entre Times Amadores, "
                "permitindo conduzir turnos, ações, placar e encerramento.",
                administrativo=True,
            ),
        ),
    ),
    CategoriaAjuda(
        chave="taca",
        nome="Taça das Casas",
        emoji="🏆",
        cor=0xD4AF37,
        resumo=(
            "Acompanha a disputa entre as Casas e registra gratificações ou penalidades vinculadas "
            "a estudantes e Figuras de Autoridade."
        ),
        comandos=(
            ComandoAjuda(
                "/taca-das-casas",
                "Publica a classificação e a pontuação atual das Casas. O painel também oferece aos "
                "moderadores o sorteio de acontecimentos.",
            ),
            ComandoAjuda(
                "/gratificação usuario:",
                "Concede pontos à Casa de um estudante por uma categoria válida, com escolha da Figura "
                "de Autoridade e prévia da publicação.",
                administrativo=True,
            ),
            ComandoAjuda(
                "/penalidade usuario:",
                "Registra a retirada de pontos da Casa de um estudante, selecionando intensidade, "
                "ocorrência e Figura de Autoridade antes da confirmação.",
                administrativo=True,
            ),
            ComandoAjuda(
                "/passagem-de-ano",
                "Mostra uma prévia administrativa para avançar idade e ano cursando dos alunos, "
                "subir o nível das fichas e reiniciar a Taça das Casas com cópia de segurança.",
                administrativo=True,
            ),
        ),
    ),
    CategoriaAjuda(
        chave="narrativa",
        nome="Narrativa",
        emoji="📖",
        cor=0x1ABC9C,
        resumo=(
            "Organiza o encerramento e a retomada das sessões narrativas, preservando separadamente "
            "o ponto em que cada personagem terminou sua história."
        ),
        comandos=(
            ComandoAjuda(
                "/encerrar",
                "Inicia o registro da Última Sessão. O moderador escolhe os participantes autorizados, "
                "e cada um informa a situação narrativa e os valores atuais de PV e PH do próprio personagem.",
                administrativo=True,
            ),
            ComandoAjuda(
                "/recapitular",
                "Mostra a última sessão concluída, reunindo os registros narrativos dos personagens "
                "para que o grupo retome a história.",
            ),
        ),
    ),
    CategoriaAjuda(
        chave="biblioteca",
        nome="Administração da biblioteca",
        emoji="📚",
        cor=0xE74C3C,
        resumo=(
            "Ferramentas administrativas para incluir, corrigir ou retirar conteúdos do Grimory. "
            "As alterações importantes passam por prévia e confirmação."
        ),
        comandos=(
            ComandoAjuda(
                "/add categoria:",
                "Adiciona Feitiços, Artes das Trevas, Bindrunes, Poções, Criaturas ou Habilidades. "
                "O formulário muda conforme a categoria e só salva e publica após aprovação.",
                administrativo=True,
            ),
            ComandoAjuda(
                "/edit categoria: item:",
                "Localiza um conteúdo existente, abre o editor adequado à sua estrutura e mostra a "
                "prévia antes de substituir os dados salvos e a publicação correspondente.",
                administrativo=True,
            ),
            ComandoAjuda(
                "/revisar-feiticos",
                "Percorre os feitiços da biblioteca por categoria e ano ou classificação interna, "
                "permitindo estruturar suas regras de combate e conferir a prévia antes de salvar.",
                administrativo=True,
            ),
            ComandoAjuda(
                "/remove",
                "Escolhe um item por categoria e o move para a lixeira após confirmação. Também permite "
                "limpar o conteúdo da lixeira sem apagar seus arquivos de categoria.",
                administrativo=True,
            ),
        ),
    ),
)


CATEGORIAS_POR_CHAVE = {categoria.chave: categoria for categoria in CATEGORIAS_AJUDA}


def embed_inicial() -> discord.Embed:
    embed = discord.Embed(
        title="📕 Ajuda do Grimory",
        description=(
            "Escolha abaixo a categoria que melhor representa o que você deseja fazer. "
            "Cada página explica a finalidade da categoria e o funcionamento de seus comandos.\n\n"
            "Os comandos marcados com **🔒 Administração** exigem a permissão "
            "**Gerenciar servidor**."
        ),
        color=COR_AJUDA,
    )
    for categoria in CATEGORIAS_AJUDA:
        embed.add_field(
            name=f"{categoria.emoji} {categoria.nome}",
            value=f"*{categoria.resumo}*",
            inline=False,
        )
    embed.set_footer(text="Este painel é visível somente para você.")
    return embed


def embed_categoria(categoria: CategoriaAjuda) -> discord.Embed:
    embed = discord.Embed(
        title=f"{categoria.emoji} Ajuda — {categoria.nome}",
        description=categoria.resumo,
        color=categoria.cor,
    )
    for comando in categoria.comandos:
        permissao = "\n🔒 **Administração:** requer Gerenciar servidor." if comando.administrativo else ""
        embed.add_field(
            name=comando.uso,
            value=f"{comando.explicacao}{permissao}",
            inline=False,
        )
    embed.set_footer(
        text=f"{len(categoria.comandos)} comando(s) nesta categoria • Escolha outra categoria abaixo"
    )
    return embed


class AjudaView(discord.ui.View):
    def __init__(self, usuario_id: int):
        super().__init__(timeout=600)
        self.usuario_id = usuario_id
        self.seletor = discord.ui.Select(
            placeholder="Escolha uma categoria de comandos",
            options=[
                discord.SelectOption(
                    label=categoria.nome,
                    value=categoria.chave,
                    emoji=categoria.emoji,
                )
                for categoria in CATEGORIAS_AJUDA
            ],
        )
        self.seletor.callback = self.selecionar_categoria
        self.add_item(self.seletor)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.usuario_id:
            return True
        await interaction.response.send_message(
            "Abra seu próprio painel com `/ajuda`.",
            ephemeral=True,
        )
        return False

    async def selecionar_categoria(self, interaction: discord.Interaction) -> None:
        categoria = CATEGORIAS_POR_CHAVE[self.seletor.values[0]]
        await interaction.response.edit_message(embed=embed_categoria(categoria), view=self)


class Ajuda(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="ajuda",
        description="Explica os comandos do Grimory organizados por categoria.",
    )
    async def ajuda(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=embed_inicial(),
            view=AjudaView(interaction.user.id),
            ephemeral=True,
        )
