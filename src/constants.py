# src.constants
import re

# Паттерн для извлечения IP-адреса и временной метки
IP_TIMESTAMP_PATTERN = re.compile(
    r"\[(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3})\].*accepted from: (\d+\.\d+\.\d+\.\d+)"
)

# Регулярные выражения для парсинга строк
LOGIN_PATTERN_SERVER = re.compile(r"PostLogin Account:\s*(\d+)")
JOIN_PATTERN_SERVER = re.compile(r"Join succeeded:\s*(\w+)")
LOGOUT_PATTERN_SERVER = re.compile(r"Logout Account:\s*(\d+)")

LOGIN_PATTERN_LOBBY = re.compile(r"ASGGameModeLobby::LobbyClientLogin NickName = ([^,]+), UniqueId = (\d+)")
LOGOUT_PATTERN_LOBBY = re.compile(r"ASGGameModeLobby::LobbyClientLogOut Account: (\d+)")

# Регулярное выражение для извлечения IP-адресов
IP_PATTERN = re.compile(r'accepted from: (\d+\.\d+\.\d+\.\d+):\d+')

UNIFIED_LOGIN_PATTERN = re.compile(
    r"(?:PostLogin Account:\s*(\d+))|"
    r"(?:ASGGameModeLobby::LobbyClientLogin NickName = ([^,]+), UniqueId = (\d+))"
)

A2S_INFO = re.compile(rb'^\xFF\xFF\xFF\xFFTSource Engine Query\x00$')
A2S_SERVERQUERY_GETCHALLENGE = re.compile(rb'^\xFF\xFF\xFF\xFFU\x00\x00\x00\x00$')
A2S_PLAYER = re.compile(rb'^\xFF\xFF\xFF\xFF[UV](.{4})$')

