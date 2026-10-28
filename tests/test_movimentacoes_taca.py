from __future__ import annotations

import unittest

from comandos.movimentacoes_taca import (
    CATEGORIAS_DESLIZE,
    CATEGORIAS_GRATIFICACAO,
    PONTOS_OCORRENCIAS,
    PUNICOES_SEM_VARINHA,
    SessaoMovimentacao,
    embed_catalogo_gratificacao,
    embed_exemplos_gratificacao,
    embed_publicacao,
    embed_previa,
    exemplos_gratificacao,
    mencao_casa_sem_emoji,
    motivo_publicacao,
    placeholder_contexto,
)
from utils.taca import CANAL_PROFETA_DIARIO_ID, carregar_autoridades


class MovimentacoesTacaTests(unittest.TestCase):
    def test_profeta_diario_e_destino_oficial(self) -> None:
        self.assertEqual(CANAL_PROFETA_DIARIO_ID, 1154807244496572456)

    def test_matriz_de_penalidades(self) -> None:
        self.assertEqual(PONTOS_OCORRENCIAS["leve"], {1: 10, 2: 15, 3: 20})
        self.assertEqual(PONTOS_OCORRENCIAS["grave"], {1: 20, 2: 25, 3: 30})

    def test_deslizes_sao_especificos_e_fixos(self) -> None:
        self.assertIn("Atraso", CATEGORIAS_DESLIZE)
        self.assertIn("Desorganização", CATEGORIAS_DESLIZE)
        self.assertIn("Atividade não entregue", CATEGORIAS_DESLIZE)

    def test_lista_oficial_de_punicoes_foi_preservada(self) -> None:
        self.assertEqual(len(PUNICOES_SEM_VARINHA), 11)
        self.assertIn("Organizar a biblioteca", PUNICOES_SEM_VARINHA)
        self.assertIn("Passar um dia trabalhando na lavanderia", PUNICOES_SEM_VARINHA)

    def test_casa_aparece_sem_coracao_na_movimentacao(self) -> None:
        self.assertEqual(mencao_casa_sem_emoji("Corvinal"), "<@&937255410719653919>")

    def test_previa_mostra_categoria_e_acontecimento(self) -> None:
        autoridade = carregar_autoridades()[0]
        sessao = SessaoMovimentacao(
            tipo="gratificacao",
            moderador_id=1,
            usuario_id=2,
            nome_personagem="Miriam",
            autoridade=autoridade,
            casa="Grifinória",
            categoria="proteger os colegas durante uma atividade coletiva",
            dimensao="Desempenho coletivo",
            pontos=15,
        )
        embed = embed_previa(sessao)
        self.assertIn("+15", embed.fields[3].value)
        self.assertEqual(embed.fields[4].value, "Desempenho coletivo")
        self.assertIn("proteger os colegas", embed.fields[5].value)

    def test_categorias_das_autoridades_sao_situacoes_especificas(self) -> None:
        autoridades = {item.nome: item for item in carregar_autoridades()}
        hagrid = " ".join(item.motivo for item in autoridades["Rúbeo Hagrid"].gratificacoes)
        kin = " ".join(item.motivo for item in autoridades["Kin Yamazaki"].gratificacoes)
        muerstein = " ".join(item.motivo for item in autoridades["Dra. Muerstein"].gratificacoes)
        self.assertIn("pelúcio engasgado", hagrid)
        self.assertIn("inscrição", kin)
        self.assertIn("primeiros socorros", muerstein)

    def test_catalogo_exibe_as_cinco_categorias_e_seus_valores(self) -> None:
        autoridade = next(
            item for item in carregar_autoridades() if item.nome == "Kin Yamazaki"
        )
        sessao = SessaoMovimentacao(
            tipo="gratificacao",
            moderador_id=1,
            usuario_id=2,
            nome_personagem="Eivor",
            autoridade=autoridade,
            casa="Sonserina",
        )
        embed = embed_catalogo_gratificacao(sessao)
        self.assertIn("Nota 10", embed.description)
        self.assertIn("Execução Perfeita", embed.description)
        for _, nome, pontos in CATEGORIAS_GRATIFICACAO:
            self.assertIn(nome, embed.description)
            self.assertIn(f"+{pontos} pontos", embed.description)

    def test_gratificacoes_padrao_permanecem_alem_das_categorias(self) -> None:
        autoridade = carregar_autoridades()[0]
        nota = SessaoMovimentacao(
            tipo="gratificacao",
            moderador_id=1,
            usuario_id=2,
            nome_personagem="Miriam",
            autoridade=autoridade,
            casa="Grifinória",
            categoria="Nota 10",
            pontos=5,
        )
        execucao = SessaoMovimentacao(
            tipo="gratificacao",
            moderador_id=1,
            usuario_id=2,
            nome_personagem="Miriam",
            autoridade=autoridade,
            casa="Grifinória",
            categoria="Execução Perfeita",
            pontos=15,
        )
        self.assertEqual(motivo_publicacao(nota), "tirar nota 10 ou acima em uma aula")
        self.assertIn("feitiço, uma poção ou um trato", motivo_publicacao(execucao))
        self.assertIn("em sua presença", motivo_publicacao(execucao))

    def test_madame_brulee_personaliza_as_gratificacoes_padrao(self) -> None:
        autoridade = next(
            item for item in carregar_autoridades() if item.nome == "Madame Brulee"
        )
        sessao = SessaoMovimentacao(
            tipo="gratificacao",
            moderador_id=1,
            usuario_id=2,
            nome_personagem="Miriam",
            autoridade=autoridade,
            casa="Grifinória",
            categoria="Nota 10",
            pontos=5,
        )
        self.assertIn("possibilidades além das rotas convencionais", motivo_publicacao(sessao))
        sessao.categoria = "Execução Perfeita"
        sessao.pontos = 15
        self.assertIn("abordagem que parecia impossível", motivo_publicacao(sessao))

    def test_cada_autoridade_tem_dois_exemplos_em_cada_categoria(self) -> None:
        for autoridade in carregar_autoridades():
            for _, nome, pontos in CATEGORIAS_GRATIFICACAO:
                sessao = SessaoMovimentacao(
                    tipo="gratificacao",
                    moderador_id=1,
                    usuario_id=2,
                    nome_personagem="Miriam",
                    autoridade=autoridade,
                    casa="Grifinória",
                    dimensao=nome,
                    pontos=pontos,
                )
                with self.subTest(autoridade=autoridade.nome, categoria=nome):
                    self.assertEqual(len(exemplos_gratificacao(sessao)), 2)

    def test_segunda_tela_exibe_os_dois_exemplos_completos(self) -> None:
        autoridade = next(
            item for item in carregar_autoridades() if item.nome == "Kin Yamazaki"
        )
        sessao = SessaoMovimentacao(
            tipo="gratificacao",
            moderador_id=1,
            usuario_id=2,
            nome_personagem="Eivor",
            autoridade=autoridade,
            casa="Sonserina",
            dimensao="Desempenho acadêmico",
            pontos=10,
        )
        exemplos = exemplos_gratificacao(sessao)
        embed = embed_exemplos_gratificacao(sessao, exemplos)
        self.assertEqual(len(exemplos), 2)
        self.assertTrue(all(item.motivo in embed.description for item in exemplos))
        self.assertIn("Personalizada", embed.description)

    def test_perspectivas_das_autoridades_foram_preservadas(self) -> None:
        autoridades = {item.nome: item for item in carregar_autoridades()}
        alessa_5 = " ".join(
            item.motivo for item in autoridades["Alessa Belshoff"].gratificacoes
            if item.pontos == 5
        )
        brulee_25 = " ".join(
            item.motivo for item in autoridades["Madame Brulee"].gratificacoes
            if item.pontos == 25
        )
        rhysand_25 = " ".join(
            item.motivo for item in autoridades["Rhysand Velaris"].gratificacoes
            if item.pontos == 25
        )
        minerva_25 = " ".join(
            item.motivo for item in autoridades["Minerva McGonagall"].penalidades
            if item.pontos == 25
        )
        self.assertIn("gentileza", alessa_5)
        self.assertIn("bondade", alessa_5)
        self.assertIn("recorde de voo", brulee_25)
        self.assertIn("ameaça classificada como XXXX", rhysand_25)
        self.assertIn("ameaça classificada como XXXX", minerva_25)

    def test_publicacao_e_uma_frase_longa_sem_cabecalho_ou_campos(self) -> None:
        autoridade = next(
            item for item in carregar_autoridades() if item.nome == "Kin Yamazaki"
        )
        sessao = SessaoMovimentacao(
            tipo="gratificacao",
            moderador_id=1,
            usuario_id=2,
            nome_personagem="Eivor",
            autoridade=autoridade,
            casa="Sonserina",
            categoria="identificar corretamente uma runa sem se precipitar na interpretação",
            pontos=10,
        )
        embed = embed_publicacao(sessao)
        self.assertIsNone(embed.title)
        self.assertFalse(embed.fields)
        self.assertIn("**Kin Yamazaki** concedeu a <@2> *10 pontos*", embed.description)
        self.assertNotIn("Eivor", embed.description)
        self.assertIn("<@&937254921219211285>", embed.description)
        self.assertIn("*10 pontos*", embed.description)

    def test_campo_personalizado_mostra_onde_o_motivo_sera_inserido(self) -> None:
        autoridade = next(
            item for item in carregar_autoridades() if item.nome == "Alessa Belshoff"
        )
        sessao = SessaoMovimentacao(
            tipo="gratificacao",
            moderador_id=1,
            usuario_id=2,
            nome_personagem="Sebastian Pendragon",
            autoridade=autoridade,
            casa="Lufa-Lufa",
            categoria="Personalizada",
            pontos=25,
        )
        self.assertEqual(
            placeholder_contexto(sessao),
            (
                "Alessa Belshoff concedeu a @Sebastian Pendrag… 25 pontos "
                "para a @Lufa-Lufa por [...]"
            ),
        )


if __name__ == "__main__":
    unittest.main()
