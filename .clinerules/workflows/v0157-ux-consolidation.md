# PetroLab v0.15.7 UX consolidation workflow

Execute this workflow autonomously in small verified stages. The authoritative backlog is `docs/UX_AUDIT_V0157_30_PROBLEMS.md`. All `.clinerules/*.md` rules are mandatory.

## 0. Preflight — do not edit yet
1. Read completely:
   - `docs/UX_AUDIT_V0157_30_PROBLEMS.md`
   - `ARCHITECTURE.md`
   - `petrolab/ui/pages/__init__.py`
   - `petrolab/ui/navigation.py`
   - the plot/table/statistics/profile/import modules named by the audit.
2. Trace the current render chain and list all wrapper/bridge/monkey-patch layers that affect primary routes.
3. Trace current session-state mechanisms for selection, routing, plotting and exact routed ids.
4. Identify existing tests that genuinely execute UI interactions versus tests that only inspect source text.
5. Write/update `docs/V0157_IMPLEMENTATION_PLAN.md` with a dependency-ordered plan. Do not create a new user-facing route merely to satisfy an audit item.

## Phase A — foundation and P0
Implement the foundation before cosmetic changes.

### A1. Stop crashes
- Fix duplicate widget keys, especially the reported chemical-selection path.
- Make reusable components accept scoped key prefixes.
- Add real regression coverage.

### A2. Navigation history
- Implement bounded Back history with route + relevant context.
- User navigation pushes history; reruns do not.
- Add visible `← Назад` in primary chrome.

### A3. Human identity
- Centralize human-readable point/dataset labels.
- Remove UUID/internal IDs from primary labels.
- Add optional technical details only where useful.

### A4. SelectionContext
- Introduce one canonical exact selection state keyed by immutable analysis ids.
- Adapt table, XY, multi-panel and statistics incrementally to it.
- Do not delete legacy selection mechanisms until adapters/tests prove equivalent behavior.

### A5. Shared selection panel/action bar
For any selection show:
- count + readable identities;
- compact chemistry preview;
- `Создать рабочую группу`;
- `Добавить в группу`;
- `Убрать из группы`;
- `Утвердить как Generation`;
- `Открыть в таблице`;
- `Открыть на графиках`;
- `Профиль` when applicable;
- `Очистить выбор`.

Run focused + integration + browser tests and commit Phase A only when its scenarios work.

## Phase B — one Data Workspace and import

### B1. Table Workspace
Create one canonical table interaction surface reused by data workflows:
- checkbox row selection;
- human identity columns fixed near the left;
- column modes `Основное | Химия | Расчёты | Все`;
- search/filter/group/sort;
- selection actions from the shared action bar;
- chemistry visible without opening a separate technical page.

Do not build another competing table page if an existing page can become canonical.

### B2. Home/recent data
- Make recent datasets open the canonical data workspace.
- Back returns to Home.

### B3. Import simplification
- One visible `Добавить данные` entry.
- Excel/CSV preview before commit.
- Explicit row/block assignment `Выбранные → Sample`.
- Summary counts per Sample before import.
- Keep advanced schema mapping behind progressive disclosure.
- Add BMP support while retaining original asset.
- Add obvious `Отменить этот импорт` after commit and safe dataset removal/unlink semantics.

### B4. Formula shortcut
- From dataset/selection/table, expose `Формула / APFU` directly.
- Keep advanced formula page for specialist settings, not as a required navigation step.

Test and commit.

## Phase C — plots, statistics, groups and profiles

### C1. Plot interaction modes
Above interactive plots provide explicit `Точка | Прямоугольник | Лассо | Панорама` control. Do not make users discover this only in Plotly toolbar.

### C2. Curated grouping
Primary grouping options only:
- PetroLab Generation;
- original Generation;
- Work Group;
- Sample;
- Grain;
- Textural zone;
- Source/article;
- Dataset;
- Mineral.
Everything else lives under `Другой столбец…`.

### C3. PlotSpec and multi-panel
- Create canonical PlotSpec.
- `+ Добавить диаграмму` works from ordinary XY.
- `Добавить этот график в набор панелей` preserves current PlotSpec.
- Panels can be added/removed/reordered without rebuilding previous panels.
- Keep publication A/B/C composition distinct from scientific linked multi-plot comparison.

### C4. Scientific group fields
- Default editor: `Confidence ellipse | Convex hull | KDE` + level/coverage + opacity + line style.
- Manual correction means add/remove analyses from group and recompute.
- Raw polygon vertices are advanced/debug only.

### C5. Statistics continuity
- PCA/cluster selection writes SelectionContext.
- `Проверить на XY` and `Показать кластеры на графиках` preserve exact ids and cluster labels.
- Cluster results need not be persisted as Work Groups until the user explicitly saves them.

### C6. Grain profile
Replace the giant point multiselect with table-first selection:
- checkbox `В профиль`;
- Sample/Grain/Point/Generation + chemistry visible;
- editable order in the same table;
- auto-fill order from Point/distance/coordinates;
- live preview based only on checked rows.

Test and commit.

## Phase D — simplify information architecture
- Reduce primary navigation to roughly 7–9 user concepts: `Главная`, `Данные`, `Графики`, `Статистика`, `Шлифы / изображения`, `Расчёты`, `Публикация`, `Поиск`, `Настройки`.
- Remove `Минералогические модули` and other implementation/catalog pages from primary navigation; preserve specialist access contextually or in advanced/help.
- Consolidate competing import/data routes.
- Remove obsolete wrapper layers now made unnecessary by canonical implementations.

## Final verification
Run the full required scenarios from `.clinerules/30-testing-definition-of-done.md` and the Definition of Done in the 30-problem audit.

Do a manual code review specifically for:
- new wrappers/monkey patches accidentally introduced;
- duplicate Streamlit keys;
- visible technical IDs;
- state broadening/loss after rerun;
- destructive data operations;
- dead routes and duplicate UX.

Update `docs/V0157_IMPLEMENTATION_PLAN.md` into a completion report with closed audit numbers and remaining known gaps.

Do not claim v0.15.7 complete until the actual workflows have been demonstrated, not merely compiled or source-inspected.