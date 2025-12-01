# src/query_server/query_server.py

import asyncio_dgram
from src.mediator.mediator import Mediator
from src.config import Config
from src.constants import A2S_INFO, A2S_SERVERQUERY_GETCHALLENGE, A2S_PLAYER
from src.query_server.query_request.info_query import info_query
from src.query_server.query_request.challenge_query import challenge_query
from src.query_server.query_request.player_query import player_query


class QueryServer:
    """
    Класс QueryServer обрабатывает входящие UDP-запросы и взаимодействует с другими компонентами через медиатор.
    """

    def __init__(self, mediator=None):
        """
        Инициализация QueryServer.
        :param mediator: Экземпляр медиатора для обмена событиями.
        """
        self.mediator = mediator
        self.config = Config()  # Загружаем конфигурацию
        self.server_ip = self.config.get("SERVER_IP", "127.0.0.1")  # Поле IP-адреса сервера
        self.query_port = self.config.get("QUERY_PORT", 12888)  # Поле порта для запросов (берем из конфига)
        self.players_data = {}  # Данные о игроках по умолчанию
        self.game_version = self.config.get("VERSION_GAME", "1.1.0").encode('utf-8')  # Версия игры
        self.challenge_numbers = {}

    async def handle_request(self, request_type, data, addr):

        """
        Обрабатывает входящий запрос.
        :param addr: ip-адрес и порт откуда пришел запрос
        :param request_type: Тип запроса (например, A2S_INFO, A2S_PLAYER).
        :param data: Данные запроса (если есть).
        """
        if request_type == "A2S_INFO":
            # Уведомляем медиатор о необходимости получить данные о игроках
            # Формируем ответ
            server_name = self.config.get("SERVERS.1005.SERVER_NAME", "[RU][PVE]Siberian MOE")
            game_port = self.config.get("SERVERS.1005.GAME_PORT", 11888)
            return await info_query(self.players_data, self.config.get("VERSION_GAME", "1.1.0"), server_name, game_port)
        elif request_type == "A2S_SERVERQUERY_GETCHALLENGE":
            # Формируем ответ
            return await challenge_query(addr[0], self.challenge_numbers)
        elif request_type == "A2S_PLAYER":
            # Формируем ответ
            return await player_query(data, addr[0], self.challenge_numbers, self.players_data)

    def handle_event(self, event_type, data):
        """
        Обрабатывает события, уведомленные медиатором.
        :param event_type: Тип события (например, get_players_response).
        :param data: Данные события (если есть).
        """
        if event_type == "get_players_response":
            # Сохраняем данные о игроках, полученные от медиатора
            self.players_data = data or {}
        elif event_type == "get_game_version_response":
            # Сохраняем версию игры, полученную от медиатора
            self.game_version = data or b'1.1.0'

    async def main(self):
        """
        Основной цикл работы Query-сервера.
        """
        self.mediator.notify("logger", {"message": f"Запуск QueryServer...", "level": "info"})
        stream = None
        try:
            # Создаем DatagramStream
            stream = await asyncio_dgram.bind((self.server_ip, self.query_port))
            self.mediator.notify("logger", {"message": f"QueryServer запущен на {self.server_ip}:{self.query_port}",
                                            "level": "info"})
            while True:
                try:
                    data, addr = await stream.recv()
                    self.mediator.notify("logger", {"message": f"Получен запрос от {addr}: {data}", "level": "debug"})

                    # Определяем тип запроса и сообщаем медиатору
                    response = await self.route_request(data, addr)
                    if response:
                        await stream.send(response, addr)
                        self.mediator.notify("logger", {"message": f"Отправлен ответ клиенту {addr[0]}:{addr[1]}: "
                                                                   f"{response}", "level": "debug"})
                    else:
                        self.mediator.notify("logger",
                                             {"message": f"Не сформировался ответ в обработчике", "level": "warning"})
                except Exception as e:
                    self.mediator.notify("logger", {"message": f"Произошла ошибка при обработке запроса: {e}",
                                                    "level": "error"})
        except Exception as e:
            self.mediator.notify("logger", {"message": f"Критическая ошибка: {e}", "level": "error"})
        finally:
            # Закрываем соединение
            if stream:
                stream.close()
                self.mediator.notify("logger", {"message": f"Соединение asyncio_dgram закрыто.", "level": "info"})

    async def route_request(self, data, addr):
        """
        Определяет тип запроса.
        """
        # Проверяем, является ли запрос A2S_INFO
        if A2S_INFO.match(data):
            self.mediator.notify("logger", {"message": f"Получен корректный запрос A2S_INFO от {addr[0]}:{addr[1]}",
                                            "level": "info"})
            return await self.handle_request('A2S_INFO', data, addr)
        elif A2S_SERVERQUERY_GETCHALLENGE.match(data):
            self.mediator.notify("logger", {"message": f"Получен корректный запрос A2S_SERVERQUERY_GETCHALLENGE от "
                                                       f"{addr[0]}:{addr[1]}", "level": "info"})
            return await self.handle_request('A2S_SERVERQUERY_GETCHALLENGE', data, addr)
        elif A2S_PLAYER.match(data):
            self.mediator.notify("logger", {"message": f"Получен корректный запрос A2S_PLAYER от "
                                                       f"{addr[0]}:{addr[1]}", "level": "info"})
            return await self.handle_request('A2S_PLAYER', data, addr)
