# src/events/types.py
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class PlayerJoinedEvent:
    player_name: str


@dataclass
class GetPlayerCountQuery:
    server_id: str

@dataclass
class DdosEvent:
    ip: str
    timestamp: str
    log_file: str


@dataclass
class LogFileChangedEvent:
    file_path: str
    line: str

@dataclass
class PlayersChangedEvent:
    server_id: str
    players_data: Dict[str, Any] # {steam_id: player_data}