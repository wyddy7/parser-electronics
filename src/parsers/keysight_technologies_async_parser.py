"""Асинхронный парсер для сайта keysight-technologies.ru"""
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
import structlog
import urllib.parse

from .base_async_parser import AsyncBaseParser


class KeysightTechnologiesAsyncParser(AsyncBaseParser):
    """
    Асинхронный парсер для сайта keysight-technologies.ru
    
    Использует httpx.AsyncClient для параллельных запросов.
    Особенность: реальные цены находятся в опциях товара (data-price), а не в основной цене.
    """
    
    def __init__(self, config: Dict[str, Any], logger: structlog.BoundLogger, search_config: Optional[Dict[str, Any]] = None):
        """
        Инициализация асинхронного парсера.
        
        Args:
            config: Конфигурация парсера
            logger: Logger для логирования
            search_config: Конфигурация поиска (min_similarity, max_results)
        """
        super().__init__(config, logger)
        
        # Настройки поиска
        self.search_config = search_config or {}
        self.min_similarity = self.search_config.get('min_similarity', 0.5)
        self.max_results = self.search_config.get('max_results', 5)
        
        # URL поиска для keysight-technologies.ru
        # Формат: /index.php?route=product/search&search={query}&description=true
        # Обязательный параметр description=true
        self.search_url_template = f"{self.base_url}index.php?route=product/search&search={{query}}&description=true"
    
    async def search_product(self, product_name: str) -> Optional[Dict[str, Any]]:
        """
        Ищет товар по названию на сайте keysight-technologies.ru (асинхронно).
        
        Args:
            product_name: Название товара
            
        Returns:
            Словарь с информацией о товаре или None
        """
        self.log.info("search_started", product=product_name)
        
        # Нормализуем название для поиска
        search_query = self._normalize_search_query(product_name)
        search_url = self.search_url_template.format(query=urllib.parse.quote(search_query))
        
        self.log.debug("trying_search_url", url=search_url, query=search_query)
        
        result = await self._search_with_url(search_url, product_name)
        if result:
            # Проверяем цену
            price = result.get('price')
            if price is None:
                # Товар найден, но без цены
                result['price'] = -1.0
                self.log.warning("product_no_price",
                               product=product_name,
                               found_name=result.get('name'))
            return result
        
        self.log.warning("product_not_found", product=product_name)
        # Возвращаем словарь с ценой = 0 вместо None
        return {
            'name': None,
            'price': 0.0,  # Цена = 0 если товар не найден
            'url': None
        }
    
    async def _search_with_url(self, search_url: str, original_name: str) -> Optional[Dict[str, Any]]:
        """
        Выполняет асинхронный поиск по конкретному URL.
        
        Args:
            search_url: URL для поиска
            original_name: Оригинальное название товара
            
        Returns:
            Информация о товаре или None
        """
        response = await self._make_request_with_retry(search_url)
        if not response:
            return None
        
        # Парсим HTML с помощью BeautifulSoup (lxml parser - быстрее)
        soup = BeautifulSoup(response.text, 'lxml')
        
        # Структура keysight-technologies.ru:
        # <div class="products-block row"> -> <div class="product-layout product-grid">
        products = soup.select('.products-block.row > .product-layout.product-grid')
        
        if products:
            self.log.debug("products_found",
                          selector='.products-block.row > .product-layout.product-grid',
                          count=len(products))
        
        if not products:
            self.log.debug("no_products_in_results", url=search_url)
            return None
        
        # Ищем наиболее подходящий товар
        for idx, product in enumerate(products[:self.max_results]):
            product_info = self._extract_product_info(product, original_name)
            
            if product_info and self._is_name_match(original_name, product_info['name']):
                # Товар найден
                price = product_info.get('price')
                if price is not None and price > 0:
                    self.log.info("product_matched_with_price",
                                 original=original_name,
                                 found=product_info['name'],
                                 price=price)
                    return product_info
                else:
                    # Товар найден, но без цены - все равно возвращаем
                    self.log.info("product_matched_without_price",
                                 original=original_name,
                                 found=product_info['name'])
                    return product_info
        
        self.log.debug("no_matching_products", original_name=original_name)
        return None
    
    def _extract_product_info(self, product_element, original_name: str) -> Optional[Dict[str, Any]]:
        """
        Извлекает информацию о товаре из HTML элемента.
        
        Args:
            product_element: BeautifulSoup элемент товара
            original_name: Оригинальное название для контекста
            
        Returns:
            Словарь с информацией о товаре
        """
        info = {}
        
        # Извлекаем название
        # В keysight-technologies.ru: <a class="product-thumb__name">Название</a>
        name_elem = product_element.select_one('.product-thumb__name')
        name = None
        if name_elem:
            name = name_elem.get_text(strip=True)
        
        if not name:
            self.log.debug("name_not_found", html=str(product_element)[:200])
            return None
        
        info['name'] = name
        
        # Извлекаем цену из опций товара
        # ВАЖНО: Основная цена .product-thumb__price.price показывает базовую цену (обычно 81 ₽)
        # Реальные цены находятся в опциях товара в атрибуте data-price
        price = None
        
        # Ищем все опции с data-price
        option_items = product_element.select('.option__item[data-price]')
        
        if option_items:
            # Берем первую опцию с ценой > 1000 (базовая цена обычно 81 ₽)
            for option_item in option_items:
                input_elem = option_item.select_one('input[data-price]')
                if input_elem and input_elem.get('data-price'):
                    try:
                        option_price = float(input_elem.get('data-price'))
                        if option_price > 1000:  # Игнорируем базовую цену (81 ₽)
                            price = option_price
                            self.log.debug("price_extracted_from_option",
                                        name=name,
                                        price=price,
                                        option_name=option_item.select_one('.option__name'))
                            break
                    except (ValueError, TypeError):
                        continue
        
        # Если не нашли в опциях, пробуем извлечь из title опции
        if not price:
            option_names = product_element.select('.option__name[title]')
            for option_name in option_names:
                title = option_name.get('title', '')
                if title and '₽' in title:
                    # Формат: "+ 43935 ₽"
                    price = self._extract_price_value_universal(title)
                    if price and price > 1000:
                        self.log.debug("price_extracted_from_title",
                                      name=name,
                                      price=price,
                                      title=title)
                        break
        
        if price:
            info['price'] = price
        else:
            info['price'] = None
            self.log.debug("price_not_found", name=name)
        
        # Извлекаем ссылку на товар
        # В keysight-technologies.ru: <a class="product-thumb__name" href="...">
        if name_elem and name_elem.get('href'):
            href = name_elem['href']
            # Делаем абсолютный URL если нужно
            if href.startswith('/'):
                href = self.base_url.rstrip('/') + href
            info['url'] = href
        
        return info

