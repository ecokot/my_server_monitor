# MOE Server Monitor

This is a server monitoring application for Myth of Empires (MOE) game servers. The application monitors server logs, tracks player connections/disconnections, detects DDoS attacks, and provides server query functionality.

## Features

- **Log Parsing**: Monitors MOE server log files in real-time
- **Player Tracking**: Tracks player connections and disconnections
- **DDoS Detection**: Detects potential DDoS attacks based on IP connection patterns
- **Query Server**: Responds to A2S_INFO, A2S_PLAYER, and A2S_SERVERQUERY_GETCHALLENGE requests
- **Event Mediator**: Uses a mediator pattern for event handling and communication

## Architecture

### Core Components

1. **Mediator Pattern**: Centralized event handling system
2. **Log Parser**: Parses game server logs and extracts player/connection data
3. **Query Server**: Handles Steam query protocol requests
4. **Configuration System**: JSON-based configuration with dynamic loading

### Directory Structure

```
/workspace/
├── config.json                 # Configuration file
├── main.py                     # Main application entry point
├── requirements.txt            # Python dependencies
├── logs/                       # Log files directory
├── src/                        # Source code
│   ├── config.py              # Configuration management
│   ├── constants.py           # Regular expressions and constants
│   ├── logger.py              # Logging utilities
│   ├── singleton.py           # Singleton pattern implementation
│   ├── events/                # Event types and definitions
│   ├── mediator/              # Mediator pattern implementation
│   ├── log_parser/            # Log parsing functionality
│   ├── query_server/          # Steam query server implementation
│   └── utils/                 # Utility functions
```

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure the application by editing `config.json`

3. Run the application:
```bash
python main.py
```

## Configuration

The `config.json` file contains:

- Server IP and game version
- Log file paths and settings
- Telegram bot token and admin settings
- DDoS detection thresholds
- Server configuration (name, ports, etc.)

## Event System

The application uses a mediator pattern for communication:

- `PlayerJoinedEvent`: Triggered when a player joins
- `DdosEvent`: Triggered when DDoS attack is detected
- `GetPlayerCountQuery`: Request for current player count
- `GetConnectedPlayersQuery`: Request for connected player list

## Query Server Protocol

The query server supports:
- A2S_INFO: Server information request
- A2S_PLAYER: Player list request
- A2S_SERVERQUERY_GETCHALLENGE: Challenge number request

## Logging

The application provides comprehensive logging with:
- File-based logging with rotation
- Console logging with colors
- Configurable log levels
- Per-class logger instances

### Log File Rotation

The application uses automatic log file rotation that occurs at midnight every day:
- Current log file `./logs/MOEService.log` is renamed to `./logs/MOEService.log.YYYY-MM-DD`
- A new `./logs/MOEService.log` file is created for new log entries
- Up to 7 days of archived logs are kept
- When accessing logs programmatically, account for this rotation behavior
- For more details, see the `LOGGING_GUIDE.md` file