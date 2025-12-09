# src/logger.py

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from src.config import Config
from src.singleton import Singleton

# ANSI цвета
COLORS = {
    'DEBUG': '\033[36m',  # Cyan
    'INFO': '\033[32m',  # Green
    'WARNING': '\033[33m',  # Yellow
    'ERROR': '\033[31m',  # Red
    'CRITICAL': '\033[1;31m',  # Bold red
    'RESET': '\033[0m'
}


class ColoredFormatter(logging.Formatter):

    def format(self, record):
        color = COLORS.get(record.levelname, COLORS['RESET'])
        # Сохраняем оригинальный формат во время форматирования
        orig_fmt = self._style._fmt
        try:
            self._style._fmt = f"{color}{orig_fmt}{COLORS['RESET']}"
            return super().format(record)
        finally:
            self._style._fmt = orig_fmt


class Logger(Singleton):
    """
    Единый логгер проекта. Использование:
      logger = Logger()
      logger.info("Hello")
    """

    def __init__(self, *args, **kwargs):
        # Защита от повторной инициализации
        if hasattr(self, '_initialized'):
            return

        config = Config()
        log_file = config.get("LOG.LOG_FILE", "./logs/app.log")
        level_file = config.get("LOG.LEVEL_FILE_LOG", "INFO")
        level_console = config.get("LOG.LEVEL_CONSOLE_LOG", "INFO")
        main_level = config.get("LOG.MAIN_LEVEL_LOG", "INFO")

        # Создаём папку логов
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        # Создаём стандартный logging.Logger (именно его будем использовать!)
        self._logger = logging.getLogger("app")
        self._logger.setLevel(getattr(logging, main_level))
        self._logger.propagate = False  # ← критически важно

        # Форматтеры
        file_formatter = logging.Formatter(
            "[%(asctime)s][%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_formatter = ColoredFormatter(
            "[%(asctime)s][%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Обработчики
        file_handler = TimedRotatingFileHandler(
            log_file,
            when="midnight",  # midnight, M , S
            interval=1,
            backupCount=14,  # 2 недели
            encoding="utf-8"
        )
        file_handler.setLevel(getattr(logging, level_file))
        file_handler.setFormatter(file_formatter)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, level_console))
        console_handler.setFormatter(console_formatter)

        # Добавляем только если ещё не добавлены
        if not self._logger.handlers:
            self._logger.addHandler(file_handler)
            self._logger.addHandler(console_handler)

        self._initialized = True

    def debug(self, msg, *args, **kwargs):
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self._logger.critical(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        self._logger.exception(msg, *args, **kwargs)

    # Опционально: доступ к внутреннему логгеру (для advanced use-cases)
    def get_logger(self) -> logging.Logger:
        return self._logger
