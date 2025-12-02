from datetime import datetime, timedelta
from collections import defaultdict
import json
import os
import subprocess
import asyncio
from typing import Optional, Callable, Dict


class DDOSProtection:
    def __init__(
        self,
        threshold: int = 50,
        interval: int = 60,
        block_duration_hours: int = 24,
        log_callback: Optional[Callable] = None,
        config_blocked_ips_file: str = "./data/blocked_ips.json"
    ):
        """
        :param threshold: Кол-во запросов за интервал, после которого IP блокируется
        :param interval: Интервал в секундах (например, 60 = за 1 минуту)
        :param block_duration_hours: Сколько часов блокировать IP
        :param log_callback: Функция для логирования (например, logger.info)
        :param config_blocked_ips_file: Путь к файлу с заблокированными IP
        """
        self.threshold = threshold
        self.interval = interval
        self.block_duration = timedelta(hours=block_duration_hours)
        self.log_callback = log_callback or print
        self.blocked_ips_file = config_blocked_ips_file

        self.ip_data = defaultdict(list)  # Активные запросы: ip -> [timestamps]
        self.blocked_ips: Dict[str, str] = self._load_blocked_ips()  # ip -> isoformat времени блокировки

        self.cleanup_task: Optional[asyncio.Task] = None

    def start(self, loop: asyncio.AbstractEventLoop):
        """Запускает фоновую задачу очистки"""
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = loop.create_task(self._periodic_cleanup())

    def stop(self):
        """Останавливает фоновую задачу"""
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            self.log_callback("DDOSProtection остановлен.")

    def add_request(self, ip: str, timestamp: str):
        """
        Добавить запрос от IP.
        :param ip: IP-адрес
        :param timestamp: Временная метка в формате "2025.12.02-18.25.17:533"
        """
        try:
            dt = datetime.strptime(timestamp, "%Y.%m.%d-%H.%M.%S:%f")
        except ValueError:
            self._log(f"Некорректный формат временной метки: {timestamp}", level="error")
            return

        # Очищаем старые записи
        self._cleanup_old_requests(ip, dt)

        # Добавляем новую
        self.ip_data[ip].append(dt)

        # Проверяем на DDoS
        if len(self.ip_data[ip]) >= self.threshold:
            self._block_ip(ip)
            del self.ip_data[ip]  # Очищаем очередь

    def is_blocked(self, ip: str) -> bool:
        """Проверить, заблокирован ли IP"""
        if ip not in self.blocked_ips:
            return False
        blocked_at = datetime.fromisoformat(self.blocked_ips[ip])
        return datetime.now() - blocked_at < self.block_duration

    def _cleanup_old_requests(self, ip: str, current_time: datetime):
        """Удаляет старые запросы (вне интервала)"""
        cutoff = current_time - timedelta(seconds=self.interval)
        self.ip_data[ip] = [t for t in self.ip_data[ip] if t > cutoff]
        if not self.ip_data[ip]:
            del self.ip_data[ip]

    async def _periodic_cleanup(self):
        """Фоновая задача: очистка старых данных и разблокировка IP"""
        while True:
            try:
                await asyncio.sleep(10)
                now = datetime.now()

                # Очистка активных запросов
                for ip in list(self.ip_data.keys()):
                    self._cleanup_old_requests(ip, now)

                # Разблокировка IP по времени
                self._unblock_expired_ips(now)

            except asyncio.CancelledError:
                self._log("Фоновая задача DDOSProtection остановлена.", "info")
                break

    def _unblock_expired_ips(self, current_time: datetime):
        """Разблокировать IP, чья блокировка истекла"""
        released = []
        for ip, blocked_at_str in self.blocked_ips.items():
            try:
                blocked_at = datetime.fromisoformat(blocked_at_str)
                if current_time - blocked_at >= self.block_duration:
                    self._unblock_ip(ip)
                    released.append(ip)
            except ValueError:
                released.append(ip)  # Удаляем битые записи

        for ip in released:
            del self.blocked_ips[ip]
        if released:
            self._save_blocked_ips()

    def _block_ip(self, ip: str):
        """Блокирует IP через netsh и сохраняет в файл"""
        if self.is_blocked(ip):
            return

        try:
            subprocess.run(
                f'netsh advfirewall firewall add rule name="Block MOE IP {ip}" '
                f'dir=in action=block remoteip={ip}',
                shell=True,
                check=True,
                timeout=5
            )
            self._log(f"IP {ip} успешно заблокирован.", "warning")
        except subprocess.SubprocessError as e:
            self._log(f"Ошибка при блокировке IP {ip}: {e}", "error")

        self.blocked_ips[ip] = datetime.now().isoformat()
        self._save_blocked_ips()

    def _unblock_ip(self, ip: str):
        """Разблокирует IP (удаляет правило)"""
        try:
            subprocess.run(
                f'netsh advfirewall firewall delete rule name="Block MOE IP {ip}"',
                shell=True,
                check=True,
                timeout=5
            )
            self._log(f"IP {ip} разблокирован (время истекло).", "info")
        except subprocess.SubprocessError as e:
            self._log(f"Ошибка при разблокировке IP {ip}: {e}", "error")

    def _load_blocked_ips(self) -> Dict[str, str]:
        """Загрузить список заблокированных IP из файла"""
        if os.path.exists(self.blocked_ips_file):
            try:
                with open(self.blocked_ips_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_blocked_ips(self):
        """Сохранить список заблокированных IP"""
        try:
            os.makedirs(os.path.dirname(self.blocked_ips_file), exist_ok=True)
            with open(self.blocked_ips_file, "w", encoding="utf-8") as f:
                json.dump(self.blocked_ips, f, indent=4, ensure_ascii=False)
        except OSError as e:
            self._log(f"Не удалось сохранить blocked_ips.json: {e}", "error")

    def _log(self, message: str, level: str = "info"):
        """Универсальный логгер (можно подменить на logger.info и т.п.)"""
        self.log_callback(f"[DDOSProtection] {level.upper()}: {message}")


# Глобальный экземпляр (опционально, если хочешь singleton)
# ddos_protection = DDOSProtection()