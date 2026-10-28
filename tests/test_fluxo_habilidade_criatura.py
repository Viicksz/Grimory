import unittest

from comandos.ficha_criaturas import (
    ACOES_HABILIDADE,
    ATIVACOES_HABILIDADE,
    CUSTOS_PH_HABILIDADE,
    CATEGORIAS_MODIFICADOR_EFEITO,
    CATEGORIAS_ROLAGEM_ACERTO,
    DADOS_EFEITO,
    MODOS_CUSTO_HABILIDADE,
    TIPOS_DANO_HABILIDADE,
    TIPOS_EFEITO_HABILIDADE,
    NECESSITA_ROLAGEM_EFEITO,
    RESOLUCOES,
    RECARGAS,
    DURACOES,
    ALCANCES,
    ALVOS,
    ConfiguracaoHabilidadeView,
    GerenciarHabilidadesCriaturaView,
    AlcanceHabilidadeView,
    CustoHabilidadeView,
    EfeitoHabilidadeView,
    EscolhaAtributoNovoEfeitoView,
    EscolhaPericiaNovaHabilidadeView,
    HabilidadeBasicaModal,
    ModificadorPersonalizadoModal,
    RolagensHabilidadeView,
    TipoEfeitoHabilidadeView,
    area_padrao,
    alcance_calculado,
    alcances_habilidade,
    aplicar_modo_custo,
    atualizar_efeito_calculado,
    bonus_escolha_criatura,
    configurar_tipo_efeito,
    duracao_por_magia,
    duracao_registrada_base,
    formatar_registro,
    interpretar_modificador_personalizado,
    montar_embeds_habilidades,
    registrar_habilidade_criatura,
)
from utils.fichas_criaturas import FichaCriatura


class FluxoHabilidadeCriaturaTests(unittest.TestCase):
    def setUp(self):
        self.ficha = FichaCriatura("Criatura de teste", "Fera", "XXX", "2 m", "De 1 m a 2 m")

    def item_base(self):
        return {"tipo de ativação": "Ativa", "tipo de ação": "Padrão"}

    def test_primeira_tela_agrupa_ativacao_e_acao(self):
        view = ConfiguracaoHabilidadeView(1, self.ficha)
        self.assertEqual([opcao.value for opcao in view.ativacao_select.options], list(ATIVACOES_HABILIDADE))
        self.assertEqual([opcao.value for opcao in view.acao_select.options], list(ACOES_HABILIDADE))
        self.assertEqual(list(ACOES_HABILIDADE), ["Completa", "Padrão", "Movimento", "Livre", "Bônus", "Reação"])
        self.assertTrue(all(opcao.description for seletor in view.children[:2] for opcao in seletor.options))

    def test_reacao_aparece_preenchida_automaticamente(self):
        view = ConfiguracaoHabilidadeView(1, self.ficha, "Reação", "Reação")
        selecionada = [opcao.value for opcao in view.acao_select.options if opcao.default]
        self.assertEqual(selecionada, ["Reação"])

    def test_gerenciador_permite_adicionar_modificar_e_remover(self):
        self.ficha.habilidades.append({"nome": "Aura"})
        view = GerenciarHabilidadesCriaturaView(1, self.ficha)
        self.assertEqual(
            [item.label for item in view.children],
            ["Adicionar", "Modificar", "Remover", "Voltar"],
        )
        self.assertFalse(view.children[1].disabled)
        self.assertFalse(view.children[2].disabled)

    def test_modificacao_preserva_item_e_substitui_sem_duplicar(self):
        original = {
            "nome": "Aura Antiga",
            "tipo de ativação": "Ativa",
            "tipo de ação": "Padrão",
            "alcance": "Toque",
        }
        self.ficha.habilidades.append(original)
        self.ficha._habilidade_indice_edicao = 0
        self.ficha._habilidade_original_edicao = dict(original)
        view = ConfiguracaoHabilidadeView(
            1, self.ficha, "Ativa", "Padrão", dict(original)
        )
        self.assertEqual(view.item["alcance"], "Toque")
        registrar_habilidade_criatura(self.ficha, {**original, "nome": "Aura Nova"})
        self.assertEqual(len(self.ficha.habilidades), 1)
        self.assertEqual(self.ficha.habilidades[0]["nome"], "Aura Nova")
        self.assertFalse(hasattr(self.ficha, "_habilidade_indice_edicao"))

    def test_modificacao_recusa_lista_alterada(self):
        original = {"nome": "Aura Antiga"}
        self.ficha.habilidades.append(original)
        self.ficha._habilidade_indice_edicao = 0
        self.ficha._habilidade_original_edicao = dict(original)
        self.ficha.habilidades[0] = {"nome": "Alterada em outro fluxo"}
        with self.assertRaises(ValueError):
            registrar_habilidade_criatura(self.ficha, {"nome": "Aura Nova"})

    def test_modal_final_possui_nome_descricao_e_efeito(self):
        modal = HabilidadeBasicaModal(1, self.ficha, self.item_base())
        self.assertEqual(
            [campo.label for campo in modal.children],
            ["Nome", "Descrição", "Efeito"],
        )

    def test_tipo_de_efeito_e_necessidade_de_rolagem_sao_selecionaveis(self):
        view = TipoEfeitoHabilidadeView(1, self.ficha, self.item_base())
        self.assertEqual([opcao.value for opcao in view.tipo_select.options], list(TIPOS_EFEITO_HABILIDADE))
        self.assertEqual([opcao.value for opcao in view.rolagem_select.options], list(NECESSITA_ROLAGEM_EFEITO))
        self.assertEqual([opcao.value for opcao in view.dano_select.options], list(TIPOS_DANO_HABILIDADE))
        self.assertTrue(all(opcao.description for opcao in view.tipo_select.options))
        self.assertTrue(all(opcao.description for opcao in view.rolagem_select.options))
        self.assertTrue(all(opcao.description for opcao in view.dano_select.options))

    def test_tipo_de_dano_e_registrado_na_habilidade(self):
        item = self.item_base()
        configurar_tipo_efeito(item, "Ofensivo", "Sim", "Fogo")
        self.assertEqual(item["tipo de dano"], "Fogo")

    def test_efeito_sem_rolagem_descarta_todos_os_dados(self):
        item = {
            **self.item_base(),
            "dado de efeito": "d8",
            "número de dados": "2",
            "modificador de efeito": "Magia +3",
            "efeito calculado": "2d8+3 (Magia)",
        }
        configurar_tipo_efeito(item, "Utilitário", "Não")
        self.assertEqual(item["tipo de efeito"], "Utilitário")
        self.assertEqual(item["tipo de dano"], "Nenhum")
        self.assertEqual(item["necessita de rolagem"], "Não")
        for campo in ("dado de efeito", "número de dados", "modificador de efeito", "efeito calculado"):
            self.assertNotIn(campo, item)

    def test_segunda_tela_agrupa_alcance_alvo_duracao_e_recarga(self):
        view = AlcanceHabilidadeView(1, self.ficha, self.item_base())
        self.assertEqual([opcao.value for opcao in view.alcance_select.options], list(alcances_habilidade(self.ficha)))
        self.assertEqual([opcao.value for opcao in view.alvo_select.options], list(ALVOS))
        self.assertEqual([opcao.value for opcao in view.duracao_select.options], list(DURACOES))
        self.assertEqual([opcao.value for opcao in view.recarga_select.options], list(RECARGAS))
        self.assertIn("Sustentado", DURACOES)
        self.assertTrue(all(opcao.description for opcao in view.recarga_select.options))

    def test_modo_de_custo_vem_antes_e_so_exibe_ph_quando_necessario(self):
        view = CustoHabilidadeView(1, self.ficha, self.item_base())
        self.assertEqual([opcao.value for opcao in view.modo_select.options], list(MODOS_CUSTO_HABILIDADE))
        self.assertIsNone(view.custo_select)
        self.assertEqual(view.children[0].placeholder, "Modo de Custo")
        com_custo = CustoHabilidadeView(
            1, self.ficha, self.item_base(), "4", "Ativação"
        )
        self.assertEqual(com_custo.children[0].placeholder, "Modo de Custo")
        self.assertEqual(com_custo.children[1].placeholder, "Custo de PH")
        self.assertEqual(
            [opcao.value for opcao in com_custo.custo_select.options],
            list(CUSTOS_PH_HABILIDADE),
        )
        self.assertEqual(MODOS_CUSTO_HABILIDADE, ("Ativação", "Turno/Rodada Sustentada", "Acúmulo", "Sem Custo"))

    def test_sem_custo_define_zero_ph_automaticamente(self):
        item = {**self.item_base(), "custo de PH": "8"}
        aplicar_modo_custo(item, self.ficha, "Sem Custo")
        self.assertEqual(item["modo de custo"], "Sem Custo")
        self.assertEqual(item["custo de PH"], "0")
        self.assertEqual(item["mecânica de custo"], "Sem custo de PH.")

    def test_quarta_tela_agrupa_as_tres_rolagens(self):
        view = RolagensHabilidadeView(1, self.ficha, self.item_base())
        self.assertEqual([opcao.value for opcao in view.acerto_select.options], list(CATEGORIAS_ROLAGEM_ACERTO))
        self.assertEqual([opcao.value for opcao in view.resistencia_select.options], ["Reflexo", "Fortitude", "Vontade", "Nenhuma"])
        self.assertEqual([opcao.value for opcao in view.reacao_select.options], list(RESOLUCOES))
        self.assertIn("Teste Oposto", RESOLUCOES)

    def test_duracao_usa_um_mais_modificador_de_magia(self):
        self.ficha.atributos["Magia"] = 16
        self.assertEqual(DURACOES, ("Instantâneo", "Turno", "Rodada", "Sustentado"))
        self.assertEqual(duracao_por_magia(self.ficha, "Instantâneo"), "Instantâneo")
        self.assertEqual(duracao_por_magia(self.ficha, "Turno"), "4 turno(s)")
        self.assertEqual(duracao_por_magia(self.ficha, "Rodada"), "4 rodada(s)")
        self.assertEqual(duracao_por_magia(self.ficha, "Sustentado"), "Sustentado")

    def test_area_calcula_tamanho_e_magia_vezes_periculosidade(self):
        self.assertEqual(
            area_padrao(self.ficha),
            "Qualquer criatura numa área de 6 m de raio ([tamanho exato + modificador de Magia] × periculosidade).",
        )

    def test_pixie_xxxx_com_magia_16_possui_raio_de_12_8_metros(self):
        pixie = FichaCriatura("Pixie", "Ser", "XXXX", "20 cm", "Menos de 50 cm")
        pixie.atributos["Magia"] = 16
        self.assertEqual(alcance_calculado(pixie), "Até 12,8 m")
        self.assertIn("12,8 m de raio", area_padrao(pixie))
        self.assertEqual(alcances_habilidade(pixie)[3], "Até 12,8 m")

    def test_ficha_exibe_alcance_e_alvo_separados(self):
        texto = formatar_registro({"nome": "Aura", "alcance": "Campo de Visão", "alvo": "Individual"})
        self.assertIn("**Alcance:** Campo de Visão", texto)
        self.assertIn("**Alvo:** Individual", texto)

    def test_campos_de_acerto_e_efeito_seguem_limite_da_periculosidade(self):
        view = EfeitoHabilidadeView(1, self.ficha, self.item_base())
        self.assertEqual([opcao.value for opcao in view.dado_select.options], list(DADOS_EFEITO))
        self.assertEqual([opcao.value for opcao in view.numero_select.options], ["1", "2", "3", "4", "5", "6"])
        self.assertEqual([opcao.value for opcao in view.modificador_select.options], list(CATEGORIAS_MODIFICADOR_EFEITO))
        personalizada = next(
            opcao for opcao in view.modificador_select.options
            if opcao.value == "Personalizado"
        )
        self.assertIn("valor numérico", personalizada.description)

    def test_modificador_personalizado_soma_valor_puro_ao_efeito(self):
        self.assertIn("Personalizado", CATEGORIAS_MODIFICADOR_EFEITO)
        self.assertEqual(interpretar_modificador_personalizado("+5"), 5)
        self.assertEqual(interpretar_modificador_personalizado(" - 3 "), -3)
        with self.assertRaisesRegex(ValueError, "número inteiro"):
            interpretar_modificador_personalizado("1d4")

        item = {"dado de efeito": "d8", "número de dados": "4"}
        atualizar_efeito_calculado(item, self.ficha, "Personalizado +5")
        self.assertEqual(item["modificador de efeito"], "Personalizado +5")
        self.assertEqual(item["efeito calculado"], "4d8+5 (Personalizado)")

        modal = ModificadorPersonalizadoModal(
            1,
            self.ficha,
            {"modificador de efeito": "Personalizado -3"},
            "d8",
            "4",
        )
        self.assertEqual(modal.valor.label, "Valor somativo puro")
        self.assertEqual(modal.valor.default, "-3")

    def test_bonus_de_magia_e_pericia_e_calculado(self):
        self.ficha.atributos["Magia"] = 16
        self.ficha.atributos["Sabedoria"] = 16
        self.ficha.pericias["Percepção"] = 2
        self.assertEqual(bonus_escolha_criatura(self.ficha, "Magia"), 3)
        self.assertEqual(bonus_escolha_criatura(self.ficha, "Percepção"), 5)

    def test_efeito_calculado_aceita_modificador_pericia_ou_nulo(self):
        self.ficha.atributos["Magia"] = 16
        item = {"dado de efeito": "d8", "número de dados": "4"}
        atualizar_efeito_calculado(item, self.ficha, "Magia")
        self.assertEqual(item["efeito calculado"], "4d8+3 (Magia)")
        atualizar_efeito_calculado(item, self.ficha, "Nulo")
        self.assertEqual(item["efeito calculado"], "4d8")

    def test_pericias_e_modificadores_abrem_selecoes_guiadas(self):
        item = {"nome": "Rajada", "tipo de ativação": "Ativa"}
        pericias = EscolhaPericiaNovaHabilidadeView(1, self.ficha, item, "acerto", {"resistencia": "", "reacao": ""})
        atributos = EscolhaAtributoNovoEfeitoView(1, self.ficha, item, "d8", "2")
        self.assertTrue(pericias.seletor.options)
        self.assertTrue(all(opcao.description for opcao in pericias.seletor.options))
        self.assertEqual(len(atributos.seletor.options), 7)
        self.assertTrue(all(opcao.description for opcao in atributos.seletor.options))

    def test_embed_da_habilidade_condensa_custo_descricao_e_efeito(self):
        texto = formatar_registro({
            "nome": "Rajada",
            "descrição": "Uma descarga concentrada.",
            "efeito": "Causa dano mágico ao alvo.",
            "tipo de ativação": "Ativa",
            "custo de PH": "4",
            "modo de custo": "Ativação",
            "mecânica de custo": "Custa 4 PH por ativação.",
            "rolagem de reação": "Teste Oposto",
            "dado de efeito": "d8",
            "número de dados": "2",
            "modificador de efeito": "Magia +3",
            "efeito calculado": "2d8+3 (Magia)",
        })
        self.assertTrue(texto.startswith("**Rajada**\n*Uma descarga concentrada.*\n`Causa dano mágico ao alvo.`\n"))
        self.assertNotIn("**Descrição:**", texto)
        self.assertNotIn("**Custo de PH:**", texto)
        self.assertNotIn("**Modo de Custo:**", texto)
        self.assertIn("**Mecânica de custo:** Custa 4 PH por ativação.", texto)
        self.assertIn("**Rolagem de Reação:** Teste Oposto", texto)
        self.assertNotIn("**Dado de Efeito:**", texto)
        self.assertNotIn("**Número de Dados:**", texto)
        self.assertNotIn("**Modificador de Efeito:**", texto)
        self.assertNotIn("**Efeito Calculado:**", texto)
        self.assertIn("**Rolagem de Efeito:** 2d8+3 (Magia)", texto)

    def test_habilidades_usam_cabecalho_largo_e_demais_campos_inline(self):
        embeds = montar_embeds_habilidades([{
            "nome": "Rajada",
            "descrição": "Uma descarga concentrada.",
            "efeito": "Causa dano mágico ao alvo.",
            "tipo de ativação": "Ativa",
            "tipo de ação": "Padrão",
            "mecânica de custo": "Custa 4 PH por ativação.",
            "tipo de efeito": "Ofensivo",
            "tipo de dano": "Magia",
            "necessita de rolagem": "Sim",
            "efeito calculado": "2d8+3 (Magia)",
        }])
        self.assertEqual(len(embeds), 1)
        self.assertEqual(embeds[0].fields[0].name, "Rajada")
        self.assertFalse(embeds[0].fields[0].inline)
        self.assertEqual(embeds[0].fields[0].value, "*Uma descarga concentrada.*\n`Causa dano mágico ao alvo.`")
        self.assertTrue(all(campo.inline for campo in embeds[0].fields[1:]))
        self.assertTrue(any(campo.name == "Tipo de Dano" and campo.value == "Magia" for campo in embeds[0].fields))
        self.assertEqual(embeds[0].fields[-1].name, "Rolagem de Efeito")


if __name__ == "__main__":
    unittest.main()
