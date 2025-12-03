# src/log_parser/players_data_manager.py

import json
import os
import time
from typing import Dict, Optional


class PlayersDataManager:
    def __init__(self, file_path: str, logger, save_interval: int = 300):
        self.file_path = file_path
        self.logger = logger
        self.save_interval = save_interval
        self._last_save_time = time.time() - save_interval  # Чтобы первый вызов точно сохранил
        self.data = {}

    def load(self):
        """Загружает данные всех игроков из JSON-файла"""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                # Валидация: оставляем только записи с ключом "name"
                valid_data = {
                    k: v for k, v in raw_data.items()
                    if isinstance(v, dict) and "name" in v
                }
                self.data = valid_data
                self.logger.debug(f"Загружено {len(self.data)} игроков из {self.file_path}")
            except (json.JSONDecodeError, OSError) as e:
                self.logger.error(f"Ошибка загрузки {self.file_path}: {e}")
                self.data = {}
        else:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            self.data = {}
            self.logger.debug(f"Файл {self.file_path} не найден. Создан пустой словарь.")

    def save_if_needed(self):
        """Сохраняет данные игроков в файл не чаще одного раза в save_interval секунд"""
        current_time = time.time()
        if current_time - self._last_save_time < self.save_interval:
            self.logger.debug("Сохранение пропущено: прошло менее 5 минут")
            return

        self._last_save_time = current_time

        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            self.logger.debug("Данные игроков сохранены")
        except OSError as e:
            self.logger.error(f"Ошибка сохранения {self.file_path}: {e}")

    def update_player(self, steam_id: str, name: str):
        """Обновляет имя игрока в данных"""
        current_entry = self.data.get(steam_id)
        if not current_entry or current_entry.get("name") != name:
            self.data[steam_id] = {"name": name}
            return True  # Флаг, что нужно сохранить
        return False

    def get_player_name(self, steam_id: str) -> Optional[str]:
        """Получает имя игрока по SteamID"""
        entry = self.data.get(steam_id)
        return entry.get("name") if entry else None

    def get_all_data(self):
        """Возвращает все данные игроков"""
        return self.data

    def set_all_data(self, data: Dict):
        """Устанавливает все данные (например, при загрузке)"""
        self.data = data
