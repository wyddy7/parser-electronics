"""Асинхронный парсер для сайта flukeshop.ru"""
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
import structlog
import urllib.parse

from .base_async_parser import AsyncBaseParser


class FlukeShopAsyncParser(AsyncBaseParser):
    """
    Асинхронный парсер для сайта flukeshop.ru
    
    Использует httpx.AsyncClient для параллельных запросов.
    Особенность: поиск не работает с запятыми, нужна нормализация запроса.
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
        
        # URL поиска для flukeshop.ru
        # Формат: /search?search={query}
        self.search_url_template = f"{self.base_url}search?search={{query}}"
    
    def _normalize_search_query(self, product_name: str) -> str:
        """
        Нормализует название товара для поискового запроса.
        
        Убирает запятые и слова после запятой (например, "тепловизор", "мультиметр").
        Оставляет только основное название модели.
        
        Пример: "Fluke TiX501, тепловизор" → "Fluke TiX501"
        
        Args:
            product_name: Исходное название
            
        Returns:
            Нормализованное название без запятых и дополнительных слов
        """
        # Убираем запятые и все что после них
        if ',' in product_name:
            product_name = product_name.split(',')[0].strip()
        
        # Убираем лишние пробелы
        return ' '.join(product_name.split())
    
    async def search_product(self, product_name: str) -> Optional[Dict[str, Any]]:
        """
        Ищет товар по названию на сайте flukeshop.ru (асинхронно).
        
        Args:
            product_name: Название товара
            
        Returns:
            Словарь с информацией о товаре или None
        """
        self.log.info("search_started", product=product_name)
        
        # Нормализуем название для поиска (убираем запятые)
        search_query = self._normalize_search_query(product_name)
        search_url = self.search_url_template.format(query=urllib.parse.quote(search_query))
        
        self.log.debug("trying_search_url", url=search_url, query=search_query, original=product_name)
        
        result = await self._search_with_url(search_url, product_name)
        if result:
            # Проверяем цену
            price = result.get('price')
            if price is None:
                # Товар найден, но без цены (снят с производства)
                result['price'] = -1.0
                self.log.warning("product_discontinued",
                               product=product_name,
                               found_name=result.get('name'))
            elif price == -2.0:
                # Цена по запросу
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
        
        # Структура flukeshop.ru:
        # <div id="products" class="product-grid"> -> <div class="products-block"> -> <div class="row products-row"> -> <div class="product-col">
        products = soup.select('div#products.product-grid > div.products-block > div.row.products-row > div.product-col')
        
        if products:
            self.log.debug("products_found",
                          selector='div#products.product-grid > div.products-block > div.row.products-row > div.product-col',
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
        # В flukeshop.ru: <h3 class="name"><a>Тепловизор <br><span class="product_title_model">Fluke TiS60+</span></a></h3>
        name_elem = product_element.select_one('h3.name a')
        name = None
        if name_elem:
            # Берем модель из span.product_title_model если есть, иначе весь текст
            model_elem = name_elem.select_one('span.product_title_model')
            if model_elem:
                name = model_elem.get_text(strip=True)
            else:
                name = name_elem.get_text(strip=True)
        
        if not name:
            self.log.debug("name_not_found", html=str(product_element)[:200])
            return None
        
        info['name'] = name
        
        # Извлекаем цену
        # В flukeshop.ru: <div class="price"><span class="price-new">1 058 992 р.</span></div>
        # Или: <div class="price">По запросу</div>
        price = None
        price_elem = product_element.select_one('div.price span.price-new')
        
        if price_elem:
            # Есть цена
            price_text = price_elem.get_text(strip=True)
            # Формат: "1 058 992 р." - универсальная функция обработает "р." как валюту
            price = self._extract_price_value_universal(price_text)
        else:
            # Проверяем статус "по запросу"
            price_div = product_element.select_one('div.price')
            if price_div:
                price_text = price_div.get_text(strip=True)
                status = self._detect_price_status(price_text)
                if status == -2.0:
                    info['price'] = -2.0
                    self.log.debug("price_on_request", name=name)
                elif status == -1.0:
                    info['price'] = -1.0
                    self.log.debug("price_discontinued", name=name)
                else:
                    info['price'] = None
                    self.log.debug("price_not_found", name=name)
            else:
                info['price'] = None
                self.log.debug("price_not_found", name=name)
        
        if price:
            info['price'] = price
            self.log.debug("price_extracted", name=name, price=price)
        
        # Извлекаем ссылку на товар
        # В flukeshop.ru: <a href="..."> в h3.name или div.block-img
        link_elem = product_element.select_one('h3.name a')
        if not link_elem:
            link_elem = product_element.select_one('div.block-img a.img')
        
        if link_elem and link_elem.get('href'):
            href = link_elem['href']
            # Делаем абсолютный URL если нужно
            if href.startswith('/'):
                href = self.base_url.rstrip('/') + href
            elif not href.startswith('http'):
                href = self.base_url.rstrip('/') + '/' + href
            info['url'] = href
        
        return info

