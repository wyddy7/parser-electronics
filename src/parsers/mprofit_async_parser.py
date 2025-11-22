"""Асинхронный парсер для сайта mprofit.ru"""
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
import structlog
import urllib.parse

from .base_async_parser import AsyncBaseParser


class MProfitAsyncParser(AsyncBaseParser):
    """
    Асинхронный парсер для сайта mprofit.ru
    
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
        
        # URL поиска для mprofit.ru
        # Формат: /catalog/?q={query}&s=Найти&type=catalog
        self.search_url_template = f"{self.base_url}catalog/?q={{query}}&s=Найти&type=catalog"
    
    async def search_product(self, product_name: str) -> Optional[Dict[str, Any]]:
        """
        Ищет товар по названию на сайте mprofit.ru (асинхронно).
        
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
        
        # Структура mprofit.ru:
        # <div class="catalog list search js_wrapper_items"> -> <div class="list_item_wrapp item_wrap item">
        # Пробуем разные селекторы (как в тесте)
        products = soup.select('.catalog.list.search.js_wrapper_items > .list_item_wrapp.item_wrap.item')
        if not products:
            # Альтернативный селектор
            products = soup.select('.list_item_wrapp.item_wrap.item')
        if not products:
            # Еще один вариант
            products = soup.select('.catalog.list.search .list_item_wrapp')
        
        self.log.info("products_selected", 
                     count=len(products),
                     selector='.catalog.list.search.js_wrapper_items > .list_item_wrapp.item_wrap.item (with fallbacks)',
                     url=search_url[:100])
        
        if products:
            self.log.debug("products_found",
                          selector='.catalog.list.search.js_wrapper_items > .list_item_wrapp.item_wrap.item (with fallbacks)',
                          count=len(products))
        
        if not products:
            self.log.debug("no_products_in_results", url=search_url)
            return None

        # Ищем наиболее подходящий товар
        # Приоритет: товары с ценой > товары "по запросу" > товары "снято с производства"
        found_with_price = None  # Товар с ценой (приоритет 1)
        found_on_request = None  # Товар "по запросу" (приоритет 2)
        found_without_price = None  # Товар без цены/снят (приоритет 3)
        
        self.log.info("processing_products",
                     total_products=len(products),
                     max_results=self.max_results,
                     original_name=original_name)
        
        for idx, product in enumerate(products[:self.max_results]):
            product_info = self._extract_product_info(product, original_name)
            
            if not product_info:
                self.log.warning("product_info_is_none", 
                                idx=idx,
                                original=original_name,
                                html_preview=str(product)[:300])
                continue
            
            if product_info:
                product_name = product_info.get('name')
                if not product_name:
                    self.log.error("product_info_has_no_name",
                                  idx=idx,
                                  original=original_name,
                                  product_info_keys=list(product_info.keys()))
                    continue
                
                is_match = self._is_name_match(original_name, product_name)
                self.log.info("checking_product_match",
                             idx=idx,
                             original=original_name,
                             found=product_name,
                             is_match=is_match,
                             price=product_info.get('price'),
                             price_type=type(product_info.get('price')).__name__)
                
                if is_match:
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
                    elif price is None or price == -1.0:
                        # Сохраняем первый товар без цены или снятый (приоритет 3)
                        if found_without_price is None:
                            found_without_price = product_info
                            self.log.info("product_matched_without_price",
                                          original=original_name,
                                          found=product_info['name'],
                                          price=price,
                                          price_type=type(price).__name__)
        
        # Возвращаем по приоритету
        if found_on_request:
            self.log.info("product_found_price_on_request",
                         original=original_name,
                         found=found_on_request['name'],
                         price=found_on_request.get('price'))
            return found_on_request
        elif found_without_price:
            self.log.info("product_found_but_discontinued",
                         original=original_name,
                         found=found_without_price['name'],
                         price=found_without_price.get('price'))
            return found_without_price
        
        self.log.warning("no_matching_products", 
                        original_name=original_name,
                        found_with_price=found_with_price is not None,
                        found_on_request=found_on_request is not None,
                        found_without_price=found_without_price is not None)
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
        # В mprofit.ru: <div class="item-title"><a><span>Название</span></a></div>
        name_elem = product_element.select_one('.item-title a span')
        if not name_elem:
            name_elem = product_element.select_one('.item-title a')
        
        name = None
        if name_elem:
            name = name_elem.get_text(strip=True)
        
        if not name:
            # Детальная диагностика: проверяем структуру HTML
            has_item_title = product_element.select_one('.item-title') is not None
            has_item_title_a = product_element.select_one('.item-title a') is not None
            has_item_title_a_span = product_element.select_one('.item-title a span') is not None
            self.log.warning("name_not_found", 
                            html=str(product_element)[:300],
                            has_item_title=has_item_title,
                            has_item_title_a=has_item_title_a,
                            has_item_title_a_span=has_item_title_a_span)
            return None
        
        info['name'] = name
        
        # Извлекаем цену
        # В mprofit.ru: <span class="price_value">303 174</span><span class="price_currency"> руб.</span>
        # Или: <div class="price">Цена по запросу</div>
        price = None
        price_value_elem = product_element.select_one('.price_value')
        
        if price_value_elem:
            # Есть цена
            price_text = price_value_elem.get_text(strip=True)
            # Добавляем "руб." для универсальной функции
            price_currency_elem = product_element.select_one('.price_currency')
            currency = price_currency_elem.get_text(strip=True) if price_currency_elem else " руб."
            price_text_with_currency = f"{price_text}{currency}"
            price = self._extract_price_value_universal(price_text_with_currency)
        else:
            # Проверяем статус "по запросу"
            price_elem = product_element.select_one('.price')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
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
                # Нет элемента .price вообще
                info['price'] = None
                self.log.debug("price_element_not_found", name=name)
        
        if price:
            info['price'] = price
            self.log.debug("price_extracted", name=name, price=price)
        
        # Извлекаем ссылку на товар
        # В mprofit.ru: <a href="..."> в .item-title
        link_elem = product_element.select_one('.item-title a')
        if link_elem and link_elem.get('href'):
            href = link_elem['href']
            # Делаем абсолютный URL если нужно
            if href.startswith('/'):
                href = self.base_url.rstrip('/') + href
            info['url'] = href
        
        return info

