"""Загрузка и валидация конфигурации из YAML файла"""
import yaml
from pathlib import Path
from typing import Dict, Any


class ConfigLoader:
    """Загрузчик конфигурации из YAML файлов"""
    
    def __init__(self, config_path: str):
        """
        Инициализация загрузчика конфигурации.
        
        Args:
            config_path: Путь к YAML файлу конфигурации
        """
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")
        
        self.config = self._load_config()
        self._validate_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Загружает YAML конфигурацию из файла.
        
        Returns:
            Словарь с конфигурацией
        """
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if config is None:
            raise ValueError(f"Пустой конфигурационный файл: {self.config_path}")
        
        return config
    
    def _validate_config(self):
        """Валидирует обязательные поля конфигурации"""
        required_sections = ['parser', 'excel', 'logging']
        
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"Отсутствует обязательная секция '{section}' в конфигурации")
        
        # Проверяем наличие хотя бы одного enabled парсера
        parsers = self.config.get('parser', {})
        enabled_parsers = [name for name, cfg in parsers.items() 
                          if cfg.get('enabled', True)]
        
        if not enabled_parsers:
            raise ValueError("Не найден ни один включенный парсер в конфигурации")
        
        # Проверяем наличие входного файла Excel
        if 'input_file' not in self.config['excel']:
            raise ValueError("Не указан входной Excel файл (excel.input_file)")
        
        # Проверяем наличие колонки с названием товара
        if 'name_column' not in self.config['excel']:
            raise ValueError("Не указана колонка с названием товара (excel.name_column)")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Получить значение из конфигурации.
        
        Args:
            key: Ключ конфигурации (поддерживает точечную нотацию, например 'parser.electronpribor.base_url')
            default: Значение по умолчанию если ключ не найден
            
        Returns:
            Значение конфигурации или default
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_enabled_parsers(self) -> list[str]:
        """
        Возвращает список имен включенных парсеров.
        
        Returns:
            Список имен парсеров (например ['electronpribor', 'pristru'])
        """
        parsers = self.config.get('parser', {})
        return [name for name, cfg in parsers.items() 
                if cfg.get('enabled', True)]
    
    def get_parser_config(self, parser_name: str) -> Dict[str, Any]:
        """
        Получить конфигурацию конкретного парсера.
        
        Args:
            parser_name: Имя парсера
            
        Returns:
            Словарь с конфигурацией парсера
            
        Raises:
            ValueError: Если парсер не найден
        """
        parsers = self.config.get('parser', {})
        if parser_name not in parsers:
            raise ValueError(f"Парсер '{parser_name}' не найден в конфигурации")
        return parsers[parser_name]
    
    def get_excel_config(self) -> Dict[str, Any]:
        """
        Получить конфигурацию Excel.
        
        Returns:
            Словарь с конфигурацией Excel
        """
        return self.config['excel']
    
    def get_logging_config(self) -> Dict[str, Any]:
        """
        Получить конфигурацию логирования.
        
        Returns:
            Словарь с конфигурацией логирования
        """
        return self.config['logging']
    
    def get_search_config(self) -> Dict[str, Any]:
        """
        Получить конфигурацию поиска.
        
        Returns:
            Словарь с конфигурацией поиска
        """
        return self.config.get('search', {})
    
    @property
    def input_file(self) -> str:
        """Путь к входному Excel файлу"""
        return self.config['excel']['input_file']
    
    @property
    def output_dir(self) -> str:
        """Директория для выходных файлов"""
        return self.config['excel'].get('output_dir', 'output')
    
    @property
    def name_column(self) -> str:
        """Имя колонки с названием товара"""
        return self.config['excel']['name_column']

