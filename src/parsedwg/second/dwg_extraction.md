# DWG Extraction — скрипты и структура БД

## Скрипты

### `scripts/extract_full_dwg.py`

Полное извлечение содержимого DWG/DXF файла в базу данных (таблицы `dwg_*`).

**Что делает:**
- Открывает DWG через ODA File Converter или DXF напрямую через ezdxf
- Последовательно записывает в БД: файл → слои → блок-определения → макеты → все примитивы → атрибуты блоков
- UUID генерируются на стороне Python, вставка идёт батчами (одним запросом на каждую группу)

**Запуск:**
```bash
PATH="/Applications/ODAFileConverter.app/Contents/MacOS:$PATH" \
PYTHONPATH=src .venv/bin/python scripts/extract_full_dwg.py path/to/file.dwg
```

---

### `scripts/verify_dwg_extraction.py`

Верификация полноты извлечения — проверяет что в БД записалось ровно то, что есть в файле.

**Четыре проверки:**
1. Количество примитивов по типам в каждом блоке (файл vs БД)
2. Все INSERT ссылаются на существующие блок-определения
3. Все примитивы ссылаются на существующие слои
4. Количество атрибутов у каждого INSERT совпадает (файл vs БД)

**Запуск:**
```bash
PATH="/Applications/ODAFileConverter.app/Contents/MacOS:$PATH" \
PYTHONPATH=src .venv/bin/python scripts/verify_dwg_extraction.py path/to/file.dwg [file_id]
```

Если `file_id` не указан — берётся последняя запись в `dwg_file` для этого пути.

---

## Структура БД

Все таблицы с префиксом `dwg_` связаны через `file_id` — каждая запись принадлежит конкретному файлу.

### Иерархия связей

```
dwg_file
  ├── dwg_layer          (слои файла)
  ├── dwg_block_def      (блок-определения)
  │     └── dwg_layout   (макеты → блок-определение)
  └── dwg_entity         (примитивы → блок-определение + слой)
        └── dwg_attrib   (атрибуты → примитив INSERT)
```

---

### `dwg_file` — загруженный файл

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid | PK |
| `path` | text | Абсолютный путь к файлу на диске |
| `md5` | varchar | MD5-хэш файла (для проверки дублей) |
| `dxf_version` | text | Версия формата (AC1027 = AutoCAD 2018 и т.п.) |
| `created_at` | timestamptz | Время загрузки |

---

### `dwg_layer` — слои файла

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid | PK |
| `file_id` | uuid | FK → dwg_file |
| `name` | text | Имя слоя (например, `A-WALL`, `0`) |
| `color` | int | Цвет слоя (ACI-индекс) |
| `linetype` | text | Тип линии (Continuous, DASHED и т.п.) |
| `lineweight` | int | Толщина линии |
| `is_on` | bool | Слой включён |
| `is_frozen` | bool | Слой заморожен |
| `is_locked` | bool | Слой заблокирован |

---

### `dwg_block_def` — блок-определения

Блок — именованный набор примитивов, переиспользуемый через INSERT. Layout-блоки (`*Model_Space`, `*Paper_Space*`) — это пространства модели и листов.

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid | PK |
| `file_id` | uuid | FK → dwg_file |
| `name` | text | Имя блока |
| `is_layout_block` | bool | `true` для Model/Paper Space |
| `base_x` | float | Базовая точка блока X |
| `base_y` | float | Базовая точка блока Y |
| `base_z` | float | Базовая точка блока Z |

---

### `dwg_layout` — макеты (листы)

Макет — именованный вид: Modelspace (рабочее пространство) или Paperspace (лист для печати). Каждый макет привязан к своему блок-определению.

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid | PK |
| `file_id` | uuid | FK → dwg_file |
| `block_def_id` | uuid | FK → dwg_block_def |
| `name` | text | Имя макета |
| `is_modelspace` | bool | `true` для Model Space |
| `tab_order` | int | Порядок вкладки в AutoCAD |

---

### `dwg_entity` — примитивы

Все графические объекты внутри блоков: линии, дуги, тексты, вставки блоков (INSERT), штриховки и т.д.

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid | PK |
| `file_id` | uuid | FK → dwg_file |
| `block_def_id` | uuid | FK → dwg_block_def (в каком блоке находится) |
| `layer_id` | uuid | FK → dwg_layer (на каком слое) |
| `entity_type` | text | Тип примитива: `LINE`, `ARC`, `TEXT`, `INSERT`, `HATCH` и т.д. |
| `handle` | text | Уникальный идентификатор объекта внутри DWG-файла |
| `insert_x` | float | Координата вставки или начальная точка X |
| `insert_y` | float | Координата вставки или начальная точка Y |
| `insert_z` | float | Координата вставки или начальная точка Z |
| `ref_block_def_id` | uuid | FK → dwg_block_def (только для INSERT: на какой блок ссылается) |
| `text_value` | text | Текстовое содержимое (для TEXT, MTEXT, ATTRIB) |
| `length` | float | Зарезервировано (не заполняется) |
| `area` | float | Зарезервировано (не заполняется) |
| `dxf_data` | jsonb | Все DXF-атрибуты объекта в сыром виде |

---

### `dwg_attrib` — атрибуты блоков

Значения атрибутов, привязанных к конкретной вставке блока (INSERT). Например, у блока двери атрибут `Марка_двери = ДВ-01`.

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid | PK |
| `file_id` | uuid | FK → dwg_file |
| `entity_id` | uuid | FK → dwg_entity (родительский INSERT) |
| `tag` | text | Имя атрибута (например, `МАРКА`, `ПОЗИЦИЯ`) |
| `value` | text | Значение атрибута |
| `is_visible` | bool | Видим ли атрибут на чертеже |
| `insert_x` | float | Координата размещения текста атрибута X |
| `insert_y` | float | Координата размещения текста атрибута Y |
| `insert_z` | float | Координата размещения текста атрибута Z |
| `dxf_data` | jsonb | Все DXF-атрибуты в сыром виде |
