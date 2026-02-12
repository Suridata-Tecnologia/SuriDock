from selenium.webdriver.support         import expected_conditions as EC
from pathlib                            import Path, WindowsPath
from selenium.webdriver.support.ui      import WebDriverWait
from pywinauto.findwindows              import find_windows
from pywinauto                          import Application
from dotenv                             import load_dotenv
from shutil                             import copy, move
from selenium                           import webdriver
from database                           import Database
from datetime                           import datetime
from zoneinfo                           import ZoneInfo
from selenium.webdriver.chrome.options  import Options
from selenium.webdriver.chrome.service  import Service
from zipfile                            import ZipFile
from loguru                             import logger
from time                               import sleep
from selenium.webdriver.common.by       import By

import subprocess
import requests
import psutil
import pika
import json
import os
import re



load_dotenv()
MACHINE_NAME        = os.getenv('MACHINE_NAME')
RABBITMQ_HOST       = os.getenv('RABBITMQ_HOST')
RABBITMQ_USERNAME   = os.getenv('RABBITMQ_USERNAME')
RABBITMQ_PASSWORD   = os.getenv('RABBITMQ_PASSWORD')
RABBITMQ_MESSAGES   = os.getenv('RABBITMQ_MESSAGES')

fuso_brasilia = ZoneInfo("America/Sao_Paulo")
logger.add('logs/script.log')

link_to_suripoint = 'https://suripoint-backend-sar7gmwfia-ue.a.run.app' # Produção
# link_to_suripoint = 'https://suripoint-backend-hom-sar7gmwfia-ue.a.run.app' # Homologação


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


def publish_message_discord(message_data):    
    channel, connection = connection_rabbitmq()
    channel.queue_declare(queue=RABBITMQ_MESSAGES, durable=True)
    channel.basic_publish(
        exchange='',
        routing_key=RABBITMQ_MESSAGES,
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


def close_process(process_name):
    try:
        for proc in psutil.process_iter(['name']):
            if process_name in proc.name().lower():
                proc.kill()
    except Exception as error:
        logger.error(f'psutil não conseguiu fechar o {process_name}: {error}')


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
    if MACHINE_NAME.lower() == 'homologação':
        if sentinel:
            script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-SentinelTESTE{agent_number}.qvs')
        else:
            script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-homo-bot{agent_number}.qvs')
    elif MACHINE_NAME.lower() == 'produção 1':
        if sentinel:
            script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-Sentinel1-agent{agent_number}.qvs')
        else:
            script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-prod1-bot{agent_number}.qvs')
    elif MACHINE_NAME.lower() == 'produção 2':
        if sentinel:
            script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-Sentinel2-agent{agent_number}.qvs')
        else:
            script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-prod2-bot{agent_number}.qvs')
    elif MACHINE_NAME.lower() == 'produção 3':
        if sentinel:
            script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-Sentinel3-agent{agent_number}.qvs')
        else:
            script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-prod3-bot{agent_number}.qvs')
    elif MACHINE_NAME.lower() == 'produção 4':
        if sentinel:
            script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-Sentinel4-agent{agent_number}.qvs')
        else:
            script_path = qvd_path.parent.joinpath('_QSScripts', f'[0]QS_Backend_Script_Standard_ScriptFile_Initial-prod4-bot{agent_number}.qvs')
    else:
        logger.error(f'Máquina não identificada: {MACHINE_NAME}')
        quit()

    return script_path


def edit_script_qvs(script_path, company_name, activity, language, month_analysis, sentinel=False):
    with open(script_path, 'r', encoding='utf-8') as f:
        script_lines = f.readlines()

    script_lines[10] = f"let vG_ClientName  = '{company_name.upper()}'; //<--- NOME DO CLIENTE EM LETA minúscula - conforme pasta do Drive\n"
    if not sentinel:
        script_lines[13] = f"let vG_Atividadeda = '{activity}';  // o que você quer fazer?\n"
        script_lines[26] = f"let vG_Idioma = '{language}'; // <--- Idioma em que se deseja apresentar os slides depois do reload (sem acento). Valores possíveis:\n"
        script_lines[29] = f"LET vG_MesAnalise = '{month_analysis}';          // não -> padrão \n"
        
    with open(script_path, 'w', encoding='utf-8') as f:
        f.writelines(script_lines)

    logger.info(f'Editou o arquivo do qlik pra rodar a empresa {company_name}')


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


def navigate_to_process(driver, wait, agent_number, sentinel=False):
    driver.get('http://localhost:4848/hub/my/work')
    driver.maximize_window()
    
    try: # colocado um try por conta do spam não aparecer a vezes
        wait.until(EC.presence_of_element_located((By.XPATH, '/html/body/div[2]/div/div/div/div[2]/div[1]/button/span')))
        driver.find_element(By.XPATH, '/html/body/div[2]/div/div/div/div[2]/div[1]/button/span').click()
    except:
        pass

    # clicando no app correto de acordo com o agente e se é sentinel ou não
    app_number = agent_number + 3 if sentinel else agent_number - 1
    apps = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.hub-ul.qv-grid.ng-scope > li')))
    apps[app_number].click()  # Seleciona o app desejado
    driver.switch_to.window(driver.window_handles[1])
    sleep(5)

    # seleciona a nova guia (app) que foi aberta
    driver.switch_to.window(driver.window_handles[1])
    sleep(10)

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
    zip_file = file.parent.joinpath(file.stem + '.zip')
    
    files=[('file',(file.stem, open(file,'rb'),'application/vnd.openxmlformats-officedocument.presentationml.presentation'))]

    response = requests.request('POST', f'{link_to_suripoint}/ppt/store', files=files)
    sleep(2)

    if is_audith:
        response = requests.request('POST', f'{link_to_suripoint}/ppt/process', data={'isAudity': is_audith})
    else:
        # Se colocar data={'isAudity': False} o suripoint gera como auditoria
        response = requests.request('POST', f'{link_to_suripoint}/ppt/process')
    sleep(2)

    if type(response.json()['statusMessage']) == dict:
        logger.info(f'o suripoint retornou um dicionário: {response.text}')
        return False
    
    if 'não encontrado' in response.json()['statusMessage'].lower():
        logger.error(f'Erro no suripoint: {response.text}')
        return False
    
    response = requests.request('GET', f'{link_to_suripoint}/ppt/download')

    with open(zip_file, 'wb') as f:
        f.write(response.content)

    logger.info(f'zip baixado {zip_file}')

    return zip_file


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
        backup_to_drive(file, qvd_path, company_name)
        suripoint_error = True

        while suripoint_error:
            for _ in range(4):
                try:
                    for _ in range(4):
                        logger.info(f'Mandando o arquivo {file.name} para o suripoint')
                        zip_file = run_in_suripoint(file, is_audith)
                        if not zip_file:
                            sleep(10)
                        else:
                            break

                    if not zip_file:
                        logger.error('o suripoint não retornou o zip')
                        save_on_drive(qvd_path, company_name, file)
                        return False
                    
                    logger.info('o suripoint retornou o zip')

                except Exception as error:
                    logger.error(f'Ocorreu um erro ao rodar o suripoint: {str(error)}')
                    save_on_drive(qvd_path, company_name, file)
                    return False
                
                try:
                    unzip(zip_file, zip_file.parent, remove_on_extract=True)
                except Exception as error:
                    logger.error(f'Ocorreu um erro ao descompactar o ZIP: {str(error)}')

                new_file = None
                for unziped_file in file.parent.glob('*.pptx'):
                    if unziped_file.name != file.name:
                        new_file = unziped_file
                        break

                aceppt_companies = ['magalu_bra', 'magalu_fesp','magalu_gndi','magalu_hap','magalu_sfran']
                if new_file:
                    if 'magalu' in new_file.stem.lower() and company_name.lower() not in aceppt_companies:
                        new_file.unlink()
                        logger.error(f'O ZIP veio com o arquivo incorreto: {new_file.stem} - {company_name}')
                        suripoint_error = True
                    else:
                        logger.success(f'O ZIP veio com o arquivo correto: {new_file.stem} - {company_name}')
                        file.unlink()
                        suripoint_error = False
                        break
                else:
                    logger.error('O ZIP veio corrompido ou não foi descompactado corretamente')

        if not new_file:
            logger.error('não existe arquivo dentro do zip')
            save_on_drive(qvd_path, company_name, file)
            return False
        else:
            destination = qvd_path.joinpath(company_name, 'base', new_file.name)
            logger.info(f'Movendo para o drive: {destination}')
            return move_file(new_file, destination)
            
    logger.error(f'não existe ppt na pasta de download, provavelmente o qlik esta com problemas para baixar e precisa ser reiniciado')
    return False