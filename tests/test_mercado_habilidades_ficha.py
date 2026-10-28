import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from comandos.ficha import (
    AnoMestriaFeiticoMercadoView,
    CategoriaMestriaFeiticoMercadoView,
    FichaAtualView,
    acoes_ph_habilidade,
    aplicar_compra,
    aplicar_mecanica_habilidade,
    aplicar_mecanica_heranca,
    aplicar_mecanica_sangue_puro,
    aplicar_uso_ph_habilidade,
    bonus_aptidoes_heranca,
    custo_aprimorar_aptidao,
    custo_subir_nivel,
    habilidades_disponiveis_mercado,
    ano_desbloqueio_mestria,
    listar_feiticos_mestria,
    montar_embeds_ficha,
    nome_mestria_feitico,
    MestriaFeiticoMercadoView,
    total_evolucoes_heranca,
)
from utils.efeitos_habilidades import aptidao_efetiva, bonus_pericias_passivos
from utils.fichas import FichaPersonagem, atributos_efetivos


def ficha_teste(**alteracoes) -> FichaPersonagem:
    dados = {
        "nome": "Teste",
        "grupo": "Players",
        "casa": "Sonserina",
        "heranca": "Parte-Vampiro",
        "nucleo": "Coração de Dragão",
        "xp": 1000,
    }
    dados.update(alteracoes)
    return FichaPersonagem(**dados)


class MercadoHabilidadesFichaTests(unittest.TestCase):
    def test_conta_as_cinco_evolucoes_da_heranca(self):
        self.assertEqual(total_evolucoes_heranca("Parte-Vampiro"), 5)

    def test_nao_compra_heranca_totalmente_desbloqueada(self):
        ficha = ficha_teste(evolucao_heranca=5)

        with self.assertRaisesRegex(ValueError, "totalmente desbloqueada"):
            aplicar_compra(ficha, "heranca", ficha.heranca, 6)

        self.assertEqual(ficha.evolucao_heranca, 5)

    def test_habilidades_possuidas_nao_aparecem_novamente(self):
        ficha = ficha_teste(origens_magicas=["Clarividência"])

        disponiveis = habilidades_disponiveis_mercado(ficha, "origem_magica")

        self.assertNotIn("Clarividência", disponiveis)

    def test_nao_compra_habilidade_duplicada_com_variacao_de_escrita(self):
        ficha = ficha_teste(origens_magicas=["CLARIVIDENCIA"])

        with self.assertRaisesRegex(ValueError, "já possui"):
            aplicar_compra(ficha, "origem", "Clarividência", 0)

        self.assertEqual(ficha.origens_magicas, ["CLARIVIDENCIA"])

    def test_experiencia_alquimica_compra_origem_pela_metade(self):
        ficha = ficha_teste(origens_magicas=[])

        custo = aplicar_compra(
            ficha,
            "experiencia_alquimica_origem",
            "Clarividência",
            0,
        )

        self.assertEqual(custo, 75)
        self.assertIn("Experiência Alquímica", ficha.origens_magicas)
        self.assertIn("Clarividência", ficha.origens_magicas)
        self.assertEqual(ficha.escolha_experiencia_alquimica, "Origem Mágica")

    def test_experiencia_alquimica_exige_escolher_uma_situacao(self):
        ficha = ficha_teste(origens_magicas=[])
        with self.assertRaisesRegex(ValueError, "Escolha primeiro"):
            aplicar_compra(ficha, "origem", "Experiência Alquímica", 0)

    def test_experiencia_alquimica_evolui_heranca_e_mantem_metade_do_custo(self):
        ficha = ficha_teste(
            heranca="Sangue Puro",
            evolucao_heranca=0,
            origens_magicas=[],
        )
        self.assertEqual(
            aplicar_compra(
                ficha,
                "experiencia_alquimica_heranca",
                "Sangue Puro",
                1,
            ),
            10,
        )
        self.assertEqual(ficha.evolucao_heranca, 1)
        self.assertEqual(ficha.escolha_experiencia_alquimica, "Herança Sanguínea")
        self.assertEqual(aplicar_compra(ficha, "heranca", "Sangue Puro", 2), 10)

    def test_mestria_escolhe_um_feitico_real_e_permite_outros(self):
        referencias = listar_feiticos_mestria()
        self.assertTrue(referencias)
        self.assertTrue(all("feitiços" in str(ref.caminho.parent).casefold() for ref in referencias))
        referencia = referencias[0]
        nome = nome_mestria_feitico(referencia.nome)
        ficha = ficha_teste(especializacoes=[])

        custo = aplicar_compra(ficha, "especializacao", nome, 0)

        self.assertEqual(custo, 20)
        self.assertIn(nome, ficha.especializacoes)
        self.assertNotIn(referencia.nome, [ref.nome for ref in listar_feiticos_mestria(ficha)])
        self.assertIn("Mestria em (Nome do Feitiço)", habilidades_disponiveis_mercado(ficha, "especializacao"))

    def test_nao_compra_duas_vezes_a_mestria_do_mesmo_feitico(self):
        referencia = listar_feiticos_mestria()[0]
        nome = nome_mestria_feitico(referencia.nome)
        ficha = ficha_teste(especializacoes=[nome])
        with self.assertRaisesRegex(ValueError, "já possui"):
            aplicar_compra(ficha, "especializacao", nome, 0)

    def test_seletor_de_mestria_usa_categoria_ano_e_feitico(self):
        referencias = listar_feiticos_mestria()
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Teste.md"
            caminho.write_text(ficha_teste().markdown(), encoding="utf-8")
            categorias = CategoriaMestriaFeiticoMercadoView(
                1, caminho, referencias
            )
            rotulos_categorias = [opcao.label for opcao in categorias.seletor.options]
            self.assertIn("Encantamentos", rotulos_categorias)
            self.assertNotIn("AB", rotulos_categorias)

            anos = AnoMestriaFeiticoMercadoView(
                1, caminho, referencias, "Encantamentos"
            )
            rotulos_anos = [opcao.label for opcao in anos.seletor.options]
            self.assertEqual(rotulos_anos[:7], [f"{ano}º Ano" for ano in range(1, 8)])

            categorias_trevas = AnoMestriaFeiticoMercadoView(
                1, caminho, referencias, "Arte das Trevas"
            )
            rotulos_trevas = [
                opcao.label for opcao in categorias_trevas.seletor.options
            ]
            self.assertIn("Imperdoáveis", rotulos_trevas)
            self.assertIn("Maldições", rotulos_trevas)
            self.assertNotIn("1º Ano", rotulos_trevas)
            self.assertEqual(
                categorias_trevas.seletor.placeholder,
                "Categoria de Arte das Trevas",
            )

            referencias_primeiro_ano = [
                referencia
                for referencia in referencias
                if referencia.categoria == "Encantamentos"
                and ano_desbloqueio_mestria(referencia) == "1º Ano"
            ]
            feiticos = MestriaFeiticoMercadoView(
                1,
                caminho,
                referencias,
                "Encantamentos",
                "1º Ano",
                referencias_primeiro_ano,
                0,
            )
        self.assertTrue(feiticos.seletor_feitico.options)
        self.assertTrue(
            all(
                "Encantamentos • 1º Ano" == opcao.description
                for opcao in feiticos.seletor_feitico.options
            )
        )


class MercadoSemImagemTests(unittest.IsolatedAsyncioTestCase):
    async def test_abrir_mercado_remove_o_anexo_da_imagem(self):
        ficha = ficha_teste(
            imagens=[
                {
                    "titulo": "Aparência",
                    "arquivo": "biblioteca/fichas/imagens/teste/aparencia.webp",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Teste.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            view = FichaAtualView(1, caminho)
            botao = next(item for item in view.children if item.label == "Mercado de XP")
            interaction = SimpleNamespace(
                response=SimpleNamespace(edit_message=AsyncMock())
            )

            await botao.callback(interaction)

        argumentos = interaction.response.edit_message.await_args.kwargs
        self.assertEqual(argumentos["attachments"], [])
        self.assertEqual(argumentos["embed"].title, "🛒 Mercado de XP")


class MecanicasSanguePuroTests(unittest.TestCase):
    def sangue_puro(self, evolucao: int, **alteracoes) -> FichaPersonagem:
        return ficha_teste(
            heranca="Sangue Puro",
            evolucao_heranca=evolucao,
            **alteracoes,
        )

    def test_habilidade_inicial_concede_historia_da_magia(self):
        self.assertEqual(
            bonus_aptidoes_heranca("Sangue Puro"),
            {"História da Magia": 4},
        )

    def test_primeira_evolucao_registra_maestria_com_dois_xp(self):
        ficha = self.sangue_puro(1, xp=30)
        aplicar_mecanica_sangue_puro(ficha, "maestria")
        self.assertEqual(ficha.xp, 32)

    def test_segunda_evolucao_reduz_dez_xp_da_aptidao(self):
        antes = self.sangue_puro(1)
        depois = self.sangue_puro(2)
        self.assertEqual(custo_aprimorar_aptidao(antes, 3), 60)
        self.assertEqual(custo_aprimorar_aptidao(depois, 3), 50)
        self.assertEqual(aplicar_compra(depois, "aptidao", "Duelos", 1), 10)

    def test_terceira_evolucao_aplica_bonus_cumulativo_e_gasta_xp(self):
        ficha = self.sangue_puro(3, xp=50)
        aplicar_mecanica_sangue_puro(ficha, "atributo", "Destreza")
        aplicar_mecanica_sangue_puro(ficha, "atributo", "Destreza")
        self.assertEqual(ficha.xp, 30)
        self.assertEqual(ficha.bonus_atributos_temporarios["Destreza"], 4)
        self.assertEqual(atributos_efetivos(ficha)["Destreza"], 14)
        atributos = next(
            embed for embed in montar_embeds_ficha(ficha)
            if embed.title == "📌 Atributos"
        )
        self.assertIn("+4 temporário", atributos.description)

    def test_encerrar_cena_remove_bonus_sem_devolver_xp(self):
        ficha = self.sangue_puro(3, xp=50)
        aplicar_mecanica_sangue_puro(ficha, "atributo", "Força")
        aplicar_mecanica_sangue_puro(ficha, "encerrar_cena")
        self.assertEqual(ficha.xp, 40)
        self.assertFalse(any(ficha.bonus_atributos_temporarios.values()))

    def test_quarta_evolucao_reduz_vinte_e_cinco_xp_do_nivel(self):
        antes = self.sangue_puro(3, nivel=4)
        depois = self.sangue_puro(4, nivel=4)
        self.assertEqual(custo_subir_nivel(antes), 250)
        self.assertEqual(custo_subir_nivel(depois), 225)

    def test_ultima_evolucao_prepara_e_consumo_reducao(self):
        ficha = self.sangue_puro(5, xp=30)
        aplicar_mecanica_sangue_puro(ficha, "reducao", "Intermediário")
        aplicar_mecanica_sangue_puro(ficha, "reducao", "Avançado")
        self.assertEqual(ficha.xp, 15)
        self.assertEqual(ficha.reducoes_dificuldade_heranca["Intermediário"], 1)
        self.assertEqual(ficha.reducoes_dificuldade_heranca["Avançado"], 1)
        aplicar_mecanica_sangue_puro(
            ficha,
            "consumir_reducao",
            "Intermediário",
        )
        self.assertEqual(ficha.reducoes_dificuldade_heranca["Intermediário"], 0)

    def test_efeitos_persistem_e_heranca_sai_dos_botoes_da_ficha(self):
        ficha = self.sangue_puro(5, xp=30)
        aplicar_mecanica_sangue_puro(ficha, "atributo", "Carisma")
        aplicar_mecanica_sangue_puro(ficha, "reducao", "Avançado")
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Sangue Puro.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            carregada = FichaPersonagem.carregar(caminho)
            botoes = {item.label for item in FichaAtualView(1, caminho).children}
        self.assertEqual(carregada.bonus_atributos_temporarios["Carisma"], 2)
        self.assertEqual(carregada.reducoes_dificuldade_heranca["Avançado"], 1)
        self.assertNotIn("Herança", botoes)

    def test_nao_permite_ativar_evolucao_ainda_bloqueada(self):
        ficha = self.sangue_puro(2, xp=100)
        with self.assertRaisesRegex(ValueError, "Terceira Evolução"):
            aplicar_mecanica_sangue_puro(ficha, "atributo", "Força")
        with self.assertRaisesRegex(ValueError, "Última Evolução"):
            aplicar_mecanica_sangue_puro(ficha, "reducao", "Avançado")


class AuditoriaMecanicasHabilidadesTests(unittest.TestCase):
    def test_experiencia_alquimica_mostra_os_tres_niveis_na_ficha(self):
        ficha = ficha_teste(
            origens_magicas=["Experiência Alquímica"],
            escolha_experiencia_alquimica="Herança Sanguínea",
        )
        habilidades = next(
            embed for embed in montar_embeds_ficha(ficha)
            if embed.title == "💡 Habilidades"
        )
        efeitos = "\n".join(
            campo.value
            for campo in habilidades.fields
            if campo.name.startswith("✨ Experiência Alquímica")
        )
        nomes = {campo.name for campo in habilidades.fields}
        self.assertIn("✨ Experiência Alquímica — Passivo", nomes)
        self.assertIn("✨ Experiência Alquímica — Primeiro Nível", nomes)
        self.assertIn("1d4+2 de dano degenerativo", efeitos)
        self.assertIn("✨ Experiência Alquímica — Segundo Nível", nomes)
        self.assertIn("2d4+2 de dano degenerativo", efeitos)
        self.assertIn("✨ Experiência Alquímica — Terceiro Nível", nomes)
        self.assertIn("2d6+4 de dano degenerativo", efeitos)

    def test_todas_as_habilidades_possuidas_mostram_seus_efeitos_oficiais(self):
        ficha = ficha_teste(
            heranca="Sangue Veela",
            especializacoes=[
                "Prodígio do Quadribol",
                "Magia Não-Verbal",
                "Magia Manual",
            ],
        )
        habilidades = next(
            embed for embed in montar_embeds_ficha(ficha)
            if embed.title == "💡 Habilidades"
        )
        campos = {campo.name: campo.value for campo in habilidades.fields}
        self.assertIn("🧬 Sangue Veela — Habilidade Inicial — Passivo", campos)
        self.assertIn("🎓 Prodígio do Quadribol", campos)
        self.assertIn("🎓 Magia Não-Verbal", campos)
        self.assertIn("🎓 Magia Manual", campos)
        self.assertIn("+2 em testes de acordo com a sua posição", campos["🎓 Prodígio do Quadribol"])
        self.assertIn("sem que o encantamento seja dito em voz alta", campos["🎓 Magia Não-Verbal"])
        self.assertIn("canalizar a energia mágica pelas mãos", campos["🎓 Magia Manual"])
        self.assertIn("\n> **Custo de PH:**", campos["🎓 Magia Manual"])
        self.assertNotIn("\n\n**Custo de PH:**", campos["🎓 Magia Manual"])

    def test_ano_familiar_e_patrono_usam_as_informacoes_como_base(self):
        ficha = ficha_teste(
            ano="--",
            familiar="--",
            patronum="--",
            informacoes=[
                {"titulo": "Cursando", "descricao": "3°Ano"},
                {"titulo": "Familiar", "descricao": "Coruja chamada Lua"},
                {"titulo": "Patronum", "descricao": "Lobo"},
            ],
        )
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Base.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            carregada = FichaPersonagem.carregar(caminho)
        self.assertEqual(carregada.ano, "3°Ano")
        self.assertEqual(carregada.familiar, "Coruja chamada Lua")
        self.assertEqual(carregada.patronum, "Lobo")
        self.assertIn("Patrono", {item["titulo"] for item in carregada.informacoes})

    def test_cada_modificador_automatico_recebe_engrenagem(self):
        ficha = ficha_teste(
            heranca="Sangue Puro",
            evolucao_heranca=4,
        )
        habilidades = next(
            embed for embed in montar_embeds_ficha(ficha)
            if embed.title == "💡 Habilidades"
        )
        self.assertIn(
            "> ⚙️ **Aprimorar aptidões:** -10 XP em cada compra.",
            habilidades.description,
        )
        self.assertIn(
            "> ⚙️ **Subir de nível:** -25 XP em todos os próximos níveis.",
            habilidades.description,
        )

    def test_consulta_da_ficha_nao_oferece_execucao_de_mecanicas(self):
        ficha = ficha_teste(
            especializacoes=["Bom de Briga", "Valente"],
            origens_magicas=["Licantropia"],
        )
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Consulta.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            botoes = {item.label for item in FichaAtualView(1, caminho).children}
        self.assertNotIn("Mecânicas", botoes)

    def test_descontos_compartilhados_pelas_tres_herancas(self):
        for heranca in ("Meio-Sangue", "Nascido-Trouxa", "Sangue Puro"):
            ficha = ficha_teste(heranca=heranca, evolucao_heranca=4, nivel=3)
            self.assertEqual(custo_aprimorar_aptidao(ficha, 2), 30)
            self.assertEqual(custo_subir_nivel(ficha), 175)

    def test_eventos_das_outras_linhagens_concedem_xp(self):
        for heranca in ("Meio-Sangue", "Nascido-Trouxa"):
            ficha = ficha_teste(heranca=heranca, evolucao_heranca=1, xp=10)
            aplicar_mecanica_heranca(ficha, "evento")
            self.assertEqual(ficha.xp, 12)

    def test_ultimas_evolucoes_registram_efeitos(self):
        meio = ficha_teste(heranca="Meio-Sangue", evolucao_heranca=5, xp=20)
        aplicar_mecanica_heranca(meio, "catalisador")
        self.assertEqual(meio.xp, 15)
        self.assertEqual(meio.efeitos_habilidades_ativos[0]["duracao"], "1d4+1 rodadas")

        trouxa = ficha_teste(heranca="Nascido-Trouxa", evolucao_heranca=5, xp=20)
        aplicar_mecanica_heranca(trouxa, "especializacao_improvisada", "Sortudo")
        self.assertEqual(trouxa.xp, 15)
        self.assertIn("Sortudo", trouxa.efeitos_habilidades_ativos[0]["nome"])

    def test_bonus_passivo_de_aptidao_entra_no_total_sem_globalizar_condicional(self):
        ficha = ficha_teste(
            origens_magicas=["Licantropia", "Sacrifício à Mimir"],
        )
        self.assertEqual(bonus_pericias_passivos(ficha), {})
        self.assertEqual(aptidao_efetiva(ficha, "Runas Antigas"), 2)
        self.assertEqual(custo_aprimorar_aptidao(ficha, 1, "Runas Antigas"), 60)

    def test_experiencia_alquimica_de_origem_nao_reduz_compras_futuras(self):
        ficha = ficha_teste(
            origens_magicas=["Experiência Alquímica"],
            escolha_experiencia_alquimica="Origem Mágica",
            xp=500,
        )
        custo = aplicar_compra(ficha, "origem", "Licantropia", 0)
        self.assertEqual(custo, 150)

    def test_parser_cobre_acoes_das_tres_categorias(self):
        self.assertTrue(acoes_ph_habilidade("heranca_sanguinea", "Maledictus"))
        self.assertEqual(
            [acao["custos"] for acao in acoes_ph_habilidade("origem_magica", "Licantropia")],
            [[2], [4], [6]],
        )
        self.assertEqual(
            acoes_ph_habilidade("especializacao", "Magizoologista Nato")[0]["custos"],
            [2, 4, 6, 8],
        )

    def test_usar_habilidade_desconta_ph_e_devorador_concede_xp(self):
        ficha = ficha_teste(
            ph=10,
            xp=20,
            especializacoes=["Devorador de Livros"],
        )
        aplicar_uso_ph_habilidade(
            ficha,
            "especializacao",
            "Devorador de Livros",
            "Devorador de Livros",
            2,
        )
        self.assertEqual((ficha.ph, ficha.xp), (8, 22))

    def test_prodigio_so_aplica_bonus_depois_de_ativado(self):
        ficha = ficha_teste(ph=7, especializacoes=["Prodígio do Quadribol"])
        aplicar_uso_ph_habilidade(
            ficha,
            "especializacao",
            "Prodígio do Quadribol",
            "Prodígio do Quadribol",
            2,
        )
        self.assertEqual(ficha.ph, 5)
        self.assertEqual(ficha.efeitos_habilidades_ativos[0]["nome"], "Prodígio do Quadribol")

    def test_habil_experiente_e_contato_visual_alteram_ficha(self):
        ficha = ficha_teste(
            ph=0,
            xp=30,
            alma=100,
            especializacoes=["Hábil e Experiente"],
            origens_magicas=["Magia por Contato Visual"],
        )
        aplicar_mecanica_habilidade(ficha, "alma_contato_visual", "4")
        self.assertEqual(ficha.alma, 96)
        aplicar_mecanica_habilidade(ficha, "xp_para_ph")
        self.assertEqual((ficha.xp, ficha.ph), (20, 1))


if __name__ == "__main__":
    unittest.main()
