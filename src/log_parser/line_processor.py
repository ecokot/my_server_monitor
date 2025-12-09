# src/log_parser/line_processor.py
import asyncio
from datetime import datetime
from typing import Dict, Optional
from src.events.types import PlayersChangedEvent
from src.constants import (
    IP_TIMESTAMP_PATTERN,
    UNIFIED_LOGIN_PATTERN,
    LOGOUT_PATTERN_LOBBY,
    LOGOUT_PATTERN_SERVER,
    LOGIN_PATTERN_SERVER,
    JOIN_NICKNAME_SERVER)


class LogLineProcessor:
    def __init__(self, connected_players: Dict, player_manager, ddos_protection, mediator, logger):
        # Это будет ссылка на словарь из LogParser, чтобы обновлять состояние
        self.connected_players = connected_players
        self.player_manager = player_manager
        self.ddos_protection = ddos_protection
        self.mediator = mediator
        self.logger = logger
        self.pending_steam_id: Optional[str] = None

    async def process_line(self, line: str, server_id: str, is_history: bool = False):
        if not line:
            return

        # 0. Сначала: проверка, не является ли строка "Join succeeded" и есть ли ожидание ID (на сервере)
        join_match = JOIN_NICKNAME_SERVER.search(line)
        if self.pending_steam_id and join_match:
            steam_id = self.pending_steam_id
            player_name = join_match.group(1)

            self.logger.debug(f"Сопоставлено: SteamID {steam_id} -> Nick {player_name} на сервере {server_id}")

            # Инициализируем сервер, если нужно
            if server_id not in self.connected_players:
                self.connected_players[server_id] = {}

            existing_player = self.connected_players[server_id].get(steam_id)

            if not existing_player:
                # Обновляем/сохраняем в players_data
                current_name = self.player_manager.get_player_name(steam_id)
                if not current_name or current_name != player_name:
                    self.player_manager.update_player(steam_id, player_name)
                    self.player_manager.save_if_needed()

                # Добавляем в онлайн
                self.connected_players[server_id][steam_id] = {
                    "name": player_name,
                    "server_id": server_id,
                    "login_time": datetime.now().isoformat()
                }
                self.logger.info(f"Игрок подключился: {player_name} (SteamID: {steam_id}) к серверу {server_id}")
                #await self._notify_players_changed(server_id)

            elif existing_player["name"].startswith("Unknown_"):
                old_name = existing_player["name"]
                existing_player["name"] = player_name
                self.player_manager.update_player(steam_id, player_name)
                self.player_manager.save_if_needed()
                self.logger.debug(f"Обновлено имя игрока {steam_id}: {old_name} → {player_name}")
                self.logger.info(f"Игрок теперь известен: {player_name} (SteamID: {steam_id})")

            self.pending_steam_id = None
            return

        # 1. DDoS Detection (остаётся)
        if is_history:
            ip_match = IP_TIMESTAMP_PATTERN.search(line)
            if ip_match:
                timestamp_str, ip = ip_match.groups()
                if not self.ddos_protection.is_blocked(ip):
                    self.ddos_protection.add_request(ip, timestamp_str)

        # 2. PostLogin — ожидание ника
        post_login_match = LOGIN_PATTERN_SERVER.search(line)
        if post_login_match:
            steam_id = post_login_match.group(1)
            self.pending_steam_id = steam_id
            self.logger.debug(f"Обнаружен SteamID {steam_id}, ожидаем ник на сервере {server_id}")
            return

        # 3. Основной вход
        login_match = UNIFIED_LOGIN_PATTERN.search(line)
        if login_match:
            steam_id = login_match.group(1) or login_match.group(3)

            if not steam_id:
                return

            # Инициализируем сервер
            if server_id not in self.connected_players:
                self.connected_players[server_id] = {}

            # Проверяем, есть ли уже на этом сервере
            if steam_id in self.connected_players[server_id]:
                self.logger.debug(f"Игрок {steam_id} уже в сети на сервере {server_id}. Пропускаем.")
                return

            parsed_name = login_match.group(2)
            current_name = self.player_manager.get_player_name(steam_id)

            if parsed_name:
                if not current_name or current_name != parsed_name:
                    updated = self.player_manager.update_player(steam_id, parsed_name)
                    if updated:
                        self.player_manager.save_if_needed()
                final_name = parsed_name
            else:
                final_name = current_name or f"Unknown_{steam_id}"

            # Убедимся, что имя есть в player_manager
            if steam_id not in self.player_manager.get_all_data():
                self.player_manager.update_player(steam_id, final_name)
                self.player_manager.save_if_needed()

            self.connected_players[server_id][steam_id] = {
                "name": final_name,
                "server_id": server_id,
                "login_time": datetime.now().isoformat()
            }
            self.logger.info(f"Игрок подключился: {final_name} (SteamID: {steam_id}) к серверу {server_id}")
            return

        # 4. Выход
        logout_match = LOGOUT_PATTERN_LOBBY.search(line) or LOGOUT_PATTERN_SERVER.search(line)
        if logout_match:
            steam_id = logout_match.group(1).strip()

            if server_id in self.connected_players and steam_id in self.connected_players[server_id]:
                player_name = self.connected_players[server_id][steam_id]["name"]
                del self.connected_players[server_id][steam_id]
                self.logger.info(f"Игрок отключился: {player_name} (SteamID: {steam_id}) с сервера {server_id}")
                #await self._notify_players_changed(server_id)
            else:
                self.logger.debug(f"Отключение неотслеживаемого игрока: {steam_id} с сервера {server_id}")
            return

    async def _notify_players_changed(self, server_id: str):
        if self.mediator:
            try:
                players_for_server = self.connected_players.get(server_id, {})
                await asyncio.create_task(self.mediator.publish(PlayersChangedEvent(server_id=server_id,
                                                                                    players_data=players_for_server)))
                self.logger.debug(f"Отправлено событие PlayersChangedEvent для сервера {server_id}")
            except Exception as e:
                self.logger.error(f"Ошибка при отправке PlayersChangedEvent: {e}")

    def reset_pending_steam_id(self):
        self.pending_steam_id = None
