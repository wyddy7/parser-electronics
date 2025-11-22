"""Тестовый скрипт для проверки обработки запросов mprofit с запятыми, пробелами и разными форматами"""
import asyncio
import sys
from pathlib import Path
import urllib.parse

# Исправляем кодировку для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Добавляем путь к src
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from config_loader import ConfigLoader
from logger import configure_logging
from parsers.factory import create_async_parser

# Тестовые запросы с разными вариантами форматирования
TEST_QUERIES = [
    # Простой запрос для проверки работоспособности
    "мультиметр",
    
    # С запятыми и описанием (как в вашем примере)
    "DT-902, индикатор порядка подключения обмоток электродвигателя и порядка чередования фаз",
    "NRP2, измеритель мощности",
    "Agilent E4418B, измеритель мощности",
    
    # С лишними пробелами
    "DT-902  ",
    "  HIOKI 3390  ",
    "Agilent   E4418B",
    
    # Без запятых (чистые артикулы)
    "DT-902",
    "NRP2",
    "Agilent E4418B",
    "HIOKI 3390",
    "АКИП-2502",
    
    # С дефисами и слэшами
    "АКИП-3404/1",
    "В7-16А",
    
    # С дополнительными словами без запятой
    "DT-902 индикатор",
    "NRP2 измеритель",
]

async def test_query(parser_instance, query: str, log) -> dict:
    """Тестирует один запрос"""
    try:
        # Показываем, что будет нормализовано
        normalized = parser_instance._normalize_search_query(query)
        encoded = urllib.parse.quote(normalized)
        search_url = parser_instance.search_url_template.format(query=encoded)
        
        print(f"\n{'─'*100}")
        print(f"Оригинальный запрос: {query}")
        print(f"После нормализации:  {normalized}")
        print(f"После URL-кодирования: {encoded}")
        print(f"URL поиска: {search_url}")
        
        # Проверяем, что возвращает сайт напрямую
        response = await parser_instance._make_request_with_retry(search_url)
        if response:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Пробуем разные селекторы
            products = soup.select('.catalog.list.search.js_wrapper_items > .list_item_wrapp.item_wrap.item')
            if not products:
                # Альтернативный селектор
                products = soup.select('.list_item_wrapp.item_wrap.item')
            if not products:
                # Еще один вариант
                products = soup.select('.catalog.list.search .list_item_wrapp')
            
            print(f"📦 Товаров найдено на странице: {len(products)}")
            
            # Если товары не найдены, показываем структуру страницы
            if not products:
                # Ищем любые элементы с классом item
                all_items = soup.select('.item')
                print(f"   Найдено элементов с классом 'item': {len(all_items)}")
                
                # Ищем контейнер результатов
                catalog = soup.select_one('.catalog.list.search')
                if catalog:
                    print(f"   Контейнер '.catalog.list.search' найден")
                    # Показываем первые 200 символов HTML
                    print(f"   HTML контейнера (первые 200 символов): {str(catalog)[:200]}...")
                else:
                    print(f"   ⚠️  Контейнер '.catalog.list.search' НЕ найден!")
                    # Показываем заголовок страницы
                    title = soup.select_one('title')
                    if title:
                        print(f"   Заголовок страницы: {title.get_text(strip=True)}")
            
            # Показываем первые 3 найденных товара (если есть)
            if products:
                print(f"Первые найденные товары:")
                for idx, product in enumerate(products[:3], 1):
                    name_elem = product.select_one('.item-title a span') or product.select_one('.item-title a')
                    if name_elem:
                        name = name_elem.get_text(strip=True)
                        print(f"  {idx}. {name[:80]}")
        
        # Выполняем поиск через парсер
        result = await parser_instance.search_product(query)
        
        # Детальная диагностика для первого товара (если есть)
        if 'products' in locals() and products and not (result and result.get('name')):
            from bs4 import BeautifulSoup
            first_product = products[0]
            name_elem = first_product.select_one('.item-title a span') or first_product.select_one('.item-title a')
            if name_elem:
                found_name = name_elem.get_text(strip=True)
                # Тестируем проверку совпадения вручную
                is_match = parser_instance._is_name_match(query, found_name)
                print(f"   🔍 Диагностика совпадения:")
                print(f"      Оригинал: '{query}'")
                print(f"      Найдено: '{found_name}'")
                print(f"      Совпадение: {is_match}")
        
        if result and result.get('name'):
            price = result.get('price', 0)
            if price > 0:
                status = f"✅ НАЙДЕН: {price:,.0f} руб."
            elif price == -2.0:
                status = "⚠️  ПО ЗАПРОСУ"
            elif price == -1.0:
                status = "❌ СНЯТ С ПРОИЗВОДСТВА"
            else:
                status = "❌ НЕ НАЙДЕН (цена = 0)"
            
            print(f"Результат парсера: {status}")
            print(f"Найденное название: {result.get('name')}")
            if result.get('url'):
                print(f"URL: {result.get('url')[:80]}...")
            
            return {
                'query': query,
                'normalized': normalized,
                'products_on_page': len(products) if 'products' in locals() else 0,
                'success': True,
                'result': result
            }
        else:
            print(f"Результат парсера: ❌ НЕ НАЙДЕН")
            if 'products' in locals() and len(products) > 0:
                print(f"⚠️  ВНИМАНИЕ: На странице найдено {len(products)} товаров, но они не прошли проверку совпадения!")
            return {
                'query': query,
                'normalized': normalized,
                'products_on_page': len(products) if 'products' in locals() else 0,
                'success': False,
                'result': None
            }
    except Exception as e:
        print(f"Результат: 🔴 ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return {
            'query': query,
            'normalized': normalized if 'normalized' in locals() else query,
            'products_on_page': 0,
            'success': False,
            'error': str(e)
        }

async def test_all_queries():
    """Тестирует все запросы"""
    
    # Загружаем конфигурацию
    config_loader = ConfigLoader('config.yaml')
    parser_config = config_loader.get_parser_config('mprofit')
    search_config = config_loader.get_search_config()
    
    # Настраиваем логирование
    logging_config = config_loader.get_logging_config()
    logging_config['level'] = 'INFO'  # Только INFO и выше
    log = configure_logging(logging_config)
    log = log.bind(component="test_mprofit_queries")
    
    print(f"\n{'='*100}")
    print(f"ТЕСТИРОВАНИЕ MPROFIT: ОБРАБОТКА ЗАПРОСОВ С ЗАПЯТЫМИ, ПРОБЕЛАМИ И РАЗНЫМИ ФОРМАТАМИ")
    print(f"{'='*100}")
    print(f"\nВсего запросов для тестирования: {len(TEST_QUERIES)}")
    print(f"{'='*100}\n")
    
    # Создаем парсер
    parser_instance = create_async_parser('mprofit', parser_config, log, search_config)
    
    results = []
    async with parser_instance:
        for idx, query in enumerate(TEST_QUERIES, 1):
            print(f"\n[{idx}/{len(TEST_QUERIES)}] Тестируем запрос...")
            result = await test_query(parser_instance, query, log)
            results.append(result)
            # Небольшая задержка между запросами
            await asyncio.sleep(0.5)
    
    # Итоговая статистика
    print(f"\n{'='*100}")
    print(f"ИТОГОВАЯ СТАТИСТИКА")
    print(f"{'='*100}\n")
    
    total = len(results)
    found = sum(1 for r in results if r.get('success') and r.get('result') and r.get('result').get('name'))
    with_price = sum(1 for r in results if r.get('success') and r.get('result') and r.get('result').get('price', 0) > 0)
    on_request = sum(1 for r in results if r.get('success') and r.get('result') and r.get('result').get('price', 0) == -2.0)
    errors = sum(1 for r in results if r.get('error'))
    products_on_pages = sum(r.get('products_on_page', 0) for r in results)
    pages_with_products = sum(1 for r in results if r.get('products_on_page', 0) > 0)
    
    print(f"Всего запросов: {total}")
    print(f"Найдено товаров парсером: {found}")
    print(f"С ценой: {with_price}")
    print(f"По запросу: {on_request}")
    print(f"Ошибок: {errors}")
    print(f"\n📦 Статистика по страницам:")
    print(f"  Всего товаров на всех страницах: {products_on_pages}")
    print(f"  Страниц с товарами: {pages_with_products}/{total}")
    if pages_with_products > 0 and found == 0:
        print(f"  ⚠️  ВНИМАНИЕ: Товары найдены на страницах, но не прошли проверку совпадения!")
    
    # Показываем примеры нормализации
    print(f"\n{'='*100}")
    print(f"ПРИМЕРЫ НОРМАЛИЗАЦИИ ЗАПРОСОВ")
    print(f"{'='*100}\n")
    
    for r in results[:10]:  # Показываем первые 10 примеров
        print(f"  '{r['query']}' → '{r['normalized']}'")
    
    print(f"\n{'='*100}\n")

if __name__ == '__main__':
    asyncio.run(test_all_queries())

