"""Конфигурация структурного логирования через structlog"""
import sys
import logging
import structlog
from pathlib import Path


def configure_logging(config: dict) -> structlog.BoundLogger:
    """
    Настраивает structlog согласно конфигурации.
    
    Использует ProcessorFormatter для разных форматов:
    - Консоль: формат из config.format ("json" или "console")
    - Файл: всегда JSON формат (JSONRenderer)
    
    Args:
        config: Словарь с настройками логирования из config.yaml
        
    Returns:
        Сконфигурированный logger
    """
    log_level = config.get("level", "DEBUG").upper()
    console_enabled = config.get("console", True)
    log_file = config.get("file", "logs/parser.log")
    log_format = config.get("format", "console").lower()  # Используем format из конфига
    
    # Создаем директорию для логов если не существует
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Общие процессоры для всех конфигураций (до форматирования)
    # Эти процессоры применяются ДО того, как данные попадут в ProcessorFormatter
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    # Конфигурируем structlog с wrap_for_formatter
    # Это подготавливает данные для ProcessorFormatter в handler'ах
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.DEBUG)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Настраиваем стандартный logging
    std_logger = logging.getLogger()
    std_logger.setLevel(getattr(logging, log_level, logging.DEBUG))
    
    # Очищаем существующие обработчики
    std_logger.handlers.clear()
    
    # Добавляем обработчик для файла с JSON форматированием
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
        file_handler.setLevel(getattr(logging, log_level, logging.DEBUG))
        
        # ProcessorFormatter для файла: JSON формат
        file_formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=shared_processors,
        )
        file_handler.setFormatter(file_formatter)
        std_logger.addHandler(file_handler)
    
    # Добавляем обработчик для консоли с форматированием из конфига
    if console_enabled:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(getattr(logging, log_level, logging.DEBUG))
        
        # Выбираем формат для консоли на основе конфига
        if log_format == "json":
            # JSON формат для консоли (удобно для CI/CD, парсинга)
            console_formatter = structlog.stdlib.ProcessorFormatter(
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.dict_tracebacks,
                    structlog.processors.JSONRenderer(),
                ],
                foreign_pre_chain=shared_processors,
            )
        else:
            # Цветной консольный формат (по умолчанию)
            console_formatter = structlog.stdlib.ProcessorFormatter(
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(colors=True),
                ],
                foreign_pre_chain=shared_processors,
            )
        
        console_handler.setFormatter(console_formatter)
        std_logger.addHandler(console_handler)
    
    return structlog.get_logger()


def get_logger(name: str = None) -> structlog.BoundLogger:
    """
    Получить logger с опциональным именем.
    
    Args:
        name: Имя logger'а (опционально)
        
    Returns:
        BoundLogger экземпляр
    """
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(logger_name=name)
    return logger

