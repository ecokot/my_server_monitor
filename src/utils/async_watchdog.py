# src/utils/async_watchdog.py
import asyncio
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class AsyncEventHandler(FileSystemEventHandler):
    def __init__(self, callback, loop):
        self.callback = callback
        self.loop = loop  # Сохраняем ссылку на цикл событий

    def on_modified(self, event):
        if not event.is_directory:
            # Выполняем корутину в основном цикле событий
            asyncio.run_coroutine_threadsafe(self.callback(event.src_path), self.loop)
    
    def on_created(self, event):
        if not event.is_directory:
            # Выполняем корутину в основном цикле событий
            asyncio.run_coroutine_threadsafe(self.callback(event.src_path), self.loop)
    
    def on_deleted(self, event):
        if not event.is_directory:
            # Выполняем корутину в основном цикле событий
            asyncio.run_coroutine_threadsafe(self.callback(event.src_path), self.loop)
    
    def on_moved(self, event):
        if not event.is_directory:
            # Обрабатываем перемещение/переименование файлов
            # Вызываем callback для обоих путей: старого и нового
            if event.src_path:
                asyncio.run_coroutine_threadsafe(self.callback(event.src_path), self.loop)
            if event.dest_path:
                asyncio.run_coroutine_threadsafe(self.callback(event.dest_path), self.loop)


async def watch_directory(directory, callback, loop):
    """
    Асинхронно отслеживает изменения в указанной директории.
    :param directory: Директория для наблюдения.
    :param callback: Функция обратного вызова при изменении файла.
    :param loop: Цикл событий для выполнения асинхронных задач.
    """
    observer = Observer()
    handler = AsyncEventHandler(callback, loop)  # Передаем цикл событий
    observer.schedule(handler, directory, recursive=False)

    # Запуск наблюдателя в отдельном потоке
    await loop.run_in_executor(None, observer.start)

    try:
        while True:
            await asyncio.sleep(1)  # Основной цикл для поддержания работы
    except asyncio.CancelledError:
        observer.stop()
        observer.join()