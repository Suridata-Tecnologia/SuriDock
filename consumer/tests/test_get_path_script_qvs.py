"""get_path_script_qvs: escolhe o script Initial de cada máquina e agente."""
import pytest

import common


def script_name(prefix, agent_number):
    return f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-{prefix}{agent_number}.qvs'


@pytest.fixture
def drive(tmp_path):
    qvd_path = tmp_path / 'Ambiente de Produção' / '_QVD'
    scripts_path = tmp_path / 'Ambiente de Produção' / '_QSScripts'
    qvd_path.mkdir(parents=True)
    scripts_path.mkdir()
    return qvd_path, scripts_path


@pytest.mark.parametrize('machine, sentinel, agent, prefix', [
    ('produção 1', False, 1, 'prod1-agent'),
    ('produção 1', True, 1, 'Sentinel1-agent'),
    ('produção 2', False, 2, 'prod2-agent'),
    ('produção 2', True, 2, 'Sentinel2-agent'),
    ('produção 3', False, 1, 'prod3-agent'),
    ('Produção 4', False, 2, 'prod4-agent'),  # MACHINE_NAME não diferencia maiúsculas
    ('Produção 4', True, 1, 'Sentinel4-agent'),
    ('homologação', False, 1, 'homo-bot'),
])
def test_escolhe_o_script_pela_maquina_e_pelo_tipo(monkeypatch, drive, os_system_calls,
                                                    machine, sentinel, agent, prefix):
    qvd_path, scripts_path = drive
    expected = scripts_path / script_name(prefix, agent)
    expected.write_text('conteúdo', encoding='utf-8')
    monkeypatch.setattr(common, 'MACHINE_NAME', machine)

    path = common.get_path_script_qvs(qvd_path, agent, sentinel=sentinel)

    assert path == expected
    assert os_system_calls == []


def test_maquina_desconhecida_encerra_o_agente(monkeypatch, drive):
    qvd_path, _ = drive
    monkeypatch.setattr(common, 'MACHINE_NAME', 'vm-desconhecida')

    with pytest.raises(SystemExit):
        common.get_path_script_qvs(qvd_path, 1)


def test_script_ausente_derruba_todos_os_agentes_da_vm(monkeypatch, drive, os_system_calls):
    """Documenta o comportamento atual (P21): se o Drive não estiver montado ou o script
    não existir, o agente roda 'pm2 delete all' e a VM inteira para de processar.
    Se esse comportamento mudar (ex.: lançar uma exceção), ajuste este teste."""
    qvd_path, _ = drive
    monkeypatch.setattr(common, 'MACHINE_NAME', 'produção 1')

    common.get_path_script_qvs(qvd_path, 1)

    assert os_system_calls == ['pm2 delete all']
