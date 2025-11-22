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
        # Используем fallback селекторы
        selectors = [
            '.products-block.row > .product-layout.product-grid',
            '.product-layout',
            '.product-thumb',
            '.products-block .product-layout'
        ]
        
        products = []
        used_selector = ""
        for selector in selectors:
            found = soup.select(selector)
            if found:
                products = found
                used_selector = selector
                break
        
        if products:
            self.log.debug("products_found",
                          selector=used_selector,
                          count=len(products))
        else:
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
        
        # Fallback для названия
        if not name_elem:
            name_selectors = ['.name', '.caption h4 a', '.caption a', 'div.caption h4']
            for sel in name_selectors:
                name_elem = product_element.select_one(sel)
                if name_elem:
                    break
                    
        name = None
        if name_elem:
            name = name_elem.get_text(strip=True)
        
        if not name:
            self.log.debug("name_not_found", html=str(product_element)[:200])
            return None
        
        info['name'] = name
        
        # Извлекаем цену
        # 1. Сначала пробуем опции (там реальные цены на аксессуары/модификации)
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
        
        # 2. Если не нашли в опциях, пробуем извлечь из title опции
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
                        
        # 3. Fallback: обычная цена
        if not price:
            price_selectors = ['.price', '.price-new', 'span.price']
            for sel in price_selectors:
                price_elem = product_element.select_one(sel)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    # Извлекаем data-price если есть (он точнее)
                    if price_elem.has_attr('data-price'):
                        try:
                            price = float(price_elem['data-price'])
                            break
                        except (ValueError, TypeError):
                            pass
                    
                    # Иначе парсим текст
                    price = self._extract_price_value_universal(price_text)
                    if price and price > 0:
                        break
        
        if price:
            info['price'] = price
        else:
            # Проверяем статус цены (по запросу, снят и т.д.)
            price_elem = product_element.select_one('.price')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                status = self._detect_price_status(price_text)
                if status:
                    info['price'] = status
                    if status == -2.0:
                        self.log.debug("price_on_request", name=name)
                    elif status == -1.0:
                        self.log.debug("price_discontinued", name=name)
                else:
                    info['price'] = None
                    self.log.debug("price_not_found", name=name)
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
