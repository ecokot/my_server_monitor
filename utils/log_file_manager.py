#!/usr/bin/env python3
"""
Утилита для управления файлами логов с учетом ротации.

Этот скрипт помогает находить и работать с текущими и архивными лог-файлами,
учитывая поведение ротации, которое происходит при смене даты.
"""

import os
import glob
from datetime import datetime
from pathlib import Path


class LogFileManager:
    """Класс для управления файлами логов с учетом ротации"""
    
    def __init__(self, log_directory="./logs", base_filename="MOEService.log"):
        self.log_directory = Path(log_directory)
        self.base_filename = base_filename
        
    def get_current_log_file(self):
        """Получить путь к текущему лог-файлу"""
        return self.log_directory / self.base_filename
        
    def get_rotated_log_files(self):
        """Получить список всех архивных лог-файлов (с суффиксами дат)"""
        pattern = str(self.log_directory / f"{self.base_filename}.*")
        rotated_files = []
        
        for file_path in glob.glob(pattern):
            filename = Path(file_path).name
            # Проверяем, что это файл с суффиксом даты YYYY-MM-DD
            if self._is_date_suffix_file(filename):
                rotated_files.append(Path(file_path))
                
        # Сортируем по дате (новые файлы в конце)
        rotated_files.sort(key=lambda x: self._extract_date_from_filename(x.name))
        return rotated_files
    
    def get_all_log_files(self):
        """Получить список всех лог-файлов (текущий + архивные)"""
        all_files = []
        current_file = self.get_current_log_file()
        
        if current_file.exists():
            all_files.append(current_file)
            
        all_files.extend(self.get_rotated_log_files())
        return all_files
    
    def _is_date_suffix_file(self, filename):
        """Проверить, является ли файл архивным логом с суффиксом даты"""
        import re
        # Проверяем формат: base_filename.YYYY-MM-DD
        pattern = rf"^{re.escape(self.base_filename)}\.\d{{4}}-\d{{2}}-\d{{2}}$"
        return bool(re.match(pattern, filename))
    
    def _extract_date_from_filename(self, filename):
        """Извлечь дату из имени файла архивного лога"""
        if self._is_date_suffix_file(filename):
            date_str = filename.split('.')[-1]  # Получаем YYYY-MM-DD
            return datetime.strptime(date_str, "%Y-%m-%d")
        return None
    
    def find_log_entries_after_date(self, target_date):
        """Найти все лог-записи после указанной даты"""
        matching_files = []
        target_datetime = datetime.strptime(target_date, "%Y-%m-%d") if isinstance(target_date, str) else target_date
        
        for log_file in self.get_all_log_files():
            if log_file == self.get_current_log_file():
                # Текущий файл всегда содержит самые свежие записи
                matching_files.append(log_file)
            else:
                # Для архивных файлов проверяем дату в имени
                file_date = self._extract_date_from_filename(log_file.name)
                if file_date and file_date >= target_datetime.date():
                    matching_files.append(log_file)
                    
        return matching_files


def main():
    """Пример использования утилиты"""
    print("Утилита управления файлами логов")
    print("=" * 40)
    
    log_manager = LogFileManager()
    
    print(f"Директория логов: {log_manager.log_directory}")
    print(f"Базовое имя файла: {log_manager.base_filename}")
    print()
    
    current_file = log_manager.get_current_log_file()
    print(f"Текущий лог-файл: {current_file} ({'существует' if current_file.exists() else 'НЕ СУЩЕСТВУЕТ'})")
    
    rotated_files = log_manager.get_rotated_log_files()
    print(f"\nАрхивные лог-файлы ({len(rotated_files)}):")
    for i, file_path in enumerate(rotated_files, 1):
        stat = file_path.stat()
        size_mb = stat.st_size / (1024 * 1024)
        print(f"  {i}. {file_path.name} ({size_mb:.2f} MB)")
    
    all_files = log_manager.get_all_log_files()
    print(f"\nВсе лог-файлы ({len(all_files)}):")
    for file_path in all_files:
        stat = file_path.stat()
        size_mb = stat.st_size / (1024 * 1024)
        print(f"  - {file_path.name} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()