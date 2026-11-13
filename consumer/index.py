from consumer   import start_consumer, start_local
from common     import *

import traceback
import pyfiglet
import argparse


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent', '-a', type=int, required=False, help='Número do agente deve estar entre 1 a 2')
    parser.add_argument('--local', '-l', type=bool, required=False, help='Define se o consumer rodará localmente')
    return parser.parse_args()


agent_number = parse_args().agent
agent_local = parse_args().local

if not agent_local:
    if not agent_number or (agent_number >= 5 or agent_number <= 0):
        raise ValueError(f'o número do agente precisa estar entre 1 a 2')

print(pyfiglet.figlet_format('SuriDock', font='slant'))
save_logs(agent_number)

if agent_local:
    close_process('chrome')
    close_process('qlik')
else:
    # se este agente caiu no meio de um job, o estado dele ficou "running": zera
    set_agent_state(agent_number, 'stopped')

    # só fecha chrome/qlik se nenhum outro agente estiver no meio de um processo
    others = running_agents(exclude=agent_number)
    if others:
        logger.info(f'{", ".join(others)} usando o qlik, agent{agent_number} não vai fechar qlik e chrome')
    else:
        close_process('chrome')
        close_process('qlik')

while not agent_local:
    try:
        start_consumer(agent_number)
    except Exception as error:
        timeline_error = traceback.format_exc()
        logger.error(f'Erro desconhecido: {timeline_error}')
        sleep(30)

start_local()
