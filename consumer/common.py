from selenium.webdriver.support         import expected_conditions as EC
from selenium.webdriver.support.ui      import WebDriverWait
from pywinauto.findwindows              import find_windows
from pywinauto                          import Application
from dotenv                             import load_dotenv
from selenium                           import webdriver
from database                           import Database
from selenium.webdriver.chrome.options  import Options
from selenium.webdriver.chrome.service  import Service
from loguru                             import logger
from time                               import sleep
from pathlib                            import Path
from selenium.webdriver.common.by       import By

import subprocess
import psutil
import os
import pika




load_dotenv()
MACHINE_NAME        = os.getenv('MACHINE_NAME')
RABBITMQ_HOST       = os.getenv('RABBITMQ_HOST')
RABBITMQ_USERNAME   = os.getenv('RABBITMQ_USERNAME')
RABBITMQ_PASSWORD   = os.getenv('RABBITMQ_PASSWORD')
RABBITMQ_MESSAGES   = os.getenv('RABBITMQ_MESSAGES')
logger.add('logs/script.log')



def connection_rabbitmq():
    credentials = pika.PlainCredentials(
        username=RABBITMQ_USERNAME,
        password=RABBITMQ_PASSWORD
    )

    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=5672,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=600,
        )
    )

    channel = connection.channel()
    return channel, connection



def find_qlik_path():
    qlik_path = Path.home().joinpath('AppData/Local/Programs/Qlik/Sense/QlikSenseBrowser/QlikSenseBrowser.exe')
    if qlik_path.exists():
        return qlik_path
    else:
        logger.error('Não foi possível encontrar a instalação do qlik')
        return False
    

def open_and_start_qlik(agent_number):
    qlik_path = find_qlik_path()
    if qlik_path:
        subprocess.Popen(qlik_path)
        sleep(5)
        app = Application(backend='uia').start(str(qlik_path))

        qlik_window = None
        window_list = []
        attempts = 0
        while not qlik_window and attempts < 10:
            attempts += 1
            for w in find_windows(backend='uia'):
                try:
                    window_list.append(app.window(handle=w).window_text())
                    if 'qlik sense desktop' in app.window(handle=w).window_text().lower():
                        qlik_window = w
                        break
                except Exception as error:
                    logger.error(f'Erro ao acessar a janela com handle {w}: {error}')
            sleep(10)

        if qlik_window:
            qlik_app = app.window(handle=qlik_window)
            qlik_app.set_focus()
            try:
                qlik_app.child_window(title='Iniciar', control_type='Button').click_input()
            except:
                logger.warning(f'agent{agent_number} não conseguiu clicar em "iniciar" no qlik')
            qlik_app.minimize()
            sleep(3)
            return qlik_app
    
    return False


def close_all_qlik_process():
    for proc in psutil.process_iter(['name']):
        if 'qlik' in proc.name().lower():
            proc.kill()


def is_qlik_running():
    qlik_path = find_qlik_path()
    if qlik_path:
        try:
            app = Application(backend="uia").connect(path=qlik_path)
        except:
            return False

        qlik_window = None
        window_list = []
        for w in find_windows(backend='uia'):
            try:
                window_list.append(app.window(handle=w).window_text())
                if 'qlik sense desktop' in app.window(handle=w).window_text().lower():
                    qlik_window = w
                    break
            except Exception as error:
                logger.error(f'Erro ao acessar a janela com handle {w}: {error}')

        if qlik_window:
            qlik_app = app.window(handle=qlik_window)
            return qlik_app

    return False


def has_gestao_pos(drive_folder):
        data = Database().find_all(
            table_name='companies',
            left_on='operator_id',
            condition=f'companies.drive_path = "{drive_folder}"',
            columns=['companies.suridata_product']
        )

        if len(data) == 0:
            return False
        
        if data[0]['suridata_product'].lower() == 'gestão pós':
            return True
        
        return False


def get_path_script_qvs(qvd_path, agent_number):
    if MACHINE_NAME.lower() == 'homologação':
        script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-homo-bot{agent_number}.qvs')
    elif MACHINE_NAME.lower() == 'produção 1':
        script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-prod1-bot{agent_number}.qvs')
    elif MACHINE_NAME.lower() == 'produção 2':
        script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-prod2-bot{agent_number}.qvs')
    elif MACHINE_NAME.lower() == 'produção 3':
        script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-prod3-bot{agent_number}.qvs')
    else:
        logger.error(f'Máquina não identificada: {MACHINE_NAME}')
        quit()

    return script_path


def edit_script_qvs(script_path, company_name, narrative, month_analysis):
    with open(script_path, 'r', encoding='utf-8') as f:
        script_lines = f.readlines()

    gestao_pos = False
    if narrative == 'False':
        gestao_pos = has_gestao_pos(company_name)

    script_lines[10] = f"let vG_ClientName  = '{company_name.upper()}'; //<--- NOME DO CLIENTE EM LETA minúscula - conforme pasta do Drive\n"
    if gestao_pos:
        script_lines[13] = f"let vG_Atividadeda = 'Processar';  // o que você quer fazer?\n"
    else:
        script_lines[13] = f"let vG_Atividadeda = 'Analisar';  // o que você quer fazer?\n"

    if narrative == 'False':
        script_lines[26] = f"let vG_Idioma = 'Portugues'; // <--- Idioma em que se deseja apresentar os slides depois do reload (sem acento). Valores possíveis:\n"
    else:
        script_lines[26] = f"let vG_Idioma = 'Ingles'; // <--- Idioma em que se deseja apresentar os slides depois do reload (sem acento). Valores possíveis:\n"

    script_lines[29] = f"LET vG_MesAnalise = '{month_analysis}';          // não -> padrão \n"
    
    with open(script_path, 'w', encoding='utf-8') as f:
        f.writelines(script_lines)

    logger.info(f'Editou o arquivo do qlik pra rodar a empresa {company_name}')


def init_browser(download_path):

    service = Service()
    chrome_options = Options()
    chrome_options.add_experimental_option('prefs', {
        "download": {
            "prompt_for_download": False,
            "default_directory": str(download_path)
        }
    })

    return webdriver.Chrome(service=service, options=chrome_options)


def prepare_page_to_process(driver, wait, agent_number):
    driver.get('http://localhost:4848/hub/my/work')
    driver.maximize_window()

    try: # colocado um try por conta do spam não aparecer a vezes
        wait.until(EC.presence_of_element_located((By.XPATH, '/html/body/div[2]/div/div/div/div[2]/div[1]/button/span')))
        driver.find_element(By.XPATH, '/html/body/div[2]/div/div/div/div[2]/div[1]/button/span').click()
    except:
        pass

    # clicando no app
    driver.find_element(By.XPATH, f'/html/body/div[1]/main/div/div/div[2]/div/div/div/div/ul/li[{agent_number}]/div/div[3]/div[1]').click()
    sleep(5)

    # seleciona a nova guia (app) que foi aberta
    driver.switch_to.window(driver.window_handles[1])
    sleep(2)

    wait.until(EC.presence_of_element_located((By.ID, 'navigation-dropdown-button'))).click() # Dropdown: Pasta
    wait.until(EC.presence_of_element_located((By.ID, 'navlist-item-dataSpaceScriptEditor'))).click() # Botão do dropdown "Editor da carga de dados"
    sleep(5)


def process_company(driver, wait):
    while True:
        sleep(10) # espera a página carregar
        try:
            # Botão do qlik "Carregar dados"
            driver.find_element(By.XPATH, '/html/body/div[4]/div[3]/div/qmfe-embed-react/qmfe-root/div/div[1]/div[1]/div[2]/div[3]/button[3]').click()
            break
        except:
            pass
    sleep(5)

    while True:
        sleep(10)
        try:
            # Botão do qlik "Continuar editando"
            driver.find_element(By.XPATH, '/html/body/div[9]/div[3]/div/div[2]/div/div/button').click()
            break
        except:
            pass
    sleep(2)


def publish_message_discord(message, discord_user_id=None):
    if discord_user_id:
        message = f'<@{discord_user_id}> {message}'
    
    channel, connection = connection_rabbitmq()
    channel.queue_declare(queue=RABBITMQ_MESSAGES, durable=True)
    channel.basic_publish(
        exchange='',
        routing_key=RABBITMQ_MESSAGES,
        body=message
    )
    connection.close()