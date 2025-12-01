# src/query_server/query_request/challenge_query.py
import random
import struct


async def challenge_query(addr, challenge_numbers):
    """
    Обрабатывает запрос A2S_SERVERQUERY_GETCHALLENGE.
    """
    # Генерируем случайный challenge number
    challenge_number = random.randint(1, 2 ** 32 - 1)
    packed_challenge_number = struct.pack('<I', challenge_number)  # Little-endian

    # Сохраняем challenge number для этого адреса
    challenge_numbers[addr] = challenge_number
    # Формируем ответ
    response = b'\xFF\xFF\xFF\xFFA' + packed_challenge_number
    return response
