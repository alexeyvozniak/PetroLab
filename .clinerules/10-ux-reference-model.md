# PetroLab UX reference model

Do not invent PetroLab interactions from scratch. Use established interaction models as references, while keeping PetroLab visually minimal and domain-specific.

## Primary reference: Airtable — data/table behavior
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

Do NOT copy Airtable branding or web-app chrome. Copy the clarity of table operations and linked-record behavior.

## Secondary reference: OriginPro — scientific plotting behavior
Use OriginPro as the behavioral benchmark for plots:
- select data first, then create a plot;
- the plot remembers its data and plot specification;
- an existing plot can be added to / merged into a multi-panel figure without rebuilding it from zero;
- panels/layers have explicit order, arrangement and shared settings;
- graph editing manipulates meaningful scientific objects (series, axes, groups, fields), not raw implementation coordinates by default.

PetroLab mapping:
- `PlotSpec` must preserve dataset/analysis selection, X, Y, grouping, source visibility, style and axis settings.
- `+ Добавить диаграмму` adds another panel using the current context.
- `Добавить этот график в набор панелей` reuses the current PlotSpec.
- Multi-panel must allow panel add/remove/reorder and common grouping/legend without reselecting all datasets.
- Group fields should be controlled through `Confidence ellipse | Convex hull | KDE`, coverage/level, opacity and line style. Manual polygon coordinates are advanced/debug only.

## PetroLab-specific reference principle
Airtable governs data navigation. OriginPro governs plotting. PetroLab connects them through one persistent SelectionContext.

Expected core loop:
`Data table → select analyses → inspect chemistry → plot → select points → create Work Group → check on several plots/PCA → approve Generation → calculate APFU/profile → export`.

At every step the user must be able to go back without losing the selection/context.

## Visual policy
- Calm, compact scientific UI; no dashboard-card explosion.
- Prefer one large working surface with a narrow contextual toolbar/action bar.
- Use whitespace and hierarchy rather than many bordered containers.
- Primary action: one per section. Secondary actions should not compete visually.
- Avoid exposing version-specific terminology (`v0154`, wrapper, staging state, etc.) in UI.
