Полнотекстовый поиск в PostgreSQL
==================================

Конспект статьи «Готовим полнотекстовый поиск в Postgres. Часть 1»
(https://habr.com/ru/articles/442170/).

.. contents::
   :depth: 2


Контекст задачи
---------------

480K+ документов, ~3.6 Гб текста. Исходный Sphinx тормозил:

- 8 Гб ОЗУ под индекс.
- 40 минут на пересборку раз в сутки — нет консистентности.
- Медленный обмен между двумя сервисами.

Выбор пал на встроенный FTS PostgreSQL: автообновление индекса, одна БД вместо двух.


Наивный подход — без индексов
------------------------------

.. code-block:: sql

   SELECT id, ts_rank(to_tsvector(text), plainto_tsquery('запрос'))
   FROM documents
   WHERE to_tsvector(text) @@ plainto_tsquery('запрос')
   ORDER BY ts_rank(to_tsvector(text), plainto_tsquery('запрос')) DESC;

**Проблемы:**

- Полный seq scan — ``to_tsvector`` и ``ts_rank`` вызываются для **каждой** строки.
- На 12K документов: 35–420 секунд.


Первый шаг — функциональный GIN-индекс
----------------------------------------

.. code-block:: sql

   CREATE INDEX idx_gin_document
   ON documents USING gin (to_tsvector('russian', text));

- Построение: ~26 с на тестовой базе.
- Время запроса: **12 секунд**. Лучше, но ещё медленно — ``to_tsvector`` всё равно
  пересчитывается при каждом запросе.


Второй шаг — материализовать ``tsvector`` в БД
------------------------------------------------

Два варианта хранения вектора:

1. Добавить колонку ``tsvector`` в исходную таблицу — нет join'ов при поиске.
2. Отдельная таблица ``one-to-one`` — основная таблица не растёт, бэкап не тронет
   вектора.

Автор выбирает вариант 2: таблица ``documents_documentvector`` с полем ``text tsvector``,
GIN-индекс на неё.

Поисковый запрос:

.. code-block:: sql

   SELECT d.id, ts_rank(v.text, plainto_tsquery('запрос'))
   FROM documents d
   JOIN documents_documentvector v ON v.document_id = d.id
   WHERE v.text @@ plainto_tsquery('запрос')
   ORDER BY ts_rank(v.text, plainto_tsquery('запрос')) DESC;

**Результат: 48 мс** (с ``ts_rank``) против исходных 420 секунд.


Третий шаг — узкое место: ``ts_rank``
--------------------------------------

Тот же запрос без ``ORDER BY ts_rank``: **1.7 мс** — в ~30 раз быстрее.

Проблема: ``ts_rank`` считается для каждой найденной строки **до** сортировки,
уменьшить выборку нельзя.

На боевой базе: 150 мс без сортировки, **1.5 секунды** с ``ts_rank``.

Кэширование частых запросов — паллиатив, сложен в сопровождении.


Индекс RUM (анонс Части 2)
---------------------------

Расширение **RUM** хранит в индексе дополнительные данные (взвешенные позиции
токенов) и позволяет вычислять «расстояние» между ``tsvector`` и ``tsquery``
**прямо при скане**, возвращая результаты уже отсортированными — без отдельного
``ts_rank``.

Автор обещает сравнить GIN и RUM по минусам, плюсам и области применения.


Ключевые функции
-----------------

.. list-table::
   :header-rows: 1

   * - Функция
     - Назначение
   * - ``to_tsvector('russian', text)``
     - Токенизация + стемминг под языковую конфигурацию
   * - ``plainto_tsquery('запрос')``
     - Простой запрос (AND по умолчанию)
   * - ``websearch_to_tsquery(...)``
     - Поддерживает кавычки, ``-минус``, ``OR``
   * - ``ts_rank(tsvector, tsquery)``
     - Релевантность (дорогая операция)
   * - ``@@``
     - Оператор совпадения tsvector и tsquery


Примеры запросов к модели Entity
---------------------------------

В проекте FTS уже настроен: ``search_entities`` в ``src/parsedwg/db.py`` использует
``websearch_to_tsquery`` по ``entity_text`` с fallback на ``name || ' ' || description``.
GIN-индекс ``ix_entity_entity_text_gin`` добавлен в миграции ``0007_entity_text_tsvector``.

Пересборка entity_text для уже загруженных данных
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Если нужно массово обновить ``entity_text`` после изменения правил наполнения:

.. code-block:: sql

   UPDATE entity
   SET entity_text = to_tsvector(
     'russian',
     concat_ws(' ', coalesce(name, ''), coalesce(description, ''))
   )
   WHERE entity_type <> 'primitive';

   UPDATE entity
   SET entity_text = to_tsvector('russian', coalesce(description, ''))
   WHERE entity_type = 'primitive';

   REINDEX INDEX ix_entity_entity_text_gin;

Базовый поиск по имени и описанию
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: sql

   SELECT id, name, description, entity_type
   FROM entity
   WHERE entity_text @@ websearch_to_tsquery('russian', 'спринклер')
   ORDER BY ts_rank(entity_text, websearch_to_tsquery('russian', 'спринклер')) DESC
   LIMIT 20;

Базовый поиск с fallback на старую схему
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: sql

   SELECT id, name, description, entity_type
   FROM entity
   WHERE entity_text @@ websearch_to_tsquery('russian', 'спринклер')
    OR to_tsvector('russian', coalesce(name, '') || ' ' || coalesce(description, ''))
       @@ websearch_to_tsquery('russian', 'спринклер')
   ORDER BY
     CASE WHEN entity_text @@ websearch_to_tsquery('russian', 'спринклер')
      THEN 1 ELSE 0 END DESC,
     ts_rank(entity_text, websearch_to_tsquery('russian', 'спринклер')) DESC,
     ts_rank(
       to_tsvector('russian', coalesce(name, '') || ' ' || coalesce(description, '')),
       websearch_to_tsquery('russian', 'спринклер')
     ) DESC
   LIMIT 20;

Поиск только по типу сущности
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: sql

   -- Только layout-ы с упоминанием вентиляции
   SELECT id, name, description, start_from
   FROM entity
   WHERE entity_type = 'layout'
     AND to_tsvector('russian', coalesce(name, '') || ' ' || coalesce(description, ''))
         @@ websearch_to_tsquery('russian', 'вентиляция')
   ORDER BY ts_rank(
       to_tsvector('russian', coalesce(name, '') || ' ' || coalesce(description, '')),
       websearch_to_tsquery('russian', 'вентиляция')
   ) DESC;

Точная фраза
^^^^^^^^^^^^

.. code-block:: sql

   -- websearch_to_tsquery поддерживает кавычки (plainto_tsquery — нет)
   SELECT id, name, entity_type, start_from
   FROM entity
   WHERE to_tsvector('russian', coalesce(name, '') || ' ' || coalesce(description, ''))
       @@ websearch_to_tsquery('russian', '"противопожарная защита"');

Исключающий поиск
^^^^^^^^^^^^^^^^^

.. code-block:: sql

   SELECT id, name, entity_type
   FROM entity
   WHERE to_tsvector('russian', coalesce(name, '') || ' ' || coalesce(description, ''))
       @@ websearch_to_tsquery('russian', 'водоснабжение -канализация');

Поиск по дереву — все потомки файла
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: sql

   -- Все блоки и примитивы файлов, где в имени/описании родителя есть "кровля"
   SELECT child.id, child.name, child.entity_type, child.description
   FROM entity child
   JOIN entity parent ON child.parent_id = parent.id
   WHERE to_tsvector('russian', coalesce(parent.name, '') || ' ' || coalesce(parent.description, ''))
       @@ websearch_to_tsquery('russian', 'кровля')
     AND child.entity_type IN ('block', 'primitive');

Без сортировки по релевантности (быстрее в 10–30 раз)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Если порядок по релевантности не критичен — убрать ``ts_rank``:

.. code-block:: sql

   SELECT id, name, entity_type, start_from
   FROM entity
   WHERE to_tsvector('russian', coalesce(name, '') || ' ' || coalesce(description, ''))
       @@ websearch_to_tsquery('russian', 'этаж автоматика')
   LIMIT 50;


Текущее состояние в проекте
-----------------------------

- GIN-индекс ``ix_entity_entity_text_gin`` на ``entity_text``
  создан в миграции ``0007_entity_text_tsvector``.
- ``search_entities`` в ``db.py`` использует ``websearch_to_tsquery`` и
  ранжирует результаты с приоритетом совпадений в ``entity_text``.
- Остается fallback на ``name + description`` для обратной совместимости.
