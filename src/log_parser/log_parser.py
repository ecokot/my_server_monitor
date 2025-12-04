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
        self.players_data_file = self.config.get("PLAYERS_DATA_FILE", "./data/players_data.json")
        self.player_manager = PlayersDataManager(self.players_data_file, self.logger, save_interval=300)
        self.line_processor = LogLineProcessor(self.connected_players, self.player_manager, None,
                                               self.mediator, self.logger)
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
        if self.shutdown_event.is_set():
            self.logger.info("LogParser: Получен сигнал остановки перед запуском.")
            return

        self.log_files = self.get_configured_log_files()
        if not self.log_files:
            self.logger.warning("Не найдены пути к лог-файлам в конфиге.")
            return

        self.logger.debug(f"Парсинг логов: {self.log_files}")

        if self.mediator:
            self.mediator.register_handler(GetPlayerCountQuery, self.get_connected_players)

        try:
            for log_file in self.log_files:
                if self.shutdown_event.is_set():
                    self.logger.info("LogParser: Получен сигнал остановки, прерываю создание задач.")
                    break
                task = asyncio.create_task(self._parse_single_log(log_file))
                self.tasks.append(task)

            if self.tasks:
                # Основное ожидание всех задач
                await asyncio.gather(*self.tasks, return_exceptions=True)

        except asyncio.CancelledError:
            self.logger.info("LogParser.start_parsing: Задача была отменена.")
            # Отменяем подзадачи
            for task in self.tasks:
                if not task.done():
                    task.cancel()
            # Дожидаемся их завершения
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)
            raise  # Поднимаем CancelledError дальше
        finally:
            self.logger.debug("LogParser.start_parsing: Завершение метода парсинга.")

    async def _parse_single_log(self, log_file_path):
        # Проверяем сигнал остановки перед началом парсинга файла
        if self.shutdown_event.is_set():
            self.logger.debug(f"LogParser: Получен сигнал остановки, пропускаю файл {log_file_path}.")
            return

        if not os.path.exists(log_file_path):
            self.logger.error(f"Файл логов не найден: {log_file_path}")
            # Ждем некоторое время и проверяем снова, так как файл может быть создан позже
            for _ in range(10):  # Проверяем в течение 10 секунд
                await asyncio.sleep(1)
                if os.path.exists(log_file_path):
                    self.logger.info(f"Файл логов найден: {log_file_path}")
                    break
            else:
                self.logger.error(f"Файл логов так и не был создан: {log_file_path}")
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
                norm_path = os.path.normpath(log_file_path)
                server_id = self.log_file_to_server_id.get(norm_path)
                if server_id:
                    await self.line_processor.process_line(line.strip(), server_id, is_history=True)
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге истории {log_file_path}: {e}")

    async def _parse_real_time(self, log_file_path):
        # Проверяем сигнал остановки перед началом реального времени
        if self.shutdown_event.is_set():
            self.logger.debug(f"LogParser: Получен сигнал остановки, пропускаю реальный парсинг {log_file_path}.")
            return

        # Для отслеживания ротации логов будем хранить текущий файл и его inode
        current_log_file = log_file_path
        initial_inode = self._get_file_inode(current_log_file)
        
        offset_tracker = {'offset': os.path.getsize(current_log_file) if os.path.exists(current_log_file) else 0}
        self.logger.debug(f"Offset файла {current_log_file}: {offset_tracker['offset']}")

        # Внутренняя функция для обработки изменений файла
        async def handle_file_change(file_path):
            # Проверяем сигнал остановки
            if self.shutdown_event.is_set():
                return
            
            # Проверяем, является ли это изменение нашего целевого файла или файла с тем же именем/шаблоном
            file_basename = os.path.basename(file_path)
            target_basename = os.path.basename(current_log_file)
            
            # Проверяем, что это нужный файл (по точному совпадению имени или по базовому имени)
            # Это позволяет обрабатывать файлы типа MOEService.log, MOEService.log.1, MOEService.log.2023-01-01
            is_target_file = (
                file_basename == target_basename or  # Точный совпадение
                os.path.normpath(file_path) == os.path.normpath(current_log_file) or  # Тот же путь
                (file_basename.startswith(target_basename) and 
                 (file_basename == target_basename or 
                  file_basename[len(target_basename)] in ['.', '-', '_']))  # Файл с суффиксом (например, .1, .2023-01-01)
            )
            
            if not is_target_file:
                return
            
            # Проверяем, не произошла ли ротация файла (изменился inode или файл перестал существовать)
            current_inode = self._get_file_inode(current_log_file)
            if current_inode is not None and initial_inode != current_inode:
                # Произошла ротация файла - обновляем текущий файл и сбрасываем смещение
                self.logger.info(f"Обнаружена ротация лог-файла: {current_log_file}")
                offset_tracker['offset'] = 0  # Начинаем читать новый файл с начала
                # Обновляем inode для нового файла
                new_inode = self._get_file_inode(current_log_file)
                if new_inode is not None:
                    initial_inode = new_inode
            elif current_inode is None and os.path.exists(current_log_file):
                # Файл был удален и создан заново
                self.logger.info(f"Файл был создан заново: {current_log_file}")
                offset_tracker['offset'] = 0
                new_inode = self._get_file_inode(current_log_file)
                if new_inode is not None:
                    initial_inode = new_inode

            try:
                # Проверяем, существует ли файл
                if not os.path.exists(file_path):
                    return
                    
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
                        return  # Выходим из handle_file_change
                    norm_path = os.path.normpath(file_path)
                    server_id = self.log_file_to_server_id.get(norm_path)
                    if server_id:
                        await self.line_processor.process_line(line.strip(), server_id)
            except Exception as e:
                # Проверяем, является ли ошибка связанной с доступом к файлу
                if "No such file or directory" in str(e) or "Permission denied" in str(e) or "Bad file descriptor" in str(e):
                    self.logger.warning(f"Файл больше не доступен {file_path}: {e}. Проверяю ротацию логов...")
                    # Возможно, произошла ротация файла
                    if os.path.exists(current_log_file):
                        # Если целевой файл существует, обновляем смещение
                        try:
                            offset_tracker['offset'] = os.path.getsize(current_log_file)
                            self.logger.info(f"Обновлено смещение для файла {current_log_file}: {offset_tracker['offset']}")
                        except Exception as size_error:
                            self.logger.error(f"Не удалось обновить смещение для файла {current_log_file}: {size_error}")
                    else:
                        # Файл не существует, возможно, он еще не создан
                        self.logger.info(f"Целевой файл {current_log_file} не существует, ждем его создания...")
                else:
                    self.logger.error(f"Ошибка при обработке файла {file_path}: {e}")

        loop = asyncio.get_event_loop()
        await watch_directory(os.path.dirname(log_file_path), handle_file_change, loop)

    def _get_file_inode(self, file_path):
        """Получает inode файла для определения ротации"""
        try:
            if os.path.exists(file_path):
                stat = os.stat(file_path)
                return stat.st_ino
            return None
        except OSError:
            return None

    def get_connected_players(self, query=None):
        """
        Обработчик запроса на получение списка подключенных игроков.
        """
        if query is None or not hasattr(query, "server_id"):
            self.logger.error("Нет server_id")
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
