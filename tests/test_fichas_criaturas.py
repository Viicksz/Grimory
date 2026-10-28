import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.fichas_criaturas import (
    FichaCriatura,
    PONTOS_ATRIBUTO,
    ReferenciaCriatura,
    ReferenciaFichaCriatura,
    dano_arma_natural,
    efeito_dano,
    passos_dano_por_tamanho,
    somar_atributo_ao_dano,
    tamanho_em_metros,
    tamanho_pertence_a_faixa,
    validar_e_normalizar_tamanho,
)
from comandos.ficha_criaturas import (
    ATRIBUTO_MAXIMO_CRIATURA,
    ARMAS_POR_TIPO,
    AtributosCriaturaView,
    ConfirmarCriaturaView,
    ConsultaAlfabeticaCriaturaView,
    ConsultaPericulosidadeCriaturaView,
    EditorCriaturaView,
    FaixaTamanhoBibliotecaView,
    GerenciarRegistrosCriaturaView,
    TamanhoCriaturaModal,
    TipoEfeitoView,
    registrar_item_criatura,
)


class FichaCriaturaTests(unittest.TestCase):
    def test_consulta_navega_por_periculosidade_e_faixa_alfabetica(self):
        referencias = [
            ReferenciaFichaCriatura("Lucas", "XXX", Path("XXX/Lucas.md")),
            ReferenciaFichaCriatura("Teste", "XXXX", Path("XXXX/Teste.md")),
        ]
        with patch(
            "comandos.ficha_criaturas.listar_fichas_criaturas",
            return_value=referencias,
        ):
            categorias = ConsultaPericulosidadeCriaturaView(1)
            faixa = ConsultaAlfabeticaCriaturaView(1, "XXXX", 9)
        self.assertEqual(
            [opcao.label for opcao in categorias.seletor.options],
            ["X", "XX", "XXX", "XXXX", "XXXXX"],
        )
        self.assertIn("1 ficha", categorias.seletor.options[2].description)
        self.assertIn("1 ficha", categorias.seletor.options[3].description)
        self.assertEqual(len(faixa.faixas.options), 12)
        self.assertEqual(faixa.faixas.options[9].label, "ST")
        self.assertEqual(faixa.fichas.options[0].label, "Teste")
        self.assertEqual(
            faixa.children[-1].label,
            "Voltar às periculosidades",
        )

    def test_consulta_oferece_editor_e_confirmacao_de_alteracoes(self):
        ficha = FichaCriatura("Teste", "Fera", "X", "1 m", "De 1 m a 2 m")
        ficha._caminho_edicao = Path("Teste.md")
        ficha._conteudo_original_edicao = ficha.markdown()

        editor = EditorCriaturaView(1, ficha)
        confirmacao = ConfirmarCriaturaView(1, ficha)

        self.assertEqual(
            [item.label for item in editor.children],
            ["Armas", "Ataque", "Habilidade", "Fraqueza", "Resistência", "Prévia"],
        )
        self.assertEqual(confirmacao.children[0].label, "Salvar alterações")

    def test_armas_e_ataques_possuem_adicao_modificacao_e_remocao(self):
        ficha = FichaCriatura("Teste", "Fera", "X", "1 m", "De 1 m a 2 m")
        ficha.armas_naturais.append({"nome": "Garras"})
        ficha.ataques.append({"nome": "Bote"})
        for tipo in ("arma", "ataque"):
            view = GerenciarRegistrosCriaturaView(1, ficha, tipo)
            self.assertEqual(
                [item.label for item in view.children],
                ["Adicionar", "Modificar", "Remover", "Voltar"],
            )
            self.assertFalse(view.children[1].disabled)
            self.assertFalse(view.children[2].disabled)

    def test_modificar_ataque_substitui_sem_duplicar(self):
        ficha = FichaCriatura("Teste", "Fera", "X", "1 m", "De 1 m a 2 m")
        original = {"nome": "Bote", "tipo de ação": "Completa"}
        ficha.ataques.append(original)
        ficha._ataque_indice_edicao = 0
        ficha._ataque_original_edicao = dict(original)
        registrar_item_criatura(
            ficha, "ataque", {"nome": "Bote", "tipo de ação": "Padrão"}
        )
        self.assertEqual(len(ficha.ataques), 1)
        self.assertEqual(ficha.ataques[0]["tipo de ação"], "Padrão")

    def test_pontos_de_atributo_por_periculosidade(self):
        self.assertEqual(
            PONTOS_ATRIBUTO,
            {"X": 10, "XX": 14, "XXX": 18, "XXXX": 22, "XXXXX": 26},
        )

    def test_atributos_de_criatura_podem_chegar_a_30(self):
        ficha = FichaCriatura("Teste", "Fera", "XXXXX", "2 m", "De 1 m a 2 m")
        ficha.atributos["Força"] = ATRIBUTO_MAXIMO_CRIATURA
        view = AtributosCriaturaView(1, ficha)
        botao_aumentar_forca = next(
            item for item in view.children
            if getattr(item, "atributo", "") == "Força" and getattr(item, "delta", 0) == 1
        )
        self.assertEqual(ATRIBUTO_MAXIMO_CRIATURA, 30)
        self.assertTrue(botao_aumentar_forca.disabled)

    def test_calcula_pv_e_ph_por_periculosidade(self):
        ficha = FichaCriatura(
            "Basilisco de teste", "Fera", "XXXXX", "15 m", "Acima de 10 m"
        )
        self.assertEqual(ficha.pv, 80)
        self.assertEqual(ficha.ph, 25)

    def test_pixie_pequena_com_constituicao_base_tem_15_pv(self):
        ficha = FichaCriatura(
            "Pixie de teste", "Fera", "XXXX", "20 cm", "Menos de 50 cm"
        )
        self.assertEqual(ficha.atributos["Constituição"], 10)
        self.assertEqual(ficha.pv, 15)

    def test_modificador_de_constituicao_escala_com_periculosidade(self):
        ficha = FichaCriatura(
            "Criatura resistente", "Fera", "XXX", "1,5 m", "De 1 m a 2 m"
        )
        ficha.atributos["Constituição"] = 14
        self.assertEqual(ficha.pv, 40)

    def test_ph_mantem_valor_minimo(self):
        ficha = FichaCriatura("Sem magia", "Fera", "XXX", "2 m", "De 1 m a 2 m")
        ficha.atributos["Magia"] = 4
        self.assertEqual(ficha.ph, 6)

    def test_diferencia_dobro_de_dados_e_resultado(self):
        self.assertEqual(efeito_dano("XXXX", True), "Recebe o dobro dos dados de dano.")
        self.assertEqual(efeito_dano("XXXXX", True), "Recebe o dobro do resultado final do dano.")

    def test_arma_natural_sobe_por_periculosidade_e_tamanho(self):
        self.assertEqual(dano_arma_natural("1d4+FOR", "X", "2 m"), "1d4+FOR")
        self.assertEqual(dano_arma_natural("1d4+FOR", "XXXXX", "2 m"), "1d12+FOR")
        self.assertEqual(dano_arma_natural("1d4+FOR", "X", "7 m"), "1d10+FOR")

    def test_tamanho_aumenta_um_passo_a_cada_dois_metros(self):
        casos = {
            "80 cm": 0,
            "2 m": 0,
            "2,5 m": 1,
            "4 m": 1,
            "5 m": 2,
            "7 m": 3,
            "9 m": 4,
            "12 m": 5,
        }
        for tamanho, esperado in casos.items():
            with self.subTest(tamanho=tamanho):
                self.assertEqual(passos_dano_por_tamanho(tamanho), esperado)

    def test_tamanho_aceita_formatos_sem_unidade(self):
        casos = {
            "2,89": (2.89, "2,89 m"),
            "289": (2.89, "2,89 m"),
            "289cm": (2.89, "2,89 m"),
            "050": (0.5, "50 cm"),
            "0,50": (0.5, "50 cm"),
            "50": (0.5, "50 cm"),
            "0,50m": (0.5, "50 cm"),
        }
        for informado, (metros, normalizado) in casos.items():
            with self.subTest(informado=informado):
                self.assertAlmostEqual(tamanho_em_metros(informado), metros)
                faixa = "De 2 m a 3 m" if metros > 2 else "Menos de 1 m"
                self.assertEqual(validar_e_normalizar_tamanho(informado, faixa), normalizado)

    def test_tamanho_incompativel_com_faixa_e_bloqueado(self):
        self.assertFalse(tamanho_pertence_a_faixa("2,89 m", "Menos de 1 m"))
        with self.assertRaisesRegex(ValueError, "não pertence à faixa"):
            validar_e_normalizar_tamanho("289", "Menos de 1 m")

    def test_tabelas_de_armas_preservam_dano_oficial(self):
        self.assertEqual(ARMAS_POR_TIPO["Armas Naturais"]["Ferrão"]["dano-base"], "1d12+Força")
        self.assertEqual(ARMAS_POR_TIPO["Armas Simples"]["Machadinha"]["alcance"], "3 m")
        self.assertEqual(ARMAS_POR_TIPO["Armas Marciais"]["Besta Pesada"]["dano"], "2d6+Destreza")
        self.assertEqual(ARMAS_POR_TIPO["Armas Exóticas"]["Katana"]["crítico"], "19")
        self.assertEqual(ARMAS_POR_TIPO["Armas de Fogo"]["Fuzil de precisão"]["alcance"], "120 m")

    def test_soma_forca_e_destreza_ao_dano_por_extenso(self):
        atributos = {"Força": 16, "Destreza": 14}
        self.assertEqual(somar_atributo_ao_dano("1d6+Força", atributos), "1d6+3 (Força)")
        self.assertEqual(somar_atributo_ao_dano("1d8+DES", atributos), "1d8+2 (Destreza)")
        self.assertEqual(
            somar_atributo_ao_dano("1d8+Destreza e 1d8+Destreza", atributos),
            "1d8+2 (Destreza) e 1d8+2 (Destreza)",
        )

    def test_fraquezas_e_resistencias_usam_rotulos_explicativos(self):
        ficha = FichaCriatura("Teste", "Fera", "X", "1 m", "De 1 m a 2 m")
        fraqueza = TipoEfeitoView(1, ficha, True, "Fogo")
        resistencia = TipoEfeitoView(1, ficha, False, "Fogo")
        self.assertEqual(
            [opcao.value for opcao in fraqueza.s.options],
            ["Aumento de Dano Sofrido", "Desvantagem em testes de resistência"],
        )
        self.assertEqual(
            [opcao.value for opcao in resistencia.s.options],
            ["Redução de Dano Sofrido", "Vantagem em testes de resistência", "Imunidade a efeito"],
        )
        self.assertTrue(all(opcao.description for opcao in fraqueza.s.options + resistencia.s.options))

    def test_biblioteca_pede_faixa_antes_do_tamanho_exato(self):
        referencia = ReferenciaCriatura(
            "Pixie", "XXXX", "Fera", Path("Pixie.md"), aptidoes="Voo"
        )
        faixa = FaixaTamanhoBibliotecaView(1, referencia, 0)
        self.assertEqual(faixa.seletor.placeholder, "Escolha a faixa de tamanho")
        self.assertTrue(all(opcao.description for opcao in faixa.seletor.options))

        modal = TamanhoCriaturaModal(1, referencia, "Menos de 1 m")
        self.assertEqual(modal.faixa, "Menos de 1 m")
        self.assertEqual(modal.tamanho.label, "Tamanho exato — Menos de 1 m")
        self.assertIn("entre 50 cm e menos de 1 m", modal.tamanho.placeholder)
        self.assertIn("80 cm", modal.tamanho.placeholder)

    def test_markdown_preserva_blocos_de_combate(self):
        ficha = FichaCriatura("Teste", "Fera", "XX", "80 cm", "Menos de 1 m")
        ficha.habilidades.append({"nome": "Fúria", "modo do custo": "Por acúmulo"})
        with tempfile.TemporaryDirectory() as temporaria:
            caminho = Path(temporaria) / "Teste.md"
            caminho.write_text(ficha.markdown(), encoding="utf-8")
            carregada = FichaCriatura.carregar(caminho)
        self.assertEqual(carregada.habilidades[0]["nome"], "Fúria")
        self.assertEqual(carregada.habilidades[0]["modo do custo"], "Por acúmulo")


if __name__ == "__main__":
    unittest.main()
