=============================================
parsedwg — извлечение данных из ``DWG``/``DXF``
=============================================

.. contents:: Содержание

Описание
========

В репозитории реализован **MVP веб-сервиса** для автоматизации обработки строительных чертежей
и сопроводительных документов:

* извлечение позиций из ``DWG`` / ``DXF``;
* учёт данных из пояснительной записки (``TXT``, ``RST``, ``MD``, ``DOCX``);
* формирование итоговой Excel-книги с листами:

  - ``СО`` — спецификация оборудования и материалов;
  - ``ВОР`` — ведомость объёмов работ;
  - ``Смета`` — заготовка сметного расчёта;
  - ``Сводка`` — краткая статистика по выгрузке.

Обработка PDF-файлов не поддерживается.

Что сделано
===========

* подготовлен веб-интерфейс на ``FastAPI``;
* добавлен CLI-режим для пакетного запуска;
* реализован парсинг текста и атрибутов из ``DXF`` через ``ezdxf``;
* для ``DWG`` предусмотрена конвертация в ``DXF`` через внешний
  ``ODA File Converter``;
* одинаковые позиции автоматически агрегируются по наименованию,
  единице измерения и разделу.

Быстрый запуск
==============

1. Установить зависимости:

   .. code-block:: bash

    ./.venv/bin/pip install -e ".[dev,web]"

  Для CLI без веб-интерфейса достаточно:

  .. code-block:: bash

    ./.venv/bin/pip install -e ".[dev]"

  Для AI-возможностей и экспорта PNG/SVG дополнительно:

  .. code-block:: bash

    ./.venv/bin/pip install -e ".[dev,web,ai,viz]"

2. Запустить веб-приложение:

   .. code-block:: bash

      PYTHONPATH=src ./.venv/bin/uvicorn parsedwg.web:app --host 127.0.0.1 --port 8000

3. Открыть в браузере страницу:

   .. code-block:: text

      http://127.0.0.1:8000

Lock-файлы
==========

Фиксированные зависимости генерируются из ``pyproject.toml`` через ``pip-tools``.
Редактировать вручную нужно только ``pyproject.toml``.

Выбирайте один lock-файл под нужный сценарий и устанавливайте его в чистое
виртуальное окружение:

.. code-block:: bash

  ./.venv/bin/pip install -r requirements.txt

.. code-block:: bash

  ./.venv/bin/pip install -r requirements-dev.txt

.. code-block:: bash

  ./.venv/bin/pip install -r requirements-full.txt

``requirements.txt`` фиксирует базовое ядро,
``requirements-dev.txt`` добавляет инструменты разработки,
``requirements-full.txt`` включает полный стек: ``dev + web + ai + viz``.

Пересборка lock-файлов после изменения зависимостей:

.. code-block:: bash

  ./.venv/bin/pip install -e ".[dev]"
  ./.venv/bin/pip-compile --strip-extras pyproject.toml -o requirements.txt
  ./.venv/bin/pip-compile --strip-extras --extra dev pyproject.toml -o requirements-dev.txt
  ./.venv/bin/pip-compile --strip-extras --extra dev --extra web --extra ai --extra viz pyproject.toml -o requirements-full.txt

CLI-режим
=========

Можно сформировать отчёт без веб-интерфейса:

.. code-block:: bash

   PYTHONPATH=src ./.venv/bin/python -m parsedwg path/to/file.dxf \
       --note path/to/note.docx \
       --output reports/result.xlsx

Также доступна фильтрация DXF с копированием только ``TEXT`` и ``MTEXT``:

.. code-block:: bash

   PYTHONPATH=src ./.venv/bin/python -m parsedwg copy-text path/to/source.dxf path/to/text-only.dxf

Если нужно брать только объекты из modelspace без листов, используйте:

.. code-block:: bash

   PYTHONPATH=src ./.venv/bin/python -m parsedwg copy-text \
       path/to/source.dxf path/to/text-only.dxf --modelspace-only

Структура проекта
=================

.. code-block:: text

   src/parsedwg/
     models.py      # модель нормализованной позиции
     parsers.py     # извлечение данных из DWG/DXF и записок
     service.py     # orchestration / агрегация
     reporting.py   # генерация Excel-файла
     web.py         # FastAPI веб-интерфейс
   tests/
     test_pipeline.py
   templates/
     index.html
   docs/
     architecture.rst

Ограничения MVP
===============

* прямой разбор бинарного ``DWG`` без внешнего конвертера не выполняется;
* смета создаётся как рабочая заготовка с формулой ``количество × цена``;
* точность результата зависит от стандартизированности подписей на чертежах.

Формулировка исходной задачи
============================

Разработать программное обеспечение для автоматизации следующего процесса:

* извлечение данных из строительных чертежей рабочей и проектной документации формата DWG и
  сопроводительных документов (пояснительная записка) и формирование на их основании документов:

  - «Спецификация оборудования и материалов» (СО);
  - «Ведомость объёмов работ» (ВОР);
  - «Смета».

