# src/mediator/mediator.py

import asyncio
from collections import defaultdict
from src.config import Config
from src.logger import LoggerMixin


class Mediator(LoggerMixin):  # <-- Наследуем от LoggerMixin
    def __init__(self, config=None):
        super().__init__()  # <-- Вызываем миксин
        self.config = config or Config()
        self._event_handlers = defaultdict(list)
        self._request_handlers = {}

    def subscribe(self, event_type, handler):
        self.logger.debug(f"Подписываем обработчик {handler.__name__} на событие {event_type.__name__}")
        self._event_handlers[event_type].append(handler)

    async def publish(self, event):
        self.logger.debug(f"Публикуем событие: {type(event).__name__}")
        tasks = []
        for handler in self._event_handlers[type(event)]:
            if asyncio.iscoroutinefunction(handler):
                task = handler(event)
            else:
                task = asyncio.to_thread(handler, event)
            tasks.append(task)
        await asyncio.gather(*tasks)

    def register_handler(self, request_type, handler):
        self.logger.debug(f"Регистрируем обработчик {handler.__name__} для запроса {request_type.__name__}")
        self._request_handlers[request_type] = handler

    def request(self, query):
        handler = self._request_handlers.get(type(query))
        if not handler:
            self.logger.error(f"Нет обработчика для запроса {type(query).__name__}")
            raise ValueError('Нет подписки на этот запрос')
        self.logger.debug(f"Передаем запрос обработчику {type(query).__name__}")
        return handler(query)