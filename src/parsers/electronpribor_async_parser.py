"""Асинхронный парсер для сайта electronpribor.ru"""
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
import re
import structlog
import httpx

from .base_async_parser import AsyncBaseParser


class ElectronpriborAsyncParser(AsyncBaseParser):
    """
    Асинхронный парсер для сайта www.electronpribor.ru
    
    Использует httpx.AsyncClient для параллельных запросов.
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
        
        # Возможные варианты URL поиска
        # Правильный формат: /search/?type_search=catalog&q=...
        self.search_patterns = [
            f"{self.base_url}/search/?type_search=catalog&q={{query}}",
            f"{self.base_url}/search/?q={{query}}",
            f"{self.base_url}/?s={{query}}",
        ]
    
    async def search_product(self, product_name: str) -> Optional[Dict[str, Any]]:
        """
        Ищет товар по названию на сайте electronpribor.ru (асинхронно).
        
        Args:
            product_name: Название товара
            
        Returns:
            Словарь с информацией о товаре или None
        """
        self.log.info("search_started", product=product_name)
        
        # Нормализуем название для поиска
        search_query = self._normalize_search_query(product_name)
        
        # Пробуем разные паттерны URL поиска
        for pattern in self.search_patterns:
            search_url = pattern.format(query=search_query)
            
            self.log.debug("trying_search_url", url=search_url, query=search_query)
            
            result = await self._search_with_url(search_url, product_name)
            if result:
                # Проверяем цену
                price = result.get('price')
                if price is None:
                    # Товар найден, но без цены (снят с производства)
                    result['price'] = -1.0  # Специальное значение
                    self.log.warning("product_discontinued",
                                   product=product_name,
                                   found_name=result.get('name'))
                elif price == -2.0:
                    # Цена по запросу - уже установлено в _extract_product_info
                    self.log.info("product_price_on_request",
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
        
        # Реальная структура electronpribor.ru:
        # <ul class="pro-list"> -> <li> -> <div> с данными товара
        products = soup.select('ul.pro-list > li')
        
        if products:
            self.log.debug("products_found",
                          selector='ul.pro-list > li',
                          count=len(products))
        
        if not products:
            self.log.debug("no_products_in_results", url=search_url)
            return None
        
        # Ищем наиболее подходящий товар
        # Приоритет: товары с ценой > товары "по запросу" > товары "снято с производства"
        found_with_price = None  # Товар с ценой (приоритет 1)
        found_on_request = None  # Товар "по запросу" (приоритет 2)
        found_without_price = None  # Товар без цены/снят (приоритет 3)
        
        for idx, product in enumerate(products[:self.max_results]):
            product_info = self._extract_product_info(product, original_name)
            
            if product_info and self._is_name_match(original_name, product_info['name']):
                price = product_info.get('price')
                
                if price is not None and price > 0:
                    # Товар с ценой - возвращаем сразу (приоритет 1)
                    self.log.info("product_matched_with_price",
                                 original=original_name,
                                 found=product_info['name'],
                                 price=price)
                    return product_info
                elif price == -2.0 and found_on_request is None:
                    # Сохраняем первый товар "по запросу" (приоритет 2)
                    found_on_request = product_info
                    self.log.debug("product_matched_on_request",
                                  original=original_name,
                                  found=product_info['name'])
                elif price is None and found_without_price is None:
                    # Сохраняем первый товар без цены (приоритет 3)
                    found_without_price = product_info
                    self.log.debug("product_matched_without_price",
                                  original=original_name,
                                  found=product_info['name'])
        
        # Возвращаем по приоритету
        if found_on_request:
            self.log.info("product_found_price_on_request",
                         original=original_name,
                         found=found_on_request['name'])
            return found_on_request
        elif found_without_price:
            self.log.info("product_found_but_discontinued",
                         original=original_name,
                         found=found_without_price['name'])
            return found_without_price
        
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
        # В electronpribor.ru: <h4> содержит название
        name_elem = product_element.select_one('h4')
        name = None
        if name_elem:
            # СНАЧАЛА удаляем все <b> теги (unwrap убирает тег но оставляет содержимое)
            for b_tag in name_elem.find_all('b'):
                b_tag.unwrap()
            # ПОТОМ извлекаем текст
            name = name_elem.get_text(strip=True)
            # Добавляем пробел после запятой если его нет
            name = re.sub(r',(\S)', r', \1', name)
            # Убираем ЛИШНИЕ пробелы
            name = re.sub(r'\s+', ' ', name)
        
        if not name:
            self.log.debug("name_not_found", html=str(product_element)[:200])
            return None
        
        info['name'] = name
        
        # Извлекаем цену  
        # В electronpribor.ru: <noindex><p>49&nbsp;000 ₽</p></noindex>
        # ВАЖНО: Берем ПЕРВЫЙ <p>, игнорируем текст после первого ₽
        price = None
        full_text = ""
        noindex_elem = product_element.select_one('noindex')
        if noindex_elem:
            # Берём весь текст из noindex
            full_text = noindex_elem.get_text(separator=' ', strip=True)
            # Разбиваем по символу ₽ и берём ТОЛЬКО первую часть
            if '₽' in full_text:
                first_price_text = full_text.split('₽')[0] + '₽'
                price = self._extract_price_value_universal(first_price_text)
            elif 'руб' in full_text.lower():
                first_price_text = full_text.split('руб')[0] + 'руб'
                price = self._extract_price_value_universal(first_price_text)
        
        # Если цена не найдена, ищем текст статуса во всем элементе товара
        if not price:
            # Берем весь текст элемента для поиска статуса
            element_text = product_element.get_text(separator=' ', strip=True)
            
            # Используем универсальную функцию определения статуса
            status = self._detect_price_status(element_text)
            if status == -2.0:
                # Цена по запросу
                info['price'] = -2.0
                self.log.debug("price_on_request", 
                              name=name,
                              status="Цена по запросу",
                              raw_text=element_text[:100])
            elif status == -1.0:
                # Снят с производства
                info['price'] = -1.0
                self.log.debug("price_discontinued", 
                              name=name,
                              status="Снят с производства",
                              raw_text=element_text[:100])
            else:
                # Без цены
                info['price'] = None
                self.log.debug("price_not_found", 
                              name=name,
                              status="Без цены",
                              raw_text=element_text[:100] if element_text else None)
        else:
            info['price'] = price
            self.log.debug("price_extracted",
                          name=name,
                          price=price)
        
        # Извлекаем ссылку на товар
        # В electronpribor.ru: <a class="search-stat-link">
        link_elem = product_element.select_one('a.search-stat-link')
        if link_elem and link_elem.get('href'):
            href = link_elem['href']
            # Делаем абсолютный URL если нужно
            if href.startswith('/'):
                href = self.base_url + href
            info['url'] = href
        
        # Всегда возвращаем товар, даже если цена = None
        # price = None означает "Снят с производства" или "Поставка прекращена"
        return info
    

