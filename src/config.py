# src/config.py

import json
import os


class Config:

    def __init__(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Ошибка парсинга JSON в конфиге: {e}")

    def get(self, key, default=None):
        """
        Общий безопасный доступ к любому полю.
        Поддерживает вложенные ключи через точку (например, "LOG.LEVEL_FILE_LOG").
        """
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def get_server(self, server_id):
        """Получить конфиг сервера по ID"""
        servers = self._config.get("SERVERS", {})
        return servers.get(str(server_id))

    @property
    def telegram_token(self):
        """Свойство: Telegram token (удобно для частого использования)"""
        return self._config.get("TELEGRAM", {}).get("TOKEN", "")