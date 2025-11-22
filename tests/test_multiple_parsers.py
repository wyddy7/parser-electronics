"""Тестовый скрипт для проверки работоспособности нескольких парсеров на осциллографах и вольтметрах"""
import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any

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

# Список парсеров для тестирования
PARSERS_TO_TEST = [
    'electronpribor',
    'prist',
    'chipdip',
    'keysight_technologies',
    'mprofit',
    'pribor_x',
    'zenit_electro',
    'flukeshop',
]

# Тестовые товары (осциллографы и вольтметры)
TEST_PRODUCTS = [
    "Осциллограф",
    "Вольтметр",
    "С1-64 Осциллограф",
    "В7-16А",
    "Fluke 87V",
    "Keysight DSOX1204A",
]

async def test_parser(parser_name: str, product_name: str, config_loader: ConfigLoader, log) -> Dict[str, Any]:
    """Тестирует один парсер на одном товаре"""
    try:
        parser_config = config_loader.get_parser_config(parser_name)
        search_config = config_loader.get_search_config()
        
        parser_instance = create_async_parser(parser_name, parser_config, log, search_config)
        
        async with parser_instance:
            result = await parser_instance.search_product(product_name)
            
            return {
                'parser': parser_name,
                'product': product_name,
                'success': True,
                'result': result,
                'error': None
            }
    except Exception as e:
        return {
            'parser': parser_name,
            'product': product_name,
            'success': False,
            'result': None,
            'error': str(e)
        }

async def test_all_parsers():
    """Тестирует все парсеры на всех товарах"""
    
    # Загружаем конфигурацию (из корня проекта)
    config_path = Path(__file__).parent.parent / 'config.yaml'
    config_loader = ConfigLoader(str(config_path))
    search_config = config_loader.get_search_config()
    
    # Настраиваем логирование (уменьшаем уровень для читаемости)
    logging_config = config_loader.get_logging_config()
    logging_config['level'] = 'INFO'  # Только INFO и выше
    log = configure_logging(logging_config)
    log = log.bind(component="test_multiple")
    
    print(f"\n{'='*100}")
    print(f"ТЕСТИРОВАНИЕ ПАРСЕРОВ НА ОСЦИЛЛОГРАФАХ И ВОЛЬТМЕТРАХ")
    print(f"{'='*100}")
    print(f"\nПарсеры для тестирования: {', '.join(PARSERS_TO_TEST)}")
    print(f"Тестовые товары: {', '.join(TEST_PRODUCTS)}")
    print(f"\n{'='*100}\n")
    
    # Проверяем доступность парсеров
    available_parsers = []
    for parser_name in PARSERS_TO_TEST:
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
    
    print(f"\nДоступные парсеры: {', '.join(available_parsers)}\n")
    print(f"{'='*100}\n")
    
    # Тестируем каждый парсер на каждом товаре
    results = []
    for product in TEST_PRODUCTS:
        print(f"\n{'─'*100}")
        print(f"ТОВАР: {product}")
        print(f"{'─'*100}\n")
        
        # Запускаем тесты параллельно для всех парсеров
        tasks = [
            test_parser(parser_name, product, config_loader, log)
            for parser_name in available_parsers
        ]
        
        product_results = await asyncio.gather(*tasks)
        results.extend(product_results)
        
        # Выводим результаты для этого товара
        for result in product_results:
            parser_name = result['parser']
            if result['success']:
                res = result['result']
                if res and res.get('name'):
                    price = res.get('price', 0)
                    if price > 0:
                        status = f"✅ НАЙДЕН: {price:,.0f} руб."
                    elif price == -2.0:
                        status = "⚠️  ПО ЗАПРОСУ"
                    elif price == -1.0:
                        status = "❌ СНЯТ С ПРОИЗВОДСТВА"
                    else:
                        status = "❌ НЕ НАЙДЕН (цена = 0)"
                    
                    print(f"  {parser_name:25} → {status}")
                    if res.get('url'):
                        print(f"    {'':25}   URL: {res['url'][:70]}...")
                else:
                    print(f"  {parser_name:25} → ❌ НЕ НАЙДЕН (result = None)")
            else:
                print(f"  {parser_name:25} → 🔴 ОШИБКА: {result['error']}")
    
    # Итоговая статистика
    print(f"\n{'='*100}")
    print(f"ИТОГОВАЯ СТАТИСТИКА")
    print(f"{'='*100}\n")
    
    for parser_name in available_parsers:
        parser_results = [r for r in results if r['parser'] == parser_name]
        total = len(parser_results)
        found = sum(1 for r in parser_results if r['success'] and r['result'] and r['result'].get('name'))
        with_price = sum(1 for r in parser_results if r['success'] and r['result'] and r['result'].get('price', 0) > 0)
        on_request = sum(1 for r in parser_results if r['success'] and r['result'] and r['result'].get('price', 0) == -2.0)
        errors = sum(1 for r in parser_results if not r['success'])
        
        print(f"{parser_name:25}: найдено={found}/{total}, с ценой={with_price}, по запросу={on_request}, ошибок={errors}")
    
    print(f"\n{'='*100}\n")

if __name__ == '__main__':
    asyncio.run(test_all_parsers())

