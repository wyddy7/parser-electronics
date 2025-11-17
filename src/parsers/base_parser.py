"""Базовый класс для всех парсеров с Session и retry механизмом"""
import time
import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
import structlog


class BaseParser(ABC):
    """
    Базовый класс для парсеров с поддержкой Session и retry.
    
    Реализует best practices из Context7:
    - requests.Session для переиспользования соединений
    - HTTPAdapter с Retry для устойчивости
    - Таймауты на каждый запрос
    - Context manager для правильного закрытия
    """
    
    def __init__(self, config: Dict[str, Any], logger: structlog.BoundLogger):
        """
        Инициализация парсера.
        
        Args:
            config: Конфигурация парсера из config.yaml
            logger: Сконфигурированный structlog logger
        """
        self.config = config
        self.base_url = config.get('base_url', '')
        self.timeout = config.get('timeout', 10)
        self.delay = config.get('delays', {}).get('between_requests', 1.5)
        self.user_agent = config.get('user_agent', 
                                     'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        self.log = logger.bind(parser=self.__class__.__name__)
        self.session = self._create_session()
        self.last_request_time = 0
        
        self.log.info("parser_initialized",
                     base_url=self.base_url,
                     timeout=self.timeout,
                     delay=self.delay)
    
    def _create_session(self) -> requests.Session:
        """
        Создает Session с настройками retry и adapter.
        
        Returns:
            Настроенный requests.Session объект
        """
        session = requests.Session()
        
        # Настраиваем retry механизм
        retry_config = self.config.get('retry', {})
        retries = Retry(
            total=retry_config.get('total', 3),
            backoff_factor=retry_config.get('backoff_factor', 0.3),
            status_forcelist=retry_config.get('status_forcelist', [429, 500, 502, 503, 504]),
            allowed_methods=['GET', 'POST', 'HEAD']  # Методы для retry
        )
        
        # Создаем adapter и монтируем его для http и https
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        
        # Устанавливаем заголовки
        session.headers.update({
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        
        self.log.debug("session_created",
                      retry_total=retry_config.get('total', 3),
                      backoff_factor=retry_config.get('backoff_factor', 0.3))
        
        return session
    
    def _apply_delay(self):
        """Применяет задержку между запросами"""
        if self.last_request_time > 0:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.delay:
                sleep_time = self.delay - elapsed
                self.log.debug("applying_delay", sleep_seconds=sleep_time)
                time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _make_request(self, url: str, method: str = 'GET', **kwargs) -> Optional[requests.Response]:
        """
        Выполняет HTTP запрос с обработкой ошибок.
        
        Args:
            url: URL для запроса
            method: HTTP метод (GET, POST, etc.)
            **kwargs: Дополнительные параметры для requests
            
        Returns:
            Response объект или None в случае ошибки
        """
        self._apply_delay()
        
        # Устанавливаем timeout если не указан
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        
        self.log.debug("request_started",
                      url=url,
                      method=method,
                      timeout=kwargs['timeout'])
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            
            self.log.debug("request_successful",
                          url=url,
                          status_code=response.status_code,
                          content_length=len(response.content))
            
            return response
            
        except requests.exceptions.HTTPError as e:
            self.log.error("http_error",
                          url=url,
                          status_code=e.response.status_code if e.response else None,
                          error=str(e))
            return None
            
        except requests.exceptions.Timeout:
            self.log.error("request_timeout",
                          url=url,
                          timeout=kwargs['timeout'])
            return None
            
        except requests.exceptions.ConnectionError as e:
            self.log.error("connection_error",
                          url=url,
                          error=str(e))
            return None
            
        except Exception as e:
            self.log.error("request_failed",
                          url=url,
                          error=str(e),
                          error_type=type(e).__name__)
            return None
    
    @abstractmethod
    def search_product(self, product_name: str) -> Optional[Dict[str, Any]]:
        """
        Поиск товара по названию (абстрактный метод).
        
        Args:
            product_name: Название товара для поиска
            
        Returns:
            Словарь с информацией о товаре или None если не найден
        """
        raise NotImplementedError("Метод search_product должен быть реализован в подклассе")
    
    def close(self):
        """Закрывает сессию и освобождает ресурсы"""
        if self.session:
            self.session.close()
            self.log.debug("session_closed")
    
    def __enter__(self):
        """Context manager вход"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager выход"""
        self.close()
        return False

