"""Чтение данных из Excel файлов с помощью pandas"""
import pandas as pd
from pathlib import Path
from typing import Optional
import structlog


logger = structlog.get_logger()


class ExcelReader:
    """Читает товары из Excel файла jshopping"""
    
    def __init__(self, file_path: str, name_column: str = 'name_ru-RU'):
        """
        Инициализация читателя Excel.
        
        Args:
            file_path: Путь к Excel файлу
            name_column: Имя колонки с названием товара
        """
        self.file_path = Path(file_path)
        self.name_column = name_column
        self.log = logger.bind(module="ExcelReader", file=str(file_path))
        
        if not self.file_path.exists():
            self.log.error("file_not_found", path=str(self.file_path))
            raise FileNotFoundError(f"Excel файл не найден: {file_path}")
    
    def read_products(self, sheet_name: Optional[str] = None) -> pd.DataFrame:
        """
        Читает товары из Excel файла.
        
        Args:
            sheet_name: Имя листа (если None - первый лист)
            
        Returns:
            DataFrame с товарами
        """
        self.log.info("reading_excel_started", sheet=sheet_name or "first")
        
        try:
            # Читаем Excel файл
            df = pd.read_excel(
                self.file_path,
                sheet_name=sheet_name or 0,  # 0 = первый лист
                engine='openpyxl'
            )
            
            self.log.debug("excel_loaded", 
                          rows=len(df), 
                          columns=len(df.columns))
            
            # Проверяем наличие ключевой колонки
            if self.name_column not in df.columns:
                available_columns = list(df.columns)
                self.log.error("name_column_not_found",
                             expected=self.name_column,
                             available=available_columns)
                raise ValueError(
                    f"Колонка '{self.name_column}' не найдена в Excel файле. "
                    f"Доступные колонки: {available_columns}"
                )
            
            # Добавляем нормализованную колонку для удобства
            df['product_name'] = df[self.name_column].astype(str).str.strip()
            
            # Убираем пустые названия
            initial_count = len(df)
            df = df[df['product_name'].notna()]
            df = df[df['product_name'] != '']
            df = df[df['product_name'] != 'nan']
            
            removed_count = initial_count - len(df)
            if removed_count > 0:
                self.log.warning("empty_names_removed", count=removed_count)
            
            self.log.info("excel_read_completed",
                         total_products=len(df),
                         valid_products=len(df))
            
            return df
            
        except Exception as e:
            self.log.error("excel_read_failed", error=str(e), error_type=type(e).__name__)
            raise
    
    def get_product_names(self, df: pd.DataFrame) -> list:
        """
        Извлекает список названий товаров.
        
        Args:
            df: DataFrame с товарами
            
        Returns:
            Список названий товаров
        """
        if 'product_name' not in df.columns:
            raise ValueError("DataFrame не содержит колонку 'product_name'")
        
        names = df['product_name'].tolist()
        self.log.debug("product_names_extracted", count=len(names))
        return names
    
    def get_sample(self, df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
        """
        Получает выборку товаров для тестирования.
        
        Args:
            df: DataFrame с товарами
            n: Количество товаров для выборки
            
        Returns:
            DataFrame с n первыми товарами
        """
        sample = df.head(n)
        self.log.debug("sample_created", requested=n, actual=len(sample))
        return sample

