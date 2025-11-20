# Шаблон сбора информации для создания парсеров

## Базовые данные
- **Сайт**: `Прибор-Х`
- **Base URL**: `https://www.pribor-x.ru/`
- **Имя парсера** (snake_case): `pribor_x`

---

## 1. Поиск товаров

**URL паттерн:**
```
https://www.pribor-x.ru/catalog/?q={query}&how=r
```

**Кодирование:**
- [ ] `urllib.parse.quote()` (пробелы → `%20`)
- [x] Замена пробелов на `+`
- [ ] Другое: `_________________`

**Примечание:** Также используется URL-кодирование для спецсимволов (например, `%2C` для запятой)

**Тестовый URL:**
- Товар: `Fluke 792A, эталон сравнения постоянного и переменного напряжения`
- URL: `https://www.pribor-x.ru/catalog/?q=Fluke+792A%2C+%D1%8D%D1%82%D0%B0%D0%BB%D0%BE%D0%BD+%D1%81%D1%80%D0%B0%D0%B2%D0%BD%D0%B5%D0%BD%D0%B8%D1%8F+%D0%BF%D0%BE%D1%81%D1%82%D0%BE%D1%8F%D0%BD%D0%BD%D0%BE%D0%B3%D0%BE+%D0%B8+%D0%BF%D0%B5%D1%80%D0%B5%D0%BC%D0%B5%D0%BD%D0%BD%D0%BE%D0%B3%D0%BE+%D0%BD%D0%B0%D0%BF%D1%80%D1%8F%D0%B6%D0%B5%D0%BD%D0%B8%D1%8F&how=r`

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
Или: `table.list_item`

**Название:**
```css
.item-title a span
```
Или: `.item-title a`

**Цена:**
```css
.price .price_value
```
Или: `.price_matrix_block .price .price_value`

Когда есть цена. Когда "по запросу": `.to-order span` (текст "Цена по запросу")

**Примечание:** Цена может быть в блоке `.price_matrix_block` или в `.cost.prices`. Валюта в `.price_currency`, единица измерения в `.price_measure`.

**Ссылка:**
```css
.item-title a
```

**HTML пример товара:**

С ценой:
```html
<div class="list_item_wrapp item_wrap item">
  <table class="list_item">
    <tr>
      <td class="description_wrapp item_info">
        <div class="item-title">
          <a href="/catalog/..." class="dark_link">
            <span>Название товара</span>
          </a>
        </div>
      </td>
      <td class="information_wrapp main_item_wrapper">
        <div class="price_matrix_block">
          <div class="price" data-currency="RUB" data-value="900">
            <span class="values_wrapper">
              <span class="price_value">900</span>
              <span class="price_currency"> руб.</span>
            </span>
            <span class="price_measure">/шт</span>
          </div>
        </div>
      </td>
    </tr>
  </table>
</div>
```

"По запросу":
```html
<div class="list_item_wrapp item_wrap item">
  <table class="list_item">
    <tr>
      <td class="description_wrapp item_info">
        <div class="item-title">
          <a href="/catalog/..." class="dark_link">
            <span>Fluke 792A Эталон сравнения постоянного и переменного напряжения</span>
          </a>
        </div>
      </td>
      <td class="information_wrapp main_item_wrapper">
        <div class="cost prices clearfix"></div>
        <div>
          <span class="small to-order btn btn-default">
            <span>Цена по запросу</span>
          </span>
        </div>
      </td>
    </tr>
  </table>
</div>
```

---

## 3. Цена

**Формат:**
- [x] `900 руб.` или `1 107 руб.` (пробелы как разделители тысяч, используется `&nbsp;` между тысячами)
- [ ] `1000.00 ₽` (точка)
- [ ] `1,000 ₽` (запятая)
- [ ] Другое: `_________________`

**Примеры:**
- `900 руб.` (цена меньше 1000)
- `1 309 руб.` (цена больше 1000, с неразрывным пробелом `&nbsp;` между тысячами)
- `1 107 руб.` (цена больше 1000, с неразрывным пробелом `&nbsp;`)

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
- Цена отображается в формате "900 руб." или "1 107 руб." (с неразрывным пробелом `&nbsp;` между тысячами)
- Когда цена отсутствует, показывается кнопка "Цена по запросу" с классом `.to-order span`
- Цена находится в `.price .price_value`, валюта в `.price_currency`
- Используется параметр `how=r` в URL поиска

---

## 7. Тестовые товары

1. `CEM DT-102` → цена: `1 309 руб.`
2. `CEM DT-103` → цена: `_________________` (нужно проверить)
3. `Fluke 792A` → цена: `Цена по запросу`
4. `Fluke 5790B AC Measurement Standard` → цена: `Цена по запросу`
5. "По запросу": `Fluke 792A` или `Fluke 5790B AC Measurement Standard`
6. "Снят": `_________________` (не обнаружено в примерах)
7. Не найден: `_________________` (нужно протестировать)

---

## 8. Конфигурация config.yaml

```yaml
parser:
  pribor_x:
    enabled: true
    base_url: "https://www.pribor-x.ru/"
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

**Примечание:** Найдены примеры товаров с реальными ценами: `CEM DT-102` (1 309 руб.) и другие мультиметры CEM.

