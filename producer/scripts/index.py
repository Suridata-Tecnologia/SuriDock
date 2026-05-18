from apps.discord   import DiscordBot
from clear_queue    import ClearQueue
from apps.listener  import FivePage
from loguru         import logger
from time           import sleep
from apps.pipe      import Pipe
from pathlib        import Path

import threading



def save_logs():
    logs_path = Path.cwd().joinpath('logs/script.log')
    if logs_path.exists():
        try:
            logs_path.unlink()
        except Exception as error:
            logger.error(f'não foi possível excluir o arquivo de logs: {error}')

    # salva os logs
    logger.add(logs_path)


def clear_queue_worker():
    while True:
        try:
            ClearQueue().run()
        except Exception as e:
            logger.exception(f'Erro no clear_queue_worker: {e}')
        sleep(3600)


def firestore_worker():
    while True:
        try:
            FivePage().run()
        except Exception as e:
            logger.exception(f'Erro no firestore_worker: {e}')
        sleep(60)


def pipe_worker():
    while True:
        Pipe().run()
        sleep(86400)

save_logs()


threading.Thread(target=clear_queue_worker, daemon=True).start()
threading.Thread(target=firestore_worker, daemon=True).start()
threading.Thread(target=pipe_worker, daemon=True).start()

DiscordBot().run()
