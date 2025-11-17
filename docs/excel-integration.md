# EXCEL INTEGRATION: Complete Guide for Price Aggregator

---

## 🎯 OVERVIEW

Your requirement: **Read input data FROM Excel + Write output data TO Excel**

This changes the architecture to become **bidirectional**:

```
Excel File (Input) ──→ [Scraper + Aggregator] ──→ Excel File (Output)
   ├─ Product list to track
   ├─ URLs to scrape
   └─ Previous prices
   
                              ↓
                         
                    [Price Updates Applied]
                    
                              ↓
                         
Excel File (Output) ←─ [New prices, changes, status]
   ├─ Updated prices
   ├─ Availability changes
   ├─ Price deltas
   └─ Timestamps
```

---

## 📦 TECHNOLOGY CHOICE

### Pandas vs OpenPyXL vs XlsxWriter

| Feature | Pandas | OpenPyXL | XlsxWriter |
|---------|--------|----------|-----------|
| **Read Excel** | ✅ Easy | ✅ Detailed | ❌ Write-only |
| **Write Excel** | ✅ Easy | ✅ Detailed | ✅ Fast |
| **Formatting** | Basic | Advanced | Advanced |
| **Formulas** | ❌ Limited | ✅ Full support | ✅ Full support |
| **Performance** | Good | Good | Excellent |
| **Simplicity** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **Use Case** | Analysis + Quick export | Complex workbooks | Large files |

**RECOMMENDATION FOR YOUR PROJECT: Pandas + OpenPyXL**

- **Pandas** for: Reading input list, manipulating data
- **OpenPyXL** for: Advanced formatting on output (conditional formatting, borders, formulas)

---

## 🏗️ REVISED ARCHITECTURE

### Complete Data Flow with Excel

```
┌─────────────────────────────────────────────────────────────┐
│                EXCEL-AWARE ARCHITECTURE                     │
└─────────────────────────────────────────────────────────────┘

STEP 1: READ INPUT EXCEL
─────────────────────────
Input: products.xlsx
       ├─ Column A: product_id
       ├─ Column B: product_name
       ├─ Column C: site (electronpribor or prist)
       ├─ Column D: url
       └─ Column E: last_known_price (optional)

     ↓ [Pandas: read_excel()]

Dict/DataFrame in memory:
{
  "products": [
    {"id": 1, "name": "Е6-32", "site": "electronpribor", "url": "...", "last_price": 47910},
    ...
  ]
}

STEP 2: SCRAPE WEBSITES
───────────────────────
For each product in DataFrame:
  1. Fetch current price
  2. Check availability
  3. Compare with last_price
  4. Calculate delta
  5. Track changes

Results collected in-memory

STEP 3: PREPARE OUTPUT DATA
────────────────────────────
Create comprehensive DataFrame:
{
  "product_id": [1, 2, 3, ...],
  "product_name": ["Е6-32", ...],
  "site": ["electronpribor", ...],
  "last_price": [47910, ...],
  "current_price": [47910, ...],
  "price_change": [0, ...],
  "price_change_pct": [0%, ...],
  "availability": ["в наличии", ...],
  "availability_date": [null, "2026-01-11", ...],
  "status": ["no change", "price_up", "price_down", ...],
  "url": ["...", ...],
  "scraped_at": ["2025-11-16 23:45", ...]
}

STEP 4: WRITE TO EXCEL WITH FORMATTING
────────────────────────────────────────
Output: prices_report_2025-11-16.xlsx

Features:
  ✓ Multiple sheets (Summary, Detailed, Changes)
  ✓ Conditional formatting (red for price up, green for price down)
  ✓ Formulas for calculations
  ✓ Frozen header rows
  ✓ Column widths auto-fitted
  ✓ Number formatting for prices (2 decimals)
  ✓ Date formatting (YYYY-MM-DD HH:MM)

```

---

## 💾 EXCEL FILE STRUCTURES

### INPUT: `products.xlsx`

```
Sheet: "Products to Track"

| product_id | product_name | site | url | last_price | last_check |
|------------|--------------|------|-----|-----------|------------|
| 1 | Е6-32, цифровой мегаомметр | electronpribor | https://www.electronpribor.ru/... | 47910 | 2025-11-15 |
| 2 | МЭС-200А | electronpribor | https://www.electronpribor.ru/... | 63500 | 2025-11-15 |
| 3 | MET/CAL-METCON | prist | https://prist.ru/... | | 2025-11-10 |
```

### OUTPUT: `prices_report_2025-11-16.xlsx`

**Sheet 1: "Summary"**
```
| Metric | Value |
|--------|-------|
| Total Products | 15 |
| Price Increases | 2 |
| Price Decreases | 1 |
| No Change | 12 |
| Newly Available | 0 |
| Out of Stock | 0 |
| Data Updated | 2025-11-16 23:45 |
```

**Sheet 2: "Detailed Results"**
```
| product_id | product_name | site | last_price | current_price | change | change_pct | availability | url |
|------------|--------------|------|-----------|--------------|--------|-----------|--------------|-----|
| 1 | Е6-32 | electronpribor | 47910 | 47910 | 0 | 0% | в наличии | https://... |
| 2 | МЭС-200А | electronpribor | 63500 | 63500 | 0 | 0% | в наличии | https://... |
| 3 | MET/CAL-METCON | prist | [not found] | [not found] | - | - | цена по запросу | https://... |
```
(with formatting: green/red backgrounds, number formatting)

**Sheet 3: "Changes Only"**
```
Only rows where price changed or availability changed
(auto-filtered for review)
```

---

## 🔧 IMPLEMENTATION CODE

### Step 1: Update requirements.txt

```
requests==2.31.0
beautifulsoup4==4.12.2
pydantic==2.5.0
python-dotenv==1.0.0
dateparser==1.1.8
pandas==2.1.3           # ← ADD FOR EXCEL
openpyxl==3.11.0        # ← ADD FOR EXCEL (advanced formatting)
xlsxwriter==3.1.2       # ← OPTIONAL (for performance)
click==8.1.7
APScheduler==3.10.4
pyyaml==6.0
loguru==0.7.2
pytest==7.4.3
pytest-vcr==1.0.2
```

### Step 2: Excel Reader Module

**File: `storage/excel_reader.py`**
```python
import pandas as pd
from typing import List, Optional
from loguru import logger
from pathlib import Path

class ExcelReader:
    """Read product input list from Excel."""
    
    @staticmethod
    def read_products(excel_path: str, sheet_name: str = "Products") -> pd.DataFrame:
        """
        Read product list from Excel.
        
        Expected columns:
        - product_id (optional)
        - product_name (required)
        - site (required: 'electronpribor' or 'prist')
        - url (required)
        - last_price (optional)
        - last_check (optional)
        """
        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            logger.info(f"Read {len(df)} products from {excel_path}")
            
            # Validate required columns
            required_cols = ['product_name', 'site', 'url']
            missing = [col for col in required_cols if col not in df.columns]
            if missing:
                raise ValueError(f"Missing required columns: {missing}")
            
            # Clean data
            df = df.fillna('')  # Replace NaN with empty string
            df['url'] = df['url'].str.strip()
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to read Excel: {e}")
            raise

    @staticmethod
    def get_products_by_site(df: pd.DataFrame, site: str) -> pd.DataFrame:
        """Filter products by site."""
        return df[df['site'].str.lower() == site.lower()]
```

### Step 3: Excel Writer Module with Formatting

**File: `storage/excel_writer.py`**
```python
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime
from typing import Dict, List
from loguru import logger
from pathlib import Path

class ExcelWriter:
    """Write results to Excel with professional formatting."""
    
    # Color schemes
    HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
    
    PRICE_UP_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")  # Light red
    PRICE_DOWN_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")  # Light green
    NO_CHANGE_FILL = PatternFill(start_color="FFFFEB", end_color="FFFFEB", fill_type="solid")  # Light yellow
    
    BORDER = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    @staticmethod
    def write_results(
        results_df: pd.DataFrame,
        summary_stats: Dict,
        output_path: str = "data/output/prices_report.xlsx"
    ):
        """
        Write results to Excel with multiple sheets and formatting.
        
        Args:
            results_df: DataFrame with all results
            summary_stats: Dict with summary statistics
            output_path: Output file path
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create Excel writer
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Sheet 1: Summary
            summary_df = ExcelWriter._create_summary_sheet(summary_stats)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Sheet 2: Detailed Results
            results_df.to_excel(writer, sheet_name='Detailed', index=False)
            
            # Sheet 3: Changes Only (filter)
            changes_df = results_df[results_df['status'] != 'no_change'].copy()
            if len(changes_df) > 0:
                changes_df.to_excel(writer, sheet_name='Changes', index=False)
            
            # Get workbook and apply formatting
            workbook = writer.book
            ExcelWriter._format_workbook(workbook, results_df, summary_df)
        
        logger.info(f"Exported results to {output_path}")
        return output_path
    
    @staticmethod
    def _create_summary_sheet(stats: Dict) -> pd.DataFrame:
        """Create summary statistics sheet."""
        data = {
            'Metric': [
                'Total Products',
                'Price Increases',
                'Price Decreases',
                'No Changes',
                'Availability Changes',
                'Data Quality Issues',
                'Scan Timestamp'
            ],
            'Value': [
                stats.get('total_products', 0),
                stats.get('price_increases', 0),
                stats.get('price_decreases', 0),
                stats.get('no_changes', 0),
                stats.get('availability_changes', 0),
                stats.get('quality_issues', 0),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ]
        }
        return pd.DataFrame(data)
    
    @staticmethod
    def _format_workbook(workbook, results_df, summary_df):
        """Apply formatting to all sheets."""
        
        # Format Summary sheet
        summary_ws = workbook['Summary']
        ExcelWriter._format_sheet(summary_ws, summary_df)
        summary_ws.column_dimensions['A'].width = 25
        summary_ws.column_dimensions['B'].width = 15
        
        # Format Detailed sheet
        detailed_ws = workbook['Detailed']
        ExcelWriter._format_sheet(detailed_ws, results_df)
        
        # Auto-adjust column widths
        for ws in [summary_ws, detailed_ws]:
            for column in ws.columns:
                max_length = 0
                column_letter = get_column_letter(column[0].column)
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)  # Cap at 50
                ws.column_dimensions[column_letter].width = adjusted_width
        
        # Format Changes sheet if exists
        if 'Changes' in workbook.sheetnames:
            changes_ws = workbook['Changes']
            ExcelWriter._format_sheet(changes_ws, results_df)
        
        # Add conditional formatting to Detailed sheet
        ExcelWriter._add_conditional_formatting(detailed_ws, results_df)
    
    @staticmethod
    def _format_sheet(worksheet, df):
        """Format header and cells."""
        # Header row
        for cell in worksheet[1]:
            cell.fill = ExcelWriter.HEADER_FILL
            cell.font = ExcelWriter.HEADER_FONT
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = ExcelWriter.BORDER
        
        # Data rows
        for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row):
            for cell in row:
                cell.border = ExcelWriter.BORDER
                cell.alignment = Alignment(horizontal='left', vertical='center')
                
                # Format numbers
                if cell.data_type == 'n':  # Numeric
                    if 'price' in cell.column_letter.lower() or 'change' in cell.column_letter.lower():
                        cell.number_format = '#,##0.00'
                    elif 'pct' in str(cell.value) or '%' in str(cell.value):
                        cell.number_format = '0.00%'
    
    @staticmethod
    def _add_conditional_formatting(worksheet, df):
        """Add conditional formatting (color coding)."""
        # Find status column
        status_col_letter = None
        for col_num, cell in enumerate(worksheet[1], 1):
            if cell.value == 'status':
                status_col_letter = get_column_letter(col_num)
                break
        
        if not status_col_letter:
            return
        
        # Color code by status
        for row_num, row in enumerate(worksheet.iter_rows(min_row=2), start=2):
            status_cell = worksheet[f'{status_col_letter}{row_num}']
            status = status_cell.value
            
            if status == 'price_up':
                for cell in row:
                    cell.fill = ExcelWriter.PRICE_UP_FILL
            elif status == 'price_down':
                for cell in row:
                    cell.fill = ExcelWriter.PRICE_DOWN_FILL
            elif status == 'no_change':
                for cell in row:
                    cell.fill = ExcelWriter.NO_CHANGE_FILL
```

### Step 4: Comparison & Aggregation Engine

**File: `processors/aggregator.py`**
```python
import pandas as pd
from typing import Dict, List, Tuple
from datetime import datetime
from loguru import logger

class PriceAggregator:
    """Aggregate current prices with historical data from Excel."""
    
    @staticmethod
    def compare_prices(
        input_df: pd.DataFrame,
        current_prices: List[Dict]
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        Compare current prices with previous data.
        
        Returns:
            (results_df, summary_stats)
        """
        logger.info(f"Comparing {len(current_prices)} current prices with {len(input_df)} historical records")
        
        # Convert current prices to DataFrame
        current_df = pd.DataFrame(current_prices)
        
        # Merge on product_id or name+site
        results = []
        stats = {
            'total_products': len(input_df),
            'price_increases': 0,
            'price_decreases': 0,
            'no_changes': 0,
            'availability_changes': 0,
            'quality_issues': 0,
        }
        
        for idx, row in input_df.iterrows():
            product_id = row.get('product_id', idx)
            product_name = row['product_name']
            site = row['site']
            url = row['url']
            last_price = row.get('last_price') or None
            last_availability = row.get('last_availability') or None
            
            # Find matching current price
            current = None
            for curr_row in current_prices:
                if curr_row['name'] == product_name and curr_row['site'] == site:
                    current = curr_row
                    break
            
            if current is None:
                # Product not found in scrape
                result = {
                    'product_id': product_id,
                    'product_name': product_name,
                    'site': site,
                    'url': url,
                    'last_price': last_price,
                    'current_price': None,
                    'price_change': None,
                    'price_change_pct': None,
                    'availability': 'not_found',
                    'availability_date': None,
                    'status': 'scrape_error',
                    'scraped_at': datetime.now()
                }
                stats['quality_issues'] += 1
            else:
                # Compare prices
                curr_price = current['price']
                curr_avail = current['availability']
                
                price_change = None
                price_change_pct = None
                status = 'no_change'
                
                if last_price and curr_price:
                    price_change = curr_price - last_price
                    price_change_pct = (price_change / last_price * 100) if last_price != 0 else 0
                    
                    if price_change > 0:
                        status = 'price_up'
                        stats['price_increases'] += 1
                    elif price_change < 0:
                        status = 'price_down'
                        stats['price_decreases'] += 1
                    else:
                        stats['no_changes'] += 1
                elif last_price is None and curr_price:
                    # New price discovered
                    status = 'newly_found'
                
                if curr_avail != last_availability:
                    stats['availability_changes'] += 1
                
                result = {
                    'product_id': product_id,
                    'product_name': product_name,
                    'site': site,
                    'url': url,
                    'last_price': last_price,
                    'current_price': curr_price,
                    'price_change': price_change,
                    'price_change_pct': price_change_pct,
                    'availability': curr_avail.value if hasattr(curr_avail, 'value') else str(curr_avail),
                    'availability_date': current.get('availability_date'),
                    'status': status,
                    'scraped_at': datetime.now()
                }
            
            results.append(result)
        
        results_df = pd.DataFrame(results)
        return results_df, stats
```

### Step 5: Updated Main CLI

**File: `cli/main.py` (updated)**
```python
import click
from pathlib import Path
from datetime import datetime
from storage.excel_reader import ExcelReader
from storage.excel_writer import ExcelWriter
from processors.aggregator import PriceAggregator
from scrapers.electronpribor import ElectronPriborScraper
from scrapers.prist import PristScraper
from loguru import logger

@click.group()
def cli():
    """Price Aggregator with Excel Integration"""
    pass

@cli.command()
@click.option('--input', type=click.Path(exists=True), default='products.xlsx',
              help='Input Excel file with products to track')
@click.option('--output', type=click.Path(), default='data/output',
              help='Output directory for results')
@click.option('--format', type=click.Choice(['xlsx', 'csv', 'both']), default='xlsx')
def scrape(input, output, format):
    """Scrape prices and update Excel with results."""
    
    logger.info(f"Starting scrape with input: {input}")
    
    # STEP 1: Read input Excel
    try:
        products_df = ExcelReader.read_products(input)
    except Exception as e:
        click.echo(f"❌ Failed to read input Excel: {e}", err=True)
        return
    
    click.echo(f"✅ Read {len(products_df)} products from {input}")
    
    # STEP 2: Scrape all sites
    all_current_prices = []
    
    scrapers = {
        'electronpribor': ElectronPriborScraper(),
        'prist': PristScraper()
    }
    
    for site_name, scraper in scrapers.items():
        site_products = ExcelReader.get_products_by_site(products_df, site_name)
        if len(site_products) == 0:
            continue
        
        try:
            logger.info(f"Scraping {site_name} ({len(site_products)} products)")
            prices = scraper.scrape()
            all_current_prices.extend(prices)
            click.echo(f"✅ {site_name}: {len(prices)} products scraped")
        except Exception as e:
            click.echo(f"❌ {site_name} failed: {e}", err=True)
        finally:
            scraper.close()
    
    # STEP 3: Compare and aggregate
    results_df, stats = PriceAggregator.compare_prices(products_df, all_current_prices)
    
    # STEP 4: Write output
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if format in ['xlsx', 'both']:
        xlsx_path = f"{output}/prices_report_{timestamp}.xlsx"
        ExcelWriter.write_results(results_df, stats, xlsx_path)
        click.echo(f"✅ Excel report: {xlsx_path}")
    
    if format in ['csv', 'both']:
        csv_path = f"{output}/prices_report_{timestamp}.csv"
        results_df.to_csv(csv_path, encoding='utf-8-sig', index=False)
        click.echo(f"✅ CSV export: {csv_path}")
    
    # Display summary
    click.echo(f"\n📊 SUMMARY:")
    click.echo(f"  Total products: {stats['total_products']}")
    click.echo(f"  Price increases: {stats['price_increases']}")
    click.echo(f"  Price decreases: {stats['price_decreases']}")
    click.echo(f"  No changes: {stats['no_changes']}")
    click.echo(f"  Availability changes: {stats['availability_changes']}")

if __name__ == '__main__':
    cli()
```

---

## 🚀 USAGE WORKFLOW

### Step 1: Create Input Excel File

Create `products.xlsx` with your products to track:

```excel
product_id | product_name | site | url | last_price | last_check
1 | Е6-32 | electronpribor | https://www.electronpribor.ru/... | 47910 | 2025-11-15
2 | МЭС-200А | electronpribor | https://www.electronpribor.ru/... | 63500 | 2025-11-15
```

### Step 2: Run Scraper

```bash
python -m cli.main scrape --input products.xlsx --output data/output --format xlsx
```

### Step 3: Review Output Excel

Open `prices_report_20251116_234500.xlsx`:
- **Sheet 1 (Summary):** Key metrics
- **Sheet 2 (Detailed):** All products with prices, formatted
- **Sheet 3 (Changes):** Only products with price/availability changes

### Step 4: Update Input Excel

After reviewing, update `products.xlsx` with new `last_price` values:

```python
# Automated update script
import pandas as pd

latest_report = pd.read_excel('data/output/prices_report_20251116_234500.xlsx', 
                              sheet_name='Detailed')
products = pd.read_excel('products.xlsx')

# Update last_price with current_price
for idx, row in latest_report.iterrows():
    product_id = row['product_id']
    new_price = row['current_price']
    products.loc[products['product_id'] == product_id, 'last_price'] = new_price
    products.loc[products['product_id'] == product_id, 'last_check'] = pd.Timestamp.now()

products.to_excel('products.xlsx', index=False)
print("✅ Updated products.xlsx with new prices")
```

### Step 5: Schedule Automation

Add to crontab (daily at 2 AM):
```bash
0 2 * * * cd /path/to/project && python -m cli.main scrape --input products.xlsx --output data/output --format xlsx
```

---

## 📋 CHECKLIST FOR EXCEL INTEGRATION

- [ ] Install pandas: `pip install pandas openpyxl`
- [ ] Create `storage/excel_reader.py` with ExcelReader class
- [ ] Create `storage/excel_writer.py` with ExcelWriter + formatting
- [ ] Create `processors/aggregator.py` with PriceAggregator
- [ ] Update CLI to use Excel input/output
- [ ] Create sample `products.xlsx` with test data
- [ ] Test scrape with Excel input
- [ ] Review formatted output
- [ ] Test update workflow
- [ ] Schedule daily runs

---

## 🎨 EXCEL FORMATTING FEATURES

✅ **Professional Look:**
- Blue header row with white bold text
- Auto-fitted column widths (max 50 chars)
- Borders on all cells
- Center-aligned headers
- Left-aligned data

✅ **Color Coding:**
- 🟢 Green: Price decreased (good deal!)
- 🔴 Red: Price increased
- 🟡 Yellow: No change

✅ **Number Formatting:**
- Prices: `47,910.00` (thousands separator)
- Percentages: `3.21%`
- Dates: `2025-11-16 23:45`

✅ **Multiple Sheets:**
- Summary: Quick stats
- Detailed: Complete results
- Changes: Filter for review

---

## 💡 ADVANCED FEATURES (Future)

1. **Conditional Formatting:** Highlight largest price changes
2. **Pivot Tables:** Analyze by site or category
3. **Charts:** Price trends over time
4. **Data Validation:** Dropdown menus for product selection
5. **Named Ranges:** Reference cells by name in formulas
6. **VBA Macros:** Auto-send email on significant changes

---

## ⚠️ EDGE CASES & SOLUTIONS

| Edge Case | Solution |
|-----------|----------|
| Product URL changed | Keep product_id, ignore URL changes |
| Product no longer available | Mark as "not_found", keep historical price |
| Excel file locked (open in Excel) | Use mode='a' (append) with pandas |
| Large Excel file (>10k products) | Use read_only=True or split into multiple files |
| Unicode characters (Ё, Ы, etc.) | Always use encoding='utf-8-sig' |
| Missing columns in input | Validation catches early with clear error |

---

**Key Point:** Excel integration transforms this from a standalone scraper into a **complete price monitoring system** where you control input, track changes, and review results all in Excel!
