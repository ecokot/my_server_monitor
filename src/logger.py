# src/log_mixin.py

import logging
from logging.handlers import TimedRotatingFileHandler
from src.config import Config

# ANSI цвета для консоли
COLORS = {
    'DEBUG': '\033[36m',  # Cyan
    'INFO': '\033[32m',  # Green
    'WARNING': '\033[33m',  # Yellow
    'ERROR': '\033[31m',  # Red
    'CRITICAL': '\033[35m',  # Magenta
    'RESET': '\033[0m'  # Reset
}


class ColoredFormatter(logging.Formatter):
    """Форматтер, добавляющий цвета в вывод консоли."""

    def format(self, record):
        log_level = record.levelname
        color = COLORS.get(log_level, COLORS['RESET'])
        self._style._fmt = f"{color}[%(asctime)s][{log_level}] - %(name)s - %(message)s{COLORS['RESET']}"
        return super().format(record)


class LoggerMixin:
    """
    Миксин, добавляющий логирование к другим классам.
    """
    _logger_initialized = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)  # Поддержка MRO
        self._setup_logger()

    def _setup_logger(self):
        class_name = self.__class__.__name__
        if class_name in LoggerMixin._logger_initialized:
            self.logger = LoggerMixin._logger_initialized[class_name]
            return

        # Получаем настройки из конфига
        config = Config()
        log_file = config.get("LOG.LOG_FILE", "./logs/MOEService.log")
        level_file = config.get("LOG.LEVEL_FILE_LOG", "DEBUG")
        level_console = config.get("LOG.LEVEL_CONSOLE_LOG", "DEBUG")
        main_level = config.get("LOG.MAIN_LEVEL_LOG", "DEBUG")

        # Создаем логгер для текущего класса
        logger = logging.getLogger(class_name)
        logger.setLevel(getattr(logging, main_level))

        # Форматтер
        file_formatter = logging.Formatter("[%(asctime)s][%(levelname)s] - %(name)s - %(message)s")
        console_formatter = ColoredFormatter()

        # Обработчик файла с ротацией
        file_handler = TimedRotatingFileHandler(
            log_file, when="midnight", interval=1, backupCount=7, encoding="utf-8"
        )
        file_handler.setLevel(getattr(logging, level_file))
        file_handler.setFormatter(file_formatter)

        # Обработчик консоли
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, level_console))
        console_handler.setFormatter(console_formatter)

        # Добавляем обработчики, если их еще нет
        if not logger.handlers:
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)

        self.logger = logger
        LoggerMixin._logger_initialized[class_name] = logger
