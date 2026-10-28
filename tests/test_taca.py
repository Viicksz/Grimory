from __future__ import annotations

import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from comandos.taca import cabecalho_taca, embed_taca, embeds_acontecimentos, mencao_casa
from utils.taca import (
    CASAS,
    EstadoTaca,
    aplicar_acontecimento,
    carregar_autoridades,
    carregar_estado_taca,
    listar_personagens_por_casa,
    salvar_estado_taca,
    sortear_acontecimento,
    texto_acontecimento,
)


class CatalogoAutoridadesTests(unittest.TestCase):
    def test_vinte_e_uma_autoridades_possuem_vinte_presets_cada(self) -> None:
        autoridades = carregar_autoridades()
        self.assertEqual(
            [item.nome for item in autoridades],
            [
                "Minerva McGonagall",
                "Rhysand Velaris",
                "Arthur Carter",
                "Kin Yamazaki",
                "Alessa Belshoff",
                "Madame Brulee",
                "Sr.Grayson",
                "Sr.Windsom",
                "Renee Moretti",
                "Sra.Targellan",
                "Lyz Evans",
                "Rúbeo Hagrid",
                "Gideon Aldrich",
                "Srta. Gabriella Dubois",
                "Dra. Muerstein",
                "Sr.Grumblefoot",
                "Sr.Nyström",
                "Illyana Corvielle",
                "Cassian Vale",
                "Owen Jones",
                "Magnus Whitmore",
            ],
        )
        self.assertEqual(sum(len(item.gratificacoes) for item in autoridades), 210)
        self.assertEqual(sum(len(item.penalidades) for item in autoridades), 210)
        for autoridade in autoridades:
            with self.subTest(autoridade=autoridade.nome):
                self.assertEqual(len(autoridade.gratificacoes), 10)
                self.assertEqual(len(autoridade.penalidades), 10)
                self.assertEqual(
                    Counter(item.pontos for item in autoridade.gratificacoes),
                    {5: 2, 10: 2, 15: 2, 20: 2, 25: 2},
                )
                self.assertEqual(
                    Counter(item.pontos for item in autoridade.penalidades),
                    {5: 2, 10: 2, 15: 2, 20: 2, 25: 2},
                )

    def test_cabecalho_usa_padrao_ornamental(self) -> None:
        self.assertEqual(
            cabecalho_taca("Taça das Casas"),
            "## ══════◄••🏆••►══════\n"
            "## Taça das Casas\n"
            "## ══════◄••🏆••►══════",
        )


class SorteioTacaTests(unittest.TestCase):
    def test_considera_apenas_as_quatro_pastas_de_casas(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            for nome in (*CASAS, "NPCs", "Players"):
                (pasta / nome).mkdir()
                (pasta / nome / f"{nome}.md").write_text(f"# {nome}\n", encoding="utf-8")
            with patch("utils.taca.PASTA_FICHAS", pasta):
                personagens = listar_personagens_por_casa()
            self.assertEqual(set(personagens), set(CASAS))
            self.assertNotIn("NPCs", personagens)
            self.assertNotIn("Players", personagens)

    def test_sorteia_primeiro_entre_casas_disponiveis(self) -> None:
        personagens = {
            "Grifinória": [],
            "Sonserina": [],
            "Lufa-Lufa": [],
            "Corvinal": ["Ollie White"],
        }
        acontecimento = sortear_acontecimento(
            gerador=random.Random(7),
            moderador_id=99,
            personagens=personagens,
        )
        self.assertEqual(acontecimento.casa, "Corvinal")
        self.assertEqual(acontecimento.personagem, "Ollie White")
        self.assertIn(abs(acontecimento.pontos), {5, 10, 15, 20, 25})
        self.assertEqual(acontecimento.moderador_id, 99)

    def test_texto_menciona_o_cargo_correto(self) -> None:
        acontecimento = sortear_acontecimento(
            gerador=random.Random(3),
            personagens={casa: (["Miriam"] if casa == "Grifinória" else []) for casa in CASAS},
        )
        texto = texto_acontecimento(acontecimento)
        self.assertIn("**Miriam**", texto)
        self.assertNotIn("❤️", texto)
        self.assertIn("<@&937255634024402954>", texto)

    def test_cada_acontecimento_tem_embed_propria_sem_titulo_ou_tipo(self) -> None:
        personagens = {casa: [f"Aluno de {casa}"] for casa in CASAS}
        acontecimentos = [
            sortear_acontecimento(
                gerador=random.Random(semente),
                personagens=personagens,
            )
            for semente in range(5)
        ]
        embeds = embeds_acontecimentos(acontecimentos)
        self.assertEqual(len(embeds), 5)
        self.assertTrue(all(embed.title is None for embed in embeds))
        self.assertTrue(all(not embed.fields for embed in embeds))
        conteudo = "\n".join(embed.description for embed in embeds)
        for coracao in ("❤️", "💚", "💛", "💙"):
            self.assertNotIn(coracao, conteudo)
        self.assertTrue(all("<@&" in embed.description for embed in embeds))

    def test_todas_as_casas_usam_coracao_e_mencao_de_cargo(self) -> None:
        esperadas = {
            "Grifinória": "❤️ <@&937255634024402954>",
            "Sonserina": "💚 <@&937254921219211285>",
            "Lufa-Lufa": "💛 <@&937255872126648340>",
            "Corvinal": "💙 <@&937255410719653919>",
        }
        self.assertEqual({casa: mencao_casa(casa) for casa in CASAS}, esperadas)

    def test_classificacao_nao_exibe_nomes_simples_das_casas(self) -> None:
        embed = embed_taca(EstadoTaca())
        classificacao = embed.fields[0].value
        for casa in CASAS:
            self.assertIn(mencao_casa(casa), classificacao)
            self.assertNotIn(f"**{casa}**", classificacao)
        self.assertTrue(classificacao.splitlines()[-1].startswith("💩 "))


class PersistenciaTacaTests(unittest.TestCase):
    def test_aplica_salva_e_recarrega_movimentacao(self) -> None:
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "Taça das Casas.md"
            acontecimento = sortear_acontecimento(
                gerador=random.Random(11),
                personagens={casa: (["Luna"] if casa == "Corvinal" else []) for casa in CASAS},
            )
            estado = EstadoTaca()
            aplicar_acontecimento(estado, acontecimento)
            salvar_estado_taca(estado, caminho)
            carregado = carregar_estado_taca(caminho)
            self.assertEqual(carregado.pontuacoes["Corvinal"], acontecimento.pontos)
            self.assertEqual(carregado.historico[0].identificador, acontecimento.identificador)
            self.assertEqual(embed_taca(carregado).title, "Taça das Casas")


if __name__ == "__main__":
    unittest.main()
