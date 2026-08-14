# Архитектура ПетроЛаба

## Назначение

ПетроЛаб — локальное Streamlit-приложение для минералогических анализов, валовой геохимии пород, изображений, статистики и подготовки публикационных материалов. Основной принцип: **измеренные данные, производные расчёты и пользовательская интерпретация хранятся отдельно и связываются стабильными идентификаторами**.

`app.py` содержит только bootstrap, тему и навигацию. Научные формулы, файловые операции, статистика и хранение данных не зависят от Streamlit и тестируются отдельно.

## Текущая структура v0.12

```text
PetroLab/
├── app.py                              # bootstrap + grouped navigation only
├── petrolab/
│   ├── db.py                           # established mineral-analysis persistence API
│   ├── storage.py                      # storage bootstrap/migrations
│   ├── storage_extensions.py           # normalized whole-rock tables
│   ├── sources.py                      # low-level linked Excel synchronization
│   ├── column_schema.py                # column names, units, source/canonical semantics
│   ├── measurement_semantics.py        # Fe/measurement interpretation
│   ├── analysis_identity.py            # stable point matching across refreshes
│   ├── derived.py                      # persisted derived results + provenance/staleness
│   ├── analysis_groups.py              # local work groups by _analysis_id
│   ├── plotting.py                     # generic publication XY
│   ├── interactive_plotting.py         # Plotly selection by immutable _analysis_id
│   ├── ternary_data.py                 # ternary QC/normalisation/geometry
│   ├── ternary_presets.py              # mineral templates/source-specific projections
│   ├── ternary_overlays.py             # sourced ternary classification geometry
│   ├── ternary_plotting.py             # mineral-agnostic ternary renderer
│   ├── scientific_overlays.py           # sourced kimberlite/lamprophyre XY boundaries
│   ├── scientific_plotting.py           # generic scientific publication XY renderer
│   ├── extended_plotting.py             # REE/spider/histogram/boxplot engines
│   ├── visualization_presets.py         # science/figure/table/marker registries
│   ├── statistics.py                    # PCA/clustering/correlation/summary statistics
│   ├── article_tables.py                # publication XLSX table builder
│   ├── rock_plotting.py                 # TAS/Harker/isotope/Rhodes rendering
│   ├── settings_service.py              # local user defaults
│   ├── release_notes.py                 # in-app changelog
│   ├── measurement_registry.py          # physical targets and method-specific observations
│   ├── slides.py                        # slide masters/previews, fields and spatial markers
│   ├── minerals/                        # scientific mineral-formula domain
│   ├── services/                        # application use-cases
│   │   ├── import_service.py
│   │   ├── analysis_service.py
│   │   ├── formula_service.py
│   │   ├── image_service.py
│   │   ├── rock_service.py
│   │   └── rock_image_service.py
│   ├── repositories/                    # explicit persistence operations
│   │   ├── analysis_repository.py
│   │   ├── image_repository.py
│   │   └── rock_repository.py
│   └── ui/
│       ├── components.py                # shared UI components
│       ├── data_scope.py                # common project/dataset/mineral selection
│       ├── plot_style_controls.py        # shared publication/marker controls
│       ├── ternary_controls.py           # ternary preset/label/overlay controls
│       ├── rock_plots.py                 # whole-rock plot orchestration only
│       ├── theme.py                      # responsive visual theme
│       └── pages/                        # independent task pages
└── tests_*.py
```

## Направление зависимостей

Допустимо:

```text
UI pages -> UI components -> services / repositories / pure plotting helpers
services -> domain / repositories / I/O
repositories -> SQLite/storage API
mineral formulas -> pandas / numpy + scientific constants
scientific plotting -> source-aware overlay registry + generic renderer
statistics -> pandas / numpy / scikit-learn
whole-rock UI -> rock service/repository + rock plotting
```

Недопустимо:

```text
minerals -> Streamlit
repositories -> Streamlit
statistics core -> SQLite writes
services -> UI
source-specific field boundaries -> Streamlit page or generic renderer
filter/cluster/work-group -> destructive source-Excel mutation
whole-rock chemistry -> analysis_rows
```

## Слои данных

### Минеральный анализ

`analysis_rows` хранит только импортированную/отредактированную аналитическую строку с происхождением. `_analysis_id` — стабильный ключ точки.

### Derived-результат

APFU, end-members и другие расчётные величины сохраняются отдельно с provenance и hash исходной строки. После изменения исходного анализа старый derived-результат автоматически считается stale.

### Локальная интерпретация

Рабочая группа, исключение из рисунка, кластер и другие исследовательские решения не записываются в лабораторный Excel как будто это измеренные данные.

### Литературный Study/Source

`studies` хранит библиографию или происхождение данных, а `dataset_studies` связывает один Study с одним или несколькими datasets. При чтении анализов `attach_study_metadata()` добавляет вычисляемый контекст статьи к строкам по `_dataset_id`; химия в `analysis_rows` при этом не переписывается.

Пользовательский фильтр работает по `Статья / источник`, а не только по имени Excel или dataset. Поэтому все таблицы одной публикации включаются и выключаются как одна серия. Выключение источника является обратимым состоянием текущего отбора:

- не удаляет строки и связь с публикацией;
- не меняет QC и минералогическую классификацию;
- одинаково применяется к preview, публикационному экспорту и supplementary;
- сохраняется в recipe/manifest как `visible_sources` и `hidden_sources`.

Клик по Plotly-легенде считается только временным экранным preview. Для воспроизводимого исключения используется общий source visibility control.

### Порода

Порода — самостоятельный объект, а не ещё один mineral dataset. Для неё нормализованы отдельные таблицы:

```text
rock_samples
   ├── rock_compositions
   ├── rock_isotopes
   ├── rock_images
   └── rock_mineral_links -> datasets
```

Связь `rock_mineral_links` позволяет использовать минералы и валовый состав вместе без копирования анализов.

## Научные диаграммы

Существуют три разных уровня:

1. **Generic XY/ternary** — любые числовые поля.
2. **Scientific presets** — рекомендованные оси и источник.
3. **Source-aware overlays** — точные литературные границы только там, где геометрия подтверждена и покрыта regression tests.

Научные коэффициенты Wyatt/Grütter/Morimoto и другие границы не должны появляться внутри Streamlit-страницы или generic renderer.

Если известны только литературные оси, но не проверенные координаты поля, preset показывает оси и citation **без приблизительного overlay**.

## REE и multi-element patterns

Нормированный pattern использует только концентрации с известной единицей (`ppm` / `µg/g`-equivalent). Bare `La`, `Rb` и т. п. с неизвестной единицей допускаются только в ненормированном графике. Это защищает от тихого принятия неизвестной величины за ppm.

Нормировочные наборы хранятся централизованно рядом с citation, а порядок элементов — отдельно от UI.

## Статистика

`statistics.py` — чистый вычислительный слой:

- descriptive statistics;
- Pearson/Spearman/Kendall correlations;
- PCA;
- K-means;
- agglomerative clustering.

Статистический модуль не пишет в `analysis_rows`. Пользователь может явно преобразовать найденный кластер в локальную рабочую группу через UI.

## Публикационные presets

`visualization_presets.py` — единый реестр:

- размеров/типографики рисунка;
- табличного оформления;
- гармоничных последовательностей маркеров;
- научных готовых диаграмм.

Старый `JOURNAL_PRESETS` является совместимым view этого общего реестра, чтобы XY/ternary и новые scientific/rock графики не расходились по оформлению.

Preset — это стартовая конфигурация, а не блокировка интерфейса: пользователь может изменить шрифт, размер, подписи, сетку, легенду, маркеры и подписи точек перед экспортом.

## Whole-rock и mineral–rock

Whole-rock модуль отделяет хранение состава от интерпретации.

- TAS — sourced classification rendering.
- Harker/binary — generic compositional scatter.
- REE/spider — тот же unit-safe engine, что у минералов.
- isotope XY — generic numerical comparison.
- Rhodes/Kd — явный equilibrium-screening proxy для связанной породы и оливина.

Whole-rock состав **не приравнивается автоматически к расплаву**. Калибровка термометра или Kd добавляется только как отдельная source-specific формула с требованиями к входам, давлению/redox и regression test.

## UI/UX

Навигация сгруппирована по задачам, а не по внутренним модулям:

```text
Работа с данными
Графики и статистика
Породы и изображения
Публикация
Справка и настройки
```

Общие выборы project/dataset/mineral находятся в `ui/data_scope.py`; publication controls — в `ui/plot_style_controls.py`. Responsive CSS и shared image gallery отвечают за узкие окна и не позволяют разным страницам реализовывать мобильную логику независимо.

Контекст `Study/Source` присоединяется централизованно и доступен универсальному поиску, фильтрам базы, quick XY, расширенному редактору, статистическим scope и таблицам для статьи. UI не реализует отдельное несогласованное сопоставление источников на каждой странице.

## Ключевые инварианты

- `main` запускается на Windows.
- `app.py` остаётся тонкой навигационной оболочкой.
- Научная формула не зависит от UI.
- `_analysis_id` не зависит от текущего положения строки DataFrame.
- Derived-результат не маскируется под измерение.
- Excel backup создаётся до двусторонней записи.
- Неизвестная единица остаётся неизвестной.
- FeO, FeOt, Fe2O3 и Fe2O3t различаются семантически.
- Изображение не перепривязывается к другой точке только из-за номера строки.
- Фильтр/кластер не удаляют исходный анализ.
- Выключение целой статьи на графике не удаляет данные и фиксируется в manifest.
- Литературная схема хранит source/DOI рядом с вычислением/геометрией.
- Generic renderer не содержит минералогических научных порогов.
- Rock data физически отделены от mineral analysis rows.
- Удаление породы не оставляет её локальные изображения сиротами.

## Как добавлять новую научную схему

1. Определить, это generic plot, axis preset или настоящий sourced overlay.
2. Добавить запись в scientific/ternary registry.
3. Если нужна особая проекция, реализовать pure source-specific transformation.
4. Координаты/порог хранить только в domain overlay/calibration module.
5. Добавить citation/DOI и ограничения применимости.
6. Добавить regression test на контрольные точки и экспорт.
7. Прогнать branch Windows CI, PR CI и post-merge `main` CI.

## Как добавлять mineral–rock калибровку

1. Создать отдельную функцию с явными единицами и обязательными входами.
2. Зафиксировать первичный источник и формулу.
3. Отдельно определить, допускается ли whole-rock как melt proxy.
4. Не применять калибровку автоматически ко всем связанным минералам.
5. Тестировать опубликованный пример/контрольный состав.
6. UI должен показывать assumptions и диапазон применимости рядом с результатом.

## Почему изменения делаются небольшими слоями

ПетроЛаб работает с научными данными и исходными Excel. Большая одномоментная перепись повышает риск тихой регрессии сильнее, чем улучшает внешний вид кода. Поэтому механический рефакторинг, научное изменение и новая пользовательская функция по возможности разделяются, а каждый новый слой защищается Windows regression tests и UI AppTest.
