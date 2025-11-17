# Price Aggregator for Measurement Equipment Retailers
## Complete Technical Architecture & Implementation Plan

---

## EXECUTIVE SUMMARY

**Project Goal:** Extract and aggregate product prices from `electronpribor.ru` and `prist.ru` (measurement equipment retailers)

**Scope:** 2 websites, estimated 50-200 products per site, mixed data formats

**Timeline:** ~1 week development + maintenance

**Complexity Level:** LOW-MEDIUM (straightforward HTML parsing, no heavy JavaScript rendering)

---

## 📋 PHASE 1: DEDUCTIVE SITE ANALYSIS

### 1.1 ELECTRONPRIBOR.RU - Detailed Findings

**URL Pattern:** `https://www.electronpribor.ru/`

**Site Architecture:**
```
├── Homepage (main listing)
│   ├── Product grid/list (AJAX-loaded or paginated)
│   ├── Product cards with: name, price, availability
│   └── Likely search/filter functionality
└── Individual product pages (optional)
    └── Detailed specs
```

**Data Extraction Points:**
- **Product Name:** `"Е6-32, цифровой мегаомметр"`
- **Price:** `47 910 ₽` (numeric + currency symbol)
- **Availability:** `в наличии` (in stock) OR `поступление 11.01.2026 г.` (arriving on date)
- **Status:** Varies from "в наличии" to "Цена по запросу"

**Expected Behavior:**
```
✅ POSITIVE:
  - Prices visible in HTML (no JavaScript rendering needed for basic data)
  - Clear structure: product name + price + availability
  - Consistent price format (number + space + ₽)

⚠️  CHALLENGES:
  - May use AJAX for pagination
  - Availability field has variable format (dates must be parsed)
  - Some products show "Цена по запросу" (no numeric price)
  - Duplicate listings (seen in provided content)
```

**Anti-Scraping Assessment:**
- No robots.txt blocking observed
- No evident rate limiting signals in provided data
- No JavaScript required to render prices
- **Risk Level:** LOW

---

### 1.2 PRIST.RU - Detailed Findings

**URL Pattern:** `https://prist.ru/` (complex multi-page site)

**Site Architecture:**
```
├── Homepage (news, featured products)
├── Product catalog
│   ├── Category pages (manufacturers like Keysight, Fluke, etc.)
│   ├── Product listing pages (pagination-based)
│   └── Individual product pages
│       ├── HTML price
│       ├── Availability status
│       ├── PDF specifications
│       └── Service information (calibration)
└── Service pages (calibration pricing tables)
    └── PDF price lists
```

**Data Extraction Points:**
```
Primary: Product pages
├── Name: "MET/CAL-METCON"
├── Brand: "Fluke"
├── Price: "Нет в наличии" OR "Цена по запросу" OR numeric price
├── Availability: "Нет в наличии" OR "поступление"
└── PDF specs: Links to PDFs with detailed info

Secondary: Calibration service page
└── Price list PDF with service rates (e.g., "2820 руб." for multimeters)
```

**Expected Behavior:**
```
✅ POSITIVE:
  - Product information structured in HTML tables/lists
  - URLs follow predictable pattern (likely /product/ or /catalog/)
  - Existing price list PDFs hint at structured data

⚠️  CHALLENGES:
  - Complex site structure (services + products mixed)
  - Many products show "Цена по запросу" (requires manual lookup)
  - Product pages may be individually rendered
  - PDF extraction needed for some price lists
  - Navigation URLs need to be crawled to find all products
```

**Anti-Scraping Assessment:**
- More sophisticated site structure suggests some scraping awareness
- Likely has robots.txt restrictions
- Possibly rate limiting on individual product pages
- **Risk Level:** MEDIUM

---

## 📐 PHASE 2: TECHNOLOGY STACK SELECTION

### 2.1 Stack Architecture

```
Data Flow:
┌─────────────────┐
│  Web Scraper    │ (Requests + BeautifulSoup4 for static HTML)
│  Core Module    │
└────────┬────────┘
         │
         ↓
┌─────────────────────────┐
│  Data Parser & Cleaner  │ (Regex, datetime parsing)
│  Edge Case Handler      │
└────────┬────────────────┘
         │
         ↓
┌─────────────────────────┐
│  Data Validator         │ (Pydantic models)
│  Deduplication          │
└────────┬────────────────┘
         │
         ↓
┌─────────────────────────┐
│  Storage Layer          │ (JSON/CSV export + optional DB)
│  (CSV/JSON/SQLite)      │
└────────┬────────────────┘
         │
         ↓
┌─────────────────────────┐
│  CLI/API Interface      │ (Python Click for CLI)
│  Scheduling (Cron)      │
└─────────────────────────┘
```

### 2.2 Tool Selection & Justification

| Component | Choice | Why | Alternative |
|-----------|--------|-----|-------------|
| **HTTP Requests** | `requests` | Simple, synchronous, suitable for 2 sites | httpx, urllib3 |
| **HTML Parsing** | `BeautifulSoup4` | Best for static HTML, mature, easy CSS selectors | lxml, parsel |
| **Data Validation** | `pydantic` | Type-safe, automatic validation, great errors | marshmallow, dataclasses |
| **Price Extraction** | `regex` + `pymorphy2` | Russian text parsing for rubles | custom parser |
| **Date Parsing** | `dateparser` | Handles Russian dates ("11.01.2026 г.") | datetime, pendulum |
| **CSV/JSON** | `pandas` (CSV) + `json` (JSON) | Mature, performant, built-in | csv module, ujson |
| **CLI** | `click` | Easy command-line args, auto-help | argparse, typer |
| **Scheduling** | `APScheduler` | Flexible, easy to test | cron, celery |
| **Testing** | `pytest` + `pytest-vcr` | Record HTTP responses, deterministic tests | unittest, mock |
| **Environment** | `python-dotenv` | Safe credential management | os.getenv() |

**Why NOT Scrapy?** Too heavyweight for 2 sites, adds complexity. Better for 20+ sites.
**Why NOT Playwright?** Unnecessary - no JavaScript rendering needed based on findings.
**Why NOT MCP?** Overkill - full control needed for production-grade scraper.

### 2.3 Project Structure

```
price-aggregator/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── setup.py
│
├── config/
│   ├── __init__.py
│   ├── settings.py              # Configuration management
│   ├── sites.yaml               # Site-specific selectors & URLs
│   └── logging_config.py        # Structured logging setup
│
├── scrapers/
│   ├── __init__.py
│   ├── base.py                  # Abstract scraper class
│   ├── electronpribor.py        # electronpribor.ru implementation
│   ├── prist.py                 # prist.ru implementation
│   └── utils.py                 # Shared utilities (headers, retry logic)
│
├── models/
│   ├── __init__.py
│   ├── product.py               # Pydantic models for validation
│   └── exceptions.py            # Custom exceptions
│
├── processors/
│   ├── __init__.py
│   ├── price_parser.py          # Price extraction & parsing
│   ├── date_parser.py           # Russian date parsing
│   ├── cleaner.py               # Data normalization
│   └── deduplicator.py          # Cross-site duplicate detection
│
├── storage/
│   ├── __init__.py
│   ├── csv_writer.py            # CSV export
│   ├── json_writer.py           # JSON export
│   └── sqlite_adapter.py        # Optional SQLite storage
│
├── cli/
│   ├── __init__.py
│   └── main.py                  # Click CLI commands
│
├── scheduler/
│   ├── __init__.py
│   └── jobs.py                  # APScheduler job definitions
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # pytest fixtures
│   ├── test_scrapers.py         # Scraper unit tests with VCR
│   ├── test_processors.py       # Parser/cleaner tests
│   ├── test_models.py           # Validation tests
│   └── cassettes/               # VCR HTTP recordings (git-tracked)
│
├── logs/
│   └── .gitkeep
│
└── data/
    ├── output/                  # CSV/JSON exports
    │   └── .gitkeep
    └── .gitkeep
```

---

## 🛠️ PHASE 3: DETAILED IMPLEMENTATION PLAN

### 3.1 Step 1: Project Setup & Configuration

**File: `requirements.txt`**
```
requests==2.31.0           # HTTP requests
beautifulsoup4==4.12.2     # HTML parsing
pydantic==2.5.0            # Data validation
python-dotenv==1.0.0       # Environment variables
dateparser==1.1.8          # Date parsing (handles Russian)
pymorphy2==0.9.7           # Russian morphology (optional)
pandas==2.1.3              # CSV handling
click==8.1.7               # CLI
APScheduler==3.10.4        # Task scheduling
pyyaml==6.0                # Config files
loguru==0.7.2              # Advanced logging
pytest==7.4.3              # Testing
pytest-vcr==1.0.2          # Record HTTP responses
requests-mock==1.11.0      # Mock HTTP responses
```

**File: `config/settings.py`**
```python
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # Scraper settings
    REQUEST_TIMEOUT: int = 15
    RETRY_ATTEMPTS: int = 3
    RETRY_DELAY: int = 2
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    
    # Rate limiting
    REQUEST_DELAY: float = 0.5  # Seconds between requests
    
    # Storage
    OUTPUT_DIR: Path = Path("data/output")
    LOG_DIR: Path = Path("logs")
    
    # Scheduling
    SCHEDULE_INTERVAL_HOURS: int = 24
    
    class Config:
        env_file = ".env"

settings = Settings()
```

**File: `config/sites.yaml`**
```yaml
sites:
  electronpribor:
    base_url: "https://www.electronpribor.ru"
    selectors:
      products: "div.product"  # CSS selector for product cards
      name: "h4.product-name"
      price: "span.price"
      availability: "span.stock"
    pagination:
      type: "ajax"  # or "url_based"
      next_button: "a.next"
    rate_limit_delay: 1.0

  prist:
    base_url: "https://prist.ru"
    selectors:
      products: "div.product-item"
      name: "a.product-link"
      price: "span.price, span.priceText"
      availability: "span.availability"
    pagination:
      type: "url_based"
      pattern: "/catalog/?page={page}"
    rate_limit_delay: 2.0
```

### 3.2 Step 2: Data Models (Pydantic)

**File: `models/product.py`**
```python
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
from enum import Enum

class AvailabilityStatus(str, Enum):
    IN_STOCK = "в наличии"
    PRE_ORDER = "поступление"
    OUT_OF_STOCK = "нет в наличии"
    REQUEST_PRICE = "цена по запросу"
    UNKNOWN = "неизвестно"

class Product(BaseModel):
    site: str                           # Source site (electronpribor, prist)
    name: str                           # Product name/model
    brand: Optional[str] = None         # Manufacturer (Fluke, Keysight, etc.)
    price: Optional[float] = None       # Price in rubles (None if "по запросу")
    currency: str = "RUB"
    availability: AvailabilityStatus    # Current availability
    availability_date: Optional[datetime] = None  # Expected date if pre-order
    url: str                            # Product page URL
    scraped_at: datetime                # When data was collected
    raw_price_text: Optional[str] = None  # Original price string for debugging
    notes: Optional[str] = None         # Substitutions, replacements, etc.
    
    @field_validator('price')
    def validate_price(cls, v):
        if v is not None and v < 0:
            raise ValueError("Price cannot be negative")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "site": "electronpribor",
                "name": "Е6-32, цифровой мегаомметр",
                "brand": "ЭЛЕКТРОНПРИБОР",
                "price": 47910.0,
                "availability": "в наличии",
                "url": "https://www.electronpribor.ru/...",
                "scraped_at": "2025-11-16T23:45:00"
            }
        }
```

### 3.3 Step 3: Price & Date Parsers

**File: `processors/price_parser.py`**
```python
import re
from typing import Optional, Tuple

class PriceParser:
    """Extract and validate prices from Russian text."""
    
    # Regex patterns
    PRICE_PATTERN = re.compile(r'(\d{1,3}(?:\s\d{3})*)\s*₽')
    PRICE_ON_REQUEST = re.compile(r'(цена\s+по\s+запросу|по\s+запросу)', re.IGNORECASE)
    
    @staticmethod
    def parse_price(text: str) -> Optional[float]:
        """
        Parse price from text like "47 910 ₽" or "Цена по запросу"
        
        Returns:
            float: Numeric price in rubles, or None if "по запросу"
        """
        if not text or not isinstance(text, str):
            return None
        
        text = text.strip()
        
        # Check if it's "по запросу"
        if PriceParser.PRICE_ON_REQUEST.search(text):
            return None
        
        # Extract price
        match = PriceParser.PRICE_PATTERN.search(text)
        if match:
            price_str = match.group(1).replace('\s', '').replace(' ', '')
            try:
                return float(price_str)
            except ValueError:
                return None
        
        return None
    
    @staticmethod
    def parse_price_with_status(text: str) -> Tuple[Optional[float], str]:
        """Return (price, raw_text) for debugging."""
        price = PriceParser.parse_price(text)
        return price, text
```

**File: `processors/date_parser.py`**
```python
from datetime import datetime
import re
from typing import Optional
import dateparser

class RussianDateParser:
    """Parse Russian date formats like 'поступление 11.01.2026 г.'"""
    
    MONTHS_RU = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
        'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
        'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
    }
    
    @staticmethod
    def parse_date(text: str) -> Optional[datetime]:
        """
        Parse dates like:
        - "поступление 11.01.2026 г."
        - "11 января 2026 г."
        - "11.01.2026"
        """
        if not text:
            return None
        
        # Try standard dateparser (handles Russian months)
        parsed = dateparser.parse(text, languages=['ru'])
        return parsed
    
    @staticmethod
    def extract_availability_date(text: str) -> Optional[datetime]:
        """Extract date from availability text."""
        # Pattern: "поступление 11.01.2026 г." -> extract date
        match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})', text)
        if match:
            return RussianDateParser.parse_date(match.group(1))
        return None
```

### 3.4 Step 4: Base Scraper Class

**File: `scrapers/base.py`**
```python
from abc import ABC, abstractmethod
from typing import List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from models.product import Product, AvailabilityStatus
from loguru import logger
import time

class BaseScraper(ABC):
    """Abstract base class for all scrapers."""
    
    def __init__(self, site_name: str, base_url: str, delay: float = 0.5):
        self.site_name = site_name
        self.base_url = base_url
        self.delay = delay
        self.session = self._create_session()
        
    def _create_session(self) -> requests.Session:
        """Create session with retry strategy."""
        session = requests.Session()
        
        # Retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })
        
        return session
    
    @abstractmethod
    def scrape(self) -> List[Product]:
        """Main scraping method. Must be implemented by subclasses."""
        pass
    
    def _fetch_page(self, url: str, timeout: int = 15) -> Optional[str]:
        """Fetch page with error handling."""
        try:
            time.sleep(self.delay)  # Rate limiting
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None
    
    def close(self):
        """Close session."""
        self.session.close()
```

### 3.5 Step 5: Site-Specific Scrapers

**File: `scrapers/electronpribor.py`**
```python
from scrapers.base import BaseScraper
from models.product import Product, AvailabilityStatus
from processors.price_parser import PriceParser
from processors.date_parser import RussianDateParser
from typing import List
from bs4 import BeautifulSoup
from datetime import datetime
from loguru import logger

class ElectronPriborScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            site_name="electronpribor",
            base_url="https://www.electronpribor.ru",
            delay=1.0
        )
    
    def scrape(self) -> List[Product]:
        """Scrape all products from electronpribor.ru"""
        logger.info("Starting ElectronPribor scraper")
        products = []
        
        # Fetch main page
        html = self._fetch_page(self.base_url)
        if not html:
            return products
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract products (adjust selector based on actual HTML)
        # From analysis: products are in cards with name, price, availability
        product_elements = soup.find_all('div', class_=['product', 'item', 'card'])
        
        logger.info(f"Found {len(product_elements)} products on page")
        
        for element in product_elements:
            try:
                product = self._parse_product(element)
                if product:
                    products.append(product)
            except Exception as e:
                logger.error(f"Error parsing product: {e}")
                continue
        
        return products
    
    def _parse_product(self, element) -> Product:
        """Parse single product element."""
        # Extract fields (selectors may need adjustment)
        name_elem = element.find('h4', class_='product-name') or element.find('a')
        price_elem = element.find('span', class_='price')
        avail_elem = element.find('span', class_=['stock', 'availability'])
        
        name = name_elem.get_text(strip=True) if name_elem else "Unknown"
        price_text = price_elem.get_text(strip=True) if price_elem else ""
        avail_text = avail_elem.get_text(strip=True) if avail_elem else ""
        
        # Parse price
        price = PriceParser.parse_price(price_text)
        
        # Parse availability
        availability, avail_date = self._parse_availability(avail_text)
        
        # Extract URL
        url = element.find('a')
        url = url['href'] if url and url.get('href') else self.base_url
        if not url.startswith('http'):
            url = self.base_url + url
        
        return Product(
            site=self.site_name,
            name=name,
            price=price,
            availability=availability,
            availability_date=avail_date,
            url=url,
            scraped_at=datetime.now(),
            raw_price_text=price_text
        )
    
    def _parse_availability(self, text: str) -> tuple:
        """Parse availability status and date."""
        text_lower = text.lower()
        
        if 'в наличии' in text_lower:
            return AvailabilityStatus.IN_STOCK, None
        elif 'поступление' in text_lower:
            date = RussianDateParser.extract_availability_date(text)
            return AvailabilityStatus.PRE_ORDER, date
        elif 'нет' in text_lower or 'недоступно' in text_lower:
            return AvailabilityStatus.OUT_OF_STOCK, None
        elif 'запрос' in text_lower or 'по запросу' in text_lower:
            return AvailabilityStatus.REQUEST_PRICE, None
        else:
            return AvailabilityStatus.UNKNOWN, None
```

**File: `scrapers/prist.py`**
```python
from scrapers.base import BaseScraper
from models.product import Product, AvailabilityStatus
from processors.price_parser import PriceParser
from processors.date_parser import RussianDateParser
from typing import List
from bs4 import BeautifulSoup
from datetime import datetime
from loguru import logger
import re

class PristScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            site_name="prist",
            base_url="https://prist.ru",
            delay=2.0  # Longer delay due to medium anti-scraping
        )
    
    def scrape(self) -> List[Product]:
        """Scrape products from prist.ru catalog."""
        logger.info("Starting Prist scraper")
        products = []
        
        # Start from catalog page
        # May need to discover catalog URL structure first
        catalog_url = f"{self.base_url}/catalog/"
        
        # Implement pagination
        page = 1
        while True:
            url = f"{catalog_url}?page={page}"
            html = self._fetch_page(url)
            
            if not html:
                break
            
            soup = BeautifulSoup(html, 'html.parser')
            product_elements = soup.find_all('div', class_=['product', 'item'])
            
            if not product_elements:
                break  # No more products
            
            logger.info(f"Page {page}: Found {len(product_elements)} products")
            
            for element in product_elements:
                try:
                    product = self._parse_product(element)
                    if product:
                        products.append(product)
                except Exception as e:
                    logger.error(f"Error parsing product: {e}")
                    continue
            
            page += 1
        
        return products
    
    def _parse_product(self, element) -> Product:
        """Parse single product from prist.ru."""
        # Extract basic info
        link_elem = element.find('a')
        if not link_elem:
            return None
        
        name = link_elem.get_text(strip=True)
        url = link_elem.get('href', '')
        if not url.startswith('http'):
            url = self.base_url + url
        
        # Extract price and availability
        price_elem = element.find('span', class_=['price', 'priceText'])
        price_text = price_elem.get_text(strip=True) if price_elem else ""
        
        avail_elem = element.find('span', class_='availability')
        avail_text = avail_elem.get_text(strip=True) if avail_elem else ""
        
        # Parse
        price = PriceParser.parse_price(price_text)
        availability, avail_date = self._parse_availability(avail_text)
        
        # Extract brand if present
        brand_elem = element.find('span', class_='brand')
        brand = brand_elem.get_text(strip=True) if brand_elem else None
        
        return Product(
            site=self.site_name,
            name=name,
            brand=brand,
            price=price,
            availability=availability,
            availability_date=avail_date,
            url=url,
            scraped_at=datetime.now(),
            raw_price_text=price_text
        )
    
    def _parse_availability(self, text: str) -> tuple:
        """Parse availability (same as ElectronPribor)."""
        text_lower = text.lower()
        
        if 'в наличии' in text_lower:
            return AvailabilityStatus.IN_STOCK, None
        elif 'поступление' in text_lower:
            date = RussianDateParser.extract_availability_date(text)
            return AvailabilityStatus.PRE_ORDER, date
        elif 'нет' in text_lower or 'недоступно' in text_lower:
            return AvailabilityStatus.OUT_OF_STOCK, None
        elif 'запрос' in text_lower or 'по запросу' in text_lower:
            return AvailabilityStatus.REQUEST_PRICE, None
        else:
            return AvailabilityStatus.UNKNOWN, None
```

### 3.6 Step 6: Data Storage

**File: `storage/csv_writer.py`**
```python
import csv
from pathlib import Path
from typing import List
from models.product import Product
from loguru import logger
from datetime import datetime

class CSVWriter:
    @staticmethod
    def write(products: List[Product], output_path: str):
        """Export products to CSV."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'site', 'name', 'brand', 'price', 'currency',
                    'availability', 'availability_date', 'url', 'scraped_at'
                ])
                writer.writeheader()
                
                for product in products:
                    writer.writerow({
                        'site': product.site,
                        'name': product.name,
                        'brand': product.brand or '',
                        'price': product.price or '',
                        'currency': product.currency,
                        'availability': product.availability.value,
                        'availability_date': product.availability_date.isoformat() if product.availability_date else '',
                        'url': product.url,
                        'scraped_at': product.scraped_at.isoformat()
                    })
            
            logger.info(f"Exported {len(products)} products to {output_path}")
        except Exception as e:
            logger.error(f"Failed to write CSV: {e}")
```

**File: `storage/json_writer.py`**
```python
import json
from pathlib import Path
from typing import List
from models.product import Product
from loguru import logger

class JSONWriter:
    @staticmethod
    def write(products: List[Product], output_path: str):
        """Export products to JSON."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(
                    [json.loads(p.model_dump_json()) for p in products],
                    f,
                    ensure_ascii=False,
                    indent=2
                )
            
            logger.info(f"Exported {len(products)} products to {output_path}")
        except Exception as e:
            logger.error(f"Failed to write JSON: {e}")
```

### 3.7 Step 7: CLI Interface

**File: `cli/main.py`**
```python
import click
from pathlib import Path
from datetime import datetime
from scrapers.electronpribor import ElectronPriborScraper
from scrapers.prist import PristScraper
from storage.csv_writer import CSVWriter
from storage.json_writer import JSONWriter
from loguru import logger

@click.group()
def cli():
    """Price Aggregator CLI"""
    pass

@cli.command()
@click.option('--site', type=click.Choice(['electronpribor', 'prist', 'all']), default='all')
@click.option('--format', type=click.Choice(['csv', 'json', 'both']), default='csv')
@click.option('--output', type=click.Path(), default='data/output')
def scrape(site, format, output):
    """Scrape price data from measurement equipment retailers."""
    
    logger.info(f"Starting scrape: site={site}, format={format}")
    
    scrapers = {
        'electronpribor': ElectronPriborScraper(),
        'prist': PristScraper()
    }
    
    all_products = []
    
    # Run scrapers
    if site == 'all':
        sites_to_scrape = ['electronpribor', 'prist']
    else:
        sites_to_scrape = [site]
    
    for site_name in sites_to_scrape:
        try:
            scraper = scrapers[site_name]
            products = scraper.scrape()
            all_products.extend(products)
            scraper.close()
            click.echo(f"✅ {site_name}: {len(products)} products")
        except Exception as e:
            click.echo(f"❌ {site_name}: {e}", err=True)
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if format in ['csv', 'both']:
        csv_path = f"{output}/prices_{timestamp}.csv"
        CSVWriter.write(all_products, csv_path)
    
    if format in ['json', 'both']:
        json_path = f"{output}/prices_{timestamp}.json"
        JSONWriter.write(all_products, json_path)
    
    click.echo(f"\n✅ Total products: {len(all_products)}")

@cli.command()
@click.option('--interval', type=int, default=24, help='Hours between scrapes')
def schedule(interval):
    """Schedule periodic scraping."""
    from scheduler.jobs import start_scheduler
    
    logger.info(f"Scheduling scrapes every {interval} hours")
    start_scheduler(interval)

if __name__ == '__main__':
    cli()
```

---

## 🧪 PHASE 4: ERROR HANDLING & EDGE CASES

### 4.1 Anticipated Errors & Solutions

| Error | Root Cause | Solution |
|-------|-----------|----------|
| **Price parsing fails** | Unexpected format (e.g., range "100-200 ₽") | Try/catch with fallback to None, log raw text |
| **Date parsing fails** | Russian date format variations | Use dateparser library with language hints |
| **404 on product URL** | Products deleted/moved | Skip with warning, mark as unavailable |
| **Network timeout** | Site slow or blocking | Exponential backoff, max 3 retries |
| **Rate limiting (429)** | Site throttles requests | Increase delay, use random User-Agent rotation |
| **JavaScript-rendered prices** | Prices not in HTML | Add Playwright as optional fallback |
| **Duplicates across sites** | Same product listed twice | Fuzzy name matching with `fuzzywuzzy` |
| **"Цена по запросу"** | Price unknown | Store as None, flag for manual review |

### 4.2 Deduplication Strategy

```python
# processors/deduplicator.py
from fuzzywuzzy import fuzz

def detect_duplicates(products):
    """Find same products across different sites."""
    duplicates = []
    
    for i, p1 in enumerate(products):
        for p2 in products[i+1:]:
            # Compare name similarity
            similarity = fuzz.token_sort_ratio(p1.name, p2.name)
            
            if similarity > 85 and p1.site != p2.site:
                duplicates.append((p1, p2, similarity))
    
    return duplicates
```

---

## 📊 PHASE 5: TESTING STRATEGY

### 5.1 Test Structure

```python
# tests/test_scrapers.py (with VCR cassettes)
import pytest
import vcr

@pytest.fixture
def electronpribor_scraper():
    return ElectronPriborScraper()

@vcr.VCR()
def test_electronpribor_scrape(electronpribor_scraper):
    """Test scraping (uses recorded HTTP responses)."""
    products = electronpribor_scraper.scrape()
    
    assert len(products) > 0
    assert all(p.site == "electronpribor" for p in products)
    assert any(p.price is not None for p in products)

def test_price_parser():
    """Test price extraction."""
    assert PriceParser.parse_price("47 910 ₽") == 47910.0
    assert PriceParser.parse_price("Цена по запросу") is None
    assert PriceParser.parse_price("360 ₽") == 360.0

def test_product_validation():
    """Test Pydantic model validation."""
    # Valid product
    product = Product(
        site="test",
        name="Test",
        price=100.0,
        availability=AvailabilityStatus.IN_STOCK,
        url="http://test.com",
        scraped_at=datetime.now()
    )
    assert product.price == 100.0
    
    # Invalid: negative price
    with pytest.raises(ValueError):
        Product(
            site="test",
            name="Test",
            price=-100.0,
            availability=AvailabilityStatus.IN_STOCK,
            url="http://test.com",
            scraped_at=datetime.now()
        )
```

---

## 🚀 PHASE 6: DEPLOYMENT & MAINTENANCE

### 6.1 Running the Scraper

```bash
# Single run (all sites, CSV output)
python -m cli.main scrape

# Specific site, JSON output
python -m cli.main scrape --site electronpribor --format json

# Schedule automatic scrapes every 24 hours
python -m cli.main schedule --interval 24

# Run tests with coverage
pytest tests/ --cov=scrapers,processors,storage
```

### 6.2 Cron Job Setup (Linux/Mac)

```bash
# Add to crontab -e
# Run daily at 2 AM
0 2 * * * cd /path/to/project && python -m cli.main scrape --format both >> logs/cron.log 2>&1

# Run tests weekly
0 3 * * 0 cd /path/to/project && pytest tests/ >> logs/test.log 2>&1
```

### 6.3 Logging Configuration

```python
# config/logging_config.py
from loguru import logger
import sys

def setup_logging():
    logger.remove()  # Remove default handler
    
    # File logging
    logger.add(
        "logs/scraper_{time:YYYY-MM-DD}.log",
        rotation="500 MB",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )
    
    # Console logging
    logger.add(
        sys.stderr,
        format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO"
    )
```

---

## 📈 PHASE 7: MAINTENANCE & MONITORING

### 7.1 What to Monitor

- **Scrape Success Rate:** Track % of products successfully parsed
- **Price Changes:** Detect anomalies (e.g., 10x price increase)
- **Site Availability:** Alert if sites go down
- **Parse Errors:** Log failures for manual review
- **Data Quality:** Monitor null prices, invalid dates

### 7.2 Anticipated Maintenance Needs

| Issue | Timeline | Action |
|-------|----------|--------|
| Site structure changes | 3-12 months | Update CSS selectors in YAML |
| New products added | Ongoing | Automatic via pagination |
| Anti-scraping measures | 6-12 months | May need to add Playwright/rotating proxies |
| Rate limit increases | 3-6 months | Monitor 429 errors, adjust delays |
| Price list format changes | 6-12 months | Update regex patterns |

---

## ✅ CHECKLIST FOR DEVELOPMENT

- [ ] Setup project structure and dependencies
- [ ] Create Pydantic models
- [ ] Implement price/date parsers with tests
- [ ] Build ElectronPribor scraper
- [ ] Build Prist scraper
- [ ] Test both scrapers with VCR recordings
- [ ] Implement CSV/JSON export
- [ ] Create CLI with Click
- [ ] Add error logging and monitoring
- [ ] Write unit tests (target 80%+ coverage)
- [ ] Add APScheduler for background jobs
- [ ] Document API and usage
- [ ] Create GitHub Actions CI/CD
- [ ] Deploy to server with cron job

---

## 🎯 EXPECTED OUTCOMES

**Initial Development:** ~1 week (40-50 hours)
- Day 1-2: Setup, models, parsers
- Day 3-4: Scrapers for both sites
- Day 5: Storage, CLI, testing
- Day 6-7: Documentation, deployment, monitoring

**Maintenance:** ~2-4 hours/month
- Monitor logs for errors
- Update selectors if site structure changes
- Adjust rate limits if needed

**Output:**
- CSV with all products (columns: site, name, brand, price, availability, url, scraped_at)
- JSON for programmatic access
- Daily cron job runs (automated)
- Notifications for price changes (optional future feature)

---

## 🔗 BEST PRACTICES IMPLEMENTED

✅ **Code Organization:** Clear separation of concerns (scrapers, parsers, storage)
✅ **Type Safety:** Pydantic models for validation
✅ **Error Handling:** Comprehensive try/catch with logging
✅ **Testing:** VCR for deterministic HTTP testing
✅ **Configuration:** YAML-based, environment variables
✅ **Logging:** Structured logging with timestamps
✅ **Rate Limiting:** Configurable delays per site
✅ **Retry Logic:** Exponential backoff for failures
✅ **Documentation:** Extensive docstrings and comments
✅ **Maintainability:** Modular design, easy to add new sites

---

## 📝 NOTES FOR FUTURE IMPROVEMENTS

1. **Database Storage:** SQLite/PostgreSQL for historical price tracking
2. **Price Alerts:** Email/Telegram notifications on significant changes
3. **API Server:** FastAPI to serve aggregated data
4. **Web Dashboard:** Visualize prices over time
5. **Duplicate Resolution:** ML-based matching across retailers
6. **Proxy Rotation:** Handle stronger anti-scraping measures
7. **Playwright Integration:** For JS-heavy sites
8. **Data Validation API:** Catch errors before export
9. **Performance Metrics:** Track scrape speed and success rates
10. **Multi-language Support:** Extend to English/other languages
