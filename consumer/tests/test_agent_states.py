"""Estado dos agentes (config/qlik_use.txt) e flag de reinício (config/restart_pending)."""
import os
import time
from pathlib import Path

import pytest

import common


QLIK_USE = Path('config/qlik_use.txt')
RESTART_FLAG = Path('config/restart_pending')
ALL_STOPPED = ['agent1-stopped', 'agent2-stopped', 'agent3-stopped', 'agent4-stopped']


def write_states(content):
    QLIK_USE.parent.mkdir(parents=True, exist_ok=True)
    QLIK_USE.write_text(content, encoding='utf-8')


# --- read_agent_states -------------------------------------------------------

def test_cria_o_arquivo_com_os_quatro_agentes_parados():
    states = common.read_agent_states()

    assert states == ALL_STOPPED
    assert QLIK_USE.read_text(encoding='utf-8') == ' ## '.join(ALL_STOPPED)


def test_completa_agentes_ausentes_e_ordena():
    write_states('agent3-running ## agent1-stopped')

    assert common.read_agent_states() == [
        'agent1-stopped', 'agent2-stopped', 'agent3-running', 'agent4-stopped'
    ]


def test_ignora_trechos_vazios():
    write_states('agent1-running ##  ## agent2-stopped')

    assert common.read_agent_states() == [
        'agent1-running', 'agent2-stopped', 'agent3-stopped', 'agent4-stopped'
    ]


def test_conteudo_corrompido_gera_erro():
    """Documenta o comportamento atual: lixo no arquivo derruba quem lê o estado.
    Se o código passar a tolerar (ex.: recriar o arquivo), ajuste este teste."""
    write_states('conteudo invalido')

    with pytest.raises(ValueError):
        common.read_agent_states()


# --- set_agent_state / running_agents ----------------------------------------

def test_set_agent_state_altera_somente_o_proprio_agente():
    common.set_agent_state(2, 'running')

    assert common.read_agent_states() == [
        'agent1-stopped', 'agent2-running', 'agent3-stopped', 'agent4-stopped'
    ]

    common.set_agent_state(2, 'stopped')

    assert common.read_agent_states() == ALL_STOPPED


def test_running_agents_lista_quem_esta_rodando():
    common.set_agent_state(1, 'running')
    common.set_agent_state(2, 'running')

    assert common.running_agents() == ['agent1', 'agent2']


def test_running_agents_ignora_o_proprio_agente():
    common.set_agent_state(1, 'running')
    common.set_agent_state(2, 'running')

    assert common.running_agents(exclude=1) == ['agent2']
    assert common.running_agents(exclude=2) == ['agent1']


def test_running_agents_vazio_quando_todos_parados():
    assert common.running_agents(exclude=1) == []


# --- restart_pending ---------------------------------------------------------

def test_sem_flag_nao_ha_reinicio_pendente():
    assert common.restart_pending() is False


def test_flag_recente_indica_reinicio_pendente():
    RESTART_FLAG.parent.mkdir(parents=True, exist_ok=True)
    RESTART_FLAG.write_text('agora', encoding='utf-8')

    assert common.restart_pending() is True


def test_flag_esquecida_e_ignorada():
    RESTART_FLAG.parent.mkdir(parents=True, exist_ok=True)
    RESTART_FLAG.write_text('antiga', encoding='utf-8')
    old = time.time() - common.RESTART_FLAG_MAX_AGE - 60
    os.utime(RESTART_FLAG, (old, old))

    assert common.restart_pending() is False
