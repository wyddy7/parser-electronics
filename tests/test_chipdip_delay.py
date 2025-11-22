"""Тест для проверки парсера ChipDip с новым механизмом задержек"""
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

async def test_chipdip_backoff():
    # 1. Настройка
    config_path = Path(__file__).parent.parent / 'config.yaml'
    config_loader = ConfigLoader(str(config_path))
    parser_config = config_loader.get_parser_config('chipdip')
    search_config = config_loader.get_search_config()
    
    logging_config = config_loader.get_logging_config()
    logging_config['level'] = 'INFO'
    log = configure_logging(logging_config)
    
    parser = create_async_parser('chipdip', parser_config, log, search_config)
    
    # 2. Тестовый запрос (товар, который точно есть на ChipDip)
    query = "Fluke 87V" 
    print(f"\n{'='*80}")
    print(f"🔍 Тестируем ChipDip с запросом: {query}")
    print(f"Конфигурация:")
    print(f"  Request Delay: {parser.request_delay}s")
    print(f"  Max Concurrent: {parser.max_concurrent}")
    print(f"  Retry Backoff: {parser.retry_backoff_factor}")
    print(f"  Retry Total: {parser.retry_total}")
    print(f"{'='*80}")
    
    async with parser:
        # Access internal method to inspect response
        normalized = parser._normalize_search_query(query)
        search_url = parser.search_url_template.format(query=urllib.parse.quote(normalized))
        
        print(f"URL: {search_url}")
        response = await parser._make_request_with_retry(search_url)
        
        if response:
            print(f"Status: {response.status_code}")
            print(f"Content preview: {response.text[:500]}...")
            if "ddos-guard" in response.text.lower() or "verify" in response.text.lower():
                print("⚠️  POSSIBLE CAPTCHA/BLOCK DETECTED IN CONTENT")
        
        result = await parser.search_product(query)
        print(f"\nРезультат: {result}")
        
        if result and result.get('name'):
            print(f"✅ УСПЕХ! Товар найден.")
            print(f"   Название: {result.get('name')}")
            print(f"   Цена: {result.get('price')}")
        else:
            print(f"❌ Товар НЕ найден или произошла ошибка (проверьте логи на 429).")

if __name__ == '__main__':
    asyncio.run(test_chipdip_backoff())

