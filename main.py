import asyncio
import signal
from src.events.types import GetPlayerCountQuery
from src.config import Config
from src.logger import LoggerMixin
from src.log_parser.log_parser import LogParser


class MainApp(LoggerMixin):
    def __init__(self):
        super().__init__()
        self.log_parser = None
        self.running = True

    async def run(self):
        self.logger.info("Starting application...")

        config = Config()
        self.log_parser = LogParser(config=config)

        # Запускаем парсинг
        log_parser_task = asyncio.create_task(self.log_parser.start_parsing())

        # Пример: запрос количества игроков через 5 секунд
        await asyncio.sleep(5)
        try:
            player_count = self.log_parser.get_connected_players(None)
            self.logger.info(f"Connected players: {len(player_count)}")
        except Exception as e:
            self.logger.error(f"Не удалось получить количество игроков: {e}")

        # Ожидаем завершения (на практике — бесконечно, пока не Ctrl+C)
        try:
            await asyncio.gather(log_parser_task)
        except (asyncio.CancelledError, KeyboardInterrupt):
            self.logger.info("LogParser task was cancelled. Shutting down...")
            await self.log_parser.shutdown()
            self.running = False
            return  # ✅ ВЫХОДИМ

    async def shutdown(self):
        """Корректное завершение всех компонентов"""
        if self.log_parser:
            await self.log_parser.shutdown()


async def main():
    app = MainApp()

    # Регистрация обработчиков сигналов
    def handle_shutdown():
        if not app.running:
            return  # ✅ Защита от повторного вызова
        print("\nReceived shutdown signal...")
        asyncio.create_task(app.shutdown())
        app.running = False

    signal.signal(signal.SIGINT, lambda s, f: handle_shutdown())
    signal.signal(signal.SIGTERM, lambda s, f: handle_shutdown())

    await app.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Application interrupted. Exiting cleanly.")