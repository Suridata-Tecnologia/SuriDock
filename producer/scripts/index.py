from apps.discord   import DiscordBot
from loguru         import logger


# salva os logs
logger.add('logs/script.log')

DiscordBot().run()