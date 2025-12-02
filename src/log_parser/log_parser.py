# src/log_parser/log_parser.py
import os
import asyncio
import json
from datetime import datetime
from src.events.types import GetPlayerCountQuery
from src.logger import LoggerMixin
from src.constants import (
    IP_TIMESTAMP_PATTERN,
    UNIFIED_LOGIN_PATTERN,
    LOGOUT_PATTERN_LOBBY,
    LOGOUT_PATTERN_SERVER,
    LOGIN_PATTERN_SERVER,
    JOIN_PATTERN_SERVER
)
from src.utils.async_watchdog import watch_directory
from src.log_parser.ddos_protection import DDOSProtection


class LogParser(LoggerMixin):
    """
    Единый модуль для парсинга логов:
    - Отслеживает вход/выход игроков
    - Сохраняет данные игроков
    - Блокирует DDoS
    - Не зависит от медиатора
    """

    def __init__(self, mediator=None, config=None, shutdown_event: asyncio.Event = None): # Добавлен shutdown_event
        super().__init__()
        self.mediator = mediator
        self.config = config or (mediator.config if mediator else None)
        if not self.config:
            raise ValueError("Config не предоставлен")

        # Принимаем и сохраняем shutdown_event
        if shutdown_event is None:
            raise ValueError("shutdown_event не предоставлен")
        self.shutdown_event = shutdown_event

        self.log_files = []
        self.connected_players = {}  # steam_id -> {name, log_file, login_time}
        self.players_data = {}  # Все игроки из файла
        self.players_data_file = self.config.get("PLAYERS_DATA_FILE", "./data/players_data.json")
        self.tasks = []
        self.pending_steam_id = None

        # DDoS Protection
        ddos_config = self.config.get("DDOS", {})
        self.ddos_protection = DDOSProtection(
            threshold=ddos_config.get("DDOS_THRESHOLD", 50),
            interval=ddos_config.get("DDOS_INTERVAL", 60),
            log_callback=self.logger.debug,
            config_blocked_ips_file=ddos_config.get("BLOCKED_IPS_FILE", "./data/blocked_ips.json")
        )

        loop = asyncio.get_event_loop()
        self.ddos_protection.start(loop)

        # Загружаем данные игроков
        self._load_players_data()

    def _load_players_data(self):
        """Загружает данные всех игроков из JSON-файла"""
        if os.path.exists(self.players_data_file):
            try:
                with open(self.players_data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                valid_data = {
                    k: v for k, v in data.items()
                    if isinstance(v, dict) and "name" in v
                }
                self.players_data = valid_data
                self.logger.debug(f"Загружено {len(self.players_data)} игроков из {self.players_data_file}")
            except (json.JSONDecodeError, OSError) as e:
                self.logger.error(f"Ошибка загрузки players_data.json: {e}")
        else:
            os.makedirs(os.path.dirname(self.players_data_file), exist_ok=True)
            self.players_data = {}
            self.logger.debug(f"Файл {self.players_data_file} не найден. Создан пустой словарь.")

    def _save_players_data(self):
        """Сохраняет данные игроков в файл"""
        try:
            with open(self.players_data_file, "w", encoding="utf-8") as f:
                json.dump(self.players_data, f, indent=4, ensure_ascii=False)
            self.logger.debug("Данные игроков сохранены")
        except OSError as e:
            self.logger.error(f"Ошибка сохранения players_data.json: {e}")

    def get_configured_log_files(self):
        servers_config = self.config.get("SERVERS", {})
        log_files = []
        for server_info in servers_config.values():
            game_log_files = server_info.get("GAME_LOG_FILES", [])
            if isinstance(game_log_files, str):
                game_log_files = [game_log_files]
            log_files.extend(game_log_files)
        return log_files

    async def start_parsing(self):
        # Проверяем сигнал остановки перед началом
        if self.shutdown_event.is_set():
            self.logger.info("LogParser: Получен сигнал остановки перед запуском.")
            return

        self.log_files = self.get_configured_log_files()
        if not self.log_files:
            self.logger.warning("Не найдены пути к лог-файлам в конфиге.")
            return

        self.logger.debug(f"Парсинг {len(self.log_files)} лог-файлов: {self.log_files}")

        if self.mediator:
            self.mediator.register_handler(GetPlayerCountQuery, self.get_connected_players)

        try:
            for log_file in self.log_files:
                # Проверяем сигнал остановки перед созданием задачи
                if self.shutdown_event.is_set():
                    self.logger.info("LogParser: Получен сигнал остановки, прерываю создание задач.")
                    break
                task = asyncio.create_task(self._parse_single_log(log_file))
                self.tasks.append(task)

            # Если задачи были созданы, ждем их завершения или сигнала остановки
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)
        except asyncio.CancelledError:
            self.logger.info("LogParser.start_parsing: Задача была отменена.")
            # Отменяем все созданные задачи
            for task in self.tasks:
                if not task.done():
                    task.cancel()
            # Ждем завершения отмененных задач
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)
            # Поднимаем исключение дальше, чтобы задача в MainApp тоже завершилась
            raise

    async def _parse_single_log(self, log_file_path):
        # Проверяем сигнал остановки перед началом парсинга файла
        if self.shutdown_event.is_set():
            self.logger.debug(f"LogParser: Получен сигнал остановки, пропускаю файл {log_file_path}.")
            return

        if not os.path.exists(log_file_path):
            self.logger.error(f"Файл логов не найден: {log_file_path}")
            return

        self.logger.debug(f"Парсинг файла: {log_file_path}")
        await self._parse_history(log_file_path)
        await self._parse_real_time(log_file_path)

    async def _parse_history(self, log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            for line in lines:
                # Проверяем сигнал остановки в цикле истории (опционально, для быстрого реагирования)
                if self.shutdown_event.is_set():
                    self.logger.debug(f"LogParser: Получен сигнал остановки, прерываю парсинг истории {log_file_path}.")
                    return
                await self._process_line(line.strip(), log_file_path, is_history=True)
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге истории {log_file_path}: {e}")

    async def _parse_real_time(self, log_file_path):
        # Проверяем сигнал остановки перед началом реального времени
        if self.shutdown_event.is_set():
            self.logger.debug(f"LogParser: Получен сигнал остановки, пропускаю реальный парсинг {log_file_path}.")
            return

        offset_tracker = {'offset': os.path.getsize(log_file_path)}
        self.logger.debug(f"Offset файла {log_file_path}: {offset_tracker['offset']}")

        # Внутренняя функция для обработки изменений файла
        async def handle_file_change(file_path):
            # Проверяем, что это нужный файл и не получен сигнал остановки
            if os.path.basename(file_path) != os.path.basename(log_file_path) or self.shutdown_event.is_set():
                return
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(offset_tracker['offset'])
                    new_lines = f.readlines()
                    current_offset = f.tell()

                    if current_offset < offset_tracker['offset']:
                        self.logger.debug(f"Файл {file_path} был усечён. Перечитываю с начала.")
                        f.seek(0)
                        new_lines = f.readlines()
                        current_offset = f.tell()

                    offset_tracker['offset'] = current_offset

                for line in new_lines:
                    # Проверяем сигнал остановки при обработке каждой новой строки
                    if self.shutdown_event.is_set():
                        self.logger.debug(f"LogParser: Получен сигнал остановки, прерываю обработку строк {file_path}.")
                        return # Выходим из handle_file_change
                    await self._process_line(line.strip(), file_path)
            except Exception as e:
                self.logger.error(f"Ошибка при обработке файла {file_path}: {e}")

        loop = asyncio.get_event_loop()
        # Передаем shutdown_event в watch_directory, если он может его использовать для остановки
        # Если watch_directory не поддерживает событие остановки, нам нужно внести изменения и туда
        # Пока что просто вызываем его
        await watch_directory(os.path.dirname(log_file_path), handle_file_change, loop)

    async def _process_line(self, line, log_file_path, is_history=False):
        if not line:
            return

        # 0. Сначала: проверка, не является ли строка "Join succeeded" и есть ли ожидание ID
        join_match = JOIN_PATTERN_SERVER.search(line)
        if self.pending_steam_id and join_match:
            steam_id = self.pending_steam_id
            player_name = join_match.group(1)

            self.logger.debug(f"Сопоставлено: SteamID {steam_id} -> Nick {player_name}")

            # 🔽 Проверяем: есть ли игрок в сети с этим steam_id?
            existing_player = self.connected_players.get(steam_id)

            # Если игрока нет — добавляем как нового
            if not existing_player:
                # Обновляем/сохраняем в players_data
                current_name = self.players_data.get(steam_id, {}).get("name")
                if not current_name or current_name != player_name:
                    self.players_data[steam_id] = {"name": player_name}
                    self._save_players_data()
                    self.logger.debug(f"Обновлено имя через Join: {steam_id} -> {player_name}")

                # Добавляем в онлайн
                self.connected_players[steam_id] = {
                    "name": player_name,
                    "log_file": log_file_path,
                    "login_time": datetime.now().isoformat()
                }
                self.logger.info(f"Игрок подключился: {player_name} (SteamID: {steam_id})")

            # 🔽 Если есть, НО имя временное (Unknown_...) — обновляем
            elif existing_player["name"].startswith("Unknown_"):
                old_name = existing_player["name"]
                # Обновляем имя в онлайн
                existing_player["name"] = player_name
                # Обновляем в players_data
                self.players_data[steam_id] = {"name": player_name}
                self._save_players_data()
                self.logger.debug(f"Обновлено имя игрока {steam_id}: {old_name} → {player_name}")
                self.logger.info(f"Игрок теперь известен: {player_name} (SteamID: {steam_id})")

            # 🔽 Если уже полноценное имя — ничего не делаем (возможно, дубль)

            # Сбрасываем ожидание
            self.pending_steam_id = None


        # 1. DDoS Detection (остаётся)
        if is_history:
            ip_match = IP_TIMESTAMP_PATTERN.search(line)
            if ip_match:
                timestamp_str, ip = ip_match.groups()
                if not self.ddos_protection.is_blocked(ip):
                    self.ddos_protection.add_request(ip, timestamp_str)

        # 2. Отдельно: ловим PostLogin Account — ставим в ожидание
        post_login_match = LOGIN_PATTERN_SERVER.search(line)
        if post_login_match:
            steam_id = post_login_match.group(1)
            self.pending_steam_id = steam_id
            self.logger.debug(f"Обнаружен SteamID, ожидаем ник: {steam_id}")

        # 3. Player Login (основной парсинг — остаётся)
        login_match = UNIFIED_LOGIN_PATTERN.search(line)
        if login_match:
            steam_id = login_match.group(1) or login_match.group(3)
            parsed_name = login_match.group(2)  # Может быть None

            if not steam_id:
                return

            if steam_id in self.connected_players:
                if self.connected_players[steam_id]['log_file'] != log_file_path:
                    self.logger.debug(f"Игрок {steam_id} уже в сети, но из другого файла. Пропускаем.")
                return

            current_entry = self.players_data.get(steam_id)
            if parsed_name:
                if not current_entry or current_entry.get("name") != parsed_name:
                    self.players_data[steam_id] = {"name": parsed_name}
                    self._save_players_data()
                    self.logger.debug(f"Обновлено имя игрока {steam_id}: {parsed_name}")
                final_name = parsed_name
            else:
                final_name = current_entry["name"] if current_entry else f"Unknown_{steam_id}"

            if steam_id not in self.players_data:
                self.players_data[steam_id] = {"name": final_name}
                self._save_players_data()
                self.logger.debug(f"Зарегистрирован игрок без имени: {steam_id} -> {final_name}")

            self.connected_players[steam_id] = {
                "name": final_name,
                "log_file": log_file_path,
                "login_time": datetime.now().isoformat(),
                "pending_steam_id": self.pending_steam_id
            }
            self.logger.info(f"Игрок подключился: {final_name} (SteamID: {steam_id})")
            return

        # 4. Player Logout — остаётся
        logout_match = LOGOUT_PATTERN_LOBBY.search(line) or LOGOUT_PATTERN_SERVER.search(line)
        if logout_match:
            steam_id = logout_match.group(1).strip()
            if steam_id in self.connected_players:
                player_name = self.connected_players[steam_id]["name"]
                del self.connected_players[steam_id]
                self.logger.info(f"Игрок отключился: {player_name} (SteamID: {steam_id})")
            else:
                self.logger.debug(f"Отключение неотслеживаемого игрока: {steam_id}")
            return

    def get_connected_players(self, query=None):
        """Возвращает копию онлайн-игроков (для GetPlayerCountQuery)"""
        return {sid: data["name"] for sid, data in self.connected_players.items()}

    @property
    def player_count(self):
        return len(self.connected_players)

    async def shutdown(self):
        """Корректное завершение парсера"""
        self.logger.info("Остановка LogParser...")
        # Отменяем все задачи парсинга файлов
        for task in self.tasks:
            if not task.done():
                task.cancel()
        # Ждем завершения отмененных задач
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

        if hasattr(self, 'ddos_protection'):
            self.ddos_protection.stop()  # Останавливает фоновую задачу
        self.logger.info("LogParser остановлен.")