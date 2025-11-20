"""Асинхронный парсер для сайта zenit-electro.ru"""
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
import structlog

from .base_async_parser import AsyncBaseParser


class ZenitElectroAsyncParser(AsyncBaseParser):
    """
    Асинхронный парсер для сайта www.zenit-electro.ru
    
    Особенности:
    - Двухэтапный парсинг: поиск → страница товара → цена
    - Цена находится только на странице товара, не в результатах поиска
    - Использует httpx.AsyncClient для параллельных запросов
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
        
        # URL поиска для zenit-electro.ru
        # Формат: /component/finder/search.html?q={query}&Search=
        self.search_url_template = f"{self.base_url}component/finder/search.html?q={{query}}&Search="
    
    def _normalize_search_query(self, product_name: str) -> str:
        """
        Нормализует название товара для поискового запроса.
        Заменяет пробелы на + для URL encoding.
        
        Args:
            product_name: Исходное название
            
        Returns:
            Нормализованное название с + вместо пробелов
        """
        # Сначала применяем базовую нормализацию (обрезка после запятой)
        normalized = super()._normalize_search_query(product_name)
        # Затем заменяем пробелы на +
        query = '+'.join(normalized.split())
        return query
    
    async def search_product(self, product_name: str) -> Optional[Dict[str, Any]]:
        """
        Ищет товар по названию на сайте zenit-electro.ru (асинхронно).
        
        Процесс:
        1. Поиск товара → получение URL страницы товара
        2. Запрос страницы товара → извлечение цены
        
        Args:
            product_name: Название товара
            
        Returns:
            Словарь с информацией о товаре или None
        """
        self.log.info("search_started", product=product_name)
        
        # Нормализуем название для поиска
        search_query = self._normalize_search_query(product_name)
        search_url = self.search_url_template.format(query=search_query)
        
        self.log.debug("trying_search_url", url=search_url, query=search_query)
        
        # Шаг 1: Поиск товара
        product_url = await self._search_with_url(search_url, product_name)
        
        if not product_url:
            self.log.warning("product_not_found", product=product_name)
            return {
                'name': None,
                'price': 0.0,  # Цена = 0 если товар не найден
                'url': None
            }
        
        # Шаг 2: Получение цены со страницы товара
        product_info = await self._fetch_product_page(product_url, product_name)
        
        if product_info:
            # Проверяем цену
            price = product_info.get('price')
            if price is None:
                # Товар найден, но без цены
                product_info['price'] = -1.0
                self.log.warning("product_no_price",
                               product=product_name,
                               found_name=product_info.get('name'))
        
        return product_info
    
    async def _search_with_url(self, search_url: str, original_name: str) -> Optional[str]:
        """
        Выполняет асинхронный поиск по конкретному URL.
        
        Args:
            search_url: URL для поиска
            original_name: Оригинальное название товара
            
        Returns:
            URL страницы товара или None если не найден
        """
        response = await self._make_request_with_retry(search_url)
        if not response:
            return None
        
        # Парсим HTML с помощью BeautifulSoup (lxml parser - быстрее)
        soup = BeautifulSoup(response.text, 'lxml')
        
        # Структура zenit-electro.ru:
        # <ul id="search-result-list" class="search-results"> -> <li>
        products = soup.select('ul#search-result-list > li')
        
        if products:
            self.log.debug("products_found",
                          selector='ul#search-result-list > li',
                          count=len(products))
        
        if not products:
            self.log.debug("no_products_in_results", url=search_url)
            return None
        
        # Ищем наиболее подходящий товар
        for idx, product in enumerate(products[:self.max_results]):
            product_info = self._extract_product_info_from_search(product, original_name)
            
            if not product_info:
                continue
            
            # Проверяем совпадение артикула
            if self._is_name_match(original_name, product_info['name'], product_info.get('url', '')):
                # Товар найден - возвращаем URL страницы товара
                self.log.info("product_matched",
                             original=original_name,
                             found=product_info['name'],
                             url=product_info['url'])
                return product_info['url']
        
        self.log.debug("no_matching_products", original_name=original_name)
        return None
    
    def _extract_product_info_from_search(self, product_element, original_name: str) -> Optional[Dict[str, Any]]:
        """
        Извлекает информацию о товаре из результата поиска.
        
        В результатах поиска zenit-electro.ru НЕТ цены, только название и URL.
        Цена будет получена позже со страницы товара.
        
        Args:
            product_element: BeautifulSoup элемент товара из результатов поиска
            original_name: Оригинальное название для контекста
            
        Returns:
            Словарь с информацией о товаре (name, url, без price)
        """
        info = {}
        
        # Извлекаем название и URL
        # Структура: <h4 class="result-title"><a href="...">Название</a></h4>
        link_elem = product_element.select_one('h4.result-title a')
        if not link_elem:
            self.log.debug("link_not_found", html=str(product_element)[:200])
            return None
        
        # Извлекаем название
        name = link_elem.get_text(strip=True)
        
        if not name:
            self.log.debug("name_not_found", html=str(product_element)[:200])
            return None
        
        info['name'] = name
        
        # Извлекаем URL товара
        href = link_elem.get('href', '')
        if href:
            # Делаем абсолютный URL если нужно
            if href.startswith('/'):
                href = self.base_url.rstrip('/') + href
            info['url'] = href
        else:
            self.log.debug("url_not_found", html=str(product_element)[:200])
            return None
        
        self.log.debug("product_info_extracted_from_search",
                      name=name,
                      url=info['url'])
        
        return info
    
    async def _fetch_product_page(self, product_url: str, original_name: str) -> Optional[Dict[str, Any]]:
        """
        Запрашивает страницу товара и извлекает цену.
        
        Args:
            product_url: URL страницы товара
            original_name: Оригинальное название для контекста
            
        Returns:
            Словарь с информацией о товаре (name, price, url)
        """
        self.log.debug("fetching_product_page", url=product_url)
        
        response = await self._make_request_with_retry(product_url)
        if not response:
            self.log.warning("product_page_not_accessible",
                           url=product_url,
                           product=original_name)
            return None
        
        # Парсим HTML страницы товара
        soup = BeautifulSoup(response.text, 'lxml')
        
        # Извлекаем название товара со страницы
        page_name = None
        name_elem = soup.select_one('h1[itemprop="name"]')
        if name_elem:
            page_name = name_elem.get_text(strip=True)
        
        # Извлекаем цену
        price = await self._extract_price_from_product_page(soup, product_url)
        
        return {
            'name': page_name or original_name,
            'price': price,
            'url': product_url
        }
    
    async def _extract_price_from_product_page(self, soup: BeautifulSoup, product_url: str) -> Optional[float]:
        """
        Извлекает цену со страницы товара.
        
        Структура цены в zenit-electro.ru:
        - Цена: <span id="block_price">23500 ₽ (с НДС)</span>
        - Брать цену с НДС (первая)
        
        Args:
            soup: BeautifulSoup объект страницы товара
            product_url: URL товара для логирования
            
        Returns:
            Цена как float или None
        """
        price_elem = soup.select_one('span#block_price')
        
        if not price_elem:
            self.log.warning("price_element_not_found",
                           url=product_url)
            return None
        
        price_text = price_elem.get_text(strip=True)
        # Формат: "23500 ₽ (с НДС)" или "20445 ₽ (без НДС)"
        # Брать цену с НДС (первая, до скобки)
        if '(' in price_text:
            price_text = price_text.split('(')[0].strip()
        
        self.log.debug("price_found_on_page",
                      url=product_url,
                      raw_text=price_text)
        
        price = self._extract_price_value_universal(price_text)
        if price:
            return price
        
        self.log.warning("price_parse_failed",
                        url=product_url,
                        text=price_text)
        return None

