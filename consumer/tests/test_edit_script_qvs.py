"""edit_script_qvs: reescreve o script Initial do agente (P35: script vazio parava a VM)."""
import pytest

import common


SCRIPT_NAME = '[0]QS_Backend_Script_Standard_ScriptFile_Initial-prod1-agent1.qvs'
VARIABLE_LINES = (10, 13, 26, 29)  # linhas 11, 14, 27 e 30 do arquivo


def make_script(path, n_lines=40):
    lines = [f'linha original {i + 1}\n' for i in range(n_lines)]
    path.write_text(''.join(lines), encoding='utf-8')
    return lines


def read_lines(path):
    return path.read_text(encoding='utf-8').splitlines(keepends=True)


@pytest.fixture
def script(tmp_path):
    path = tmp_path / SCRIPT_NAME
    original = make_script(path)
    return path, original


def test_substitui_cliente_atividade_idioma_e_mes(script):
    path, _ = script

    common.edit_script_qvs(path, 'vmp_amil', 'Portal', 'Portugues', '10/2026')

    lines = read_lines(path)
    assert "let vG_ClientName  = 'VMP_AMIL';" in lines[10]
    assert "let vG_Atividadeda = 'Portal';" in lines[13]
    assert "let vG_Idioma = 'Portugues';" in lines[26]
    assert "LET vG_MesAnalise = '10/2026';" in lines[29]


def test_preserva_as_demais_linhas(script):
    path, original = script

    common.edit_script_qvs(path, 'empresa', 'Validar', 'Portugues', 'não')

    lines = read_lines(path)
    assert len(lines) == len(original)
    for index, line in enumerate(original):
        if index not in VARIABLE_LINES:
            assert lines[index] == line, f'linha {index + 1} foi alterada'


def test_sentinela_altera_apenas_o_cliente(script):
    path, original = script

    common.edit_script_qvs(path, 'cliente', 'ignorada', 'ignorado', 'ignorado', sentinel=True)

    lines = read_lines(path)
    assert "let vG_ClientName  = 'CLIENTE';" in lines[10]
    for index, line in enumerate(original):
        if index != 10:
            assert lines[index] == line


def test_grava_acentos_em_utf8(script):
    path, _ = script

    common.edit_script_qvs(path, 'são_joão', 'Processar', 'Portugues', 'não')

    lines = read_lines(path)
    assert "'SÃO_JOÃO'" in lines[10]
    assert "'não'" in lines[29]


@pytest.mark.parametrize('n_lines', [0, 1, 29])
def test_script_vazio_ou_curto_gera_erro_e_nao_altera_o_arquivo(tmp_path, n_lines):
    path = tmp_path / SCRIPT_NAME
    make_script(path, n_lines)
    before = path.read_bytes()

    with pytest.raises(ValueError, match='restaure'):
        common.edit_script_qvs(path, 'empresa', 'Validar', 'Portugues', 'não')

    assert path.read_bytes() == before
    assert not (tmp_path / (SCRIPT_NAME + '.tmp')).exists()


def test_sentinela_aceita_script_com_11_linhas(tmp_path):
    path = tmp_path / SCRIPT_NAME
    make_script(path, 11)

    common.edit_script_qvs(path, 'empresa', None, None, None, sentinel=True)

    assert "'EMPRESA'" in read_lines(path)[10]


def test_sentinela_com_10_linhas_gera_erro(tmp_path):
    path = tmp_path / SCRIPT_NAME
    make_script(path, 10)

    with pytest.raises(ValueError):
        common.edit_script_qvs(path, 'empresa', None, None, None, sentinel=True)


def test_falha_na_troca_preserva_o_original_e_remove_o_temporario(script, tmp_path, monkeypatch):
    path, _ = script
    before = path.read_bytes()

    def failing_replace(src, dst):
        raise OSError('disco cheio')

    monkeypatch.setattr(common.os, 'replace', failing_replace)

    with pytest.raises(OSError, match='disco cheio'):
        common.edit_script_qvs(path, 'empresa', 'Validar', 'Portugues', 'não')

    assert path.read_bytes() == before
    assert not (tmp_path / (SCRIPT_NAME + '.tmp')).exists()


def test_nao_deixa_arquivo_temporario_apos_sucesso(script, tmp_path):
    path, _ = script

    common.edit_script_qvs(path, 'empresa', 'Validar', 'Portugues', 'não')

    assert not (tmp_path / (SCRIPT_NAME + '.tmp')).exists()
