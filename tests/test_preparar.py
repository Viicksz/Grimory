import unittest

from comandos.preparar import criar_grupos_indice_pocoes, montar_embeds_indice_pocoes
from utils.biblioteca import normalizar_rotulo


class IndicePrepararPocoesTests(unittest.TestCase):
    def test_indice_agrupa_por_ano_e_aplica_links_oficiais(self) -> None:
        grupos = criar_grupos_indice_pocoes()
        self.assertEqual(
            [grupo.titulo for grupo in grupos],
            [f"{ano}º Ano" for ano in range(1, 8)],
        )
        self.assertEqual(sum(len(grupo.itens) for grupo in grupos), 42)

        primeiro_grupo = grupos[0]
        primeira_pocao = primeiro_grupo.itens[0]
        url = "https://discord.com/channels/1/2/3"
        links = {
            (
                normalizar_rotulo(primeiro_grupo.titulo),
                normalizar_rotulo(primeira_pocao.nome),
            ): url,
        }
        embeds = montar_embeds_indice_pocoes(links)
        self.assertIn(
            f"[{primeira_pocao.nome}]({url})",
            embeds[0].description,
        )


if __name__ == "__main__":
    unittest.main()
