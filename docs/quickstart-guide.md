# FINAL IMPLEMENTATION GUIDE: Start Here

---

## 🎯 COMPLETE SOLUTION OVERVIEW

You asked for: **Full architectural plan with tech stack, best practices, and everything to avoid errors**

Here's what you got:

### 📚 Documents Generated

1. **`price-aggregator-spec.md`** ← FULL TECHNICAL SPEC
   - 40+ page comprehensive architecture
   - Complete code examples for every component
   - Testing strategy with VCR
   - Deployment options

2. **`summary-guide.md`** ← QUICK START
   - Executive summary
   - Data flow diagrams
   - Tech stack justification
   - Best practices checklist

3. **`excel-integration.md`** ← YOUR REQUIREMENT
   - Excel input/output handling
   - Bidirectional workflow
   - Pandas + OpenPyXL combo
   - Real usage examples

4. **THIS DOCUMENT** ← Implementation roadmap

---

## 🏗️ RECOMMENDED ARCHITECTURE (FINAL)

```
Price Aggregator System (Production-Ready)
├── Core Components
│   ├── Scrapers (requests + BeautifulSoup4)
│   │   ├─ Base scraper with retries
│   │   ├─ ElectronPribor implementation
│   │   └─ Prist implementation
│   │
│   ├── Data Processing
│   │   ├─ Price parser (regex for "47 910 ₽")
│   │   ├─ Date parser (Russian: "11.01.2026 г.")
│   │   ├─ Aggregator (compare old vs new)
│   │   └─ Pydantic models (type validation)
│   │
│   ├── Storage Layer
│   │   ├─ Excel reader (pandas)
│   │   ├─ Excel writer (openpyxl with formatting)
│   │   ├─ CSV export (pandas)
│   │   └─ JSON export (built-in)
│   │
│   └── Interface
│       ├─ CLI (click) - manual runs
│       └─ Scheduler (APScheduler) - automated daily
│
├── Data Flow
│   products.xlsx (INPUT)
│      ↓
│   [Read products to track]
│      ↓
│   [Scrape current prices from websites]
│      ↓
│   [Compare with previous prices]
│      ↓
│   prices_report_TIMESTAMP.xlsx (OUTPUT with formatting)
│      ├─ Summary sheet (metrics)
│      ├─ Detailed sheet (all products, color-coded)
│      └─ Changes sheet (only updated items)
│
└── Deployment
    └─ Cron job (daily 2 AM)
       └─ Auto-generates reports
```

---

## 📋 EXACT IMPLEMENTATION STEPS

### Phase 1: Foundation Setup (2 hours)

**1.1 Create project structure:**
```bash
mkdir price-aggregator
cd price-aggregator

# Create folders
mkdir -p config scrapers models processors storage cli scheduler tests logs data/{output,cassettes}
mkdir -p .github/workflows

# Create files
touch config/__init__.py config/settings.py config/sites.yaml
touch scrapers/__init__.py scrapers/base.py scrapers/electronpribor.py scrapers/prist.py scrapers/utils.py
touch models/__init__.py models/product.py models/exceptions.py
touch processors/__init__.py processors/price_parser.py processors/date_parser.py processors/cleaner.py processors/aggregator.py
touch storage/__init__.py storage/csv_writer.py storage/json_writer.py storage/excel_reader.py storage/excel_writer.py
touch cli/__init__.py cli/main.py
touch scheduler/__init__.py scheduler/jobs.py
touch tests/__init__.py tests/conftest.py tests/test_scrapers.py tests/test_processors.py
touch requirements.txt README.md .env.example .gitignore
```

**1.2 Create requirements.txt:**
```
requests==2.31.0
beautifulsoup4==4.12.2
pydantic==2.5.0
python-dotenv==1.0.0
dateparser==1.1.8
pandas==2.1.3
openpyxl==3.11.0
click==8.1.7
APScheduler==3.10.4
pyyaml==6.0
loguru==0.7.2
pytest==7.4.3
pytest-vcr==1.0.2
```

**1.3 Install dependencies:**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**1.4 Create .env.example:**
```
# Scraper settings
REQUEST_TIMEOUT=15
RETRY_ATTEMPTS=3
USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64)
REQUEST_DELAY=1.0

# Paths
OUTPUT_DIR=data/output
LOG_DIR=logs

# Schedule
SCHEDULE_INTERVAL_HOURS=24
```

---

### Phase 2: Core Models & Parsers (3 hours)

**2.1 models/product.py** — Copy from price-aggregator-spec.md (Section 3.3)

**2.2 processors/price_parser.py** — Copy from price-aggregator-spec.md (Section 3.3)

**2.3 processors/date_parser.py** — Copy from price-aggregator-spec.md (Section 3.3)

**2.4 Test parsers locally:**
```python
# test_parsers.py (quick test)
from processors.price_parser import PriceParser

assert PriceParser.parse_price("47 910 ₽") == 47910.0
assert PriceParser.parse_price("360 ₽") == 360.0
assert PriceParser.parse_price("Цена по запросу") is None
print("✅ Price parser works!")
```

---

### Phase 3: Base Scraper & Site Implementations (4 hours)

**3.1 scrapers/base.py** — Copy from price-aggregator-spec.md (Section 3.4)

**3.2 scrapers/electronpribor.py** — Copy from price-aggregator-spec.md (Section 3.5)

**3.3 scrapers/prist.py** — Copy from price-aggregator-spec.md (Section 3.5)

**3.4 Test scrapers:**
```bash
# Quick test - fetch one page
python -c "from scrapers.electronpribor import ElectronPriborScraper; s = ElectronPriborScraper(); products = s.scrape(); print(f'Found {len(products)} products'); [print(p) for p in products[:2]]"
```

---

### Phase 4: Storage (Excel, CSV, JSON) (2 hours)

**4.1 storage/excel_reader.py** — Copy from excel-integration.md (Step 2)

**4.2 storage/excel_writer.py** — Copy from excel-integration.md (Step 3)

**4.3 processors/aggregator.py** — Copy from excel-integration.md (Step 4)

**4.4 Test storage:**
```python
import pandas as pd
from storage.excel_reader import ExcelReader

# Create test Excel
df = pd.DataFrame({
    'product_id': [1, 2],
    'product_name': ['Product A', 'Product B'],
    'site': ['electronpribor', 'prist'],
    'url': ['http://test.com/1', 'http://test.com/2'],
    'last_price': [1000, 2000]
})
df.to_excel('test_products.xlsx', index=False)

# Test reading
products = ExcelReader.read_products('test_products.xlsx')
print(f"✅ Read {len(products)} products from Excel")
```

---

### Phase 5: CLI Interface (1 hour)

**5.1 cli/main.py** — Copy from excel-integration.md (Step 5)

**5.2 Test CLI:**
```bash
# Create sample input
python -c "
import pandas as pd
df = pd.DataFrame({
    'product_id': [1],
    'product_name': ['Test Product'],
    'site': ['electronpribor'],
    'url': ['https://www.electronpribor.ru/'],
    'last_price': [50000]
})
df.to_excel('products.xlsx', index=False)
"

# Run scraper
python -m cli.main scrape --input products.xlsx --output data/output --format xlsx
```

---

### Phase 6: Testing & Quality Assurance (2 hours)

**6.1 tests/conftest.py:**
```python
import pytest
from unittest.mock import Mock, patch

@pytest.fixture
def sample_products():
    return [
        {
            'site': 'electronpribor',
            'name': 'Test Product',
            'price': 50000,
            'availability': 'в наличии'
        }
    ]

@pytest.fixture
def mock_requests(monkeypatch):
    def mock_get(*args, **kwargs):
        mock = Mock()
        mock.text = "<html><body>Test</body></html>"
        mock.status_code = 200
        return mock
    
    monkeypatch.setattr('requests.get', mock_get)
```

**6.2 Run tests:**
```bash
pytest tests/ -v --cov=scrapers,processors,storage
```

---

### Phase 7: Deployment & Scheduling (1 hour)

**7.1 Create cron job (Linux/Mac):**
```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 2 AM)
0 2 * * * cd /path/to/project && python -m cli.main scrape --input products.xlsx --output data/output --format xlsx >> logs/cron.log 2>&1
```

**7.2 Or use APScheduler (cross-platform):**
```python
# scheduler/jobs.py
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

scheduler = BackgroundScheduler()

def daily_scrape():
    import subprocess
    subprocess.run(['python', '-m', 'cli.main', 'scrape'])
    print(f"[{datetime.now()}] Scrape completed")

scheduler.add_job(daily_scrape, 'cron', hour=2, minute=0)
scheduler.start()
```

---

## 🎯 TECH STACK SUMMARY (Why These Tools)

| Layer | Tool | Why | Alternative |
|-------|------|-----|-------------|
| **HTTP** | requests | Simple, mature, handles retries | httpx |
| **HTML** | BeautifulSoup4 | Easy CSS selectors, perfect for static HTML | lxml |
| **Parsing** | regex | Built-in, fast, perfect for prices | parsel |
| **Validation** | Pydantic | Type-safe, auto-errors, great DX | marshmallow |
| **Date** | dateparser | Russian language support | pendulum |
| **Excel I/O** | pandas + openpyxl | pandas for read/write, openpyxl for formatting | xlrd |
| **CLI** | click | Auto-help, decorators, easy | typer |
| **Logging** | loguru | Structured, timestamps, file rotation | logging |
| **Scheduling** | APScheduler | Cron-like, cross-platform, testable | schedule |
| **Testing** | pytest + VCR | Deterministic, no network calls | unittest |

**NOT USED (and why not):**
- ❌ **Scrapy:** Too heavy for 2 sites
- ❌ **Playwright:** No JavaScript rendering needed
- ❌ **MCP:** Loss of control, higher cost
- ❌ **GitHub solutions:** Most target Amazon/eBay, not Russian B2B

---

## ⚠️ ERROR PREVENTION CHECKLIST

### Before Writing Code

- ✅ Read full `price-aggregator-spec.md` (understand architecture)
- ✅ Review `excel-integration.md` (understand Excel workflow)
- ✅ Check real sites manually (understand data structure)

### During Development

- ✅ Test parsers with sample data FIRST
- ✅ Use VCR to record HTTP responses (deterministic tests)
- ✅ Add logging to EVERY scrapy method
- ✅ Handle 429 (rate limit) errors with backoff
- ✅ Validate input Excel structure before processing
- ✅ Test with actual site prices before deployment

### Before Production

- ✅ Run `pytest` — all tests pass
- ✅ Manual test CLI: `python -m cli.main scrape`
- ✅ Check output Excel has formatting
- ✅ Test cron job: run manually first
- ✅ Monitor logs first week
- ✅ Handle edge cases (missing data, special chars, etc.)

---

## 🚀 QUICK START (TL;DR)

```bash
# 1. Setup
git clone your-repo
cd price-aggregator
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Create input
python -c "
import pandas as pd
df = pd.DataFrame({
    'product_id': [1, 2],
    'product_name': ['Е6-32', 'МЭС-200А'],
    'site': ['electronpribor', 'electronpribor'],
    'url': ['https://www.electronpribor.ru/products/e6-32', 'https://www.electronpribor.ru/products/mes-200a'],
    'last_price': [47910, 63500]
})
df.to_excel('products.xlsx', index=False)
"

# 3. Run scraper
python -m cli.main scrape --input products.xlsx --output data/output --format xlsx

# 4. Check output
ls -lah data/output/prices_report_*.xlsx

# 5. Schedule
crontab -e
# Add: 0 2 * * * cd /path && python -m cli.main scrape --input products.xlsx --output data/output --format xlsx
```

---

## 📊 EXPECTED OUTPUT

**Console output:**
```
✅ Read 15 products from products.xlsx
✅ electronpribor: 12 products scraped
✅ prist: 3 products scraped
✅ Excel report: data/output/prices_report_20251116_234500.xlsx
✅ CSV export: data/output/prices_report_20251116_234500.csv

📊 SUMMARY:
  Total products: 15
  Price increases: 2
  Price decreases: 1
  No changes: 12
  Availability changes: 0
```

**Output Excel file:**
- 📋 Sheet 1: Summary (metrics)
- 📋 Sheet 2: Detailed (all products, color-coded)
- 📋 Sheet 3: Changes (only price/availability changes)

---

## 💡 BEST PRACTICES IMPLEMENTED

✅ **Code Organization:** Clear separation of concerns (scrapers, parsers, storage)
✅ **Type Safety:** Pydantic models catch errors early
✅ **Error Handling:** Comprehensive try/catch with logging
✅ **Configuration:** YAML-based, environment variables
✅ **Logging:** Structured logs with timestamps and context
✅ **Rate Limiting:** Per-site configurable delays
✅ **Testing:** VCR cassettes for deterministic tests
✅ **Extensibility:** New sites = 100 lines max
✅ **Excel Integration:** Professional formatting, multiple sheets
✅ **Documentation:** Every file documented, examples provided

---

## 🔧 TROUBLESHOOTING

**Q: "ModuleNotFoundError: No module named 'requests'"**
A: Run `pip install -r requirements.txt`

**Q: "BeautifulSoup can't parse the page"**
A: Site might use JavaScript. Add this to scraper to debug:
```python
with open('debug.html', 'w') as f:
    f.write(html)
# Then inspect debug.html in browser
```

**Q: "Price is showing 'по запросу', not a number"**
A: PriceParser returns None — this is expected! Check excel_writer.py handles None prices.

**Q: "Excel file is locked, can't write"**
A: Close Excel file, or use mode='a' in ExcelWriter:
```python
with pd.ExcelWriter(path, engine='openpyxl', mode='a') as writer:
    ...
```

**Q: "Cron job not running"**
A: Check logs: `tail -f logs/cron.log`
Run manually to test: `python -m cli.main scrape`

---

## 📞 GETTING HELP

1. **Documentation:** Read the full spec files (they have everything)
2. **Code Examples:** All functions have docstrings
3. **Testing:** Run `pytest -v` to see what works
4. **Logging:** Check `logs/*.log` for detailed error messages

---

## 🎓 LEARNING OBJECTIVES

After implementing this, you'll understand:

✅ Web scraping architecture (requests, BeautifulSoup)
✅ Price/date parsing in Russian
✅ Type-safe Python with Pydantic
✅ Excel read/write automation
✅ CLI development with Click
✅ Task scheduling (cron, APScheduler)
✅ Professional error handling
✅ Testing best practices (VCR, pytest)
✅ Production deployment patterns
✅ System design for scalability

---

## ✨ NEXT STEPS AFTER CORE IS WORKING

1. **Monitor logs** for the first week
2. **Add more sites** (follow same 100-line pattern)
3. **Implement price alerts** (email on big changes)
4. **Build database** (SQLite for historical tracking)
5. **Create API** (FastAPI to serve aggregated data)
6. **Add dashboard** (Streamlit for visualization)
7. **Scale to 100+ sites** (add proxy rotation)

---

**Total estimated implementation time: 40 hours over 1 week**

**Maintenance time: 2-4 hours per month**

---

*Version 2.0 — Excel Integration Edition*
*Updated: 2025-11-16*
