# src/log_parser.py
import os
import asyncio
from src.events.types import DdosEvent, GetPlayerCountQuery
from src.logger import LoggerMixin  # Используем миксин для логирования
from src.constants import IP_TIMESTAMP_PATTERN, UNIFIED_LOGIN_PATTERN, LOGOUT_PATTERN_LOBBY, LOGOUT_PATTERN_SERVER
from src.utils.async_watchdog import watch_directory
from src.log_parser.ddos_protection import DDOSProtection


class LogParser(LoggerMixin):
    """
    Класс для парсинга логов Myth of Empires.
    Отслеживает подключения/отключения игроков и DDoS-атаки.
    События DDoS отправляются через медиатор.
    События подключения/отключения игроков логируются, но НЕ отправляются через медиатор.
    """

    def __init__(self, mediator=None, config=None):
        super().__init__()  # Инициализация логгера из миксина
        self.mediator = mediator
        self.config = config or mediator.config  # Используем переданный config или из медиатора
        self.log_files = []
        self.connected_players = {}  # Словарь {steam_id: player_name}
        self.tasks = []  # Для отслеживания запущенных задач

        ddos_config = self.config.get("DDOS", {})
        self.ddos_protection = DDOSProtection(
            threshold=ddos_config.get("DDOS_THRESHOLD", 50),
            interval=ddos_config.get("DDOS_INTERVAL", 60),
            log_callback=self.logger.debug,  # или debug, warning — как удобно
            config_blocked_ips_file=self.config.get("DDOS", {}).get("BLOCKED_IPS_FILE", "./data/blocked_ips.json")
        )

        # Запускаем фоновую очистку
        loop = asyncio.get_event_loop()
        self.ddos_protection.start(loop)

    def get_configured_log_files(self):
        """Получает пути к лог-файлам из конфига."""
        servers_config = self.config.get("SERVERS", {})
        log_files = []
        for server_info in servers_config.values():
            game_log_files = server_info.get("GAME_LOG_FILES", [])
            if isinstance(game_log_files, str):
                game_log_files = [game_log_files]
            log_files.extend(game_log_files)
        return log_files

    async def start_parsing(self):
        """Запускает парсинг логов."""
        self.log_files = self.get_configured_log_files()
        if not self.log_files:
            self.logger.warning("Не найдены пути к лог-файлам в конфиге.")
            return

        self.logger.debug(f"Начинаю парсинг {len(self.log_files)} лог-файлов: {self.log_files}")

        # Подписываем медиатор на GetConnectedPlayersQuery, если он предоставлен
        if self.mediator:
            self.mediator.register_handler(GetPlayerCountQuery, self._handle_get_players_query)

        # Запуск задач для парсинга каждого файла
        for log_file in self.log_files:
            task = asyncio.create_task(self._parse_single_log(log_file))
            self.tasks.append(task)

        # Ожидаем завершения всех задач (или отмены, если основная задача отменена)
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def _parse_single_log(self, log_file_path):
        """Парсит один файл логов: сначала историю, потом реальное время."""
        if not os.path.exists(log_file_path):
            self.logger.error(f"Файл логов не найден: {log_file_path}")
            return

        self.logger.debug(f"Начинаю парсинг файла: {log_file_path}")

        # --- 1. Полный парсинг истории ---
        await self._parse_history(log_file_path)

        # --- 2. Режим реального времени ---
        await self._parse_real_time(log_file_path)

    async def _parse_history(self, log_file_path):
        """Парсит историю файла до текущего момента."""
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            for line in lines:
                await self._process_line(line.strip(), log_file_path, is_history=True)

        except Exception as e:
            self.logger.error(f"Ошибка при парсинге истории файла {log_file_path}: {e}")

    async def _parse_real_time(self, log_file_path):
        offset_tracker = {'offset': os.path.getsize(log_file_path)}
        self.logger.debug(f"Начальный offset файла {log_file_path}: {offset_tracker['offset']}")

        async def handle_file_change(file_path):
            if os.path.basename(file_path) != os.path.basename(log_file_path):
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
                    await self._process_line(line.strip(), file_path)

            except Exception as e:
                self.logger.error(f"Ошибка при обработке файла {file_path}: {e}")

        loop = asyncio.get_event_loop()
        await watch_directory(os.path.dirname(log_file_path), handle_file_change, loop)

    async def _process_line(self, line, log_file_path, is_history=False):
        """Обрабатывает одну строку лога."""
        if not line:
            return

        # 1. Проверка на DDoS (IP и временная метка)
        if is_history:
            ip_match = IP_TIMESTAMP_PATTERN.search(line)
            if ip_match:
                timestamp_str, ip = ip_match.groups()
                if not self.ddos_protection.is_blocked(ip):  # Не обрабатываем уже заблокированные
                    self.ddos_protection.add_request(ip, timestamp_str)

        # 2. Проверка на подключение игрока
        login_match = UNIFIED_LOGIN_PATTERN.search(line)
        if login_match:
            # steam_id из старого формата (group 1) или нового (group 3)
            steam_id = login_match.group(1) or login_match.group(3)
            # player_name из нового формата (group 2), если есть
            player_name = login_match.group(2) if login_match.group(2) else f"Unknown_{steam_id}"

            if steam_id:
                self.connected_players[steam_id] = player_name
                # Логируем подключение, НЕ отправляем через медиатор
                self.logger.info(f"Игрок подключился: {player_name} (SteamID: {steam_id}) из файла {log_file_path}")
            return  # Не проверяем logout, если был login

        # 3. Проверка на отключение игрока
        logout_match = LOGOUT_PATTERN_LOBBY.search(line) or LOGOUT_PATTERN_SERVER.search(line)
        if logout_match:
            steam_id = logout_match.group(1).strip()
            if steam_id in self.connected_players:
                player_name = self.connected_players.pop(steam_id)
                # Логируем отключение, НЕ отправляем через медиатор
                self.logger.info(f"Игрок отключился: {player_name} (SteamID: {steam_id}) из файла {log_file_path}")
            else:
                # Игрок, который не был отслеживаем (например, был до запуска парсера)
                self.logger.debug(f"Обнаружено отключение неотслеживаемого игрока: {steam_id} из файла {log_file_path}")
            return

    def _handle_get_players_query(self, query: GetPlayerCountQuery):
        """Обработчик запроса на получение списка подключенных игроков."""
        # Возвращает копию словаря, чтобы избежать изменений извне
        return self.connected_players.copy()

    @property
    def player_count(self):
        return len(self.connected_players)
