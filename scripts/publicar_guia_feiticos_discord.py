from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass

import aiohttp


COR_FEITICOS = 0xFFFFFF
COR_RUNAS = 0xDCAC53
COR_TREVAS = 0x200101
COR_TRANSFIGURACAO = 0x755BC0
COR_INDICE = 0x667A92

MENSAGENS_COMPARATIVAS = {
    "feiticos-comparativo-01": "1540879424982089861",
    "feiticos-comparativo-02": "1540879428840591424",
    "feiticos-comparativo-03": "1540879431726399562",
    "feiticos-comparativo-04": "1540879434637254668",
    "feiticos-comparativo-05": "1540879438357725327",
    "feiticos-comparativo-06": "1540879441771626507",
    "feiticos-comparativo-07": "1540879445215416372",
    "feiticos-comparativo-08": "1540879448247640185",
    "feiticos-comparativo-09": "1540879451083247689",
    "feiticos-comparativo-10": "1540879453784113185",
    "feiticos-comparativo-11": "1540879457177567283",
}


@dataclass(frozen=True)
class Secao:
    titulo: str
    descricao: str
    cor: int
    imagem: str | None = None
    campos: tuple[dict[str, object], ...] = ()

    def embed(self) -> dict[str, object]:
        linhas = self.descricao.strip().splitlines()
        descricao_compacta: list[str] = []
        for indice, linha in enumerate(linhas):
            if not linha.strip():
                anterior = linhas[indice - 1].lstrip() if indice else ""
                seguinte = linhas[indice + 1].lstrip() if indice + 1 < len(linhas) else ""
                if anterior.startswith(">") or seguinte.startswith(">"):
                    continue
            descricao_compacta.append(linha)
        dados: dict[str, object] = {
            "title": self.titulo,
            "description": "\n".join(descricao_compacta),
            "color": self.cor,
        }
        if self.imagem:
            dados["image"] = {"url": self.imagem}
        if self.campos:
            dados["fields"] = list(self.campos)
        return dados


def _anos(ids: tuple[str, ...]) -> str:
    return " • ".join(
        f"[{ano}º](https://discord.com/channels/935603393710424084/{thread_id})"
        for ano, thread_id in enumerate(ids, start=1)
    )


SECOES = (
    Secao(
        "🪄 Realizando Feitiços",
        """
_Todo feitiço exige domínio da arte mágica à qual pertence. Sua execução une conhecimento, precisão e a capacidade do bruxo de conduzir aquela forma de magia._

> » Para conjurá-lo, realize **1d20 + o total da Aptidão correspondente** contra a **CD indicada para o ano do personagem** na ficha do feitiço.
> » Se o resultado igualar ou superar a CD, a magia se manifesta. Se ficar abaixo, a conjuração falha.
> » O valor da Aptidão já é o total registrado na ficha: não some novamente atributo ou treinamento.

_Os graus **Básico, Intermediário e Avançado** representam a complexidade da magia. Os algarismos de **I a VII** indicam sua progressão. A tabela individual do feitiço sempre prevalece, pois uma mesma magia pode ser mais difícil para alunos menos experientes e tornar-se mais acessível com os anos de estudo._
""",
        COR_FEITICOS,
        "https://i.imgur.com/WaOtr89.png",
    ),
    Secao(
        "📚 Aptidões da Ficha",
        """
_Cada prática consulta a Aptidão adequada. Atualmente, a ficha reúne:_

> **Defesa contra Arte das Trevas • Transfiguração • Encantamentos • Duelos • Poções • Herbologia • História da Magia • Astronomia • Runas Antigas • Estudo dos Trouxas • Adivinhação • Aritmância • Trato de Criaturas Mágicas • Alquimia • Estudos Antigos • Quadribol • Vôo • Arte das Trevas**

_Para feitiços, utilize a Aptidão informada por sua categoria. Outras práticas, como poções, Runas, voo e Quadribol, consultam seus próprios conhecimentos quando suas regras exigirem._
""",
        COR_FEITICOS,
    ),
    Secao(
        "📌 Classificações Mágicas",
        """
> » **Encantamento** — magia de função objetiva e variada.
> » **Transfiguração** — cria, altera ou reorganiza matéria e forma.
> » **Azaração** — efeito prejudicial geralmente voltado a incômodo, brincadeira ou punição.
> » **Maldição** — magia criada para causar prejuízo grave ou duradouro.
> » **Feitiço de defesa** — ergue proteção contra lampejos, magia hostil ou ataques descritos.
> » **Contra-feitiço** — anula, reverte ou desfaz outra magia.
> » **Medibruxaria** — reúne feitiços, poções e ervas destinados à cura e ao bem-estar.

_A classificação explica a natureza da magia; a categoria de sua ficha determina qual Aptidão participa da conjuração._
""",
        COR_FEITICOS,
    ),
    Secao(
        "✨ Manifestação, Mira e Resposta",
        """
> » **Lampejo** — a magia parte da varinha e percorre uma trajetória visível até o alvo. Pode ser interceptada por barreiras compatíveis e é a única forma de manifestação que permite **Esquiva**, pois existe algo atravessando o espaço do qual o alvo pode sair.

> » **Campo de Visão** — a magia se manifesta diretamente sobre uma criatura, objeto ou ponto que o conjurador consiga enxergar. Não há um projétil viajando entre os dois; perder a visão do alvo, encontrar cobertura total ou deixar de reconhecê-lo pode impedir a aplicação conforme a descrição.

> » **Intuição** — a magia encontra seu alvo por uma percepção, vínculo mental, emoção, identidade ou conexão simbólica. A ficha precisa declarar o que permite reconhecer o alvo, se é necessário vê-lo e quais circunstâncias podem romper essa ligação.

> » **Contato** — exige toque direto pela mão, varinha, objeto conduzido ou outro meio especificado. O conjurador precisa alcançar o alvo antes da manifestação; depois que o contato válido acontece, a reação disponível será a resistência ou defesa indicada pela magia.

> » **Área** — não é uma mira por si só, mas a forma do alvo atingido. A magia pode ocupar círculo, cone, linha, campo, explosão ou outra região. Sua ficha informa o ponto de origem, dimensões, quem pode ser afetado e se aliados também são alcançados.

> » **Condição especial** — certas magias dependem de nome, marca, som, objeto, memória, vínculo, componente ou situação exclusiva. O requisito deve ser descrito expressamente e não pode ser substituído por uma interpretação genérica.

_**Mira**, **alcance** e **alvo** são informações diferentes: a mira explica como a magia chega; o alcance, até onde; e o alvo, quem, o quê ou qual área ela pode afetar. A própria ficha também informa se a resposta é Defesa, Contra-feitiço, Vontade, Fortitude, Reflexo, Especial ou nenhuma._

_Efeitos corpóreos criam ou movimentam matéria física. A proteção necessária deve ser coerente com o que foi manifestado e com as respostas permitidas pela magia._
""",
        COR_FEITICOS,
    ),
    Secao(
        "⏳ Ações e Ativações",
        """
_Uma magia pode exigir uma ação **Livre, de Movimento, Padrão, Completa ou uma Reação**. A ficha determina o tempo necessário; uma ação completa compromete toda a disponibilidade do conjurador naquele turno._

> » **Instantânea** — manifesta e resolve seu efeito imediatamente.
> » **Sustentada** — permanece enquanto o conjurador mantiver concentração. Diante de ataque, dor, pressão ou outra distração, ele realiza **Vontade contra a mesma CD usada para conjurar o feitiço**. A falha encerra a magia.
> » **Preparada** — é conjurada ou reservada para responder a um gatilho declarado. Quando o acontecimento previsto ocorre, a magia é liberada conforme sua ficha.

_Duração, interrupção, acúmulo e encerramento pertencem a cada feitiço. Não existe um limite geral de sustentação baseado apenas no valor da Aptidão._
""",
        COR_FEITICOS,
    ),
    Secao(
        "🚫 Feitiços Acima do Ano",
        """
_Um estudante pode tentar uma magia acima de seu ano somente quando possuir, dentro da narrativa, conhecimento prévio de sua execução. Estudar a fórmula, observar uma demonstração ou receber instrução não elimina a diferença de experiência._

> » A tentativa utiliza a **CD correspondente ao ano atual do personagem** e ocorre com **desvantagem**, representando os riscos de manipular uma magia ainda não dominada pelo currículo comum.
""",
        COR_FEITICOS,
    ),
    Secao(
        "📈 Feitiços Fortificados",
        """
Fortificar um feitiço significa canalizar mais força, concentração e intensidade do que sua manifestação comum suporta. Para cada **+2 acrescentado à CD**, valores numéricos já existentes no efeito recebem um fortalecimento:

• **+1 dado** do mesmo tipo usado pelo efeito original;
• **+2** em bônus numéricos fixos;
• **+1×** quando a magia possuir um multiplicador próprio.

Se a magia tiver dados e bônus fixos, ambos são ampliados. A fortificação nunca cria uma propriedade nova: ela intensifica dano, cura, proteção, duração, alcance ou outro valor que a descrição já permita fortalecer.
""",
        COR_FEITICOS,
    ),
    Secao(
        "💢 Escala de Dano e Cura",
        """
Esta escala orienta os valores máximos esperados para cada grau. A ficha individual da magia continua sendo a autoridade sobre seus dados e efeitos.

**Básico — d4**
Ⅰ • CD 12 a 6 • 1 dado +1 • resultado entre 2 e 5
Ⅱ • CD 14 a 8 • 2 dados +2 • resultado entre 4 e 10

**Intermediário — d6**
Ⅲ • CD 16 a 10 • 2 dados +2 • resultado entre 4 e 14
Ⅳ • CD 18 a 12 • 3 dados +4 • resultado entre 7 e 22
Ⅴ • CD 20 a 14 • 4 dados +6 • resultado entre 10 e 30

**Avançado — d8**
Ⅵ • CD 25 a 18 • 4 dados +6 • resultado entre 10 e 38
Ⅶ • CD 30 a 20 • 6 dados +8 • resultado entre 14 e 56
""",
        COR_FEITICOS,
    ),
    Secao(
        "⏱️ Duração e Resistência",
        """
Como referência, magias **Básicas** costumam durar de **1 a 4 turnos ou rodadas**; **Intermediárias**, de **3 a 6**; e **Avançadas**, de **4 a 10**. Uma duração expressa na própria ficha sempre substitui essa escala.

Quando uma magia permitir resistência e não trouxer uma fórmula especial, a referência por grau é:

**Básico** — CD 12 + Aptidão do conjurador na arte correspondente
**Intermediário** — CD 14 + Aptidão do conjurador
**Avançado** — CD 16 + Aptidão do conjurador

A perícia de resistência — Vontade, Fortitude, Reflexo ou outra — é definida pelo efeito enfrentado.
""",
        COR_FEITICOS,
    ),
    Secao(
        "📜 Runas Antigas",
        """
_Para aqueles que percorrem o caminho do Futhark, uma runa jamais é apenas um desenho. Cada traço reproduz uma parcela da ordem que atravessa os nove mundos; cada corte na madeira, marca na pedra ou inscrição sobre a pele oferece à magia um caminho pelo qual ela pode despertar._

**A runa recebe primeiro um corpo, criado pelas mãos de quem a prepara. Depois recebe intenção, quando seu propósito é escolhido. Somente então recebe poder, despertado pela magia de quem conhece seu verdadeiro significado.**

_Diferentemente dos feitiços, que são lançados em um instante, a magia rúnica exige paciência e precisão. Seu poder não nasce da velocidade, mas da união entre símbolo, suporte e vontade. Uma inscrição corretamente preparada não entrega sua manifestação ao acaso: seus efeitos, sua força e sua duração permanecem tão firmes quanto os traços que lhe deram forma._

As vinte e quatro runas do Futhark são reunidas em três Ætts. Cada um representa uma parte diferente da jornada percorrida entre o mundo material, as provações da existência e aquilo que habita além da carne.

> » **O Primeiro Ætt de Freyr** guarda as forças primordiais da criação, da matéria e das qualidades cultivadas pelo indivíduo. Nele encontram-se o fogo que transforma, a força que sustenta, o caminho que conduz e a prosperidade construída através da troca.

> » **O Segundo Ætt de Heimdall** conduz o iniciado através das provações da sobrevivência. Suas runas falam de necessidade, resistência, destruição, destino e dos desafios que precisam ser atravessados antes que a vitória possa ser alcançada.

> » **O Terceiro Ætt de Tyr** volta-se à natureza mental, espiritual e ancestral. Suas inscrições lidam com sacrifício, renascimento, consciência, herança e com a jornada final daquele que busca ultrapassar os limites de sua própria existência.

Os Ætts, contudo, não formam degraus de poder. Uma runa do Primeiro Ætt pode exigir mais domínio que uma inscrição do Terceiro, pois cada família preserva manifestações simples e forças capazes de tocar a matéria, a mente, o espírito e o destino.

_Por isso, Runas Antigas não seguem a progressão dos anos escolares. O conhecimento rúnico é conquistado por estudo, treinamento, pesquisa, tradição ou experiência. Um personagem somente pode preparar e despertar as runas cujo significado tenha verdadeiramente aprendido._
""",
        COR_RUNAS,
        "https://i.imgur.com/sjG147m.png",
    ),
    Secao(
        "✍️ Preparação e Ativação de Runas",
        """
_Toda runa precisa primeiro receber uma forma física e somente depois pode ser despertada._

> » **Preparação — ação de Movimento:** tempo necessário para desenhar, gravar, entalhar ou marcar corretamente o símbolo em seu suporte.
> » **Ativação — ação Padrão:** o personagem canaliza sua magia através da inscrição e realiza **1d20 + Aptidão em Runas Antigas**.

O resultado precisa alcançar a CD correspondente à manifestação escolhida:

> » **Básico — CD 10**
> » **Intermediário — CD 13**
> » **Avançado — CD 16**

A Aptidão participa da rolagem e não reduz a CD. Fazer uma runa do zero consome, portanto, uma ação de Movimento e uma ação Padrão. Uma runa preparada anteriormente já consumiu sua ação de Movimento e exige somente a ação Padrão para ser ativada.

_Primeiro o conjurador desperta a inscrição. Depois, quando houver resistência, o alvo realiza o teste indicado pela runa. Uma resistência bem-sucedida não significa que a ativação falhou: a runa despertou, mas sua manifestação não conseguiu se fixar sobre aquele alvo._

> A própria capacidade determina a CD e se a resistência utiliza Vontade, Fortitude, Reflexo ou outra defesa apropriada.
""",
        COR_RUNAS,
    ),
    Secao(
        "🪨 Inscrições, Vínculos e Tatuagens",
        """
_Uma inscrição pode permanecer gravada na pele, entalhada em uma arma ou escondida em uma pedra durante muitos anos. Contudo, enquanto não receber uma parcela da magia de seu portador, continuará sendo apenas um símbolo adormecido._

O limite de um bruxo não está na quantidade de marcas que pode carregar, mas em quantas delas consegue manter ligadas à própria essência e prontas para despertar. Ele pode possuir qualquer quantidade razoável de inscrições físicas, tatuagens ou entalhes, mas essas marcas não produzem magia apenas por existirem.

> » Para ser ativada posteriormente, uma runa precisa estar vinculada ao personagem e carregada com sua magia.
> » Cada personagem pode manter uma quantidade de runas vinculadas igual a **1 + Aptidão em Runas Antigas**.
> » Somente essas inscrições estão prontas para despertar através de uma ação Padrão.

_**Tatuagens rúnicas** transformam o próprio corpo em suporte para a magia. A tinta preserva o símbolo, mas é a vontade do portador que decide quando ele deverá despertar. Criar uma tatuagem é um procedimento ritualístico realizado fora de combate; seus traços precisam ser reproduzidos corretamente e podem exigir tintas, sangue, cinzas, ervas ou outros materiais definidos pela manifestação._

> Depois de concluída, a tatuagem torna-se uma matriz permanente e não precisa ser redesenhada a cada utilização.
> Para utilizar uma tatuagem adormecida, o portador emprega uma ação de Movimento para vinculá-la e carregá-la; posteriormente, utiliza uma ação Padrão para ativá-la.
> A tatuagem pode permanecer vinculada entre cenas, permitindo que seja preparada antecipadamente.
""",
        COR_RUNAS,
    ),
    Secao(
        "⚖️ Escala de Efeitos Rúnicos",
        """
_Os valores abaixo determinam o orçamento comum de uma runa, mas não substituem sua identidade. Uma inscrição capaz de produzir uma manifestação extraordinária pode causar menos dano ou não conceder nenhum bônus numérico._

**Dano ou cura instantânea**
> » **Básica** — 4 pontos
> » **Intermediária** — 8 pontos
> » **Avançada** — 12 pontos
> » Uma cura Avançada que exija ritual, materiais raros e limite de uma utilização por episódio pode recuperar até 20 PV.

**Dano contínuo por turno**
> » **Básica** — 2 pontos durante 2 turnos
> » **Intermediária** — 4 pontos durante 3 turnos
> » **Avançada** — 6 pontos durante 4 turnos
> » Uma runa que cause dano em área, imponha penalidades ou altere o ambiente utiliza o dano de uma classificação inferior.

**Bônus**
> » **Básica** — +2 em uma finalidade durante 2 turnos
> » **Intermediária** — +2 em duas finalidades relacionadas durante 3 turnos
> » **Avançada** — +4 em uma finalidade específica ou +2 em uma aplicação ampla durante 4 turnos

Vantagem pode substituir um bônus: uma runa Básica concede vantagem em um teste; uma Intermediária, em até dois testes relacionados; e uma Avançada, em uma finalidade durante até 4 turnos. O benefício deve acompanhar a identidade da runa, não substituir sua capacidade principal.

**Efeitos de controle** duram 1 turno no Básico, 2 no Intermediário e 3 no Avançado.

Vantagem, rompimento, alcance, área e resistência devem aparecer expressamente na capacidade mágica da runa quando existirem.
""",
        COR_RUNAS,
    ),
    Secao(
        "☠️ Arte das Trevas",
        """
_As Artes das Trevas compreendem práticas mágicas que violam deliberadamente os limites naturais da vida, da morte, da liberdade e da própria alma. Sua magia se alimenta de forças como sofrimento, dominação, corrupção, sacrifício, profanação e destruição._

_Um feitiço não pertence às Artes das Trevas apenas porque pode ferir alguém. Ele é considerado trevoso quando seu próprio funcionamento corrompe a alma, viola a vontade de outro ser, profana a vida ou a morte, produz sofrimento como finalidade ou força a magia a ultrapassar seus limites naturais._

**Aprendendo Artes das Trevas**
> Todas essas práticas são proibidas em Hogwarts. Seus feitiços, rituais e métodos não são lecionados nem oferecidos como parte da formação escolar. Em Defesa Contra as Artes das Trevas, os estudantes aprendem a reconhecer sinais, resistir aos efeitos e combater praticantes, mas não são ensinados a conjurá-las.

> Por isso, feitiços das Artes das Trevas não possuem ano de desbloqueio. Um bruxo pode aprendê-los em qualquer ano se encontrar uma fonte capaz de transmitir o conhecimento: mestre, grimório proibido, culto, pacto, artefato, ruína, tradição familiar ou pesquisa clandestina.

> Conhecer o nome de uma magia não significa saber realizá-la. O bruxo precisa aprender efetivamente sua execução. O ano em que se encontra ainda interfere na dificuldade: um estudante jovem pode tentar uma Arte das Trevas avançada que tenha aprendido, mas enfrentará uma CD muito maior que a de um bruxo experiente.

> As Artes das Trevas não possuem graus Básicos I ou II. Sua menor classificação é **Intermediário III**.
""",
        COR_TREVAS,
        "https://i.imgur.com/2Chv3gF.png",
    ),
    Secao(
        "🕯️ Vertentes das Artes das Trevas",
        "As vertentes determinam a natureza da prática e a maneira como ela utiliza as Artes das Trevas. Cada magia possui uma vertente principal, mesmo quando apresenta características relacionadas a outras práticas.",
        COR_TREVAS,
        campos=(
            {"name": "Maldições", "value": "__Maldições atribuem uma condição sobrenatural nociva a uma pessoa, criatura, objeto, lugar ou linhagem.__ Podem permanecer adormecidas, despertar sob determinadas condições, perseguir o alvo por anos ou atravessar gerações. Provocam enfermidades, deformações, azar, dor, loucura, perda de sentidos, deterioração do corpo, fraqueza da alma e outras formas de sofrimento. Sua remoção costuma exigir contramaldição, poção, ritual, condição específica ou destruição da fonte; Finite Incantatem não as desfaz automaticamente, salvo exceções raras.", "inline": False},
            {"name": "Necromancia", "value": "__Necromancia trabalha diretamente com a morte, os mortos e criaturas não-vivas.__ Permite animar cadáveres, criar ou comandar Inferis, aprisionar espíritos, consultar os mortos, manipular restos mortais, drenar energia vital e ligar uma alma a um corpo sem vida. Divindades e entidades exteriores pertencem à Magia Ritualística. Reanimar um corpo não devolve verdadeiramente sua vida: normalmente produz uma criatura sem alma, movida por magia e obrigada a seguir o criador.", "inline": False},
            {"name": "Magia Ritualística", "value": "__A Magia Ritualística estabelece contato com entidades, divindades, forças antigas e inteligências além da compreensão comum.__ Círculos, símbolos, oferendas, sacrifícios, objetos de canalização, posições celestes, palavras específicas e participantes podem integrar sua preparação. Rituais permitem invocar, aprisionar, consultar, barganhar ou pactuar, mas aquilo que responde não precisa ser benevolente, verdadeiro ou obediente e pode cobrar preços inesperados ou explorar as palavras do pedido.", "inline": False},
            {"name": "Alquimia Sombria", "value": "__A Alquimia Sombria utiliza ingredientes, processos mágicos e transformações para corromper matéria, substâncias, corpos e formas de vida.__ Pode alterar seres vivos, modificar cadáveres, produzir híbridos, criar homúnculos, desenvolver substâncias profanas ou conceder propriedades artificiais. Também busca curas, aprimoramentos e prolongamentos antinaturais. Seus resultados podem funcionar, mas normalmente cobram um preço muito maior do que aparentam.", "inline": False},
            {"name": "Magia de Controle", "value": "__A Magia de Controle interfere na vontade, nas emoções, nos pensamentos e nas ações de outro ser.__ Pode provocar impulsos, medo, confiança, obediência, controlar movimentos, alterar decisões ou retirar completamente a autonomia. Diferente da Ilusão, que modifica o que a vítima percebe, o Controle modifica aquilo que ela sente, decide ou faz. Geralmente permite Vontade, embora formas extremas possam exigir condições especiais para serem resistidas ou quebradas.", "inline": False},
            {"name": "Magia de Destruição", "value": "__A Magia de Destruição utiliza forças sombrias para aniquilar corpos, estruturas, terrenos e proteções mágicas.__ Inclui chamas profanas, explosões, corrosão, sufocamento, decomposição, tempestades e manifestações criadas especificamente para devastar. Nem todo feitiço ofensivo pertence a essa vertente: sua finalidade principal precisa ser romper, consumir ou eliminar. Em grande escala, pode atingir aliados, inocentes e o próprio conjurador, continuando a se espalhar depois do primeiro impacto.", "inline": False},
            {"name": "Magia de Ilusão", "value": "__A Magia de Ilusão altera a percepção e faz a vítima experimentar algo que não está realmente presente.__ Imagens, sons, cheiros, sabores, sensações táteis, dor, calor, frio ou cenários completos podem compor a experiência. Manifestações profundas utilizam medos, traumas e lembranças. Mesmo sem ferimentos físicos, podem produzir pânico, confusão, sofrimento psicológico e dano de alma. Contradições, interferências externas e interações impossíveis podem permitir novos testes de Vontade conforme a magia.", "inline": False},
        ),
    ),
    Secao(
        "🖤 Corrupção de Alma",
        """
_As Artes das Trevas não retiram poder apenas da capacidade mágica do conjurador. Sempre que são manifestadas, atravessam e desgastam sua alma, deixando marcas mesmo quando utilizadas com domínio e precisão. A Corrupção não é uma barra separada: ela é representada diretamente por **dano de alma**._

> Depois de realizar com sucesso um feitiço das Artes das Trevas ou concluir um ritual sombrio, o conjurador realiza **Vontade contra a mesma CD usada para executar a magia**, considerando seu ano e o grau de dificuldade. No sucesso, sofre metade do dano correspondente; na falha, sofre o valor integral.

> » **Intermediário III** — 2 no sucesso ou 4 na falha
> » **Intermediário IV** — 3 ou 6
> » **Intermediário V** — 4 ou 8
> » **Avançado VI** — 5 ou 10
> » **Avançado VII** — 6 ou 12

**Regras importantes**
• O teste de Corrupção é separado do teste de execução.
• Se o feitiço não se manifesta, não existe Corrupção de Alma.
• A Corrupção acontece mesmo que o ataque erre ou o alvo resista posteriormente.
• Uma conjuração provoca apenas um teste, independentemente da quantidade de alvos.
• Feitiços sustentados cobram o teste quando se manifestam, não a cada turno.
• Conjurar novamente o mesmo feitiço provoca um novo teste.
• Em rituais, o teste acontece quando o ritual é concluído, salvo consequências adicionais descritas.
• Sacrifícios, sangue, oferendas e outros custos não substituem a Corrupção.
• Algumas vertentes podem impor riscos adicionais além desse dano.
""",
        COR_TREVAS,
    ),
    Secao(
        "🦋 Transfiguração",
        """
_Transfiguração é um ramo da magia que incide sobre a forma ou a aparência de um objeto através da alteração de sua estrutura molecular. Seu domínio não se resume a mudar uma cor: ele exige compreender o estado, a substância, a anatomia e a finalidade daquilo que será transformado._

**Transfiguração Verdadeira**
> Permite transformar coisas nos mais variados níveis.

> » **CD 10** — alterar o estado das coisas, como transformar algo líquido em sólido; modificar substâncias, como água em rum; mudar a cor de um objeto e realizar alterações semelhantes.
> » **CD 12** — transformar um objeto em outro.
> » **CD 14** — transformar um objeto em um animal ou um animal em um objeto.

**Transfiguração Física**
> Refere-se ao ramo capaz de alterar aspectos físicos de um bruxo.

> » **CD 14** — mudar pequenos detalhes, como cor dos olhos, cabelo, unhas, manchas e cicatrizes.
> » **CD 16** — assumir aspectos animalescos, como garras e presas para ataques, asas para movimentação, olhos de águia ou guelras.
> » **CD 18** — mudar aspectos básicos da estrutura corporal, como altura, etnia e detalhes faciais.
> » **CD 20** — alterar aspectos complexos, como estrutura muscular e anatomia, tornando-se mais forte ou mais rápido momentaneamente. Um físico fortalecido pode, por exemplo, conceder **+2 em Atletismo**.
""",
        COR_TRANSFIGURACAO,
    ),
    Secao(
        "🏗️ Conjurare Forma",
        """
_A Transfiguração de Conjuração cria objetos físicos a partir das moléculas presentes no ar. Diferente de uma ilusão, aquilo que é conjurado possui matéria, peso, textura e presença real, podendo ser tocado, usado e movido normalmente enquanto durar o efeito mágico._

> Para executá-la, o bruxo normalmente traça no ar um movimento circular ou retangular com a varinha, como se estivesse abrindo uma planta mágica diante de si. O gesto delimita a forma do objeto. Em seguida, pronuncia `Conjurare Forma`, concentrando-se na estrutura, no tamanho, no material e na função daquilo que deseja trazer à existência.

> A Conjuração não funciona somente com vontade ou imaginação vaga. O bruxo precisa possuir uma **Referência de Forma** que oriente a magia: pergaminho, esboço, planta, catálogo mágico, miniatura ou lembrança visual extremamente precisa. Quanto mais complexo for o objeto, mais detalhada precisa ser essa referência.

> Um aluno iniciante pode conjurar uma caixa ou almofada com uma imagem mental clara. Para criar uma cabana, escada articulada ou sala mobiliada, precisará de um modelo detalhado contendo proporções, materiais, encaixes e organização.

> » **CD 8** — objetos pequenos, simples e temporários: copos, velas, almofadas, bancos baixos, caixas e cordas curtas.
> » **CD 10** — objetos pequenos com função simples: cadeiras, mesas pequenas, escadas curtas, ferramentas, lanternas e prateleiras.
> » **CD 12** — móveis médios e conjuntos simples: cama, escrivaninha, armário, tapete, porta provisória, divisória, baú ou tenda pequena.
> » **CD 14** — objetos grandes ou articulados: escadas maiores, estantes, carrinhos, portas reforçadas, tendas completas e móveis detalhados.
> » **CD 16** — estruturas pequenas: cabanas simples, quiosques, pontes curtas, abrigos e cômodos provisórios.
> » **CD 18** — estruturas complexas e permanentes: cabanas habitáveis, ateliês, salas completas, mobiliário integrado, mecanismos não mágicos simples e ambientes planejados.
> » **CD 20** — casas pequenas, oficinas completas, estufas, salas encantáveis, mecanismos não mágicos complexos e ambientes inteiros, ainda exigindo uma referência extremamente detalhada.

**Riscos e limites**
_A Conjuração não cria seres vivos verdadeiros, alimento nutritivo, dinheiro válido, varinhas, relíquias, artefatos mágicos ou itens únicos. Objetos conjurados podem ser reais e funcionais, mas não possuem propriedades mágicas próprias sem receberem outro encantamento._

_Quando mal executada, pode produzir objetos frágeis, tortos, incompletos, instáveis ou feitos de materiais inadequados. É uma prática delicada porque exige poder mágico, precisão, memória visual, estudo da forma e compreensão da matéria._
""",
        COR_TRANSFIGURACAO,
    ),
    Secao(
        "♻️ Reparifarge",
        """
_**Reparifarge** é o contra-feitiço direto de uma Conjuração. Diferente da Desconjuração, é uma magia simples e específica, usada para reparar um feitiço transfiguratório e fazê-lo voltar a seu estado original._

> Quando usado corretamente, o objeto conjurado retorna à sua forma original de referência. Se a conjuração surgiu de um pergaminho, planta, maquete, desenho, catálogo mágico ou outra representação, a matéria criada se desfaz e a magia volta ao ponto de origem simbólico daquela forma.

> Uma cadeira conjurada a partir de um pergaminho, por exemplo, não é enviada ao entre-lugar. Ela perde a estrutura material criada e retorna ao estado de referência: ideia, imagem ou representação contida naquele pergaminho.

> Por isso, Reparifarge é considerado seguro e comum nas aulas de Transfiguração. Serve para limpar conjurações temporárias, corrigir exercícios malfeitos e encerrar criações que já cumpriram sua função.
""",
        COR_TRANSFIGURACAO,
    ),
    Secao(
        "🕳️ Dissolvere Forma",
        """
_A Desconjuração pode ser usada sobre qualquer matéria inanimada, não apenas objetos conjurados. Ela não apaga nem destrói o objeto. Em vez disso, desfaz sua presença no espaço atual e envia sua estrutura material para uma dimensão instável conhecida informalmente como **entre-lugar**. O feitiço responsável por esse processo é `Dissolvere Forma`._

> Esse espaço se assemelha, em conceito, à Sala Precisa: um lugar moldado pela necessidade, cheio de objetos perdidos, esquecidos, falhados, descartados ou desconjurados ao longo do tempo. Porém, o Vazio das Formas não possui entrada conhecida, não obedece a uma arquitetura estável e não pode ser acessado fisicamente por meios comuns. Objetos desconjurados são “arquivados” pela magia.

> » **CD 12** — objetos pequenos.
> » **CD 14** — móveis simples e objetos medianos.
> » **CD 16** — móveis grandes ou conjuntos simples.
> » **CD 18** — objetos complexos, como automóveis ou tendas estruturadas.
> » **CD 20** — objetos encantados, protegidos ou amaldiçoados, exigindo primeiro a quebra da proteção.
""",
        COR_TRANSFIGURACAO,
    ),
    Secao(
        "🔎 Reconjurare Forma",
        """
_A Reconjuração recupera um objeto enviado ao entre-lugar pela Desconjuração. Ela não cria um novo objeto nem substitui aquilo que foi perdido: traz de volta a matéria original, puxando-a novamente para o plano físico comum. O feitiço responsável é `Reconjurare Forma`._

> Diferente da Conjuração, que utiliza uma referência para criar matéria a partir do ar, a Reconjuração precisa localizar magicamente uma matéria que já existe, mas foi deslocada. Por isso depende de memória, precisão e vínculo conceitual.

> O bruxo precisa possuir uma imagem mental extremamente precisa, incluindo forma, tamanho, peso, material, marcas, função e identidade. Quanto mais único, complexo, antigo ou danificado for o objeto, mais difícil será encontrá-lo e puxá-lo de volta.

> Se a imagem for vaga ou incompleta, a magia pode falhar, trazer um objeto parecido mas errado ou recuperar somente parte da matéria. Descrições, desenhos, registros, lembranças encantadas e fragmentos relacionados ajudam a reforçar a referência.

> A CD é a mesma utilizada para desconjurar o objeto. Em uma falha, ele permanece perdido; falhas graves podem afastá-lo ainda mais, dificultando ou impedindo novas tentativas sem uma referência excepcionalmente forte.
""",
        COR_TRANSFIGURACAO,
    ),
    Secao(
        "🗂️ Bibliotecas Oficiais",
        """
Consulte as fichas completas para conhecer descrição, ano, grau, dificuldade e efeitos de cada magia.
""",
        COR_INDICE,
        campos=(
            {
                "name": "Duelos — por ano",
                "value": _anos(("1528887116359139431", "1528887149947261051", "1528887202854076598", "1528887228007317705", "1528887250425745522", "1528887292897267714", "1528887347926667428")),
                "inline": False,
            },
            {
                "name": "Encantamentos — por ano",
                "value": _anos(("1528904524566364263", "1528904569260609538", "1528904626479431691", "1528904674156085459", "1528904747313139903", "1528904797510697075", "1528904827655033014")),
                "inline": False,
            },
            {
                "name": "Transfiguração — por ano",
                "value": _anos(("1516226309955522630", "1516226341379248148", "1516226445888983044", "1516226480752038048", "1516226526029418520", "1516226670011482182", "1516226716375191703")),
                "inline": False,
            },
            {
                "name": "Defesa Contra Arte das Trevas — por ano",
                "value": _anos(("1528913716181995541", "1528913745584197664", "1528913807668412559", "1528913843584237679", "1528913872600305875", "1528913921430524005", "1528913951134318673")),
                "inline": False,
            },
            {
                "name": "Vertentes das Artes das Trevas",
                "value": "[Maldições](https://discord.com/channels/935603393710424084/1528779736636198953) • [Necromancia](https://discord.com/channels/935603393710424084/1528780157840789608) • [Ritualística](https://discord.com/channels/935603393710424084/1528780517477187665) • [Alquimia Sombria](https://discord.com/channels/935603393710424084/1528780705369423906) • [Controle](https://discord.com/channels/935603393710424084/1528780858671235296) • [Destruição](https://discord.com/channels/935603393710424084/1528780894020702259) • [Ilusão](https://discord.com/channels/935603393710424084/1528780926048407664)",
                "inline": False,
            },
            {
                "name": "Runas Antigas",
                "value": "[Primeiro Ætt](https://discord.com/channels/935603393710424084/1217302949844226150) • [Segundo Ætt](https://discord.com/channels/935603393710424084/1217303113724198912) • [Terceiro Ætt](https://discord.com/channels/935603393710424084/1217303248164356166) • [Bindrunes](https://discord.com/channels/935603393710424084/1530825802973712506)",
                "inline": False,
            },
        ),
    ),
)


GRUPOS = (
    (0, 1),
    (2, 3, 4, 5),
    (6, 7, 8),
    (9, 10),
    (11, 12),
    (13, 15),
    (14,),
    (16,),
    (17, 18),
    (19, 20),
    (21,),
)


def montar_publicacoes() -> list[dict[str, object]]:
    return [
        {
            "nome": f"feiticos-comparativo-{indice:02d}",
            "embeds": [SECOES[numero].embed() for numero in grupo],
        }
        for indice, grupo in enumerate(GRUPOS, start=1)
    ]


def validar(publicacoes: list[dict[str, object]]) -> dict[str, int]:
    total_embeds = 0
    for publicacao in publicacoes:
        embeds = publicacao["embeds"]
        if not isinstance(embeds, list) or not 1 <= len(embeds) <= 10:
            raise ValueError(f"{publicacao['nome']}: quantidade inválida de embeds.")
        soma = 0
        for embed in embeds:
            titulo = str(embed.get("title", ""))
            descricao = str(embed.get("description", ""))
            if len(titulo) > 256:
                raise ValueError(f"{publicacao['nome']}: título excede 256 caracteres.")
            if len(descricao) > 4096:
                raise ValueError(f"{publicacao['nome']}: descrição excede 4096 caracteres.")
            soma += len(titulo) + len(descricao)
            campos = embed.get("fields", [])
            if len(campos) > 25:
                raise ValueError(f"{publicacao['nome']}: mais de 25 campos.")
            for campo in campos:
                nome = str(campo["name"])
                valor = str(campo["value"])
                if len(nome) > 256 or len(valor) > 1024:
                    raise ValueError(f"{publicacao['nome']}: campo excede o limite.")
                soma += len(nome) + len(valor)
        if soma > 6000:
            raise ValueError(f"{publicacao['nome']}: embeds somam {soma}/6000 caracteres.")
        total_embeds += len(embeds)
    return {"publicacoes": len(publicacoes), "embeds": total_embeds}


async def publicar(webhook: str, publicacoes: list[dict[str, object]]) -> None:
    resultados: list[dict[str, str]] = []
    destino = webhook + ("&" if "?" in webhook else "?") + "wait=true"
    async with aiohttp.ClientSession() as sessao:
        for publicacao in publicacoes:
            payload = {
                "embeds": publicacao["embeds"],
                "allowed_mentions": {"parse": []},
            }
            while True:
                resposta = await sessao.post(destino, json=payload)
                if resposta.status == 429:
                    dados = await resposta.json()
                    await asyncio.sleep(float(dados.get("retry_after", 1)))
                    continue
                corpo = await resposta.text()
                if resposta.status >= 400:
                    raise RuntimeError(
                        f"Falha ao publicar {publicacao['nome']}: "
                        f"HTTP {resposta.status}: {corpo}"
                    )
                mensagem = json.loads(corpo)
                resultados.append(
                    {
                        "nome": str(publicacao["nome"]),
                        "id": str(mensagem["id"]),
                        "canal": str(mensagem["channel_id"]),
                    }
                )
                break
            await asyncio.sleep(0.4)
    print(json.dumps(resultados, ensure_ascii=False, indent=2))


async def atualizar(webhook: str, publicacoes: list[dict[str, object]]) -> None:
    resultados: list[dict[str, str]] = []
    async with aiohttp.ClientSession() as sessao:
        for publicacao in publicacoes:
            nome = str(publicacao["nome"])
            destino = f"{webhook}/messages/{MENSAGENS_COMPARATIVAS[nome]}"
            payload = {
                "embeds": publicacao["embeds"],
                "allowed_mentions": {"parse": []},
            }
            while True:
                resposta = await sessao.patch(destino, json=payload)
                if resposta.status == 429:
                    dados = await resposta.json()
                    await asyncio.sleep(float(dados.get("retry_after", 1)))
                    continue
                corpo = await resposta.text()
                if resposta.status >= 400:
                    raise RuntimeError(
                        f"Falha ao atualizar {nome}: HTTP {resposta.status}: {corpo}"
                    )
                mensagem = json.loads(corpo)
                resultados.append({"nome": nome, "id": str(mensagem["id"])})
                break
            await asyncio.sleep(0.4)
    print(json.dumps(resultados, ensure_ascii=False, indent=2))


def main() -> None:
    analisador = argparse.ArgumentParser()
    analisador.add_argument("--validar", action="store_true")
    analisador.add_argument("--publicar", action="store_true")
    analisador.add_argument("--atualizar", action="store_true")
    analisador.add_argument("--somente")
    argumentos = analisador.parse_args()

    publicacoes = montar_publicacoes()
    resumo = validar(publicacoes)
    if argumentos.validar:
        print(json.dumps(resumo, ensure_ascii=False, indent=2))
        return
    if not argumentos.publicar and not argumentos.atualizar:
        raise SystemExit("Use --validar, --publicar ou --atualizar.")

    webhook = os.environ.get("GRIMORY_FEITICOS_WEBHOOK", "").strip()
    if not webhook:
        raise SystemExit("Defina GRIMORY_FEITICOS_WEBHOOK antes de publicar.")
    if argumentos.atualizar:
        if argumentos.somente:
            nomes_somente = {
                nome.strip() for nome in argumentos.somente.split(",") if nome.strip()
            }
            publicacoes = [
                item for item in publicacoes if item["nome"] in nomes_somente
            ]
            encontrados = {str(item["nome"]) for item in publicacoes}
            desconhecidos = nomes_somente - encontrados
            if desconhecidos:
                raise SystemExit(
                    "Publicação desconhecida: " + ", ".join(sorted(desconhecidos))
                )
        asyncio.run(atualizar(webhook, publicacoes))
    else:
        asyncio.run(publicar(webhook, publicacoes))


if __name__ == "__main__":
    main()
