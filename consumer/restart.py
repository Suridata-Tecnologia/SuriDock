from datetime   import datetime, timedelta
from time       import sleep
from tqdm       import tqdm

import os



def next_restart(seconds):
        x = datetime.now() + timedelta(seconds=seconds)
        return f'{str(x.hour).zfill(2)}:{str(x.minute).zfill(2)}:{str(x.second).zfill(2)} {str(x.day).zfill(2)}/{str(x.month).zfill(2)}/{x.year}'



def wait_to_restart(seconds):
    formated_time = next_restart(seconds)
    for sec in tqdm(range(seconds), ascii=True, desc=f'Reiniciando suridock ás {formated_time}'):
        sleep(1)

    os.system('pm2 restart all')



wait_to_restart(10800) # 3 horas
