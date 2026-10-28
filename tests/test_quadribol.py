from __future__ import annotations

import asyncio
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
from discord.ext import commands

from comandos.ficha import montar_embeds_ficha
from comandos.quadribol import (
    AcoesTurnoView,
    HabilidadeView,
    BalacoView,
    ConfigurarJogadorView,
    ConfigurarPartidaView,
    CentralManobrasView,
    CriarManobraView,
    ConfirmarJogadorView,
    DefesaBalacoView,
    DefesaGolView,
    Quadribol,
    QuadribolView,
    ResistenciaTempoObrigatoriaView,
    RolagensOpostasModal,
    OutrosControlesView,
    PainelResultadoView,
    PosseGolesView,
    SelecionarCasaJogadorView,
    SelecionarCasaTimeView,
    SelecionarFichaJogadorView,
    TentativaGolView,
    ManobraView,
    RascunhoManobra,
    EscolherAlvosCondicaoView,
    EscolherCondicaoCatalogadaView,
    EscolherOrigemEfeitoView,
    VassourasDetalheView,
    VassourasLinhasView,
    VassourasModelosView,
    _embed_painel_acao,
    _embed_resistencia_tempo_obrigatoria,
    embed_partida,
    embed_placar_partida,
    embed_detalhe_manobra,
    embed_resultado_balaco,
    embed_resultado_gol,
    embed_resultado_partida,
    embed_resultado_recuperacao,
    embed_jogador_time,
    embed_catalogo_vassouras,
    embeds_time,
    embed_previa_jogador,
    embed_registro_jogador,
    formatar_cabecalho_vassoura,
    formatar_cabecalho_linha_vassouras,
    lotes_embeds,
    montar_embeds_vassoura,
    montar_embed_linha_vassouras,
    montar_publicacao_linha_vassouras,
)
from utils.fichas import (
    GRUPOS_ALFABETICOS_FICHAS,
    FichaPersonagem,
    ReferenciaFicha,
    salvar_ficha,
)
from utils.quadribol import (
    CONDICOES_QUADRIBOL,
    FORMACAO_PADRAO,
    JOGOS_TEMPORADA,
    PROGRESSO_POMO_POR_VELOCIDADE,
    EfeitoQuadribol,
    EventoPartida,
    JogadorPartida,
    PartidaQuadribol,
    ManobraQuadribol,
    Vassoura,
    adicionar_efeito,
    adicionar_condicao_catalogada,
    adicionar_gol,
    adicionar_manobra_biblioteca,
    executar_poeta,
    executar_rei,
    aplicar_beneficio_manobra,
    aplicar_resultado_na_taca,
    atribuir_posse_goles,
    avancar_rodada,
    avancar_turno,
    bonus_posicao,
    carregar_faltas,
    carregar_manobras,
    carregar_partida,
    validar_nova_manobra,
    casa_da_referencia,
    configurar_jogador,
    criar_partida,
    descricao_vassoura,
    encontrar_vassoura,
    faixa_preco_linha,
    jogador_partida_de_ficha,
    listar_fichas_elegiveis,
    listar_vassouras,
    linhas_vassouras,
    linhas_vassouras_por_preco,
    modificador_condicoes_acao,
    manobra_exige_coordenador,
    perfil_linha_vassoura,
    obter_informacao,
    obter_vassoura_ficha,
    perseguir_pomo,
    preparar_acao,
    preparar_fortitude_tempo_externa,
    preparar_encerramento,
    progresso_necessario_pomo,
    registrar_falta,
    resolver_balaco,
    resolver_penalti,
    resolver_passe_goles,
    resolver_tomada_goles,
    resolver_finta_wronski,
    resolver_resistencia_tempo,
    resolver_tentativa_gol,
    remover_efeito,
    reservas_disponiveis,
    rolar_manobra,
    salvar_partida,
    sincronizar_vassouras_partida,
    testar_recuperacao,
    total_pericia,
    tem_tempo_meteorologico,
)
from utils.taca import CASAS, EstadoTaca


def criar_ficha(
    caminho: Path,
    nome: str,
    casa: str,
    posicao: str = "Artilheiro",
    vassoura: str = "Nimbus de Teste (+3 de Vôo)",
    *,
    prodigio: bool = False,
    situacao: str = "Titular",
    grupo: str | None = None,
) -> ReferenciaFicha:
    grupo_ficha = grupo or casa
    ficha = FichaPersonagem(
        nome=nome,
        grupo=grupo_ficha,
        casa=casa,
        heranca="Puro-Sangue",
        nucleo="Pena de Fênix",
    )
    ficha.atributos["Destreza"] = 16
    ficha.atributos["Força"] = 14
    ficha.atributos["Constituição"] = 14
    ficha.pericias["Iniciativa"] = 2
    ficha.pericias["Pontaria"] = 2
    ficha.pericias["Reflexo"] = 2
    ficha.pericias["Fortitude"] = 2
    ficha.aptidoes["Quadribol"] = 2
    ficha.aptidoes["Vôo"] = 1
    ficha.informacoes = [
        {"titulo": "Jogador de Quadribol", "descricao": posicao},
        {"titulo": "Situação no time", "descricao": situacao},
        {"titulo": "Vassoura", "descricao": vassoura},
    ]
    if prodigio:
        ficha.especializacoes.append("Prodígio do Quadribol")
        ficha.efeitos_habilidades_ativos.append(
            {
                "nome": "Prodígio do Quadribol",
                "efeito": "+2 no teste correspondente à posição do jogador.",
                "duracao": "Até encerrar o efeito",
            }
        )
    salvar_ficha(ficha, caminho, nova=True)
    return ReferenciaFicha(nome, grupo_ficha, caminho)


def jogador(
    nome: str,
    casa: str,
    posicao: str,
    *,
    forca: int = 2,
    fortitude: int = 4,
    vida: int = 3,
    reflexo: int = 4,
    velocidade: int = 0,
    situacao: str = "Titular",
    em_campo: bool = True,
    bonus_pontaria_vassoura: int = 0,
    dado_bonus_pontaria_vassoura: str = "",
    uso_bonus_pontaria: str = "",
) -> JogadorPartida:
    return JogadorPartida(
        nome=nome,
        casa=casa,
        posicao=posicao,
        caminho_ficha=f"{nome}.md",
        vassoura="Teste",
        bonus_vassoura=0,
        vida_vassoura=vida,
        vida_vassoura_maxima=vida,
        iniciativa_dado=10,
        iniciativa_bonus=2,
        iniciativa_total=12,
        quadribol=2,
        voo=2,
        fortitude=fortitude,
        modificador_forca=forca,
        teste_posicao="Pontaria",
        bonus_teste_posicao=4,
        velocidade_vassoura=velocidade,
        reflexo=reflexo,
        situacao=situacao,
        em_campo=em_campo,
        bonus_pontaria_vassoura=bonus_pontaria_vassoura,
        dado_bonus_pontaria_vassoura=dado_bonus_pontaria_vassoura,
        uso_bonus_pontaria=uso_bonus_pontaria,
    )


class FilaDados:
    def __init__(self, *valores: int):
        self.valores = iter(valores)

    def randint(self, minimo: int, maximo: int) -> int:
        valor = next(self.valores)
        if not minimo <= valor <= maximo:
            raise AssertionError("Dado fora dos limites do teste.")
        return valor


def partida_basica(jogadores: list[JogadorPartida] | None = None) -> PartidaQuadribol:
    return PartidaQuadribol(
        identificador="teste",
        jogo="Final",
        casa_1="Grifinória",
        casa_2="Sonserina",
        moderador_id=99,
        criado_em="2026-07-31T12:00:00+00:00",
        jogadores=jogadores or [],
        gols={"Grifinória": 0, "Sonserina": 0},
        progresso_pomos={
            "Grifinória": {"Grifinória": 0, "Sonserina": 0},
            "Sonserina": {"Grifinória": 0, "Sonserina": 0},
        },
        disparadas_pomo={"Grifinória": [], "Sonserina": []},
        rodadas_surgimento_pomo={"1": 1, "2": 1},
    )


class PosseGolesTests(unittest.TestCase):
    def test_passe_empatado_favorece_time_com_a_goles(self) -> None:
        passador = jogador("Passador", "Grifinória", "Artilheiro")
        destino = jogador("Destino", "Grifinória", "Artilheiro")
        interceptador = jogador("Interceptador", "Sonserina", "Artilheiro")
        partida = partida_basica([passador, destino, interceptador])
        partida.posse_goles = passador.nome

        resultado = resolver_passe_goles(
            partida,
            passador.nome,
            destino.nome,
            interceptador.nome,
            resultado_passe_externo=15,
            resultado_interceptacao_externo=15,
        )

        self.assertTrue(resultado.sucesso)
        self.assertEqual(partida.posse_goles, destino.nome)
        self.assertEqual(resultado.bonus_passes_acumulado, 1)
        self.assertEqual(partida.bonus_passes_gol["Grifinória"], 1)

    def test_passes_acumulam_no_proximo_arremesso_e_sao_consumidos(self) -> None:
        primeiro = jogador("Primeiro", "Grifinória", "Artilheiro")
        segundo = jogador("Segundo", "Grifinória", "Artilheiro")
        interceptador = jogador("Interceptador", "Sonserina", "Artilheiro")
        goleiro = jogador("Goleiro", "Sonserina", "Goleiro")
        partida = partida_basica([primeiro, segundo, interceptador, goleiro])
        partida.posse_goles = primeiro.nome

        resolver_passe_goles(
            partida, primeiro.nome, segundo.nome, interceptador.nome,
            resultado_passe_externo=15, resultado_interceptacao_externo=10,
        )
        partida.indice_turno = 1
        resolver_passe_goles(
            partida, segundo.nome, primeiro.nome, interceptador.nome,
            resultado_passe_externo=15, resultado_interceptacao_externo=10,
        )
        partida.indice_turno = 0
        resultado = resolver_tentativa_gol(
            partida, primeiro.nome,
            resultado_artilheiro_externo=10, resultado_goleiro_externo=20,
        )

        self.assertEqual(resultado.bonus_passes_artilheiro, 2)
        self.assertEqual(resultado.total_artilheiro, 12)
        self.assertIn("Passes bem-sucedidos +2", resultado.fontes_artilheiro)
        self.assertEqual(partida.bonus_passes_gol["Grifinória"], 0)

    def test_interceptacao_apaga_sequencia_de_passes(self) -> None:
        passador = jogador("Passador", "Grifinória", "Artilheiro")
        destino = jogador("Destino", "Grifinória", "Artilheiro")
        interceptador = jogador("Interceptador", "Sonserina", "Artilheiro")
        partida = partida_basica([passador, destino, interceptador])
        partida.posse_goles = passador.nome
        partida.bonus_passes_gol["Grifinória"] = 3

        resultado = resolver_passe_goles(
            partida, passador.nome, destino.nome, interceptador.nome,
            resultado_passe_externo=8, resultado_interceptacao_externo=15,
        )

        self.assertFalse(resultado.sucesso)
        self.assertTrue(resultado.sequencia_passes_interrompida)
        self.assertEqual(partida.bonus_passes_gol["Grifinória"], 0)

    def test_pedir_passe_usa_aliado_como_passador(self) -> None:
        solicitante = jogador("Solicitante", "Grifinória", "Artilheiro")
        portador = jogador("Portador", "Grifinória", "Artilheiro")
        interceptador = jogador("Interceptador", "Sonserina", "Artilheiro")
        partida = partida_basica([solicitante, portador, interceptador])
        partida.posse_goles = portador.nome

        resultado = resolver_passe_goles(
            partida,
            solicitante.nome,
            solicitante.nome,
            interceptador.nome,
            resultado_passe_externo=16,
            resultado_interceptacao_externo=12,
        )

        self.assertEqual(resultado.atacante, portador.nome)
        self.assertEqual(partida.posse_goles, solicitante.nome)

    def test_tomada_empatada_favorece_quem_tenta_tomar(self) -> None:
        atacante = jogador("Atacante", "Grifinória", "Artilheiro")
        atacante.atletismo = 6
        atacante.atributo_atletismo = "Destreza"
        portador = jogador("Portador", "Sonserina", "Artilheiro")
        partida = partida_basica([atacante, portador])
        partida.posse_goles = portador.nome

        resultado = resolver_tomada_goles(
            partida,
            atacante.nome,
            resultado_atletismo_externo=14,
            resultado_reflexo_externo=14,
        )

        self.assertTrue(resultado.sucesso)
        self.assertEqual(partida.posse_goles, atacante.nome)

    def test_gol_exige_posse_e_abre_reposicao(self) -> None:
        artilheiro = jogador("A", "Grifinória", "Artilheiro")
        outro = jogador("Outro", "Grifinória", "Artilheiro")
        goleiro = jogador("G", "Sonserina", "Goleiro")
        partida = partida_basica([artilheiro, outro, goleiro])
        partida.posse_goles = outro.nome
        with self.assertRaisesRegex(ValueError, "posse da Goles"):
            resolver_tentativa_gol(partida, artilheiro.nome)

        partida.posse_goles = artilheiro.nome
        resultado = resolver_tentativa_gol(
            partida,
            artilheiro.nome,
            resultado_artilheiro_externo=20,
            resultado_goleiro_externo=10,
        )
        self.assertTrue(resultado.gol)
        self.assertEqual(partida.posse_goles, "")

    def test_finta_destaca_dano_sem_alterar_ficha_e_pula_proximo_turno(self) -> None:
        executor = jogador("Executor", "Grifinória", "Apanhador")
        alvo = jogador("Alvo", "Sonserina", "Apanhador", vida=5)
        partida = partida_basica([executor, alvo])

        resultado = resolver_finta_wronski(
            partida,
            executor.nome,
            gerador=FilaDados(5, 3, 2),
        )

        self.assertFalse(resultado.evitou_colisao)
        self.assertFalse(resultado.resistiu_impacto)
        self.assertEqual(resultado.dano_concussivo, 6)
        self.assertEqual(alvo.vida_vassoura, 2)
        self.assertEqual(alvo.turnos_pulados, 1)
        avancar_turno(partida)
        self.assertEqual(alvo.turnos_pulados, 0)
        self.assertEqual(partida.jogador_atual().nome, executor.nome)
        self.assertTrue(any(evento.tipo == "turno_pulado" for evento in partida.eventos))


class CatalogoVassourasTests(unittest.TestCase):
    def test_catalogo_real_possui_cinquenta_e_tres_modelos_organizados_em_linhas(self) -> None:
        modelos = listar_vassouras()
        self.assertEqual(len(modelos), 53)
        linhas = linhas_vassouras(modelos)
        self.assertEqual(len(linhas), 18)
        self.assertEqual(
            faixa_preco_linha(linhas["Nimbus"]),
            "145 Galeões – 520 Galeões",
        )
        self.assertEqual(
            [item.nome for item in linhas["Cleansweep"]],
            ["Cleansweep", "Cleansweep 5", "Cleansweep 6", "Cleansweep 7", "Cleansweep 11"],
        )
        nimbus = next(item for item in modelos if item.nome == "Nimbus 2000")
        self.assertEqual(
            (
                nimbus.bonus_voo,
                nimbus.bonus_reflexo,
                nimbus.bonus_fortitude,
                nimbus.vida_maxima,
                nimbus.velocidade,
                nimbus.custo,
            ),
            (1, 1, 0, 3, "10m/s", "430 Galeões"),
        )
        self.assertTrue(nimbus.avaliacao_bastian)
        self.assertTrue(all(modelo.imagem_url for modelo in modelos))
        self.assertEqual(
            list(linhas_vassouras_por_preco(modelos)),
            [
                "Artesanal", "Twigger", "Comet", "Bluebottle", "Cleansweep",
                "Cavalier", "Swiftstick", "Starsweeper", "Stormrider",
                "Estrela Cadente", "Nimbus", "Yajirushi", "Oakshaft",
                "Onda Aérea", "Tinderblast", "Thunderbolt", "Turbo", "Firebolt",
            ],
        )

    def test_ficha_completa_da_vassoura_preserva_todos_os_dados(self) -> None:
        modelo = Vassoura(
            nome="Turbo XX",
            bonus_voo=1,
            vida_maxima=3,
            descricao="Descrição integral do modelo.",
            linha="Turbo",
            velocidade="8m/s",
            custo="275 Galeões",
            especificacoes=(
                "+1d4 em testes de Vôo envolvendo arrancadas curtas",
                "Disparada de 17m/s.",
            ),
            bonus_reflexo=2,
            bonus_pontaria=1,
            uso_bonus_pontaria="Interceptação",
            avaliacao_bastian="Avaliação integral de Bastian.",
            imagem_url="https://i.imgur.com/exemplo.png",
        )
        embeds = montar_embeds_vassoura(modelo)
        self.assertEqual(len(embeds), 1)
        self.assertIn("Avaliação integral de Bastian.", embeds[0].description)
        self.assertEqual(
            [(campo.name, campo.value) for campo in embeds[0].fields],
            [
                ("Perfil:", "Descrição integral do modelo."),
                ("Pontos de Vida:", "3"),
                ("Velocidade:", "8m/s"),
                ("Custo:", "275 Galeões"),
                (
                    "Especificações:",
                    "+1d4 em testes de Vôo envolvendo arrancadas curtas\nDisparada de 17m/s.",
                ),
            ],
        )
        self.assertEqual(embeds[0].image.url, "https://i.imgur.com/exemplo.png")
        self.assertIn("## 🧹 Turbo XX", formatar_cabecalho_vassoura(modelo))

    def test_modelos_esportivos_privilegiam_as_necessidades_de_cada_posicao(self) -> None:
        modelos = {item.nome: item for item in listar_vassouras()}

        comet = modelos["Comet 290"]
        self.assertIn(
            "+2 em testes de Reflexo para defender os aros e interceptar a Goles",
            comet.especificacoes,
        )
        self.assertIn(
            "+1d4 em testes de Pontaria para rebater a Goles em direção a um aliado",
            comet.especificacoes,
        )

        cleansweep = modelos["Cleansweep 11"]
        self.assertEqual(
            (cleansweep.bonus_pontaria, cleansweep.dado_bonus_pontaria, cleansweep.uso_bonus_pontaria),
            (1, "", "Finalização"),
        )
        self.assertIn(
            "+1 em testes de Pontaria ao arremessar a Goles contra as balizas",
            cleansweep.especificacoes,
        )

        stormrider = modelos["Stormrider Furacão"]
        self.assertEqual(
            (stormrider.bonus_pontaria, stormrider.dado_bonus_pontaria, stormrider.uso_bonus_pontaria),
            (1, "", "Ataque direto"),
        )
        self.assertIn(
            "+1 em testes de Pontaria para direcionar Balaços contra jogadores adversários",
            stormrider.especificacoes,
        )

        firebolt = modelos["Firebolt"]
        self.assertIn(
            "+1d4 em testes de Voo envolvendo arrancadas competitivas",
            firebolt.especificacoes,
        )

        oakshaft = modelos["Oakshaft 79"]
        self.assertEqual((oakshaft.bonus_fortitude, oakshaft.vida_maxima), (2, 15))

    def test_embed_da_linha_nimbus_preserva_apresentacao(self) -> None:
        embed = montar_embed_linha_vassouras("Nimbus")
        self.assertIsNotNone(embed)
        self.assertIn("A Nimbus entende uma coisa", embed.description)
        modelos = linhas_vassouras()["Nimbus"]
        cabecalho, embeds = montar_publicacao_linha_vassouras("Nimbus", modelos)
        self.assertEqual(len(embeds), 5)
        self.assertIn("## 🧹 Nimbus", cabecalho)
        self.assertEqual(
            [embed.image.url for embed in embeds[1:]],
            [
                "attachment://vassoura-nimbus-1000-d4fee9e14a.webp",
                "attachment://vassoura-nimbus-1700-1efca4f4c3.webp",
                "attachment://vassoura-nimbus-2000-a2c162936b.webp",
                "attachment://vassoura-nimbus-2001-235bed5215.webp",
            ],
        )
        self.assertIn("Linha de Vassouras", formatar_cabecalho_linha_vassouras("Nimbus"))

    def test_catalogo_do_comando_exibe_as_dezoito_linhas(self) -> None:
        embed = embed_catalogo_vassouras()
        self.assertEqual(len(embed.fields), 18)
        self.assertIn("Nimbus", [campo.name for campo in embed.fields])
        cavalier = next(campo for campo in embed.fields if campo.name == "Cavalier")
        self.assertEqual(
            cavalier.value,
            "Estabilidade e controle defensivo para Goleiros e Batedores.\n"
            "*68 Galeões – 215 Galeões*",
        )
        self.assertTrue(all(not campo.inline for campo in embed.fields))
        self.assertNotIn("modelo(s)", "\n".join(campo.value for campo in embed.fields))
        self.assertNotIn("Perfil geral:", cavalier.value)
        self.assertNotIn("Faixa de preço:", cavalier.value)

    def test_perfil_curto_da_linha_vem_da_biblioteca(self) -> None:
        self.assertEqual(
            perfil_linha_vassoura("Cavalier"),
            "Estabilidade e controle defensivo para Goleiros e Batedores.",
        )

    def test_consulta_navega_por_linha_modelo_e_possui_voltas(self) -> None:
        linhas = VassourasLinhasView(55)
        self.assertEqual(linhas.children[0].placeholder, "Escolha a linha da vassoura")
        cavalier = next(
            opcao for opcao in linhas.children[0].options if opcao.value == "Cavalier"
        )
        self.assertEqual(
            cavalier.description,
            "Estabilidade e controle defensivo para Goleiros e Batedores.",
        )
        modelos_nimbus = linhas_vassouras()["Nimbus"]
        modelos = VassourasModelosView(55, "Nimbus", modelos_nimbus)
        self.assertEqual(modelos.children[0].placeholder, "Modelo — Nimbus")
        self.assertEqual(modelos.children[1].label, "Voltar às linhas")
        detalhe = VassourasDetalheView(55, "Nimbus", modelos_nimbus)
        self.assertEqual(
            [item.label for item in detalhe.children],
            ["Voltar aos modelos", "Voltar às linhas"],
        )

    def test_catalogo_carrega_pontaria_condicional_das_vassouras_adaptadas(self) -> None:
        modelos = {item.nome: item for item in listar_vassouras()}
        self.assertEqual(
            (
                modelos["Cavalier Sabre"].bonus_pontaria,
                modelos["Cavalier Sabre"].dado_bonus_pontaria,
                modelos["Cavalier Sabre"].uso_bonus_pontaria,
            ),
            (2, "", "Interceptação"),
        )
        self.assertEqual(
            (
                modelos["Thunderbolt X"].bonus_pontaria,
                modelos["Thunderbolt X"].dado_bonus_pontaria,
                modelos["Thunderbolt X"].uso_bonus_pontaria,
            ),
            (0, "1d4", "Redirecionamento"),
        )
        self.assertEqual(
            (
                modelos["Yajirushi Caçadora"].bonus_pontaria,
                modelos["Yajirushi Caçadora"].dado_bonus_pontaria,
                modelos["Yajirushi Caçadora"].uso_bonus_pontaria,
            ),
            (2, "", "Finalização"),
        )
        self.assertIn(
            "+2 de Pontaria em Interceptação",
            descricao_vassoura(modelos["Cavalier Sabre"]),
        )
        self.assertIn(
            "+1d4 de Pontaria em Redirecionamento",
            descricao_vassoura(modelos["Thunderbolt X"]),
        )

    def test_bonus_dois_fica_so_no_modelo_final_e_nao_existe_bonus_tres(self) -> None:
        modelos = {item.nome: item for item in listar_vassouras()}
        self.assertEqual(
            [modelos[nome].bonus_reflexo for nome in ("Comet 220", "Comet 260", "Comet 290")],
            [1, 1, 2],
        )
        self.assertEqual(
            [
                modelos[nome].bonus_reflexo
                for nome in ("Swiftstick Clássica", "Swiftstick Elite", "Swiftstick Ultra")
            ],
            [1, 1, 2],
        )
        self.assertTrue(
            all(
                0 <= bonus <= 2
                for modelo in modelos.values()
                for bonus in (
                    modelo.bonus_voo,
                    modelo.bonus_reflexo,
                    modelo.bonus_fortitude,
                    modelo.bonus_pontaria,
                )
            )
        )
        for linha, modelos_da_linha in linhas_vassouras_por_preco(modelos.values()).items():
            nomes_com_dois = [
                modelo.nome
                for modelo in modelos_da_linha
                if 2 in (
                    modelo.bonus_voo,
                    modelo.bonus_reflexo,
                    modelo.bonus_fortitude,
                    modelo.bonus_pontaria,
                )
            ]
            if nomes_com_dois:
                self.assertEqual(
                    nomes_com_dois,
                    [modelos_da_linha[-1].nome],
                    msg=f"{linha} possui +2 fora do modelo final.",
                )

    def test_catalogo_exibe_bonus_real_e_vida(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            modelo = Vassoura("Nimbus de Teste", 3, 4, "Somente para testes.")
            (pasta / "Nimbus de Teste.md").write_text(modelo.markdown(), encoding="utf-8")
            carregada = encontrar_vassoura("Nimbus de Teste", pasta)
            self.assertEqual(carregada, modelo)
            self.assertEqual(descricao_vassoura(carregada), "Nimbus de Teste (+3 de Vôo)")
            self.assertEqual(len(listar_vassouras(pasta=pasta)), 1)

    def test_catalogo_omite_aviso_quando_nao_ha_bonus_geral(self) -> None:
        modelo = Vassoura("Yajirushi Arqueiro", 0, 3)
        self.assertEqual(descricao_vassoura(modelo), "Yajirushi Arqueiro")

    def test_arquivo_incompleto_nao_vira_opcao(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            (pasta / "README.md").write_text("# Catálogo\n", encoding="utf-8")
            self.assertEqual(listar_vassouras(pasta=pasta), [])


class JogadorQuadribolTests(unittest.TestCase):
    def test_ficha_de_players_e_elegivel_pela_casa_registrada_nela(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            referencia = criar_ficha(
                Path(temporario) / "Luna.md",
                "Luna",
                "Corvinal",
                grupo="Players",
            )
            self.assertEqual(casa_da_referencia(referencia), "Corvinal")
            with patch("utils.quadribol.listar_fichas", return_value=[referencia]):
                self.assertEqual(listar_fichas_elegiveis(), [referencia])
            ficha = configurar_jogador(
                referencia,
                "Apanhador",
                Vassoura("Nimbus de Teste", 3, 4),
            )
            self.assertEqual(ficha.grupo, "Players")
            self.assertEqual(ficha.casa, "Corvinal")
            self.assertEqual(obter_informacao(ficha, "Jogador de Quadribol"), "Apanhador")

    def test_configuracao_adiciona_e_atualiza_informacoes_sem_duplicar(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "Luna.md"
            referencia = criar_ficha(caminho, "Luna", "Corvinal")
            ficha = configurar_jogador(referencia, "Apanhador", Vassoura("Cometa", 2, 3))
            self.assertEqual(obter_informacao(ficha, "Jogador de Quadribol"), "Apanhador")
            self.assertEqual(obter_informacao(ficha, "Situação no time"), "Titular")
            self.assertEqual(obter_vassoura_ficha(ficha), "Cometa")
            recarregada = FichaPersonagem.carregar(caminho)
            self.assertEqual(
                sum(item["titulo"] == "Vassoura" for item in recarregada.informacoes),
                0,
            )
            vassouras = [
                item for item in recarregada.itens
                if item.get("tipo") == "Vassoura"
            ]
            self.assertEqual(len(vassouras), 2)
            equipada = next(item for item in vassouras if item["equipada"] == "Sim")
            self.assertEqual(equipada["nome"], "Cometa")
            self.assertEqual(equipada["categoria"], "Variados")

    def test_partida_recarrega_vassoura_da_biblioteca_preservando_dano(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            referencia = criar_ficha(
                raiz / "Luna.md",
                "Luna",
                "Corvinal",
                posicao="Apanhador",
                vassoura="Modelo Vivo",
            )
            antigo = Vassoura(
                "Modelo Vivo",
                1,
                5,
                velocidade="6m/s",
                bonus_reflexo=1,
                bonus_fortitude=1,
            )
            item = jogador_partida_de_ficha(
                referencia,
                antigo,
                gerador=random.Random(3),
            )
            item.vida_vassoura = 3
            partida = partida_basica([item])
            pasta = raiz / "vassouras"
            pasta.mkdir()
            atualizado = Vassoura(
                "Modelo Vivo",
                3,
                8,
                velocidade="10m/s",
                bonus_reflexo=3,
                bonus_fortitude=2,
                dado_bonus_pontaria="1d4",
                uso_bonus_pontaria="Interceptação",
            )
            (pasta / "Modelo Vivo.md").write_text(
                atualizado.markdown(), encoding="utf-8"
            )

            self.assertTrue(
                sincronizar_vassouras_partida(
                    partida,
                    pasta_vassouras=pasta,
                )
            )
            self.assertEqual(item.vida_vassoura_maxima, 8)
            self.assertEqual(item.vida_vassoura, 6)
            self.assertEqual(item.velocidade_vassoura, 10)
            self.assertEqual(item.voo, 4)
            self.assertEqual(item.reflexo, 8)
            self.assertEqual(item.fortitude, 6)
            self.assertEqual(item.bonus_teste_posicao, 4)
            self.assertEqual(item.bonus_pontaria_vassoura, 0)
            self.assertEqual(item.dado_bonus_pontaria_vassoura, "1d4")
            self.assertEqual(item.uso_bonus_pontaria, "Interceptação")

    def test_iniciativa_reutiliza_total_da_ficha_sem_somar_destreza_duas_vezes(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            referencia = criar_ficha(Path(temporario) / "Luna.md", "Luna", "Corvinal")
            ficha = FichaPersonagem.carregar(referencia.caminho)
            self.assertEqual(total_pericia(ficha, "Iniciativa"), 5)
            item = jogador_partida_de_ficha(
                referencia,
                Vassoura("Nimbus de Teste", 3, 4),
                gerador=random.Random(7),
            )
            self.assertEqual(item.iniciativa_bonus, 5)
            self.assertEqual(item.iniciativa_total, item.iniciativa_dado + 5)

    def test_bonus_geral_de_reflexo_e_fortitude_da_vassoura_entra_na_partida(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            referencia = criar_ficha(Path(temporario) / "Luna.md", "Luna", "Corvinal")
            ficha = FichaPersonagem.carregar(referencia.caminho)
            reflexo_base = total_pericia(ficha, "Reflexo")
            fortitude_base = total_pericia(ficha, "Fortitude")
            item = jogador_partida_de_ficha(
                referencia,
                Vassoura(
                    "Defensiva",
                    0,
                    5,
                    bonus_reflexo=2,
                    bonus_fortitude=1,
                ),
                gerador=random.Random(4),
            )
            self.assertEqual(item.reflexo, reflexo_base + 2)
            self.assertEqual(item.fortitude, fortitude_base + 1)

    def test_prodigio_aplica_dois_apenas_ao_teste_da_posicao(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            referencia = criar_ficha(
                Path(temporario) / "Luna.md",
                "Luna",
                "Corvinal",
                posicao="Apanhador",
                prodigio=True,
            )
            ficha = FichaPersonagem.carregar(referencia.caminho)
            teste, total = bonus_posicao(ficha, "Apanhador", Vassoura("Nimbus", 3, 4))
            self.assertEqual(teste, "Vôo")
            self.assertEqual(total, 1 + 3 + 2)
            self.assertEqual(ficha.aptidoes["Quadribol"], 2)
            embed = embed_jogador_time(
                ficha,
                "Apanhador",
                "Titular",
                Vassoura("Nimbus", 3, 4),
            )
            campo = next(
                item for item in embed.fields
                if item.name == "Teste principal da posição"
            )
            self.assertIn(
                "**Vôo:** +1 Aptidão +3 Vassoura +2 Habilidade = **+6 total**",
                campo.value,
            )

    def test_prodigio_possuido_mas_inativo_nao_altera_o_teste(self) -> None:
        ficha = FichaPersonagem(
            nome="Reyssa",
            grupo="Lufa-Lufa",
            casa="Lufa-Lufa",
            heranca="Nascido-Trouxa",
            nucleo="Coração de Dragão",
            especializacoes=["Prodígio do Quadribol"],
        )
        ficha.atributos["Destreza"] = 16
        ficha.pericias["Pontaria"] = 2
        teste, total = bonus_posicao(ficha, "Artilheiro", Vassoura("Yajirushi", 0, 0))
        self.assertEqual((teste, total), ("Pontaria", 5))
        embed = embed_jogador_time(
            ficha,
            "Artilheiro",
            "Titular",
            Vassoura("Yajirushi", 0, 0),
        )
        campo = next(item for item in embed.fields if item.name == "Habilidades aplicáveis")
        self.assertIn("Prodígio do Quadribol — 2ph", campo.value)
        self.assertIn("+2 em Pontaria", campo.value)
        self.assertIn("Disponível para ativação", campo.value)

    def test_testes_em_campo_detalham_todas_as_fontes_do_bonus(self) -> None:
        ficha = FichaPersonagem(
            nome="Goleira",
            grupo="Corvinal",
            casa="Corvinal",
            heranca="Meio-Sangue",
            nucleo="Pena de Fênix",
        )
        ficha.atributos["Destreza"] = 16
        ficha.pericias["Reflexo"] = 2
        ficha.pericias["Iniciativa"] = 2
        embed = embed_jogador_time(
            ficha,
            "Goleiro",
            "Titular",
            Vassoura("Defensiva", 2, 0, bonus_reflexo=1),
        )
        principal = next(
            item for item in embed.fields
            if item.name == "Teste principal da posição"
        )
        campo = next(item for item in embed.fields if item.name == "Testes em campo")
        self.assertIn(
            "**Reflexo:** +3 Destreza +2 Treinada +1 Vassoura = **+6 total**",
            principal.value,
        )
        self.assertIn("**Vôo:** +0 Aptidão +2 Vassoura = **+2 total**", campo.value)
        self.assertIn(
            "**Pontaria:** +3 Destreza +0 Inexperiente = **+3 total**",
            campo.value,
        )
        self.assertEqual(
            [
                linha.split("**", 2)[1].rstrip(":")
                for linha in campo.value.splitlines()
            ],
            ["Iniciativa", "Pontaria", "Fortitude", "Vôo", "Quadribol"],
        )

    def test_ficha_do_time_mostra_todas_as_particularidades_da_vassoura(self) -> None:
        ficha = FichaPersonagem(
            nome="Lauriet",
            grupo="Lufa-Lufa",
            casa="Lufa-Lufa",
            heranca="Meio-Sangue",
            nucleo="Pena de Fênix",
        )
        especificacoes = (
            "+1 em testes de Voo envolvendo velocidade em linha reta",
            "+1d4 em testes de Voo envolvendo arrancadas curtas",
            "Disparada de 17m/s com -3 em testes de Controle, Freio e Reflexo até o fim do impulso",
        )
        embed = embed_jogador_time(
            ficha,
            "Apanhador",
            "Titular",
            Vassoura(
                "Turbo XX",
                0,
                3,
                linha="Turbo",
                velocidade="8m/s",
                especificacoes=especificacoes,
            ),
        )
        campo = next(item for item in embed.fields if item.name == "Vassoura")
        self.assertIn("» **PV:** 3\n» **Velocidade:** 8m/s", campo.value)
        for especificacao in especificacoes:
            self.assertIn(f"» {especificacao}", campo.value)

    def test_apresentacao_da_ficha_consulta_bonus_atual_do_catalogo(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            (pasta / "Nimbus.md").write_text(
                Vassoura("Nimbus", 3, 3).markdown(), encoding="utf-8"
            )
            ficha = FichaPersonagem(
                nome="Luna",
                grupo="Corvinal",
                casa="Corvinal",
                heranca="Puro-Sangue",
                nucleo="Pena de Fênix",
            )
            ficha.informacoes = [
                {"titulo": "Vassoura", "descricao": "Nimbus (+1 de Vôo)"}
            ]
            with patch("utils.quadribol.PASTA_VASSOURAS", pasta):
                embeds = montar_embeds_ficha(ficha)
            informacoes = next(item for item in embeds if item.title == "📋 Informações")
            self.assertEqual(informacoes.fields[0].value, "Nimbus (+3 de Vôo)")


class PartidaQuadribolTests(unittest.TestCase):
    def test_criacao_exige_e_ordena_formacao_completa(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            raiz = Path(temporario)
            pasta_fichas = raiz / "fichas"
            pasta_vassouras = raiz / "vassouras"
            pasta_vassouras.mkdir(parents=True)
            modelo = Vassoura("Nimbus de Teste", 3, 4)
            (pasta_vassouras / "Nimbus de Teste.md").write_text(modelo.markdown(), encoding="utf-8")
            for casa in ("Grifinória", "Sonserina"):
                pasta = pasta_fichas / casa
                pasta.mkdir(parents=True)
                numero = 0
                for posicao, quantidade in FORMACAO_PADRAO.items():
                    for _ in range(quantidade):
                        numero += 1
                        criar_ficha(pasta / f"{casa}-{numero}.md", f"{casa}-{numero}", casa, posicao)
            with patch("utils.fichas.PASTA_FICHAS", pasta_fichas):
                partida = criar_partida(
                    "Grifinória",
                    "Sonserina",
                    "1º jogo",
                    55,
                    pasta_vassouras=pasta_vassouras,
                    gerador=random.Random(9),
                )
            self.assertEqual(len(partida.jogadores), 14)
            self.assertEqual(
                [item.iniciativa_total for item in partida.jogadores],
                sorted((item.iniciativa_total for item in partida.jogadores), reverse=True),
            )
            self.assertTrue(
                all(3 <= rodada <= 7 for rodada in partida.rodadas_surgimento_pomo.values())
            )

    def test_placar_esportivo_e_pontos_da_taca_sao_separados(self) -> None:
        partida = partida_basica()
        for _ in range(20):
            adicionar_gol(partida, "Grifinória")
        for _ in range(3):
            adicionar_gol(partida, "Sonserina")
        partida.pomo = "Sonserina"
        partida.estado = "aguardando_confirmacao"
        self.assertEqual(partida.placar("Grifinória"), 200)
        self.assertEqual(partida.placar("Sonserina"), 180)
        self.assertEqual(partida.vencedor(), "Grifinória")
        self.assertEqual(partida.pontos_taca("Grifinória"), 45)
        self.assertEqual(partida.pontos_taca("Sonserina"), 13)
        placar = embed_placar_partida(partida)
        detalhes = embed_partida(partida)
        self.assertIn("Grifinória 200 × 180 Sonserina", placar.description)
        self.assertNotIn("Grifinória 200 × 180 Sonserina", str(detalhes.to_dict()))
        self.assertNotIn("Taça das Casas", str(placar.to_dict()))
        self.assertNotIn("+45", str(placar.to_dict()))

    def test_resultado_final_resume_placar_faltas_e_penaltis_sem_controles(self) -> None:
        partida = partida_basica()
        partida.gols["Grifinória"] = 2
        partida.pomos = {"Grifinória": "Grifinória"}
        partida.estado = "encerrada"
        partida.taca_aplicada = True
        partida.eventos.extend(
            (
                EventoPartida(
                    tipo="gol",
                    casa="Grifinória",
                    jogador="Angelina",
                    valor=1,
                    descricao="Angelina marcou: 18 contra 12 de Draco.",
                ),
                EventoPartida(
                    tipo="pomo",
                    casa="Grifinória",
                    jogador="Harry",
                    valor=20,
                    descricao="Harry capturou o Pomo do lado de Grifinória.",
                ),
                EventoPartida(
                    tipo="falta",
                    casa="Sonserina",
                    jogador="Marcus",
                    descricao="Marcus cometeu Trombar; pênalti para Grifinória.",
                ),
                EventoPartida(
                    tipo="penalti",
                    casa="Grifinória",
                    jogador="Angelina",
                    valor=1,
                    descricao="Angelina converteu o pênalti de Trombar: 17 contra 11.",
                ),
                EventoPartida(
                    tipo="penalti",
                    casa="Sonserina",
                    jogador="Draco",
                    valor=0,
                    descricao="Oliver defendeu o pênalti de Guidonar: 16 contra 13.",
                ),
            )
        )

        embed = embed_resultado_partida(partida)
        conteudo = str(embed.to_dict())

        self.assertIn("Resultado Final", embed.title)
        self.assertIn("Jogadas que alteraram o placar", conteudo)
        self.assertIn("Gol (+10)", conteudo)
        self.assertIn("Pomo capturado (+150)", conteudo)
        self.assertIn("Faltas registradas", conteudo)
        self.assertIn("Angelina converteu", conteudo)
        self.assertIn("Oliver defendeu", conteudo)
        self.assertIn("Grifinória: +37", conteudo)
        self.assertNotIn("Ordem de iniciativa", conteudo)
        self.assertNotIn("Adversidade meteorológica", conteudo)

    def test_resultado_final_exibe_adversidade_meteorologica_no_inicio(self) -> None:
        partida = partida_basica()
        partida.estado = "encerrada"
        partida.eventos.append(
            EventoPartida(
                tipo="efeito",
                descricao=(
                    "Tempo Meteorológico (Difícil, CD 14) aplicado a ambas as equipes "
                    "por Efeito narrativo — Ventos cruzados durante o primeiro tempo."
                ),
            )
        )

        embed = embed_resultado_partida(partida)
        nomes = [campo.name for campo in embed.fields]
        conteudo = str(embed.to_dict())

        self.assertIn("🌦️ Adversidade meteorológica", nomes)
        self.assertLess(
            nomes.index("🌦️ Adversidade meteorológica"),
            nomes.index("📈 Jogadas que alteraram o placar"),
        )
        self.assertIn("Ventos cruzados durante o primeiro tempo", conteudo)

    def test_resultado_e_aplicado_uma_unica_vez_para_as_duas_casas(self) -> None:
        partida = partida_basica()
        adicionar_gol(partida, "Grifinória")
        adicionar_gol(partida, "Sonserina")
        adicionar_gol(partida, "Sonserina")
        partida.pomo = "Grifinória"
        partida.estado = "aguardando_confirmacao"
        estado = EstadoTaca()
        acontecimentos = aplicar_resultado_na_taca(partida, estado)
        self.assertEqual(len(acontecimentos), 2)
        self.assertEqual(estado.pontuacoes["Grifinória"], 36)
        self.assertEqual(estado.pontuacoes["Sonserina"], 2)
        with self.assertRaisesRegex(ValueError, "já foi aplicado"):
            aplicar_resultado_na_taca(partida, estado)

    def test_partida_persiste_jogadores_efeitos_e_eventos(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "partida.md"
            alvo = jogador("Alvo", "Sonserina", "Artilheiro")
            alvo.efeitos.append(EfeitoQuadribol("Vantagem", "Manobra", "Pontaria", 2, 1))
            partida = partida_basica([jogador("Batedor", "Grifinória", "Batedor"), alvo])
            partida.eventos.append(EventoPartida(tipo="teste", descricao="Persistido"))
            salvar_partida(partida, caminho)
            carregada = carregar_partida(caminho)
            self.assertEqual(carregada.jogadores[1].efeitos[0].bonus, 2)
            self.assertEqual(carregada.eventos[-1].descricao, "Persistido")


class TurnosBalacosEManobrasTests(unittest.TestCase):
    def test_rei_aplica_carisma_ao_aliado_e_consumo_na_proxima_acao(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "Rei.md"
            ficha = FichaPersonagem(
                nome="Lider",
                grupo="Personagem",
                casa="Grifinória",
                heranca="Puro-Sangue",
                nucleo="Teste",
            )
            ficha.atributos["Carisma"] = 16
            ficha.especializacoes.append("Rei")
            salvar_ficha(ficha, caminho, nova=True)
            lider = jogador("Lider", "Grifinória", "Artilheiro")
            lider.caminho_ficha = str(caminho)
            aliado = jogador("Aliado", "Grifinória", "Artilheiro")
            partida = partida_basica([lider, aliado])

            resultado = executar_rei(partida, "Lider", "Aliado")
            fontes: list[str] = []
            bonus = modificador_condicoes_acao(
                partida, aliado, "gol", gerador=FilaDados(), fontes=fontes
            )

            self.assertEqual(resultado.bonus, 3)
            self.assertEqual(bonus, 3)
            self.assertIn("Orientação de Rei", fontes[0])
            self.assertFalse(any(efeito.categoria == "Habilidade" for efeito in aliado.efeitos))

    def test_poeta_usa_mais_quatro_contra_cd_da_condicao_e_remove_no_sucesso(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "Poeta.md"
            ficha = FichaPersonagem(
                nome="Poeta",
                grupo="Personagem",
                casa="Lufa-Lufa",
                heranca="Puro-Sangue",
                nucleo="Teste",
            )
            ficha.atributos["Carisma"] = 14
            ficha.pericias["Persuasão"] = 2
            ficha.especializacoes.append("Poeta // Artista")
            salvar_ficha(ficha, caminho, nova=True)
            poeta = jogador("Poeta", "Lufa-Lufa", "Artilheiro")
            poeta.caminho_ficha = str(caminho)
            aliado = jogador("Aliado", "Lufa-Lufa", "Artilheiro")
            aliado.efeitos.append(
                EfeitoQuadribol(
                    nome="Sob Pressão",
                    origem="Efeito narrativo",
                    categoria="Estado emocional",
                    intensidade="Padrão",
                    cd_resistencia=12,
                    duracao_tipo="partida",
                )
            )
            partida = partida_basica([poeta, aliado])

            resultado = executar_poeta(
                partida,
                "Poeta",
                "Aliado",
                "Sob Pressão",
                gerador=FilaDados(5),
            )

            self.assertEqual(resultado.total, 13)
            self.assertEqual(resultado.cd, 12)
            self.assertTrue(resultado.sucesso)
            self.assertFalse(aliado.efeitos)

    def test_embed_de_recuperacao_destaca_resultado_cd_e_consequencia(self) -> None:
        falha = embed_resultado_recuperacao(
            "Sebastian Pendragon",
            "Atordoado por Rebate Duplo",
            ("Resultado externo +14",),
            14,
            18,
            False,
        )
        sucesso = embed_resultado_recuperacao(
            "Sebastian Pendragon",
            "Atordoado por Rebate Duplo",
            ("d20 (18)", "Fortitude da ficha +0"),
            18,
            18,
            True,
        )

        self.assertEqual(falha.title, "❌ Recuperação malsucedida")
        self.assertIn("Fortitude contra CD 18", falha.description)
        self.assertIn("**Total: 14**", falha.description)
        self.assertIn("turno foi encerrado automaticamente", falha.description)
        self.assertEqual(sucesso.title, "✅ Recuperação bem-sucedida")
        self.assertIn("pode agir normalmente neste turno", sucesso.description)

    def test_preparar_acao_da_prioridade_no_inicio_da_proxima_rodada(self) -> None:
        jogadores = [
            jogador("Um", "Grifinória", "Artilheiro"),
            jogador("Dois", "Sonserina", "Batedor"),
            jogador("Tres", "Sonserina", "Apanhador"),
        ]
        partida = partida_basica(jogadores)

        preparar_acao(partida)
        self.assertEqual(partida.jogador_atual().nome, "Dois")
        self.assertEqual(partida.acoes_preparadas, ["Um"])

        avancar_turno(partida)
        self.assertEqual(partida.jogador_atual().nome, "Tres")
        avancar_turno(partida)
        self.assertEqual(partida.jogador_atual().nome, "Um")
        self.assertTrue(partida.executando_acoes_preparadas)
        self.assertEqual(partida.rodada_tempo, 2)

        avancar_turno(partida)
        self.assertEqual(partida.jogador_atual().nome, "Um")
        self.assertFalse(partida.executando_acoes_preparadas)
        self.assertEqual(partida.acoes_preparadas, [])
        self.assertEqual(partida.rodada_tempo, 2)

    def test_multiplas_acoes_preparadas_seguem_a_ordem_de_iniciativa(self) -> None:
        baixa = jogador("Baixa", "Grifinória", "Artilheiro")
        alta = jogador("Alta", "Sonserina", "Batedor")
        media = jogador("Media", "Sonserina", "Apanhador")
        baixa.iniciativa_total = 8
        alta.iniciativa_total = 20
        media.iniciativa_total = 14
        partida = partida_basica([baixa, alta, media])

        preparar_acao(partida)
        preparar_acao(partida)
        preparar_acao(partida)

        self.assertEqual(partida.rodada_tempo, 2)
        self.assertTrue(partida.executando_acoes_preparadas)
        self.assertEqual(partida.acoes_preparadas, ["Alta", "Media", "Baixa"])
        self.assertEqual(partida.jogador_atual().nome, "Alta")

        avancar_turno(partida)
        self.assertEqual(partida.jogador_atual().nome, "Media")
        avancar_turno(partida)
        self.assertEqual(partida.jogador_atual().nome, "Baixa")
        avancar_turno(partida)
        self.assertFalse(partida.executando_acoes_preparadas)
        self.assertEqual(partida.jogador_atual().nome, "Baixa")

    def test_embed_separa_preparados_e_preserva_indices_da_iniciativa(self) -> None:
        jogadores = [
            jogador("Primeiro", "Grifinória", "Batedor"),
            jogador("Vicktory", "Grifinória", "Apanhador"),
            jogador("Lauriet", "Sonserina", "Apanhador"),
            jogador("Quarto", "Sonserina", "Artilheiro"),
        ]
        for iniciativa, participante in zip((23, 19, 18, 14), jogadores):
            participante.iniciativa_total = iniciativa
        partida = partida_basica(jogadores)
        partida.rodada_tempo = 2
        partida.acoes_preparadas = ["Vicktory", "Lauriet"]
        partida.executando_acoes_preparadas = True

        embed = embed_partida(partida)
        campos = {campo.name: campo.value for campo in embed.fields}

        titulo_preparadas = (
            "⏳ Ações preparadas em execução: prioridade antes da iniciativa normal desta rodada."
        )
        preparados = campos[titulo_preparadas]
        iniciativa = campos["Ordem de iniciativa"]
        self.assertNotIn("prioridade antes da iniciativa normal", preparados)
        self.assertIn("`02`", preparados)
        self.assertIn("Vicktory", preparados)
        self.assertIn("`03`", preparados)
        self.assertIn("Lauriet", preparados)
        self.assertNotIn("Ação preparada", campos["Turno atual"])
        self.assertIn("`01`", iniciativa)
        self.assertIn("Primeiro", iniciativa)
        self.assertIn("`04`", iniciativa)
        self.assertIn("Quarto", iniciativa)
        self.assertNotIn("Vicktory", iniciativa)
        self.assertNotIn("Lauriet", iniciativa)

    def test_acao_preparada_nao_pode_ser_adiada_novamente(self) -> None:
        partida = partida_basica([jogador("Um", "Grifinória", "Artilheiro")])
        preparar_acao(partida)
        with self.assertRaisesRegex(ValueError, "não pode ser adiada novamente"):
            preparar_acao(partida)

    def test_goleiros_ficam_fora_da_iniciativa_e_da_vez_atual(self) -> None:
        artilheiro = jogador("Angelina", "Grifinória", "Artilheiro")
        goleiro = jogador("Oliver", "Grifinória", "Goleiro")
        apanhador = jogador("Harry", "Sonserina", "Apanhador")
        partida = partida_basica([artilheiro, goleiro, apanhador])
        self.assertEqual(
            [item.nome for item in partida.jogadores_em_iniciativa()],
            ["Angelina", "Harry"],
        )
        self.assertEqual(partida.jogador_atual().nome, "Angelina")
        avancar_turno(partida)
        self.assertEqual(partida.jogador_atual().nome, "Harry")
        avancar_turno(partida)
        self.assertEqual(partida.jogador_atual().nome, "Angelina")
        self.assertEqual(partida.rodada_tempo, 2)

    def test_passar_rodada_encerra_a_atual_mesmo_partindo_do_meio(self) -> None:
        jogadores = [
            jogador("Um", "Grifinória", "Artilheiro"),
            jogador("Dois", "Sonserina", "Batedor"),
            jogador("Tres", "Sonserina", "Apanhador"),
        ]
        partida = partida_basica(jogadores)
        avancar_turno(partida)
        self.assertEqual(partida.jogador_atual().nome, "Dois")
        avancar_rodada(partida)
        self.assertEqual(partida.jogador_atual().nome, "Um")
        self.assertEqual(partida.rodada_tempo, 2)

    def test_passar_rodada_nao_e_bloqueado_por_jogador_atordoado(self) -> None:
        atordoado = jogador("Atordoado", "Grifinória", "Artilheiro")
        atordoado.efeitos.append(
            EfeitoQuadribol(
                nome="Atordoado por Balaço",
                origem="Batedor",
                turnos_restantes=2,
                cd_recuperacao=12,
            )
        )
        outro = jogador("Outro", "Sonserina", "Artilheiro")
        partida = partida_basica([atordoado, outro])

        avancar_rodada(partida)

        self.assertEqual(partida.rodada_tempo, 2)
        self.assertEqual(partida.jogador_atual().nome, "Atordoado")

    def test_embed_identifica_time_e_esconde_vassoura_da_ordem(self) -> None:
        artilheiro = jogador("Angelina", "Grifinória", "Artilheiro")
        goleiro = jogador("Oliver", "Sonserina", "Goleiro")
        partida = partida_basica([artilheiro, goleiro])
        conteudo = str(embed_partida(partida).to_dict())
        self.assertIn("Artilheiro da Grifinória", conteudo)
        self.assertIn("Goleiros em espera", conteudo)
        self.assertNotIn(artilheiro.vassoura, conteudo)

    def test_embed_separa_efeitos_da_iniciativa_e_mostra_modificador(self) -> None:
        afetado = jogador("Angelina", "Grifinória", "Artilheiro")
        outro = jogador("Draco", "Sonserina", "Artilheiro")
        partida = partida_basica([afetado, outro])
        adicionar_condicao_catalogada(partida, "Confiante", [afetado.nome])

        embed = embed_partida(partida)
        campos = {campo.name: campo.value for campo in embed.fields}
        efeitos = campos["⏳ Efeitos e condições ativos"]

        self.assertIn("Angelina", efeitos)
        self.assertIn("Confiante", efeitos)
        self.assertIn("`+1d4`", efeitos)
        self.assertNotIn("Draco", efeitos)
        self.assertNotIn("Confiante", campos["Turno atual"])
        self.assertNotIn("Confiante", campos["Ordem de iniciativa"])

    def test_tempo_meteorologico_agrupa_as_equipes_sem_repetir_jogadores(self) -> None:
        a = jogador("A", "Grifinória", "Artilheiro")
        b = jogador("B", "Sonserina", "Artilheiro")
        partida = partida_basica([a, b])
        adicionar_condicao_catalogada(
            partida,
            "Tempo Meteorológico",
            [a.nome, b.nome],
            intensidade="Difícil",
            origem="Efeito narrativo — Ventos cruzados",
        )

        embed = embed_partida(partida)
        efeitos = next(
            campo.value
            for campo in embed.fields
            if campo.name == "⏳ Efeitos e condições ativos"
        )

        self.assertIn("Tempo Meteorológico — Ambas as equipes", efeitos)
        self.assertIn("Ventos cruzados", efeitos)
        self.assertIn("Fortitude CD 14", efeitos)
        self.assertIn("`-(1d4+1)`", efeitos)
        self.assertNotIn("**A**", efeitos)
        self.assertNotIn("**B**", efeitos)

    def test_meta_do_pomo_varia_com_toda_a_tabela_de_velocidade(self) -> None:
        apanhador = jogador("Harry", "Grifinória", "Apanhador")
        for velocidade, meta in PROGRESSO_POMO_POR_VELOCIDADE.items():
            with self.subTest(velocidade=velocidade):
                apanhador.velocidade_vassoura = velocidade
                self.assertEqual(progresso_necessario_pomo(apanhador), meta)

    def test_vassoura_de_dez_metros_captura_ao_chegar_em_cinquenta_e_cinco(self) -> None:
        apanhador = jogador(
            "Harry",
            "Grifinória",
            "Apanhador",
            velocidade=10,
        )
        partida = partida_basica([apanhador])
        partida.progresso_pomos["Grifinória"]["Grifinória"] = 43
        resultado = perseguir_pomo(partida, "Harry", gerador=FilaDados(10))
        self.assertEqual(resultado.necessario, 55)
        self.assertEqual(resultado.progresso_atual, 55)
        self.assertTrue(resultado.capturou)

    def test_disparada_reduz_a_meta_so_naquele_turno_e_uma_vez_por_pomo(self) -> None:
        apanhador = jogador(
            "Harry",
            "Grifinória",
            "Apanhador",
            velocidade=8,
        )
        apanhador.vassoura = "Tinderblast Exclusiva"
        partida = partida_basica([apanhador])
        resultado = perseguir_pomo(
            partida,
            "Harry",
            usar_disparada=True,
            gerador=FilaDados(1, 4),
        )
        self.assertEqual(resultado.velocidade_considerada, 17)
        self.assertEqual(resultado.necessario, 30)
        self.assertFalse(resultado.capturou)
        self.assertEqual(resultado.bonus_vassoura_situacional, 4)
        apanhador.perseguiu_pomo_no_turno = False
        with self.assertRaisesRegex(ValueError, "já usou a Disparada"):
            perseguir_pomo(
                partida,
                "Harry",
                usar_disparada=True,
                gerador=FilaDados(20),
            )
        resultado_normal = perseguir_pomo(
            partida,
            "Harry",
            gerador=FilaDados(1, 4),
        )
        self.assertEqual(resultado_normal.necessario, 65)
        self.assertEqual(resultado_normal.bonus_vassoura_situacional, 4)

    def test_painel_nao_apresenta_meta_temporaria_da_disparada_como_permanente(self) -> None:
        apanhador = jogador("Harry", "Grifinória", "Apanhador", velocidade=8)
        apanhador.vassoura = "Tinderblast Exclusiva"
        adversario = jogador("Draco", "Sonserina", "Apanhador", velocidade=10)
        partida = partida_basica([apanhador, adversario])

        conteudo = str(embed_partida(partida).to_dict())

        self.assertIn("Grifinória: 0/65", conteudo)
        self.assertIn("Disparada 17m/s (pode ser usada no próprio turno)", conteudo)
        self.assertNotIn("17m/s → 30", conteudo)

    def test_segundo_pomo_so_aparece_no_segundo_tempo_e_no_lado_oposto(self) -> None:
        apanhador = jogador("Harry", "Grifinória", "Apanhador")
        partida = partida_basica([apanhador])
        partida.rodadas_surgimento_pomo = {"1": 1, "2": 3}
        self.assertEqual(partida.pomos_ativos(), ("Grifinória",))
        partida.progresso_pomos["Grifinória"]["Grifinória"] = 63
        primeiro = perseguir_pomo(partida, "Harry", gerador=FilaDados(10))
        self.assertTrue(primeiro.capturou)
        self.assertEqual(partida.pomos_ativos(), ())
        preparar_encerramento(partida)
        self.assertEqual(partida.estado, "intervalo")
        preparar_encerramento(partida)
        self.assertEqual((partida.tempo, partida.estado), (2, "ativa"))
        self.assertEqual(partida.pomos_ativos(), ())
        avancar_turno(partida)
        avancar_turno(partida)
        self.assertEqual(partida.pomos_ativos(), ("Sonserina",))
        self.assertEqual(partida.progresso_pomos["Sonserina"]["Grifinória"], 0)
        self.assertEqual(partida.capturas_pomo("Grifinória"), 1)
        self.assertEqual(partida.placar("Grifinória"), 150)

    def test_encerramento_manual_funciona_mesmo_sem_os_dois_pomos(self) -> None:
        partida = partida_basica()
        adicionar_gol(partida, "Grifinória")
        preparar_encerramento(partida)
        self.assertEqual(partida.estado, "intervalo")
        preparar_encerramento(partida)
        self.assertEqual(partida.tempo, 2)
        preparar_encerramento(partida)
        self.assertEqual(partida.estado, "aguardando_confirmacao")
        estado = EstadoTaca()
        aplicar_resultado_na_taca(partida, estado)
        self.assertEqual(estado.pontuacoes["Grifinória"], 26)
        self.assertEqual(partida.estado, "encerrada")

    def test_cada_um_dos_dois_pomos_vale_cento_e_cinquenta_e_dez_na_taca(self) -> None:
        partida = partida_basica()
        partida.pomos = {
            "Grifinória": "Grifinória",
            "Sonserina": "Sonserina",
        }
        self.assertEqual(partida.placar("Grifinória"), 150)
        self.assertEqual(partida.placar("Sonserina"), 150)
        partida.tempo = 2
        preparar_encerramento(partida)
        estado = EstadoTaca()
        aplicar_resultado_na_taca(partida, estado)
        self.assertEqual(estado.pontuacoes["Grifinória"], 10)
        self.assertEqual(estado.pontuacoes["Sonserina"], 10)

    def test_pomo_surge_em_rodada_secreta_entre_tres_e_sete(self) -> None:
        apanhador = jogador("Harry", "Grifinória", "Apanhador")
        partida = partida_basica([apanhador])
        partida.rodadas_surgimento_pomo = {"1": 3, "2": 6}
        self.assertEqual(partida.pomos_ativos(), ())
        avancar_turno(partida)
        self.assertEqual(partida.rodada_tempo, 2)
        self.assertEqual(partida.pomos_ativos(), ())
        avancar_turno(partida)
        self.assertEqual(partida.rodada_tempo, 3)
        self.assertEqual(partida.pomos_ativos(), ("Grifinória",))
        anuncios = [item for item in partida.eventos if item.tipo == "surgimento_pomo"]
        self.assertEqual(len(anuncios), 1)
        self.assertIn("O POMO SURGIU!!!", anuncios[0].descricao)

    def test_apanhador_acumula_ate_setenta_e_cinco_e_captura_automaticamente(self) -> None:
        apanhador = jogador("Harry", "Grifinória", "Apanhador")
        adversario = jogador("Draco", "Sonserina", "Apanhador")
        partida = partida_basica([apanhador, adversario])
        partida.progresso_pomos["Grifinória"]["Grifinória"] = 63
        resultado = perseguir_pomo(partida, "Harry", gerador=FilaDados(10))
        self.assertEqual(resultado.progresso_atual, 75)
        self.assertTrue(resultado.capturou)
        self.assertEqual(partida.pomos["Grifinória"], "Grifinória")
        self.assertEqual(partida.pomos_ativos(), ())
        self.assertEqual(partida.estado, "ativa")

    def test_perseguicao_so_pode_ser_feita_uma_vez_no_turno(self) -> None:
        apanhador = jogador("Harry", "Grifinória", "Apanhador")
        partida = partida_basica([apanhador])
        perseguir_pomo(partida, "Harry", gerador=FilaDados(5))
        with self.assertRaisesRegex(ValueError, "já sustentou"):
            perseguir_pomo(partida, "Harry", gerador=FilaDados(5))

    def test_nao_sustentar_perseguicao_no_turno_apaga_o_acumulo(self) -> None:
        apanhador = jogador("Harry", "Grifinória", "Apanhador")
        adversario = jogador("Draco", "Sonserina", "Artilheiro")
        partida = partida_basica([apanhador, adversario])
        partida.progresso_pomos["Grifinória"]["Grifinória"] = 30
        apanhador.pomo_perseguido = "Grifinória"
        avancar_turno(partida)
        self.assertEqual(partida.progresso_pomos["Grifinória"]["Grifinória"], 0)

    def test_balaco_falho_na_fortitude_atordoa_e_apaga_progresso_do_pomo(self) -> None:
        atacante = jogador("Fred", "Grifinória", "Batedor", forca=3)
        alvo = jogador("Draco", "Sonserina", "Apanhador", vida=2)
        partida = partida_basica([atacante, alvo])
        partida.progresso_pomos["Grifinória"]["Sonserina"] = 40
        alvo.pomo_perseguido = "Grifinória"
        resultado = resolver_balaco(
            partida,
            "Fred",
            "Draco",
            gerador=FilaDados(20, 1, 1),
        )
        self.assertTrue(resultado.atingiu)
        self.assertFalse(resultado.resistiu)
        self.assertEqual(resultado.cd_fortitude, 15)
        self.assertEqual(alvo.efeitos[0].turnos_restantes, 2)
        self.assertEqual(alvo.vida_vassoura, 1)
        self.assertEqual(partida.progresso_pomos["Grifinória"]["Sonserina"], 0)

    def test_balaco_faz_artilheiro_perder_a_goles_para_o_time_adversario(self) -> None:
        atacante = jogador("Fred", "Grifinória", "Batedor", forca=3)
        novo_portador = jogador("Angelina", "Grifinória", "Artilheiro")
        alvo = jogador("Draco", "Sonserina", "Artilheiro", fortitude=20)
        aliado_alvo = jogador("Pansy", "Sonserina", "Artilheiro")
        partida = partida_basica([atacante, novo_portador, alvo, aliado_alvo])
        partida.posse_goles = alvo.nome

        resultado = resolver_balaco(
            partida,
            atacante.nome,
            alvo.nome,
            gerador=FilaDados(20, 1, 20),
        )

        self.assertTrue(resultado.atingiu)
        self.assertTrue(resultado.resistiu)
        self.assertEqual(resultado.posse_perdida_por, alvo.nome)
        self.assertEqual(resultado.casa_nova_posse, "Grifinória")
        self.assertEqual(partida.posse_goles, "")
        self.assertEqual(partida.reposicao_goles_casa, "Grifinória")
        self.assertIn("perdeu a posse da Goles", partida.eventos[-1].descricao)
        self.assertIn("Escolha um Artilheiro", embed_resultado_balaco(resultado, partida).description)

        with self.assertRaisesRegex(ValueError, "time adversário"):
            atribuir_posse_goles(partida, aliado_alvo.nome)

        atribuir_posse_goles(partida, novo_portador.nome)
        self.assertEqual(partida.posse_goles, novo_portador.nome)
        self.assertEqual(partida.reposicao_goles_casa, "")

    def test_vassoura_quebrada_pertence_ao_jogador_e_fica_inutil(self) -> None:
        atacante = jogador("Fred", "Grifinória", "Batedor", forca=3)
        alvo = jogador("Draco", "Sonserina", "Apanhador", vida=1)
        partida = partida_basica([atacante, alvo])

        resultado = resolver_balaco(
            partida,
            "Fred",
            "Draco",
            gerador=FilaDados(20, 1, 20),
        )

        self.assertEqual(alvo.vida_vassoura, 0)
        self.assertTrue(alvo.vassoura_quebrada)
        self.assertFalse(alvo.ativo)
        self.assertIn("Quebrada", partida.eventos[-1].descricao)
        self.assertIn("Quebrada", embed_resultado_balaco(resultado, partida).description)

        outro_jogador = jogador("Pansy", "Sonserina", "Artilheiro", vida=1)
        self.assertEqual(outro_jogador.vida_vassoura, 1)
        self.assertFalse(outro_jogador.vassoura_quebrada)

    def test_rebate_duplo_usa_cd_quatorze_mais_maior_forca_e_um_de_dano(self) -> None:
        primeiro = jogador("Fred", "Grifinória", "Batedor", forca=3)
        segundo = jogador("Jorge", "Grifinória", "Batedor", forca=1)
        alvo = jogador("Draco", "Sonserina", "Apanhador", vida=3)
        partida = partida_basica([primeiro, segundo, alvo])
        resultado = resolver_balaco(
            partida,
            "Fred",
            "Draco",
            rebate_duplo=True,
            segundo_batedor="Jorge",
            gerador=FilaDados(20, 1, 1),
        )
        self.assertEqual(resultado.cd_fortitude, 17)
        self.assertEqual(alvo.vida_vassoura, 2)

    def test_recuperacao_bem_sucedida_remove_atordoamento(self) -> None:
        atacante = jogador("Fred", "Grifinória", "Batedor", forca=0)
        alvo = jogador("Draco", "Sonserina", "Apanhador", fortitude=0)
        partida = partida_basica([atacante, alvo])
        resolver_balaco(partida, "Fred", "Draco", gerador=FilaDados(20, 1, 1))
        partida.indice_turno = 1
        alvo.fortitude = 20
        fontes: list[str] = []
        _, _, sucesso = testar_recuperacao(
            partida,
            "Draco",
            gerador=FilaDados(1),
            fontes=fontes,
        )
        self.assertTrue(sucesso)
        self.assertFalse(alvo.efeitos)
        self.assertEqual(fontes, ["d20 (1)", "Fortitude da ficha +20"])

    def test_atordoado_so_pode_realizar_teste_de_recuperacao(self) -> None:
        alvo = jogador("Draco", "Sonserina", "Artilheiro")
        outro = jogador("Fred", "Grifinória", "Batedor")
        partida = partida_basica([alvo, outro])
        alvo.efeitos.append(
            EfeitoQuadribol(
                nome="Atordoado por Balaço",
                origem="Fred",
                turnos_restantes=2,
                cd_recuperacao=12,
            )
        )

        with self.assertRaisesRegex(ValueError, "só pode realizar o Teste de Recuperação"):
            preparar_acao(partida)
        with self.assertRaisesRegex(ValueError, "só pode realizar o Teste de Recuperação"):
            avancar_turno(partida)

        _, _, sucesso = testar_recuperacao(
            partida,
            alvo.nome,
            gerador=FilaDados(1),
        )
        self.assertFalse(sucesso)
        avancar_turno(partida, permitir_atordoado=True)
        self.assertEqual(partida.jogador_atual().nome, outro.nome)
        self.assertEqual(alvo.efeitos[0].turnos_restantes, 1)

    def test_defesa_empatada_e_do_jogador_e_evitar_o_balaco(self) -> None:
        atacante = jogador("Fred", "Grifinória", "Batedor")
        alvo = jogador("Draco", "Sonserina", "Apanhador", reflexo=4)
        partida = partida_basica([atacante, alvo])
        resultado = resolver_balaco(
            partida,
            "Fred",
            "Draco",
            gerador=FilaDados(10, 10),
        )
        self.assertFalse(resultado.atingiu)
        self.assertEqual(alvo.vida_vassoura, 3)

    def test_bonus_condicional_entra_no_ataque_direto_e_na_interceptacao(self) -> None:
        atacante = jogador(
            "Fred",
            "Grifinória",
            "Batedor",
            bonus_pontaria_vassoura=1,
            uso_bonus_pontaria="Ataque direto",
        )
        alvo = jogador("Draco", "Sonserina", "Apanhador")
        protetor = jogador(
            "Crabbe",
            "Sonserina",
            "Batedor",
            bonus_pontaria_vassoura=2,
            uso_bonus_pontaria="Interceptacao",
        )
        partida = partida_basica([atacante, alvo, protetor])
        resultado = resolver_balaco(
            partida,
            "Fred",
            "Draco",
            defesa="Batedor",
            defensor="Crabbe",
            gerador=FilaDados(10, 9),
        )
        self.assertEqual(resultado.bonus_vassoura_ataque, 1)
        self.assertEqual(resultado.bonus_vassoura_defesa, 2)
        self.assertFalse(resultado.atingiu)

    def test_thunderbolt_redireciona_balaco_ao_superar_ataque_por_cinco(self) -> None:
        atacante = jogador("Fred", "Grifinória", "Batedor")
        novo_alvo = jogador("Jorge", "Grifinória", "Artilheiro", fortitude=20)
        protegido = jogador("Draco", "Sonserina", "Apanhador")
        protetor = jogador(
            "Crabbe",
            "Sonserina",
            "Batedor",
            dado_bonus_pontaria_vassoura="1d4",
            uso_bonus_pontaria="Redirecionamento",
        )
        partida = partida_basica([atacante, novo_alvo, protegido, protetor])
        resultado = resolver_balaco(
            partida,
            "Fred",
            "Draco",
            defesa="Batedor",
            defensor="Crabbe",
            redirecionar=True,
            alvo_redirecionado="Jorge",
            gerador=FilaDados(1, 4, 10, 1, 20),
        )
        self.assertTrue(resultado.redirecionou)
        self.assertTrue(resultado.atingiu_redirecionado)
        self.assertEqual(resultado.bonus_vassoura_defesa, 4)
        self.assertEqual(resultado.dado_bonus_vassoura_defesa, 4)
        self.assertEqual(protegido.vida_vassoura, 3)
        self.assertEqual(novo_alvo.vida_vassoura, 2)

    def test_fortitude_bem_sucedida_preserva_progresso_do_pomo(self) -> None:
        atacante = jogador("Fred", "Grifinória", "Batedor", forca=0)
        alvo = jogador("Draco", "Sonserina", "Apanhador", fortitude=20)
        partida = partida_basica([atacante, alvo])
        partida.progresso_pomos["Grifinória"]["Sonserina"] = 32
        alvo.pomo_perseguido = "Grifinória"
        resultado = resolver_balaco(
            partida,
            "Fred",
            "Draco",
            gerador=FilaDados(20, 1, 1),
        )
        self.assertTrue(resultado.resistiu)
        self.assertEqual(partida.progresso_pomos["Grifinória"]["Sonserina"], 32)
        self.assertFalse(alvo.efeitos)

    def test_condicao_expira_depois_dos_turnos_do_proprio_jogador(self) -> None:
        primeiro = jogador("A", "Grifinória", "Artilheiro")
        segundo = jogador("B", "Sonserina", "Artilheiro")
        partida = partida_basica([primeiro, segundo])
        adicionar_efeito(partida, "A", "Bônus", "Manobra", "Pontaria", 2, 1)
        expirados = avancar_turno(partida)
        self.assertEqual([item.nome for item in expirados], ["Bônus"])
        self.assertFalse(primeiro.efeitos)
        self.assertEqual(partida.jogador_atual().nome, "B")
        self.assertIn("Bônus terminou para A", partida.eventos[-2].descricao)

    def test_condicao_negativa_exige_intensidade_e_guarda_cd(self) -> None:
        alvo = jogador("A", "Grifinória", "Artilheiro")
        partida = partida_basica([alvo])
        with self.assertRaisesRegex(ValueError, "intensidade"):
            adicionar_condicao_catalogada(partida, "Sob Pressão", ["A"])
        efeitos = adicionar_condicao_catalogada(
            partida,
            "Sob Pressão",
            ["A"],
            intensidade="Muito difícil",
        )
        self.assertEqual(efeitos[0].cd_resistencia, 16)
        self.assertEqual(efeitos[0].dado_modificador, "-1d4")
        self.assertEqual(efeitos[0].duracao_tipo, "partida")

    def test_condicao_guarda_a_origem_escolhida(self) -> None:
        alvo = jogador("A", "Grifinória", "Artilheiro")
        partida = partida_basica([alvo])
        efeito = adicionar_condicao_catalogada(
            partida,
            "Abalado",
            ["A"],
            intensidade="Leve",
            origem="Impacto ou acontecimento",
        )[0]
        self.assertEqual(efeito.origem, "Impacto ou acontecimento")

    def test_efeitos_positivos_nao_aceitam_intensidade(self) -> None:
        alvo = jogador("A", "Grifinória", "Artilheiro")
        partida = partida_basica([alvo])
        with self.assertRaisesRegex(ValueError, "não possuem intensidade"):
            adicionar_condicao_catalogada(
                partida,
                "Confiante",
                ["A"],
                intensidade="Leve",
            )
        efeito = adicionar_condicao_catalogada(partida, "Confiante", ["A"])[0]
        self.assertEqual(efeito.intensidade, "")
        self.assertEqual(efeito.cd_resistencia, 0)

    def test_efeito_da_proxima_rodada_encerra_automaticamente(self) -> None:
        primeiro = jogador("A", "Grifinória", "Artilheiro")
        segundo = jogador("B", "Sonserina", "Artilheiro")
        partida = partida_basica([primeiro, segundo])
        efeito = adicionar_condicao_catalogada(partida, "Confiante", ["A"])[0]
        self.assertEqual(efeito.rodada_final, 2)
        avancar_rodada(partida)
        self.assertIn(efeito, primeiro.efeitos)
        avancar_rodada(partida)
        self.assertNotIn(efeito, primeiro.efeitos)
        self.assertTrue(
            any("terminou automaticamente" in evento.descricao for evento in partida.eventos)
        )

    def test_rivalidade_liga_exatamente_adversarios(self) -> None:
        a = jogador("A", "Grifinória", "Artilheiro")
        b = jogador("B", "Sonserina", "Goleiro")
        partida = partida_basica([a, b])
        efeitos = adicionar_condicao_catalogada(
            partida,
            "Rivalidade",
            ["A", "B"],
            intensidade="Padrão",
        )
        self.assertEqual([efeito.rival for efeito in efeitos], ["B", "A"])
        self.assertEqual([efeito.cd_resistencia for efeito in efeitos], [12, 12])

    def test_catalogo_separa_intensidade_dos_efeitos_positivos(self) -> None:
        positivos = {
            item.nome
            for item in CONDICOES_QUADRIBOL
            if item.categoria == "Estado emocional positivo"
        }
        self.assertEqual(positivos, {"Confiante", "Motivado", "Em Sintonia", "Determinado"})
        self.assertTrue(
            all(not item.exige_intensidade for item in CONDICOES_QUADRIBOL if item.nome in positivos)
        )

    def test_sob_pressao_testa_vontade_e_aplica_dado_na_acao(self) -> None:
        alvo = jogador("A", "Grifinória", "Artilheiro")
        partida = partida_basica([alvo])
        adicionar_condicao_catalogada(
            partida,
            "Sob Pressão",
            ["A"],
            intensidade="Padrão",
        )
        modificador = modificador_condicoes_acao(
            partida,
            alvo,
            "gol",
            gerador=FilaDados(5, 3),
        )
        self.assertEqual(modificador, -3)
        self.assertIn("5 contra CD 12", partida.eventos[-1].descricao)

    def test_tempo_meteorologico_testa_fortitude_e_aplica_um_d4_mais_um(self) -> None:
        a = jogador("A", "Grifinória", "Artilheiro", fortitude=4)
        b = jogador("B", "Grifinória", "Batedor", fortitude=6)
        partida = partida_basica([a, b])
        efeitos = adicionar_condicao_catalogada(
            partida,
            "Tempo Meteorológico",
            ["A", "B"],
            intensidade="Padrão",
            origem="Efeito narrativo — Chuva intensa",
        )
        fontes: list[str] = []

        modificador = modificador_condicoes_acao(
            partida,
            a,
            "gol",
            gerador=FilaDados(5, 3),
            fontes=fontes,
        )

        self.assertEqual([efeito.cd_resistencia for efeito in efeitos], [12, 12])
        self.assertEqual(modificador, -4)
        self.assertIn("Fortitude", fontes[0])
        self.assertIn("1d4+1 = 4", fontes[0])

    def test_tempo_meteorologico_aceita_fortitude_externa_uma_unica_vez(self) -> None:
        a = jogador("A", "Grifinória", "Artilheiro", fortitude=0)
        b = jogador("B", "Grifinória", "Batedor")
        partida = partida_basica([a, b])
        adicionar_condicao_catalogada(
            partida,
            "Tempo Meteorológico",
            ["A", "B"],
            intensidade="Padrão",
        )
        preparar_fortitude_tempo_externa(partida, "A", 15)
        fontes: list[str] = []

        modificador = modificador_condicoes_acao(
            partida, a, "gol", gerador=FilaDados(), fontes=fontes
        )

        self.assertEqual(modificador, 0)
        self.assertIsNone(a.resultado_tempo_externo)
        self.assertIn("resultado externo de Fortitude 15", fontes[0])

    def test_resistencia_ao_tempo_prepara_e_aplica_penalidade_sem_rolar_novamente(self) -> None:
        alvo = jogador("A", "Grifinória", "Artilheiro", fortitude=4)
        aliado = jogador("B", "Grifinória", "Batedor")
        partida = partida_basica([alvo, aliado])
        adicionar_condicao_catalogada(
            partida,
            "Tempo Meteorológico",
            ["A", "B"],
            intensidade="Padrão",
        )

        resultado = resolver_resistencia_tempo(
            partida, "A", gerador=FilaDados(5, 3)
        )
        fontes: list[str] = []
        modificador = modificador_condicoes_acao(
            partida, alvo, "gol", gerador=FilaDados(), fontes=fontes
        )

        self.assertFalse(resultado.sucesso)
        self.assertEqual(resultado.penalidade, -4)
        self.assertEqual(modificador, -4)
        self.assertIn("d20 5 + Fortitude +4", fontes[0])
        self.assertIsNone(alvo.penalidade_tempo_preparada)

    def test_remover_tempo_meteorologico_encerra_para_toda_a_equipe(self) -> None:
        a = jogador("A", "Grifinória", "Artilheiro")
        b = jogador("B", "Grifinória", "Batedor")
        partida = partida_basica([a, b])
        adicionar_condicao_catalogada(
            partida,
            "Tempo Meteorológico",
            ["A", "B"],
            intensidade="Difícil",
            origem="Efeito narrativo — Ventania",
        )
        self.assertTrue(tem_tempo_meteorologico(a))
        self.assertTrue(tem_tempo_meteorologico(b))

        remover_efeito(partida, "A", 0)

        self.assertFalse(tem_tempo_meteorologico(a))
        self.assertFalse(tem_tempo_meteorologico(b))

    def test_determinado_ignora_condicao_emocional_negativa(self) -> None:
        alvo = jogador("A", "Grifinória", "Artilheiro")
        partida = partida_basica([alvo])
        adicionar_condicao_catalogada(
            partida,
            "Abalado",
            ["A"],
            intensidade="Excepcional",
        )
        adicionar_condicao_catalogada(partida, "Determinado", ["A"])
        avancar_rodada(partida)
        modificador = modificador_condicoes_acao(partida, alvo, "gol", gerador=FilaDados())
        self.assertEqual(modificador, 0)
        self.assertIn("estava Determinado", partida.eventos[-1].descricao)

    def test_confiante_entra_na_primeira_acao_da_proxima_rodada_e_e_consumido(self) -> None:
        alvo = jogador("A", "Grifinória", "Artilheiro")
        partida = partida_basica([alvo])
        efeito = adicionar_condicao_catalogada(partida, "Confiante", ["A"])[0]
        self.assertEqual(efeito.rodada_inicial, 2)
        self.assertEqual(
            modificador_condicoes_acao(partida, alvo, "gol", gerador=FilaDados()),
            0,
        )
        avancar_rodada(partida)
        fontes: list[str] = []
        self.assertEqual(
            modificador_condicoes_acao(
                partida,
                alvo,
                "gol",
                gerador=FilaDados(3),
                fontes=fontes,
            ),
            3,
        )
        self.assertEqual(fontes, ["Confiante 1d4 = 3"])
        self.assertFalse(any(item.nome == "Confiante" for item in alvo.efeitos))

    def test_motivado_concede_um_enquanto_o_gatilho_estiver_ativo(self) -> None:
        alvo = jogador("A", "Grifinória", "Artilheiro")
        partida = partida_basica([alvo])
        adicionar_condicao_catalogada(
            partida,
            "Motivado",
            ["A"],
            gatilho="proteger a equipe",
        )
        fontes: list[str] = []
        self.assertEqual(
            modificador_condicoes_acao(partida, alvo, "gol", fontes=fontes),
            1,
        )
        self.assertEqual(fontes, ["Motivado +1"])

    def test_em_sintonia_concede_um_dado_apenas_em_manobra_coletiva(self) -> None:
        a = jogador("A", "Grifinória", "Artilheiro")
        b = jogador("B", "Grifinória", "Artilheiro")
        partida = partida_basica([a, b])
        adicionar_condicao_catalogada(
            partida,
            "Em Sintonia",
            ["A", "B"],
            gerador=FilaDados(2),
        )
        self.assertEqual(
            modificador_condicoes_acao(partida, a, "manobra", coletiva=False),
            0,
        )
        fontes: list[str] = []
        self.assertEqual(
            modificador_condicoes_acao(
                partida,
                a,
                "manobra",
                coletiva=True,
                gerador=FilaDados(4),
                fontes=fontes,
            ),
            4,
        )
        self.assertEqual(fontes, ["Em Sintonia 1d4 = 4"])

    def test_rivalidade_pode_conceder_bonus_ou_penalidade(self) -> None:
        a = jogador("A", "Grifinória", "Artilheiro")
        b = jogador("B", "Sonserina", "Goleiro")
        partida = partida_basica([a, b])
        adicionar_condicao_catalogada(
            partida,
            "Rivalidade",
            ["A", "B"],
            intensidade="Padrão",
        )
        self.assertEqual(
            modificador_condicoes_acao(
                partida,
                a,
                "gol",
                oponente="B",
                gerador=FilaDados(15, 4),
            ),
            4,
        )

    def test_moderador_pode_encerrar_efeito_persistente_ou_por_gatilho(self) -> None:
        alvo = jogador("A", "Grifinória", "Artilheiro")
        partida = partida_basica([alvo])
        adicionar_condicao_catalogada(
            partida,
            "Motivado",
            ["A"],
            gatilho="O objetivo foi alcançado",
        )
        removido = remover_efeito(partida, "A", 0)
        self.assertEqual(removido.nome, "Motivado")
        self.assertFalse(alvo.efeitos)
        self.assertIn("foi encerrado", partida.eventos[-1].descricao)

    def test_catalogo_mantem_apenas_manobras_com_cd_definida(self) -> None:
        manobras = carregar_manobras()
        self.assertEqual(len(manobras), 15)
        muralha = next(item for item in manobras if item.nome == "Formação Muralha de Ogro")
        self.assertEqual(muralha.cd, 0)
        resgate = next(item for item in manobras if item.nome == "Resgate em Gangorra")
        self.assertEqual((resgate.cd, resgate.requisito_quadribol), (12, 1))

    def test_catalogo_registra_as_novas_regras_das_manobras(self) -> None:
        manobras = {item.nome: item for item in carregar_manobras()}
        self.assertIn("teste de Vôo CD 18", manobras["Finta de Wronski"].beneficio)
        self.assertIn("Fortitude CD 15", manobras["Finta de Wronski"].beneficio)
        self.assertIn("1d6+4", manobras["Finta de Wronski"].beneficio)
        self.assertIn("perde 3 PV", manobras["Finta de Wronski"].beneficio)
        self.assertIn("+1 em Pontaria", manobras["Formação de Ataque Hawkshead (Cabeça de Falcão)"].beneficio)
        self.assertIn("-2 em seus testes de Reflexo", manobras["Formação de Ataque Hawkshead (Cabeça de Falcão)"].beneficio)
        self.assertIn("aliado ou adversário", manobras["Zona de Fogo"].beneficio)
        self.assertIn("média dos bônus de Pontaria", manobras["Zona de Fogo"].beneficio)

    def test_requisito_da_manobra_nao_e_bonus_adicional(self) -> None:
        coordenador = jogador("Luna", "Corvinal", "Apanhador")
        coordenador.quadribol = 2
        partida = PartidaQuadribol(
            identificador="manobra",
            jogo="1º jogo",
            casa_1="Corvinal",
            casa_2="Lufa-Lufa",
            moderador_id=1,
            criado_em="agora",
            jogadores=[coordenador],
            gols={"Corvinal": 0, "Lufa-Lufa": 0},
        )
        finta = next(item for item in carregar_manobras() if item.nome == "Finta de Wronski")
        dado, total, _ = rolar_manobra(partida, finta, "Luna", gerador=random.Random(3))
        self.assertEqual(total, dado + 2)

    def test_coordenador_existe_apenas_em_manobra_coletiva(self) -> None:
        manobras = {item.nome: item for item in carregar_manobras()}
        self.assertFalse(manobra_exige_coordenador(manobras["Pancada de Fingbourg"]))
        self.assertFalse(manobra_exige_coordenador(manobras["Slip Groth Roll (Desvio da Preguiça)"]))
        self.assertFalse(manobra_exige_coordenador(manobras["Finta de Wronski"]))
        self.assertTrue(manobra_exige_coordenador(manobras["Relâmpago de Dragão"]))

    def test_manobra_individual_usa_jogador_em_destaque(self) -> None:
        atual = jogador("Atual", "Grifinória", "Artilheiro")
        colega = jogador("Colega", "Grifinória", "Artilheiro")
        atual.quadribol = colega.quadribol = 2
        partida = partida_basica([atual, colega])
        manobra = next(
            item for item in carregar_manobras() if item.nome == "Pancada de Fingbourg"
        )
        with self.assertRaisesRegex(ValueError, "jogador em destaque"):
            rolar_manobra(partida, manobra, "Colega", resultado_externo=20)

    def test_coordenador_coletivo_deve_ser_do_time_do_turno(self) -> None:
        atual = jogador("Atual", "Grifinória", "Artilheiro")
        adversario = jogador("Adversário", "Sonserina", "Artilheiro")
        atual.quadribol = adversario.quadribol = 2
        partida = partida_basica([atual, adversario])
        manobra = next(
            item for item in carregar_manobras() if item.nome == "Relâmpago de Dragão"
        )
        with self.assertRaisesRegex(ValueError, "time do turno atual"):
            rolar_manobra(partida, manobra, "Adversário", resultado_externo=20)

    def test_flecha_envenenada_aplica_e_consumo_bonus_no_arremesso(self) -> None:
        artilheiro = jogador("Leroy", "Grifinória", "Artilheiro")
        artilheiro.quadribol = 5
        goleiro = jogador("Carlos", "Sonserina", "Goleiro", reflexo=4)
        partida = partida_basica([artilheiro, goleiro])
        manobra = next(
            item for item in carregar_manobras() if item.nome == "Flecha Envenenada"
        )

        aplicar_beneficio_manobra(partida, manobra, "Leroy", finalizador="Leroy")
        resultado = resolver_tentativa_gol(
            partida,
            "Leroy",
            resultado_artilheiro_externo=10,
            resultado_goleiro_externo=11,
        )

        self.assertEqual(resultado.total_artilheiro, 12)
        self.assertEqual(resultado.bonus_manobra_artilheiro, 2)
        self.assertEqual(resultado.fontes_manobra_artilheiro, ("Flecha Envenenada (+2)",))
        self.assertFalse(any(efeito.nome == "Flecha Envenenada" for efeito in artilheiro.efeitos))

    def test_mergulho_usa_media_de_enganacao_e_pode_retirar_a_defesa(self) -> None:
        primeiro = jogador("A", "Grifinória", "Artilheiro")
        segundo = jogador("B", "Grifinória", "Artilheiro")
        terceiro = jogador("C", "Grifinória", "Artilheiro")
        goleiro = jogador("G", "Sonserina", "Goleiro", reflexo=20)
        partida = partida_basica([primeiro, segundo, terceiro, goleiro])
        manobra = next(
            item for item in carregar_manobras() if item.nome == "Mergulho do Falcão"
        )

        with patch("utils.quadribol._pericia_jogador", side_effect=[3, 6, 9]):
            aplicar_beneficio_manobra(
                partida,
                manobra,
                "A",
                finalizador="A",
            )
        resultado = resolver_tentativa_gol(
            partida,
            "A",
            resultado_artilheiro_externo=10,
            resultado_goleiro_externo=30,
            resultado_percepcao_externo=15,
        )

        self.assertEqual(resultado.cd_percepcao, 16)
        self.assertFalse(resultado.passou_percepcao)
        self.assertTrue(resultado.gol)
        self.assertEqual(resultado.total_artilheiro, 11)
        self.assertEqual(resultado.total_goleiro, 0)

    def test_muralha_de_ogro_e_automatica_e_dura_ate_ser_removida(self) -> None:
        artilheiros = [
            jogador(nome, "Grifinória", "Artilheiro")
            for nome in ("A", "B", "C")
        ]
        batedores = [
            jogador(nome, "Grifinória", "Batedor")
            for nome in ("D", "E")
        ]
        apanhador = jogador("F", "Grifinória", "Apanhador")
        atacante = jogador("X", "Sonserina", "Batedor")
        goleiro = jogador("G", "Sonserina", "Goleiro")
        partida = partida_basica([*artilheiros, *batedores, apanhador, atacante, goleiro])
        manobra = next(
            item for item in carregar_manobras() if item.nome == "Formação Muralha de Ogro"
        )
        fontes: list[str] = []

        self.assertEqual(
            rolar_manobra(partida, manobra, "A", fontes=fontes),
            (0, 0, True),
        )
        aplicar_beneficio_manobra(partida, manobra, "A")
        balaco = resolver_balaco(
            partida,
            "X",
            "F",
            resultado_ataque_externo=10,
            resultado_defesa_externo=20,
        )
        gol = resolver_tentativa_gol(
            partida,
            "A",
            resultado_artilheiro_externo=10,
            resultado_goleiro_externo=20,
        )

        self.assertEqual(fontes, ["Execução automática — sem teste"])
        self.assertEqual(balaco.total_ataque, 6)
        self.assertIn("Manobra: Formação Muralha de Ogro (-4)", balaco.fontes_ataque)
        self.assertEqual(gol.total_artilheiro, 8)
        indice = next(
            indice
            for indice, efeito in enumerate(batedores[0].efeitos)
            if efeito.nome == manobra.nome
        )
        remover_efeito(partida, batedores[0].nome, indice)
        self.assertFalse(
            any(
                efeito.nome == manobra.nome
                for item in partida.jogadores
                for efeito in item.efeitos
            )
        )

    def test_danca_das_serpentes_dura_uma_volta_completa_da_iniciativa(self) -> None:
        coordenador = jogador("A", "Grifinória", "Artilheiro")
        aliado = jogador("B", "Grifinória", "Batedor")
        adversario = jogador("C", "Sonserina", "Artilheiro")
        partida = partida_basica([coordenador, aliado, adversario])
        manobra = next(
            item for item in carregar_manobras() if item.nome == "A Dança das Serpentes"
        )

        aplicar_beneficio_manobra(
            partida,
            manobra,
            "A",
            finalizador="A",
        )

        aplicar_beneficio_manobra(
            partida,
            manobra,
            "A",
            finalizador="A",
        )

        self.assertTrue(all(any(efeito.nome == manobra.nome for efeito in item.efeitos) for item in (coordenador, aliado)))
        self.assertEqual(
            sum(efeito.nome == manobra.nome for efeito in coordenador.efeitos),
            2,
        )
        self.assertEqual(
            sum(efeito.nome == manobra.nome for efeito in aliado.efeitos),
            1,
        )
        avancar_turno(partida)
        avancar_turno(partida)
        self.assertTrue(any(efeito.nome == manobra.nome for efeito in coordenador.efeitos))
        avancar_turno(partida)
        self.assertEqual(partida.jogador_atual().nome, "A")
        self.assertFalse(any(efeito.nome == manobra.nome for item in partida.jogadores for efeito in item.efeitos))

    def test_zona_de_fogo_usa_media_e_penaliza_reflexo(self) -> None:
        primeiro = jogador("Fred", "Grifinória", "Batedor")
        segundo = jogador("Jorge", "Grifinória", "Batedor")
        segundo.bonus_teste_posicao = 2
        alvo = jogador("Draco", "Sonserina", "Artilheiro", reflexo=4, fortitude=20)
        partida = partida_basica([primeiro, segundo, alvo])
        manobra = next(item for item in carregar_manobras() if item.nome == "Zona de Fogo")
        aplicar_beneficio_manobra(partida, manobra, "Fred")

        resultado = resolver_balaco(
            partida,
            "Fred",
            "Draco",
            zona_fogo=True,
            gerador=FilaDados(10, 10, 20),
        )

        self.assertEqual(resultado.total_ataque, 13)
        self.assertEqual(resultado.total_defesa, 12)
        self.assertTrue(resultado.atingiu)
        self.assertIn("Média da Zona de Fogo: (+4 e +2) ÷ 2 = +3", resultado.fontes_ataque)
        self.assertIn("Zona de Fogo -2", resultado.fontes_defesa)

    def test_hawkshead_aplica_bonus_de_passe_e_penalidade_de_interceptacao(self) -> None:
        artilheiros = [
            jogador(nome, "Grifinória", "Artilheiro")
            for nome in ("A", "B", "C")
        ]
        interceptor = jogador("X", "Sonserina", "Artilheiro", reflexo=0)
        partida = partida_basica([*artilheiros, interceptor])
        partida.posse_goles = "A"
        manobra = next(
            item
            for item in carregar_manobras()
            if item.nome == "Formação de Ataque Hawkshead (Cabeça de Falcão)"
        )

        aplicar_beneficio_manobra(partida, manobra, "A")
        resultado = resolver_passe_goles(
            partida,
            "A",
            "B",
            "X",
            resultado_passe_externo=10,
            resultado_interceptacao_externo=12,
        )

        self.assertEqual(resultado.total_atacante, 11)
        self.assertEqual(resultado.total_defensor, 10)
        self.assertTrue(resultado.sucesso)
        self.assertIn("Manobra: Formação de Ataque Hawkshead", " ".join(resultado.fontes_atacante))
        self.assertIn("(-2)", " ".join(resultado.fontes_defensor))
        indice = next(
            indice
            for indice, efeito in enumerate(artilheiros[0].efeitos)
            if efeito.nome == manobra.nome
        )
        remover_efeito(partida, artilheiros[0].nome, indice)
        self.assertFalse(
            any(
                efeito.nome == manobra.nome
                for participante in partida.jogadores
                for efeito in participante.efeitos
            )
        )

    def test_resgate_em_gangorra_entrega_posse_ao_artilheiro_do_bote(self) -> None:
        artilheiros = [
            jogador(nome, "Grifinória", "Artilheiro")
            for nome in ("A", "B", "C")
        ]
        portador = jogador("X", "Sonserina", "Artilheiro")
        partida = partida_basica([*artilheiros, portador])
        partida.posse_goles = portador.nome
        manobra = next(
            item for item in carregar_manobras() if item.nome == "Resgate em Gangorra"
        )

        texto = aplicar_beneficio_manobra(
            partida,
            manobra,
            "A",
            finalizador="B",
        )

        self.assertEqual(partida.posse_goles, "B")
        self.assertIn("B realizou o bote", texto)

    def test_interceptacao_inimiga_encerra_zona_de_fogo(self) -> None:
        primeiro = jogador("Fred", "Grifinória", "Batedor")
        segundo = jogador("Jorge", "Grifinória", "Batedor")
        alvo = jogador("Draco", "Sonserina", "Artilheiro")
        interceptor = jogador("Crabbe", "Sonserina", "Batedor")
        partida = partida_basica([primeiro, segundo, alvo, interceptor])
        manobra = next(item for item in carregar_manobras() if item.nome == "Zona de Fogo")
        aplicar_beneficio_manobra(partida, manobra, "Fred")

        resultado = resolver_balaco(
            partida,
            "Fred",
            "Draco",
            zona_fogo=True,
            defesa="Batedor",
            defensor="Crabbe",
            gerador=FilaDados(1, 20),
        )

        self.assertFalse(resultado.atingiu)
        self.assertTrue(resultado.zona_fogo_encerrada)
        self.assertFalse(any(efeito.nome == "Zona de Fogo" for item in (primeiro, segundo) for efeito in item.efeitos))

    def test_rolagem_externa_nao_repete_ficha_ou_vassoura_mas_aplica_confiante(self) -> None:
        artilheiro = jogador("A", "Grifinória", "Artilheiro")
        artilheiro.vassoura = "Yajirushi Arqueiro"
        goleiro = jogador("G", "Sonserina", "Goleiro")
        partida = partida_basica([artilheiro, goleiro])
        adicionar_condicao_catalogada(partida, "Confiante", ["A"])
        avancar_rodada(partida)

        resultado = resolver_tentativa_gol(
            partida,
            "A",
            resultado_artilheiro_externo=10,
            resultado_goleiro_externo=12,
            gerador=FilaDados(3),
        )

        self.assertEqual(resultado.total_artilheiro, 13)
        self.assertEqual(
            resultado.fontes_artilheiro,
            ("Resultado externo 10", "Confiante 1d4 = 3"),
        )
        self.assertFalse(any("Yajirushi" in fonte for fonte in resultado.fontes_artilheiro))
        embed = embed_resultado_gol(resultado)
        self.assertIn("`Resultado externo 10`", embed.description)
        self.assertIn("`Confiante 1d4 = 3`", embed.description)
        self.assertNotIn("+ bônus", embed.description)

    def test_vassoura_concede_no_maximo_um_dado_situacional_na_manobra(self) -> None:
        coordenador = jogador("A", "Grifinória", "Artilheiro")
        coordenador.quadribol = 2
        coordenador.vassoura = "Cleansweep 11"
        partida = partida_basica([coordenador])
        manobra = next(
            item for item in carregar_manobras() if item.nome == "Mergulho do Falcão"
        )
        fontes: list[str] = []

        dado, total, sucesso = rolar_manobra(
            partida,
            manobra,
            "A",
            gerador=FilaDados(4, 10),
            fontes=fontes,
        )

        self.assertEqual((dado, total, sucesso), (10, 16, True))
        self.assertEqual(sum("1d4" in fonte for fonte in fontes), 1)
        self.assertTrue(any("Cleansweep 11" in fonte for fonte in fontes))

    def test_pancada_de_fingbourg_aplica_menos_seis_na_defesa_correspondente(self) -> None:
        artilheiro = jogador("Angelina", "Grifinória", "Artilheiro")
        artilheiro.quadribol = 2
        goleiro = jogador("Marcus", "Sonserina", "Goleiro", reflexo=6)
        partida = partida_basica([artilheiro, goleiro])
        manobra = next(
            item for item in carregar_manobras() if item.nome == "Pancada de Fingbourg"
        )

        aplicar_beneficio_manobra(partida, manobra, "Angelina")
        resultado = resolver_tentativa_gol(
            partida,
            "Angelina",
            resultado_artilheiro_externo=10,
            resultado_goleiro_externo=15,
        )

        self.assertEqual(resultado.total_goleiro, 9)
        self.assertEqual(resultado.bonus_manobra_goleiro, -6)
        self.assertEqual(resultado.fontes_manobra_goleiro, ("Pancada de Fingbourg (-6)",))

    def test_slip_groth_roll_aplica_dois_e_consumo_na_esquiva_de_balaco(self) -> None:
        atacante = jogador("Fred", "Grifinória", "Batedor")
        alvo = jogador("Luna", "Sonserina", "Apanhador", reflexo=3)
        alvo.quadribol = 2
        partida = partida_basica([alvo, atacante])
        manobra = next(
            item
            for item in carregar_manobras()
            if item.nome == "Slip Groth Roll (Desvio da Preguiça)"
        )

        aplicar_beneficio_manobra(partida, manobra, "Luna")
        resultado = resolver_balaco(
            partida,
            "Fred",
            "Luna",
            resultado_ataque_externo=10,
            resultado_defesa_externo=9,
        )

        self.assertEqual(resultado.total_defesa, 11)
        self.assertEqual(resultado.bonus_manobra_defesa, 2)
        self.assertFalse(any(efeito.nome == manobra.nome for efeito in alvo.efeitos))

    def test_parte_vampiro_aplica_passivo_de_um_dado_quatro_em_reflexo(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "Goleiro.md"
            ficha = FichaPersonagem(
                nome="Goleiro",
                grupo="Personagem",
                casa="Sonserina",
                heranca="Parte-Vampiro",
                nucleo="Teste",
            )
            salvar_ficha(ficha, caminho, nova=True)
            artilheiro = jogador("Artilheiro", "Grifinória", "Artilheiro")
            goleiro = jogador("Goleiro", "Sonserina", "Goleiro", reflexo=4)
            goleiro.caminho_ficha = str(caminho)
            partida = partida_basica([artilheiro, goleiro])

            resultado = resolver_tentativa_gol(
                partida,
                "Artilheiro",
                resultado_artilheiro_externo=10,
                resultado_goleiro_externo=10,
                gerador=FilaDados(4),
            )

            self.assertEqual(resultado.total_goleiro, 14)
            self.assertEqual(resultado.bonus_habilidade_goleiro, 4)
            self.assertEqual(resultado.fontes_habilidade_goleiro, ("Parte-Vampiro 1d4 = 4",))

    def test_brutamontes_ativo_aplica_quatro_na_fortitude_contra_balaco(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "Alvo.md"
            ficha = FichaPersonagem(
                nome="Alvo",
                grupo="Personagem",
                casa="Sonserina",
                heranca="Puro-Sangue",
                nucleo="Teste",
            )
            ficha.efeitos_habilidades_ativos.append(
                {"nome": "Brutamontes", "efeito": "+4 contra dano concussivo"}
            )
            salvar_ficha(ficha, caminho, nova=True)
            atacante = jogador("Fred", "Grifinória", "Batedor", forca=2)
            alvo = jogador("Alvo", "Sonserina", "Artilheiro", fortitude=0)
            alvo.caminho_ficha = str(caminho)
            partida = partida_basica([atacante, alvo])

            resultado = resolver_balaco(
                partida,
                "Fred",
                "Alvo",
                resultado_ataque_externo=15,
                resultado_defesa_externo=5,
                gerador=FilaDados(10),
            )

            self.assertEqual(resultado.total_fortitude, 14)
            self.assertTrue(resultado.resistiu)
            self.assertEqual(resultado.fontes_habilidade_fortitude, ("Brutamontes +4",))


class FaltasEPenaltiTests(unittest.TestCase):
    def test_catalogo_traz_as_dez_faltas_com_punicoes_prontas(self) -> None:
        faltas = carregar_faltas()
        self.assertEqual(len(faltas), 10)
        furar = next(item for item in faltas if item.nome == "Furar a Goles")
        self.assertEqual((furar.cartao, furar.consequencia), ("Vermelho", "Pênalti"))
        roubar = next(item for item in faltas if item.nome == "Roubar o Pomo")
        self.assertEqual((roubar.cartao, roubar.consequencia), ("Vermelho", "Derrota automática"))

    def test_segundo_amarelo_expulsa_e_reserva_entra_na_mesma_iniciativa(self) -> None:
        infrator = jogador("Draco", "Sonserina", "Batedor")
        infrator.cartoes_amarelos = 1
        reserva = jogador(
            "Goyle",
            "Sonserina",
            "Batedor",
            situacao="Reserva",
            em_campo=False,
        )
        cobrador = jogador("Harry", "Grifinória", "Artilheiro")
        partida = partida_basica([infrator, cobrador, reserva])
        falta = next(item for item in carregar_faltas() if item.nome == "Trombar")
        registro = registrar_falta(partida, "Draco", falta)
        self.assertEqual(registro.cartao_aplicado, "Vermelho")
        self.assertEqual(registro.reserva, "Goyle")
        self.assertTrue(reserva.em_campo)
        self.assertFalse(infrator.em_campo)
        self.assertEqual(reserva.iniciativa_total, 12)
        self.assertEqual(reservas_disponiveis(partida, "Draco"), [])

    def test_penalti_e_duelo_direto_e_empate_favorece_o_goleiro(self) -> None:
        infrator = jogador("Draco", "Sonserina", "Batedor")
        cobrador = jogador("Harry", "Grifinória", "Artilheiro")
        goleiro = jogador("Bole", "Sonserina", "Goleiro")
        partida = partida_basica([infrator, cobrador, goleiro])
        falta = next(item for item in carregar_faltas() if item.nome == "Trombar")
        registrar_falta(partida, "Draco", falta)
        resultado = resolver_penalti(partida, "Harry", gerador=FilaDados(10, 10))
        self.assertFalse(resultado.gol)
        self.assertEqual(partida.gols["Grifinória"], 0)
        self.assertEqual(partida.penalti_casa, "")

    def test_yajirushi_aplica_bonus_de_finalizacao_no_penalti(self) -> None:
        infrator = jogador("Draco", "Sonserina", "Batedor")
        cobrador = jogador(
            "Harry",
            "Grifinória",
            "Artilheiro",
            bonus_pontaria_vassoura=2,
            uso_bonus_pontaria="Finalizacao",
        )
        goleiro = jogador("Bole", "Sonserina", "Goleiro")
        partida = partida_basica([infrator, cobrador, goleiro])
        falta = next(item for item in carregar_faltas() if item.nome == "Trombar")
        registrar_falta(partida, "Draco", falta)
        resultado = resolver_penalti(partida, "Harry", gerador=FilaDados(10, 10))
        self.assertTrue(resultado.gol)
        self.assertEqual(resultado.bonus_vassoura_artilheiro, 2)

    def test_tentativa_de_gol_com_resultados_externos_e_empate_favorece_goleiro(self) -> None:
        cobrador = jogador("Harry", "Grifinória", "Artilheiro")
        goleiro = jogador("Bole", "Sonserina", "Goleiro")
        partida = partida_basica([cobrador, goleiro])
        resultado = resolver_tentativa_gol(
            partida,
            "Harry",
            resultado_artilheiro_externo=18,
            resultado_goleiro_externo=18,
        )
        self.assertFalse(resultado.gol)
        self.assertTrue(resultado.rolagem_externa_artilheiro)
        self.assertTrue(resultado.rolagem_externa_goleiro)
        self.assertEqual(partida.gols["Grifinória"], 0)

    def test_tentativa_de_gol_supera_defesa_e_altera_placar(self) -> None:
        cobrador = jogador("Harry", "Grifinória", "Artilheiro")
        goleiro = jogador("Bole", "Sonserina", "Goleiro")
        partida = partida_basica([cobrador, goleiro])
        resultado = resolver_tentativa_gol(
            partida,
            "Harry",
            resultado_artilheiro_externo=19,
            resultado_goleiro_externo=18,
        )
        self.assertTrue(resultado.gol)
        self.assertEqual(partida.gols["Grifinória"], 1)

    def test_roubar_o_pomo_forca_derrota_e_aguarda_confirmacao(self) -> None:
        infrator = jogador("Draco", "Sonserina", "Batedor")
        partida = partida_basica([infrator])
        falta = next(item for item in carregar_faltas() if item.nome == "Roubar o Pomo")
        registro = registrar_falta(partida, "Draco", falta)
        self.assertEqual(registro.cartao_aplicado, "Vermelho")
        self.assertEqual(partida.vencedor_forcado, "Grifinória")
        self.assertEqual(partida.estado, "aguardando_confirmacao")


class InterfaceQuadribolTests(unittest.TestCase):
    def test_embeds_de_rolagem_destacam_titulo_e_instrucao(self) -> None:
        alvo = jogador("Almie Etienne", "Grifinória", "Artilheiro")
        adversario = jogador("Adversário", "Sonserina", "Artilheiro")
        partida = partida_basica([alvo, adversario])
        painel = _embed_painel_acao(
            partida,
            "🏐 Passar a Goles",
            "Escolha o destinatário e quem realizará a interceptação.",
        )
        self.assertTrue(painel.description.startswith("# 🏐 Passar a Goles\n## "))

        adicionar_condicao_catalogada(
            partida,
            "Tempo Meteorológico",
            [alvo.nome, adversario.nome],
            intensidade="Padrão",
        )
        clima = _embed_resistencia_tempo_obrigatoria(
            partida,
            alvo,
            "reagir à disputa pela Goles",
        )
        self.assertIn("# 🌦️ Resistir a Condições Meteorológicas", clima.description)
        self.assertIn(
            "## Antes de reagir à disputa pela Goles, **Almie Etienne** precisa "
            "realizar um teste de **Fortitude** contra **CD 12**.",
            clima.description,
        )

    def test_reacao_ao_clima_exibe_resistencia_obrigatoria_antes_da_jogada(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        goleiro = jogador("Goleiro", "Grifinória", "Goleiro", fortitude=2)
        aliado = jogador("Aliado", "Grifinória", "Artilheiro")
        partida = partida_basica([goleiro, aliado])
        adicionar_condicao_catalogada(
            partida,
            "Tempo Meteorológico",
            [goleiro.nome, aliado.nome],
            intensidade="Padrão",
        )
        view = ResistenciaTempoObrigatoriaView(
            cog,
            partida,
            goleiro.nome,
            "defender o arremesso",
            discord.ui.View(),
            discord.ui.View(),
            content_anterior=None,
            embeds_anteriores=[],
        )
        botoes = {
            item.label: item
            for item in view.children
            if isinstance(item, discord.ui.Button)
        }

        self.assertEqual(
            set(botoes),
            {"Resistir a Condições Meteorológicas", "Rolagem Externa", "Voltar"},
        )
        self.assertEqual(
            botoes["Resistir a Condições Meteorológicas"].style,
            discord.ButtonStyle.danger,
        )
        self.assertEqual(botoes["Rolagem Externa"].style, discord.ButtonStyle.secondary)
        self.assertEqual(botoes["Voltar"].style, discord.ButtonStyle.secondary)

    def test_painel_privado_substitui_o_anterior_da_mesma_partida(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        partida = partida_basica([jogador("Atual", "Grifinória", "Artilheiro")])
        anterior = AsyncMock()
        novo = AsyncMock()
        resposta = SimpleNamespace(send_message=AsyncMock())
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=123),
            response=resposta,
            original_response=AsyncMock(return_value=novo),
        )
        chave = (partida.identificador, 123)
        cog.paineis_privados[chave] = anterior

        asyncio.run(
            cog.abrir_painel_privado(
                interaction,
                partida,
                content="Novo painel",
            )
        )

        anterior.delete.assert_awaited_once_with()
        resposta.send_message.assert_awaited_once_with(
            ephemeral=True,
            content="Novo painel",
        )
        self.assertIs(cog.paineis_privados[chave], novo)

    def test_resultado_permite_reabrir_turno_ou_fechar_painel(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        partida = partida_basica([jogador("Atual", "Grifinória", "Artilheiro")])

        botoes = {
            item.label: item
            for item in PainelResultadoView(cog, partida).children
            if isinstance(item, discord.ui.Button)
        }

        self.assertEqual(set(botoes), {"Ver turno atual", "Fechar painel"})
        self.assertEqual(botoes["Ver turno atual"].style, discord.ButtonStyle.primary)
        self.assertEqual(botoes["Fechar painel"].style, discord.ButtonStyle.secondary)

    def test_acoes_separam_verdes_azuis_cinzas_e_voltar_vermelho(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        sem_habilidade = partida_basica(
            [jogador("Comum", "Grifinória", "Artilheiro")]
        )
        self.assertNotIn(
            "Executar Habilidade",
            [item.label for item in AcoesTurnoView(cog, sem_habilidade).children],
        )

        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "Rei.md"
            ficha = FichaPersonagem(
                nome="Rei",
                grupo="Personagem",
                casa="Grifinória",
                heranca="Puro-Sangue",
                nucleo="Teste",
            )
            ficha.especializacoes.append("Rei")
            salvar_ficha(ficha, caminho, nova=True)
            rei = jogador("Rei", "Grifinória", "Artilheiro")
            rei.caminho_ficha = str(caminho)
            partida = partida_basica([rei])
            botoes = {
                item.label: item
                for item in AcoesTurnoView(cog, partida).children
                if isinstance(item, discord.ui.Button)
            }

            self.assertEqual(botoes["Executar Habilidade"].style, discord.ButtonStyle.primary)
            self.assertEqual(botoes["Executar Habilidade"].row, 1)
            self.assertEqual(botoes["Executar Manobra"].row, 1)
            self.assertEqual(botoes["Marcar Gol"].style, discord.ButtonStyle.success)
            self.assertEqual(botoes["Marcar Gol"].row, 0)
            self.assertEqual(botoes["Efeitos e Condições"].style, discord.ButtonStyle.secondary)
            self.assertEqual(botoes["Efeitos e Condições"].row, 2)
            self.assertEqual(botoes["Voltar"].style, discord.ButtonStyle.secondary)
            self.assertEqual(botoes["Voltar"].row, 2)
            self.assertIsInstance(HabilidadeView(cog, partida), HabilidadeView)

    def test_menu_de_manobras_filtra_posicao_e_requisito_do_jogador(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        atual = jogador("Atual", "Grifinória", "Artilheiro")
        atual.quadribol = 1
        partida = partida_basica([atual])
        view = ManobraView(cog, partida)
        seletor = next(item for item in view.children if isinstance(item, discord.ui.Select))
        manobras = {manobra.nome: manobra for manobra in carregar_manobras()}

        self.assertTrue(seletor.options)
        self.assertTrue(
            all(
                "Artilheiro" in manobras[opcao.value].posicoes
                and manobras[opcao.value].requisito_quadribol <= 1
                for opcao in seletor.options
            )
        )

    def test_habilidade_mantem_cada_escolha_visivel_ate_a_execucao(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "Poeta.md"
            ficha = FichaPersonagem(
                nome="Poeta",
                grupo="Personagem",
                casa="Grifinória",
                heranca="Puro-Sangue",
                nucleo="Teste",
            )
            ficha.especializacoes.append("Poeta // Artista")
            salvar_ficha(ficha, caminho, nova=True)
            poeta = jogador("Poeta", "Grifinória", "Artilheiro")
            poeta.caminho_ficha = str(caminho)
            aliado = jogador("Aliado", "Grifinória", "Artilheiro")
            aliado.efeitos.append(
                EfeitoQuadribol(
                    nome="Abalado",
                    origem="Efeito narrativo",
                    categoria="Estado emocional",
                    cd_resistencia=12,
                )
            )
            partida = partida_basica([poeta, aliado])
            view = HabilidadeView(cog, partida)
            view.carregar = lambda _interaction: partida
            interacao = SimpleNamespace(
                response=SimpleNamespace(edit_message=AsyncMock())
            )
            habilidade, alvo, condicao = [
                item for item in view.children if isinstance(item, discord.ui.Select)
            ]

            habilidade._values = ["Poeta // Artista"]
            asyncio.run(habilidade.callback(interacao))
            self.assertEqual(
                [opcao.value for opcao in habilidade.options if opcao.default],
                ["Poeta // Artista"],
            )
            alvo._values = ["Aliado"]
            asyncio.run(alvo.callback(interacao))
            self.assertEqual(
                [opcao.value for opcao in alvo.options if opcao.default], ["Aliado"]
            )
            condicao._values = ["Abalado"]
            asyncio.run(condicao.callback(interacao))
            self.assertEqual(
                [opcao.value for opcao in condicao.options if opcao.default],
                ["Abalado"],
            )
            self.assertEqual((habilidade.max_values, alvo.max_values, condicao.max_values), (1, 1, 1))

            sem_condicao = jogador("Sem condição", "Grifinória", "Artilheiro")
            partida_sem_alvo = partida_basica([poeta, sem_condicao])
            view_sem_alvo = HabilidadeView(cog, partida_sem_alvo)
            view_sem_alvo.carregar = lambda _interaction: partida_sem_alvo
            seletores_sem_alvo = [
                item
                for item in view_sem_alvo.children
                if isinstance(item, discord.ui.Select)
            ]
            seletores_sem_alvo[0]._values = ["Poeta // Artista"]
            asyncio.run(seletores_sem_alvo[0].callback(interacao))
            self.assertTrue(seletores_sem_alvo[1].disabled)
            self.assertEqual(
                seletores_sem_alvo[1].placeholder,
                "Nenhum aliado com condição emocional ativa",
            )
            embed_enviada = interacao.response.edit_message.await_args.kwargs["embed"]
            self.assertIn("Nenhum aliado possui", embed_enviada.description)

    def test_disputa_da_goles_fixa_um_destino_e_um_interceptador(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        passador = jogador("Passador", "Grifinória", "Artilheiro")
        destino = jogador("Destino", "Grifinória", "Artilheiro")
        interceptador = jogador("Interceptador", "Sonserina", "Artilheiro")
        partida = partida_basica([passador, destino, interceptador])
        partida.posse_goles = passador.nome
        view = PosseGolesView(cog, partida, "passar")
        seletores = [
            item for item in view.children if isinstance(item, discord.ui.Select)
        ]
        interacao = SimpleNamespace(
            response=SimpleNamespace(edit_message=AsyncMock())
        )

        seletores[0]._values = [destino.nome]
        asyncio.run(seletores[0].callback(interacao))
        seletores[1]._values = [interceptador.nome]
        asyncio.run(seletores[1].callback(interacao))

        self.assertEqual(view.destinatario, destino.nome)
        self.assertEqual(view.interceptador, interceptador.nome)
        self.assertEqual(
            [opcao.value for opcao in seletores[0].options if opcao.default],
            [destino.nome],
        )
        self.assertEqual(
            [opcao.value for opcao in seletores[1].options if opcao.default],
            [interceptador.nome],
        )
        primeira = SimpleNamespace(
            response=SimpleNamespace(is_done=lambda: False, send_message=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )
        segunda = SimpleNamespace(
            response=SimpleNamespace(is_done=lambda: False, send_message=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )
        self.assertTrue(asyncio.run(view.iniciar_resolucao(primeira)))
        self.assertTrue(all(item.disabled for item in view.children))
        self.assertFalse(asyncio.run(view.iniciar_resolucao(segunda)))
        segunda.response.send_message.assert_awaited_once()

    def test_clima_bloqueia_acoes_ate_resistencia_ser_resolvida(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        alvo = jogador("Afetado", "Grifinória", "Batedor", fortitude=2)
        aliado = jogador("Aliado", "Grifinória", "Artilheiro")
        partida = partida_basica([alvo, aliado])
        adicionar_condicao_catalogada(
            partida,
            "Tempo Meteorológico",
            ["Afetado", "Aliado"],
            intensidade="Padrão",
        )

        bloqueada = AcoesTurnoView(cog, partida)
        self.assertEqual(
            {item.label for item in bloqueada.children},
            {
                "Voltar",
                "Resistir a Condições Meteorológicas",
                "Rolagem Externa",
            },
        )

        resolver_resistencia_tempo(partida, "Afetado", resultado_externo=15)
        liberada = AcoesTurnoView(cog, partida)
        self.assertIn("Acertar Alvo", [item.label for item in liberada.children])
        self.assertNotIn(
            "Resistir a Condições Meteorológicas",
            [item.label for item in liberada.children],
        )

    def test_modal_de_disputa_identifica_jogadores_e_resultados(self) -> None:
        modal = RolagensOpostasModal(
            "Pontaria — Angelina Johnson",
            "Reflexo — Draco Malfoy",
            lambda *_: None,
            titulo="Passe × Interceptação — Resultados",
            ajuda_atacante="Total final do passe para Alicia Spinnet",
            ajuda_defensor="Total final da tentativa de interceptação",
        )

        self.assertEqual(modal.title, "Passe × Interceptação — Resultados")
        self.assertEqual(modal.atacante.label, "Pontaria — Angelina Johnson")
        self.assertEqual(
            modal.atacante.placeholder,
            "Total final do passe para Alicia Spinnet",
        )
        self.assertEqual(modal.defensor.label, "Reflexo — Draco Malfoy")
        self.assertEqual(
            modal.defensor.placeholder,
            "Total final da tentativa de interceptação",
        )

    def test_painel_de_atordoado_mostra_somente_recuperacao(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        alvo = jogador("Atordoado", "Grifinória", "Artilheiro")
        alvo.efeitos.append(
            EfeitoQuadribol(
                nome="Atordoado por Balaço",
                origem="Batedor",
                turnos_restantes=2,
                cd_recuperacao=12,
            )
        )
        partida = partida_basica([alvo])

        view = QuadribolView(cog, partida)

        self.assertEqual(
            [item.label for item in view.children],
            ["Teste de Recuperação", "Passar rodada"],
        )

    def test_controles_principais_tem_ordem_cor_e_linhas_definidas(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        partida = partida_basica([jogador("Atual", "Grifinória", "Artilheiro")])

        botoes = QuadribolView(cog, partida).children

        self.assertEqual(
            [(item.label, item.style, item.row) for item in botoes],
            [
                ("Ações do turno", discord.ButtonStyle.primary, 0),
                ("Passar turno", discord.ButtonStyle.primary, 0),
                ("Passar rodada", discord.ButtonStyle.danger, 0),
                ("Preparar ação", discord.ButtonStyle.secondary, 1),
                ("Outros controles", discord.ButtonStyle.secondary, 1),
            ],
        )

    def test_previa_da_vassoura_usa_formato_vertical_e_bonus_nas_especificacoes(self) -> None:
        ficha = FichaPersonagem(
            nome="Luna",
            grupo="Corvinal",
            casa="Corvinal",
            heranca="Puro-Sangue",
            nucleo="Pena de Fênix",
        )
        vassoura = Vassoura(
            "Comet 260",
            0,
            5,
            linha="Comet",
            velocidade="5m/s",
            custo="90 Galeões e 4 Sicles",
            especificacoes=("Curvas fechadas",),
            bonus_reflexo=1,
            bonus_fortitude=1,
        )
        embed = embed_previa_jogador(ficha, "Apanhador", "Titular", vassoura)
        campos = {campo.name: campo.value for campo in embed.fields}
        self.assertEqual(
            campos["Vassoura"],
            "**Comet 260** *Comet*\n"
            "» **PV**: 5\n"
            "» **Velocidade**: 5m/s\n"
            "» **Valor**: 90 Galeões e 4 Sicles",
        )
        self.assertEqual(
            campos["Especificações da vassoura"],
            "» **Vôo: +0**\n"
            "» **Reflexo: +1**\n"
            "» **Fortitude: +1**\n"
            "» Curvas fechadas",
        )
        processando = embed_registro_jogador(
            ficha, "Apanhador", "Titular", vassoura, concluido=False
        )
        concluido = embed_registro_jogador(
            ficha, "Apanhador", "Titular", vassoura, concluido=True
        )
        self.assertEqual(processando.title, "⏳ Registrando inscrição…")
        self.assertEqual(concluido.title, "✅ Inscrição no time concluída")
        self.assertEqual(concluido.fields[-1].value, campos["Especificações da vassoura"])

    def test_comandos_e_controles_principais_estao_registrados(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        view = QuadribolView(cog)
        self.assertFalse(hasattr(Quadribol, "jogador"))
        self.assertEqual(Quadribol.quadribol.name, "quadribol")
        self.assertEqual(Quadribol.time.name, "time")
        self.assertEqual(Quadribol.quadribol.parameters, [])
        self.assertEqual(Quadribol.time.parameters, [])
        menu_time = SelecionarCasaTimeView(1)
        seletor_time = next(
            item for item in menu_time.children if isinstance(item, discord.ui.Select)
        )
        self.assertEqual([item.value for item in seletor_time.options], [*CASAS, "amador"])
        self.assertEqual(
            {item.custom_id for item in view.children},
            {
                "quadribol:acoes",
                "quadribol:turno",
                "quadribol:preparar",
                "quadribol:rodada",
                "quadribol:outros",
            },
        )

    def test_submenus_expoem_apenas_as_acoes_da_posicao(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        comuns = {"Executar Manobra", "Efeitos e Condições", "Voltar"}

        artilheiro = partida_basica([jogador("Artilheiro", "Grifinória", "Artilheiro")])
        acoes_artilheiro = {item.label for item in AcoesTurnoView(cog, artilheiro).children}
        self.assertEqual(acoes_artilheiro, comuns | {"Marcar Gol"})

        apanhador = partida_basica([jogador("Apanhador", "Grifinória", "Apanhador")])
        acoes_apanhador = {item.label for item in AcoesTurnoView(cog, apanhador).children}
        self.assertEqual(acoes_apanhador, comuns | {"Perseguir Pomo"})

        batedor = partida_basica([jogador("Batedor", "Grifinória", "Batedor")])
        acoes_batedor = {item.label for item in AcoesTurnoView(cog, batedor).children}
        self.assertEqual(acoes_batedor, comuns | {"Acertar Alvo"})

        outros = {item.label for item in OutrosControlesView(cog, artilheiro).children}
        self.assertIn("Voltar", outros)
        self.assertIn("Registrar Falta", outros)
        self.assertEqual(
            outros,
            {"Registrar Falta", "Desfazer placar", "Encerrar / Intervalo", "Voltar"},
        )
        encerrar = next(
            item
            for item in OutrosControlesView(cog, artilheiro).children
            if item.label == "Encerrar / Intervalo"
        )
        self.assertEqual(encerrar.style, discord.ButtonStyle.primary)

        condicoes = EscolherCondicaoCatalogadaView(cog, artilheiro)
        seletor_condicao = next(
            item for item in condicoes.children if isinstance(item, discord.ui.Select)
        )
        self.assertNotIn("Efeito manual", [item.label for item in seletor_condicao.options])

        origens = EscolherOrigemEfeitoView(cog, artilheiro)
        seletor_origem = next(
            item for item in origens.children if isinstance(item, discord.ui.Select)
        )
        self.assertEqual(
            [item.label for item in seletor_origem.options],
            ["Efeito narrativo"],
        )
        self.assertNotIn("Efeito manual", [item.label for item in seletor_origem.options])

        painel_manobra = ManobraView(cog, artilheiro)
        seletores_manobra = sorted(
            (item for item in painel_manobra.children if isinstance(item, discord.ui.Select)),
            key=lambda item: item.row,
        )
        self.assertEqual(len(seletores_manobra), 1)
        self.assertFalse(seletores_manobra[0].disabled)
        self.assertIn(
            "Voltar",
            {item.label for item in painel_manobra.children if isinstance(item, discord.ui.Button)},
        )

    def test_embed_detalhe_manobra_preserva_formato_da_biblioteca(self) -> None:
        manobra = next(
            item for item in carregar_manobras() if item.nome == "Relâmpago de Dragão"
        )
        embed = embed_detalhe_manobra(manobra)
        campos = {campo.name: campo.value for campo in embed.fields}

        self.assertEqual(embed.title, "🧩 Relâmpago de Dragão")
        self.assertEqual(embed.description, manobra.descricao)
        self.assertEqual(campos["CD"], "12")
        self.assertEqual(campos["Requisito de Quadribol"], "+1")
        self.assertEqual(campos["Posições"], "Artilheiro")
        self.assertEqual(campos["Participantes"], "Três Artilheiros.")
        self.assertEqual(campos["Execução"], manobra.execucao)
        self.assertEqual(campos["Benefício"], manobra.beneficio)

    def test_seletores_priorizam_turno_aliados_e_adversarios(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        partida = partida_basica(
            [
                jogador("Adversário", "Sonserina", "Artilheiro"),
                jogador("Aliado", "Grifinória", "Artilheiro"),
                jogador("Dono do turno", "Grifinória", "Batedor"),
            ]
        )
        partida.indice_turno = 2
        view = EscolherAlvosCondicaoView(
            cog,
            partida,
            "Confiante",
            "Efeito narrativo",
        )
        seletor = next(item for item in view.children if isinstance(item, discord.ui.Select))
        self.assertEqual(
            [item.label for item in seletor.options],
            ["Dono do turno", "Aliado", "Adversário"],
        )

    def test_gol_oferece_rolagem_do_bot_ou_externa_para_os_dois_jogadores(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        partida = partida_basica(
            [
                jogador("Artilheiro", "Grifinória", "Artilheiro"),
                jogador("Goleiro", "Sonserina", "Goleiro"),
            ]
        )
        ataque = TentativaGolView(cog, partida)
        self.assertEqual(
            {item.label for item in ataque.children},
            {"Realizar Arremesso", "Rolagem Externa", "Voltar"},
        )
        defesa = DefesaGolView(cog, partida, "Artilheiro", None)
        self.assertEqual(
            {item.label for item in defesa.children},
            {"Realizar Defesa", "Rolagem Externa", "Voltar"},
        )

    def test_ataque_de_balaco_usa_batedor_do_turno_e_parceiro_aliado_so_no_duplo(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        partida = partida_basica(
            [
                jogador("Atacante", "Grifinória", "Batedor"),
                jogador("Parceiro", "Grifinória", "Batedor"),
                jogador("Inimigo", "Sonserina", "Batedor"),
                jogador("Alvo", "Sonserina", "Artilheiro"),
            ]
        )
        view = BalacoView(cog, partida)
        self.assertEqual(view.atacante, "Atacante")
        seletores = [item for item in view.children if isinstance(item, discord.ui.Select)]
        self.assertEqual(
            [item.placeholder for item in seletores],
            ["Jogador atingido", "Tipo de rebatida"],
        )
        self.assertEqual(
            {opcao.value for opcao in seletores[0].options},
            {"Inimigo", "Alvo"},
        )
        self.assertIn(
            "Concluir ação",
            {getattr(item, "label", "") for item in view.children},
        )
        self.assertIn(
            "↩️ Voltar",
            {getattr(item, "label", "") for item in view.children},
        )
        self.assertNotIn(
            "Escolher Alvo",
            {getattr(item, "label", "") for item in view.children},
        )

        view.alvo = "Alvo"
        view.definir_tipo("duplo")
        self.assertTrue(next(opcao for opcao in view.seletor_alvo.options if opcao.value == "Alvo").default)
        self.assertTrue(next(opcao for opcao in view.seletor_tipo.options if opcao.value == "duplo").default)
        self.assertIsNotNone(view.seletor_parceiro)
        self.assertEqual(
            [opcao.value for opcao in view.seletor_parceiro.options],
            ["Parceiro"],
        )
        view.definir_tipo("normal")
        self.assertIsNone(view.seletor_parceiro)

    def test_defesa_de_balaco_revela_somente_os_campos_da_escolha(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        partida = partida_basica(
            [
                jogador("Atacante", "Grifinória", "Batedor"),
                jogador("Alvo", "Sonserina", "Artilheiro"),
                jogador("Defensor", "Sonserina", "Batedor"),
            ]
        )
        view = DefesaBalacoView(cog, partida, "Atacante", "Alvo", False, "")

        def seletores() -> list[str]:
            return [
                item.placeholder
                for item in view.children
                if isinstance(item, discord.ui.Select)
            ]

        self.assertEqual(seletores(), ["Forma de defesa"])
        view.definir_defesa("Batedor")
        self.assertEqual(
            seletores(),
            ["Forma de defesa", "Batedor defensor — apenas se escolhido acima"],
        )
        view.definir_defesa("Redirecionar")
        self.assertEqual(
            seletores(),
            [
                "Forma de defesa",
                "Batedor defensor — apenas se escolhido acima",
                "Novo alvo — apenas para redirecionamento",
            ],
        )
        view.definir_defesa("Reflexo")
        self.assertEqual(seletores(), ["Forma de defesa"])

    def test_jogador_comeca_pelas_casas_e_usa_as_doze_faixas(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        casas = SelecionarCasaJogadorView(cog, 1)
        seletor_casas = next(item for item in casas.children if isinstance(item, discord.ui.Select))
        self.assertEqual([item.value for item in seletor_casas.options], list(CASAS))
        referencias = [
            ReferenciaFicha("Arthur", "Grifinória", Path("fichas/Grifinória/Arthur.md")),
            ReferenciaFicha("Minerva", "Grifinória", Path("fichas/Grifinória/Minerva.md")),
            ReferenciaFicha("Draco", "Sonserina", Path("fichas/Sonserina/Draco.md")),
        ]
        with patch("comandos.quadribol.listar_fichas_elegiveis", return_value=referencias):
            fichas = SelecionarFichaJogadorView(cog, 1, "Grifinória")
        faixas = next(
            item
            for item in fichas.children
            if isinstance(item, discord.ui.Select) and item.row == 0
        )
        self.assertEqual(
            [item.label for item in faixas.options],
            list(GRUPOS_ALFABETICOS_FICHAS),
        )
        self.assertEqual([item.nome for item in fichas.jogadores], ["Arthur"])

    def test_menu_da_casa_inclui_fichas_guardadas_em_players(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            referencia = criar_ficha(
                Path(temporario) / "Luna.md",
                "Luna",
                "Corvinal",
                grupo="Players",
            )
            bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
            cog = Quadribol(bot)
            with patch(
                "comandos.quadribol.listar_fichas_elegiveis",
                return_value=[referencia],
            ):
                view = SelecionarFichaJogadorView(cog, 1, "Corvinal", pagina=5)
            self.assertEqual([item.nome for item in view.jogadores], ["Luna"])

    def test_primeira_equipe_some_do_menu_da_adversaria(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        cog = Quadribol(bot)
        view = ConfigurarPartidaView(cog, 1, casa_1="Grifinória")
        seletores = {
            item.row: item
            for item in view.children
            if isinstance(item, discord.ui.Select)
        }
        self.assertEqual(len(seletores), 3)
        self.assertNotIn(
            "Grifinória",
            [item.value for item in seletores[1].options],
        )
        self.assertEqual(
            [item.value for item in seletores[2].options],
            list(JOGOS_TEMPORADA),
        )

    def test_linhas_recomendadas_vem_primeiro_sem_preco_na_descricao(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            referencia = criar_ficha(
                Path(temporario) / "Luna.md",
                "Luna",
                "Corvinal",
                vassoura="",
            )
            bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
            cog = Quadribol(bot)
            linhas = ConfigurarJogadorView(cog, referencia, 1)
            seletor_linhas = next(
                item
                for item in linhas.children
                if isinstance(item, discord.ui.Select) and item.row == 2
            )
            nimbus = next(item for item in seletor_linhas.options if item.value == "Nimbus")
            self.assertEqual(nimbus.description, "Favorece: Apanhador")
            descricoes = {
                item.value: item.description for item in seletor_linhas.options
            }
            self.assertEqual(descricoes["Cavalier"], "Favorece: Goleiro/Batedor")
            self.assertEqual(descricoes["Thunderbolt"], "Favorece: Batedor/Apanhador")
            self.assertEqual(descricoes["Oakshaft"], "Favorece: Batedor")
            self.assertFalse(
                any("Gale" in (item.description or "") for item in seletor_linhas.options)
            )
            self.assertEqual(
                [item.value for item in seletor_linhas.options[:3]],
                ["Cleansweep", "Onda Aérea", "Yajirushi"],
            )
            self.assertFalse(
                any(
                    isinstance(item, discord.ui.Select) and item.row == 3
                    for item in linhas.children
                )
            )
            modelos = ConfigurarJogadorView(
                cog,
                referencia,
                1,
                linha="Nimbus",
            )
            seletor_modelos = next(
                item
                for item in modelos.children
                if isinstance(item, discord.ui.Select) and item.row == 3
            )
            self.assertEqual(
                [item.value for item in seletor_modelos.options],
                ["Nimbus 1000", "Nimbus 1700", "Nimbus 2000", "Nimbus 2001"],
            )
            self.assertTrue(
                all("Gale" in (item.description or "") for item in seletor_modelos.options)
            )
            confirmacao = ConfirmarJogadorView(
                cog,
                referencia,
                "Artilheiro",
                "Titular",
                listar_vassouras()[0],
                1,
            )
            self.assertEqual(
                [item.label for item in confirmacao.children],
                ["Confirmar", "Voltar", "Cancelar"],
            )

    def test_time_mostra_uma_embed_por_jogador_com_titulares_primeiro(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            titular = criar_ficha(
                pasta / "Luna.md",
                "Luna",
                "Corvinal",
                posicao="Artilheiro",
                situacao="Titular",
                grupo="Players",
            )
            reserva = criar_ficha(
                pasta / "Cho.md",
                "Cho",
                "Corvinal",
                posicao="Apanhador",
                situacao="Reserva",
            )
            modelo = Vassoura(
                "Nimbus de Teste",
                2,
                4,
                linha="Nimbus",
                velocidade="9m/s",
                bonus_reflexo=1,
            )
            with (
                patch(
                    "comandos.quadribol.listar_fichas_elegiveis",
                    return_value=[reserva, titular],
                ),
                patch("comandos.quadribol.listar_vassouras", return_value=[modelo]),
            ):
                embeds = embeds_time("Corvinal")
            self.assertEqual(len(embeds), 8)
            self.assertEqual(embeds[0].description, "**Goleiro • Titular**")
            self.assertEqual(embeds[0].fields[0].value, "--")
            self.assertEqual(embeds[1].title, "💙 Luna")
            self.assertEqual(embeds[1].description, "**Artilheiro • Titular**")
            self.assertIn(
                "**Pontaria:** +3 Destreza +2 Treinada = **+5 total**",
                embeds[1].fields[1].value,
            )
            self.assertEqual(embeds[-1].title, "💙 Cho")
            self.assertEqual(embeds[-1].description, "**Apanhador • Reserva**")
            self.assertEqual(
                sum(item.title == "💙 --" for item in embeds),
                6,
            )
            pequenos = [discord.Embed(title="--") for _ in range(11)]
            self.assertEqual([len(item) for item in lotes_embeds(pequenos)], [10, 1])

    def test_time_vazio_exibe_as_sete_vagas_titulares_com_tracos(self) -> None:
        with patch("comandos.quadribol.listar_fichas_elegiveis", return_value=[]):
            embeds = embeds_time("Lufa-Lufa")
        self.assertEqual(len(embeds), 7)
        self.assertEqual(
            [item.description for item in embeds],
            [
                "**Goleiro • Titular**",
                "**Artilheiro • Titular**",
                "**Artilheiro • Titular**",
                "**Artilheiro • Titular**",
                "**Batedor • Titular**",
                "**Batedor • Titular**",
                "**Apanhador • Titular**",
            ],
        )
        self.assertTrue(
            all(campo.value == "--" for embed in embeds for campo in embed.fields)
        )


class CatalogoManobrasTests(unittest.TestCase):
    def manobra(self, nome: str = "Investida de Teste") -> ManobraQuadribol:
        return ManobraQuadribol(
            nome=nome,
            cd=16,
            requisito_quadribol=5,
            posicoes=("Artilheiro", "Batedor"),
            participantes="Um Artilheiro e um Batedor.",
            descricao="Uma formação excepcional criada para validar o catálogo.",
            execucao="Os participantes coordenam o avanço e concluem a formação.",
            beneficio="Concede uma vantagem decisiva descrita pela manobra.",
        )

    def test_adiciona_manobra_com_requisito_ate_cinco(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Manobras.md"
            caminho.write_text("# Manobras de Quadribol\n", encoding="utf-8")
            adicionada = adicionar_manobra_biblioteca(
                self.manobra(), caminho=caminho
            )
            carregadas = carregar_manobras(caminho)
        self.assertEqual(adicionada.requisito_quadribol, 5)
        self.assertEqual(len(carregadas), 1)
        self.assertEqual(carregadas[0], adicionada)

    def test_rejeita_requisito_acima_de_cinco_e_nome_duplicado(self) -> None:
        invalida = self.manobra()
        invalida = ManobraQuadribol(
            **{**invalida.__dict__, "requisito_quadribol": 6}
        )
        with self.assertRaisesRegex(ValueError, r"entre \+1 e \+5"):
            validar_nova_manobra(invalida)
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Manobras.md"
            caminho.write_text("# Manobras de Quadribol\n", encoding="utf-8")
            adicionar_manobra_biblioteca(self.manobra(), caminho=caminho)
            with self.assertRaisesRegex(ValueError, "Já existe"):
                validar_nova_manobra(self.manobra(), caminho=caminho)

    def test_central_oferece_consulta_e_criacao_em_etapas(self) -> None:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        cog = Quadribol(bot)
        central = CentralManobrasView(123, cog)
        self.assertEqual(
            [item.label for item in central.children],
            ["Consultar Manobras", "Criar Manobra"],
        )
        criacao = CriarManobraView(cog, 123, RascunhoManobra())
        self.assertEqual(criacao.children[0].options[-1].value, "5")
        self.assertEqual(criacao.children[1].max_values, 4)
        self.assertIn("Revisar Manobra", [item.label for item in criacao.children[2:]])

    def test_indice_recebe_link_sem_observacao_final(self) -> None:
        texto = "**Manobras existentes**\n» [Antiga](url)"
        novo = Quadribol._inserir_link_manobra_indice(
            texto,
            "Nova Manobra",
            "https://discord.com/channels/1/2/3",
        )
        self.assertIn("» [Nova Manobra](https://discord.com/channels/1/2/3)", novo)
        self.assertNotIn("Selecione o nome de uma manobra", novo)

    def test_guia_recebe_link_antes_da_proxima_secao(self) -> None:
        texto = "**Manobras existentes**\n» [Antiga](url)\n\n## 12 — Efeitos e condições"
        novo = Quadribol._inserir_link_manobra_indice(
            texto,
            "Nova Manobra",
            "https://discord.com/channels/1/2/3",
        )
        self.assertLess(novo.index("Nova Manobra"), novo.index("## 12"))


if __name__ == "__main__":
    unittest.main()
    carregar_faltas,
