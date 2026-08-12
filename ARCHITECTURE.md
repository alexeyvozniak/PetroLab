# Архитектура ПетроЛаба

## Текущее состояние

ПетроЛаб построен как локальное Streamlit-приложение с несколькими независимыми слоями: импорт и связь с Excel, SQLite-база анализов, минералогические пересчёты, derived-результаты, изображения, XY/ternary-графики, экспорт и журнал изменений.

`app.py` больше не содержит рабочую бизнес-логику: он инициализирует приложение и выбирает страницу. Научные расчёты, файловые операции и хранение данных отделены от Streamlit и тестируются независимо.

## Текущая структура

```text
PetroLab/
├── app.py                         # entrypoint + navigation only
├── petrolab/
│   ├── db.py                      # established persistence API
│   ├── dataframe_utils.py         # pure dataframe helpers
│   ├── io_utils.py                # tabular I/O and hashes
│   ├── sources.py                 # low-level linked Excel synchronization
│   ├── derived.py                 # persisted formula results + provenance/staleness
│   ├── analysis_identity.py       # stable analysis matching across refreshes
│   ├── analysis_groups.py         # local working groups by _analysis_id
│   ├── plotting.py                # publication XY rendering/export
│   ├── interactive_plotting.py    # diagnostic Plotly XY selection
│   ├── ternary_data.py            # ternary normalization/QC/geometry
│   ├── ternary_presets.py         # mineral templates + source projections
│   ├── ternary_overlays.py        # sourced classification boundaries/classifiers
│   ├── ternary_plotting.py        # generic Plotly/Matplotlib ternary renderer
│   ├── minerals/                  # scientific formula domain
│   ├── services/                  # application use-cases
│   ├── repositories/              # explicit persistence transactions
│   └── ui/
│       ├── components.py          # shared Streamlit components
│       ├── ternary_controls.py    # preset/custom/overlay controls
│       └── pages/                 # independent workspace pages
└── tests_*.py
```

## Направление зависимостей

Допустимо:

```text
UI -> services / repositories / pure presentation helpers
services -> domain / repositories / I/O
repositories -> persistence API
plotting -> pandas / matplotlib / plotly
ternary_plotting -> ternary_data + generic overlay model
ternary_presets -> scientific source projections
ternary_overlays -> sourced classification geometry and classifiers
minerals -> pandas / numpy + scientific constants
```

Недопустимо:

```text
minerals -> Streamlit
repositories -> Streamlit
pure helpers -> session_state
services -> UI
source-specific field names -> generic plotting renderer
```

## Ключевые инварианты

- `main` запускается на Windows.
- Научная формула не зависит от UI.
- База хранит стабильный `_analysis_id` каждой точки.
- Derived-результат хранится отдельно от исходного анализа и становится stale после изменения источника.
- Синхронизация Excel создаёт backup до изменения файла.
- Изображения связываются через стабильные ID/области привязки, а не через позицию строки в текущем DataFrame.
- Фильтры и рабочие группы не переписывают исходный Excel.
- Рефакторинг не меняет численные научные результаты без отдельного обоснованного изменения и теста.
- Литературная классификационная схема хранит источник и DOI рядом с координатами границ.
- Generic renderer не содержит минералогических названий или научных порогов.

## Ternary: разделение ответственности

Ternary-подсистема специально разделена на небольшие слои:

```text
raw + current derived data
        ↓
ternary_presets.py        # какие компоненты нужны и нужна ли source projection
        ↓
ternary_data.py           # QC + нормировка + координаты
        ↓
ternary_overlays.py       # классификация + литературные линии/подписи
        ↓
ternary_plotting.py       # только отрисовка
        ↓
ui/ternary_controls.py    # выбор пользователем
        ↓
ui/pages/plots_ternary.py # orchestration, filters, selection, export, recipes
```

Например, строгий Morimoto Wo–En–Fs preset не переиспользует старые Fe²⁺-only end-member поля как будто они полностью соответствуют источнику. Он создаёт локальную, не сохраняемую в исходный Excel проекцию из APFU-компонентов, требуемых выбранной схемой. Это позволяет исправлять или добавлять научные классификации без скрытого изменения уже сохранённых результатов формул.

## Как добавлять новую классификационную диаграмму

1. Добавить `TernaryPreset` и перечислить требуемые колонки.
2. Если источнику нужна особая проекция, реализовать её как pure function в `ternary_presets.py` или отдельном domain-модуле.
3. Если нужны литературные поля, добавить `TernaryOverlay` с полной ссылкой, DOI и тестируемыми координатами.
4. Не добавлять научные пороги в `ternary_plotting.py` или Streamlit-страницу.
5. Добавить regression tests на границы, классификацию, проекцию и экспорт.
6. Прогнать Windows branch CI, PR CI и post-merge `main` CI.

## Почему не переписываем всё сразу

ПетроЛаб работает с научными данными и исходными Excel. Большая одномоментная перепись дала бы красивую структуру ценой высокого риска тихих регрессий. Поэтому новые возможности добавляются через маленькие слои с явными зависимостями и тестами, а изменение научного смысла отделяется от механического рефакторинга.
