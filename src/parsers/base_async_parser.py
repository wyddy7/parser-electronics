"""Асинхронный базовый класс для всех парсеров с httpx.AsyncClient и retry механизмом"""
import asyncio
import time
import httpx
import re
import urllib.parse
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
import structlog
from httpx import AsyncClient, Limits, Timeout


class AsyncBaseParser(ABC):
    """
    Асинхронный базовый класс для парсеров с поддержкой httpx.AsyncClient.
    
    Реализует best practices:
    - httpx.AsyncClient для асинхронных запросов
    - Connection pooling для переиспользования соединений
    - Retry механизм с exponential backoff
    - Rate limiting через asyncio.Semaphore
    - Таймауты на каждый запрос
    - Context manager для правильного закрытия
    """
    
    def __init__(self, config: Dict[str, Any], logger: structlog.BoundLogger):
        """
        Инициализация асинхронного парсера.
        
        Args:
            config: Конфигурация парсера из config.yaml
            logger: Сконфигурированный structlog logger
        """
        self.config = config
        self.base_url = config.get('base_url', '')
        self.timeout = config.get('timeout', 10)
        self.user_agent = config.get('user_agent', 
                                     'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # Настройки асинхронности
        async_config = config.get('async', {})
        self.max_concurrent = async_config.get('max_concurrent', 50)
        self.connection_pool_size = async_config.get('connection_pool_size', 100)
        self.request_delay = async_config.get('request_delay', 0.5)  # Задержка между запросами
        
        # Retry настройки
        retry_config = config.get('retry', {})
        self.retry_total = retry_config.get('total', 3)
        self.retry_backoff_factor = retry_config.get('backoff_factor', 0.3)
        self.retry_status_forcelist = retry_config.get('status_forcelist', [429, 500, 502, 503, 504])
        
        self.log = logger.bind(parser=self.__class__.__name__)
        self.client: Optional[AsyncClient] = None
        self.semaphore: Optional[asyncio.Semaphore] = None
        self.last_request_time = 0.0  # Для отслеживания времени последнего запроса
        
        self.log.info("async_parser_initialized",
                     base_url=self.base_url,
                     timeout=self.timeout,
                     max_concurrent=self.max_concurrent,
                     connection_pool_size=self.connection_pool_size,
                     request_delay=self.request_delay)
    
    async def _create_client(self) -> AsyncClient:
        """
        Создает httpx.AsyncClient с настройками connection pooling.
        
        Returns:
            Настроенный httpx.AsyncClient объект
        """
        # Настройки connection pooling
        limits = Limits(
            max_connections=self.connection_pool_size,
            max_keepalive_connections=20
        )
        
        # Настройки таймаута
        timeout = Timeout(
            connect=5.0,
            read=self.timeout,
            write=5.0,
            pool=5.0
        )
        
        # Создаем клиент с заголовками
        client = AsyncClient(
            base_url=self.base_url,
            limits=limits,
            timeout=timeout,
            headers={
                'User-Agent': self.user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
            },
            follow_redirects=True
        )
        
        self.log.debug("async_client_created",
                      max_connections=self.connection_pool_size,
                      timeout=self.timeout)
        
        return client
    
    async def _apply_delay(self):
        """Применяет задержку между запросами для снижения нагрузки на сервер"""
        if self.request_delay > 0 and self.last_request_time > 0:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.request_delay:
                sleep_time = self.request_delay - elapsed
                self.log.debug("applying_delay", sleep_seconds=sleep_time)
                await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    async def _make_request_with_retry(
        self, 
        url: str, 
        method: str = 'GET',
        **kwargs
    ) -> Optional[httpx.Response]:
        """
        Выполняет асинхронный HTTP запрос с retry механизмом.
        
        Args:
            url: URL для запроса
            method: HTTP метод (GET, POST, etc.)
            **kwargs: Дополнительные параметры для httpx
            
        Returns:
            Response объект или None в случае ошибки
        """
        # Применяем задержку между запросами
        await self._apply_delay()
        
        # Используем Semaphore для rate limiting
        if self.semaphore:
            async with self.semaphore:
                return await self._execute_request_with_retry(url, method, **kwargs)
        else:
            return await self._execute_request_with_retry(url, method, **kwargs)
    
    async def _execute_request_with_retry(
        self,
        url: str,
        method: str = 'GET',
        **kwargs
    ) -> Optional[httpx.Response]:
        """Внутренний метод для выполнения запроса с retry логикой"""
        last_exception = None
        
        for attempt in range(self.retry_total):
            try:
                self.log.debug("request_started",
                              url=url,
                              method=method,
                              attempt=attempt + 1,
                              max_attempts=self.retry_total)
                
                # Выполняем запрос
                response = await self.client.request(method, url, **kwargs)
                
                # Проверяем статус код
                if response.status_code in self.retry_status_forcelist:
                    # Нужен retry
                    if attempt < self.retry_total - 1:
                        wait_time = self.retry_backoff_factor * (2 ** attempt)
                        self.log.warning("retry_scheduled",
                                        url=url,
                                        status_code=response.status_code,
                                        attempt=attempt + 1,
                                        wait_time=wait_time)
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # Последняя попытка
                        self.log.error("request_failed_after_retries",
                                      url=url,
                                      status_code=response.status_code,
                                      attempts=self.retry_total)
                        return None
                
                # Успешный ответ
                response.raise_for_status()
                
                self.log.debug("request_successful",
                              url=url,
                              status_code=response.status_code,
                              content_length=len(response.content))
                
                return response
                
            except httpx.HTTPStatusError as e:
                last_exception = e
                if e.response.status_code in self.retry_status_forcelist:
                    if attempt < self.retry_total - 1:
                        wait_time = self.retry_backoff_factor * (2 ** attempt)
                        self.log.warning("http_error_retry",
                                        url=url,
                                        status_code=e.response.status_code,
                                        attempt=attempt + 1,
                                        wait_time=wait_time)
                        await asyncio.sleep(wait_time)
                        continue
                
                self.log.error("http_error",
                              url=url,
                              status_code=e.response.status_code if e.response else None,
                              error=str(e))
                return None
                
            except httpx.TimeoutException:
                last_exception = None
                if attempt < self.retry_total - 1:
                    wait_time = self.retry_backoff_factor * (2 ** attempt)
                    self.log.warning("timeout_retry",
                                    url=url,
                                    attempt=attempt + 1,
                                    wait_time=wait_time)
                    await asyncio.sleep(wait_time)
                    continue
                
                self.log.error("request_timeout",
                              url=url,
                              timeout=self.timeout)
                return None
                
            except httpx.ConnectError as e:
                last_exception = e
                if attempt < self.retry_total - 1:
                    wait_time = self.retry_backoff_factor * (2 ** attempt)
                    self.log.warning("connection_error_retry",
                                    url=url,
                                    attempt=attempt + 1,
                                    wait_time=wait_time)
                    await asyncio.sleep(wait_time)
                    continue
                
                self.log.error("connection_error",
                              url=url,
                              error=str(e))
                return None
                
            except Exception as e:
                last_exception = e
                self.log.error("request_failed",
                              url=url,
                              error=str(e),
                              error_type=type(e).__name__,
                              attempt=attempt + 1)
                if attempt < self.retry_total - 1:
                    wait_time = self.retry_backoff_factor * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
                return None
        
        # Все попытки исчерпаны
        if last_exception:
            self.log.error("request_failed_all_attempts",
                          url=url,
                          error=str(last_exception),
                          attempts=self.retry_total)
        return None
    
    def _extract_price_value_universal(self, price_text: str) -> Optional[float]:
        """
        Универсальное извлечение цены из текста.
        
        Обрабатывает:
        - Пробелы как разделители тысяч (5 530 руб.)
        - Неразрывные пробелы (&nbsp;, &#160;, \xa0)
        - Диапазоны цен (берет первую: 45 144 — 40 629 ₽)
        - Разные форматы валют (₽, руб., р.)
        - Форматы с НДС (23500 ₽ (с НДС))
        
        Args:
            price_text: Текст с ценой
            
        Returns:
            Цена как float или None
        """
        if not price_text:
            return None
        
        # Заменяем неразрывные пробелы на обычные
        price_text = price_text.replace('\xa0', ' ').replace('&nbsp;', ' ')
        price_text = price_text.replace('&#160;', ' ')
        
        # Обрабатываем диапазоны цен (берем первую цену)
        if '—' in price_text or ' - ' in price_text:
            price_text = re.split(r'[—\-]', price_text)[0]
        
        # Извлекаем число (убираем все кроме цифр, точек, запятых)
        cleaned = re.sub(r'[^\d,.]', '', price_text)
        
        # Заменяем запятую на точку
        cleaned = cleaned.replace(',', '.')
        
        # Обрабатываем множественные точки (оставляем только последнюю для десятичных)
        parts = cleaned.split('.')
        if len(parts) > 2:
            cleaned = ''.join(parts[:-1]) + '.' + parts[-1]
        
        try:
            price = float(cleaned)
            return price if price > 0 else None
        except ValueError:
            self.log.debug("price_parse_failed", text=price_text, cleaned=cleaned)
            return None
    
    def _detect_price_status(self, element_text: str) -> Optional[float]:
        """
        Определяет статус цены: реальная цена, по запросу (-2.0), снят (-1.0).
        
        Args:
            element_text: Текст элемента для проверки статуса
            
        Returns:
            float: -2.0 если "по запросу", -1.0 если "снят", None если статус не определен
        """
        if not element_text:
            return None
        
        text_lower = element_text.lower()
        
        # Проверка "по запросу"
        on_request_phrases = ['по запросу', 'уточняйте', 'запросить', 'уточнить', 'запрос']
        if any(phrase in text_lower for phrase in on_request_phrases):
            return -2.0
        
        # Проверка "снят"
        discontinued_phrases = ['снят', 'прекращена поставка', 'не производится']
        if any(phrase in text_lower for phrase in discontinued_phrases):
            return -1.0
        
        return None  # Статус не определен, пробуем извлечь цену
    
    def _normalize_search_query(self, product_name: str) -> str:
        """
        Нормализует название товара для поискового запроса.
        
        Базовая реализация:
        1. Обрезает после запятой (если есть)
        2. Убирает лишние пробелы
        
        Переопределяется в подклассах для специфичных случаев.
        
        Args:
            product_name: Исходное название товара
            
        Returns:
            Нормализованное название
        """
        # Обрезаем после запятой
        if ',' in product_name:
            product_name = product_name.split(',')[0].strip()
        
        # Убираем лишние пробелы
        return ' '.join(product_name.split())
    
    def _is_name_match(self, original: str, found: str, found_url: str = "", threshold: float = 0.5) -> bool:
        """
        Проверяет соответствие найденного названия оригинальному.
        
        Сравнивает АРТИКУЛЫ с учетом модификаций (например "TG").
        Требует ТОЧНОЕ совпадение базового артикула.
        Если в оригинале есть модификация (второе слово), проверяет её наличие в найденном.
        
        Args:
            original: Оригинальное название из Excel (например "АКИП-4204/1 TG")
            found: Найденное название с сайта (например "АКИП-4204/1, анализатор спектра")
            found_url: URL найденного товара (для специфичных случаев, например prist)
            threshold: Не используется (оставлен для совместимости API)
            
        Returns:
            True если артикулы совпадают ТОЧНО и модификации совпадают (если есть)
        """
        # Извлекаем артикулы
        # Артикул может быть в формате:
        # - "АКИП-3404" (буквы-цифры)
        # - "АКИП-3404/1" (буквы-цифры/цифра)
        # - "В7-78/2" (буква+цифра-цифры/цифра)
        # - "Е6-32" (буква+цифра-цифры)
        # - "АКИП 9806/3" (буквы пробел цифры/цифра)
        # - "Fluke T90" (бренд пробел модель)
        # Паттерн: (буквы ИЛИ буква+цифра) + дефис + цифры + возможно слэш+цифра
        article_pattern = re.compile(r'^([А-ЯA-ZЁ]+(?:[0-9]+)?[-/][0-9]+(?:[/][0-9]+)?)', re.IGNORECASE)
        
        # Извлекаем артикул из оригинального названия
        original_text = original if original else ""
        
        # Специальная обработка для Fluke: "Fluke T90" → "FlukeT90"
        if original_text.startswith('Fluke'):
            fluke_match = re.match(r'(Fluke\s+[A-Za-z0-9+/\-]+)', original_text, re.IGNORECASE)
            if fluke_match:
                original_code = fluke_match.group(1).replace(' ', '')  # "Fluke T90" → "FlukeT90"
            else:
                # Fallback: первое слово
                original_code = original_text.split()[0] if original_text else ""
        else:
            # Обычная обработка для других артикулов
            original_match = article_pattern.match(original_text.replace(' ', ''))
            if original_match:
                original_code = original_match.group(1)
            else:
                # Если не нашли, пробуем найти артикул с пробелом и дефисом/слэшем (АКИП 9806/3)
                spaced_pattern = re.compile(r'^([А-ЯA-ZЁ]+(?:\s+[A-Za-z0-9]+)?[-/][0-9]+(?:[/][0-9]+)?)', re.IGNORECASE)
                spaced_match = spaced_pattern.match(original_text)
                if spaced_match:
                    original_code = spaced_match.group(1).replace(' ', '')
                else:
                    # Паттерн для артикулов с пробелом БЕЗ дефиса/слэша (Agilent E4418B, HIOKI 3390)
                    brand_model_pattern = re.compile(r'^([А-ЯA-ZЁ]+\s+[A-Za-z0-9]+)', re.IGNORECASE)
                    brand_model_match = brand_model_pattern.match(original_text)
                    if brand_model_match:
                        original_code = brand_model_match.group(1)
                    else:
                        # Fallback: первое слово
                        original_code = original_text.split()[0] if original_text else ""
        
        # Для найденного: берем до запятой, затем извлекаем артикул по паттерну
        found_parts = found.split(',')
        found_text = found_parts[0].strip() if found_parts else ""
        # Убираем скобки и их содержимое (например, "(демонстрационный)")
        found_text = re.sub(r'\([^)]*\)', '', found_text).strip()
        
        # Специальная обработка для Fluke в найденном тексте
        if found_text.startswith('Fluke'):
            fluke_match = re.match(r'(Fluke\s+[A-Za-z0-9+/\-]+)', found_text, re.IGNORECASE)
            if fluke_match:
                found_code = fluke_match.group(1).replace(' ', '')  # "Fluke T90" → "FlukeT90"
            else:
                found_code = found_text.split()[0] if found_text else ""
        else:
            # Извлекаем артикул из найденного текста по паттерну
            # Используем search() вместо match(), так как артикул может быть в середине строки
            # Например: "Указатель правильности чередования фаз CEM DT-902"
            # Создаем паттерн БЕЗ ^ для поиска в любом месте строки
            
            # Паттерн 1: артикулы с дефисом/слэшем (DT-902, АКИП-2502)
            article_search_pattern = re.compile(r'([А-ЯA-ZЁ]+(?:[0-9]+)?[-/][0-9]+(?:[/][0-9]+)?)', re.IGNORECASE)
            match = article_search_pattern.search(found_text)
            if match:
                found_code = match.group(1)
            else:
                # Паттерн 2: артикулы с пробелом и дефисом/слэшем (АКИП 9806/3)
                spaced_pattern = re.compile(r'([А-ЯA-ZЁ]+(?:\s+[A-Za-z0-9]+)?[-/][0-9]+(?:[/][0-9]+)?)', re.IGNORECASE)
                spaced_match = spaced_pattern.search(found_text)
                if spaced_match:
                    found_code = spaced_match.group(1).replace(' ', '')
                else:
                    # Паттерн 3: артикулы с пробелом БЕЗ дефиса/слэша (Agilent E4418B, HIOKI 3390)
                    # Ищем артикул в конце строки (обычно он там находится)
                    # Формат: буквы + пробел + буквы/цифры (модель)
                    words = found_text.split()
                    if len(words) >= 2:
                        # Проверяем последние 2 слова как потенциальный артикул
                        last_two = ' '.join(words[-2:])
                        # Паттерн: первое слово - буквы (бренд), второе - буквы/цифры (модель)
                        brand_model_pattern = re.compile(r'^([A-ZА-ЯЁ][A-ZА-ЯЁa-zа-я0-9]*\s+[A-Za-z0-9]+)', re.IGNORECASE)
                        if brand_model_pattern.match(last_two):
                            found_code = last_two
                        else:
                            # Пробуем найти артикул в любом месте строки
                            brand_model_pattern = re.compile(r'([A-ZА-ЯЁ][A-ZА-ЯЁa-zа-я0-9]*\s+[A-Za-z0-9]+)', re.IGNORECASE)
                            all_matches = brand_model_pattern.findall(found_text)
                            if all_matches:
                                found_code = all_matches[-1]  # Берем последнее совпадение
                            else:
                                found_code = found_text.split()[0] if found_text else ""
                    else:
                        # Fallback: первое слово
                        found_code = found_text.split()[0] if found_text else ""
        
        # Нормализуем для сравнения (нижний регистр, убираем ВСЕ пробелы и дефисы)
        # Также заменяем латинскую A на кириллическую А для унификации
        orig_normalized = original_code.lower().replace(' ', '').replace('-', '').replace('a', 'а').strip()
        found_normalized = found_code.lower().replace(' ', '').replace('-', '').replace('a', 'а').strip()
        
        # ПРОВЕРКА 1: ТОЧНОЕ совпадение базового артикула
        if orig_normalized != found_normalized:
            self.log.debug("name_match_check",
                          original=original,
                          original_code=original_code,
                          orig_normalized=orig_normalized,
                          found=found,
                          found_code=found_code,
                          found_normalized=found_normalized,
                          match=False,
                          reason="base_article_mismatch")
            return False
        
        # ПРОВЕРКА 2: Если в оригинале есть модификация (второе слово), проверяем её наличие
        original_words = original.split()
        if len(original_words) > 1:
            # Есть модификация (например "TG", "без трекинг генератора" и т.д.)
            modification = original_words[1].lower().rstrip(',')  # Убираем запятую
            
            # Проверяем, является ли второе слово частью артикула
            # Нормализуем артикулы для сравнения (убираем пробелы, дефисы, приводим к нижнему регистру)
            original_code_normalized = original_code.lower().replace(' ', '').replace('-', '').replace('a', 'а')
            found_code_normalized = found_code.lower().replace(' ', '').replace('-', '').replace('a', 'а')
            
            # Если второе слово является частью извлеченного артикула - это не модификация, пропускаем проверку
            if modification in original_code_normalized:
                # Это часть артикула, не модификация - пропускаем проверку
                self.log.info("name_match_check",
                              original=original,
                              original_code=original_code,
                              original_code_normalized=original_code_normalized,
                              found=found,
                              found_code=found_code,
                              found_code_normalized=found_code_normalized,
                              match=True,
                              reason="modification_is_part_of_article",
                              modification=modification)
                return True
            
            # Если модификация короткая (1-3 символа) и является частью найденного артикула - пропускаем проверку
            if len(modification) <= 3 and modification.isalnum():
                if modification in found_code_normalized:
                    # Это часть артикула, не модификация - пропускаем проверку
                    self.log.debug("name_match_check",
                                  original=original,
                                  original_code=original_code,
                                  found=found,
                                  found_code=found_code,
                                  match=True,
                                  reason="modification_is_part_of_article",
                                  modification=modification)
                    return True
            
            # Проверяем наличие модификации в найденном названии (без запятой)
            found_name_lower = found.lower().replace(',', '')
            if modification not in found_name_lower:
                # Модификация не найдена - это другой товар
                self.log.info("name_match_check",
                              original=original,
                              original_code=original_code,
                              found=found,
                              found_code=found_code,
                              match=False,
                              reason="modification_mismatch",
                              modification=modification,
                              found_name_lower=found_name_lower)
                return False
        
        # Все проверки пройдены
        self.log.debug("name_match_check",
                      original=original,
                      original_code=original_code,
                      found=found,
                      found_code=found_code,
                      match=True)
        return True
    
    @abstractmethod
    async def search_product(self, product_name: str) -> Optional[Dict[str, Any]]:
        """
        Поиск товара по названию (абстрактный async метод).
        
        Args:
            product_name: Название товара для поиска
            
        Returns:
            Словарь с информацией о товаре или None если не найден
        """
        raise NotImplementedError("Метод search_product должен быть реализован в подклассе")
    
    async def __aenter__(self):
        """Async context manager вход"""
        self.client = await self._create_client()
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager выход"""
        if self.client:
            await self.client.aclose()
            self.log.debug("async_client_closed")
        return False

