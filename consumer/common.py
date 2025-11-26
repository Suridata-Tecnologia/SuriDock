from pywinauto.findwindows  import find_windows
from pywinauto              import Application
from loguru                 import logger
from time                   import sleep
from pathlib                import Path

import subprocess


logger.add('logs/script.log')


def find_qlik_path():
    qlik_path = Path.home().joinpath('AppData/Local/Programs/Qlik/Sense/QlikSenseBrowser/QlikSenseBrowser.exe')
    if qlik_path.exists():
        return qlik_path
    else:
        logger.error('Não foi possível encontrar a instalação do qlik')
        return False
    

def open_and_start_qlik(qlik_path):
    subprocess.Popen(qlik_path)
    app = Application(backend='uia').start(str(qlik_path))

    qlik_window = None
    window_list = []
    while not qlik_window:
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
        qlik_app.child_window(title='Iniciar', control_type='Button').click_input()
        qlik_app.minimize()
        sleep(3)
        return qlik_app
    
    return False
