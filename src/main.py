"""Главный CLI модуль для запуска парсера"""
import click
import sys
import asyncio
from pathlib import Path
from typing import Optional
from tqdm import tqdm

from config_loader import ConfigLoader
from logger import configure_logging, get_logger
from excel.reader import ExcelReader
from excel.writer import ExcelWriter
from parsers.factory import create_parser, create_async_parser


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
    help='Имя парсера для использования (если не указано - используется первый enabled). Устаревший параметр, используйте --parsers'
)
@click.option(
    '--parsers',
    type=str,
    default=None,
    help='Список парсеров через запятую для параллельной обработки (например: electronpribor,prist)'
)
def main(config: str, limit: Optional[int], output: Optional[str], parser: Optional[str], parsers: Optional[str]):
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
        
        # Получаем конфигурацию поиска
        search_config = config_loader.get_search_config()
        
        # Определяем режим работы: параллельный или одиночный
        use_parallel = parsers is not None
        
        if use_parallel:
            # ПАРАЛЛЕЛЬНЫЙ РЕЖИМ: несколько парсеров
            parser_names = [p.strip() for p in parsers.split(',')]
            parser_names = [p for p in parser_names if p]  # Убираем пустые
            
            if len(parser_names) == 0:
                click.echo("ERROR Список парсеров пуст. Укажите парсеры через запятую: --parsers electronpribor,prist", err=True)
                sys.exit(1)
            
            if len(parser_names) == 1:
                click.echo("WARNING Указан только один парсер. Используйте --parser для одиночного режима", err=True)
            
            # Валидация всех парсеров
            parser_instances = []
            for parser_name in parser_names:
                try:
                    parser_config = config_loader.get_parser_config(parser_name)
                except ValueError:
                    enabled_parsers = config_loader.get_enabled_parsers()
                    click.echo(f"ERROR Парсер '{parser_name}' не найден в конфигурации", err=True)
                    if enabled_parsers:
                        click.echo(f"      Доступные парсеры: {', '.join(enabled_parsers)}", err=True)
                    sys.exit(1)
                
                if not parser_config.get('enabled', True):
                    click.echo(f"ERROR Парсер '{parser_name}' отключен в конфигурации (enabled: false)", err=True)
                    sys.exit(1)
                
                async_config = parser_config.get('async', {})
                if not async_config.get('enabled', False):
                    click.echo(f"ERROR Парсер '{parser_name}' должен быть async для параллельного режима", err=True)
                    click.echo(f"      Установите parser.{parser_name}.async.enabled: true в config.yaml", err=True)
                    sys.exit(1)
                
                try:
                    parser_instance = create_async_parser(parser_name, parser_config, log, search_config)
                    parser_instances.append((parser_name, parser_instance))
                except ValueError as e:
                    click.echo(f"ERROR Не удалось создать парсер '{parser_name}': {e}", err=True)
                    log.error("parser_creation_failed", parser_name=parser_name, error=str(e))
                    sys.exit(1)
            
            click.echo(f"\n[ПАРАЛЛЕЛЬНЫЙ РЕЖИМ] Используется {len(parser_names)} парсеров: {', '.join(parser_names)}")
            for parser_name, (_, _) in zip(parser_names, parser_instances):
                async_config = config_loader.get_parser_config(parser_name).get('async', {})
                max_concurrent = async_config.get('max_concurrent', 50)
                click.echo(f"   {parser_name}: до {max_concurrent} одновременных запросов")
            
            click.echo("\nНачинаем параллельный парсинг цен...")
            
            # Получаем параметры батчинга (берем минимальные для безопасности)
            all_async_configs = [config_loader.get_parser_config(p).get('async', {}) for p in parser_names]
            batch_size = min(cfg.get('batch_size', 30) for cfg in all_async_configs)
            checkpoint_interval = min(cfg.get('checkpoint_interval', 50) for cfg in all_async_configs)
            batch_delay = max(cfg.get('batch_delay', 4) for cfg in all_async_configs)  # Максимальная пауза
            
            # Подготавливаем writer для финального сохранения
            output_dir = excel_config.get('output_dir', 'output')
            writer = ExcelWriter(output_dir)
            
            # Создаем отдельный writer для checkpoint'ов в output/temp
            temp_dir = Path(output_dir) / 'temp'
            temp_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_writer = ExcelWriter(str(temp_dir))
            
            results = asyncio.run(_process_products_parallel_async(
                parser_instances, df, total_products, log,
                excel_config, writer, checkpoint_writer, output, parser_names,
                batch_size, checkpoint_interval, batch_delay
            ))
            
            click.echo("\nOK Параллельный парсинг завершен!")
            
            # Создаем сводку для параллельного режима
            click.echo(f"\nСтатистика по парсерам:")
            for parser_name in parser_names:
                found_count = sum(1 for v in results.values() 
                                 if v and parser_name in v and v[parser_name] is not None 
                                 and v[parser_name].get('price', 0) > 0)
                on_request_count = sum(1 for v in results.values() 
                                      if v and parser_name in v and v[parser_name] is not None 
                                      and v[parser_name].get('price', 0) == -2)
                not_found_count = sum(1 for v in results.values() 
                                     if not v or parser_name not in v or v[parser_name] is None 
                                     or v[parser_name].get('price', 0) == 0)
                click.echo(f"   {parser_name}: найдено={found_count}, по запросу={on_request_count}, не найдено={not_found_count}")
            
            # Записываем результаты в Excel
            click.echo("\nСохранение результатов...")
            output_path = writer.write_results_parallel(df, results, output, parser_names=parser_names)
            
            click.echo(f"OK Результаты сохранены: {output_path}")
            log.info("parallel_parser_completed",
                    total=total_products,
                    parsers=parser_names,
                    output_file=output_path)
        
        else:
            # ОДИНОЧНЫЙ РЕЖИМ: один парсер (старая логика)
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
            
            # Проверяем, нужно ли использовать async версию
            async_config = parser_config.get('async', {})
            use_async = async_config.get('enabled', False)
            
            click.echo(f"\nИспользуется парсер: {parser_name}")
            if use_async:
                max_concurrent = async_config.get('max_concurrent', 50)
                click.echo(f"[ASYNC] Асинхронный режим: до {max_concurrent} одновременных запросов")
            else:
                click.echo("[SYNC] Синхронный режим")
            
            # Пытаемся создать парсер
            try:
                if use_async:
                    parser_instance = create_async_parser(parser_name, parser_config, log, search_config)
                else:
                    parser_instance = create_parser(parser_name, parser_config, log, search_config)
            except ValueError as e:
                click.echo(f"ERROR Не удалось создать парсер '{parser_name}': {e}", err=True)
                if use_async:
                    click.echo(f"      Убедитесь, что файл src/parsers/{parser_name}_async_parser.py существует", err=True)
                else:
                    click.echo(f"      Убедитесь, что файл src/parsers/{parser_name}_parser.py существует", err=True)
                log.error("parser_creation_failed", parser_name=parser_name, error=str(e))
                sys.exit(1)
            
            click.echo("\nНачинаем парсинг цен...")
            
            # Обрабатываем товары (async или sync)
            if use_async:
                # Получаем параметры батчинга из конфига
                batch_size = async_config.get('batch_size', 30)
                checkpoint_interval = async_config.get('checkpoint_interval', 50)
                batch_delay = async_config.get('batch_delay', 4)
                
                # Подготавливаем writer для финального сохранения
                output_dir = excel_config.get('output_dir', 'output')
                writer = ExcelWriter(output_dir)
                
                # Создаем отдельный writer для checkpoint'ов в output/temp
                temp_dir = Path(output_dir) / 'temp'
                temp_dir.mkdir(parents=True, exist_ok=True)
                checkpoint_writer = ExcelWriter(str(temp_dir))
                
                results = asyncio.run(_process_products_async(
                    parser_instance, df, total_products, log,
                    excel_config, writer, checkpoint_writer, output, parser_name,
                    batch_size, checkpoint_interval, batch_delay
                ))
            else:
                results = _process_products_sync(parser_instance, df, total_products, log)
            
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
        # Обработка KeyboardInterrupt уже происходит в _process_products_async
        # Здесь просто завершаем
        click.echo("\n\nЗавершение работы...")
        if 'log' in locals():
            log.warning("interrupted_by_user")
        sys.exit(130)
        
    except Exception as e:
        click.echo(f"\nERROR Неожиданная ошибка: {e}", err=True)
        if 'log' in locals():
            log.error("unexpected_error",
                     error=str(e),
                     error_type=type(e).__name__)
        sys.exit(1)


def _process_products_sync(parser_instance, df, total_products, log):
    """Синхронная обработка товаров"""
    results = {}
    
    with parser_instance:
        for idx, row in tqdm(
            df.iterrows(), 
            total=total_products, 
            desc="Парсинг товаров",
            file=sys.stdout,
            dynamic_ncols=True,
            mininterval=0.5,
            maxinterval=1.0,
            smoothing=0.3,
            leave=True
        ):
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
    
    return results


async def _process_products_async(
    parser_instance, df, total_products, log,
    excel_config, writer, checkpoint_writer, output, parser_name,
    batch_size, checkpoint_interval, batch_delay
):
    """Асинхронная обработка товаров с батчингом и промежуточным сохранением"""
    from datetime import datetime
    from pathlib import Path
    
    results = {}
    # temp находится внутри output директории
    output_dir = excel_config.get('output_dir', 'output')
    temp_dir = Path(output_dir) / 'temp'
    
    async def process_single_product(idx, row):
        """Обработка одного товара"""
        product_name = row.get('product_name', '')
        
        if not product_name or product_name == 'nan':
            log.debug("skipping_empty_product", index=idx)
            return product_name, None
        
        try:
            # Ищем товар на сайте
            product_log = log.bind(product=product_name, index=idx)
            product_log.debug("processing_product")
            
            result = await parser_instance.search_product(product_name)
            
            if result:
                product_log.info("product_found", 
                               price=result.get('price'),
                               found_name=result.get('name'))
            else:
                product_log.warning("product_not_found")
            
            return product_name, result
        
        except Exception as e:
            log.error("processing_error",
                    product=product_name,
                    error=str(e),
                    error_type=type(e).__name__)
            return product_name, None
    
    def cleanup_old_checkpoints(keep_last=1):
        """Удаляет старые checkpoint файлы из temp, оставляя только последние N"""
        try:
            if not temp_dir.exists():
                return
                
            checkpoint_files_list = sorted(
                temp_dir.glob(f"checkpoint_{parser_name}_*.xlsx"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            
            # Удаляем все кроме последних N
            deleted_count = 0
            for old_file in checkpoint_files_list[keep_last:]:
                try:
                    old_file.unlink()
                    deleted_count += 1
                    log.debug("old_checkpoint_deleted", file=str(old_file))
                except Exception as e:
                    log.warning("checkpoint_delete_failed", file=str(old_file), error=str(e))
            
            if deleted_count > 0:
                log.debug("old_checkpoints_cleaned", deleted_count=deleted_count)
        except Exception as e:
            log.warning("checkpoint_cleanup_failed", error=str(e))
    
    def delete_all_checkpoints():
        """Удаляет все checkpoint файлы из temp после успешного завершения"""
        try:
            if not temp_dir.exists():
                return
                
            checkpoint_files_list = list(temp_dir.glob(f"checkpoint_{parser_name}_*.xlsx"))
            
            deleted_count = 0
            for checkpoint_file in checkpoint_files_list:
                try:
                    checkpoint_file.unlink()
                    deleted_count += 1
                except Exception as e:
                    log.warning("checkpoint_delete_failed", file=str(checkpoint_file), error=str(e))
            
            if deleted_count > 0:
                log.info("checkpoints_cleaned", deleted_count=deleted_count)
                click.echo(f"\n[ОЧИСТКА] Удалено {deleted_count} checkpoint файлов из temp")
        except Exception as e:
            log.warning("checkpoint_cleanup_failed", error=str(e))
    
    def save_checkpoint(current_results, completed_count):
        """Сохраняет промежуточные результаты в temp"""
        try:
            checkpoint_filename = f"checkpoint_{parser_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            checkpoint_path = checkpoint_writer.write_results(df, current_results, checkpoint_filename, parser_name=parser_name)
            
            # Удаляем старые checkpoint'ы, оставляя только последний
            cleanup_old_checkpoints(keep_last=1)
            
            log.info("checkpoint_saved", 
                    completed=completed_count, 
                    total=total_products,
                    file=checkpoint_filename)
            click.echo(f"\n[CHECKPOINT] Сохранено {completed_count}/{total_products} товаров в temp: {checkpoint_filename}")
            return checkpoint_path
        except Exception as e:
            log.error("checkpoint_failed", error=str(e), error_type=type(e).__name__)
            return None
    
    # Обрабатываем по батчам
    async with parser_instance:
        all_rows = list(df.iterrows())
        completed = 0
        last_checkpoint = 0
        
        with tqdm(
            total=total_products, 
            desc="Парсинг товаров",
            file=sys.stdout,
            dynamic_ncols=True,
            mininterval=0.5,
            maxinterval=1.0,
            smoothing=0.3,
            leave=True
        ) as pbar:
            try:
                # Разбиваем на батчи
                for batch_start in range(0, len(all_rows), batch_size):
                    batch = all_rows[batch_start:batch_start + batch_size]
                    batch_num = (batch_start // batch_size) + 1
                    total_batches = (len(all_rows) + batch_size - 1) // batch_size
                    
                    log.debug("batch_started",
                             batch_num=batch_num,
                             total_batches=total_batches,
                             batch_size=len(batch))
                    
                    # Создаем задачи для текущего батча
                    tasks = [
                        process_single_product(idx, row)
                        for idx, row in batch
                    ]
                    
                    # Обрабатываем батч
                    for coro in asyncio.as_completed(tasks):
                        product_name, result = await coro
                        results[product_name] = result
                        completed += 1
                        pbar.update(1)
                        
                        # Сохраняем checkpoint каждые N товаров
                        if completed - last_checkpoint >= checkpoint_interval:
                            save_checkpoint(results.copy(), completed)
                            last_checkpoint = completed
                    
                    # Пауза между батчами (чтобы не перегружать сервер)
                    if batch_start + batch_size < len(all_rows):
                        log.debug("batch_completed",
                                 batch_num=batch_num,
                                 completed=completed,
                                 total=total_products)
                        await asyncio.sleep(batch_delay)
                
                # Финальное сохранение checkpoint
                if completed > last_checkpoint:
                    save_checkpoint(results, completed)
                
                # Удаляем все checkpoint'ы после успешного завершения
                delete_all_checkpoints()
                    
            except KeyboardInterrupt:
                click.echo("\n\n[ПРЕРВАНО] Сохранение промежуточных результатов...")
                if completed > 0:
                    final_checkpoint = save_checkpoint(results, completed)
                    click.echo(f"[СОХРАНЕНО] Обработано {completed}/{total_products} товаров")
                    if final_checkpoint:
                        click.echo(f"[ФАЙЛ] {final_checkpoint}")
                    click.echo("[ВНИМАНИЕ] Checkpoint файлы НЕ удалены (парсинг прерван)")
                log.warning("interrupted_by_user", completed=completed, total=total_products)
                raise
    
    return results


async def _process_products_parallel_async(
    parser_instances: list,
    df, total_products, log,
    excel_config, writer, checkpoint_writer, output, parser_names,
    batch_size, checkpoint_interval, batch_delay
):
    """
    Обрабатывает товары параллельно через несколько парсеров.
    
    Args:
        parser_instances: Список кортежей (parser_name, parser_instance)
        df: DataFrame с товарами
        total_products: Общее количество товаров
        log: Logger
        excel_config: Конфигурация Excel
        writer: ExcelWriter для финального сохранения
        checkpoint_writer: ExcelWriter для checkpoint'ов
        output: Имя выходного файла
        parser_names: Список имен парсеров
        batch_size: Размер батча
        checkpoint_interval: Интервал сохранения checkpoint
        batch_delay: Задержка между батчами
        
    Returns:
        Dict[product_name, Dict[parser_name, result]]
        Например: {
            "АКИП-3409": {
                "electronpribor": {"price": 1000, "name": "...", "url": "..."},
                "prist": {"price": 1200, "name": "...", "url": "..."}
            }
        }
    """
    from datetime import datetime
    from pathlib import Path
    from contextlib import AsyncExitStack
    from typing import List, Tuple, Dict, Optional, Any
    
    results = {}  # product_name -> {parser_name -> result}
    output_dir = excel_config.get('output_dir', 'output')
    temp_dir = Path(output_dir) / 'temp'
    
    async def process_single_product_parallel(idx, row, active_parsers: List[Tuple[str, Any]]):
        """Обрабатывает один товар через все парсеры параллельно"""
        product_name = row.get('product_name', '')
        
        if not product_name or product_name == 'nan':
            log.debug("skipping_empty_product", index=idx)
            return product_name, {}
        
        try:
            # Создаем задачи для всех парсеров
            tasks = {}
            for parser_name, parser_instance in active_parsers:
                product_log = log.bind(product=product_name, parser=parser_name, index=idx)
                product_log.debug("processing_product_parallel")
                tasks[parser_name] = parser_instance.search_product(product_name)
            
            # Запускаем все парсеры параллельно
            parser_results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            
            # Формируем результат
            product_results = {}
            for (parser_name, _), result in zip(active_parsers, parser_results):
                if isinstance(result, Exception):
                    log.error("parser_error",
                             product=product_name,
                             parser=parser_name,
                             error=str(result),
                             error_type=type(result).__name__)
                    product_results[parser_name] = None
                else:
                    product_results[parser_name] = result
                    if result:
                        log.debug("product_found_parallel",
                                 product=product_name,
                                 parser=parser_name,
                                 price=result.get('price'))
                    else:
                        log.debug("product_not_found_parallel",
                                 product=product_name,
                                 parser=parser_name)
            
            return product_name, product_results
        
        except Exception as e:
            log.error("processing_error_parallel",
                     product=product_name,
                     error=str(e),
                     error_type=type(e).__name__)
            return product_name, {}
    
    def cleanup_old_checkpoints(keep_last=1):
        """Удаляет старые checkpoint файлы из temp, оставляя только последние N"""
        try:
            if not temp_dir.exists():
                return
                
            # Ищем checkpoint файлы для параллельного режима
            checkpoint_files_list = sorted(
                temp_dir.glob(f"checkpoint_parallel_*.xlsx"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            
            # Удаляем все кроме последних N
            deleted_count = 0
            for old_file in checkpoint_files_list[keep_last:]:
                try:
                    old_file.unlink()
                    deleted_count += 1
                    log.debug("old_checkpoint_deleted", file=str(old_file))
                except Exception as e:
                    log.warning("checkpoint_delete_failed", file=str(old_file), error=str(e))
            
            if deleted_count > 0:
                log.debug("old_checkpoints_cleaned", deleted_count=deleted_count)
        except Exception as e:
            log.warning("checkpoint_cleanup_failed", error=str(e))
    
    def delete_all_checkpoints():
        """Удаляет все checkpoint файлы из temp после успешного завершения"""
        try:
            if not temp_dir.exists():
                return
                
            checkpoint_files_list = list(temp_dir.glob(f"checkpoint_parallel_*.xlsx"))
            
            deleted_count = 0
            for checkpoint_file in checkpoint_files_list:
                try:
                    checkpoint_file.unlink()
                    deleted_count += 1
                except Exception as e:
                    log.warning("checkpoint_delete_failed", file=str(checkpoint_file), error=str(e))
            
            if deleted_count > 0:
                log.info("checkpoints_cleaned", deleted_count=deleted_count)
                click.echo(f"\n[ОЧИСТКА] Удалено {deleted_count} checkpoint файлов из temp")
        except Exception as e:
            log.warning("checkpoint_cleanup_failed", error=str(e))
    
    def save_checkpoint(current_results, completed_count):
        """Сохраняет промежуточные результаты в temp"""
        try:
            checkpoint_filename = f"checkpoint_parallel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            checkpoint_path = checkpoint_writer.write_results_parallel(
                df, current_results, checkpoint_filename, parser_names=parser_names
            )
            
            # Удаляем старые checkpoint'ы, оставляя только последний
            cleanup_old_checkpoints(keep_last=1)
            
            log.info("checkpoint_saved", 
                    completed=completed_count, 
                    total=total_products,
                    file=checkpoint_filename)
            click.echo(f"\n[CHECKPOINT] Сохранено {completed_count}/{total_products} товаров в temp: {checkpoint_filename}")
            return checkpoint_path
        except Exception as e:
            log.error("checkpoint_failed", error=str(e), error_type=type(e).__name__)
            return None
    
    # Управляем контекстами всех парсеров через AsyncExitStack
    async with AsyncExitStack() as stack:
        # Входим в контексты всех парсеров
        active_parsers = []
        for parser_name, parser_instance in parser_instances:
            parser = await stack.enter_async_context(parser_instance)
            active_parsers.append((parser_name, parser))
        
        log.info("parallel_parsing_started",
                parsers=parser_names,
                total_products=total_products,
                batch_size=batch_size)
        
        all_rows = list(df.iterrows())
        completed = 0
        last_checkpoint = 0
        
        with tqdm(
            total=total_products, 
            desc="Параллельный парсинг",
            file=sys.stdout,
            dynamic_ncols=True,
            mininterval=0.5,
            maxinterval=1.0,
            smoothing=0.3,
            leave=True
        ) as pbar:
            try:
                # Разбиваем на батчи
                for batch_start in range(0, len(all_rows), batch_size):
                    batch = all_rows[batch_start:batch_start + batch_size]
                    batch_num = (batch_start // batch_size) + 1
                    total_batches = (len(all_rows) + batch_size - 1) // batch_size
                    
                    log.debug("batch_started_parallel",
                             batch_num=batch_num,
                             total_batches=total_batches,
                             batch_size=len(batch),
                             parsers=parser_names)
                    
                    # Создаем задачи для текущего батча
                    tasks = [
                        process_single_product_parallel(idx, row, active_parsers)
                        for idx, row in batch
                    ]
                    
                    # Обрабатываем батч
                    for coro in asyncio.as_completed(tasks):
                        product_name, product_results = await coro
                        results[product_name] = product_results
                        completed += 1
                        pbar.update(1)
                        
                        # Сохраняем checkpoint каждые N товаров
                        if completed - last_checkpoint >= checkpoint_interval:
                            save_checkpoint(results.copy(), completed)
                            last_checkpoint = completed
                    
                    # Пауза между батчами
                    if batch_start + batch_size < len(all_rows):
                        log.debug("batch_completed_parallel",
                                 batch_num=batch_num,
                                 completed=completed,
                                 total=total_products)
                        await asyncio.sleep(batch_delay)
                
                # Финальное сохранение checkpoint
                if completed > last_checkpoint:
                    save_checkpoint(results, completed)
                
                # Удаляем все checkpoint'ы после успешного завершения
                delete_all_checkpoints()
                    
            except KeyboardInterrupt:
                click.echo("\n\n[ПРЕРВАНО] Сохранение промежуточных результатов...")
                if completed > 0:
                    final_checkpoint = save_checkpoint(results, completed)
                    click.echo(f"[СОХРАНЕНО] Обработано {completed}/{total_products} товаров")
                    if final_checkpoint:
                        click.echo(f"[ФАЙЛ] {final_checkpoint}")
                    click.echo("[ВНИМАНИЕ] Checkpoint файлы НЕ удалены (парсинг прерван)")
                log.warning("interrupted_by_user", completed=completed, total=total_products)
                raise
    
    return results


if __name__ == '__main__':
    main()

