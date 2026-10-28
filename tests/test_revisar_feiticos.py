from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comandos.revisar_feiticos import (
    BaseFeiticoView,
    DefesaContraView,
    DuracaoAlvoView,
    EfeitosFeiticoView,
    RegrasUniversaisView,
    TiposFeiticoView,
    classificacao_revisao,
    grupos_revisao,
)
from comandos.executar import criar_embeds_entrada
from utils.biblioteca import interpretar_markdown
from utils.feiticos_combate import (
    aplicar_perfil,
    descricao_publica,
    extrair_perfil,
    limpar_mecanicas_legadas,
    normalizar_perfil,
    pendencias,
    perfil_vazio,
    salvar_revisao,
)


FICHA = """# Teste

Categoria:
Duelos

Ano de desbloqueio:
3º Ano

Grau de dificuldade:
Intermediário Ⅲ

Descrição:
Descrição oficial.
**2d6+2 de dano ígneo.**

Dificuldade por ano:
3º Ano: 14+
"""


def perfil_completo():
    perfil = perfil_vazio()
    perfil.update(
        {
            "estado": "completa",
            "mira": "Lampejo",
            "alcance": "Médio",
            "alvo": "Criatura",
            "tipo_acao": "Padrão",
            "ativacao": "Sustentada",
            "duracao": {"valor": "3", "unidade": "Turno"},
            "tipos": ["Dano", "Debuff"],
            "respostas": ["Esquiva", "Contra-feitiço"],
            "acumulo": "Não acumula",
            "encerramento": "Termina ao perder a concentração.",
            "efeitos": [{"tipo": "Debuff", "texto": "O alvo sofre -2 em Reflexo"}],
            "dano": {
                "inicial": "2d6+2",
                "tipo_inicial": "ígneo",
                "sustentado": "+2",
                "tipo_sustentado": "elétrico",
                "frequencia": "turno",
            },
        }
    )
    return normalizar_perfil(perfil)


class PerfilFeiticoCombateTests(unittest.TestCase):
    def test_seletores_do_editor_possuem_resposta_imediata(self) -> None:
        class Sessao:
            perfil = perfil_completo()

        base = BaseFeiticoView(1, Sessao())
        tipos = TiposFeiticoView(1, Sessao())

        self.assertIs(base.mira.callback.__self__, base)
        self.assertEqual(base.mira.callback.__name__, "registrar_selecao")
        self.assertIs(base.acao.callback.__self__, base)
        self.assertIs(base.ativacao.callback.__self__, base)
        self.assertIs(tipos.seletor.callback.__self__, tipos)

    def test_duracao_e_menu_e_gatilho_so_aparece_para_preparada(self) -> None:
        class Sessao:
            perfil = perfil_completo()

        sessao = Sessao()
        sustentada = DuracaoAlvoView(1, sessao)
        self.assertEqual(
            [opcao.value for opcao in sustentada.unidade.options],
            ["Instantâneo", "Turno", "Rodada", "Minuto", "Cena"],
        )
        self.assertEqual(
            [opcao.value for opcao in sustentada.alcance.options],
            ["Pessoal", "Contato", "Curto", "Médio", "Longo", "Campo de Visão", "Especial"],
        )
        self.assertEqual(
            [opcao.value for opcao in sustentada.alvo.options],
            ["Pessoal", "Criatura", "Objeto", "Ponto", "Múltiplos", "Área", "Especial"],
        )
        self.assertNotIn("Gatilho", [getattr(item, "label", None) for item in sustentada.children])

        sessao.perfil = dict(sessao.perfil, ativacao="Preparada")
        preparada = DuracaoAlvoView(1, sessao)
        self.assertIn("Gatilho", [getattr(item, "label", None) for item in preparada.children])

    def test_regras_usam_menus_e_nao_duplicam_efeito_publico(self) -> None:
        class Sessao:
            perfil = perfil_completo()

        view = RegrasUniversaisView(1, Sessao())
        placeholders = [
            getattr(item, "placeholder", None)
            for item in view.children
            if hasattr(item, "placeholder")
        ]
        self.assertIn("Como o alvo pode responder?", placeholders)
        self.assertIn("Como efeitos repetidos se acumulam?", placeholders)
        self.assertNotIn("Efeito público adicional", str(view.children))

    def test_efeitos_mostram_somente_os_tipos_escolhidos(self) -> None:
        class Sessao:
            perfil = perfil_completo()

        labels = [
            getattr(item, "label", None)
            for item in EfeitosFeiticoView(1, Sessao()).children
        ]
        self.assertIn("Dano", labels)
        self.assertIn("Debuff", labels)
        self.assertNotIn("Cura", labels)
        self.assertNotIn("Buff, debuff ou efeito", labels)

    def test_defesa_e_contra_feitico_usam_menus_separados(self) -> None:
        class Sessao:
            perfil = perfil_completo()

        sessao = Sessao()
        sessao.perfil["defesa"]["momento"] = "Reação"
        sessao.perfil["contra_feitico"].update(
            {"habilitado": True, "momento": "Reação imediata"}
        )
        view = DefesaContraView(1, sessao)
        labels = [getattr(item, "label", None) for item in view.children]
        self.assertIn("Detalhes da defesa", labels)
        self.assertIn("Detalhes do contra-feitiço", labels)
        self.assertEqual(view.momento.values, [])
        self.assertEqual(view.momento_contra.values, [])

    def test_selecao_agrupa_por_ano_sem_faixa_alfabetica(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            primeiro = raiz / "Zeta.md"
            terceiro = raiz / "Alfa.md"
            primeiro.write_text(FICHA.replace("3º Ano", "1ºAno"), encoding="utf-8")
            terceiro.write_text(FICHA, encoding="utf-8")

            grupos = grupos_revisao([terceiro, primeiro])

            self.assertEqual(
                [(tipo, rotulo) for tipo, rotulo, _ in grupos],
                [("Ano", "1º Ano"), ("Ano", "3º Ano")],
            )
            self.assertEqual(grupos[0][2], [primeiro])

    def test_ano_especial_preserva_informacao_da_ficha(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "Especial.md"
            arquivo.write_text(
                FICHA.replace("3º Ano", "Aulas de Transfiguração"),
                encoding="utf-8",
            )
            self.assertEqual(
                classificacao_revisao(arquivo),
                ("Ano", "Aulas de Transfiguração"),
            )

    def test_sem_ano_usa_vertente_oficial(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "Sombrio.md"
            arquivo.write_text(
                FICHA.replace(
                    "Ano de desbloqueio:\n3º Ano\n\n",
                    "Vertente:\nMaldições\n\n",
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                classificacao_revisao(arquivo),
                ("Vertente", "Maldições"),
            )

    def test_bloco_tecnico_roundtrip_preserva_campos_da_ficha(self) -> None:
        conteudo = aplicar_perfil(FICHA, perfil_completo())
        perfil = extrair_perfil(conteudo)
        entrada = interpretar_markdown(conteudo)

        self.assertEqual(perfil["mira"], "Lampejo")
        self.assertEqual(entrada.titulo, "Teste")
        self.assertEqual(entrada.campos["Categoria"], "Duelos")
        self.assertNotIn("GRIMORY_COMBATE", entrada.descricao)

    def test_publicacao_e_compacta_e_dano_fica_na_mesma_linha(self) -> None:
        texto = descricao_publica("Descrição oficial.", perfil_completo())
        self.assertEqual(texto.splitlines()[0], "`Lampejo`")
        self.assertEqual(texto.splitlines()[1], "Descrição oficial.")
        self.assertNotIn("\n\n", texto)
        self.assertIn("`Alcance: Médio.`", texto)
        self.assertIn("`Alvo: Criatura.`", texto)
        self.assertIn(
            "`2d6+2 de dano ígneo, +2 de dano elétrico por turno sustentado.`",
            texto,
        )

    def test_sustentado_exige_vontade_na_mesma_cd(self) -> None:
        concentracao = perfil_completo()["concentracao"]
        self.assertTrue(concentracao["exigida"])
        self.assertEqual(concentracao["pericia"], "Vontade")
        self.assertEqual(concentracao["cd"], "Mesma CD do feitiço")

    def test_preparada_exige_gatilho(self) -> None:
        perfil = perfil_completo()
        perfil["ativacao"] = "Preparada"
        perfil["gatilho"] = ""
        self.assertIn("gatilho da magia preparada", pendencias(perfil))
        perfil["gatilho"] = "Quando alguém atravessar a barreira."
        self.assertNotIn("gatilho da magia preparada", pendencias(perfil))

    def test_migracao_preserva_alcance_alvo_e_area_legados(self) -> None:
        perfil = normalizar_perfil(
            {
                "mira": "Vínculo de sangue",
                "alcance": "Até o fim do castelo",
                "alvo": "",
                "area": "Círculo de 6 metros",
            }
        )
        self.assertEqual(perfil["versao"], 2)
        self.assertEqual(perfil["mira"], "Especial")
        self.assertEqual(perfil["detalhes_mira"], "Vínculo de sangue")
        self.assertEqual(perfil["alcance"], "Especial")
        self.assertEqual(perfil["detalhes_alcance"], "Até o fim do castelo")
        self.assertEqual(perfil["alvo"], "Área")
        self.assertEqual(perfil["area"], "Círculo de 6 metros")

    def test_area_e_condicoes_especiais_geram_pendencias_proprias(self) -> None:
        perfil = perfil_completo()
        perfil.update({"mira": "Especial", "detalhes_mira": "", "alvo": "Área", "area": ""})
        faltas = pendencias(perfil)
        self.assertIn("condição especial da manifestação", faltas)
        self.assertIn("dimensões e afetados da área", faltas)
        perfil["detalhes_mira"] = "Exige conhecer o nome verdadeiro."
        perfil["area"] = "Círculo de 6 metros; afeta todos dentro dele."
        faltas = pendencias(perfil)
        self.assertNotIn("condição especial da manifestação", faltas)
        self.assertNotIn("dimensões e afetados da área", faltas)

    def test_salvar_revisao_remove_mecanica_legada_e_mantem_backup_possivel(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "Teste.md"
            caminho.write_text(FICHA, encoding="utf-8")
            descricao = limpar_mecanicas_legadas(
                interpretar_markdown(FICHA).descricao
            )
            salvar_revisao(caminho, perfil_completo(), descricao)
            salvo = caminho.read_text(encoding="utf-8")
            self.assertNotIn("**2d6+2 de dano ígneo.**", salvo)
            self.assertEqual(interpretar_markdown(salvo).descricao, "Descrição oficial.")

    def test_executar_renderiza_perfil_sem_expor_bloco_tecnico(self) -> None:
        entrada = interpretar_markdown(aplicar_perfil(FICHA, perfil_completo()))
        entrada.descricao = limpar_mecanicas_legadas(entrada.descricao)
        embeds = criar_embeds_entrada(entrada, "feitico", "Teste")
        self.assertTrue(embeds[0].description.startswith("`Lampejo`\nDescrição oficial."))
        self.assertNotIn("GRIMORY_COMBATE", embeds[0].description)


if __name__ == "__main__":
    unittest.main()
