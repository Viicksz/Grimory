"""Publica uma versão revisada do canal Inicio via webhook do Discohook."""

from __future__ import annotations

import asyncio
import json
import os

import aiohttp


WEBHOOK = os.environ.get("GRIMORY_QUADRIBOL_WEBHOOK", "").strip()


EMBEDS = [
    {
        "title": "📌 Conceitos Iniciais",
        "color": 0x5865F2,
        "description": (
            "_Antes de escolher sua história, conheça os valores que sustentam a ficha._\n\n"
            "**Pontos de Vida (PV)**\n"
            "> Quando um personagem sofre dano, seja por combate, acidente ou magia, seus pontos de vida são reduzidos de acordo com a quantidade e o tipo de dano recebido. Se os PV chegarem a zero ou menos, ele fica inconsciente e precisa realizar pelo menos três testes de salvaguarda para evitar a morte.\n"
            "» **PV iniciais:** `10 + Constituição`\n"
            "» **PV por nível:** `5 + Constituição`\n\n"
            "**Pontos de Habilidade (PH)**\n"
            "> Os pontos de habilidade representam a energia que o personagem gasta para executar suas habilidades pessoais. Cada habilidade possui um custo específico; quando esse custo ultrapassa a reserva de PH, ela não pode ser realizada.\n"
            "» **PH iniciais:** `Sabedoria ÷ 2`\n"
            "» **PH por nível:** `2 + Sabedoria`\n\n"
            "**Integridade da Alma**\n"
            "> A integridade da alma representa a estabilidade mental, emocional e espiritual do personagem. Eventos traumáticos, horrores sobrenaturais e forças malignas podem desgastá-la, provocando paranoia, alucinações ou perda de controle.\n"
            "» **Valor inicial:** `100%`"
        ),
    },
    {
        "title": "📋 Atributos",
        "color": 0x5865F2,
        "description": (
            "_Os atributos formam o alicerce físico, mental e social do personagem. Eles influenciam suas perícias e resistências._\n\n"
            "» **Força** — potência física, esforço e impacto.\n"
            "» **Destreza** — coordenação, velocidade, precisão e reação.\n"
            "» **Constituição** — vigor, saúde e resistência corporal.\n"
            "» **Inteligência** — raciocínio, memória e conhecimento.\n"
            "» **Sabedoria** — percepção, intuição, vontade e conexão interior.\n"
            "» **Carisma** — presença, influência e expressão pessoal.\n\n"
            "» **Na criação:** o personagem começa com `14 pontos de atributo`.\n"
            "» **Ao subir de nível:** recebe `2 pontos de atributo`."
        ),
    },
    {
        "title": "📌 Perícias e Bônus",
        "color": 0x5865F2,
        "description": (
            "_Uma perícia representa treinamento, experiência e talento em uma área de conhecimento ou prática._\n\n"
            "» **Inexperiente:** `+0`\n"
            "» **Treinado:** `+2`\n"
            "» **Expert:** `+4`\n"
            "» **Mestre:** `+6`\n\n"
            "Ao realizar um teste, some o modificador do atributo utilizado ao bônus de treinamento da perícia. O valor exibido na ficha já reúne esses componentes; não acrescente o treinamento uma segunda vez.\n\n"
            "» **Na criação:** o personagem começa com `2 perícias treinadas`.\n"
            "» **Treinada:** custo de `50 XP`.\n"
            "» **Expert:** perícia Treinada + `100 XP`.\n"
            "» **Mestre:** perícia Expert + `150 XP`."
        ),
    },
    {
        "title": "🪄 Aptidões Mágicas",
        "color": 0x5865F2,
        "description": (
            "_As Aptidões indicam o domínio do personagem sobre diferentes práticas mágicas. Quando uma magia exige uma Aptidão, use o total correspondente registrado na ficha._\n\n"
            "**Obrigatórias**\n"
            "» Defesa contra Arte das Trevas\n» Transfiguração\n» Encantamentos\n» Duelos\n» Poções\n» Herbologia\n» História da Magia\n» Astronomia\n\n"
            "**Opcionais**\n"
            "» Runas Antigas\n» Estudo dos Trouxas\n» Adivinhação\n» Aritmância\n» Trato de Criaturas Mágicas\n\n"
            "**Extracurriculares**\n"
            "» Alquimia\n» Estudos Antigos\n» Quadribol\n» Vôo\n\n"
            "**Arte proibida**\n"
            "» Arte das Trevas\n\n"
            "Para aumentar uma Aptidão Mágica em `+1`, compre o próximo ponto com XP. O custo segue a fórmula `20 × bônus seguinte`."
        ),
    },
    {
        "title": "⬆️ Subindo de Nível",
        "color": 0x5865F2,
        "description": (
            "_Cada nível representa evolução física, mental e mágica. O custo do próximo nível é calculado pela fórmula `50 × próximo nível` e se soma aos custos anteriores._\n\n"
            "**Exemplo: do nível 1 ao nível 4**\n"
            "» Nível 1 → `50 XP`\n"
            "» Nível 2 → `100 XP`\n"
            "» Nível 3 → `150 XP`\n"
            "» Nível 4 → `200 XP`\n"
            "» **Total:** `500 XP`\n\n"
            "Ao subir de nível, o personagem recebe normalmente os bônus de evolução: pontos de atributo, PV e PH conforme as regras acima.\n\n"
            "**Ganhando XP**\n"
            "» Participar de aulas e treinos: `2 XP`.\n"
            "» Concluir Side-quests de outros alunos: `20 XP + bônus de dificuldade`.\n"
            "» Concluir arcos de campanha: `100 XP + bônus de dificuldade`.\n"
            "» Habilidades específicas: quantidade variável."
        ),
    },
    {
        "title": "❤️ Grifinória",
        "color": 0xC0392B,
        "description": (
            "Lar dos bravos e cavalheiros, o símbolo da Gryffindor apresenta em seu estandarte um orgulhoso leão, acompanhado das cores vermelha e amarelo-dourada. A Casa valoriza feitos de coragem e superação pessoal que costumam ser realizados por altruísmo. Seus estudantes tendem a ser bastante aventureiros, mas se destacam, sobretudo, pela lealdade.\n\n"
            "Entretanto, os alunos da Gryffindor podem ser imprudentes nos atos de bravura, muitas vezes por teimosia ou falta de melhor julgamento da situação — o que pode ser visto como egoísmo. Alvo Dumbledore, Harry Potter e Minerva McGonagall são alguns dos membros mais conhecidos da Casa.\n\n"
            "» **Perícia da Casa:** escolha entre `(FOR) Atletismo` ou `(DES) Iniciativa`."
        ),
    },
    {
        "title": "💛 Lufa-Lufa",
        "color": 0xF1C40F,
        "description": (
            "Os estudantes da Hufflepuff são dedicados, pacientes e honestos. Suas admiráveis características os tornam trabalhadores árduos e modestos, sendo receptivos a todos os demais tipos de bruxos. Por outro lado, o excesso dessas qualidades pode se tornar um ponto negativo: justamente por sua flexibilidade e compreensão, os alunos podem ser complacentes e muito dependentes de outras pessoas, tornando-se ingênuos.\n\n"
            "O estandarte da Hufflepuff apresenta vívido amarelo e preto como as principais cores, com um astuto texugo como mascote. Seus membros mais conhecidos são Newt Scamander, Cedrico Diggory e Ninfadora Tonks.\n\n"
            "» **Perícia da Casa:** escolha entre `(SAB) Vontade` ou `(CAR) Sorte`."
        ),
    },
    {
        "title": "💙 Corvinal",
        "color": 0x3498DB,
        "description": (
            "Os bruxos pertencentes à Ravenclaw se destacam por sua exímia inteligência. Nesse contexto, suas principais características são relacionadas a sabedoria, criatividade e personalidade única, o que garante a eles certa excentricidade. Contudo, a valorização exacerbada do academicismo pode torná-los perfeccionistas, frios, insensíveis e demasiadamente críticos em relação às outras Casas.\n\n"
            "Um misterioso corvo (ou uma águia, conforme algumas representações), acompanhado das cores azul e bronze, compõe o estandarte da Ravenclaw. Entre seus membros mais populares, estão Luna Lovegood, Gilderoy Lockhart e Garrick Olivaras. Curiosamente, Rowena Ravenclaw é a única entre os quatro fundadores de Hogwarts sem uma tradução regionalizada para seu nome.\n\n"
            "» **Perícia da Casa:** escolha entre `(INT) Investigação` ou `(SAB) Percepção`."
        ),
    },
    {
        "title": "💚 Sonserina",
        "color": 0x2ECC71,
        "description": (
            "Os membros da Slytherin têm como características, sobretudo, a ambição e a busca pela grandeza, por isso estão sempre se dedicando a alcançar e expandir metas e se empenhando com inteligência em diversas áreas da magia. Por outro lado, essas qualidades podem promover um senso de competição muito aflorado, o que os torna presunçosos e egoístas.\n\n"
            "Com uma imponente serpente como mascote, o estandarte da Slytherin é colorido com verde e prata. Alguns de seus membros mais populares são Merlin, Tom Riddle, Draco Malfoy e Dolores Umbridge.\n\n"
            "» **Perícia da Casa:** escolha entre `(DES) Furtividade` ou `(CAR) Enganação`."
        ),
    },
    {
        "title": "🧍 Família 🧍",
        "color": 0xD4AF37,
        "description": (
            "💎 **Classe Social**\n"
            "_A classe social de sua família afeta sua situação monetária, social, assim como seu status e fama. Para determinar a classe social, realize `1d6`._\n"
            "» `0` **Pobre** — resultado de uma família nascida trouxa após o modificador de `-1`.\n"
            "» `1–2` **Média**\n"
            "» `3–4` **Alta**\n"
            "» `5–6` **Prestígio**\n"
            "_Se o seu personagem vier de uma família trouxa, aplique um modificador de `-1` no teste. Quando o resultado cair em `0`, a classe social atribuída será Pobre._\n\n"
            "**Pobre** — inicia sem Galeões.\n"
            "**Média** — inicia com 10 Galeões (US$ 250,00).\n"
            "**Alta** — inicia com 25 Galeões (US$ 625,00).\n"
            "**Prestígio** — inicia com 50 Galeões (US$ 1.250,00).\n\n"
            "⚖️ **Conversão**\n"
            "`17 Sicles` = `1 Galeão`\n"
            "`29 Nuques` = `1 Sicle`\n"
            "`493 Nuques` = `1 Galeão`\n\n"
            "💵 **Dólares**\n"
            "`1 Galeão` = `US$ 25,00`\n"
            "`1 Sicle` = `US$ 1,50`\n"
            "`1 Nuque` = `US$ 0,05`."
        ),
    },
    {
        "title": "💡 Habilidades",
        "color": 0xE67E22,
        "description": (
            "_A ficha também registra aquilo que torna cada personagem diferente dos demais._\n\n"
            "» **Herança Sanguínea** — a linhagem mágica e os traços que acompanham sua origem.\n"
            "» **Origem Mágica** — experiências e circunstâncias que moldaram sua relação com a magia.\n"
            "» **Especialização** — uma área de domínio que pode conceder benefícios quando a situação corresponde ao treinamento escolhido.\n\n"
            "Esses elementos não substituem atributos, perícias ou Aptidões: eles complementam a história e podem ser consultados quando uma regra ou cena reconhecer sua aplicação."
        ),
    },
    {
        "title": "🧾 Como criar sua ficha",
        "color": 0x9B59B6,
        "description": (
            "_Sua jornada começa pelo comando `/ficha`. A partir dele, você escolhe o que deseja fazer e acompanha cada etapa da montagem da personagem._\n\n"
            "» **Criar** inicia uma ficha nova. Primeiro, escolha a pasta correspondente ao tipo de ficha. Essa escolha não é apenas organizacional: ela define quais perguntas aparecerão, quais campos estarão disponíveis e onde o resultado será guardado.\n\n"
            "» **Players** guarda personagens de jogadores e solicita quem será o titular da ficha.\n\n"
            "» **NPCs** abre uma etapa adicional para escolher entre **Bruxo(a)**, **Humano/Trouxa**, **Semi-Humano** e **Espírito**. Cada tipo possui informações próprias, por isso o formulário muda conforme a escolha.\n\n"
            "» **Grifinória**, **Sonserina**, **Lufa-Lufa** e **Corvinal** organizam personagens de alunos pela Casa. Nessas pastas, a ficha também permite definir a perícia concedida pela Casa escolhida.\n\n"
            "» **Figuras de Autoridade** é destinada a professores e demais autoridades, com campos próprios para esse tipo de personagem.\n\n"
            "» **Criaturas** possui um fluxo separado, organizado por espécie e periculosidade, porque suas informações não seguem o mesmo formato de uma ficha humanoide.\n\n"
            "» Depois da pasta e das escolhas específicas do tipo, o formulário apresenta o nível inicial e os dados de identidade, informações, atributos, perícias, Aptidões, herança sanguínea, origem mágica e especialização.\n\n"
            "» Cada etapa pode ser revisada antes do salvamento. O formulário mostra uma prévia completa; confirme apenas quando todos os dados estiverem corretos.\n\n"
            "» Depois de criada, a ficha pode ser consultada pelo próprio `/ficha` e atualizada pelos comandos de edição disponíveis, sem precisar reconstruí-la do zero.\n\n"
            "_Os valores derivados — como Pontos de Vida, Pontos de Habilidade e bônus de perícia — são calculados a partir das informações registradas. Mantenha os dados atualizados para que os valores usados nas regras correspondam à personagem._"
        ),
    },
    {
        "title": "📖 A ficha de personagem",
        "color": 0x9B59B6,
        "description": (
            "_A ficha reúne tudo o que define o personagem dentro e fora de Hogwarts. Ela é apresentada em blocos para que cada informação tenha seu próprio espaço e possa ser consultada sem confusão._\n\n"
            "» **Identidade** reúne o nome, a idade, a altura, a Casa, o ano escolar, o nível e a experiência. É o bloco que identifica quem é a personagem e em que momento da jornada ela está.\n\n"
            "» **Informações** guarda dados complementares, como familiar, Patrono, vínculos, descrições pessoais e outras informações registradas durante a criação ou por comandos próprios.\n\n"
            "» **Recursos** apresenta Pontos de Vida, Pontos de Habilidade e a integridade da Alma. São os valores que acompanham a personagem e podem mudar conforme acontecimentos, descanso ou uso de habilidades.\n\n"
            "» **Atributos** mostra Força, Destreza, Constituição, Inteligência, Sabedoria e Carisma. Eles representam as capacidades fundamentais usadas para calcular e interpretar os testes.\n\n"
            "» **Perícias** reúne o treinamento e o bônus de cada perícia: Atletismo, Reflexo, Pontaria, Vontade, Fortitude e todas as demais áreas utilizadas nas cenas. O valor exibido já considera o modificador correspondente.\n\n"
            "» **Aptidões** apresenta o domínio das práticas mágicas, incluindo Defesa contra Arte das Trevas, Transfiguração, Encantamentos, Duelos, Poções, Quadribol e as demais aptidões registradas.\n\n"
            "» **Habilidades** reúne Herança Sanguínea, Origem Mágica e Especialização, além de habilidades adquiridas que podem ser reconhecidas em situações específicas.\n\n"
            "» **Itens e feitiços** aparecem nos blocos finais quando a personagem possui equipamentos, itens catalogados, feitiços aprendidos ou um Grimório Pessoal.\n\n"
            "_A ficha individual é sempre a referência para os testes e para a interpretação das regras. Quando uma perícia ou Aptidão exibe um bônus, esse valor já considera o treinamento e o modificador correspondente._"
        ),
    },
    {
        "title": "🗒️ Modelo de ficha finalizada",
        "color": 0x9B59B6,
        "description": (
            "```text\n"
            "Nome // Idade: --\n"
            "Altura: --\n"
            "Herança Sanguínea: --\n"
            "Ano: --  //  Nível: --  //  XP: --\n"
            "Familiar: --\n"
            "Patrono: --\n\n"
            "Pontos de Vida: --\n"
            "Pontos de Habilidade: --\n"
            "Alma: 100%\n\n"
            "Atributos\n"
            "Força: --\nDestreza: --\nConstituição: --\nInteligência: --\nSabedoria: --\nCarisma: --\n\n"
            "Perícias\n"
            "Atletismo: --\nLuta: --\nReflexo: --\nAcrobacia: --\nPontaria: --\nEsgrima: --\nFurtividade: --\nIniciativa: --\nMontar: --\nCrime: --\nPrestidigitação: --\nCiência: --\nInvestigação: --\nMedicina: --\nTática: --\nTecnologia: --\nArmas de Fogo: --\nAdestramento: --\nSobrevivência: --\nRastreamento: --\nIntuição: --\nPercepção: --\nVontade: --\nSorte: --\nArtes: --\nPersuasão: --\nEnganação: --\nIntimidação: --\nFortitude: --\n\n"
            "Aptidões\n"
            "Defesa contra Arte das Trevas: --\nTransfiguração: --\nEncantamentos: --\nDuelos: --\nPoções: --\nHerbologia: --\nHistória da Magia: --\nAstronomia: --\nRunas Antigas: --\nEstudo dos Trouxas: --\nAdivinhação: --\nAritmância: --\nTrato de Criaturas Mágicas: --\nAlquimia: --\nEstudos Antigos: --\nQuadribol: --\nVôo: --\nArte das Trevas: --\n\n"
            "Origem Mágica: --\n"
            "Especialização: --\n"
            "```\n"
            "_Este é apenas o formato de apresentação. Os campos recebem os valores escolhidos durante a criação._"
        ),
    },
    {
        "title": "👤 Nome da personagem",
        "description": "_Ficha de Personagem • tipo de ficha_",
        "color": 0x2C2F33,
        "fields": [
            {"name": "Tipo", "value": "--", "inline": False},
            {"name": "Classe Social", "value": "--", "inline": True},
            {"name": "Casa", "value": "--", "inline": True},
            {"name": "Herança Sanguínea", "value": "--", "inline": True},
            {"name": "Núcleo de Varinha", "value": "--", "inline": True},
            {"name": "Lvl", "value": "--", "inline": True},
            {"name": "XP", "value": "--", "inline": True},
            {"name": "Aparência", "value": "--", "inline": False},
            {"name": "📋 Informações", "value": "Altura e Idade: --\nCursando: --\nJogador de Quadribol: --\nSituação no time: --\nFamiliar: --\nPatrono: --", "inline": False},
            {"name": "🎒 Itens", "value": "--", "inline": False},
            {"name": "📊 Estatísticas", "value": "Pontos de Vida: --\nPontos de Habilidade: --\nAlma: --", "inline": False},
            {"name": "📌 Atributos", "value": "Força: --\nDestreza: --\nConstituição: --\nInteligência: --\nSabedoria: --\nCarisma: --", "inline": False},
            {"name": "📌 Perícias", "value": "Atletismo: --\nLuta: --\nReflexo: --\nAcrobacia: --\nPontaria: --\nEsgrima: --\nFurtividade: --\nIniciativa: --\nMontar: --\nCrime: --\nPrestidigitação: --\nCiência: --\nInvestigação: --\nMedicina: --\nTática: --\nTecnologia: --\nArmas de Fogo: --\nAdestramento: --\nSobrevivência: --\nRastreamento: --\nIntuição: --\nPercepção: --\nVontade: --\nSorte: --\nArtes: --\nPersuasão: --\nEnganação: --\nIntimidação: --\nFortitude: --", "inline": False},
            {"name": "📖 Aptidões", "value": "Defesa contra Arte das Trevas: --\nTransfiguração: --\nEncantamentos: --\nDuelos: --\nPoções: --\nHerbologia: --\nHistória da Magia: --\nAstronomia: --\nRunas Antigas: --\nEstudo dos Trouxas: --\nAdivinhação: --\nAritmância: --\nTrato de Criaturas Mágicas: --\nAlquimia: --\nEstudos Antigos: --\nQuadribol: --\nVôo: --\nArte das Trevas: --", "inline": False},
            {"name": "💡 Habilidades", "value": "Evoluções de Herança: --\nOrigens Mágicas: --\nEspecializações: --\nHabilidades adquiridas: --", "inline": False},
            {"name": "🪄 Feitiços", "value": "--", "inline": False},
        ],
    },
    {
        "title": "🔎 Consultar e administrar fichas",
        "color": 0x8E44AD,
        "description": (
            "_No mesmo comando `/ficha`, escolha **Consultar** para localizar uma ficha já existente._\n\n"
            "» Primeiro escolha a pasta: **Players**, **NPCs**, uma das quatro Casas, **Figuras de Autoridade** ou **Criaturas**.\n"
            "» Para personagens e autoridades, o segundo menu separa os nomes pelas faixas **AB, CD, EF, GH, IJ, KL, MN, OP, QR, ST, UV e WXYZ**. Fichas de jogadores ficam na pasta **Players**, mesmo que o personagem pertença a uma Casa.\n"
            "» Depois escolha o nome. A ficha é apresentada em partes quando necessário, sempre nesta ordem: **Identidade**, **Informações**, **Itens**, **Estatísticas**, **Atributos**, **Perícias**, **Aptidões**, **Habilidades** e, por fim, **Feitiços** ou **Grimório Pessoal**.\n"
            "» A divisão existe para preservar a leitura e os limites do Discord; uma ficha grande pode ocupar até três mensagens, sem alterar a ordem dos blocos.\n"
            "» A consulta também mostra imagens, itens guardados, feitiços catalogados, habilidades, efeitos ativos e os valores derivados da ficha."
        ),
    },
    {
        "title": "🎒 Itens, feitiços e habilidades na ficha",
        "color": 0x8E44AD,
        "description": (
            "_A ficha não termina nos atributos._\n\n"
            "» **Informações** registram dados narrativos e equipamentos apresentados pelo personagem. Para jogadores de Quadribol, a Vassoura aparece aqui com o modelo e os bônus reais do catálogo.\n"
            "» **Itens** reúnem o inventário separado por categorias, com quantidade e descrição.\n"
            "» **Feitiços** exibem os feitiços catalogados como favoritos ou conhecidos, com categoria e descrição completa. Para Figuras de Autoridade, essa parte aparece como **Grimório Pessoal**.\n"
            "» **Habilidades** mostram Herança Sanguínea, Origens Mágicas, Especializações, evoluções e efeitos ativos. Essa é a última seção de habilidades antes do bloco de feitiços.\n\n"
            "_Cada alteração feita pelos comandos próprios atualiza a ficha publicada e mantém esses blocos na mesma ordem._"
        ),
    },
]

# Organização final da publicação: as Casas ocupam uma única mensagem, e o
# conjunto de fichas permanece no final da sequência. Todas as embeds usam a
# mesma cor para manter uma identidade visual uniforme.
_titulos_casas = {
    "❤️ Grifinória",
    "💛 Lufa-Lufa",
    "💙 Corvinal",
    "💚 Sonserina",
}
_casas = [embed for embed in EMBEDS if embed.get("title") in _titulos_casas]
EMBEDS = [embed for embed in EMBEDS if embed.get("title") not in _titulos_casas]
if _casas:
    _mencoes_casas = {
        "❤️ Grifinória": "**❤️ <@&937255634024402954>**",
        "💛 Lufa-Lufa": "**💛 <@&937255872126648340>**",
        "💙 Corvinal": "**💙 <@&937255410719653919>**",
        "💚 Sonserina": "**💚 <@&937254921219211285>**",
    }
    _casas_descricao = "\n\n".join(
        f"{_mencoes_casas[embed['title']]}\n{embed['description']}" for embed in _casas
    )
    _indice_ficha = next(
        (indice for indice, embed in enumerate(EMBEDS) if embed.get("title") == "🧾 Como criar sua ficha"),
        len(EMBEDS),
    )
    EMBEDS.insert(
        _indice_ficha,
        {
            "title": "🏰 As Casas de Hogwarts",
            "description": "_Cada Casa possui uma identidade própria e uma perícia que pode ser escolhida durante a criação da ficha._\n\n" + _casas_descricao,
            "color": 0x5865F2,
        },
    )

for _embed in EMBEDS:
    _embed["color"] = 0x5865F2

# A consulta real do /ficha dos Players é dividida em blocos. O modelo vazio
# segue a mesma apresentação, apenas substituindo os valores por "--".
_indice_visual = next(
    (indice for indice, embed in enumerate(EMBEDS) if embed.get("title") == "👤 Nome da personagem"),
    None,
)
if _indice_visual is not None:
    EMBEDS.pop(_indice_visual)
    _ficha_vazia = [
        {"title": "👤 Nome da personagem", "description": "_Ficha de Personagem • Players_"},
        {"title": "📋 Informações", "fields": [
            {"name": "Altura e Idade", "value": "--", "inline": True},
            {"name": "Cursando", "value": "--", "inline": True},
            {"name": "Jogador de Quadribol", "value": "--", "inline": True},
            {"name": "Situação no time", "value": "--", "inline": True},
            {"name": "Familiar", "value": "--", "inline": True},
            {"name": "Patrono", "value": "--", "inline": True},
        ]},
        {"title": "🎒 Itens", "description": "💰 **Dinheiro**\n» --\n🪶 **Ingredientes**\n» --\n🥧 **Alimentos**\n» --\n🧭 **Variados**\n» --"},
        {"title": "📊 Estatísticas", "fields": [
            {"name": "Pontos de Vida", "value": "--", "inline": True},
            {"name": "Pontos de Habilidade", "value": "--", "inline": True},
            {"name": "Alma", "value": "--", "inline": True},
        ]},
        {"title": "📌 Atributos", "description": "**Pontos de atributo disponíveis:** --\n\nForça: --\nDestreza: --\nConstituição: --\nInteligência: --\nSabedoria: --\nCarisma: --"},
        {"title": "📌 Perícias", "description": "Atletismo: --\nLuta: --\nReflexo: --\nAcrobacia: --\nPontaria: --\nEsgrima: --\nFurtividade: --\nIniciativa: --\nMontar: --\nCrime: --\nPrestidigitação: --\nCiência: --\nInvestigação: --\nMedicina: --\nTática: --\nTecnologia: --\nArmas de Fogo: --\nAdestramento: --\nSobrevivência: --\nRastreamento: --\nIntuição: --\nPercepção: --\nVontade: --\nSorte: --\nArtes: --\nPersuasão: --\nEnganação: --\nIntimidação: --\nFortitude: --"},
        {"title": "📖 Aptidões", "description": "Defesa contra Arte das Trevas: --\nTransfiguração: --\nEncantamentos: --\nDuelos: --\nPoções: --\nHerbologia: --\nHistória da Magia: --\nAstronomia: --\nRunas Antigas: --\nEstudo dos Trouxas: --\nAdivinhação: --\nAritmância: --\nTrato de Criaturas Mágicas: --\nAlquimia: --\nEstudos Antigos: --\nQuadribol: --\nVôo: --\nArte das Trevas: --"},
        {"title": "💡 Habilidades", "description": "🧬 **Evoluções de Herança:** --\n✨ **Origens Mágicas:** --\n🎓 **Especializações:** --\n\nHabilidades adquiridas: --"},
        {"title": "🪄 Feitiços", "description": "--"},
    ]
    # O cabeçalho textual segue o mesmo padrão usado nas fichas das threads.
    _blocos_ficha = _ficha_vazia
    # Retira os blocos explicativos finais para recolocá-los antes da ficha.
    _explicativos_finais = []
    for _titulo in ("🔎 Consultar e administrar fichas", "🎒 Itens, feitiços e habilidades na ficha"):
        for _embed in list(EMBEDS):
            if _embed.get("title") == _titulo:
                _explicativos_finais.append(_embed)
                EMBEDS.remove(_embed)
    _indice_modelo = next(
        (indice for indice, embed in enumerate(EMBEDS) if embed.get("title") == "🗒️ Modelo de ficha finalizada"),
        len(EMBEDS),
    )
    EMBEDS[_indice_modelo:_indice_modelo] = _explicativos_finais
    for deslocamento, ficha_embed in enumerate(_blocos_ficha):
        ficha_embed["color"] = 0x5865F2
        EMBEDS.append(ficha_embed)


async def publicar() -> str:
    if not WEBHOOK:
        raise RuntimeError("Defina GRIMORY_QUADRIBOL_WEBHOOK antes de publicar.")
    url = WEBHOOK + ("&" if "?" in WEBHOOK else "?") + "wait=true"
    timeout = aiohttp.ClientTimeout(total=30)
    def tamanho_embed(embed: dict) -> int:
        return (
            len(embed.get("title", ""))
            + len(embed.get("description", ""))
            + sum(len(campo.get("name", "")) + len(campo.get("value", "")) for campo in embed.get("fields", []))
        )

    lotes: list[list[dict]] = []
    lote: list[dict] = []
    tamanho = 0
    for embed in EMBEDS:
        custo = tamanho_embed(embed)
        if lote and (len(lote) >= 10 or tamanho + custo > 5800):
            lotes.append(lote)
            lote, tamanho = [], 0
        lote.append(embed)
        tamanho += custo
    if lote:
        lotes.append(lote)
    respostas = []
    async with aiohttp.ClientSession(timeout=timeout) as sessao:
        for lote in lotes:
            payload = {"username": "Grimory", "embeds": lote}
            if any(embed.get("title") == "👤 Nome da personagem" for embed in lote):
                payload["content"] = (
                    "## ══════◄•• 👤 ••►══════\n"
                    "## Nome da personagem\n"
                    "## *Ficha de Personagem • Players*\n"
                    "## ══════◄•• 👤 ••►══════"
                )
            async with sessao.post(url, json=payload) as resposta:
                corpo = await resposta.text()
                if resposta.status >= 400:
                    raise RuntimeError(f"Discord recusou a publicação ({resposta.status}): {corpo}")
                respostas.append(corpo)
    return "\n".join(respostas)


if __name__ == "__main__":
    print(asyncio.run(publicar()))
