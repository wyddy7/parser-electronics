"""Асинхронный базовый класс для всех парсеров с httpx.AsyncClient и retry механизмом"""
import asyncio
import time
import httpx
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

