# src/query_server/query_server.py
import asyncio

import asyncio_dgram
from src.events.types import PlayersChangedEvent, GetPlayerCountQuery
from src.constants import A2S_INFO, A2S_SERVERQUERY_GETCHALLENGE, A2S_PLAYER
from src.query_server.query_request.info_query import info_query
from src.query_server.query_request.challenge_query import challenge_query
from src.query_server.query_request.player_query import player_query
from src.config import Config


class QueryServer:
    """
    Класс QueryServer обрабатывает входящие UDP-запросы и взаимодействует с другими компонентами через медиатор.
    """

    def __init__(self, mediator=None, server_id=None, logger=None):
        """
        Инициализация QueryServer.
        :param mediator: Экземпляр медиатора для обмена событиями.
        :param server_id: ID сервера из конфига (например, '1005').
        """
        self.mediator = mediator
        self.config = self.mediator.config or Config()  # Загружаем конфигурацию
        self.logger = logger or self.mediator.logger  # Используем логгер из медиатора, если он предоставлен

        if not server_id:
            self.logger.error("server_id должен быть указан для QueryServer")
            raise ValueError("server_id должен быть указан для QueryServer")

        # Получаем настройки конкретного сервера
        servers_config = self.config.get("SERVERS", {})
        server_config = servers_config.get(server_id, {})
        if not server_config:
            self.logger.error(f"Конфигурация для сервера с ID {server_id} не найдена в конфиге.")
            raise ValueError(f"Конфигурация для сервера с ID {server_id} не найдена в конфиге.")

        self.server_id = server_id
        self.server_ip = self.config.get("SERVER_IP", "127.0.0.1")  # Общий IP-адрес сервера
        # Используем QUERY_PORT из конфигурации конкретного сервера
        self.query_port = server_config.get("QUERY_PORT", 12888)
        self.players_data = {}  # Данные о подключенных игроках для этого сервера
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
            # Уведомляем медиатор о необходимости получить данные о подключенных игроках для ЭТОГО сервера
            # Формируем ответ
            server_name = self.config.get(f"SERVERS.{self.server_id}.SERVER_NAME", f"[{self.server_id}] Default Server")
            game_port = self.config.get(f"SERVERS.{self.server_id}.GAME_PORT", 11888)
            # Передаем количество подключенных игроков для этого сервера
            self.players_data = self.mediator.request(GetPlayerCountQuery(server_id=self.server_id))
            return await info_query(self.players_data, self.config.get("VERSION_GAME", "1.1.0"), server_name,
                                    game_port)
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
            # Сохраняем данные о подключенных игроках, полученные от медиатора
            # Предполагаем, что data = {steam_id: player_data} для конкретного сервера
            # NOTE: Этот вызов может быть инициирован LogParser'ом при изменении состояния
            # или по запросу от медиатора. Пока что просто обновляем.
            # Важно: LogParser должен передавать данные только для *этого* server_id
            # или мы должны фильтровать здесь.
            # Для простоты сейчас обновляем всё.
            self.players_data = data or {}
            self.logger.debug(
                f"QueryServer {self.server_id}: Обновлены данные подключенных игроков. Количество: {len(self.players_data)}")

    async def main(self):
        """
        Основной цикл работы Query-сервера.
        """
        self.logger.info(f"QueryServer {self.server_id}: Запуск на {self.server_ip}:{self.query_port}...")
        stream = None
        try:
            # Создаем DatagramStream
            stream = await asyncio_dgram.bind((self.server_ip, self.query_port))
            self.logger.info(f"QueryServer {self.server_id}: Слушаю на {self.server_ip}:{self.query_port}")
            while True:
                try:
                    data, addr = await stream.recv()
                    self.logger.debug(f"QueryServer {self.server_id}: Получен запрос от {addr}: {data}")

                    # Определяем тип запроса и сообщаем медиатору
                    response = await self.route_request(data, addr)
                    if response:
                        await stream.send(response, addr)
                        self.logger.debug(f"QueryServer {self.server_id}: Отправлен ответ клиенту {addr[0]}:{addr[1]} - {response}")
                    else:
                        self.logger.warning(f"QueryServer {self.server_id}: Не сформировался ответ в обработчике")
                except Exception as e:
                    self.logger.error(f"QueryServer {self.server_id}: Ошибка при обработке запроса: {e}")
        except asyncio.CancelledError:
            self.logger.info(f"QueryServer {self.server_id}: Задача отменена, завершаю работу.")
        except Exception as e:
            self.logger.error(f"QueryServer {self.server_id}: Критическая ошибка: {e}")
        finally:
            # Закрываем соединение
            if stream:
                stream.close()
                self.logger.info(f"QueryServer {self.server_id}: Соединение asyncio_dgram закрыто.")

    async def route_request(self, data, addr):
        """
        Определяет тип запроса.
        """
        # Проверяем, является ли запрос A2S_INFO
        if A2S_INFO.match(data):
            self.logger.info(f"QueryServer {self.server_id}: Получен A2S_INFO от {addr[0]}:{addr[1]}")
            player_data = self.mediator.request(GetPlayerCountQuery(server_id=self.server_id))

            self.logger.info(f"Connected players on server {self.server_id}: {len(player_data)}")
            return await self.handle_request('A2S_INFO', data, addr)
        elif A2S_SERVERQUERY_GETCHALLENGE.match(data):
            self.logger.info(
                f"QueryServer {self.server_id}: Получен A2S_SERVERQUERY_GETCHALLENGE от {addr[0]}:{addr[1]}")
            return await self.handle_request('A2S_SERVERQUERY_GETCHALLENGE', data, addr)
        elif A2S_PLAYER.match(data):
            self.logger.info(f"QueryServer {self.server_id}: Получен A2S_PLAYER от {addr[0]}:{addr[1]}")
            return await self.handle_request('A2S_PLAYER', data, addr)

    def handle_players_changed_event(self, event: PlayersChangedEvent):
        """
        Обработчик события об изменении игроков.
        :param event: Объект PlayersChangedEvent
        """
        # Обновляем данные только если событие касается *нашего* server_id
        if event.server_id == self.server_id:
            self.players_data = event.players_data
            self.logger.debug(
                f"QueryServer {self.server_id}: Обновлены данные подключенных игроков из события."
                f" Количество: {len(self.players_data)}")

        else:
            # self.logger.debug(f"QueryServer {self.server_id}: Игнорирую событие для сервера {event.server_id}")
            pass
