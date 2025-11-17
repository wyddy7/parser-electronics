"""Главный CLI модуль для запуска парсера"""
import click
import sys
from pathlib import Path
from typing import Optional
from tqdm import tqdm

from config_loader import ConfigLoader
from logger import configure_logging, get_logger
from excel.reader import ExcelReader
from excel.writer import ExcelWriter
from parsers.factory import create_parser


@click.command()
@click.option(
    '--config',
    type=click.Path(exists=True),
    default='config.yaml',
    help='Путь к YAML файлу конфигурации'
)
@click.option(
    '--limit',
    type=int,
    default=None,
    help='Ограничить количество обрабатываемых товаров (для тестирования)'
)
@click.option(
    '--output',
    type=str,
    default=None,
    help='Имя выходного файла (без пути, только имя)'
)
@click.option(
    '--parser',
    type=str,
    default=None,
    help='Имя парсера для использования (если не указано - используется первый enabled)'
)
def main(config: str, limit: Optional[int], output: Optional[str], parser: Optional[str]):
    """
    Price Parser - парсер цен с различных сайтов
    
    Читает товары из Excel файла, ищет цены на выбранном сайте,
    сохраняет результаты в новый Excel файл.
    """
    try:
        # Загружаем конфигурацию
        click.echo("Загрузка конфигурации...")
        config_loader = ConfigLoader(config)
        
        # Настраиваем логирование
        logging_config = config_loader.get_logging_config()
        log = configure_logging(logging_config)
        log = log.bind(component="main")
        
        log.info("parser_started", config_file=config, limit=limit)
        click.echo(f"OK Конфигурация загружена: {config}")
        
        # Читаем входной Excel файл
        excel_config = config_loader.get_excel_config()
        input_file = excel_config['input_file']
        name_column = excel_config['name_column']
        
        if not Path(input_file).exists():
            click.echo(f"ERROR Входной файл не найден: {input_file}", err=True)
            log.error("input_file_not_found", file=input_file)
            sys.exit(1)
        
        click.echo(f"Чтение входного файла: {input_file}")
        reader = ExcelReader(input_file, name_column)
        df = reader.read_products()
        
        # Применяем лимит если указан
        if limit:
            df = reader.get_sample(df, limit)
            click.echo(f"ТЕСТ Режим тестирования: обработка {limit} товаров")
        
        total_products = len(df)
        click.echo(f"OK Загружено товаров: {total_products}")
        log.info("products_loaded", count=total_products, limit=limit)
        
        # Выбор парсера
        if parser:
            parser_name = parser
            # Проверяем, что парсер существует в конфиге
            try:
                parser_config = config_loader.get_parser_config(parser_name)
            except ValueError:
                enabled_parsers = config_loader.get_enabled_parsers()
                click.echo(f"ERROR Парсер '{parser_name}' не найден в конфигурации", err=True)
                if enabled_parsers:
                    click.echo(f"      Доступные парсеры: {', '.join(enabled_parsers)}", err=True)
                sys.exit(1)
            
            # Проверяем, что парсер включен
            if not parser_config.get('enabled', True):
                enabled_parsers = config_loader.get_enabled_parsers()
                click.echo(f"ERROR Парсер '{parser_name}' отключен в конфигурации (enabled: false)", err=True)
                if enabled_parsers:
                    click.echo(f"      Доступные парсеры: {', '.join(enabled_parsers)}", err=True)
                sys.exit(1)
        else:
            # Берем первый enabled парсер
            enabled_parsers = config_loader.get_enabled_parsers()
            if not enabled_parsers:
                click.echo("ERROR Нет включенных парсеров в конфигурации", err=True)
                sys.exit(1)
            parser_name = enabled_parsers[0]
            if len(enabled_parsers) > 1:
                click.echo(f"WARNING Используется первый парсер: {parser_name}")
                click.echo(f"      Доступные: {', '.join(enabled_parsers)}")
            # Получаем конфигурацию парсера
            parser_config = config_loader.get_parser_config(parser_name)
        
        # Получаем конфигурацию поиска
        search_config = config_loader.get_search_config()
        
        click.echo(f"\nИспользуется парсер: {parser_name}")
        
        # Пытаемся создать парсер
        try:
            parser_instance = create_parser(parser_name, parser_config, log, search_config)
        except ValueError as e:
            click.echo(f"ERROR Не удалось создать парсер '{parser_name}': {e}", err=True)
            click.echo(f"      Убедитесь, что файл src/parsers/{parser_name}_parser.py существует", err=True)
            log.error("parser_creation_failed", parser_name=parser_name, error=str(e))
            sys.exit(1)
        
        click.echo("\nНачинаем парсинг цен...")
        results = {}
        
        # Обрабатываем каждый товар с прогресс-баром
        with parser_instance:
            for idx, row in tqdm(df.iterrows(), total=total_products, desc="Парсинг товаров"):
                product_name = row.get('product_name', '')
                
                if not product_name or product_name == 'nan':
                    log.debug("skipping_empty_product", index=idx)
                    results[product_name] = None
                    continue
                
                try:
                    # Ищем товар на сайте
                    product_log = log.bind(product=product_name, index=idx)
                    product_log.debug("processing_product")
                    
                    result = parser_instance.search_product(product_name)
                    results[product_name] = result
                    
                    if result:
                        product_log.info("product_found", 
                                       price=result.get('price'),
                                       found_name=result.get('name'))
                    else:
                        product_log.warning("product_not_found")
                
                except Exception as e:
                    log.error("processing_error",
                            product=product_name,
                            error=str(e),
                            error_type=type(e).__name__)
                    results[product_name] = None
        
        click.echo("\nOK Парсинг завершен!")
        
        # Создаем сводку
        # Найдено = цена > 0, по запросу = цена == -2, снято = цена == -1, не найдено = цена == 0 или None
        found_count = sum(1 for v in results.values() 
                         if v is not None and v.get('price', 0) > 0)
        on_request_count = sum(1 for v in results.values() 
                              if v is not None and v.get('price', 0) == -2)
        discontinued_count = sum(1 for v in results.values() 
                                 if v is not None and v.get('price', 0) == -1)
        not_found_count = sum(1 for v in results.values() 
                              if v is None or v.get('price', 0) == 0)
        
        click.echo(f"\nСтатистика:")
        click.echo(f"   Всего товаров: {total_products}")
        click.echo(f"   Найдено цен: {found_count}")
        click.echo(f"   Цена по запросу: {on_request_count}")
        click.echo(f"   Снято с производства: {discontinued_count}")
        click.echo(f"   Не найдено: {not_found_count}")
        
        # Записываем результаты в Excel
        click.echo("\nСохранение результатов...")
        output_dir = excel_config.get('output_dir', 'output')
        writer = ExcelWriter(output_dir)
        
        output_path = writer.write_results(df, results, output, parser_name=parser_name)
        
        click.echo(f"OK Результаты сохранены: {output_path}")
        log.info("parser_completed",
                total=total_products,
                found=found_count,
                on_request=on_request_count,
                discontinued=discontinued_count,
                not_found=not_found_count,
                output_file=output_path)
        
        click.echo("\nГотово!")
        
    except FileNotFoundError as e:
        click.echo(f"ERROR Файл не найден: {e}", err=True)
        sys.exit(1)
        
    except ValueError as e:
        click.echo(f"ERROR Ошибка конфигурации: {e}", err=True)
        sys.exit(1)
        
    except KeyboardInterrupt:
        click.echo("\n\nПрервано пользователем")
        log.warning("interrupted_by_user")
        sys.exit(130)
        
    except Exception as e:
        click.echo(f"\nERROR Неожиданная ошибка: {e}", err=True)
        if 'log' in locals():
            log.error("unexpected_error",
                     error=str(e),
                     error_type=type(e).__name__)
        sys.exit(1)


if __name__ == '__main__':
    main()

