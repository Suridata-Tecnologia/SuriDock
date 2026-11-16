"""restart.py: reinício de 3 em 3 horas sem abortar jobs em andamento (P36)."""
import pytest

import common
import restart as restart_module


@pytest.fixture
def restart(tmp_path, monkeypatch):
    # os caminhos do restart.py são absolutos (pasta do consumer): aponta para a pasta temporária
    config = tmp_path / 'config'
    monkeypatch.setattr(restart_module, 'CONFIG_PATH', config)
    monkeypatch.setattr(restart_module, 'QLIK_USE_PATH', config / 'qlik_use.txt')
    monkeypatch.setattr(restart_module, 'RESTART_FLAG_PATH', config / 'restart_pending')
    monkeypatch.setattr(restart_module, 'sleeps', [], raising=False)
    monkeypatch.setattr(restart_module, 'sleep', lambda seconds: restart_module.sleeps.append(seconds))
    return restart_module


def test_running_agents_sem_arquivo_devolve_lista_vazia(restart):
    assert restart.running_agents() == []


def test_le_o_mesmo_formato_gravado_pelos_agentes(restart):
    common.set_agent_state(1, 'running')
    common.set_agent_state(3, 'running')

    assert restart.running_agents() == ['agent1', 'agent3']


def test_flag_criada_pelo_restart_e_vista_pelos_agentes(restart):
    assert common.restart_pending() is False

    restart.wait_agents_idle()

    assert restart.RESTART_FLAG_PATH.exists()
    assert common.restart_pending() is True


def test_reinicia_na_hora_quando_nenhum_agente_esta_ocupado(restart):
    assert restart.wait_agents_idle() is True
    assert restart.sleeps == []


def test_espera_o_agente_terminar_antes_de_reiniciar(restart, monkeypatch):
    common.set_agent_state(2, 'running')

    def finish_job(seconds):
        restart.sleeps.append(seconds)
        common.set_agent_state(2, 'stopped')

    monkeypatch.setattr(restart, 'sleep', finish_job)

    assert restart.wait_agents_idle() is True
    assert restart.sleeps == [30]


def test_desiste_de_esperar_apos_o_tempo_maximo(restart, monkeypatch):
    common.set_agent_state(1, 'running')
    monkeypatch.setattr(restart, 'MAX_WAIT_IDLE', 60)

    assert restart.wait_agents_idle() is False
    assert restart.sleeps == [30, 30]


def test_clear_stale_flag_remove_a_flag_do_reinicio_anterior(restart):
    restart.CONFIG_PATH.mkdir(parents=True)
    restart.RESTART_FLAG_PATH.write_text('anterior', encoding='utf-8')

    restart.clear_stale_flag()

    assert not restart.RESTART_FLAG_PATH.exists()
    assert restart.sleeps == [30]


def test_clear_stale_flag_sem_flag_nao_espera(restart):
    restart.clear_stale_flag()

    assert restart.sleeps == []


def test_wait_to_restart_cria_a_flag_e_reinicia_o_pm2(restart, os_system_calls):
    restart.wait_to_restart(2)

    assert restart.RESTART_FLAG_PATH.exists()
    assert os_system_calls == ['pm2 restart all']
