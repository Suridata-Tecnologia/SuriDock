"""save_logs: info no stdout, erro no stderr (o pm2 trata stderr como erro) e um arquivo por agente."""
import sys
from pathlib import Path

import pytest
from loguru import logger

import common


@pytest.fixture(autouse=True)
def restore_logger():
    yield
    logger.remove()  # fecha os arquivos de log abertos na pasta temporária
    logger.add(sys.stderr)


def test_info_vai_para_o_stdout_e_erro_para_o_stderr(capsys):
    common.save_logs(1)

    logger.info('mensagem de info')
    logger.warning('mensagem de aviso')
    logger.error('mensagem de erro')

    out, err = capsys.readouterr()
    assert 'mensagem de info' in out and 'mensagem de info' not in err
    assert 'mensagem de aviso' in out and 'mensagem de aviso' not in err
    assert 'mensagem de erro' in err and 'mensagem de erro' not in out


@pytest.mark.parametrize('agent_number, file_name', [
    (1, 'script-agent1.log'),
    (2, 'script-agent2.log'),
    (None, 'script-local.log'),
])
def test_cada_agente_tem_o_proprio_arquivo(agent_number, file_name):
    common.save_logs(agent_number)
    logger.info('registro')

    assert 'registro' in Path('logs', file_name).read_text(encoding='utf-8')


def test_apaga_o_log_da_execucao_anterior():
    log_file = Path('logs', 'script-agent1.log')
    log_file.parent.mkdir()
    log_file.write_text('execução anterior\n', encoding='utf-8')

    common.save_logs(1)
    logger.info('execução nova')

    content = log_file.read_text(encoding='utf-8')
    assert 'execução anterior' not in content
    assert 'execução nova' in content
