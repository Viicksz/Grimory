import unittest

from comandos.executar import (
    GrupoIndice,
    ItemIndice,
    agrupar_embeds_indice,
    criar_embeds_indice,
    destino_grupo_indice,
    organizar_lotes_indice,
)
from utils.biblioteca import EntradaBiblioteca
from utils.biblioteca import normalizar_rotulo


def item(numero: int) -> ItemIndice:
    return ItemIndice(
        nome=f"Feitiço {numero:02d}",
        entrada=EntradaBiblioteca(
            titulo=f"Feitiço {numero:02d}",
            descricao="Descrição de teste.",
            campos={"Categoria": "Encantamentos"},
        ),
        tipo="feitico",
    )


class IndiceExecucaoLinksTests(unittest.TestCase):
    def test_nome_vira_link_markdown_quando_mensagem_foi_localizada(self) -> None:
        grupo = GrupoIndice("1º Ano", [item(1), item(2)])
        links = {
            (normalizar_rotulo(grupo.titulo), normalizar_rotulo("Feitiço 01")): (
                "https://discord.com/channels/1/2/3"
            ),
        }
        embed = criar_embeds_indice("Encantamentos", [grupo], 123, links)[0]
        self.assertIn(
            "• [Feitiço 01](https://discord.com/channels/1/2/3)",
            embed.description,
        )
        self.assertIn("• Feitiço 02", embed.description)

    def test_destino_bindrune_usa_thread_unica(self) -> None:
        grupo = GrupoIndice("Radial", [item(1)])
        destinos = {("runas antigas", "bindrunes"): 123}
        self.assertEqual(destino_grupo_indice("Bindrunes", grupo, destinos), 123)

    def test_indices_com_links_sao_divididos_no_limite_do_discord(self) -> None:
        grupos = [
            GrupoIndice(f"{ano}º Ano", [item(numero) for numero in range(20)])
            for ano in range(1, 8)
        ]
        links = {
            (normalizar_rotulo(grupo.titulo), normalizar_rotulo(feitico.nome)): (
                f"https://discord.com/channels/123456789012345678/"
                f"{100000000000000000 + ano}/{200000000000000000 + numero}"
            )
            for ano, grupo in enumerate(grupos)
            for numero, feitico in enumerate(grupo.itens)
        }
        lotes = agrupar_embeds_indice(
            criar_embeds_indice("Encantamentos", grupos, 123, links)
        )
        self.assertGreater(len(lotes), 1)
        self.assertTrue(all(len(lote) <= 10 for lote in lotes))
        self.assertTrue(all(sum(len(embed) for embed in lote) <= 6000 for lote in lotes))

    def test_anos_sao_separados_em_basico_intermediario_e_avancado(self) -> None:
        grupos = [
            GrupoIndice(f"{ano}º Ano", [item(ano)])
            for ano in range(1, 8)
        ]
        embeds = criar_embeds_indice("DCAT", grupos, 123)
        lotes = organizar_lotes_indice("DCAT", grupos, embeds)
        self.assertEqual(
            [lote.rotulo for lote in lotes],
            [
                "Básico — 1º e 2º Ano",
                "Intermediário — 3º ao 5º Ano",
                "Avançado — 6º e 7º Ano",
            ],
        )
        self.assertEqual([len(lote.embeds) for lote in lotes], [2, 3, 2])


if __name__ == "__main__":
    unittest.main()
