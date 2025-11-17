"""Фабрика для создания парсеров"""
from typing import Dict, Type, Optional
import importlib
import structlog
from .base_parser import BaseParser


# Регистр парсеров: имя -> класс
PARSER_REGISTRY: Dict[str, Type[BaseParser]] = {}


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


# Автоматическая регистрация известных парсеров
def _auto_register():
    """Автоматически регистрирует парсеры из модулей"""
    try:
        from .electronpribor_parser import ElectronpriborParser
        register_parser('electronpribor', ElectronpriborParser)
    except ImportError:
        pass


_auto_register()

