"""Диагностический скрипт для keysight-technologies.ru"""
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
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config_loader import ConfigLoader
from logger import configure_logging
from parsers.factory import create_async_parser

async def test_debug():
    # 1. Настройка
    config_path = Path(__file__).parent.parent / 'config.yaml'
    config_loader = ConfigLoader(str(config_path))
    parser_config = config_loader.get_parser_config('keysight_technologies')
    search_config = config_loader.get_search_config()
    
    logging_config = config_loader.get_logging_config()
    logging_config['level'] = 'INFO'
    log = configure_logging(logging_config)
    
    parser = create_async_parser('keysight_technologies', parser_config, log, search_config)
    
    # 2. Тестовый запрос
    query = "Agilent E4418B" # Популярный осциллограф
    print(f"\n{'='*80}")
    print(f"🔍 Тестируем запрос: {query}")
    
    async with parser:
        # 3. Проверка URL и сырого ответа
        normalized = parser._normalize_search_query(query)
        search_url = parser.search_url_template.format(query=urllib.parse.quote(normalized))
        print(f"URL: {search_url}")
        
        response = await parser._make_request_with_retry(search_url)
        if not response:
            print("❌ Нет ответа от сервера")
            return

        print(f"Статус ответа: {response.status_code}")
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'lxml')
        
        # 4. Проверка селекторов (Ожидание vs Реальность)
        print(f"\n🕵️ Проверка селекторов:")
        
        # Текущий селектор
        current_selector = '.products-block.row > .product-layout.product-grid'
        items = soup.select(current_selector)
        print(f"  [Текущий] '{current_selector}': {len(items)} товаров")
        
        # Альтернативы
        alternatives = [
            '.product-layout',
            '.product-thumb',
            '.products-block .product-layout',
            'div[class*="product-layout"]'
        ]
        
        for alt in alternatives:
            count = len(soup.select(alt))
            print(f"  [Альтернатива] '{alt}': {count} товаров")
            
        # 5. Анализ всех найденных товаров
        product_containers = soup.select('.product-layout') or soup.select('.product-thumb')
        
        if product_containers:
            print(f"\n📦 Анализ найденных товаров ({len(product_containers)} шт.):")
            
            for idx, container in enumerate(product_containers, 1):
                print(f"\n  --- Товар #{idx} ---")
                # Название
                name_elem = container.select_one('.product-thumb__name')
                name = name_elem.get_text(strip=True) if name_elem else "Без названия"
                print(f"  Название: {name}")
                
                # Цена
                price_elem = container.select_one('.price')
                price = price_elem.get_text(strip=True) if price_elem else "Без цены"
                print(f"  Цена: {price}")
                
                if idx == 1:
                     print(f"   HTML (первые 200 символов): {str(container)[:200]}...")
                    
        else:
            print("\n❌ Товары вообще не найдены. Структура страницы:")
            body_classes = soup.body['class'] if soup.body and soup.body.has_attr('class') else "Нет классов"
            print(f"   Body classes: {body_classes}")
            # Показать основные контейнеры
            main_divs = [d.get('class') for d in soup.find_all('div', limit=10) if d.get('class')]
            print(f"   Первые 10 div классов: {main_divs}")

    # 6. Полный тест через search_product
    print(f"\n{'='*80}")
    print(f"🧪 Тест parser.search_product('{query}'):")
    
    async with parser:
        result = await parser.search_product(query)
        print(f"\nРезультат: {result}")
        if result:
            print(f"✅ Товар найден!")
            print(f"   Название: {result.get('name')}")
            print(f"   Цена: {result.get('price')}")
            print(f"   URL: {result.get('url')}")
        else:
            print(f"❌ Товар НЕ найден через search_product")

if __name__ == '__main__':
    asyncio.run(test_debug())

