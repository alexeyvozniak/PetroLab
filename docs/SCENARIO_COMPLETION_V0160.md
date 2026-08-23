# PetroLab v0.16: Scenario Completion on Product Design

Branch: `product/v0160-scenario-completion`

Base: `product/task-first-shell-v0160`

This branch completes the main user scenarios on top of the Product Design shell. Product Design is the source of truth for UX and visual architecture. Existing branches may contribute functionality and proven scientific mechanics, but they must not reintroduce old navigation, parallel workflows, technical top-level pages, or temporary runtime hotfix wrappers.

Primary navigation remains:

`Обзор | Образцы | Поиск | Шлифы | Анализы | Добавить`

Everything expert-only or infrequent stays contextual or under `Дополнительно`.

## 0. Shared foundation before scenario work

Do not create a separate state model for each scenario. Reuse the same scientific identities and contexts:

- `project_id`
- `sample_id`
- `dataset_id`
- `analysis_id`
- `thin_section_id`
- `image_id`
- physical point / field
- `SelectionContext`
- `WorkContext`
- source / study
- Work Group
- PetroLab Generation
- Textural zone

`analysis_id` remains the immutable identity of an analytical row.

Keep these concepts separate:

- Selection = what is being investigated now
- Work Group = temporary scientific grouping
- Generation = confirmed interpretation
- Textural zone = observed morphological zone
- Hide = temporarily hide from plots
- Exclude = omit from statistics
- mineral assignment = scientific mineral interpretation
- source chemistry = immutable raw chemistry

Implementation rules:

1. Do not create new `v0160_*_hotfix.py` files or runtime monkeypatch layers.
2. Put new logic in canonical modules.
3. Page-to-page handoffs must carry stable IDs instead of reconstructing state from labels.
4. Destructive actions must be reversible or explicitly confirmed.
5. Do not expose internal IDs to users unless they are genuinely useful.
6. Reuse one Selection across Workspace, tables, plots, thin sections, statistics, Formulae and thermodynamics.

---

## 1. Cross-project global database search

### User story

The user remembers that apatite, phlogopite, a sample or a literature dataset was loaded before, but does not remember the project. They should be able to search the whole PetroLab library, inspect where the result lives, open it, or link the existing dataset into the current project without copying chemistry.

### UX

On the main Search page add scope:

`В текущем проекте | Во всей PetroLab`

Default: current project.

When searching the whole library, group results into:

- Анализы
- Образцы
- Шлифы и изображения
- Источники

Each result must show context, for example:

`19 ТР-1`

`Турий мыс · Проект «Кола»`

`43 анализа · 3 изображения · 1 шлиф`

or:

`Apatite · Reguir et al., 2009`

`Проект «Литературные данные» · 124 анализа`

For objects from another project provide:

- `Открыть`
- `Использовать в текущем проекте`

The second action must create a project linkage only. It must not clone analysis rows, alter provenance, or move the source dataset.

After linking, show:

`Данные подключены к проекту. Исходный набор остался в проекте «…».`

### Implementation

Primary UI: `petrolab/ui/pages/global_search.py`.

Do not create a second global-search page. Introduce a small search service that returns normalized hits including project context and stable object IDs. A possible contract is:

```python
SearchHit(
    kind,
    project_id,
    sample_id,
    dataset_id,
    thin_section_id,
    image_id,
    analysis_ids,
    title,
    subtitle,
    source_label,
)
```

The exact data structure may differ, but Search UI should not manually maintain five incompatible result lists.

### Acceptance

1. Project A contains apatite.
2. Project B contains phlogopite.
3. Open Project B and search `apatite` in current project: no hit.
4. Switch to whole PetroLab: apatite from A appears.
5. Click `Использовать в текущем проекте`.
6. The same dataset becomes available in B for Search, Workspace and Plot.
7. Source analysis-row count does not increase.

---

## 2. Search as an object browser

### User story

Search must not end in passive tables. Any found Sample, dataset, thin section, image or source should be directly openable while preserving the search state and current Selection.

### UX

Keep grouped tabs, but make each result interactive.

Example object result:

`19 ТР-1`

`Sample · Турий мыс`

`43 анализа · 5 изображений · 1 шлиф`

`Открыть →`

Example source result:

`Smith et al., 2020`

`124 анализа · Apatite`

`Открыть | Добавить к сравнению`

Image results should include thumbnail, type, Sample and thin-section context. Clicking an image opens it in its correct object context.

### Preserve search state

Search → object → back must restore:

- search text
- active scope
- active tab
- current Selection
- relevant scroll/navigation state when practical

Do not clear Search merely because another page was opened.

### Analysis result actions

Provide:

- `Выбрать все найденные`
- `Добавить к Selection`
- `Вычесть из Selection`
- `Построить график`
- `Сравнить`
- `Скрыть на графиках`

Use canonical `SelectionContext`. Do not create a special search selection.

### Source visibility

Sources should be individually toggleable, for example:

- ☑ Мои анализы
- ☑ Smith et al., 2020
- ☑ Petrov et al., 2019
- ☐ Ivanov et al., 2021

Changing source visibility is temporary view state. It must not delete rows or mutate the DataUniverse.

### Acceptance

1. Search `19 ТР-1`.
2. Open a non-first matching Sample or image.
3. Return to Search.
4. Query, scope and tab are intact.
5. Select all analytical hits and send them to Plot.
6. Exact `analysis_id` membership is preserved.

---

## 3. Excel → images → exact physical linking

This is a P0 workflow.

### Main flow

The user uploads one workbook and a batch of images.

PetroLab should:

1. classify uploaded files;
2. inspect all workbook sheets;
3. normalize/confirm columns and provenance;
4. map rows to Sample and mineral context;
5. safely import analyses;
6. then start the image-linking flow automatically.

After import show:

`Добавлено 683 анализа. Теперь разберём 10 изображений.`

### Image-linking screen

Left side, about 60% width:

- large image preview
- image counter `2 / 10`
- previous/next controls
- thumbnail strip

Right side:

`К чему относится изображение?`

Fields in natural physical order:

- Sample
- Шлиф / препарат
- Поле / Grain
- Тип изображения
- аналитические точки
- Textural zone where applicable

Avoid making dataset selection the primary mental model. Dataset may remain an implementation detail or an advanced fallback.

### Exact analytical links

Under `Какие анализы находятся здесь?` provide search and checklist controls with:

- point / grain / label search
- `Выбрать найденные`
- `Очистить`

The saved relation must resolve to exact immutable analysis IDs.

### Physical fields on thin section

Fields/areas on a thin section may only be:

- rectangle
- square

Do not introduce arbitrary polygons for physical fields.

Lasso remains a plot Selection tool, not a geometry tool for thin-section fields.

The intended hierarchy is:

```text
Sample
└── Thin section
    ├── Field 1
    │   ├── BSE image
    │   ├── Point 1
    │   ├── Point 2
    │   └── Point 3
    └── Field 2
        └── ...
```

A Field is a physical object, not a dataset.

### Multiple images of the same field

A field may have multiple representations:

- overview image
- BSE
- enlarged BSE
- PPL
- XPL
- element map
- SEM / EDS image

These should share the same physical context and Selection.

### Textural zone

Textural zone is attached to chosen analysis IDs and remains separate from Work Group and Generation.

Common values may include Core, Rim, Reaction zone and Altered zone, while allowing custom terms.

### Inbox for unlinked images

Separate these actions:

- `Сохранить без привязки`
- `Не импортировать`

`Сохранить без привязки` creates a real image asset and places it into:

`Входящие`

The Thin Sections / Images area should show an Inbox count, for example:

`Входящие · 12`

From Inbox the user can later:

- link to Sample
- link to thin section
- link to Field
- change image type
- delete

### Atomic batch save

Keep rollback semantics. A failure on image 8 must not silently leave an ambiguous half-saved batch 1–7.

### Final screen

After successful save:

`10 изображений добавлено`

`8 связано`

`2 находятся во Входящих`

Actions:

- `Открыть шлиф`
- `Посмотреть связанные анализы`
- `Разобрать Входящие`
- `Готово`

### Acceptance

1. Upload a multi-sheet workbook and 10 images.
2. Import analyses.
3. Link 8 images to Sample/thin-section/Field/analysis IDs.
4. Save 2 into Inbox.
5. Restart the app.
6. All 10 assets remain available; 8 retain exact links and 2 remain in Inbox.

---

## 4. Unified Sample / Thin Section Workspace

This should become the main working surface of PetroLab. Do not add a new top-level route. Extend the existing Object Workspace.

### User story

Open `19 ТР-1` and inspect everything related to that Sample without bouncing through database, images, analyses, plots and thin sections as independent applications.

### Header

Breadcrumb:

`Турий мыс / 19 ТР-1`

Title:

`19 ТР-1`

Context badges:

- `243 анализа`
- `2 шлифа`
- `14 изображений`
- `3 источника`
- minerals/phases summary

Primary actions:

- `+ Добавить`
- `Построить график`
- `Сравнить`

### Workspace sections

Preserve the Product Design structure:

- Обзор
- Анализы
- Изображения
- Шлифы и объекты
- Расчёты

All sections use the same Selection.

### Thin-section working view

Layout concept:

```text
┌────────────────────────────┬───────────────────┐
│                            │ Точки / Selection │
│       большой шлиф         │                   │
│                            │ P-1               │
│  □ Field 1                 │ P-2               │
│             □ Field 2      │ P-3               │
│   • точка                  │                   │
│                            │                   │
├────────────────────────────┴───────────────────┤
│ связанные анализы / химия                      │
└────────────────────────────────────────────────┘
```

Required synchronization:

- click a physical point → corresponding analysis IDs join/replace Selection according to current Selection mode;
- click/select analytical rows → linked physical markers highlight;
- Plot → `На шлифе` opens the exact thin section, image and marker;
- Thin section → Plot sends the same Selection back to plots;
- changing BSE/PPL/XPL/element-map representation does not clear Selection.

### One Selection everywhere

The same selection must be readable in:

- Object Workspace
- Analysis table
- Thin section
- XY
- Multi-panel
- Statistics
- Formulae

Do not copy it into page-specific selection stores.

### Acceptance

1. Open Sample.
2. Select analytical rows.
3. Open `Шлифы и объекты`: corresponding markers highlight.
4. Click a marker: the linked rows become selected.
5. Open Plot and then return `На шлифе`.
6. Exact `analysis_id` membership remains unchanged.

---

## 5. Calculations as a continuation of Selection

### User story

The user selects 17 phlogopite analyses and opens Calculations. PetroLab already knows the selected points and should not ask for the dataset again unless there is a genuine ambiguity.

### Contextual calculations UI

At the top show:

`17 выбранных анализов`

`Phlogopite`

`Sample 19 ТР-1`

Then show only applicable calculation families, for example:

`Структурная формула / APFU`

`17/17 подходящих входов · Рекомендуется`

`Термобарометрия`

`12/17 имеют необходимые поля`

`Пользовательская формула`

`Распределение элементов`

Do not expose methods that cannot be applied to the current input.

### Mineral reassignment workflow

Point-level mineral interpretation already belongs outside raw chemistry. Expose it in the Product Design UI.

In Selection Panel add:

`Изменить минерал / фазу`

Dialog / drawer:

`Текущая интерпретация: Phlogopite`

`Назначить: Amphibole`

Optional reason:

`точка попала на включение амфибола`

Before save show:

`Будет изменена интерпретация 3 анализов. Исходная химия останется без изменений. Сохранённые APFU для этих точек потребуется пересчитать.`

Action:

`Переотнести`

After save:

`3 точки переотнесены в Amphibole`

`Пересчитать APFU →`

### Batch reassignment

Allow reassignment for the whole current Selection. If multiple current mineral interpretations are present, show that clearly before confirmation.

### History

Point details should expose interpretation history, for example:

`Phlogopite → Amphibole`

`23.08.2026`

`точка на включении`

Never silently overwrite the source Mineral column.

### Calculation results

Results should foreground:

- method
- source/reference
- assumptions
- input count
- valid count
- warning count
- failed count
- output fields

Do not make a giant result table the only UI.

Actions:

- `Сохранить`
- `На график`
- `Сравнить`
- `Назад к Sample`

`На график` must preserve Selection.

### Acceptance

1. Select 10 points.
2. Reassign 3 from Phlogopite to Amphibole.
3. Raw chemistry remains unchanged.
4. Reassignment history exists.
5. Active APFU for changed points is invalidated/stale.
6. Recalculate as Amphibole.
7. Plot opens with the same 3 points selected.

---

## 6. Reproducible Figure Recipe and publication workflow

### User story

A publication figure created today must reopen months later with the same exact data membership, source visibility, axes, styles, grouping and layout.

### Figure Recipe

Add:

`Сохранить как Figure Recipe`

Recipe must capture at minimum:

```text
project_id
dataset_ids
analysis_ids / DataUniverse
source visibility
hidden analysis_ids
excluded analysis_ids
panel layout
panel kinds
X/Y/Z variables
color_column
marker_column
group_column
style_map
axis limits
legend settings
journal preset
font
marker size
grid
figure dimensions
calculated/derived field dependencies
created_at
updated_at
```

Hide and Exclude remain separate concepts.

### Independent color and marker encoding

Use one canonical control model across publication plots:

`Цвет точек: Source`

`Значок точек: Generation`

For example:

- Smith 2020 = blue
- Petrov 2019 = orange

while independently:

- Core = circle
- Rim = square
- Antecryst = diamond

Do not couple color and marker grouping.

### Source visibility

Provide a clear source panel:

- ☑ Мои анализы
- ☑ Smith et al., 2020
- ☑ Petrov et al., 2019
- ☐ Ivanov et al., 2021

This is Figure Recipe visibility state, not deletion from the DataUniverse.

### Saved figures

Under `Публикация` show:

`Сохранённые фигуры`

Example card:

`Fig 8 mica evolution`

`4 панели · 568 анализов`

`изменена 23.08.2026`

Actions:

- `Открыть`
- `Дублировать`
- `Экспорт`

### Mixed-panel export

Complete export for figures containing any mix of:

- XY
- ternary
- spider

Minimum output:

- SVG
- PNG 600 dpi
- XLSX data used in figure
- reproducibility manifest

### Reproducibility manifest

Export a JSON manifest such as:

`fig_08_recipe.json`

It does not contain binary datasets, but it must contain enough state to reconstruct the figure against the same PetroLab project/library.

### Acceptance

1. Create a four-panel figure.
2. Set color=Source and marker=Generation.
3. Hide one source.
4. Save Figure Recipe.
5. Close/reopen the app.
6. Open the Recipe.
7. Data membership, hidden source, styles, axes and panel layout are identical.
8. SVG, PNG, XLSX and JSON manifest export successfully.

---

## 7. Redesign Home only after scenarios 1–6

The Home page should be a work overview, not a second navigation menu.

### Continue

Show recent work objects such as:

- `19 ТР-1`
- `Fig 8 mica evolution`
- `Turiy Mys thin section A05`

### Requires attention

Examples:

- `12 изображений без связи`
- `7 анализов требуют подтверждения минерала`
- `2 сохранённых расчёта устарели`

Each item must have an immediate resolving action.

### Recent data

Show recent Samples/datasets with direct opening.

### Quick actions

Limit to:

- `Добавить данные`
- `Найти`
- `Продолжить последнюю работу`

Do not reproduce the whole primary navigation as a row of buttons.

---

## 8. Explicit non-goals / forbidden regressions

Do not:

- restore the 9-item navigation from the older design branch;
- cherry-pick the large hotfix branch wholesale;
- create a second image wizard next to the canonical one;
- create a separate thin-section Selection;
- duplicate datasets per project when a linkage is sufficient;
- mutate raw chemistry when changing interpretation;
- use Sample names as sole transition identity when `sample_id` is known;
- use dataset labels as identity;
- implement source hiding by deleting/filtering away the underlying DataUniverse permanently;
- merge Textural zone into Generation;
- treat Work Group as permanent mineral classification;
- allow arbitrary polygons for physical thin-section fields;
- add new `v0160_*_hotfix.py` runtime wrappers.

When an old implementation conflicts with Product Design, rewrite the old implementation to fit Product Design rather than adapting Product Design to legacy screens.

---

## 9. Recommended commit sequence

```text
1. refactor: unify scenario context and navigation handoffs
2. feat: add cross-project global search
3. feat: make all search results object-openable
4. feat: complete physical image linking and inbox
5. feat: integrate thin-section linked workspace
6. feat: add mineral reassignment and contextual calculations
7. feat: add reproducible figure recipes and mixed export
8. feat: align home overview with task-first shell
9. test: add end-to-end scenario acceptance coverage
10. docs: document v0.16 canonical user workflows
```

Keep scenario commits reviewable. Do not collapse the entire branch into one giant implementation commit while work is ongoing.

---

## 10. End-to-end acceptance suite

### A. Cross-project search

Project A → apatite. Project B → search whole PetroLab → link result → Plot. Verify no duplicated analysis rows.

### B. Search state

Search `19 ТР-1` → open a specific result → return → query/scope/tab/Selection preserved.

### C. Excel + images

Multi-sheet Excel + 10 images → import → link 8 → save 2 to Inbox → restart → relationships preserved.

### D. Physical hierarchy

Sample → thin section → create rectangular Field → link BSE → link analytical points → open point → Selection exact.

### E. Linked science

Select on XY with lasso → Multi-panel → Thin section → Formulae → Plot. Verify identical analysis-ID membership.

### F. Wrong mineral

Select point → Phlogopite → Amphibole → raw chemistry unchanged → history saved → APFU invalidated → Amphibole APFU recalculates.

### G. Publication

Create four-panel figure → color=Source → marker=Generation → hide one article → save Recipe → reopen → identical figure state → export SVG/PNG/XLSX/manifest.

---

## 11. Responsive and browser acceptance

Validate at least:

- 1920×1080
- 1440×900
- 1366×768
- 968×516

At small viewport:

- the working scientific object remains visible;
- primary actions remain accessible;
- large horizontal button rows do not break layout;
- secondary controls may collapse into `...` or expanders;
- scientific plots must not become unusably short;
- the first meaningful plot/content must not be entirely below the initial viewport.

---

## 12. Definition of Done

This PR is complete only when a user can execute all of these without entering technical maintenance pages or rebuilding context manually:

1. Find old apatite data anywhere in PetroLab and use it in the current project.
2. Find a specific Sample and open everything related to it.
3. Upload Excel plus a batch of images and link them naturally to Sample, thin section, Field and exact analysis points.
4. Work with thin section, analytical table and plots as one linked workspace.
5. Select points, correct mineral interpretation when needed and run an applicable calculation.
6. Create a publication figure and reproduce the same figure later with identical data and styling.

If any path requires remembering an internal dataset name, visiting a technical database page, manually repeating the same filters, or selecting the same points again, the scenario is not complete.
