# src/query_server/query_request/player_query.py

import struct
from mediator.mediator import Mediator

mediator = Mediator()


async def player_query(data, addr, challenge_numbers, players):
    """
    Обрабатывает запрос A2S_PLAYER.
    :param data: Входящие данные запроса.
    :param addr: Адрес клиента.
    :param challenge_numbers: Словарь challenge numbers для проверки запроса.
    :param players: Список или словарь игроков.
    :return: Байтовый ответ на запрос A2S_PLAYER или None, если запрос некорректен.
    """
    # Преобразуем список игроков в словарь, если это необходимо
    if isinstance(players, list):
        players = {player["steam_id"]: player for player in players}

    # Извлекаем challenge number (последние 4 байта)
    challenge_number = data[-4:]
    received_challenge_number = struct.unpack('<I', challenge_number)[0]

    # Проверяем challenge number
    if received_challenge_number != 0:
        expected_challenge_number = challenge_numbers.get(addr)
        if expected_challenge_number is None or expected_challenge_number != received_challenge_number:
            # Логируем ошибку через медиатор
            mediator.notify("logger", {"message": f"Некорректный challenge number: ожидался "
                                                  f"{expected_challenge_number}, получен {received_challenge_number}",
                                       "level": "warning"})
            return None

        # Удаляем challenge number из памяти после использования
        del challenge_numbers[addr]

    # Формируем ответ
    response = b'\xFF\xFF\xFF\xFFD' + struct.pack('B', len(players))  # Количество игроков

    for idx, (steam_id, player_data) in enumerate(players.items()):
        # Проверяем, что у игрока есть имя
        if "name" not in player_data:
            mediator.notify("logger", {"message": f"Недостаточно данных для игрока с ID {steam_id}. "
                                                  f"Пропускаем.", "level": "warning"})
            continue

        # Добавляем данные игрока в ответ
        response += struct.pack('B', idx + 1)  # Идентификатор игрока
        response += player_data["name"].encode('utf-8') + b'\x00'  # Имя игрока (с завершающим нулем)
        response += struct.pack('<i', 0)  # Счет игрока (little-endian)
        response += struct.pack('<f', 0)  # Время игры (little-endian)

    return response
