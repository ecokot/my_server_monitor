#!/usr/bin/env python3
"""
Тестовый скрипт для проверки обработки ротации логов
"""
import asyncio
import os
import time
from datetime import datetime

async def simulate_log_rotation():
    """Симуляция ротации логов для тестирования"""
    log_file = "/workspace/logs/MOEService.log"
    
    print(f"Тестирование обработки ротации логов на файле: {log_file}")
    
    # Создаем директорию, если не существует
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Создаем тестовый лог-файл
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Server started\n")
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Player connected: TestPlayer1\n")
    
    print(f"Создан начальный лог-файл с {os.path.getsize(log_file)} байтами")
    
    # Добавляем несколько строк
    for i in range(5):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Test message {i+1}\n")
        await asyncio.sleep(1)
    
    print("Симуляция ротации лога: переименовываем текущий файл и создаем новый")
    
    # Симулируем ротацию лога - переименовываем файл и создаем новый
    backup_file = log_file + ".1"
    if os.path.exists(backup_file):
        os.remove(backup_file)
    
    os.rename(log_file, backup_file)
    print(f"Старый файл переименован в: {backup_file}")
    
    # Создаем новый файл
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] New log file after rotation\n")
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Player connected: TestPlayer2\n")
    
    print(f"Создан новый файл: {log_file} с {os.path.getsize(log_file)} байтами")
    
    # Добавляем еще несколько строк в новый файл
    for i in range(3):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] New file message {i+1}\n")
        await asyncio.sleep(1)
    
    print("Тест завершен")

if __name__ == "__main__":
    asyncio.run(simulate_log_rotation())