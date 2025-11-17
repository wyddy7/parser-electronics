"""Фабрика для создания парсеров"""
from typing import Dict, Type, Optional
import importlib
import structlog
from .base_parser import BaseParser
from .base_async_parser import AsyncBaseParser


# Регистр парсеров: имя -> класс
PARSER_REGISTRY: Dict[str, Type[BaseParser]] = {}
ASYNC_PARSER_REGISTRY: Dict[str, Type[AsyncBaseParser]] = {}


def register_parser(name: str, parser_class: Type[BaseParser]):
    """
    Регистрирует парсер в фабрике.
    
    Args:
        name: Имя парсера (например 'electronpribor')
        parser_class: Класс парсера
    """
    PARSER_REGISTRY[name] = parser_class


def create_parser(
    parser_name: str,
    config: Dict,
    logger: structlog.BoundLogger,
    search_config: Optional[Dict] = None
) -> BaseParser:
    """
    Создает парсер по имени.
    
    Args:
        parser_name: Имя парсера (например 'electronpribor')
        config: Конфигурация парсера
        logger: Logger
        search_config: Конфигурация поиска
        
    Returns:
        Экземпляр парсера
        
    Raises:
        ValueError: Если парсер не найден
    """
    if parser_name not in PARSER_REGISTRY:
        # Формируем имя класса (например: electronpribor -> ElectronpriborParser)
        # Преобразуем snake_case в PascalCase
        class_name_parts = parser_name.split('_')
        class_name = ''.join(word.capitalize() for word in class_name_parts) + 'Parser'
        
        # Пробуем динамический импорт
        try:
            # Используем относительный импорт из текущего пакета
            module_name = f".{parser_name}_parser"
            module = importlib.import_module(module_name, package=__package__)
            
            parser_class = getattr(module, class_name)
            register_parser(parser_name, parser_class)
        except ImportError as e:
            raise ValueError(
                f"Парсер '{parser_name}' не реализован. "
                f"Модуль 'parsers.{parser_name}_parser' не найден. "
                f"Создайте файл src/parsers/{parser_name}_parser.py с классом {class_name}"
            )
        except AttributeError as e:
            raise ValueError(
                f"Парсер '{parser_name}' не реализован. "
                f"Класс '{class_name}' не найден в модуле 'parsers.{parser_name}_parser'. "
                f"Убедитесь, что класс существует и правильно назван"
            )
    
    parser_class = PARSER_REGISTRY[parser_name]
    
    # Проверяем сигнатуру конструктора
    import inspect
    sig = inspect.signature(parser_class.__init__)
    params = list(sig.parameters.keys())[1:]  # Пропускаем self
    
    if 'search_config' in params:
        return parser_class(config, logger, search_config)
    else:
        return parser_class(config, logger)


def register_async_parser(name: str, parser_class: Type[AsyncBaseParser]):
    """
    Регистрирует async парсер в фабрике.
    
    Args:
        name: Имя парсера (например 'electronpribor')
        parser_class: Класс async парсера
    """
    ASYNC_PARSER_REGISTRY[name] = parser_class


def create_async_parser(
    parser_name: str,
    config: Dict,
    logger: structlog.BoundLogger,
    search_config: Optional[Dict] = None
) -> AsyncBaseParser:
    """
    Создает async парсер по имени.
    
    Args:
        parser_name: Имя парсера (например 'electronpribor')
        config: Конфигурация парсера
        logger: Logger
        search_config: Конфигурация поиска
        
    Returns:
        Экземпляр async парсера
        
    Raises:
        ValueError: Если парсер не найден
    """
    if parser_name not in ASYNC_PARSER_REGISTRY:
        # Формируем имя класса (например: electronpribor -> ElectronpriborAsyncParser)
        # Преобразуем snake_case в PascalCase
        class_name_parts = parser_name.split('_')
        class_name = ''.join(word.capitalize() for word in class_name_parts) + 'AsyncParser'
        
        # Пробуем динамический импорт
        try:
            # Используем относительный импорт из текущего пакета
            module_name = f".{parser_name}_async_parser"
            module = importlib.import_module(module_name, package=__package__)
            
            parser_class = getattr(module, class_name)
            register_async_parser(parser_name, parser_class)
        except ImportError as e:
            raise ValueError(
                f"Async парсер '{parser_name}' не реализован. "
                f"Модуль 'parsers.{parser_name}_async_parser' не найден. "
                f"Создайте файл src/parsers/{parser_name}_async_parser.py с классом {class_name}"
            )
        except AttributeError as e:
            raise ValueError(
                f"Async парсер '{parser_name}' не реализован. "
                f"Класс '{class_name}' не найден в модуле 'parsers.{parser_name}_async_parser'. "
                f"Убедитесь, что класс существует и правильно назван"
            )
    
    parser_class = ASYNC_PARSER_REGISTRY[parser_name]
    
    # Проверяем сигнатуру конструктора
    import inspect
    sig = inspect.signature(parser_class.__init__)
    params = list(sig.parameters.keys())[1:]  # Пропускаем self
    
    if 'search_config' in params:
        return parser_class(config, logger, search_config)
    else:
        return parser_class(config, logger)


# Автоматическая регистрация известных парсеров
def _auto_register():
    """Автоматически регистрирует парсеры из модулей"""
    try:
        from .electronpribor_parser import ElectronpriborParser
        register_parser('electronpribor', ElectronpriborParser)
    except ImportError:
        pass
    
    try:
        from .electronpribor_async_parser import ElectronpriborAsyncParser
        register_async_parser('electronpribor', ElectronpriborAsyncParser)
    except ImportError:
        pass
    
    try:
        from .prist_async_parser import PristAsyncParser
        register_async_parser('prist', PristAsyncParser)
    except ImportError:
        pass


_auto_register()

