from common     import close_all_qlik_process
from consumer   import start_consumer

import pyfiglet
import argparse


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent', '-a', type=int, required=True, help='Número do agente deve estar entre 1 a 4')
    return parser.parse_args()


agent_number = parse_args().agent
if agent_number >= 5 or agent_number <= 0:
    raise ValueError(f'o número do agente precisa estar entre 1 a 4')



print(pyfiglet.figlet_format('SuriDock', font='slant'))
close_all_qlik_process()
start_consumer(agent_number)
