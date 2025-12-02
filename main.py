# main.py
import asyncio
import signal
# ... другие импорты ...
from src.events.types import GetPlayerCountQuery
from src.config import Config
from src.logger import LoggerMixin
from src.log_parser.log_parser import LogParser


class MainApp(LoggerMixin):
    def __init__(self):
        super().__init__()
        self.log_parser = None
        self.running = True
        # Создаем asyncio.Event для сигнала остановки
        self.shutdown_event = asyncio.Event()

    async def run(self):
        self.logger.info("Starting application...")

        config = Config()
        # Передаем shutdown_event в LogParser
        self.log_parser = LogParser(config=config, shutdown_event=self.shutdown_event)

        # Запускаем парсинг
        log_parser_task = asyncio.create_task(self.log_parser.start_parsing())

        # Пример: запрос количества игроков через 5 секунд
        # Важно: проверить, не был ли сигнал остановки до sleep
        if not self.shutdown_event.is_set():
            await asyncio.sleep(5)

        if not self.shutdown_event.is_set():
            try:
                player_count = self.log_parser.get_connected_players(None)
                self.logger.info(f"Connected players: {len(player_count)}")
            except Exception as e:
                self.logger.error(f"Не удалось получить количество игроков: {e}")

        # Ожидаем завершения (на практике — ждем сигнал остановки)
        await self.shutdown_event.wait() # Ждем, пока shutdown_event.set() не будет вызван

        # После получения сигнала остановки, отменяем задачу парсера
        self.logger.info("Received shutdown signal. Cancelling LogParser task...")
        log_parser_task.cancel()

        try:
            # Ждем, пока задача корректно завершится (обработает CancelledError)
            await log_parser_task
        except asyncio.CancelledError:
            self.logger.info("LogParser task was cancelled.")
        # except Exception:
        #     self.logger.exception("LogParser task failed with an exception during shutdown.")

        # Вызываем shutdown для финализации
        await self.log_parser.shutdown()
        self.running = False
        self.logger.info("Application shutdown complete.")


async def main():
    app = MainApp()

    # Регистрация обработчиков сигналов
    def handle_shutdown(signum, frame):
        if not app.running:
            return  # Защита от повторного вызова
        print(f"\nReceived shutdown signal {signum}...")
        # Устанавливаем событие остановки, которое будет перехвачено в run()
        app.shutdown_event.set()
        # app.running = False # app.running теперь управляется через shutdown_event

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
    print("Application exited cleanly.")