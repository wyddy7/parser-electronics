# Шаблон сбора информации для создания парсеров

## Базовые данные
- **Сайт**: `MProfit`
- **Base URL**: `https://mprofit.ru/`
- **Имя парсера** (snake_case): `mprofit`

---

## 1. Поиск товаров

**URL паттерн:**
```
https://mprofit.ru/catalog/?q={query}&s=Найти&type=catalog
```

**Кодирование:**
- [x] `urllib.parse.quote()` (пробелы → `%20`)
- [x] Замена пробелов на `+`
- [ ] Другое: `_________________`

**Примечание:** Используется URL-кодирование для спецсимволов (например, `%2C` для запятой) и замена пробелов на `+`

**Тестовый URL:**
- Товар: `NRP2, измеритель мощности`
- URL: `https://mprofit.ru/catalog/?q=NRP2%2C+%D0%B8%D0%B7%D0%BC%D0%B5%D1%80%D0%B8%D1%82%D0%B5%D0%BB%D1%8C+%D0%BC%D0%BE%D1%89%D0%BD%D0%BE%D1%81%D1%82%D0%B8&s=%D0%9D%D0%B0%D0%B9%D1%82%D0%B8&type=catalog`

---

## 2. CSS Селекторы

**Контейнер результатов:**
```css
.catalog.list.search.js_wrapper_items > .list_item_wrapp.item_wrap.item
```

**Элемент товара:**
```css
.list_item_wrapp.item_wrap.item
```

**Название:**
```css
.item-title a span
```
Или: `.item-title a`

**Цена:**
```css
.price_value
```
Когда есть цена. Когда "по запросу": `.price` (текст "Цена по запросу")

**Примечание:** Валюта в `.price_currency` (руб.), единица измерения в `.price_measure` (/шт)

**Ссылка:**
```css
.item-title a
```

**HTML пример товара:**

С ценой:
```html
<div class="list_item_wrapp item_wrap item">
  <div class="list_item item_info">
    <div class="description_wrapp">
      <div class="item-title">
        <a href="/catalog/izmeritel-moshchnosti-agilent-e4418b/">
          <span>Измеритель мощности Agilent E4418B (демонстрационный)</span>
        </a>
      </div>
    </div>
    <div class="information_wrapp main_item_wrapper">
      <div class="cost prices clearfix">
        <div class="price font-bold">
          <div class="price_value_block values_wrapper">
            <span class="price_value">303 174</span>
            <span class="price_currency"> руб.</span>
          </div>
          <span class="price_measure">/шт</span>
        </div>
      </div>
    </div>
  </div>
</div>
```

"По запросу":
```html
<div class="list_item_wrapp item_wrap item">
  <div class="list_item item_info">
    <div class="description_wrapp">
      <div class="item-title">
        <a href="/catalog/izmeritel-moshchnosti-akip-2502/">
          <span>Измеритель мощности АКИП-2502</span>
        </a>
      </div>
    </div>
    <div class="information_wrapp main_item_wrapper">
      <div class="cost prices clearfix">
        <div class="price_matrix_wrapper">
          <div class="price font-bold">
            Цена по запросу
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
```

---

## 3. Цена

**Формат:**
- [x] `303 174 руб.` (пробелы как разделители тысяч)
- [ ] `1000.00 ₽` (точка)
- [ ] `1,000 ₽` (запятая)
- [ ] Другое: `_________________`

**Примеры:**
- `303 174 руб.` (цена с пробелами между тысячами)
- `3 547 729 руб.` (большие суммы)
- `36 259 руб.` (меньшие суммы)

**Особые случаи:**
- Диапазон цен: `_________________` → брать: `_________________`
- "По запросу": текст `Цена по запросу`
- "Снят": текст `_________________` (не обнаружено в примерах)

---

## 4. Страница товара

- [x] Цена в результатах поиска
- [ ] Нужен переход на страницу товара

**Если нужна страница:**
- Селектор цены: `_________________`
- Селектор названия: `_________________`

---

## 5. Выбор товара

**Критерии:**
- [ ] Точное совпадение названия
- [ ] Совпадение артикула
- [x] Частичное совпадение (поиск работает по части названия)

**Приоритет:**
1. С ценой > "по запросу" > "снят"
2. Точное > частичное

---

## 6. Технические настройки

**Рекомендуемые значения:**
- `timeout`: `18-20` сек
- `request_delay`: `0.8-1.0` сек
- `max_concurrent`: `4-6`
- `batch_delay`: `4-5` сек

**Особенности:**
- Цена отображается в формате "303 174 руб." (пробелы между тысячами)
- Когда цена отсутствует, показывается текст "Цена по запросу" в блоке `.price`
- Используется параметр `s=Найти` и `type=catalog` в URL поиска
- Статусы наличия: "Мало", "Уточняйте наличие"

---

## 7. Тестовые товары

1. `Agilent E4418B` → цена: `303 174 руб.`
2. `HIOKI 3390` → цена: `3 547 729 руб.`
3. `NRP2` → цена: `_________________` (нужно проверить)
4. "По запросу": `АКИП-2502` или `Измеритель мощности АКИП-2502`
5. "Снят": `_________________` (не обнаружено в примерах)
6. Не найден: `_________________` (нужно протестировать)

---

## 8. Конфигурация config.yaml

```yaml
parser:
  mprofit:
    enabled: true
    base_url: "https://mprofit.ru/"
    async:
      enabled: true
      max_concurrent: 4-6
      request_delay: 0.8-1.0
      batch_size: 20-30
      batch_delay: 4-5
    timeout: 18-20
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
```

---

## Чеклист готовности

- [x] Base URL
- [x] URL паттерн поиска
- [x] Селектор контейнера
- [x] Селектор товара
- [x] Селектор названия
- [x] Селектор цены
- [x] Селектор ссылки
- [x] Формат цены
- [x] Статусы ("по запросу", "снят")
- [x] Тестовые товары
- [x] Конфигурация

**Готово к реализации!** ✅

