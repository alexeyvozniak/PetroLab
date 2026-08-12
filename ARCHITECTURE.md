# Архитектура ПетроЛаба

## Текущее состояние

ПетроЛаб уже содержит несколько самостоятельных подсистем: импорт и связь с Excel, SQLite-базу анализов, минералогические пересчёты, изображения, построение графиков, экспорт и журнал изменений. Исторически значительная часть orchestration/UI выросла внутри одного `app.py`.

Рефакторинг выполняется эволюционно: сначала выносятся чистые функции и константы, затем страницы, затем сценарии приложения. На каждом этапе пользовательское поведение сохраняется и проверяется CI.

## Целевая структура

```text
PetroLab/
├── app.py                    # entrypoint + navigation only
├── petrolab/
│   ├── db.py                 # current persistence API; later split gradually
│   ├── dataframe_utils.py    # pure dataframe helpers
│   ├── io_utils.py           # reading tabular files and hashes
│   ├── plotting.py           # figure construction/export helpers
│   ├── plot_presets.py       # journal/display presets
│   ├── sources.py            # linked source synchronization
│   ├── minerals/             # scientific domain logic
│   ├── services/             # application use-cases (target)
│   └── ui/                   # Streamlit pages/components (target)
└── tests_*.py
```

## Направление зависимостей

Допустимо:

```text
UI -> services -> domain / persistence / I/O
UI -> pure presentation helpers
services -> domain / persistence / I/O
plotting -> pandas / matplotlib
minerals -> pandas / numpy + scientific constants
```

Нежелательно:

```text
minerals -> Streamlit
DB -> Streamlit
pure helpers -> session_state
services -> UI
```

## Ключевые инварианты

- `main` запускается на Windows.
- Научная формула не зависит от UI.
- База хранит стабильный `_analysis_id` каждой точки.
- Синхронизация Excel создаёт backup до изменения файла.
- Изображения связываются через стабильные ID/области привязки, а не через позицию строки в текущем DataFrame.
- Рефакторинг не меняет численные результаты без отдельного научного изменения и теста.

## План декомпозиции

### Этап 1 — foundation

- вынести чистые dataframe helpers;
- вынести журнальные пресеты;
- убрать deprecated Streamlit API;
- убрать предупреждения PyArrow;
- зафиксировать правила разработки.

### Этап 2 — UI pages

Создать `petrolab/ui/pages/` и переносить по одной странице за PR:

1. Projects;
2. Sources/import;
3. Unified database;
4. Images;
5. Formula recalculation/minerals;
6. Plot Studio;
7. Export/change log.

`app.py` после этого должен только инициализировать приложение и выбрать страницу.

### Этап 3 — services

Из страниц выносятся сценарии, которые меняют состояние:

- import service;
- Excel synchronization service;
- image asset service;
- export service;
- plot recipe service.

### Этап 4 — persistence cleanup

Большой `db.py` постепенно делится на небольшие repository-модули по сущностям без изменения схемы БД одним скачком.

## Почему не переписываем всё сразу

ПетроЛаб уже работает с научными данными и исходными Excel. Большая одномоментная перепись дала бы красивую структуру ценой высокого риска тихих регрессий. Поэтому каждый перенос должен быть механическим, тестируемым и небольшим.
