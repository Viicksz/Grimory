from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
from discord.ext import commands

from comandos.combate import (
    AcoesCombateView,
    AnoFeiticoCombateView,
    CategoriaFeiticoCombateView,
    ControleCombateView,
    CombateCog,
    PainelCombateView,
    SelecionarFaixaCombateView,
    SelecionarFeiticoCombateView,
    SelecionarAlvoAtaqueView,
    SelecionarOrigemCombateView,
    TipoAtaqueView,
    VIDEOS_HOMENAGEM,
    embed_combate,
    embed_acoes_turno,
    embed_relatorio,
    _cd_feitico_por_ficha,
    _feitico_eh_lampejo,
    _feitico_eh_reacao_magica,
    _feitico_disponivel_para_ficha,
    _reacao_magica_compativel,
    _ajuste_cd_reacao,
    _bonus_registrado,
    _dano_feitico,
    _tipo_acao_registrado,
    _armas_participante,
    _pocoes_participante,
)
from comandos.executar import ItemIndice
from utils.biblioteca import EntradaBiblioteca
from utils.combate import (
    EQUIPE_ALIADOS,
    EQUIPE_OPONENTES,
    Combate,
    ParticipanteCombate,
    ReferenciaCombatente,
    adicionar_participante,
    alterar_recursos,
    aplicar_dano_combate,
    avancar_turno,
    carregar_combate,
    criar_combate,
    criar_novo_combate,
    consumir_acao,
    encerrar_combate,
    extrair_expressao_dano,
    iniciar_combate,
    participante_da_referencia,
    ativar_habilidade_combate,
    tipo_acao_descricao,
    salvar_combate,
    registrar_ataque_combate,
    rolar_expressao_dano,
)
from utils.fichas import FichaPersonagem
from utils.fichas_criaturas import FichaCriatura


def participante(
    nome: str,
    equipe: str,
    *,
    bonus: int = 0,
    ordem: int = 0,
    pv: int = 20,
    ph: int = 5,
) -> ParticipanteCombate:
    return ParticipanteCombate(
        identificador=nome.casefold().replace(" ", "-"),
        nome=nome,
        equipe=equipe,
        tipo_ficha="personagem",
        caminho_ficha=f"{nome}.md",
        pv_maximo=pv,
        ph_maximo=ph,
        pv_atual=pv,
        ph_atual=ph,
        iniciativa_bonus=bonus,
        ordem_entrada=ordem,
        usuario_id=0,
    )


class DominioCombateTests(unittest.TestCase):
    def test_personagem_entra_com_pv_ph_e_iniciativa_da_ficha(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Aurora.md"
            ficha = FichaPersonagem("Aurora", "Estudantes", "Corvinal", "--", "--")
            ficha.pv = 31
            ficha.ph = 9
            ficha.titular_id = 321
            ficha.atributos["Destreza"] = 14
            ficha.pericias["Iniciativa"] = 2
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            referencia = ReferenciaCombatente("Aurora", "personagem", "Estudantes", caminho)

            item = participante_da_referencia(referencia, EQUIPE_ALIADOS, 0)

            self.assertEqual((item.pv_atual, item.pv_maximo), (31, 31))
            self.assertEqual((item.ph_atual, item.ph_maximo), (9, 9))
            self.assertEqual(item.iniciativa_bonus, 4)
            self.assertEqual(item.usuario_id, 321)

    def test_criatura_usa_ph_como_recurso_temporario(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Criatura.md"
            ficha = FichaCriatura(
                nome="Criatura",
                classificacao="Fera",
                periculosidade="XX",
                tamanho="1,5 m",
                faixa_tamanho="De 1 m a 2 m",
            )
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            referencia = ReferenciaCombatente("Criatura", "criatura", "Criatura XX", caminho)

            item = participante_da_referencia(referencia, EQUIPE_OPONENTES, 0)

            self.assertEqual(item.pv_maximo, ficha.pv)
            self.assertEqual(item.ph_maximo, ficha.ph)

    def test_inicio_ordena_por_total_e_desempata_pelo_bonus(self) -> None:
        combate = criar_combate(1)
        combate.participantes = [
            participante("A", EQUIPE_ALIADOS, bonus=2, ordem=0),
            participante("B", EQUIPE_OPONENTES, bonus=5, ordem=1),
        ]
        dados = iter((13, 10))

        iniciar_combate(combate, lambda: next(dados))

        self.assertEqual([item.nome for item in combate.participantes], ["B", "A"])
        self.assertEqual(combate.rodada, 1)
        self.assertEqual(combate.participante_atual().nome, "B")

    def test_reforco_entra_no_fim_sem_reordenar_iniciativa(self) -> None:
        combate = criar_combate(1)
        combate.participantes = [
            participante("A", EQUIPE_ALIADOS, ordem=0),
            participante("B", EQUIPE_OPONENTES, ordem=1),
        ]
        iniciar_combate(combate, lambda: 10)
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "C.md"
            ficha = FichaPersonagem("C", "Estudantes", "--", "--", "--")
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            referencia = ReferenciaCombatente("C", "personagem", "Estudantes", caminho)
            adicionar_participante(combate, referencia, EQUIPE_OPONENTES)

        self.assertEqual([item.nome for item in combate.participantes], ["A", "B", "C"])
        self.assertEqual(combate.participantes[-1].iniciativa_dado, 0)

    def test_turno_ignora_mortos_e_incapacitados(self) -> None:
        combate = criar_combate(1)
        combate.estado = "ativo"
        combate.rodada = 1
        combate.participantes = [
            participante("A", EQUIPE_ALIADOS),
            participante("B", EQUIPE_OPONENTES),
            participante("C", EQUIPE_OPONENTES),
        ]
        combate.participantes[1].estado = "morto"
        combate.participantes[2].estado = "incapacitado"

        proximo = avancar_turno(combate)

        self.assertEqual(proximo.nome, "A")
        self.assertEqual(combate.rodada, 2)

    def test_recursos_sao_limitados_ao_maximo_e_zero_incapacita(self) -> None:
        item = participante("A", EQUIPE_ALIADOS)
        alterar_recursos(item, pv=99, ph=99)
        self.assertEqual((item.pv_atual, item.ph_atual), (20, 5))
        alterar_recursos(item, pv=0)
        self.assertEqual(item.estado, "incapacitado")
        self.assertEqual(item.dano_recebido, 20)

    def test_novo_combate_leva_apenas_vivos_e_preserva_ph(self) -> None:
        anterior = criar_combate(1)
        vivo = participante("Vivo", EQUIPE_ALIADOS, pv=20, ph=8)
        vivo.pv_atual = 4
        vivo.ph_atual = 2
        morto = participante("Morto", EQUIPE_OPONENTES)
        morto.estado = "morto"
        anterior.participantes = [vivo, morto]

        novo = criar_novo_combate(anterior, "5m", rolar_dados=lambda quantidade, faces: 4)

        self.assertEqual([item.nome for item in novo.participantes], ["Vivo"])
        self.assertEqual(novo.participantes[0].pv_atual, 9)
        self.assertEqual(novo.participantes[0].ph_atual, 2)
        self.assertEqual(anterior.estado, "encerrado")

    def test_persistencia_nao_depende_da_ficha_original(self) -> None:
        combate = criar_combate(123)
        combate.participantes.append(participante("A", EQUIPE_ALIADOS))
        combate.mensagem_atualizacao_id = 987
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "combate.md"
            salvar_combate(combate, caminho)
            restaurado = carregar_combate(caminho)
        self.assertEqual(restaurado.identificador, combate.identificador)
        self.assertEqual(restaurado.participantes[0].pv_atual, 20)
        self.assertEqual(restaurado.mensagem_atualizacao_id, 987)

    def test_economia_de_acoes_permite_duplo_movimento_mas_nao_duplo_ataque(self) -> None:
        item = participante("A", EQUIPE_ALIADOS)
        self.assertEqual(consumir_acao(item, "movimento"), "movimento")
        self.assertEqual(
            consumir_acao(item, "movimento"),
            "padrão convertida em movimento",
        )
        with self.assertRaisesRegex(ValueError, "movimento"):
            consumir_acao(item, "movimento")
        with self.assertRaisesRegex(ValueError, "padrão"):
            consumir_acao(item, "padrao")

    def test_habilidade_so_consume_acao_quando_descricao_determina(self) -> None:
        combate = criar_combate(1)
        item = participante("A", EQUIPE_ALIADOS, ph=10)
        combate.participantes = [item]
        consumo = ativar_habilidade_combate(
            combate, item.identificador, "Instinto", "Efeito imediato.", 2
        )
        self.assertEqual(consumo, "não consome ação")
        self.assertFalse(item.acao_padrao_usada)
        self.assertFalse(item.acao_livre_usada)
        consumo = ativar_habilidade_combate(
            combate,
            item.identificador,
            "Concentração",
            "Esta habilidade gasta uma ação padrão.",
            4,
        )
        self.assertEqual(consumo, "padrão")
        self.assertTrue(item.acao_padrao_usada)
        self.assertEqual(item.ph_atual, 4)
        self.assertEqual(tipo_acao_descricao("Usada como ação completa."), "completa")

    def test_acao_completa_consumira_todas_as_reservas(self) -> None:
        item = participante("A", EQUIPE_ALIADOS)
        self.assertEqual(consumir_acao(item, "completa"), "completa")
        self.assertTrue(item.acao_padrao_usada)
        self.assertTrue(item.acao_movimento_usada)
        self.assertTrue(item.acao_livre_usada)

    def test_habilidade_de_criatura_paga_ph_respeita_acao_e_recarga(self) -> None:
        combate = criar_combate(1)
        item = participante("Teste", EQUIPE_OPONENTES, ph=44)
        combate.participantes = [item]

        registrar_ataque_combate(
            combate,
            item.identificador,
            "Teste usou Estalo Abissal.",
            tipo_acao="padrao",
            custo_ph=4,
            nome_recarga="Estalo Abissal",
            recarga="2 rodada(s)",
        )

        self.assertEqual(item.ph_atual, 40)
        self.assertTrue(item.acao_padrao_usada)
        self.assertEqual(item.recargas["Estalo Abissal"], 2)
        with self.assertRaisesRegex(ValueError, "recarga"):
            registrar_ataque_combate(
                combate,
                item.identificador,
                "Teste repetiu Estalo Abissal.",
                nome_recarga="Estalo Abissal",
                recarga="2 rodada(s)",
            )

    def test_dano_da_habilidade_e_extraido_rolado_e_aplicado(self) -> None:
        expressao = extrair_expressao_dano("2d8+6 (Magia) de dano mágico.")
        self.assertEqual(expressao, "2d8+6")
        dados = iter((3, 7))
        total, resultados, modificador = rolar_expressao_dano(
            expressao, lambda minimo, maximo: next(dados)
        )
        self.assertEqual((total, resultados, modificador), (16, [3, 7], 6))

        combate = criar_combate(1)
        atacante = participante("Teste", EQUIPE_OPONENTES)
        alvo = participante("Alvo", EQUIPE_ALIADOS, pv=12)
        combate.participantes = [atacante, alvo]
        aplicado = aplicar_dano_combate(
            combate, atacante.identificador, alvo.identificador, total, "Estalo Abissal"
        )
        self.assertEqual(aplicado, 12)
        self.assertEqual(alvo.pv_atual, 0)
        self.assertEqual(alvo.estado, "incapacitado")
        self.assertEqual(atacante.dano_causado, 12)


class InterfaceCombateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        self.cog = CombateCog(self.bot)

    def test_comando_e_botoes_principais(self) -> None:
        combate = criar_combate(1)
        view = PainelCombateView(self.cog, combate)
        rotulos = {item.label for item in view.children}
        self.assertEqual(CombateCog.combate.name, "combate")
        self.assertIn("Novo aliado", rotulos)
        self.assertIn("Novo oponente", rotulos)
        self.assertIn("Controle de Combate", rotulos)
        self.assertNotIn("Encerrar combate", rotulos)
        self.assertNotIn("Novo combate", rotulos)

        controle = ControleCombateView(self.cog, 1, combate)
        rotulos_controle = {item.label for item in controle.children}
        self.assertEqual(
            rotulos_controle,
            {"PV, PH e estado", "Novo combate", "Encerrar combate", "Voltar"},
        )

    def test_botao_de_acao_abre_as_quatro_categorias(self) -> None:
        combate = criar_combate(1)
        item = participante("A", EQUIPE_ALIADOS)
        combate.participantes = [item]
        view = AcoesCombateView(self.cog, 1, combate, item)
        self.assertEqual(
            [botao.label for botao in view.children],
            ["Usar habilidade", "Não usar habilidade", "Encerrar turno", "Voltar"],
        )
        self.assertEqual(
            next(botao for botao in view.children if botao.label == "Voltar").row,
            4,
        )
        self.assertEqual(
            next(botao for botao in view.children if botao.label == "Encerrar turno").row,
            4,
        )
        item.acao_padrao_usada = True
        concluido = AcoesCombateView(self.cog, 1, combate, item)
        self.assertEqual(
            [botao.label for botao in concluido.children],
            ["Encerrar turno", "Voltar"],
        )

    def test_feitico_usa_cd_do_ano_e_so_libera_esquiva_para_lampejo(self) -> None:
        ficha = FichaPersonagem("A", "Grifinória", "Grifinória", "--", "--")
        ficha.ano = "4°Ano"
        entrada = EntradaBiblioteca(
            "Teste",
            "O lampejo segue em direção ao alvo.",
            {
                "Categoria": "Duelos",
                "Grau de dificuldade": "Intermediário Ⅲ",
                "Dificuldade por ano": "1º Ano: 14+\n4º Ano: 10+\n+18y: 8+",
            },
        )
        item = ItemIndice("Teste", entrada, "feitico")
        self.assertEqual(_cd_feitico_por_ficha(item, ficha), (10, "4º Ano"))
        self.assertTrue(_feitico_eh_lampejo(item))
        entrada_sem_lampejo = EntradaBiblioteca("Outro", "Afeta o alvo diretamente.", {})
        self.assertFalse(
            _feitico_eh_lampejo(ItemIndice("Outro", entrada_sem_lampejo, "feitico"))
        )

        contra = EntradaBiblioteca(
            "Deflecto",
            "**Reação** Desvia o lampejo de um feitiço intermediário.",
            {
                "Categoria": "Duelos",
                "Ano de desbloqueio": "3º Ano",
                "Grau de dificuldade": "Intermediário Ⅲ",
            },
        )
        reversao = EntradaBiblioteca(
            "Densaugeo",
            "O efeito pode ser revertido por um contra-feitiço apropriado.",
            {"Categoria": "Transfiguração", "Ano de desbloqueio": "3º Ano"},
        )
        item_contra = ItemIndice("Deflecto", contra, "feitico")
        self.assertTrue(
            _feitico_eh_reacao_magica(item_contra)
        )
        self.assertFalse(
            _feitico_eh_reacao_magica(ItemIndice("Densaugeo", reversao, "feitico"))
        )
        self.assertTrue(_reacao_magica_compativel(item_contra, item, lampejo=True))
        self.assertFalse(_reacao_magica_compativel(item_contra, item, lampejo=False))
        ficha.aptidoes["Duelos"] = 2
        self.assertTrue(_feitico_disponivel_para_ficha(item_contra, ficha))
        ficha.ano = "2º Ano"
        self.assertFalse(_feitico_disponivel_para_ficha(item_contra, ficha))

        protego = ItemIndice(
            "Protego",
            EntradaBiblioteca(
                "Protego",
                "Quando conjurado como reação a CD aumenta em +4.",
                {},
            ),
            "feitico",
        )
        self.assertEqual(_ajuste_cd_reacao(protego), 4)

    def test_elektrus_separa_dano_inicial_do_sustentado(self) -> None:
        descricao = (
            "1d4+2 de dano elétrico, +2 de dano elétrico por turno sustentado."
        )
        self.assertEqual(extrair_expressao_dano(descricao), "1d4+2")

    def test_campos_estruturados_da_habilidade_definem_bonus_e_acao(self) -> None:
        self.assertEqual(_bonus_registrado("Magia +6"), 6)
        self.assertEqual(_bonus_registrado("Luta -2"), -2)
        self.assertEqual(_tipo_acao_registrado("Padrão"), "padrao")
        self.assertEqual(_tipo_acao_registrado("Ação completa"), "completa")

    def test_combate_prefere_perfil_estruturado_do_feitico(self) -> None:
        entrada = EntradaBiblioteca(
            "Teste",
            "A descrição antiga chama isto de lampejo, mas o perfil é oficial.",
            {"Categoria": "Duelos"},
            perfil_combate={
                "mira": "Campo de Visão",
                "dano": {"inicial": "3d8+1"},
                "defesa": {"ajuste_cd_reacao": 6},
            },
        )
        item = ItemIndice("Teste", entrada, "feitico")
        self.assertFalse(_feitico_eh_lampejo(item))
        self.assertEqual(_dano_feitico(item), "3d8+1")
        self.assertEqual(_ajuste_cd_reacao(item), 6)

    def test_feiticos_seguem_categoria_ano_indice_clicavel_e_seletor(self) -> None:
        itens = [
            ItemIndice(
                "Primeiro",
                EntradaBiblioteca(
                    "Primeiro", "", {"Ano de desbloqueio": "1º Ano", "Categoria": "Duelos"}
                ),
                "feitico",
            ),
            ItemIndice(
                "Terceiro",
                EntradaBiblioteca(
                    "Terceiro", "", {"Ano de desbloqueio": "3° Ano", "Categoria": "Duelos"}
                ),
                "feitico",
            ),
        ]
        with patch("comandos.combate.carregar_todos_feiticos", return_value=itens):
            categorias = CategoriaFeiticoCombateView(self.cog, 1, "combate", "participante")
            anos = AnoFeiticoCombateView(
                self.cog, 1, "combate", "participante", "duelos"
            )
        self.assertEqual([opcao.label for opcao in categorias.seletor.options], ["Duelos"])
        self.assertIn("Voltar", [getattr(item, "label", None) for item in categorias.children])
        self.assertEqual([opcao.label for opcao in anos.seletor.options], ["1º Ano", "3º Ano"])
        self.assertIn("Voltar", [getattr(item, "label", None) for item in anos.children])

        indice = SelecionarFeiticoCombateView(
            self.cog,
            1,
            "combate",
            "participante",
            "duelos",
            "1º Ano",
            [itens[0]],
            {"primeiro": "https://discord.com/channels/1/2/3"},
        )
        self.assertIn("[Primeiro](https://discord.com/channels/1/2/3)", indice.embed_indice().description)
        self.assertEqual([opcao.label for opcao in indice.seletor.options], ["Primeiro"])
        self.assertIn("Voltar", [getattr(item, "label", None) for item in indice.children])

    def test_ataque_oferece_somente_alvos_da_equipe_adversaria(self) -> None:
        combate = criar_combate(1)
        atacante = participante("Atacante", EQUIPE_ALIADOS)
        aliado = participante("Aliado", EQUIPE_ALIADOS)
        oponente = participante("Oponente", EQUIPE_OPONENTES)
        combate.participantes = [atacante, aliado, oponente]
        with patch.object(self.cog, "localizar", return_value=(combate, Path("combate.md"))):
            view = SelecionarAlvoAtaqueView(
                self.cog,
                1,
                combate.identificador,
                atacante.identificador,
                tipo="arma",
                nome="Ataque",
                bonus=0,
                cd=0,
                lampejo=False,
                dano="1d6",
                externo=False,
            )
        self.assertEqual([opcao.label for opcao in view.seletor.options], ["Oponente"])

    def test_menu_de_ataque_mostra_somente_recursos_presentes_na_ficha(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            ficha_criatura = FichaCriatura(
                nome="Criatura",
                classificacao="Fera",
                periculosidade="X",
                tamanho="1 m",
                faixa_tamanho="De 1 m a 2 m",
            )
            ficha_criatura.armas_naturais.append(
                {"nome": "Garras", "categoria": "Armas Naturais", "dano": "1d6"}
            )
            caminho_criatura = raiz / "Criatura.md"
            caminho_criatura.write_text(ficha_criatura.markdown(), encoding="utf-8")
            criatura = participante("Criatura", EQUIPE_OPONENTES)
            criatura.tipo_ficha = "criatura"
            criatura.caminho_ficha = str(caminho_criatura)

            ficha_sem_magia = FichaPersonagem("Sem magia", "NPCs", "--", "--", "--")
            caminho_personagem = raiz / "Sem magia.md"
            caminho_personagem.write_text(ficha_sem_magia.markdown(), encoding="utf-8")
            personagem = participante("Sem magia", EQUIPE_ALIADOS)
            personagem.caminho_ficha = str(caminho_personagem)

            combate = criar_combate(1)
            combate.participantes = [criatura, personagem]
            with patch.object(self.cog, "localizar", return_value=(combate, Path("combate.md"))):
                menu_criatura = TipoAtaqueView(
                    self.cog, 1, combate.identificador, criatura.identificador
                )
                menu_sem_magia = TipoAtaqueView(
                    self.cog, 1, combate.identificador, personagem.identificador
                )

            self.assertEqual(
                [getattr(item, "label", None) for item in menu_criatura.children],
                ["Arma", "Voltar"],
            )
            criatura.acao_padrao_usada = True
            with patch.object(self.cog, "localizar", return_value=(combate, Path("combate.md"))):
                menu_sem_acao = TipoAtaqueView(
                    self.cog, 1, combate.identificador, criatura.identificador
                )
            self.assertEqual(
                [getattr(item, "label", None) for item in menu_sem_acao.children],
                ["Voltar"],
            )
            self.assertEqual(
                [getattr(item, "label", None) for item in menu_sem_magia.children],
                ["Voltar"],
            )

    def test_personagem_usa_armas_e_pocoes_exclusivamente_do_inventario(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Inventario.md"
            ficha = FichaPersonagem("Inventário", "Players", "Corvinal", "--", "--")
            ficha.atributos["Destreza"] = 14
            ficha.itens = [
                {
                    "categoria": "Armas",
                    "nome": "Espada Longa",
                    "quantidade": "1",
                    "tipo": "Cortante",
                    "dano": "1d8+des",
                    "critico": "19",
                },
                {"categoria": "Poções", "nome": "Poção Wiggenweld", "quantidade": "2"},
            ]
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            personagem = participante("Inventário", EQUIPE_ALIADOS)
            personagem.caminho_ficha = str(caminho)
            oponente = participante("Alvo", EQUIPE_OPONENTES)
            combate = criar_combate(1)
            combate.estado = "ativo"
            combate.participantes = [personagem, oponente]
            with patch.object(self.cog, "localizar", return_value=(combate, Path("combate.md"))):
                ataques = TipoAtaqueView(
                    self.cog, 1, combate.identificador, personagem.identificador
                )
                acoes = AcoesCombateView(self.cog, 1, combate, personagem)

            self.assertIn("Arma", [getattr(item, "label", None) for item in ataques.children])
            self.assertIn("Usar poção", [getattr(item, "label", None) for item in acoes.children])
            armas = _armas_participante(personagem)
            self.assertEqual(armas[0]["dano"], "1d8+2 (Destreza)")
            self.assertEqual(armas[0]["tipo de dano"], "Cortante")
            self.assertEqual(_pocoes_participante(personagem)[0]["quantidade"], "2")

    def test_embed_mostra_as_duas_equipes_e_recursos(self) -> None:
        combate = criar_combate(1)
        combate.participantes = [
            participante("Aliado", EQUIPE_ALIADOS),
            participante("Oponente", EQUIPE_OPONENTES),
        ]
        embed = embed_combate(combate)
        campos = {campo.name: campo.value for campo in embed.fields}
        self.assertFalse(embed.description.startswith("> "))
        self.assertIn("Aliado", campos["👥 Aliados"])
        self.assertIn("20/20", campos["👥 Aliados"])
        self.assertIn("> PV", campos["👥 Aliados"])
        self.assertIn("Oponente", campos["🔥 Oponentes"])
        self.assertEqual(embed.title, "⚔️ Combate")

    def test_embed_marca_turno_e_rodada_atuais(self) -> None:
        combate = criar_combate(1)
        combate.estado = "ativo"
        combate.rodada = 1
        combate.indice_turno = 0
        combate.participantes = [
            participante("Aliado", EQUIPE_ALIADOS),
            participante("Oponente", EQUIPE_OPONENTES),
        ]
        self.assertIn(
            "⏱️ **1º turno da Primeira Rodada**", embed_combate(combate).description
        )
        self.assertFalse(
            any(campo.name.startswith("Ações") for campo in embed_combate(combate).fields)
        )
        acoes = embed_acoes_turno(combate.participante_atual()).fields[0].value
        self.assertIn("Ação Completa: ✅", acoes)
        self.assertIn("Ação Padrão: ✅", acoes)
        self.assertIn("Ação de Movimento: ✅", acoes)
        self.assertIn("Ação Livre: ✅", acoes)
        combate.indice_turno = 1
        combate.rodada = 2
        self.assertIn(
            "⏱️ **2º turno da Segunda Rodada**", embed_combate(combate).description
        )

    def test_selecao_pergunta_pasta_e_depois_faixa_alfabetica(self) -> None:
        referencias = [
            ReferenciaCombatente("Aurora", "personagem", "Grifinória", Path("Aurora.md")),
            ReferenciaCombatente("Zacarias", "personagem", "NPCs", Path("Zacarias.md")),
        ]
        with patch("comandos.combate.listar_referencias_combate", return_value=referencias):
            origem = SelecionarOrigemCombateView(
                self.cog, 1, "combate", EQUIPE_ALIADOS
            )
            pastas = [opcao.label for opcao in origem.seletor.options]
            self.assertIn("NPCs", pastas)
            self.assertIn("Figuras de Autoridade", pastas)
            self.assertIn("Grifinória", pastas)
            self.assertIn("Criaturas", pastas)

            alfabetica = SelecionarFaixaCombateView(
                self.cog,
                1,
                "combate",
                EQUIPE_ALIADOS,
                "Grifinória",
                0,
            )
            self.assertEqual(
                [opcao.label for opcao in alfabetica.faixas.options],
                ["AB", "CD", "EF", "GH", "IJ", "KL", "MN", "OP", "QR", "ST", "UV", "WXYZ"],
            )
            self.assertNotIn(
                "Finalizar",
                [getattr(item, "label", None) for item in alfabetica.children],
            )

            apos_primeira = SelecionarFaixaCombateView(
                self.cog,
                1,
                "combate",
                EQUIPE_ALIADOS,
                "Grifinória",
                0,
                pode_finalizar=True,
            )
            botoes = {
                item.label: item
                for item in apos_primeira.children
                if isinstance(item, discord.ui.Button)
            }
            self.assertEqual(botoes["Finalizar"].style, discord.ButtonStyle.success)
            self.assertEqual(botoes["Finalizar"].row, 4)
            self.assertTrue(hasattr(apos_primeira, "fichas"))
            self.assertTrue(apos_primeira._nova(1).pode_finalizar)

    def test_relatorio_homenageia_mortos_com_frase_oficial(self) -> None:
        combate = criar_combate(1)
        morto = participante("Perdido", EQUIPE_ALIADOS)
        morto.estado = "morto"
        combate.participantes = [morto]
        encerrar_combate(combate)
        embed = embed_relatorio(combate)
        nomes = [campo.name for campo in embed.fields]
        self.assertIn("🕯️ Honra aos que ficaram, descansem em paz 🕊", nomes)
        self.assertEqual(len(VIDEOS_HOMENAGEM), 4)


class InteracaoCombateTests(unittest.IsolatedAsyncioTestCase):
    async def test_encerrar_turno_confirma_clique_antes_de_atualizar(self) -> None:
        combate = criar_combate(1)
        atual = participante("Atual", EQUIPE_ALIADOS)
        seguinte = participante("Seguinte", EQUIPE_OPONENTES)
        combate.participantes = [atual, seguinte]
        iniciar_combate(combate, lambda: 10)
        response = SimpleNamespace(defer=AsyncMock())
        interaction = SimpleNamespace(
            response=response,
            followup=SimpleNamespace(send=AsyncMock()),
            delete_original_response=AsyncMock(),
        )

        class CogFalso:
            def localizar(self, _):
                return combate, Path("combate.json")

            async def mutar(self, _, operacao):
                self.assert_confirmado()
                operacao(combate)
                return combate

            async def atualizar_mensagem(self, _):
                self.assert_confirmado()

            @staticmethod
            def assert_confirmado():
                if response.defer.await_count != 1:
                    raise AssertionError("O clique deve ser confirmado antes da atualização.")

        view = AcoesCombateView(CogFalso(), 1, combate, combate.participante_atual())
        await view.encerrar_turno(interaction)

        response.defer.assert_awaited_once()
        interaction.delete_original_response.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
