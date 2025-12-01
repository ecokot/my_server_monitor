# src/query_server/query_request/info_query.py
import struct
from config.settings import GAME_PORT, GAME_APP_ID, SERVER_NAME


async def info_query(players_data, game_version):
    # Формируем ответ
    extra_data_flags = 0x80 | 0x10 | 0x20 | 0x01  # Флаги: порт, Steam ID, keywords, Game ID
    packed_port = struct.pack('<H', GAME_PORT)  # Порт сервера (16-битное целое, little-endian)
    steam_id = 90263762545778710
    packed_steam_id = struct.pack('<Q', steam_id)  # Steam ID (uint64, little-endian)
    game_id = int(GAME_APP_ID)
    packed_game_id = struct.pack('<Q', game_id)  # Game ID (uint64, little-endian)
    keywords = (
            b'BUILDID:0,OWNINGID:90263762545778710,OWNINGNAME:' + SERVER_NAME + b',SESSIONFLAGS:552,'
                                                                                b'MATCHTIMEOUT_f:120.000000,GameMode_s:SG\x00')
    response = (
            b'\xFF\xFF\xFF\xFF' +  # Префикс ответа
            b'I' +  # Тип ответа (A2S_INFO)
            b'\x11' +  # Версия протокола (17)
            SERVER_NAME + b'\x00' +  # Название сервера
            b'Map_Lobby\x00' +  # Карта
            b'MOE\x00' +  # Папка игры
            b'MOE\x00' +  # Игра
            b'\x00\x00' +  # ID игры (0)
            struct.pack('B', len(players_data)) +  # Игроки (текущее количество)
            b'\x64' +  # Максимум игроков (100)
            b'\x00' +  # Боты (0)
            b'd' +  # Тип сервера ('d' для dedicated)
            b'w' +  # Платформа ('w' для Windows)
            b'\x00' +  # Пароль (password_protected)
            b'\x01' +  # VAC (1 - включен, 0 - выключен)
            game_version + b'\x00' +  # Версия игры
            struct.pack('B', extra_data_flags) +  # Extra Data Flags
            packed_port +  # Порт сервера (если установлен флаг 0x80)
            packed_steam_id +  # Steam ID (если установлен флаг 0x10)
            keywords +  # Keywords (если установлен флаг 0x20)
            packed_game_id  # Game ID (если установлен флаг 0x01)
    )
    return response
