import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from comandos.ficha import montar_embeds_ficha
from utils.fichas import FichaPersonagem
from utils.publicacao_narrativa import (
    ConfiguracaoNarrativa,
    carregar_configuracao_narrativa,
    destino_narrativo,
    destino_time,
    montar_entrada_aluno,
    montar_entrada_autoridade,
    montar_entrada_npc,
    montar_entrada_time,
    montar_entradas_ficha,
    preparar_fila_narrativa,
    publicar_fila_narrativa,
    sincronizar_publicacoes_narrativas,
)


def ficha_base(nome: str, grupo: str, casa: str) -> FichaPersonagem:
    return FichaPersonagem(nome, grupo, casa, "Meio-Sangue", "Pena de Fênix")


class ClienteQueNaoPodePublicar:
    def get_channel(self, _identificador):
        raise AssertionError("A publicação narrativa desligada não pode acessar o Discord.")


class MensagemExistente:
    def __init__(self, identificador: int):
        self.id = identificador
        self.edicoes = []

    async def edit(self, **dados):
        self.edicoes.append(dados)


class CanalExistente:
    def __init__(self, mensagem: MensagemExistente):
        self.mensagem = mensagem
        self.envios = []

    async def fetch_message(self, identificador: int):
        self.assert_id = identificador
        return self.mensagem

    async def send(self, **dados):
        self.envios.append(dados)
        raise AssertionError("Uma atualização não pode duplicar a publicação existente.")


class ClienteComPublicacoes:
    def __init__(self, canais: dict[int, CanalExistente]):
        self.canais = canais

    def get_channel(self, identificador: int):
        return self.canais[identificador]


class PublicacaoNarrativaTests(unittest.IsolatedAsyncioTestCase):
    def test_todo_salvamento_da_ficha_dispara_sincronizacao(self):
        origem = Path("comandos/ficha.py").read_text(encoding="utf-8")
        arvore = ast.parse(origem)
        funcoes_com_salvamento = []
        for funcao in ast.walk(arvore):
            if not isinstance(funcao, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            chamadas = {
                chamada.func.id
                if isinstance(chamada.func, ast.Name)
                else chamada.func.attr
                if isinstance(chamada.func, ast.Attribute)
                else ""
                for chamada in ast.walk(funcao)
                if isinstance(chamada, ast.Call)
            }
            if "salvar_ficha" in chamadas and funcao.name != "sincronizar_publicacao_personagem":
                funcoes_com_salvamento.append((funcao.name, funcao.lineno, chamadas))
        self.assertGreaterEqual(len(funcoes_com_salvamento), 15)
        sem_sincronizacao = [
            f"{nome}:{linha}"
            for nome, linha, chamadas in funcoes_com_salvamento
            if "sincronizar_publicacao_personagem" not in chamadas
        ]
        self.assertEqual(sem_sincronizacao, [])

    def test_todas_as_rotas_recebidas_estao_configuradas(self):
        self.assertEqual(destino_narrativo(ficha_base("A", "NPCs", "--")), 1533249207165648916)
        self.assertEqual(destino_narrativo(ficha_base("A", "Figuras de Autoridade", "--")), 1533246491395756203)
        self.assertEqual(destino_narrativo(ficha_base("A", "Grifinória", "Grifinória")), 1124927661517578320)
        self.assertEqual(destino_narrativo(ficha_base("A", "Sonserina", "Sonserina")), 1124927463584190635)
        self.assertEqual(destino_narrativo(ficha_base("A", "Lufa-Lufa", "Lufa-Lufa")), 1124928017374908438)
        self.assertEqual(destino_narrativo(ficha_base("A", "Corvinal", "Corvinal")), 1124927830761934978)
        self.assertEqual(destino_time("Grifinória"), 1124945987459350538)
        self.assertEqual(destino_time("Sonserina"), 1124945817875251200)
        self.assertEqual(destino_time("Lufa-Lufa"), 1124946495301496982)
        self.assertEqual(destino_time("Corvinal"), 1124946355731832985)

    def test_aluno_exige_imagem_altura_idade_e_cursando(self):
        ficha = ficha_base("Estudante", "Grifinória", "Grifinória")
        entrada = montar_entrada_aluno(ficha, Path("Estudante.md"))
        self.assertEqual(entrada.pendencias, ["Altura e Idade", "Cursando", "imagem do personagem"])
        ficha.imagens = [{"url": "https://exemplo.test/aluno.png"}]
        ficha.informacoes = [
            {"titulo": "Altura e Idade", "descricao": "1,55 com 13 Anos"},
            {"titulo": "Cursando", "descricao": "2º Ano"},
        ]
        entrada = montar_entrada_aluno(ficha, Path("Estudante.md"))
        self.assertTrue(entrada.pronta)
        self.assertEqual(entrada.embeds[0].title, "Estudante")
        self.assertEqual([campo.name for campo in entrada.embeds[0].fields], ["Cursando", "Altura e Idade"])
        self.assertTrue(all(campo.inline for campo in entrada.embeds[0].fields))

    def test_informacoes_da_ficha_sempre_comecam_por_cursando_e_altura_inline(self):
        ficha = ficha_base("Estudante", "Grifinória", "Grifinória")
        ficha.informacoes = [
            {"titulo": "Patrono", "descricao": "Leão"},
            {"titulo": "Altura e Idade", "descricao": "1,55 com 13 Anos"},
            {"titulo": "Cursando", "descricao": "2º Ano"},
        ]
        informacoes = montar_embeds_ficha(ficha)[1]
        self.assertEqual(
            [campo.name for campo in informacoes.fields],
            ["Cursando", "Altura e Idade", "Patrono"],
        )
        self.assertTrue(informacoes.fields[0].inline)
        self.assertTrue(informacoes.fields[1].inline)
        self.assertFalse(informacoes.fields[2].inline)

    def test_concluinte_publica_como_npc_e_nao_retorna_ao_time(self):
        ficha = ficha_base("Concluinte", "NPCs", "Grifinória")
        ficha.ano = "Ensino Completo"
        ficha.imagens = [{"url": "https://exemplo.test/concluinte.png"}]
        ficha.informacoes = [
            {"titulo": "Cursando", "descricao": "Ensino Completo"},
            {"titulo": "Jogador de Quadribol", "descricao": "Apanhador"},
            {"titulo": "Situação no time", "descricao": "Titular"},
            {"titulo": "Vassoura", "descricao": "Nimbus 2001"},
        ]
        entradas = montar_entradas_ficha(ficha, Path("Concluinte.md"))
        self.assertEqual([entrada.tipo for entrada in entradas], ["npc"])
        self.assertEqual(entradas[0].destino_id, 1533249207165648916)

    def test_autoridade_publica_apenas_campos_narrativos_e_sobre_opcional(self):
        ficha = ficha_base("Professora", "Figuras de Autoridade", "--")
        ficha.imagens = [{"url": "https://exemplo.test/professora.png"}]
        ficha.informacoes = [
            {"titulo": "Altura e Idade", "descricao": "1,72 com 45 Anos"},
            {"titulo": "Cargo", "descricao": "Professora"},
            {"titulo": "Valores", "descricao": "Disciplina"},
            {"titulo": "Personalidade", "descricao": "Severa e justa"},
        ]
        ficha.sobre_narrativo = "Texto narrativo original."
        entrada = montar_entrada_autoridade(ficha, Path("Professora.md"))
        self.assertTrue(entrada.pronta)
        self.assertEqual(
            [campo.name for campo in entrada.embeds[0].fields],
            ["Altura e Idade", "Cargo", "Valores", "Personalidade"],
        )
        self.assertEqual(len(entrada.embeds), 2)
        self.assertEqual(entrada.embeds[1].title, "Sobre")
        self.assertEqual(entrada.embeds[1].description, "Texto narrativo original.")

    def test_npc_exige_altura_e_idade_antes_do_sobre(self):
        ficha = ficha_base("Humano", "NPCs", "--")
        ficha.imagens = [{"url": "https://exemplo.test/humano.png"}]
        ficha.tipo_npc = "Humano/Trouxa"
        ficha.informacoes = [{"titulo": "Sobre", "descricao": "Um comerciante."}]
        pendente = montar_entrada_npc(ficha, Path("Humano.md"))
        self.assertIn("Altura e Idade", pendente.pendencias)
        ficha.informacoes.insert(
            0, {"titulo": "Altura e Idade", "descricao": "1,80 com 30 Anos"}
        )
        entrada = montar_entrada_npc(ficha, Path("Humano.md"))
        self.assertTrue(entrada.pronta)
        self.assertEqual(entrada.embeds[0].fields[0].name, "Altura e Idade")
        self.assertEqual(entrada.embeds[1].title, "Sobre")

    def test_jogador_do_time_recebe_foto_propria_e_da_vassoura(self):
        ficha = ficha_base("Amber", "Grifinória", "Grifinória")
        ficha.imagens = [{"url": "https://exemplo.test/amber.png"}]
        ficha.informacoes = [
            {"titulo": "Jogador de Quadribol", "descricao": "Batedor"},
            {"titulo": "Situação no time", "descricao": "Titular"},
            {"titulo": "Vassoura", "descricao": "Oakshaft 79"},
        ]
        entrada = montar_entrada_time(ficha, Path("Amber.md"))
        self.assertIsNotNone(entrada)
        assert entrada is not None
        self.assertTrue(entrada.pronta)
        self.assertEqual(len(entrada.embeds), 2)
        self.assertEqual(entrada.embeds[0].image.url, "https://exemplo.test/amber.png")
        self.assertTrue(entrada.embeds[1].image.url)

    async def test_fila_e_integracao_ficam_desligadas_sem_autorizacao(self):
        configuracao = carregar_configuracao_narrativa()
        self.assertFalse(configuracao.ativa)
        self.assertEqual(configuracao.intervalo_minutos, 10)
        with tempfile.TemporaryDirectory() as pasta:
            dados = preparar_fila_narrativa(Path(pasta) / "fila.json")
        self.assertFalse(dados["publicacao_ativa"])
        self.assertEqual(dados["intervalo_minutos"], 10)
        self.assertGreater(dados["quantidade"], 0)
        self.assertEqual(dados["quantidade"], dados["prontas"] + dados["pendentes"])
        resultado = await sincronizar_publicacoes_narrativas(
            ClienteQueNaoPodePublicar(), ficha_base("Teste", "NPCs", "--"), Path("Teste.md")
        )
        self.assertEqual(resultado.mensagem_narrativa_id, 0)
        self.assertEqual(resultado.mensagem_time_id, 0)
        with self.assertRaisesRegex(RuntimeError, "bloqueada"):
            await publicar_fila_narrativa(ClienteQueNaoPodePublicar())

    async def test_edicao_atualiza_publicacoes_existentes_sem_duplicar(self):
        ficha = ficha_base("Amber", "Grifinória", "Grifinória")
        ficha.mensagem_narrativa_discord_id = 7001
        ficha.mensagem_time_discord_id = 7002
        ficha.imagens = [{"url": "https://exemplo.test/amber-atualizada.png"}]
        ficha.informacoes = [
            {"titulo": "Altura e Idade", "descricao": "1,70 com 16 Anos"},
            {"titulo": "Cursando", "descricao": "3º Ano"},
            {"titulo": "Jogador de Quadribol", "descricao": "Batedor"},
            {"titulo": "Situação no time", "descricao": "Titular"},
            {"titulo": "Vassoura", "descricao": "Oakshaft 79"},
        ]
        mensagem_narrativa = MensagemExistente(7001)
        mensagem_time = MensagemExistente(7002)
        canal_narrativo = CanalExistente(mensagem_narrativa)
        canal_time = CanalExistente(mensagem_time)
        cliente = ClienteComPublicacoes(
            {
                1124927661517578320: canal_narrativo,
                1124945987459350538: canal_time,
            }
        )
        with patch(
            "utils.publicacao_narrativa.carregar_configuracao_narrativa",
            return_value=ConfiguracaoNarrativa(ativa=True, intervalo_minutos=10),
        ):
            resultado = await sincronizar_publicacoes_narrativas(
                cliente, ficha, Path("Amber.md")
            )
        self.assertEqual(resultado.mensagem_narrativa_id, 7001)
        self.assertEqual(resultado.mensagem_time_id, 7002)
        self.assertEqual(len(mensagem_narrativa.edicoes), 1)
        self.assertEqual(len(mensagem_time.edicoes), 1)
        self.assertEqual(canal_narrativo.envios, [])
        self.assertEqual(canal_time.envios, [])
        campos_narrativos = {
            campo.name: campo.value
            for campo in mensagem_narrativa.edicoes[0]["embeds"][0].fields
        }
        self.assertEqual(
            campos_narrativos,
            {"Altura e Idade": "1,70 com 16 Anos", "Cursando": "3º Ano"},
        )
        self.assertEqual(
            mensagem_time.edicoes[0]["embeds"][0].image.url,
            "https://exemplo.test/amber-atualizada.png",
        )


if __name__ == "__main__":
    unittest.main()
