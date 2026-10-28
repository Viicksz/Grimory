from utils.sistemas import consultar_secao, listar_sistemas, secoes_sistema


def test_catalogo_de_sistemas_localiza_quadribol():
    sistemas = listar_sistemas()
    assert any(sistema.nome == "Sistema de Quadribol" for sistema in sistemas)


def test_secoes_preservam_regras_completas():
    secoes = secoes_sistema("Quadribol")
    titulos = {secao.titulo for secao in secoes}
    assert {"A partida", "Goles, passes e posse", "Manobras", "Faltas e pênaltis"} <= titulos
    assert "O Pomo não é capturado instantaneamente" in consultar_secao("Quadribol", "Gols, Pomos e Taça")
