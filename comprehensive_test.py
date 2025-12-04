#!/usr/bin/env python3
"""
Комплексный тест для проверки всех сценариев обработки ротации логов
"""
import asyncio
import os
import time
from datetime import datetime

async def test_comprehensive_log_rotation():
    """Комплексное тестирование различных сценариев ротации логов"""
    log_file = "/workspace/logs/MOEService.log"
    
    print("=== Комплексное тестирование ротации логов ===")
    
    # Создаем директорию, если не существует
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Сценарий 1: Создание начального файла и добавление данных
    print("\n1. Создание начального файла...")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Server started\n")
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Player connected: TestPlayer1\n")
    
    print(f"   Начальный файл создан с {os.path.getsize(log_file)} байтами")
    
    # Добавляем несколько строк
    for i in range(3):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Initial message {i+1}\n")
        await asyncio.sleep(0.5)
    
    # Сценарий 2: Классическая ротация (переименование файла)
    print("\n2. Классическая ротация (переименование файла)...")
    backup_file = log_file + ".1"
    if os.path.exists(backup_file):
        os.remove(backup_file)
    
    os.rename(log_file, backup_file)
    print(f"   Старый файл переименован в: {backup_file}")
    
    # Создаем новый файл
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] New log file after rotation\n")
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Player connected: TestPlayer2\n")
    
    print(f"   Новый файл создан: {log_file} с {os.path.getsize(log_file)} байтами")
    
    # Добавляем строки в новый файл
    for i in range(3):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] New file message {i+1}\n")
        await asyncio.sleep(0.5)
    
    # Сценарий 3: Усечение файла (truncation)
    print("\n3. Тестирование усечения файла...")
    initial_size = os.path.getsize(log_file)
    with open(log_file, "w", encoding="utf-8") as f:  # Открываем в режиме записи, что усекает файл
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] File truncated and restarted\n")
    
    new_size = os.path.getsize(log_file)
    print(f"   Файл усечен: {initial_size} -> {new_size} байт")
    
    # Добавляем строки после усечения
    for i in range(2):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] After truncate {i+1}\n")
        await asyncio.sleep(0.5)
    
    # Сценарий 4: Ротация с датой в имени файла
    print("\n4. Ротация с датой в имени файла...")
    date_backup = f"{log_file}.{datetime.now().strftime('%Y-%m-%d')}"
    if os.path.exists(date_backup):
        os.remove(date_backup)
    
    os.rename(log_file, date_backup)
    print(f"   Файл переименован с датой: {date_backup}")
    
    # Создаем новый файл
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] New file with date rotation\n")
    
    print(f"   Новый файл создан: {log_file}")
    
    # Добавляем строки
    for i in range(2):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Date rotation msg {i+1}\n")
        await asyncio.sleep(0.5)
    
    # Сценарий 5: Временная недоступность файла
    print("\n5. Тестирование временной недоступности файла...")
    temp_backup = log_file + ".tmp"
    
    # Переименовываем файл
    os.rename(log_file, temp_backup)
    print(f"   Файл временно недоступен: переименован в {temp_backup}")
    
    await asyncio.sleep(1)  # Ждем 1 секунду
    
    # Восстанавливаем файл
    os.rename(temp_backup, log_file)
    print(f"   Файл восстановлен: {log_file}")
    
    # Добавляем строки после восстановления
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] After recovery\n")
    
    print("\n=== Все сценарии тестирования завершены успешно ===")
    
    # Показываем список всех созданных файлов
    print("\nСозданные файлы:")
    log_dir = os.path.dirname(log_file)
    for file in sorted(os.listdir(log_dir)):
        if file.startswith(os.path.basename(log_file)):
            file_path = os.path.join(log_dir, file)
            size = os.path.getsize(file_path)
            print(f"  {file}: {size} байт")


if __name__ == "__main__":
    asyncio.run(test_comprehensive_log_rotation())