# PetroLab v0.15.7 — JMP-level linked exploration pass

This workflow is a focused continuation of the v0.15.7 UX consolidation. It does NOT replace `docs/UX_AUDIT_V0157_30_PROBLEMS.md`; it sharpens the interaction model for audit items 4, 6–8, 11–19, 29–30.

Read first:
1. all `.clinerules/*.md`;
2. `docs/UX_AUDIT_V0157_30_PROBLEMS.md`;
3. `docs/V0157_IMPLEMENTATION_PLAN.md`;
4. current git status/diff/log.

Do not redo A1. Start from the first incomplete prerequisite.

## Goal

Make PetroLab exploration behave like a linked scientific workspace rather than a collection of independent Streamlit pages.

A selection of analyses must be one shared row state across the table, XY plots, multi-panel, PCA/clustering and profile workflows. The user must be able to brush/select in any view and immediately see the same analyses highlighted everywhere else.

Do not implement this by adding another wrapper, bridge, versioned page or parallel session-state system.

## J0 — prerequisites first

Before advanced JMP behavior, finish the minimum v0.15.7 foundation required for it:
- A2 navigation history/back;
- A3 human analysis labels with UUID hidden by default;
- A4 canonical SelectionContext;
- A5 shared selection panel/action bar;
- A6 canonical Table Workspace skeleton.

If any of these already exist, inspect and reuse them. Do not create competing abstractions.

Checkpoint commit after these prerequisites are demonstrably working.

## J1 — canonical linked SelectionContext

Create one canonical state model keyed by immutable `analysis_id`.

Required semantics:
- `replace(ids)`;
- `add(ids)`;
- `subtract(ids)`;
- `invert(visible_ids)`;
- `clear()`;
- `select_visible(visible_ids)`;
- stable ordered unique ids;
- origin metadata (`table`, `xy`, `multi_panel`, `pca`, `cluster`, `profile`, `legend`, etc.);
- revision/token to prevent circular write-back loops;
- project/dataset universe validation so stale ids are safely discarded.

Legacy state keys may read/write through adapters during migration, but there must be only one source of truth.

Do not persist ordinary selection to the database.

## J2 — table ↔ plot bidirectional linking

Implement and test these exact user behaviors:

1. User checks 12 rows in Table Workspace → every currently rendered linked plot highlights exactly the same 12 analyses.
2. User clicks one point in XY in Replace mode → table selection becomes that one analysis.
3. User brushes 5 points in Add mode → previous selection plus those 5 is selected in table and every linked plot.
4. User brushes 2 selected points in Subtract mode → those two disappear from selection everywhere.
5. Change X/Y axes → current selection remains highlighted if analyses remain in scope.
6. Open/add a second plot → it inherits the same selection immediately.
7. Clear selection from any linked view → clears everywhere.

Do not require page reload, duplicated datasets or saving a Work Group.

## J3 — visible selection tools

Above interactive plots expose a compact tool strip:
- `Точка`;
- `Прямоугольник`;
- `Лассо`;
- `Панорама`.

Beside it expose selection operation:
- `Заменить`;
- `Добавить`;
- `Вычесть`.

Always show `Выбрано: N` and a visible `Сбросить` action.

Plotly modebar is secondary; essential selection actions must not be hidden there.

## J4 — row state: Hide and Exclude are different

Implement reversible scientific row-state behavior without deleting source analyses.

- `hidden`: omitted from plots, still available to calculations/statistics unless excluded;
- `excluded`: omitted from calculations/statistical models but retained in source data; if still plotted, visually indicate excluded status clearly;
- selected and hidden/excluded may coexist;
- actions apply to the selected analyses;
- `Show hidden` / `Include excluded` restores state;
- the user must be warned if a statistical calculation excludes selected analyses.

Do not silently map `hidden` or `excluded` to QC failure, Generation or deletion.

Ephemeral hide/exclude can live in work/session context. Persist only if the user explicitly saves the view/state.

## J5 — linked statistics and clusters

PCA and clustering must behave as linked views of the same underlying analyses.

Acceptance behavior:
- current table/plot selection enters PCA highlighted;
- brushing PCA updates SelectionContext and therefore table/XY/multi-panel;
- cluster labels can be used as temporary display grouping without writing them to the DB;
- clicking/selecting one cluster highlights those analyses everywhere;
- `Проверить на XY` opens/activates linked XY without losing selection;
- only explicit `Сохранить как рабочую группу` persists a cluster interpretation.

## J6 — interactive legend as an analytical control

For meaningful categorical groupings (Generation, Work Group, Sample, Grain, Textural zone, Source, Dataset, Mineral):
- clicking a legend item selects/highlights corresponding analyses;
- additive selection of multiple legend categories is possible;
- hiding a legend category is a visual hide, not data deletion and not statistical exclusion;
- legend order/color/marker are consistent across linked panels for the same grouping.

Do not expose arbitrary technical categorical columns in the primary grouping control.

## J7 — linked multi-panel behavior

All panels in an analytical multi-panel share one SelectionContext.

Required:
- brush in panel A highlights corresponding points in panels B–F;
- selection survives panel reorder/add/remove;
- each panel keeps its own PlotSpec (X, Y, axes) but shares current row selection;
- grouping legend is consistent across panels;
- a panel can be opened from single XY without rebuilding its configuration.

Publication A/B/C composition is a separate concept and must not be confused with linked analytical multi-panel.

## J8 — filter vs selection

Make the difference explicit:
- filter defines which analyses are currently visible/in scope;
- selection identifies analyses inside that scope;
- changing filters intersects selection with valid visible/universe ids according to a documented rule; never silently converts filter into selection;
- show a small notice if a filter removes currently selected analyses from view;
- provide `Показать только выбранное` as a temporary view action, not as dataset duplication.

## J9 — human detail panel

When selection is non-empty, show a compact selection inspector:
- Sample · Grain · Point · Generation;
- Work Group / Textural zone / Source where available;
- compact chemistry with major oxides and relevant trace values;
- for multi-selection: count, ranges/summary and first rows rather than UUID lists;
- `_analysis_id` only under technical/advanced details.

Hover identity and table identity must use the same formatter.

## J10 — E2E contract

Do not mark this pass complete until real UI tests demonstrate at least:

1. table select → two XY plots highlight same rows;
2. XY rectangle Replace → table updates;
3. XY lasso Add → table + second plot update;
4. Subtract → selection count decreases everywhere;
5. change X/Y → selection persists;
6. PCA brush → XY/table update;
7. cluster click/select → linked XY highlights cluster without DB persistence;
8. legend category select → table and other panels highlight it;
9. Hide selected removes points from plots but not table/source data;
10. Exclude selected changes statistical scope but does not delete/hide source rows;
11. Back navigation restores work context and selection;
12. no visible UUIDs in normal table/plot/selection inspector.

Use real Streamlit AppTest/browser automation where interaction is supported. Source-string tests are not sufficient proof.

## Architecture constraints

- No new `v0157_wrapper.py`, bridge or monkey patch.
- Prefer new stable domain/components with non-versioned names, then migrate callers.
- Do not maintain several independent selection keys once a caller is migrated.
- Avoid circular rerun loops: use revision/origin tokens and idempotent writes.
- Do not persist transient exploration unless the user explicitly saves it.
- Never mutate/delete source analytical values to implement UI state.
- Keep scientific semantics of Generation, Work Group, QC and source provenance intact.

## Working rhythm

Work in small coherent commits:
1. inspect root cause;
2. implement one linked behavior;
3. run focused unit/integration tests;
4. run actual UI/E2E scenario;
5. fix regressions;
6. commit only when green;
7. continue autonomously.

Do not stop for routine decisions. Stop only for destructive data migration, scientific semantic ambiguity, unavoidable user-data risk or contradictory requirements.

## Final report

Report:
- exact audit items closed;
- JMP-like linked behaviors demonstrated;
- canonical components introduced;
- legacy state/wrappers removed or still pending;
- exact tests executed and results;
- remaining UX gaps;
- commit list.
