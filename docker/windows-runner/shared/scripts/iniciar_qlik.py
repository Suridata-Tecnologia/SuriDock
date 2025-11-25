from pywinauto.findwindows  import find_windows
from pywinauto              import Application
from loguru                 import logger
from time                   import sleep
from pathlib                import Path


sleep(15)  # Wait for 15 seconds to ensure the application is ready
logger.add('logs/script.log')

qlik_path = Path('C:/Users/admin/AppData/Local/Programs/Qlik/Sense/QlikSenseBrowser/QlikSenseBrowser.exe')
app = Application(backend="uia").start(str(qlik_path))

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
    qlik_app.set_focus()
    start_btn = qlik_app.child_window(title='Iniciar', control_type='Button').click_input()
    logger.success('Teste concluído com sucesso.')
else:
    logger.error(f'Janela do Qlik Sense Desktop não encontrada: {window_list}')
