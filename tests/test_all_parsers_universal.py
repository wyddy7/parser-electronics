"""Универсальный тестовый скрипт для проверки всех парсеров на одинаковых запросах"""
import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# Исправляем кодировку для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Добавляем путь к src (из tests/ в корень проекта)
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config_loader import ConfigLoader
from logger import configure_logging
from parsers.factory import create_async_parser

# Список всех парсеров
ALL_PARSERS = [
    'electronpribor',
    'prist',
    'chipdip',
    'keysight_technologies',
    'mprofit',
    'pribor_x',
    'zenit_electro',
    'flukeshop',
]

# Универсальные тестовые запросы (должны работать на всех парсерах)
# Формат: (запрос, описание)
UNIVERSAL_TEST_QUERIES = [
    ("Fluke 87V", "Популярный мультиметр Fluke"),
    ("DT-902", "Индикатор CEM"),
    ("Agilent E4418B", "Измеритель мощности Agilent"),
    ("HIOKI 3390", "Измеритель мощности HIOKI"),
    ("АКИП-2502", "Измеритель мощности АКИП"),
    ("мультиметр", "Общий запрос - мультиметр"),
    ("осциллограф", "Общий запрос - осциллограф"),
    # Специфичные товары для проверки конкретных магазинов
    ("DSOX1204A", "Осциллограф Keysight (для проверки keysight_technologies)"),
]

async def test_parser_query(parser_name: str, query: str, config_loader: ConfigLoader, log) -> Dict[str, Any]:
    """Тестирует один парсер на одном запросе"""
    try:
        parser_config = config_loader.get_parser_config(parser_name)
        search_config = config_loader.get_search_config()
        
        parser_instance = create_async_parser(parser_name, parser_config, log, search_config)
        
        async with parser_instance:
            result = await parser_instance.search_product(query)
            
            return {
                'parser': parser_name,
                'query': query,
                'success': True,
                'found': result is not None and result.get('name') is not None,
                'price': result.get('price') if result else None,
                'price_type': None if not result else (
                    'price' if result.get('price', 0) > 0 else
                    'on_request' if result.get('price') == -2.0 else
                    'discontinued' if result.get('price') == -1.0 else
                    'none'
                ),
                'name': result.get('name') if result else None,
                'url': result.get('url') if result else None,
                'error': None
            }
    except Exception as e:
        return {
            'parser': parser_name,
            'query': query,
            'success': False,
            'found': False,
            'price': None,
            'price_type': None,
            'name': None,
            'url': None,
            'error': str(e)
        }

async def test_all_parsers_universal():
    """Тестирует все парсеры на универсальных запросах"""
    
    # Загружаем конфигурацию (из корня проекта)
    config_path = Path(__file__).parent.parent / 'config.yaml'
    config_loader = ConfigLoader(str(config_path))
    search_config = config_loader.get_search_config()
    
    # Настраиваем логирование
    logging_config = config_loader.get_logging_config()
    logging_config['level'] = 'WARNING'  # Только WARNING и выше (меньше шума)
    log = configure_logging(logging_config)
    log = log.bind(component="test_universal")
    
    print(f"\n{'='*100}")
    print(f"УНИВЕРСАЛЬНОЕ ТЕСТИРОВАНИЕ ВСЕХ ПАРСЕРОВ")
    print(f"{'='*100}")
    print(f"\nВремя запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nПарсеры для тестирования: {', '.join(ALL_PARSERS)}")
    print(f"Универсальные запросы: {len(UNIVERSAL_TEST_QUERIES)}")
    print(f"\n{'='*100}\n")
    
    # Проверяем доступность парсеров
    available_parsers = []
    for parser_name in ALL_PARSERS:
        try:
            parser_config = config_loader.get_parser_config(parser_name)
            if parser_config.get('enabled', True):
                async_config = parser_config.get('async', {})
                if async_config.get('enabled', False):
                    available_parsers.append(parser_name)
                else:
                    print(f"[SKIP] {parser_name}: async не включен")
            else:
                print(f"[SKIP] {parser_name}: отключен в конфиге")
        except ValueError:
            print(f"[SKIP] {parser_name}: не найден в конфиге")
    
    if not available_parsers:
        print("[ERROR] Нет доступных парсеров для тестирования!")
        return
    
    print(f"Доступные парсеры ({len(available_parsers)}): {', '.join(available_parsers)}\n")
    print(f"{'='*100}\n")
    
    # Тестируем каждый запрос на всех парсерах
    all_results = []
    
    for query, description in UNIVERSAL_TEST_QUERIES:
        print(f"\n{'─'*100}")
        print(f"ЗАПРОС: {query}")
        print(f"Описание: {description}")
        print(f"{'─'*100}\n")
        
        # Запускаем тесты параллельно для всех парсеров
        tasks = [
            test_parser_query(parser_name, query, config_loader, log)
            for parser_name in available_parsers
        ]
        
        query_results = await asyncio.gather(*tasks)
        all_results.extend(query_results)
        
        # Выводим результаты для этого запроса
        for result in query_results:
            parser_name = result['parser']
            if result['success']:
                if result['found']:
                    price = result['price']
                    price_type = result['price_type']
                    
                    if price_type == 'price':
                        status = f"✅ НАЙДЕН: {price:,.0f} руб."
                    elif price_type == 'on_request':
                        status = "⚠️  ПО ЗАПРОСУ"
                    elif price_type == 'discontinued':
                        status = "❌ СНЯТ С ПРОИЗВОДСТВА"
                    else:
                        status = "⚠️  НАЙДЕН (без цены)"
                    
                    print(f"  {parser_name:25} → {status}")
                    if result['name']:
                        name_short = result['name'][:60] + "..." if len(result['name']) > 60 else result['name']
                        print(f"    {'':25}   {name_short}")
                else:
                    print(f"  {parser_name:25} → ❌ НЕ НАЙДЕН")
            else:
                print(f"  {parser_name:25} → 🔴 ОШИБКА: {result['error']}")
        
        print()  # Пустая строка между запросами
    
    # Итоговая статистика
    print(f"\n{'='*100}")
    print(f"ИТОГОВАЯ СТАТИСТИКА ПО ПАРСЕРАМ")
    print(f"{'='*100}\n")
    
    for parser_name in available_parsers:
        parser_results = [r for r in all_results if r['parser'] == parser_name]
        total = len(parser_results)
        found = sum(1 for r in parser_results if r['found'])
        with_price = sum(1 for r in parser_results if r['price_type'] == 'price')
        on_request = sum(1 for r in parser_results if r['price_type'] == 'on_request')
        discontinued = sum(1 for r in parser_results if r['price_type'] == 'discontinued')
        errors = sum(1 for r in parser_results if not r['success'])
        
        success_rate = (found / total * 100) if total > 0 else 0
        
        print(f"{parser_name:25}:")
        print(f"  {'':25}   Найдено: {found}/{total} ({success_rate:.1f}%)")
        print(f"  {'':25}   С ценой: {with_price}")
        print(f"  {'':25}   По запросу: {on_request}")
        print(f"  {'':25}   Снят: {discontinued}")
        print(f"  {'':25}   Ошибок: {errors}")
        print()
    
    # Статистика по запросам
    print(f"{'='*100}")
    print(f"СТАТИСТИКА ПО ЗАПРОСАМ")
    print(f"{'='*100}\n")
    
    for query, description in UNIVERSAL_TEST_QUERIES:
        query_results = [r for r in all_results if r['query'] == query]
        found_count = sum(1 for r in query_results if r['found'])
        total_parsers = len(query_results)
        
        print(f"{query:30} ({description}):")
        print(f"  {'':30}   Найдено на {found_count}/{total_parsers} парсерах")
        print()
    
    print(f"{'='*100}\n")
    print(f"Тестирование завершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

if __name__ == '__main__':
    asyncio.run(test_all_parsers_universal())
