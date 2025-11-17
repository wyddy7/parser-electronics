"""Тестовый скрипт для проверки поиска АКИП-3404"""
import asyncio
import sys
from pathlib import Path

# Исправляем кодировку для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Добавляем путь к src
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from config_loader import ConfigLoader
from logger import configure_logging, get_logger
from parsers.factory import create_async_parser

async def test_search():
    """Тестирует поиск конкретного товара"""
    
    # Загружаем конфигурацию
    config_loader = ConfigLoader('config.yaml')
    parser_config = config_loader.get_parser_config('electronpribor')
    search_config = config_loader.get_search_config()
    
    # Настраиваем логирование
    logging_config = config_loader.get_logging_config()
    log = configure_logging(logging_config)
    log = log.bind(component="test")
    
    # Создаем парсер
    parser_instance = create_async_parser('electronpribor', parser_config, log, search_config)
    
    # Тестовый товар - проверяем проблемный случай с АКИП 9806/3 (пробел между АКИП и 9806/3)
    test_product = "АКИП 9806/3 Антенна биконическая"
    
    print(f"\n{'='*80}")
    print(f"Тестируем поиск товара:")
    print(f"{test_product}")
    print('='*80)
    
    try:
        async with parser_instance:
            result = await parser_instance.search_product(test_product)
            
            print(f"\nРезультат поиска:")
            print(f"{'='*80}")
            if result:
                print(f"[OK] ТОВАР НАЙДЕН!")
                print(f"  Название: {result.get('name')}")
                print(f"  Цена: {result.get('price')}")
                print(f"  URL: {result.get('url')}")
                
                # Проверяем цену
                price = result.get('price')
                if price == -1.0:
                    print(f"  Статус: Снят с производства")
                elif price == -2.0:
                    print(f"  Статус: Цена по запросу")
                elif price == 0.0:
                    print(f"  Статус: Не найден (цена = 0)")
                elif price and price > 0:
                    print(f"  Статус: В наличии, цена: {price} руб.")
            else:
                print(f"[FAIL] ТОВАР НЕ НАЙДЕН")
                print(f"  result = None")
    except Exception as e:
        print(f"\n[ERROR] ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n{'='*80}")

if __name__ == '__main__':
    asyncio.run(test_search())

