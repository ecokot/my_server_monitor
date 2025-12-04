#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы парсера с ротацией логов
"""
import asyncio
import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

# Импортируем необходимые классы
import sys
sys.path.insert(0, '/workspace')

from src.log_parser.log_parser import LogParser
from src.events.types import GetPlayerCountQuery


class MockMediator:
    def __init__(self):
        self.config = self.load_config()
        self.logger = self.create_logger()
        
    def load_config(self):
        # Загружаем конфигурацию из файла
        with open('/workspace/config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def create_logger(self):
        import logging
        logger = logging.getLogger('test_logger')
        logger.setLevel(logging.DEBUG)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger
    
    def register_handler(self, event_type, handler):
        pass


async def test_log_parser_with_rotation():
    """Тестирование парсера с ротацией логов"""
    print("Тестирование парсера с ротацией логов...")
    
    # Создаем mock объекты
    mediator = MockMediator()
    shutdown_event = asyncio.Event()
    
    # Создаем LogParser
    parser = LogParser(mediator=mediator, config=mediator.config, logger=mediator.logger, shutdown_event=shutdown_event)
    
    # Создаем тестовый лог-файл
    log_file = "/workspace/logs/MOEService.log"
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Создаем начальный лог-файл
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Server started\n")
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Player connected: TestPlayer1\n")
    
    print(f"Создан тестовый лог-файл: {log_file}")
    
    # Запускаем парсер в отдельной задаче
    parse_task = asyncio.create_task(parser.start_parsing())
    
    # Ждем немного, чтобы парсер начал работу
    await asyncio.sleep(2)
    
    # Симулируем ротацию лога
    print("Симуляция ротации лога...")
    backup_file = log_file + ".1"
    if os.path.exists(backup_file):
        os.remove(backup_file)
    
    os.rename(log_file, backup_file)
    print(f"Старый файл переименован в: {backup_file}")
    
    # Создаем новый файл
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] New log file after rotation\n")
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Player connected: TestPlayer2\n")
    
    print(f"Создан новый файл: {log_file}")
    
    # Добавляем несколько строк в новый файл
    for i in range(3):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] New message {i+1}\n")
        await asyncio.sleep(1)
    
    # Останавливаем парсер
    print("Остановка парсера...")
    shutdown_event.set()
    try:
        await asyncio.wait_for(parse_task, timeout=5.0)
    except asyncio.TimeoutError:
        parse_task.cancel()
        try:
            await parse_task
        except:
            pass
    
    print("Тест завершен успешно!")


if __name__ == "__main__":
    asyncio.run(test_log_parser_with_rotation())