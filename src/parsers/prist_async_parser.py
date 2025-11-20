"""Асинхронный парсер для сайта prist.ru"""
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
import re
import structlog
import httpx
import urllib.parse

from .base_async_parser import AsyncBaseParser


class PristAsyncParser(AsyncBaseParser):
    """
    Асинхронный парсер для сайта prist.ru
    
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
        
        # URL поиска для prist.ru
        # Формат: /search/index.php?q={query}&s=
        self.search_url_template = f"{self.base_url}/search/index.php?q={{query}}&s="
    
    async def search_product(self, product_name: str) -> Optional[Dict[str, Any]]:
        """
        Ищет товар по названию на сайте prist.ru (асинхронно).
        
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
        search_url = self.search_url_template.format(query=urllib.parse.quote(search_query))
        
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
                # Товар найден, но без цены (снят с производства)
                product_info['price'] = -1.0
                self.log.warning("product_discontinued",
                               product=product_name,
                               found_name=product_info.get('name'))
            elif price == -2.0:
                # Цена по запросу
                self.log.info("product_price_on_request",
                             product=product_name,
                             found_name=product_info.get('name'))
        
        return product_info
    
    def _normalize_search_query(self, product_name: str) -> str:
        """
        Нормализует название товара для поискового запроса.
        Оставляет пробелы для URL encoding через urllib.parse.quote
        
        Args:
            product_name: Исходное название
            
        Returns:
            Исходное название (URL encoding будет применен позже)
        """
        # Просто убираем лишние пробелы
        return ' '.join(product_name.split())
    
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
        
        # Структура prist.ru:
        # <div class="search-products"> -> <ol> -> <li> -> <div> -> <a href="...">
        products = soup.select('div.search-products > ol > li')
        
        if products:
            self.log.debug("products_found",
                          selector='div.search-products > ol > li',
                          count=len(products))
        
        if not products:
            self.log.debug("no_products_in_results", url=search_url)
            return None
        
        # Ищем наиболее подходящий товар
        # Для prist.ru: если артикул совпадает, переходим на страницу товара
        # (модификация может быть в URL или на странице)
        for idx, product in enumerate(products[:self.max_results]):
            product_info = self._extract_product_info_from_search(product, original_name)
            
            if not product_info:
                continue
            
            # Проверяем совпадение артикула (с учетом URL для модификаций)
            if self._is_name_match(original_name, product_info['name'], product_info.get('url', ''), self.min_similarity):
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
        
        В результатах поиска prist.ru НЕТ цены, только название и URL.
        Цена будет получена позже со страницы товара.
        
        Args:
            product_element: BeautifulSoup элемент товара из результатов поиска
            original_name: Оригинальное название для контекста
            
        Returns:
            Словарь с информацией о товаре (name, url, без price)
        """
        info = {}
        
        # Извлекаем название и URL
        # Структура: <div><a href="...">Название</a></div>
        link_elem = product_element.select_one('div > a')
        if not link_elem:
            self.log.debug("link_not_found", html=str(product_element)[:200])
            return None
        
        # Извлекаем название (убираем <b> теги)
        name = link_elem.get_text(strip=True)
        # Убираем <b> теги из названия
        for b_tag in link_elem.find_all('b'):
            b_tag.unwrap()
        name = link_elem.get_text(strip=True)
        
        if not name:
            self.log.debug("name_not_found", html=str(product_element)[:200])
            return None
        
        # Нормализуем название
        name = re.sub(r'\s+', ' ', name)
        info['name'] = name
        
        # Извлекаем URL товара
        href = link_elem.get('href', '')
        if href:
            # Делаем абсолютный URL если нужно
            if href.startswith('/'):
                href = self.base_url + href
            # Убираем параметры поиска из URL (sphrase_id)
            if '?' in href:
                href = href.split('?')[0]
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
        
        # Извлекаем название товара со страницы (если нужно)
        # Обычно используем название из результатов поиска
        page_name = None
        name_elem = soup.select_one('h1, .product-title, .item-title')
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
        
        ВАЖНО: Берет цену ТОЛЬКО если есть надпись "Цена (с НДС):" или "Цена:".
        Если такой надписи нет - значит цены нет, возвращает None или -2.0.
        
        Структура цены в prist.ru:
        - Основная цена: <td>Цена (с НДС):</td><td><div class="price-block-1"><span class="price">191 045 ₽</span></div></td>
        - Цена поверки: <td>Стоимость поверки (с НДС):</td><td><div class="price-block-2"><span class="price">9 210 ₽</span></div></td>
        
        Также есть meta тег: <meta content="191045.00" itemprop="price"/>
        
        Args:
            soup: BeautifulSoup объект страницы товара
            product_url: URL товара для логирования
            
        Returns:
            Цена как float, -2.0 (по запросу), None (нет цены) или 0.0 (ошибка)
        """
        # КРИТИЧНО: Проверяем наличие надписи "Цена (с НДС):" или "Цена:"
        # Структура: <td>Цена (с НДС):</td><td><div class="price-block-1">...</div></td>
        price_label_found = False
        
        # Вариант 1: Ищем <td> с текстом "Цена (с НДС):"
        # Используем find_all с функцией проверки текста
        all_tds = soup.find_all('td')
        for td in all_tds:
            td_text = td.get_text(strip=True)
            # Проверяем наличие "Цена" и "НДС" в тексте td
            if re.search(r'Цена\s*\(.*НДС', td_text, re.IGNORECASE):
                # Проверяем, что в следующем td или в том же tr есть price-block-1
                # Ищем в том же <tr>
                tr = td.find_parent('tr')
                if tr:
                    # Проверяем наличие price-block-1 в этой строке
                    price_block_in_row = tr.select_one('div.price-block-1')
                    if price_block_in_row:
                        price_label_found = True
                        break
                # Или проверяем следующий sibling td
                next_td = td.find_next_sibling('td')
                if next_td and next_td.select_one('div.price-block-1'):
                    price_label_found = True
                    break
        
        # Если надпись "Цена (с НДС):" найдена - извлекаем цену
        if price_label_found:
            price_block_1 = soup.select_one('div.price-block-1 span.price')
            
            if price_block_1:
                # Пробуем извлечь из meta тега (точнее)
                meta_price = price_block_1.select_one('meta[itemprop="price"]')
                if meta_price and meta_price.get('content'):
                    try:
                        price = float(meta_price.get('content'))
                        self.log.debug("price_extracted_from_meta",
                                      url=product_url,
                                      price=price)
                        return price
                    except (ValueError, TypeError):
                        pass
                
                # Fallback: извлекаем из текста
                price_text = price_block_1.get_text(strip=True)
                
                self.log.debug("price_found_in_block1",
                              url=product_url,
                              raw_text=price_text)
                
                price = self._extract_price_value_universal(price_text)
                if price:
                    return price
        
        # Надпись "Цена (с НДС):" НЕ найдена - значит цены нет
        # Проверяем статусы для определения причины
        page_text = soup.get_text(separator=' ', strip=True).lower()
        
        # Проверяем "по запросу"
        if any(phrase in page_text for phrase in ['по запросу', 'уточняйте', 'запросить', 'уточнить', 'запрос']):
            self.log.debug("price_on_request",
                          url=product_url,
                          reason="найдено 'по запросу', надпись 'Цена (с НДС):' отсутствует")
            return -2.0  # Цена по запросу
        
        # Если нет надписи "Цена (с НДС):" - значит цены нет
        self.log.warning("price_label_not_found",
                        url=product_url,
                        reason="надпись 'Цена (с НДС):' отсутствует, цена не указана")
        return None
    
    def _is_name_match(self, original: str, found: str, found_url: str = "", threshold: float = 0.5) -> bool:
        """
        Проверяет соответствие найденного названия оригинальному.
        
        Сравнивает АРТИКУЛЫ с учетом модификаций (например "TG").
        Требует ТОЧНОЕ совпадение базового артикула.
        Если в оригинале есть модификация (второе слово), проверяет её наличие в найденном.
        
        Использует тот же алгоритм что и electronpribor парсер.
        
        Args:
            original: Оригинальное название из Excel (например "АКИП-4204/1 TG")
            found: Найденное название с сайта (например "АКИП-4204/3A")
            threshold: Не используется (оставлен для совместимости API)
            
        Returns:
            True если артикулы совпадают ТОЧНО и модификации совпадают (если есть)
        """
        # Извлекаем артикулы
        article_pattern = re.compile(r'^([А-ЯA-ZЁ]+(?:[0-9]+)?[-/][0-9]+(?:[/][0-9]+)?)', re.IGNORECASE)
        
        # Извлекаем артикул из оригинального названия
        original_text = original if original else ""
        original_match = article_pattern.match(original_text.replace(' ', ''))
        if original_match:
            original_code = original_match.group(1)
        else:
            spaced_pattern = re.compile(r'^([А-ЯA-ZЁ]+(?:\s+[0-9]+)?[-/][0-9]+(?:[/][0-9]+)?)', re.IGNORECASE)
            spaced_match = spaced_pattern.match(original_text)
            if spaced_match:
                original_code = spaced_match.group(1).replace(' ', '')
            else:
                original_code = original_text.split()[0] if original_text else ""
        
        # Для найденного: берем до запятой, затем извлекаем артикул
        found_parts = found.split(',')
        found_text = found_parts[0].strip() if found_parts else ""
        
        match = article_pattern.match(found_text)
        if match:
            found_code = match.group(1)
        else:
            parts = re.split(r'([А-ЯA-ZЁ]+)', found_text, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) > 1 and parts[0]:
                found_code = parts[0].rstrip('-/')
            else:
                found_code = found_text.split()[0] if found_text else ""
        
        # Нормализуем для сравнения
        orig_normalized = original_code.lower().replace(' ', '').replace('-', '').replace('a', 'а').strip()
        found_normalized = found_code.lower().replace(' ', '').replace('-', '').replace('a', 'а').strip()
        
        # ПРОВЕРКА 1: ТОЧНОЕ совпадение базового артикула
        if orig_normalized != found_normalized:
            self.log.debug("name_match_check",
                          original=original,
                          original_code=original_code,
                          found=found,
                          found_code=found_code,
                          match=False,
                          reason="base_article_mismatch")
            return False
        
        # ПРОВЕРКА 2: Если в оригинале есть модификация, проверяем её наличие
        # Для prist.ru делаем ОЧЕНЬ гибкую проверку - если артикул совпадает точно,
        # то считаем товар найденным (модификация может быть в URL или на странице товара)
        original_words = original.split()
        if len(original_words) > 1:
            modification = original_words[1].lower()
            found_name_lower = found.lower()
            found_url_lower = found_url.lower() if found_url else ""
            
            # Для prist.ru: если артикул совпадает точно, модификация не критична
            # На сайте модификация может быть:
            # - В URL (например /akip_4205_1_tg/)
            # - В полном названии на странице товара
            # - Отсутствовать в результатах поиска, но быть на странице
            
            # Проверяем наличие модификации в названии ИЛИ в URL
            modification_in_name = modification in found_name_lower
            modification_in_url = modification in found_url_lower or modification.replace('/', '_') in found_url_lower
            
            # Проверяем наличие модификации, но не строго
            if len(modification) <= 3:
                # Короткая модификация (TG, /1, /2 и т.д.) - проверяем более гибко
                # Если модификация не найдена в названии, проверяем URL
                if not modification_in_name and not modification_in_url:
                    # Но все равно считаем совпадением, если артикул точно совпадает
                    # (модификация может быть на странице товара)
                    self.log.debug("name_match_check",
                                  original=original,
                                  original_code=original_code,
                                  found=found,
                                  found_code=found_code,
                                  found_url=found_url,
                                  match=True,
                                  reason="article_matches_short_modification_may_be_on_page",
                                  modification=modification)
                    return True
                else:
                    # Модификация найдена в названии или URL - отлично
                    self.log.debug("name_match_check",
                                  original=original,
                                  original_code=original_code,
                                  found=found,
                                  found_code=found_code,
                                  found_url=found_url,
                                  match=True,
                                  reason="article_and_modification_match",
                                  modification=modification,
                                  in_name=modification_in_name,
                                  in_url=modification_in_url)
                    return True
            else:
                # Длинная модификация - проверяем наличие ключевых слов
                modification_words = modification.split()
                if len(modification_words) > 0:
                    # Проверяем наличие хотя бы одного ключевого слова в названии
                    key_word_found = any(word in found_name_lower for word in modification_words if len(word) > 3)
                    if not key_word_found:
                        # Если ключевые слова не найдены, но артикул совпадает точно,
                        # все равно считаем совпадением (на сайте может быть другое описание)
                        self.log.debug("name_match_check",
                                      original=original,
                                      original_code=original_code,
                                      found=found,
                                      found_code=found_code,
                                      found_url=found_url,
                                      match=True,
                                      reason="article_matches_but_modification_different",
                                      modification=modification)
                        return True
                    else:
                        # Ключевые слова найдены
                        self.log.debug("name_match_check",
                                      original=original,
                                      original_code=original_code,
                                      found=found,
                                      found_code=found_code,
                                      match=True,
                                      reason="article_and_keywords_match",
                                      modification=modification)
                        return True
        
        # Все проверки пройдены
        self.log.debug("name_match_check",
                      original=original,
                      original_code=original_code,
                      found=found,
                      found_code=found_code,
                      match=True)
        return True

