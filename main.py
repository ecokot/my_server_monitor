import asyncio
import signal
from src.events.types import GetPlayerCountQuery
from src.config import Config
from src.logger import LoggerMixin
from src.log_parser.log_parser import LogParser
from src.mediator.mediator import Mediator

class MainApp(LoggerMixin):
    def __init__(self):
        super().__init__()
        self.log_parser = None
        self.running = True
        self.shutdown_event = asyncio.Event()

    async def run(self):
        self.logger.info("Starting application...")

        config = Config()
        mediator = Mediator(config)
        self.log_parser = LogParser(mediator=mediator, config=config, shutdown_event=self.shutdown_event)

        log_parser_task = asyncio.create_task(self.log_parser.start_parsing())
        #------------------Подписка на события------------------
        mediator.subscribe(GetPlayerCountQuery, self.log_parser.get_connected_players)

        #------------------Тестова зона-------------------------
        if not self.shutdown_event.is_set():
            await asyncio.sleep(5)
        if not self.shutdown_event.is_set():
            try:
                player_count = mediator.request(GetPlayerCountQuery(server_id="1005"))
                self.logger.info(f"Connected players: {player_count}")
            except Exception as e:
                self.logger.error(f"Не удалось получить количество игроков: {e}")
        #------------------Конец тестовой зоны------------------

        await self.shutdown_event.wait()
        self.logger.info("Received shutdown signal. Cancelling LogParser task...")
        log_parser_task.cancel()

        try:
            await log_parser_task
        except asyncio.CancelledError:
            self.logger.info("LogParser task was cancelled.")
        except Exception:
            self.logger.exception("LogParser task failed during shutdown.")


        await self.log_parser.shutdown()
        self.running = False
        self.logger.info("Application shutdown complete.")

    async def shutdown(self):
        if self.log_parser:
            await self.log_parser.shutdown()


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