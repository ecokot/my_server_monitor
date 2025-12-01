# src/main.py

import asyncio
from src.mediator.mediator import Mediator
from src.events.types import PlayerJoinedEvent, GetPlayerCountQuery, DdosEvent, GetConnectedPlayersQuery
from src.config import Config
from src.logger import LoggerMixin
from src.log_parser.log_parser import LogParser


class MainApp(LoggerMixin):
    def __init__(self):
        super().__init__()

    async def run(self):
        self.logger.info("Starting application...")

        config = Config()
        mediator = Mediator(config)

        # Подписка на события и запросы
        mediator.subscribe(PlayerJoinedEvent, async_print_player)
        mediator.subscribe(PlayerJoinedEvent, sync_print_player)
        mediator.subscribe(DdosEvent, handle_ddos_event) # <-- Подписываемся на DDoS события

        mediator.register_handler(GetPlayerCountQuery, lambda q: 42) # <-- Временный обработчик
        # mediator.register_handler(GetConnectedPlayersQuery, ...) # <-- LogParser сам зарегистрирует обработчик

        # --- Интеграция LogParser ---
        log_parser = LogParser(mediator=mediator, config=config) # <-- Создаем LogParser
        # Запускаем парсинг в фоновой задаче
        log_parser_task = asyncio.create_task(log_parser.start_parsing())

        # Пример отправки события PlayerJoinedEvent
        await mediator.publish(PlayerJoinedEvent("Артём"))
        player_count = mediator.request(GetPlayerCountQuery())
        print(f"Player count (from mediator): {player_count}")
        print(f"Telegram token: {mediator.config.get('TELEGRAM.TOKEN')}")

        # Пример запроса количества подключенных игроков через медиатор (LogParser должен зарегистрировать обработчик)
        try:
            connected_players = mediator.request(GetConnectedPlayersQuery())
            print(f"Connected players (from LogParser via mediator): {len(connected_players)} - {connected_players}")
        except ValueError:
            print("Обработчик GetConnectedPlayersQuery не зарегистрирован или не найден.")

        # Ждем log_parser_task (в реальном приложении это может быть бесконечное ожидание)
        # await log_parser_task

        self.logger.info("Application finished.")


async def async_print_player(event):
    await asyncio.sleep(1)
    print("ASYNC:", event.player_name)


def sync_print_player(event):
    print("SYNC:", event.player_name)


def handle_ddos_event(event: DdosEvent):
    print(f"[DDOS EVENT] IP: {event.ip}, Time: {event.timestamp}, File: {event.log_file}")


async def main():
    app = MainApp()
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())