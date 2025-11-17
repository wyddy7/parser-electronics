# Price Parser

Парсер цен с сайта electronpribor.ru для Excel файлов.

## Установка

```bash
pip install -r requirements.txt
```

## Использование

```bash
# Тестовый прогон на 10 товарах
python src/main.py --config config.yaml --limit 10

# Полный прогон всех товаров
python src/main.py --config config.yaml
```

## Структура проекта

```
etalon-parser/
├── config.yaml                    # Конфигурация
├── src/
│   ├── parsers/
│   │   ├── base_parser.py         # Базовый класс с Session + retry
│   │   └── electronpribor_parser.py
│   ├── excel/
│   │   ├── reader.py              # Чтение Excel
│   │   └── writer.py              # Запись Excel
│   ├── logger.py                  # Structlog конфигурация
│   ├── config_loader.py           # Загрузка YAML
│   └── main.py                    # CLI точка входа
├── output/                        # Выходные файлы
├── logs/                          # Логи в JSON
└── requirements.txt
```

## Конфигурация

Настройки в `config.yaml`:
- Параметры парсера (URL, задержки, retry)
- Путь к входному Excel файлу
- Параметры поиска товаров
- Настройки логирования

## Логирование

- Структурное логирование через structlog
- DEBUG уровень для детальной отладки
- JSON логи в файле `logs/parser.log`
- Цветной вывод в консоль при разработке

