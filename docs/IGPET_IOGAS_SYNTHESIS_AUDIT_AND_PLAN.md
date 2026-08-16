# PetroLab: IgPet → ioGAS
## Независимый аудит текущей реализации и план продуктового синтеза

Дата аудита: 2026-08-16  
Базовая ветка: `refactor/v0158-master-backlog`  
Базовый commit: `35b3e30f2a12b6fde71cbcc93cf853dbc5737906`  
Связанный draft PR: #87 (`v0.15.8+: Airtable/JMP/Origin master backlog`)

---

## 0. Решение в одной фразе

Целевая модель PetroLab:

> **IgPet на входе, ioGAS после первого результата.**
>
> **Fast first plot, deep second step.**

Пользователь должен получить первый научно осмысленный результат почти без настройки, а затем иметь возможность бесшовно углубляться в данные: выделять точки, открывать связанные представления, сравнивать источники, скрывать серии, строить статистику, переходить к изображениям, сохранять состояние исследования и возвращаться к нему без повторного выбора данных.

Это не два режима программы и не два интерфейса. Это один непрерывный workflow с постепенным раскрытием сложности.

### Целевой пользовательский контракт

1. Если PetroLab уже знает текущие данные, программа **не должна спрашивать их повторно**.
2. Если PetroLab может предложить научно корректный первый график, он должен **показать его сразу**.
3. Для первого полезного графика требуется не более **одного осмысленного действия после выбора контекста**.
4. После построения графика вся глубина исследования становится доступна **без потери текущего отбора и состояния**.
5. Таблица, графики, PCA, clustering, профили и связанные изображения должны работать с одной идентичностью анализа — `analysis_id`.
6. `Selection`, `Filter`, `Hide`, `Exclude`, `Work Group` и `Generation` — разные сущности и никогда не должны подменять друг друга.
7. Быстрота не должна достигаться угадыванием научно неоднозначных вещей. Fe speciation, неясная фаза, единицы и другие научно значимые неоднозначности по-прежнему требуют явного решения или безопасного unresolved state.

---

# 1. Что именно берём от референсов

## 1.1. IgPet: скорость входа и предметность

Нужны не визуальный стиль и не старая файловая архитектура IgPet, а четыре свойства:

- пользователь формулирует задачу научным языком, а не языком UI;
- первый график появляется очень быстро;
- разумные defaults используются до того, как пользователь начал ручную настройку;
- частые операции требуют одного-двух осмысленных действий.

Целевой эквивалент в PetroLab:

`контекст данных → рекомендуемое научное действие → готовый график`.

Примеры:

- mica → наиболее полезная слюдяная XY-диаграмма;
- clinopyroxene → диагностическая XY/ternary;
- whole-rock → TAS/Harker;
- trace-element dataset → REE/spider;
- mixed minerals → сначала phase review, затем диагностические графики;
- exact selection from search → график строится именно для этого selection, без повторного выбора dataset.

## 1.2. ioGAS: глубина исследования

Берём не ribbon и не плотный desktop UI, а поведение:

- один data universe;
- много представлений тех же записей;
- linked brushing;
- единый selection;
- независимые visibility/filter/exclusion states;
- быстрый переход между таблицей, графиками и статистикой;
- сохранение исследовательского состояния;
- повторно применимые templates отдельно от checkpoints конкретной сессии.

Целевой эквивалент:

`первый график → выделение → все связанные представления → сравнение → интерпретация → сохранение состояния`.

## 1.3. Как это соотносится с уже принятым Airtable/JMP/Origin reference model

Текущую reference model не нужно отменять. Нужна иерархия:

### Макроуровень продукта

**IgPet → ioGAS** отвечает на вопрос: «Как пользователь входит в анализ и как растёт глубина?»

### Микроуровень взаимодействий

- **Airtable** — как устроена рабочая таблица и представления;
- **JMP** — как работают selection, row states и linked exploration;
- **OriginPro** — как устроены PlotSpec, multi-panel и публикационные настройки.

То есть новый принцип не конкурирует с текущим backlog v0.15.8. Он объясняет, **в какой последовательности пользователь должен встретить уже реализуемые механизмы**.

---

# 2. Беспристрастный аудит текущего состояния

Обозначения:

- **STRONG** — реализовано хорошо и соответствует цели;
- **PARTIAL** — основа есть, но пользовательский сценарий неполный;
- **DISCONNECTED** — механизм написан, но не встроен в основной путь;
- **DEBT** — работает, но форма реализации мешает целевой модели;
- **MISSING** — важного механизма пока нет;
- **AHEAD** — в данном узком аспекте PetroLab делает больше/безопаснее референсов.

---

## 2.1. IgPet-слой: быстрый первый результат

### A. Быстрый безопасный импорт — AHEAD

`petrolab/ui/pages/quick_import.py`, `petrolab/ui/intake_workflow.py`, import services.

Уже есть:

- preview до записи;
- распознавание oxide/trace columns;
- контроль неоднозначных канонических полей;
- подсчёт `<DL` / `<LOD`;
- научно значимый вопрос о FeO/Fe2O3 только при реальной неоднозначности;
- запрет на тихое угадывание;
- автоматическая обработка high-confidence mineral assignment;
- unresolved/mixed state вместо выдуманной фазы;
- отсутствие partial write при ошибке;
- post-import actions.

Это уже сильнее простого IgPet-подхода «открыл таблицу и построил»: PetroLab сохраняет скорость, но добавляет scientific safety.

### B. Один пользовательский вход «Добавить данные» — STRONG / PARTIAL

`petrolab/ui/pages/add_data.py` уже формулирует единый маршрут:

`файл → листы/колонки → Sample → проверка → сохранение → изображения`.

Положительно:

- основной sidebar не показывает несколько competing imports;
- литература и собственные анализы различаются provenance, а не отдельной моделью данных;
- изображения встроены в тот же intake story.

Остаточный долг:

- внутри codebase ещё остаются `quick_import`, `data_intake`, `universal_intake`, wrappers и compatibility routes;
- это допустимо как transitional internals, но они не должны продолжать развиваться как самостоятельные продукты;
- все новые импортные возможности должны добавляться в canonical intake, а старые маршруты — постепенно превращаться в adapters/redirects.

### C. Mineral-aware Smart Start — AHEAD, BUT DISCONNECTED

`petrolab/smart_start.py` уже содержит curated recommendations для mica, clinopyroxene, orthopyroxene, garnet, olivine, feldspar, spinel, Fe-Ti oxides, apatite, perovskite, nepheline, carbonate, titanite, zircon и др.

Сильная сторона:

- рекомендация учитывает реальный набор доступных колонок;
- есть fallback;
- есть mineral-aware XY и ternary candidates;
- это потенциально умнее статического списка диаграмм IgPet.

Главная проблема:

> **Smart Start существует как capability, но не является главным путём к графику.**

`plots_dashboard.py` по-прежнему предлагает пользователю вручную выбрать datasets, minerals, X, Y и grouping до появления первого осмысленного результата.

Это сейчас самый большой разрыв IgPet-части.

### D. Post-import → useful plot — PARTIAL

После импорта есть действие «Построить график», но оно в основном приводит пользователя в plot workspace, где требуется повторная настройка.

Цель:

- import завершён;
- DataUniverse уже известен;
- mineral/data type уже известны или оценены;
- PetroLab создаёт первый `PlotSpec` автоматически;
- пользователь сразу видит график.

### E. Первый график при входе в «Графики» — MISSING

Если известен текущий WorkContext / exact selection, PetroLab должен открыть уже готовый рекомендованный график.

Сейчас данные часто приходится заново подтверждать и выбирать оси.

### F. «Быстрое построение / Расширенный редактор» — DEBT

Сегментированный верхнеуровневый выбор режима в `plots_dashboard.py` функционально понятен, но противоречит целевой модели.

Проблема:

- создаёт две ментальные модели программы;
- заставляет пользователя заранее решать, насколько «продвинутым» он хочет быть;
- усложняет возврат из advanced к обычному исследованию;
- снижает ощущение бесшовного нарастания возможностей.

Цель:

- один Plot Workbench;
- первый слой минимален;
- X/Y, group, source, axes доступны сразу компактно;
- глубокие настройки раскрываются контекстно;
- advanced editor остаётся внутренним capability/handoff, а не вторым продуктом.

---

# 3. ioGAS-слой: linked exploration

## 3.1. Canonical SelectionContext — STRONG

`petrolab/ui/selection_context.py`

Это одна из лучших частей текущей архитектуры.

Уже есть:

- selection по immutable `analysis_id`;
- Replace / Add / Subtract;
- revision/origin state;
- независимые row display states;
- `hidden` отдельно от `excluded`;
- `labelled`, display colors и markers отдельно от научной классификации.

Это правильная фундаментальная модель. Её **не нужно переписывать**.

## 3.2. Linked XY brushing — STRONG

`petrolab/ui/xy_components.py`

Уже есть:

- point selection;
- rectangle;
- lasso;
- pan;
- запись выбора в canonical SelectionContext;
- чтение того же selection для подсветки;
- Replace/Add/Subtract controls;
- сохранение идентичности по analysis_id.

Это уже настоящее linked-exploration поведение, а не декоративная имитация.

## 3.3. Selection action bar — STRONG / PARTIAL

`petrolab/ui/selection_components.py`

Хорошо реализовано разделение:

- transient selection;
- Work Group;
- formal Generation;
- display states;
- export/secondary actions.

Осталось обеспечить, чтобы **один и тот же action bar** был доступен во всех relevant views и не дублировался локальными вариантами.

## 3.4. PCA / clustering ↔ linked selection — STRONG

`petrolab/ui/pages/statistics.py`

Положительно:

- statistical selection входит в общий SelectionContext;
- Exclude влияет на расчёт, Hide — нет;
- CoDA/CLR semantics явно учитываются;
- программа не должна автоматически изобретать pseudocount без достаточного основания.

В узком аспекте scientific safety это сильнее типичного generic exploratory software.

## 3.5. Series Manager — STRONG

`petrolab/ui/plot_manager.py`

Уже есть важное различие:

- `Show/Hide series` — presentation state;
- `Select series` — selection operation;
- row Hide / Exclude — другие states.

Это прямо поддерживает сценарий:

`Article A + Article B → compare → turn A off without deleting/filtering the records`.

Такую модель нужно сохранить.

## 3.6. PlotSpec — STRONG

`petrolab/ui/plot_spec.py`, `advanced_plot_handoff.py`.

Уже есть canonical описание графика, которое позволяет переносить:

- data scope;
- X/Y;
- grouping;
- source visibility;
- styles;
- axes;
- другие plot settings.

Это правильная база для seamless quick → deep → multi-panel → publication.

## 3.7. Multi-panel and panel manager — STRONG / PARTIAL

`linked_panels.py`, `panel_manager.py`, `multi_panel.py`.

Инфраструктура уже сильная:

- несколько linked panels;
- panel manager;
- перенос текущего PlotSpec;
- selection propagation.

Но пользовательский сценарий всё ещё чувствуется как переход в отдельный инструмент. Цель — `+ Добавить график` внутри текущей исследовательской поверхности, а не ощущение запуска другого модуля.

## 3.8. Canonical Table Workspace — STRONG, но миграция не завершена

`petrolab/ui/analysis_table.py`, `table_view_state.py`, `view_presets.py`, `table_filters.py`, `table_grouping.py`, `table_scope.py`.

Это уже хороший Airtable/JMP-like фундамент:

- один набор records;
- views без копирования данных;
- Search / Fields / Filter / Group / Sort / View;
- saved table views;
- row selection;
- linked SelectionContext;
- record detail.

Однако одновременно остаются другие пользовательские table experiences.

---

# 4. Где сейчас реализовано криво или переходно

Это не означает, что код плохой. В большинстве случаев проблема — **дублирование уже после появления нового правильного ядра**.

## 4.1. Три разных лица таблицы — DEBT

Сейчас существуют как минимум:

1. canonical `analysis_table.py` внутри object workspace;
2. `analyses_dashboard.py` — мощный editable data editor с drafts/sync;
3. `database_browser.py` — ещё один browser/filter/selection route.

Проблема для пользователя:

- «где моя настоящая таблица?»;
- разные способы select/filter/edit;
- разные route/session handoffs;
- трудно выстроить один muscle memory.

При этом **движок analyses_dashboard нельзя выбрасывать**: local drafts, conflict detection, safe Excel sync и backups очень ценны.

Правильное решение:

- `analysis_table.py` становится единственным normal-use Table Workspace;
- «Редактировать» переводит ту же таблицу в edit surface или открывает contextual editor;
- draft/sync backend переиспользуется без переписывания;
- `database_browser` перестаёт иметь собственную модель selection и остаётся catalog/admin/detail layer либо становится compatibility redirect.

## 4.2. `workflow_*` session keys — DEBT

В codebase ещё много маршрутов вида:

- `workflow_plot_dataset_ids`;
- `workflow_plot_analysis_ids`;
- `workflow_edit_*`;
- `workflow_table_*`;
- специальные keys для thermodynamics и т. д.

Они были разумным мостом до появления canonical SelectionContext/WorkContext/PlotSpec.

Теперь их избыток создаёт риск:

- два источника истины;
- state drift;
- повторный выбор данных;
- сложные hidden handoffs;
- разные правила очистки state.

Правило миграции:

- Data scope → WorkContext/DataUniverse;
- transient rows → SelectionContext;
- graph definition → PlotSpec;
- persistent table representation → TableViewState;
- специальные `workflow_*` keys допускаются только как compatibility adapter на границе старого route.

## 4.3. Object Workspace всё ещё page/section oriented — PARTIAL

`object_workspace.py` уже делает очень важную вещь: Sample/Dataset становятся единым контекстом, где доступны analyses/images/entities/thermodynamics.

Но это пока набор sections/tabs, а не единая investigative surface.

Например, пользователь не видит одновременно:

- таблицу;
- основной график;
- secondary graph/PCA;
- details selected point.

Цель — wide-screen workbench, где несколько представлений сосуществуют и реагируют на один selection.

## 4.4. Global Search выглядит сильнее, чем фактически ищет — PARTIAL

`global_search.py` хорошо собирает сущности и передаёт exact IDs, но text matching в основном literal/contains.

Запрос уровня:

`apatite Smith 2024`

не должен зависеть от того, встречается ли вся строка целиком в одном поле.

Нужно:

- token AND semantics;
- typed filter chips;
- Mineral / Source / Article / Sample / Method / Generation facets;
- additive result selection;
- search result scope как нормальный DataUniverse, а не временный маршрут.

## 4.5. Publication controls слишком близко к first-plot flow — DEBT

Быстрый exploration screen не должен визуально конкурировать с SVG/PNG/XLSX manifest/export controls.

Экспорт должен быть доступен сразу, но вторично:

- compact Export button;
- раскрываемая панель;
- либо handoff в Publication Composer.

Первый экран графика должен оставаться аналитическим.

---

# 5. Где PetroLab уже лучше референсов

Важно: речь не о «PetroLab лучше ioGAS вообще», а о конкретных узких качествах текущей архитектуры.

## 5.1. Scientific-safe import

PetroLab не просто читает columns, а моделирует неоднозначность и умеет отказаться от угадывания.

Особенно сильны:

- Fe ambiguity handling;
- oxide/trace semantics;
- provenance;
- unresolved mixed phase;
- no partial write;
- pre-save preview.

## 5.2. Mineral-aware Smart Start

Статическая библиотека диаграмм полезна, но PetroLab уже способен выбирать рекомендации на основе:

- минерала;
- фактически доступных колонок;
- типа данных.

После правильной интеграции это может быть удобнее статического меню IgPet.

## 5.3. Physical-world model

PetroLab знает не только rows, но и:

- Sample;
- Grain;
- Point;
- Thin section;
- image;
- source/article;
- dataset;
- analytical provenance.

Это позволяет сделать то, чего generic EDA обычно не умеет: выбрать химическую точку и сразу увидеть физически связанный объект/фотографию.

## 5.4. Scientific interpretation separated from UI state

Очень важное решение:

- selection ≠ Work Group;
- Work Group ≠ Generation;
- Hidden ≠ Excluded;
- display style ≠ classification.

Это снижает риск превратить визуальный эксперимент в случайное изменение научной базы.

## 5.5. Safe editable source workflow

`analyses_dashboard.py` уже имеет:

- local draft;
- draft survives restart;
- conflict detection;
- explicit save;
- safe source Excel synchronization;
- backup before write.

Такую безопасность нужно перенести в единый Table Workspace, а не потерять при UX-консолидации.

## 5.6. Statistical scientific guardrails

В compositional workflows PetroLab уже пытается защищать пользователя от методологически неправильной Euclidean обработки и не скрывает assumptions.

Это должно остаться частью продукта даже при ускорении интерфейса.

---

# 6. Целевая архитектура пользовательского состояния

Нельзя создавать ещё один параллельный state manager. Нужно собрать уже существующие canonical state objects в одну понятную пользовательскую сессию.

## 6.1. DataUniverse

Нужна явная модель текущего «мира данных»:

```text
DataUniverse
- project_id
- dataset_ids
- exact_analysis_ids | null
- source/article constraints
- query/filter scope
- QC policy
- origin (import/search/sample/dataset/selection/recent)
```

Она должна либо расширить текущий WorkContext/DataScope, либо быть тонким immutable adapter над ними.

**Не создавать второй независимый источник истины.**

## 6.2. SelectionContext

Оставить существующий canonical implementation.

Содержит transient selected rows и операции selection.

## 6.3. RowDisplayStates

Оставить существующую модель:

- hidden;
- excluded;
- labelled;
- display color;
- display marker.

## 6.4. ScientificAction

Над существующим `smart_start.py` ввести пользовательский слой:

```text
ScientificAction
- id
- title
- kind: xy | ternary | ree | spider | tas | harker | classification | distribution
- required_columns
- confidence
- reason
- generated_plot_spec
- target_panel_type
```

Это не AI agent. Это deterministic domain recommendation layer.

## 6.5. PlotSpec

Сохранить текущий canonical PlotSpec.

Первый рекомендованный график, ручное изменение осей, multi-panel и publication должны использовать **один и тот же объект**, а не пересобирать настройки из UI widgets.

## 6.6. Exploration Workspace

Не нужен новый state duplicate. Нужен orchestration layer, который ссылается на existing canonical objects:

```text
ExplorationWorkspace
- data_universe_ref
- active_table_view_ref
- panel_specs[]
- active_panel_id
- selection_context_ref
- row_display_states_ref
```

## 6.7. WorkspaceSnapshot

Нужна новая persistent entity — аналог ioGAS checkpoint:

```text
WorkspaceSnapshot
- name
- project_id
- DataUniverse serialization
- TableViewState reference/state
- open PanelSpecs / PlotSpecs
- panel layout
- active panel
- selection (optional, explicit policy)
- row presentation states
- source/series visibility
- statistics view specs
- timestamp
```

Snapshot отвечает на вопрос:

> «Верни меня ровно туда, где я остановился».

## 6.8. AnalysisTemplate

Отдельно от Snapshot:

```text
AnalysisTemplate
- panel types
- X/Y or semantic variable aliases
- grouping
- styles
- axes
- scientific fields
- table view structure
- NO concrete dataset/analysis ids
```

Template отвечает на вопрос:

> «Примени мой стандартный способ анализа к другому набору».

Snapshot и Template нельзя объединять.

---

# 7. Целевой интерфейс Plot Workbench

## Состояние 1: только вошли

Показывается:

- текущий context chip: `Kandalaksha · mica · 612 analyses`;
- рекомендованный график уже построен;
- компактная строка:
  - `График`;
  - `X`;
  - `Y`;
  - `Цвет/группа`;
  - `Источники`;
  - `+ график`;
  - `Ещё`;
- основной canvas.

Не показывается сразу:

- длинный publication export block;
- manual field vertex editor;
- десятки style controls;
- отдельный выбор «быстрый или расширенный режим».

## Состояние 2: пользователь выделил точки

Без перехода на другую страницу появляются:

- `N selected`;
- `Open in table`;
- `Create Work Group`;
- `Add to Work Group`;
- `Approve Generation`;
- `Hide`;
- `Exclude`;
- `Label`;
- `Show linked image` если есть;
- `Clear selection`.

Та же selection подсвечена во всех открытых views.

## Состояние 3: пользователь нажал `+ график`

Появляется новая linked panel:

- recommended alternative;
- XY;
- ternary;
- distribution;
- PCA;
- cluster;
- profile — если применимо.

Selection не сбрасывается.

## Состояние 4: пользователь раскрывает «Ещё»

Только здесь появляются:

- log axes;
- precise ranges;
- marker internals;
- fields/envelopes;
- annotations;
- journal style;
- advanced handoff.

Это progressive disclosure вместо beginner/advanced split.

---

# 8. План реализации

## PHASE 0 — зафиксировать product contract и golden tests

### Задачи

1. Добавить product-flow rule в `.clinerules`.
2. Зафиксировать 10 golden workflows из раздела 10.
3. Добавить test helpers для проверки:
   - сохранения DataUniverse;
   - сохранения SelectionContext;
   - PlotSpec handoff;
   - количества обязательных пользовательских выборов до первого plot.
4. Не начинать новый large feature module до закрытия P0 flow gaps.

### Definition of done

- ни один новый plot/data route не создаёт альтернативный selection state;
- каждый новый workflow знает, какой canonical state object он читает и пишет;
- regression tests фиксируют context continuity.

---

## PHASE 1 — подключить Smart Start к реальному UI

**Приоритет: P0. Максимальный UX-эффект при минимальном архитектурном риске.**

### Файлы

- `petrolab/smart_start.py`;
- `petrolab/ui/pages/plots_dashboard.py`;
- `petrolab/ui/pages/quick_import.py`;
- `petrolab/ui/pages/home_dashboard.py`;
- `petrolab/ui/pages/object_workspace.py`;
- `petrolab/ui/pages/global_search.py`;
- новый тонкий orchestration module, например `petrolab/ui/scientific_actions.py`.

### Задачи

1. Обобщить `smart_start.recommendations()` в ranked `ScientificAction` API.
2. Рекомендации должны принимать уже известный DataUniverse, а не просить выбрать datasets заново.
3. При открытии `plots`:
   - если есть incoming PlotSpec → открыть его;
   - иначе если есть current DataUniverse → автоматически построить top recommendation;
   - иначе показать простой scope chooser.
4. После import:
   - `Открыть график` создаёт top recommended PlotSpec;
   - маршрут открывается уже с готовым графиком.
5. После Global Search:
   - `Построить` использует exact result IDs;
   - не требует повторно выбирать dataset/mineral.
6. После selection в table:
   - `Построить` создаёт PlotSpec по selected rows;
   - если selection пуст, используется visible/current universe.
7. Добавить compact selector `Рекомендовано / Другой график…`, а не экран настройки перед первым plot.
8. Использовать data-aware defaults и не показывать невозможные диаграммы.

### Acceptance

- import → useful plot: 1 действие после успешного сохранения;
- current Sample/Dataset → Plots: график виден без обязательного выбора X/Y;
- search exact selection → Plot: exact rows сохранены;
- mica/cpx/garnet/apatite/whole-rock regression fixtures получают корректные рекомендации;
- ни одна неоднозначная scientific transformation не происходит тихо.

---

## PHASE 2 — убрать разрыв «Быстро / Расширенно»

**Приоритет: P0.**

### Задачи

1. Убрать top-level segmented choice `Быстрое построение / Расширенный редактор` из normal workflow.
2. Оставить один Plot Workbench.
3. Всегда показывать компактные controls:
   - X;
   - Y;
   - Swap;
   - Group/Color;
   - Sources;
   - Add panel.
4. Перенести advanced controls в contextual disclosure:
   - `Оси`;
   - `Стиль`;
   - `Поля`;
   - `Подписи`;
   - `Публикация`.
5. Advanced editor может остаться internal route, но открывается через handoff с текущим PlotSpec.
6. Возврат из advanced обязан восстанавливать exact PlotSpec + DataUniverse + selection.

### Acceptance

- пользователь никогда не обязан выбирать уровень сложности до работы;
- quick → advanced → back не меняет данные, selection, series visibility и оси;
- first viewport не перегружен secondary controls.

---

## PHASE 3 — единый Exploration Workspace

**Приоритет: P1. Самый важный шаг к настоящему ioGAS-поведению.**

### Задачи

1. На широком экране создать one-work-surface layout:
   - left/upper compact context toolbar;
   - main chart canvas;
   - optional table panel;
   - optional second/third linked panel;
   - collapsible record/selection inspector.
2. `+ график` добавляет panel в текущий workspace, а не уводит в отдельный mental model.
3. Поддержать panel types:
   - XY;
   - ternary;
   - distribution;
   - PCA;
   - clustering;
   - grain profile when applicable.
4. Любая panel selection пишет в один SelectionContext.
5. Таблица читает тот же selection.
6. Narrow viewport fallback — tabs/stack, но state тот же.
7. Navigation to dedicated statistics/profile pages остаётся как deep editor, но не обязательна для обычного сравнения.

### Acceptance

- table + 2 plots одновременно видны на 1920×1080;
- lasso на plot A подсвечивает plot B и table;
- смена X/Y на plot B не сбрасывает selection;
- закрытие panel не удаляет data universe;
- opening PCA from current workspace не требует dataset reselection.

---

## PHASE 4 — единый Attribute / Series Manager

**Приоритет: P1.**

Сейчас нужные capabilities существуют, но распределены по series manager, source controls, style controls и table/grouping controls.

### Цель

Один понятный contextual drawer, который отвечает на четыре вопроса:

1. **Кто показан?**
2. **Как сгруппирован?**
3. **Как выглядит?**
4. **Что выбрано?**

### Задачи

1. Объединить normal-use controls для:
   - group by;
   - color;
   - marker;
   - size;
   - series visibility;
   - source/article visibility;
   - select series.
2. Визуально разделить:
   - Filter — universe;
   - Hide — presentation;
   - Exclude — calculations;
   - Select — transient selection.
3. Legend interactions:
   - click select series;
   - eye show/hide;
   - optional context menu for style.
4. Series style keyed by semantic group/category, чтобы одна категория выглядела одинаково во всех linked plots.

### Acceptance

Сценарий:

`Article A apatites → add Article B → compare → hide Article A → show A → select only B`

выполняется без ухода из workspace и без изменения database membership.

---

## PHASE 5 — одна таблица вместо трёх

**Приоритет: P1.**

### Задачи

1. Сделать `analysis_table.py` единственным normal-use Table Workspace.
2. Перенести в него как режим/контекстное действие возможности `analyses_dashboard.py`:
   - editable columns;
   - draft autosave;
   - conflict display;
   - explicit DB save;
   - safe Excel sync;
   - backup semantics.
3. Не переносить бизнес-логику копированием: использовать существующий analysis service/draft backend.
4. `database_browser.py`:
   - удалить/не развивать собственную selection toolbar;
   - использовать canonical table component;
   - оставить catalog/entity browsing там, где это реально отличается от analysis table.
5. Убрать user-facing необходимость понимать разницу между `workspace`, `database`, `analyses`.
6. Compatibility routes могут жить до следующего major cleanup.

### Acceptance

- один normal route «Данные»;
- из него доступны view/filter/group/select/edit/record detail;
- selection сохраняется при входе/выходе из edit mode;
- local draft survives restart;
- Excel conflict safety не ухудшена;
- нет второго пользовательского механизма фильтрации тех же analysis rows.

---

## PHASE 6 — семантический поиск и additive comparison

**Приоритет: P1/P2.**

### Задачи

1. Заменить literal whole-query matching на tokenized AND matching.
2. Добавить explicit facets/chips:
   - Mineral;
   - Sample;
   - Source/Article;
   - Dataset;
   - Method;
   - Generation;
   - Object/Thin section.
3. Поиск возвращает DataUniverse, а не временную копию dataset.
4. Additive action:
   - `Добавить результаты к текущему сравнению`.
5. Search result can be used as series/source group.
6. Поддержать workflow:
   - найти apatite from Article A;
   - открыть plot;
   - search/add apatite from Article B;
   - toggle either source.

### Acceptance

- query `apatite Smith 2024` работает как набор терминов/фасетов, а не exact substring;
- adding second source does not replace first by default;
- exact record IDs preserved;
- no dataset duplication.

---

## PHASE 7 — Checkpoints отдельно от Templates

**Приоритет: P2.**

### WorkspaceSnapshot

Добавить persistence layer, например `petrolab/workspace_snapshots.py`.

Сохранять:

- DataUniverse;
- TableViewState;
- open panels;
- PlotSpecs;
- panel layout;
- current source/series visibility;
- row presentation states;
- active panel;
- optional selection policy.

### AnalysisTemplate

Сохранять reusable analysis structure без concrete record IDs.

### Home

`Продолжить` должно показывать не только recent Sample/Dataset context, но и named/recent exploration snapshots.

### Acceptance

- закрыть PetroLab → открыть → выбрать recent snapshot → получить те же panels, axes, visible sources and context;
- template можно применить к другому compatible dataset;
- template не тащит concrete analysis ids;
- snapshot не превращается в новый dataset.

---

## PHASE 8 — убрать остаточную фрагментацию и отполировать первый viewport

**Приоритет: P2.**

### Задачи

1. Secondary export controls свернуть в один compact Export action.
2. Hidden compatibility routes перестать использовать в новых links.
3. Старые wrappers не получают новых функций.
4. Проверить terminology:
   - Analysis;
   - Selection;
   - Work Group;
   - Generation;
   - Filter;
   - Hide;
   - Exclude;
   - Source/Article;
   - View;
   - Snapshot;
   - Template.
5. Проверить 1366×768 и 1920×1080.
6. Убрать лишние headers/cards/vertical scroll до первого результата.
7. Context should be visible but compact:
   - project;
   - current universe;
   - visible N;
   - selected N.

---

## PHASE 9 — возможности, где PetroLab может уйти дальше ioGAS

Не P0. Делать после бесшовного core workflow.

### 9.1. Chemistry ↔ physical image linking

Выделение анализа на графике:

- показывает linked micrograph;
- подсвечивает точку/region на thin section;
- из изображения можно выбрать точку и увидеть её на всех chemistry plots.

### 9.2. Scientific recommendation ladder

После first plot PetroLab может рекомендовать next scientifically relevant actions:

- `Проверить на ternary`;
- `Посмотреть trace elements`;
- `Проверить PCA`;
- `Сравнить с литературой`;
- `Рассчитать APFU`.

Только deterministic, explainable recommendations; никаких скрытых изменений данных.

### 9.3. Method-aware linked point

Если одна физическая точка имеет EPMA + LA-ICP-MS + EDS, selection can expose a composite point without pretending these are the same measurement row.

Это потенциально сильное уникальное направление PetroLab.

---

# 9. Какие файлы трогать, а какие не переписывать

## Сохранять как canonical foundation

- `petrolab/ui/selection_context.py`;
- `petrolab/ui/plot_spec.py`;
- `petrolab/ui/table_view_state.py`;
- `petrolab/ui/analysis_table.py`;
- `petrolab/ui/plot_manager.py`;
- `petrolab/ui/linked_panels.py`;
- `petrolab/ui/panel_manager.py`;
- `petrolab/ui/work_context.py`;
- import services;
- analysis draft/sync services.

## Основные integration targets

- `petrolab/smart_start.py`;
- `petrolab/ui/pages/plots_dashboard.py`;
- `petrolab/ui/pages/home_dashboard.py`;
- `petrolab/ui/pages/object_workspace.py`;
- `petrolab/ui/pages/global_search.py`;
- `petrolab/ui/pages/quick_import.py`;
- `petrolab/ui/pages/statistics.py`;
- `petrolab/ui/pages/multi_panel.py`;
- `petrolab/ui/source_controls.py`;
- `petrolab/ui/plot_style_controls.py`.

## Migration / consolidation targets

- `petrolab/ui/pages/analyses_dashboard.py`;
- `petrolab/ui/pages/database_browser.py`;
- legacy `workflow_*` state bridges;
- hidden compatibility wrappers/routes.

## Новые небольшие модули, которые оправданы

- `petrolab/ui/scientific_actions.py` — orchestration around Smart Start;
- `petrolab/workspace_snapshots.py` — persistence of exploration state;
- при необходимости `petrolab/ui/exploration_workspace.py` — composition layer, **не новый state source**.

---

# 10. Golden end-to-end workflows

Эти сценарии важнее количества отдельных feature tests.

## G1. Fresh mineral Excel → useful plot

1. Add data.
2. Preview.
3. Resolve only genuine ambiguity.
4. Save.
5. Click `Открыть график`.
6. Useful mineral-aware plot already visible.
7. Lasso outliers.
8. Open selected rows in table.

**Fail:** user must reselect dataset/mineral/X/Y before seeing anything.

## G2. Existing Sample → immediate exploration

1. Search/open Sample.
2. Click Plots.
3. Recommended plot visible.
4. `+ график` → second plot.
5. Selection in either highlights both and table.

## G3. Article A vs Article B

1. Search `apatite + Article A`.
2. Plot.
3. Add `apatite + Article B`.
4. Distinct source series visible.
5. Hide A.
6. Show A.
7. Select B only.

No copied dataset and no loss of A membership.

## G4. PCA → XY → ternary

1. Open current universe in PCA.
2. Select cluster.
3. Open XY.
4. Same analyses highlighted.
5. Change axes.
6. Selection persists.
7. Open ternary.
8. Same analyses highlighted.

## G5. Filter vs Hide vs Exclude

1. Filter to mineral/source scope.
2. Hide one series.
3. Exclude selected outliers.
4. Plot still knows hidden rows exist.
5. Statistics ignores excluded rows but not hidden rows.
6. Undo/restore independently.

## G6. Save exact research state

1. Open table + 3 panels.
2. Customize axes and styles.
3. Hide one source.
4. Save snapshot.
5. Restart app.
6. Restore snapshot.
7. Same universe/layout/panels/axes/source visibility returns.

## G7. Quick → advanced → back

1. Start from recommended plot.
2. Change one axis.
3. Open advanced controls.
4. Add scientific field/manual publication setting.
5. Return.
6. No PlotSpec/selection/state loss.

## G8. Safe editing

1. Select analyses.
2. Edit metadata/value through canonical table.
3. Draft autosaves.
4. Restart.
5. Draft returns.
6. Source changed externally → conflict shown.
7. Safe sync creates backup.

## G9. Chemistry ↔ image

1. Select point on graph.
2. Record detail shows linked image/thin section if available.
3. Open image.
4. Selected chemistry point remains context.

## G10. Analytical graph → publication

1. Build linked exploration plot.
2. Send exact PlotSpec to Publication Composer.
3. Modify publication layout.
4. Analytical workspace remains unchanged.

---

# 11. Product metrics / Definition of Done

Не использовать количество функций как главный показатель.

## Speed

- current context → first useful plot: **0–1 deliberate action**;
- Home → recent context → useful plot: **≤2 deliberate actions**;
- post-import → useful plot: **1 deliberate action**;
- no re-selection of dataset when context already knows it.

## Continuity

- selection survives axis changes;
- selection survives adding/removing panels;
- selection transfers table ↔ plots ↔ PCA/clustering;
- exact data universe survives route handoff;
- advanced handoff round-trip is lossless.

## Cognitive load

- no Beginner/Advanced product split;
- one normal data table;
- one normal Add Data path;
- one canonical meaning for Hide, Exclude, Filter and Select;
- first viewport contains only controls needed for current task.

## Scientific integrity

- no silent resolution of Fe ambiguity;
- no phase guess below confidence threshold;
- no silent deletion of QC-poor data;
- no hidden conversion of presentation state into calculation exclusion;
- source/provenance retained.

## Persistence

- reusable views do not duplicate datasets;
- snapshots restore exploration state;
- templates are reusable across datasets;
- snapshot and template semantics remain separate.

## Regression

- Windows install/smoke workflows stay green;
- import regression stays green;
- existing SelectionContext/PlotSpec/TableViewState tests stay green;
- golden workflows receive integration/browser coverage.

---

# 12. Приоритеты

## P0 — делать первым

1. Wire Smart Start into actual Plots entry.
2. Post-import/search/table-selection → ready PlotSpec.
3. Remove mandatory dataset/X/Y reselection where context exists.
4. Replace Quick/Advanced split with progressive disclosure.
5. Preserve one canonical state path during all handoffs.

## P1

6. Unified Exploration Workspace.
7. Unified Attribute/Series Manager.
8. One Table Workspace, edit mode inside it.
9. Retire duplicate selection/filter toolbars.
10. Semantic/additive source search workflow.

## P2

11. WorkspaceSnapshot.
12. AnalysisTemplate.
13. Home/Continue integration.
14. Visual density/polish and compatibility-route cleanup.

## P3

15. Bidirectional image linked brushing.
16. Next-action scientific recommendations.
17. Composite physical point exploration across analytical methods.

---

# 13. Что НЕ надо делать

1. **Не переписывать database core ради UX-синтеза.**
2. **Не создавать второй SelectionContext.**
3. **Не создавать второй PlotSpec.**
4. **Не делать отдельные Beginner и Expert версии интерфейса.**
5. **Не копировать ribbon ioGAS.**
6. **Не копировать старый UI IgPet.**
7. **Не создавать temporary datasets для selection/filter/source comparison.**
8. **Не ослаблять scientific safety ради one-click UX.**
9. **Не добавлять новый top-level module, если задача решается контекстным действием внутри workspace.**
10. **Не продолжать развивать compatibility pages как равноправные продукты.**
11. **Не считать новый feature завершённым, если он заставляет повторно выбирать уже известные данные.**
12. **Не считать linked exploration завершённым, пока selection не переживает переходы и изменения представления.**

---

# 14. Итоговая оценка текущего PetroLab

Оценка — инженерная, не количественный benchmark.

### IgPet-like speed of entry

- capability foundation: **сильная**;
- реальный пользовательский путь: **средний**;
- причина: Smart Start и безопасный import уже есть, но первый plot всё ещё слишком часто требует конфигурации.

### ioGAS-like linked exploration

- state architecture: **сильная**;
- linked XY/statistical interaction: **сильная**;
- unified visible workspace: **средняя / недособранная**;
- persistence of full exploration state: **пока слабая**.

### PetroLab-specific scientific layer

- provenance/safe import: **очень сильная**;
- physical sample/point/image model: **сильнее generic EDA model**;
- scientific interpretation states: **сильная**;
- safe editing/source synchronization: **сильная**.

## Главный вывод

PetroLab уже не нужно «догонять IgPet и ioGAS по списку функций».

Большая часть необходимых низкоуровневых механизмов уже существует. Главная работа следующего этапа — **собрать их в правильную последовательность взаимодействия**:

```text
OPEN CONTEXT
    ↓
INSTANT SCIENTIFICALLY REASONABLE RESULT      ← IgPet strength
    ↓
SELECT / BRUSH / COMPARE
    ↓
TABLE + PLOTS + PCA + SOURCES + IMAGES
    ↓
GROUP / INTERPRET / CALCULATE
    ↓
SAVE RESEARCH STATE                           ← ioGAS strength
    ↓
PUBLICATION
```

Если выполнить P0 и P1 именно как workflow consolidation, PetroLab перестанет ощущаться как набор очень хороших модулей и начнёт ощущаться как **одна научная среда, которая сначала проста, а затем становится глубокой ровно настолько, насколько это нужно пользователю**.
