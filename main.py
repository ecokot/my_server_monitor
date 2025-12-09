# src/main.py

import asyncio
import signal
from src.events.types import GetPlayerCountQuery
from src.logger import Logger
from src.log_parser.log_parser import LogParser
from src.mediator.mediator import Mediator
from src.query_server.query_server import QueryServer


class MainApp:
    def __init__(self):
        super().__init__()
        self.query_server2 = None
        self.logger = None
        self.log_parser = None
        self.query_server = None
        self.running = True
        self.shutdown_event = asyncio.Event()

    async def run(self):
        config = Config()
        self.logger = Logger(config)
        self.logger.info("Starting application...")

        config = Config()
        mediator = Mediator(config, logger=self.logger)

        # Инициализируем LogParser
        self.log_parser = LogParser(mediator=mediator, config=config, shutdown_event=self.shutdown_event)

        # --- Инициализируем QueryServer для конкретного сервера ---
        #  Получаем ID сервера из конфига (например, первый доступный)
        server_ids = list(config.get("SERVERS", {}).keys())
        if not server_ids:
            self.logger.error("Не найдено ни одного сервера в конфиге. Выход.")
            return

        target_server_id = server_ids[0]  # Или можно жестко задать: target_server_id = "1005"
        self.logger.info(f"Запуск QueryServer для сервера ID: {target_server_id}")
        self.query_server = QueryServer(mediator=mediator, server_id=target_server_id, logger=self.logger)
        #  target_server_id1 = server_ids[1]
        #  self.logger.info(f"Запуск QueryServer для сервера ID: {target_server_id1}")
        #  self.query_server2 = QueryServer(mediator=mediator, server_id=target_server_id1, logger=self.logger)

        # Создаём задачи
        log_parser_task = asyncio.create_task(self.log_parser.start_parsing())
        query_server_task = asyncio.create_task(self.query_server.main())  # <-- Новая задача

        #  ------------------Подписка на события------------------
        # Теперь GetPlayerCountQuery будет обрабатываться LogParser'ом
        mediator.subscribe(GetPlayerCountQuery,
                           self.log_parser.get_connected_players)  # <-- Убираем, т.к. register_handler

        #  ------------------Тестова зона-------------------------
        if not self.shutdown_event.is_set():
            await asyncio.sleep(5)
        if not self.shutdown_event.is_set():
            try:
                # mediator.subscribe(PlayersChangedEvent, self.query_server.handle_players_changed_event)
                # Передаём server_id в запрос
                player_data = mediator.request(GetPlayerCountQuery(server_id=target_server_id))

                self.logger.info(f"Connected players on server {target_server_id}: {len(player_data)}")
            except Exception as e:
                self.logger.error(f"Не удалось получить количество игроков: {e}")
        #  ------------------Конец тестовой зоны------------------

        await self.shutdown_event.wait()
        self.logger.info("Received shutdown signal. Cancelling tasks...")

        # Отменяем все задачи
        log_parser_task.cancel()
        query_server_task.cancel()  # <-- Отменяем задачу QueryServer

        # Ждём завершения задач
        try:
            await asyncio.gather(log_parser_task, query_server_task, return_exceptions=True)
            self.logger.info("LogParser and QueryServer tasks were cancelled.")
        except Exception:
            self.logger.exception("Tasks failed during shutdown.")

        await self.log_parser.shutdown()
        self.running = False
        self.logger.info("Application shutdown complete.")

    async def shutdown(self):
        if self.log_parser:
            await self.log_parser.shutdown()
        # QueryServer завершится сам через CancelledError


async def main():
    app = MainApp()

    def handle_shutdown(signum, frame):
        if not app.running:
            return
        app.logger.info(f"Received shutdown signal {signum}. Shutting down...")
        app.shutdown_event.set()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    await app.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        print("Application exited cleanly.")
