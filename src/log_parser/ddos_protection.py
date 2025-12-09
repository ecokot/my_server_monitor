from datetime import datetime, timedelta
from collections import defaultdict
import json
import ctypes
import os
import sys
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
            config_blocked_ips_file: str = "./data/blocked_ips.json",
            logger=None
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
        self.logger = logger
        # Новая проверка
        self.admin_access = self._is_admin()
        if not self.admin_access:
            self.logger.warning("Предупреждение: Приложение запущено без прав администратора. Функция блокировки IP"
                              " через netsh будет отключена.")

        self.ip_data = defaultdict(list)  # Активные запросы: ip -> [timestamps]
        self.blocked_ips: Dict[str, str] = self._load_blocked_ips()  # ip -> isoformat времени блокировки

        self.cleanup_task: Optional[asyncio.Task] = None

    def _is_admin(self):
        """Проверяет, запущено ли приложение с правами администратора."""
        try:
            # Для Windows
            if sys.platform.startswith('win'):
                return ctypes.windll.shell32.IsUserAnAdmin()
            else:
                # Для Unix-систем проверяем эффективный UID
                return os.geteuid() == 0
        except AttributeError:
            # Если ctypes.windll.shell32 или os.geteuid недоступны (редко)
            self.logger.warning("Не удалось проверить права администратора: библиотека ctypes недоступна.")
            return False
        except OSError:
            # os.geteuid может бросить OSError на Windows
            self.logger.warning("Не удалось проверить права администратора: ошибка получения UID.")
            return False

    def start(self, loop: asyncio.AbstractEventLoop):
        """Запускает фоновую задачу очистки"""
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = loop.create_task(self._periodic_cleanup())

    def stop(self):
        """Останавливает фоновую задачу"""
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            self.logger.debug("DDOSProtection остановлен.")

    def add_request(self, ip: str, timestamp: str):
        """
        Добавить запрос от IP.
        :param ip: IP-адрес
        :param timestamp: Временная метка в формате "2025.12.02-18.25.17:533"
        """
        try:
            dt = datetime.strptime(timestamp, "%Y.%m.%d-%H.%M.%S:%f")
        except ValueError:
            self.logger.error(f"Некорректный формат временной метки: {timestamp}")
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
                self.logger.info("Фоновая задача DDOSProtection остановлена.")
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
        """Блокирует IP через netsh и сохраняет в файл, если есть права администратора."""
        if self.is_blocked(ip):
            return

        if not self.admin_access:
            # Если нет прав, просто логируем, что IP должен быть заблокирован, но не блокируем через netsh
            self.logger.warning(
                f"Нет прав администратора: невозможно заблокировать IP {ip} через netsh. IP добавлен в список"
                f" ожидания.")
            # Все равно сохраняем в файл, чтобы не забыть
            self.blocked_ips[ip] = datetime.now().isoformat()
            self._save_blocked_ips()
            return

        try:
            result = subprocess.run(
                f'netsh advfirewall firewall add rule name="Block MOE IP {ip}" '
                f'dir=in action=block remoteip={ip}',
                shell=True,
                check=True,
                timeout=5
            )
            # check=True означает, что subprocess.CalledProcessError будет выброшен, если returncode != 0
            self.logger.warning(f"IP {ip} успешно заблокирован через netsh.")
        except subprocess.TimeoutExpired:
            self.logger.error(f"Таймаут при попытке заблокировать IP {ip} через netsh.")
            # Не сохраняем в файл, если команда не завершена
            return
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Ошибка при блокировке IP {ip} через netsh (return code {e.returncode}): {e}")
            # Не сохраняем в файл, если команда вернула ошибку
            return
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при блокировке IP {ip} через netsh: {e}")
            # Не сохраняем в файл, если произошла другая ошибка
            return

        # Только если netsh прошла успешно, сохраняем в файл
        self.blocked_ips[ip] = datetime.now().isoformat()
        self._save_blocked_ips()

    def _unblock_ip(self, ip: str):
        """Разблокирует IP (удаляет правило), если есть права администратора."""
        if not self.admin_access:
            # Если нет прав, логируем, что разблокировка невозможна
            self.logger.warning(
                f"Нет прав администратора: невозможно разблокировать IP {ip} через netsh. Попробуйте перезапустить с "
                f"правами администратора.")
            # Удаляем из *внутреннего* списка, чтобы не пытаться разблокировать снова при следующем цикле
            # Но не пытаемся выполнить команду netsh
            return

        try:
            result = subprocess.run(
                f'netsh advfirewall firewall delete rule name="Block MOE IP {ip}"',
                shell=True,
                check=True,
                timeout=5
            )
            self.logger.info(f"IP {ip} разблокирован через netsh (время истекло).", "info")
        except subprocess.TimeoutExpired:
            self.logger.error(f"Таймаут при попытке разблокировать IP {ip} через netsh.")
            # Не удаляем из внутреннего списка, чтобы попробовать снова позже
            return
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Ошибка при разблокировке IP {ip} через netsh (return code {e.returncode}): {e}")
            # Не удаляем из внутреннего списка, чтобы попробовать снова позже
            return
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при разблокировке IP {ip} через netsh: {e}")
            # Не удаляем из внутреннего списка, чтобы попробовать снова позже
            return

        # Только если netsh прошла успешно, удаляем из внутреннего списка и сохраняем
        if ip in self.blocked_ips:
            del self.blocked_ips[ip]
        self._save_blocked_ips()

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
            self.logger.error(f"Не удалось сохранить blocked_ips.json: {e}")

# Глобальный экземпляр (опционально, если хочешь singleton)
# ddos_protection = DDOSProtection()
