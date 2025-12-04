# Логирование и ротация логов в проекте

## Общая информация

В проекте используется модуль логирования с автоматической ротацией файлов. Это означает, что при определенных условиях (в данном случае - при смене даты) текущий файл лога переименовывается, и создается новый файл с тем же именем.

## Поведение при смене даты

При наступлении полуночи (00:00) происходит ротация лог-файла:
- Файл `./logs/MOEService.log` переименовывается в `./logs/MOEService.log.YYYY-MM-DD`
- Создается новый файл `./logs/MOEService.log` для записи новых логов

## Как это работает

Ротация реализована с помощью `TimedRotatingFileHandler` с параметрами:
- `when="midnight"` - ротация происходит в полночь
- `interval=1` - интервал в 1 день
- `backupCount=7` - хранится до 7 архивных файлов логов
- `encoding="utf-8"` - кодировка файлов

## Решение проблемы недоступности файла

Если ваша система ожидает найти лог-файл с определенным именем, учтите следующее:

1. **Текущий лог-файл** всегда будет доступен по пути `./logs/MOEService.log`
2. **Архивные лог-файлы** будут иметь суффикс с датой, например: `MOEService.log.2025-12-04`
3. При мониторинге логов рекомендуется:
   - Читать текущий файл `MOEService.log` для новых записей
   - Для просмотра исторических данных использовать файлы с суффиксами дат
   - При необходимости читать как текущий, так и архивные файлы

## Пример получения всех лог-файлов

```python
import os
from datetime import datetime, timedelta

def get_log_files(log_directory="./logs", base_name="MOEService.log"):
    """Получить список всех файлов логов (текущий и архивные)"""
    all_files = []
    current_file = os.path.join(log_directory, base_name)
    if os.path.exists(current_file):
        all_files.append(current_file)
    
    # Найти все файлы с суффиксом даты
    for filename in os.listdir(log_directory):
        if filename.startswith(base_name + ".") and len(filename) == len(base_name) + 11:  # base_name + "." + "YYYY-MM-DD"
            all_files.append(os.path.join(log_directory, filename))
    
    return sorted(all_files)
```

## Уведомления о ротации

Система логирования теперь включает уведомления о ротации файлов. При ротации в лог будет добавлена запись вида:
```
[2025-12-04 00:00:01,001][INFO] - SomeClass - Log file rotated: ./logs/MOEService.log -> ./logs/MOEService.log.2025-12-04
```

## Настройка параметров ротации

Параметры ротации можно изменить в файле `src/logger.py` в строке создания `TimedRotatingFileHandler`.