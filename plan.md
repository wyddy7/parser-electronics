# План: Price Parser MVP

## Цель

Создать рабочий парсер для electronpribor.ru с современными best practices: структурное логирование, retry механизм, CSS селекторы.

## Структура проекта

```
etalon-parser/
├── config.yaml                    # Конфигурация
├── src/
│   ├── __init__.py
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── base_parser.py         # Базовый класс с Session + retry
│   │   └── electronpribor_parser.py
│   ├── excel/
│   │   ├── __init__.py
│   │   ├── reader.py              # Pandas для чтения
│   │   └── writer.py              # OpenPyXL для записи с форматированием
│   ├── logger.py                  # Structlog конфигурация
│   ├── config_loader.py           # Загрузка YAML
│   └── main.py                    # CLI точка входа
├── output/                        # Выходные файлы
├── logs/                          # Логи в JSON
├── requirements.txt
└── README.md
```

## Реализация по шагам

### 1. Базовая настройка проекта

Создать `requirements.txt`:

```
requests==2.31.0
beautifulsoup4==4.12.0
lxml==4.9.0              # Быстрый парсер для BeautifulSoup
pandas==2.1.3
openpyxl==3.1.2
pyyaml==6.0.1
click==8.1.7
tqdm==4.66.1
structlog==24.1.0        # Структурное логирование
urllib3==2.1.0           # Для retry механизма
```

Создать `config.yaml`:

```yaml
parser:
  electronpribor:
    enabled: true
    base_url: "https://www.electronpribor.ru"
    delays:
      between_requests: 1.5  # секунды
    retry:
      total: 3               # Количество повторов
      backoff_factor: 0.3    # 0.3, 0.6, 1.2 секунды
      status_forcelist: [429, 500, 502, 503, 504]
    timeout: 10              # Таймаут запроса (секунды)
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

excel:
  input_file: "jshopping_export_2025-11-06_20-07-59.xlsx"
  output_dir: "output"
  name_column: "name_ru-RU"  # Колонка с названием товара

search:
  min_similarity: 0.7  # Минимальное совпадение названия (0-1)
  max_results: 5       # Сколько результатов поиска проверять

logging:
  level: "DEBUG"           # DEBUG для разработки
  console: true            # Вывод в консоль
  file: "logs/parser.log"  # Файл для логов
  format: "json"           # json для production, console для dev
```

### 2. Структурное логирование (structlog)

`src/logger.py` - настройка structlog:

- DEBUG уровень по умолчанию
- ConsoleRenderer для разработки (цветной вывод)
- JSONRenderer + dict_tracebacks для production/файлов
- Автоматические временные метки (ISO 8601)
- Контекстные поля (product_name, parser_name, step)

Пример использования:

```python
log = structlog.get_logger()
log = log.bind(parser="electronpribor", product="Б5-7")
log.info("search_started", query="Б5-7 источник")
log.debug("request_sent", url="...", method="GET")
log.error("price_not_found", reason="empty_selector")
```

### 3. Загрузчик конфигурации

`src/config_loader.py`:

- Загрузка YAML через PyYAML
- Валидация обязательных полей
- Возврат typed dict для удобства

### 4. Excel Reader

`src/excel/reader.py` (на основе pandas):

- `read_excel()` с автоопределением первого листа
- Поиск колонки `name_ru-RU`
- Очистка данных (strip, убрать NaN)
- Возврат полного DataFrame

### 5. Базовый парсер (с retry и Session)

`src/parsers/base_parser.py`:

Ключевые практики из Context7:

- Использовать `requests.Session()` для переиспользования соединений
- Настроить `HTTPAdapter` с `urllib3.util.Retry`:
  - total=3 повтора
  - backoff_factor=0.3
  - status_forcelist=[429, 500, 502, 503, 504]
- Context manager для правильного закрытия сессии
- `.raise_for_status()` для обработки HTTP ошибок
- Таймауты на каждый запрос
- User-Agent в headers

Структура:

```python
class BaseParser:
    def __init__(self, config, logger):
        self.session = self._create_session()
        self.log = logger.bind(parser=self.__class__.__name__)
    
    def _create_session(self):
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.3, 
                       status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        return session
    
    def search_product(self, name):
        # Абстрактный метод
        raise NotImplementedError
    
    def close(self):
        self.session.close()
```

### 6. Парсер для electronpribor.ru

`src/parsers/electronpribor_parser.py`:

Ключевые практики из Context7:

- BeautifulSoup с `lxml` парсером (быстрее html.parser)
- CSS селекторы через `.select()` и `.select_one()`
- Обработка пустых результатов
- Структурное логирование на каждом шаге

Логика:

1. Формировать URL поиска (изучить структуру на сайте)
2. Отправить GET запрос через self.session
3. Парсить HTML: `BeautifulSoup(response.text, 'lxml')`
4. Найти контейнер результатов: `soup.select('.search-results .item')`
5. Для каждого результата:

   - Извлечь название: `.select_one('.product-name')`
   - Сравнить с запросом (fuzzy match)
   - Если подходит - извлечь цену: `.select_one('.price')`

6. Логировать каждый шаг
7. Вернуть найденную цену или None

### 7. Excel Writer

`src/excel/writer.py` (pandas + openpyxl):

- Копировать оригинальный DataFrame
- Добавить колонки: `Цена Electronpribor`, `Дата парсинга`, `Статус`
- Заполнить данными из результатов парсинга
- Сохранить через `df.to_excel()` с openpyxl engine
- Применить базовое форматирование:
  - Жирные заголовки
  - Автоширина колонок
  - Цветовая кодировка статусов (зеленый=найдено, красный=не найдено)

### 8. Main CLI

`src/main.py` (click для CLI):

```bash
python src/main.py --config config.yaml --limit 10  # Тест
python src/main.py --config config.yaml             # Полный прогон
```

Логика:

1. Настроить structlog из конфига
2. Загрузить конфиг
3. Прочитать Excel
4. Создать парсер (с контекстным менеджером)
5. Для каждого товара (с tqdm прогресс-баром):

   - Логировать начало обработки
   - Вызвать parser.search_product()
   - Обработать исключения
   - Логировать результат

6. Закрыть парсер
7. Записать результаты в новый Excel
8. Логировать итоговую статистику

### 9. Тестирование

1. Запустить на 1 товаре - проверить логи
2. Запустить на 5 товарах - проверить retry механизм
3. Запустить на 10 товарах - проверить выходной файл
4. Проверить JSON логи в файле

## Best Practices из Context7

1. **Requests**:

   - Session для переиспользования соединений
   - HTTPAdapter + Retry для устойчивости
   - Timeout на каждый запрос
   - Context manager или явный .close()

2. **BeautifulSoup**:

   - lxml парсер (быстрее)
   - CSS селекторы (.select, .select_one)
   - Проверка на None перед извлечением данных

3. **Structlog**:

   - Bind для контекста (parser, product)
   - Dict tracebacks для исключений
   - JSON в файлы, Console для терминала
   - Уровень DEBUG для детальной отладки

## Порядок разработки

1. Настроить structlog + config_loader
2. Реализовать excel reader + тест чтения
3. Изучить electronpribor.ru (вручную через DevTools)
4. Реализовать base_parser с Session + retry
5. Реализовать electronpribor_parser
6. Тест парсера на 1 товаре
7. Реализовать excel writer
8. Собрать main.py
9. Тестовый прогон на 10 товарах
10. Финальная проверка логов и выходного файла