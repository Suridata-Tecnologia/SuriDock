from datetime   import datetime, timedelta
from pathlib    import Path
from time       import sleep
from tqdm       import tqdm

import os



CONFIG_PATH         = Path(__file__).resolve().parent.joinpath('config')
QLIK_USE_PATH       = CONFIG_PATH.joinpath('qlik_use.txt')
RESTART_FLAG_PATH   = CONFIG_PATH.joinpath('restart_pending')
MAX_WAIT_IDLE       = 2 * 3600 # tempo máximo esperando os agentes terminarem os jobs



def next_restart(seconds):
        x = datetime.now() + timedelta(seconds=seconds)
        return f'{str(x.hour).zfill(2)}:{str(x.minute).zfill(2)}:{str(x.second).zfill(2)} {str(x.day).zfill(2)}/{str(x.month).zfill(2)}/{x.year}'



def running_agents():
    try:
        content = QLIK_USE_PATH.read_text(encoding='utf-8')
    except FileNotFoundError:
        return []

    return [a.strip().split('-')[0] for a in content.split(' ## ') if a.strip().endswith('-running')]



def clear_stale_flag():
    # o "pm2 restart all" também reinicia este script, então a flag do restart anterior
    # ainda existe aqui. Espera os agentes subirem antes de liberá-los para pegar jobs.
    if RESTART_FLAG_PATH.exists():
        sleep(30)
        RESTART_FLAG_PATH.unlink(missing_ok=True)
        print('Flag de restart removida, agentes liberados para pegar jobs')



def wait_agents_idle():
    # cria a flag: os agentes param de pegar jobs novos e terminam o que estão fazendo
    CONFIG_PATH.mkdir(parents=True, exist_ok=True)
    RESTART_FLAG_PATH.write_text(datetime.now().isoformat(), encoding='utf-8')

    waited = 0
    while waited < MAX_WAIT_IDLE:
        agents = running_agents()
        if not agents:
            return True

        print(f'Aguardando {", ".join(agents)} terminar antes de reiniciar...')
        sleep(30)
        waited += 30

    print('Tempo máximo de espera atingido, reiniciando mesmo com agentes ocupados')
    return False



def wait_to_restart(seconds):
    formated_time = next_restart(seconds)
    for sec in tqdm(range(seconds), ascii=True, desc=f'Reiniciando suridock ás {formated_time}'):
        sleep(1)

    wait_agents_idle()
    # a flag continua existindo durante o restart; o novo restart.py a remove ao subir
    os.system('pm2 restart all')



clear_stale_flag()
wait_to_restart(10800) # 3 horas
