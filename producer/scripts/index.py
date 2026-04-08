from apps.discord   import DiscordBot
from clear_queue    import ClearQueue
from apps.listener  import FivePage
from loguru         import logger
from time           import sleep
from pathlib        import Path

import threading



def save_logs():
    logs_path = Path.cwd().joinpath('logs/script.log')
    if logs_path.exists():
        logs_path.unlink()

    # salva os logs
    logger.add(logs_path)


def clear_queue_worker():
    worker = ClearQueue()
    while True:
        try:
            worker.run()
        except Exception as e:
            logger.exception(f'Erro no clear_queue_worker: {e}')
        sleep(3600)


def firestore_worker():
    worker = FivePage()
    while True:
        try:
            worker.run()
        except Exception as e:
            logger.exception(f'Erro no firestore_worker: {e}')
        sleep(60)

save_logs()

threading.Thread(target=clear_queue_worker, daemon=True).start()
# threading.Thread(target=firestore_worker, daemon=True).start()

DiscordBot().run()
