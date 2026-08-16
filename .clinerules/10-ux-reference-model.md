# PetroLab UX reference model

Do not invent PetroLab interactions from scratch. Use established interaction models as references, while keeping PetroLab visually minimal, scientific and domain-specific.

The three reference products govern different layers of behavior:

- **Airtable** governs data/table interaction.
- **JMP** governs linked exploratory analysis, row state and brushing.
- **OriginPro** governs scientific plots, graph specifications and multi-panel composition.

Do NOT imitate branding, chrome or visual styling. Copy the predictable interaction models.

## 1. Airtable — data/table behavior

Use Airtable as the behavioral benchmark for the Data Workspace:
- one central grid/table for records;
- search, filter, sort and group live next to the table;
- multiple views are different presentations of the same records, not duplicated data;
- linked entities are shown by readable names, not database ids;
- row selection is obvious and bulk actions act on the selected rows;
- a record can be opened for detail without losing the table context;
- grouping produces readable collapsible groups rather than exposing arbitrary technical columns.

PetroLab mapping:
- Record = analysis row.
- Linked records = Sample, Grain, image, source/article, thin section, analytical session.
- View = current scientific view/filter/selection, not a copied dataset.
- Group = Work Group / Generation / Sample / Grain / Textural zone / Source / Dataset / Mineral.

## 2. JMP — linked exploratory analysis

Use JMP as the behavioral benchmark for selection, brushing and linked views.

Core rule: **all views representing the same analysis rows are linked by analysis_id**.

Expected behavior:
- selecting a row in the table highlights the same analysis on every open graph/statistical view;
- selecting a point, bar, cluster or brushed region in a graph highlights the corresponding table rows and all other linked views;
- changing X/Y, opening a second plot, PCA, cluster view or profile does not silently destroy the current selection;
- selection is a transient row state, not a copied dataset, not a Work Group and not a Generation;
- selection operations are explicit: `Replace | Add | Subtract`, plus `Invert`, `Select visible`, and `Clear` where useful;
- rectangle/lasso brushing is a first-class tool, not hidden in the Plotly modebar;
- clicking a legend category can select/highlight the corresponding analyses;
- filters change the visible analysis universe; selection chooses rows inside that universe. Filtering and selection must never be silently conflated;
- hiding a row from plots is distinct from excluding it from calculations. Both states are reversible and must never delete source data;
- labels, colors and markers are display/row states and may coexist with selection; they must not require changing scientific Generation values;
- no temporary scientific subset should require physically duplicating a dataset.

### PetroLab row-state semantics

PetroLab should expose a small domain model analogous to JMP row states, keyed by immutable `analysis_id`:

- `selected`: current linked selection;
- `hidden`: omitted from visual plots but still present in data and calculations unless separately excluded;
- `excluded`: omitted from statistical/calculation scope but retained in source data; show clearly when excluded points remain visible;
- `labelled`: optional human point label on plots;
- `display_color` / `display_marker`: temporary or saved visual styling, separate from scientific classification.

Do not force all row states into the database. Ephemeral exploration state belongs in session/work context; only explicitly saved user decisions should persist.

### SelectionContext contract

`SelectionContext` is the canonical cross-view state and must use immutable `analysis_id` values.
It should carry at least:
- ordered/unique selected analysis ids;
- selection operation/origin;
- current dataset/project universe;
- optional temporary grouping metadata such as cluster labels;
- revision/token sufficient to avoid circular update loops.

Every table, XY plot, multi-panel plot, PCA/cluster view and profile selector must read/write this same contract. Legacy session-state keys may temporarily adapt to it during migration, but they must not remain independent sources of truth.

### Linked-view acceptance example

A user selects 14 analyses in the table. All current plots highlight exactly those 14. The user changes one plot from `TiO2–MgO` to `Al2O3–FeO`: the same 14 remain highlighted. The user brushes 5 additional points on that plot in `Add` mode: the table and every linked plot now show 19 selected. The user opens PCA: the same 19 are highlighted. The user subtracts 3 PCA points: all linked views now show 16. No Work Group or Generation is created until the user explicitly chooses to save/approve one.

## 3. OriginPro — scientific plotting behavior

Use OriginPro as the behavioral benchmark for plots:
- select data first, then create a plot;
- the plot remembers its data and plot specification;
- an existing plot can be added to / merged into a multi-panel figure without rebuilding it from zero;
- panels/layers have explicit order, arrangement and shared settings;
- graph editing manipulates meaningful scientific objects (series, axes, groups, fields), not raw implementation coordinates by default.

PetroLab mapping:
- `PlotSpec` must preserve dataset/analysis universe, X, Y, grouping, source visibility, style and axis settings.
- Current linked `SelectionContext` is applied to a PlotSpec but is not baked into/destroyed by it unless the user explicitly saves a subset.
- `+ Добавить диаграмму` adds another panel using the current context.
- `Добавить этот график в набор панелей` reuses the current PlotSpec.
- Multi-panel must allow panel add/remove/reorder and common grouping/legend without reselecting all datasets.
- Group fields should be controlled through `Confidence ellipse | Convex hull | KDE`, coverage/level, opacity and line style. Manual polygon coordinates are advanced/debug only.

## PetroLab-specific reference principle

Airtable governs data navigation. JMP governs linked exploration. OriginPro governs plot construction and composition. PetroLab connects all three through one persistent work context and one canonical SelectionContext.

Expected core loop:
`Data table → select analyses → inspect chemistry → linked plots → brush/compare → PCA/cluster → create Work Group → verify on several plots → approve Generation → calculate APFU/profile → export`.

At every step the user must be able to go back without losing the relevant dataset, plot and selection context.

## Visual policy

- Calm, compact scientific UI; no dashboard-card explosion.
- Prefer one large working surface with a narrow contextual toolbar/action bar.
- Use whitespace and hierarchy rather than many bordered containers.
- Primary action: one per section. Secondary actions should not compete visually.
- Selection count and current selection mode should always be visible during exploration.
- Avoid exposing version-specific terminology (`v0154`, wrapper, staging state, etc.) in UI.
