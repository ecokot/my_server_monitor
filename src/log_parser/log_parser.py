# src/log_parser/log_parser.py
import os
import asyncio
from src.events.types import GetPlayerCountQuery
from src.utils.async_watchdog import watch_directory
from src.log_parser.ddos_protection import DDOSProtection

from src.log_parser.players_data_manager import PlayersDataManager
from src.log_parser.line_processor import LogLineProcessor


class LogParser:
    """
    Координирует работу парсинга
    """

    def __init__(self, mediator=None, config=None, logger=None, shutdown_event: asyncio.Event = None):
        self.log_files = None
        self.mediator = mediator
        self.config = config or (mediator.config if mediator else None)
        self.logger = logger or (mediator.logger if mediator else None)
        if not self.config:
            raise ValueError("Config не предоставлен")

        if shutdown_event is None:
            raise ValueError("shutdown_event не предоставлен")
        self.shutdown_event = shutdown_event

        self.connected_players = {}

        # --- Выносим логику ---
        self.players_data_file = self.config.get("PLAYERS_DATA_FILE", "./data/players_data.json")
        self.player_manager = PlayersDataManager(self.players_data_file, self.logger, save_interval=300)
        self.line_processor = LogLineProcessor(self.connected_players, self.player_manager, None,
                                               self.mediator, self.logger)
        # ---

        self.tasks = []

        # DDoS Protection
        ddos_config = self.config.get("DDOS", {})
        self.ddos_protection = DDOSProtection(
            threshold=ddos_config.get("DDOS_THRESHOLD", 50),
            interval=ddos_config.get("DDOS_INTERVAL", 60),
            log_callback=self.logger.debug,
            config_blocked_ips_file=ddos_config.get("BLOCKED_IPS_FILE", "./data/blocked_ips.json")
        )
        # Установим ddos_protection в line_processor
        self.line_processor.ddos_protection = self.ddos_protection

        loop = asyncio.get_event_loop()
        self.ddos_protection.start(loop)

        # Загружаем данные игроков
        self.player_manager.load()

        # Инициализируем подключение серверов: log_file -> server_id
        self.log_file_to_server_id = self._build_log_file_mapping()

    def _build_log_file_mapping(self):
        """Создаёт маппинг: путь к логу → server_id"""
        mapping = {}
        servers_config = self.config.get("SERVERS", {})
        for server_id, server_info in servers_config.items():
            game_log_files = server_info.get("GAME_LOG_FILES", [])
            if isinstance(game_log_files, str):
                game_log_files = [game_log_files]
            for log_file in game_log_files:
                mapping[os.path.normpath(log_file)] = server_id
        return mapping

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

        self.logger.debug(f"Парсинг файла: {self.log_files}")

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
                # Используем line_processor
                norm_path = os.path.normpath(log_file_path)
                server_id = self.log_file_to_server_id.get(norm_path)
                if server_id:
                    await self.line_processor.process_line(line.strip(), server_id, is_history=True)
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге истории {log_file_path}: {e}")

    async def _parse_real_time(self, log_file_path):
        # Проверяем сигнал остановки перед началом
        if self.shutdown_event.is_set():
            self.logger.debug(f"LogParser: Получен сигнал остановки, пропускаем реальный парсинг {log_file_path}.")
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
                    current_offset = os.path.getsize(file_path)
                    # Если файл был усечён, перечитываем с начала
                    if current_offset < offset_tracker['offset']:
                        self.logger.debug(f"Файл {file_path} был усечён. Перечитываем с начала.")
                        f.seek(0)
                        offset_tracker['offset'] = 0

                    f.seek(offset_tracker['offset'])
                    new_lines = f.readlines()
                    offset_tracker['offset'] = f.tell()

                for line in new_lines:
                    # Проверяем сигнал остановки при обработке каждой новой строки
                    if self.shutdown_event.is_set():
                        self.logger.debug(
                            f"LogParser: Получен сигнал остановки, прерываем обработку строк {file_path}.")
                        return  # Выходим из handle_file_change
                    # Используем line_processor
                    norm_path = os.path.normpath(file_path)
                    server_id = self.log_file_to_server_id.get(norm_path)
                    if server_id:
                        await self.line_processor.process_line(line.strip(), server_id)
            except Exception as e:
                self.logger.error(f"Ошибка при обработке файла {file_path}: {e}")

        loop = asyncio.get_event_loop()
        await watch_directory(os.path.dirname(log_file_path), handle_file_change, loop)

    def get_connected_players(self, query=None):
        """
        Обработчик GetPlayerCountQuery.
        :param query: Объект с .server_id или None
        :return: Количество игроков
        """
        if query is None or not hasattr(query, "server_id"):
            # Если нет server_id — возвращаем пустой словарь
            self.logger.error("Запрос без server_id")
            return {}
        server_id = query.server_id
        return self.connected_players.get(server_id, {})

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
            self.ddos_protection.stop()
        self.logger.info("LogParser остановлен.")
