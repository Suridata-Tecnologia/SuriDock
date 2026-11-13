from selenium.webdriver.support                 import expected_conditions as EC
from pathlib                                    import Path, WindowsPath
from urllib.parse                               import urlparse, unquote
from extensions.google_cloud                    import GoogleFirestore
from selenium.webdriver.support.ui              import WebDriverWait
from selenium.webdriver                         import ActionChains
from pywinauto.findwindows                      import find_windows
from pywinauto                                  import Application
from dotenv                                     import load_dotenv
from shutil                                     import copy, move
from base64                                     import b64encode
from selenium                                   import webdriver
from database                                   import Database
from datetime                                   import datetime
from zoneinfo                                   import ZoneInfo
from selenium.webdriver.chrome.options          import Options
from selenium.webdriver.chrome.service          import Service
from zipfile                                    import ZipFile
from loguru                                     import logger
from time                                       import sleep, monotonic
from contextlib                                 import contextmanager
from selenium.webdriver.common.by               import By
from selenium.common.exceptions                 import TimeoutException, ElementClickInterceptedException
from selenium.webdriver.common.keys             import Keys
from anticaptchaofficial.recaptchav2proxyless   import *

import subprocess
import threading
import requests
import psutil
import pika
import json
import os
import msvcrt
import re
import sys



load_dotenv()
CAPTCHA_KEY         = os.getenv('CAPTCHA_KEY')
MACHINE_NAME        = os.getenv('MACHINE_NAME')
RABBITMQ_HOST       = os.getenv('RABBITMQ_HOST')
RABBITMQ_USERNAME   = os.getenv('RABBITMQ_USERNAME')
RABBITMQ_PASSWORD   = os.getenv('RABBITMQ_PASSWORD')
RABBITMQ_MESSAGES   = os.getenv('RABBITMQ_MESSAGES')
RABBITMQ_FIVEPAGE   = os.getenv('RABBITMQ_FIVEPAGE')
LOCAL_MODE          = False



fuso_brasilia = ZoneInfo("America/Sao_Paulo")
link_to_suripoint = 'https://suripoint-backend-87769041781.us-east1.run.app/' # Produção
# link_to_suripoint = 'https://suripoint-backend-hom-87769041781.us-east1.run.app/' # Homologação



def save_logs(agent_number=None):
    # um arquivo por agente: se todos usassem o mesmo, um agente não conseguiria
    # apagá-lo enquanto o outro está com ele aberto (WinError 32)
    log_name = f'script-agent{agent_number}.log' if agent_number else 'script-local.log'
    logs_path = Path.cwd().joinpath('logs', log_name)
    if logs_path.exists():
        try:
            logs_path.unlink()
        except Exception as error:
            logger.error(f'não foi possível excluir o arquivo de logs: {error}')

    # console: o loguru escreve tudo no stderr por padrão, e o pm2 marca stderr como erro
    # (prefixo vermelho e arquivo *-error.log). Info/warning vão para o stdout, só erros para o stderr.
    logger.remove()
    logger.add(sys.stdout, level='DEBUG', filter=lambda record: record['level'].no < 40)
    logger.add(sys.stderr, level='ERROR')

    # salva os logs
    logger.add(logs_path)

    
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


def set_local_mode(enabled=True):
    global LOCAL_MODE
    LOCAL_MODE = enabled


def is_local_mode():
    return LOCAL_MODE


def publish_message_discord(message_data):
    if LOCAL_MODE:
        return

    channel, connection = connection_rabbitmq()
    channel.queue_declare(queue=RABBITMQ_MESSAGES, durable=True)
    channel.basic_publish(
        exchange='',
        routing_key=RABBITMQ_MESSAGES,
        body=json.dumps(message_data).encode('utf-8')
    )
    connection.close()


def publish_message_fivepage(message_data):    
    if LOCAL_MODE:
        return

    channel, connection = connection_rabbitmq()
    channel.queue_declare(queue=RABBITMQ_FIVEPAGE, durable=True)
    channel.basic_publish(
        exchange='',
        routing_key=RABBITMQ_FIVEPAGE,
        body=json.dumps(message_data).encode('utf-8')
    )
    connection.close()


def find_qlik_path():
    qlik_path = Path.home().joinpath('AppData/Local/Programs/Qlik/Sense/QlikSenseBrowser/QlikSenseBrowser.exe')
    if qlik_path.exists():
        return qlik_path
    else:
        logger.error('Não foi possível encontrar a instalação do qlik')
        return False
    

def wait_qlik_hub(timeout=180):
    # o engine do qlik só sobe a porta 4848 depois do "iniciar"
    for _ in range(timeout // 5):
        try:
            if requests.get('http://localhost:4848/hub/my/work', timeout=5).status_code == 200:
                return True
        except requests.RequestException:
            pass
        sleep(5)
    return False


def open_and_start_qlik(agent_number):
    qlik_path = find_qlik_path()
    if qlik_path:
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
            try:
                # o conteúdo da janela (e o botão) carrega alguns segundos depois da janela aparecer
                start_button = qlik_app.child_window(title='Iniciar', control_type='Button')
                start_button.wait('exists enabled', timeout=90, retry_interval=2)
                # clica via automação (funciona mesmo com a sessão minimizada/RDP desconectado).
                # o invoke() pode ficar bloqueado até o qlik terminar de iniciar, por isso roda numa thread
                threading.Thread(target=start_button.invoke, daemon=True).start()
            except Exception as error:
                logger.warning(f'agent{agent_number} não conseguiu clicar em "iniciar" no qlik: {error}')

            if wait_qlik_hub():
                logger.info(f'agent{agent_number} iniciou o qlik (hub respondendo na porta 4848)')
            else:
                logger.error(f'agent{agent_number}: hub do qlik não respondeu na porta 4848 após clicar em "iniciar"')
            qlik_app.minimize()
            sleep(3)
            return qlik_app

        qlik_titles = sorted({t for t in window_list if 'qlik' in t.lower()})
        logger.error(f'agent{agent_number}: abriu o qlik mas não encontrou a janela "Qlik Sense Desktop" '
                     f'após {attempts} tentativas. Janelas do qlik encontradas: {qlik_titles}')

    return False


def close_process(process_name):
    try:
        for proc in psutil.process_iter(['name']):
            if process_name in proc.name().lower():
                proc.kill()
    except Exception as error:
        logger.error(f'psutil não conseguiu fechar o {process_name}: {error}')


QLIK_USE_PATH       = Path('config/qlik_use.txt')
RESTART_FLAG_PATH   = Path('config/restart_pending')
RESTART_FLAG_MAX_AGE = 2 * 3600 + 600  # flag mais velha que isso é considerada esquecida
AGENT_SLOTS         = 4


def read_agent_states():
    # config/qlik_use.txt: "agent1-stopped ## agent2-running ## ..." - estado de cada agente
    if not QLIK_USE_PATH.exists():
        QLIK_USE_PATH.parent.mkdir(parents=True, exist_ok=True)
        QLIK_USE_PATH.write_text(
            ' ## '.join(f'agent{n}-stopped' for n in range(1, AGENT_SLOTS + 1)),
            encoding='utf-8'
        )

    agents = [a.strip() for a in QLIK_USE_PATH.read_text(encoding='utf-8').split(' ## ') if a.strip()]
    present = {a.split('-')[0] for a in agents}
    for n in range(1, AGENT_SLOTS + 1):
        if f'agent{n}' not in present:
            agents.append(f'agent{n}-stopped')

    return sorted(agents, key=lambda a: int(a.split('-')[0].replace('agent', '')))


def set_agent_state(agent_number, state):
    agents = read_agent_states()
    agents[agent_number - 1] = f'agent{agent_number}-{state}'
    QLIK_USE_PATH.write_text(' ## '.join(agents), encoding='utf-8')


def running_agents(exclude=None):
    # lista os agentes marcados como "running", ignorando o próprio agente (exclude)
    return [
        a.split('-')[0] for a in read_agent_states()
        if a.endswith('-running') and a.split('-')[0] != f'agent{exclude}'
    ]


def restart_pending():
    # o restart.py cria essa flag para os agentes pararem de pegar jobs novos antes do "pm2 restart all"
    if not RESTART_FLAG_PATH.exists():
        return False

    try:
        age = datetime.now().timestamp() - RESTART_FLAG_PATH.stat().st_mtime
    except FileNotFoundError:
        return False

    return age < RESTART_FLAG_MAX_AGE


QLIK_LOCK_PATH = Path('config/qlik_start.lock')


@contextmanager
def qlik_start_lock(agent_number, timeout=900):
    # trava entre os agentes para só um abrir/reiniciar o qlik por vez. Se os dois abrem
    # ao mesmo tempo, as instâncias brigam e nenhum agente encontra a janela.
    # usa lock do Windows no arquivo: é liberado automaticamente se o processo morrer.
    QLIK_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(QLIK_LOCK_PATH, 'a+')
    started = monotonic()
    waiting_logged = False

    try:
        while True:
            try:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if not waiting_logged:
                    logger.info(f'agent{agent_number} aguardando outro agente terminar de abrir o qlik...')
                    waiting_logged = True
                if monotonic() - started > timeout:
                    raise TimeoutError(f'agent{agent_number} esperou {timeout}s pela trava de abertura do qlik')
                sleep(2)

        try:
            yield
        finally:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        lock_file.close()


def ensure_qlik_ready(agent_number):
    # garante que o hub do qlik responde na porta 4848 (só a janela existir não basta)
    with qlik_start_lock(agent_number):
        # caminho comum: qlik já aberto e funcionando (inclusive se outro agente acabou de abrir)
        if wait_qlik_hub(timeout=5):
            return True

        if is_qlik_running():
            # janela aberta: pode estar terminando de iniciar, dá um tempo
            if wait_qlik_hub(timeout=60):
                return True
            logger.warning(f'agent{agent_number}: janela do qlik aberta mas o hub (porta 4848) não responde, reiniciando o qlik...')

        # hub fora do ar: nenhum agente consegue estar usando o qlik, então é seguro
        # matar o que sobrou (processos travados/sem janela) antes de abrir de novo
        close_process('qlik')
        sleep(5)

        if not open_and_start_qlik(agent_number):
            return False

        return wait_qlik_hub(timeout=10)


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


def get_path_script_qvs(qvd_path, agent_number, sentinel=False):
    machine = MACHINE_NAME.lower()

    mapping = {
        'lucas': ('Sentinel-lucas', 'lucas-bot'),
        'nathalia': ('Sentinel-nathalia', 'nathalia-bot'),
        'luiza': ('Sentinel-luiza', 'luiza-bot'),
        'homologação': ('SentinelTESTE', 'homo-bot'),
        'produção 1': ('Sentinel1-agent', 'prod1-agent'),
        'produção 2': ('Sentinel2-agent', 'prod2-agent'),
        'produção 3': ('Sentinel3-agent', 'prod3-agent'),
        'produção 4': ('Sentinel4-agent', 'prod4-agent'),
    }

    if machine not in mapping:
        logger.error(f'Máquina não identificada: {MACHINE_NAME}')
        quit()

    prefix = mapping[machine][0 if sentinel else 1]

    filename = f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-{prefix}{agent_number}.qvs'

    script_path = qvd_path.parent.joinpath('_QSScripts', filename)
    if not script_path.exists():
        logger.error('app google drive fechado, fechando consumers...')
        os.system('pm2 delete all')

    return script_path


def edit_script_qvs(script_path, company_name, activity, language, month_analysis, sentinel=False):
    with open(script_path, 'r', encoding='utf-8') as f:
        script_lines = f.readlines()

    min_lines = 11 if sentinel else 30
    if len(script_lines) < min_lines:
        raise ValueError(
            f'Script {script_path} tem {len(script_lines)} linhas (mínimo {min_lines}). '
            'O arquivo pode estar vazio/corrompido - restaure-o antes de rodar.'
        )

    script_lines[10] =f"let vG_ClientName  = '{company_name.upper()}'; //<--- NOME DO CLIENTE EM LETA minúscula - conforme pasta do Drive\n"
    if not sentinel:
        script_lines[13] = f"let vG_Atividadeda = '{activity}';  // o que você quer fazer?\n"
        script_lines[26] = f"let vG_Idioma = '{language}'; // <--- Idioma em que se deseja apresentar os slides depois do reload (sem acento). Valores possíveis:\n"
        script_lines[29] = f"LET vG_MesAnalise = '{month_analysis}';          // não -> padrão \n"
        
    # grava num arquivo temporário e só depois substitui o original, para que
    # uma interrupção no meio da escrita não deixe o .qvs vazio
    tmp_path = Path(script_path).with_name(Path(script_path).name + '.tmp')
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.writelines(script_lines)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, script_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    logger.info(f'Editou o arquivo {script_path} do qlik pra rodar a empresa {company_name}')


def init_browser(download_path='.'):
    service = Service()
    chrome_options = Options()
    chrome_options.add_experimental_option('prefs', {
        "download": {
            "prompt_for_download": False,
            "default_directory": str(download_path)
        }
    })

    return webdriver.Chrome(service=service, options=chrome_options)


def close_qlik_modal(driver, timeout=5):
    # o hub do qlik às vezes abre um pop-up (spam) que cobre a lista de apps;
    # ele reaparece a cada recarregamento do hub, então precisa ser fechado antes de cada clique
    try:
        WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, '/html/body/div[2]/div/div/div/div[2]/div[1]/button/span'))
        ).click()
    except Exception:
        pass

    modal = (By.CSS_SELECTOR, '.lui-modal-background')
    try:
        WebDriverWait(driver, 10).until(EC.invisibility_of_element_located(modal))
        return
    except TimeoutException:
        pass

    # botão de fechar não encontrado: tenta fechar com ESC
    logger.warning('Pop-up do Qlik continua aberto, tentando fechar com ESC...')
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    try:
        WebDriverWait(driver, 5).until(EC.invisibility_of_element_located(modal))
    except TimeoutException:
        logger.warning('Não foi possível fechar o pop-up do Qlik')


def navigate_to_process(driver, wait, agent_number, sentinel=False, app_name=False):
    driver.get('http://localhost:4848/hub/my/work')
    driver.maximize_window()

    close_qlik_modal(driver, timeout=wait._timeout)

    if not app_name:
        app_name = f'sentinel{agent_number}' if sentinel else f'agent{agent_number}'

    # o hub pode demorar (ou o Qlik Desktop pode estar iniciando): tenta algumas vezes recarregando
    apps = None
    for attempt in range(3):
        try:
            apps = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.hub-ul.qv-grid.ng-scope > li')))
            break
        except TimeoutException:
            logger.warning(f'Lista de apps do Qlik não carregou (tentativa {attempt + 1}/3), recarregando o hub...')
            driver.get('http://localhost:4848/hub/my/work')

    if not apps:
        raise TimeoutException(
            'Hub do Qlik (localhost:4848) não listou os apps. '
            'Verifique se o Qlik Sense Desktop está aberto e logado, e se o hub está em modo grade.'
        )

    close_qlik_modal(driver)

    for app in apps:
        if app_name in app.text.lower():
            try:
                app.click() # clica no app correto
            except ElementClickInterceptedException:
                logger.warning(f'Clique no app {app_name} interceptado por outro elemento, clicando via JavaScript')
                close_qlik_modal(driver)
                driver.execute_script('arguments[0].click();', app)
            sleep(1)
            break
    
    # seleciona a nova guia (app) que foi aberta
    driver.switch_to.window(driver.window_handles[1])
    sleep(5)

    for _ in range(20):
        try:
            wait.until(EC.presence_of_element_located((By.ID, 'navigation-dropdown-button'))).click() # Dropdown: Pasta
            wait.until(EC.presence_of_element_located((By.ID, 'navlist-item-dataSpaceScriptEditor'))).click() # Botão do dropdown "Editor da carga de dados"
            break
        except:
            pass

    sleep(10)


def find_id_of_button(driver):
        for x in range(5, 15):
            try:
                # Botão do qlik "Continuar editando"
                button = driver.find_element(By.XPATH, f'/html/body/div[{x}]/div[3]/div/div[2]/div/div/button')
                return button, x
            except:
                pass

        return None, None


def process_company(driver):
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
            button, id_div = find_id_of_button(driver)
            if not button and not id_div:
                continue

            try:
                error = driver.find_element(By.XPATH, f'/html/body/div[{id_div}]/div[3]/div/div[1]/div/div[1]/p')
                if error.text.lower() == 'carga de dados não concluída.':
                    driver.quit()
                    return False
            except:
                pass
            
            button.click()
            return True
        except:
            pass


def wait_qlik_create_ppt(driver):
    download_button = None
    trys = 0

    while not download_button and trys < 600:
        try:
            download_button = driver.find_element(By.XPATH, '/html/body/div[7]/div/div/div[2]/div[2]/div[6]/div/a')
            break
        except:
            download_button = None

        try:
            driver.find_element(By.XPATH, '/html/body/div[7]/div/div/div[2]/div[2]/div[6]/div/p')
            driver.find_element(By.XPATH, '/html/body/div[7]/div/div/div[2]/div[3]/button[2]').click()
        except:
            pass

        trys += 1
        sleep(3)

    return download_button


def navigate_to_export(driver, wait, narrative, gestao_pos):
    wait.until(EC.presence_of_element_located((By.ID, 'navigation-dropdown-button'))).click() # Dropdown: Editor da carga de dados
    wait.until(EC.presence_of_element_located((By.ID, 'navlist-item-story'))).click() # Botão do dropdown "Narrativa"
    sleep(10)

    if not narrative:
        if gestao_pos:
            # PÓS - Relatório Gestão de Saúde e Risco
            wait.until(EC.presence_of_element_located((By.XPATH, '/html/body/div[4]/div[4]/div/div[1]/div[1]/qmfe-embed-react/qmfe-root/div/div/div/qmfe-embed-react/qmfe-root/div[1]/div[4]/div/div[1]/div/div/div[4]/div/div/div/div[1]/button'))).click()
            sleep(10)
        else:
            # Relatório Gestão de Saúde e Risco (12 meses)(NOVO)
            # Não clica em nada porque ja está selecionado por padrão
            pass
    else:
        # Relatório Gestão INGLÊS
        wait.until(EC.presence_of_element_located((By.XPATH, '/html/body/div[4]/div[4]/div/div[1]/div[1]/qmfe-embed-react/qmfe-root/div/div/div/qmfe-embed-react/qmfe-root/div[1]/div[4]/div/div[1]/div/div/div[3]/div/div/div/div[1]/button'))).click()
        sleep(10)

    # Botão reproduzir
    driver.find_element(By.XPATH, '/html/body/div[4]/div[3]/div[2]/button[3]').click()
    sleep(10)

    wait.until(EC.presence_of_element_located((By.XPATH, '/html/body/div[4]/div[4]/div/div[2]/div[3]/div[2]/button'))).click() # Botão 3 pontinhos
    wait.until(EC.presence_of_element_located((By.XPATH, '/html/body/div[4]/div[4]/div/div[2]/div[3]/div[2]/div/button[3]'))).click() # Botão exportar
    wait.until(EC.presence_of_element_located((By.XPATH, '/html/body/div[7]/div/div/div/ng-transclude/div/ul/li[1]/span'))).click() # Botão exportar para o PowerPoint
    sleep(3)
    
    # Digita o tamanho da folha em largura
    input_tag = driver.find_element(By.XPATH, '/html/body/div[7]/div/div/div[2]/div[2]/div[2]/span/input')
    input_tag.clear()
    input_tag.send_keys('1220')

    # Digita o tamanho da folha em altura
    input_tag = driver.find_element(By.XPATH, '/html/body/div[7]/div/div/div[2]/div[2]/div[3]/span/input')
    input_tag.clear()
    input_tag.send_keys('740')

    # Botão exportar
    driver.find_element(By.XPATH, '/html/body/div[7]/div/div/div[2]/div[3]/button[2]').click()
    sleep(1)

    download_button = wait_qlik_create_ppt(driver)
    if download_button:
        download_button.click()
        sleep(10)
    else:
        logger.error('o qlik não conseguiu gerar o link para download do ppt')
        driver.quit()
        return False
    
    return True


def wait_until_download_finish(download_path, driver):
        while True:
            sleep(1)
            if not '.crdownload' in [ file.suffix for file in download_path.rglob('*.*') ]:
                break

        sleep(3)
        driver.quit()


def get_url_fivepage(drive_folder):
    data = Database().find_pretty_name_and_operator_name(drive_folder)[0]

    base_dashboard_param = b64encode(bytes(str(data['dashboard_param']), 'utf-8')).decode()
    base_company_id      = b64encode(bytes(str(data['id']), 'utf-8')).decode()
    base_onepage         = b64encode(bytes(str('One Page'), 'utf-8')).decode()

    return f'https://portal.suridata.com.br/dashboard/{base_company_id}/bmFu/{base_onepage}/{base_dashboard_param}/1', data['dashboard_param']


def get_pretty_name(company_name):
    data = Database().find_pretty_name_and_policy(company_name)
    try:
        company_pretty_name = data[0]['dashboard_param']
        audit_date          = data[0]['audit_date']
        suridata_product    = data[0]['suridata_product']
    except Exception as error:
        company_pretty_name = company_name
        audit_date = None
        suridata_product = None
        logger.error(f'Erro ao fazer consulta no banco: {error}')

    return company_pretty_name, audit_date, suridata_product


def need_audith(user_audith, company_pretty_name, audit_date, suridata_product, discord_user_id):
    is_trello = False if discord_user_id else True
    is_audith = False

    if audit_date and suridata_product:
        month_from_db = audit_date.split('-')[1]
        month_current = str(datetime.now(fuso_brasilia).month).zfill(2)

        logger.info(f'month_current: {month_current} | month_from_db: {month_from_db} | suridata_product: {suridata_product}')

        if suridata_product.lower() == 'controle 300' or suridata_product.lower() == 'controle 6m':
            month_lists = ['01-07', '02-08', '03-09', '04-10', '05-11', '06-12']
            for x in range(len(month_lists)):
                if month_from_db in month_lists[x]:
                    if month_current in month_lists[x]:
                        is_audith = True
                        break

        elif suridata_product.lower() == 'controle' or suridata_product.lower() == 'suri beta' or suridata_product.lower() == 'controle sct' or suridata_product.lower() == 'gestão':
            month_lists = ['01-04-07-10', '02-05-08-11', '03-06-09-12']
            for x in range(len(month_lists)):
                if month_from_db in month_lists[x]:
                    if month_current in month_lists[x]:
                        is_audith = True
                        break

    if is_audith:
        logger.info(f'{company_pretty_name} - esse relatório precisa de auditoria')
    else:
        logger.info(f'{company_pretty_name} - esse relatório não precisa de auditoria')

    if not is_trello:
        if not user_audith:
            is_audith = False
            logger.info(f'usuário alterou auditoria para: False')
        elif user_audith:
            is_audith = True
            logger.info(f'usuário alterou auditoria para: True')
        else:
            logger.info(f'usuário não fez alterações na auditoria: {is_audith}')

    return is_audith


def backup_to_drive(file, qvd_path, company_name):
    destination = qvd_path.joinpath(company_name, 'base', 'Validação Automática', file.name)

    if not destination.parent.exists():
        destination.parent.mkdir(parents=True)

    copy(file, destination)
    logger.info(f'Arquivo bruto salvo em: {str(destination)}')


def run_in_suripoint(file, is_audith):
    ppt_file = file.parent
    files=[('file',(file.stem, open(file,'rb'),'application/vnd.openxmlformats-officedocument.presentationml.presentation'))]
    response = requests.request('POST', f'{link_to_suripoint}/ppt/process', data={'originalFilename': file.name}, files=files, params={'audity': str(is_audith).lower()})

    if response.status_code == 200:
        url = response.json()['downloadLink']
        file_name = unquote(urlparse(url).path.split('/')[-1])
        ppt_file = ppt_file.joinpath(file_name)
        response = requests.request('GET', url)

        with open(ppt_file, 'wb') as f:
            f.write(response.content)

    logger.info(f'ppt baixado {ppt_file}')

    return ppt_file


def move_file(current_path, new_path, delete_on_move=True, backup_old_file=True):
    # Verifica se os objetos recebidos são do tipo WindowsPath
    if not (isinstance(current_path, WindowsPath) and isinstance(new_path, WindowsPath)):
        return False
    
    # Verifica se o arquivo antigo existe
    if new_path.exists():
        if backup_old_file:
            backup_file = new_path.parent.joinpath('backup - bot', new_path.name)

            if backup_file.exists():
                backup_file.unlink()
            elif not backup_file.parent.exists():
                backup_file.parent.mkdir(parents=True)

            move(new_path, backup_file)
        else:
            new_path.unlink()
    elif not new_path.parent.exists():
        new_path.parent.mkdir(parents=True)

    copy(current_path, new_path)

    if delete_on_move:
        current_path.unlink()

    return True


def save_on_drive(qvd_path, company_name, file):
    destination = qvd_path.joinpath(company_name, 'base', file.name)
    move_file(file, destination)


def unzip(compressed_file, path_to_extract='.', remove_on_extract=False):
    compressed_file = Path(compressed_file)
    path_to_extract = Path(path_to_extract)

    zip = ZipFile(compressed_file)
    compressed_files = zip.infolist()

    for file in compressed_files:
        # caminho completo para o arquivo que sera extraido
        future_filepath = path_to_extract.joinpath(file.filename)
        # nome do arquivo que sera excluido
        future_filename = file.filename

        # verifica se o caminho futuro ja existe
        # se existir, é verificado se já foi adicionao um contador
        # se ja existir um contador, ele sera incrementado
        # caso contrario, sera adicionado antes da extensaoi do arquivo (1)
        count = 1
        while future_filepath.exists():
            numbered_suffix = f'({count})'
            file_ext        = future_filepath.suffix

            if '(' in future_filename:
                future_filename = re.sub("\\(.*?\\)", numbered_suffix, future_filename)
            else:
                future_filename = f'{future_filepath.stem} {numbered_suffix}{file_ext}'

            future_filepath = path_to_extract.joinpath(future_filename)

            count += 1

        # muda o nome do arquivo comprimido para o nome futuro que sera usado
        file.filename = future_filename
        zip.extract(file, path_to_extract)

    zip.close()

    # remove zip caso remove_on_extract seja true
    remove_on_extract and compressed_file.unlink()


def move_to_drive(qvd_path, company_name, is_audith, download_path, narrative, company_pretty_name):
    for file in download_path.rglob('*.pptx'):
        if not narrative:
            file_name = download_path.joinpath(f'{company_pretty_name}.pptx')
        else:
            file_name = download_path.joinpath(f'{company_pretty_name} IN.pptx')

        logger.info(f'{file.name} renomeado para {file_name.name}')
        file.rename(file_name)
        file = file_name
        logger.info(f'Criando backup {file.name}')
        backup_to_drive(file, qvd_path, company_name)

        logger.info(f'Mandando o arquivo {file.name} para o suripoint')
        ppt_file = run_in_suripoint(file, is_audith)
        destination = qvd_path.joinpath(company_name, 'base', ppt_file.name)
        logger.info(f'Movendo para o drive: {destination}')
        return move_file(ppt_file, destination)
            
    logger.error(f'não existe ppt na pasta de download, provavelmente o qlik esta com problemas para baixar e precisa ser reiniciado')
    return False


def clear_folder(folder_path):
    for file in folder_path.rglob('*.*'):
        file.unlink()


def bypass_captcha(url, url_key):
    solver = recaptchaV2Proxyless()
    solver.set_verbose(1)
    solver.set_key(CAPTCHA_KEY)
    solver.set_website_url(url)
    solver.set_website_key(url_key)

    return solver.solve_and_return_solution()
