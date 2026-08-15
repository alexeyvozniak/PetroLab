# PetroLab 0.15.5 — whole-rock workspace release audit

This release is built on the merged v0.15.4 main and preserves Publication Composer, Grain Profile, project-scoped universal intake and all earlier silent-error runtime layers.

## Object-centred whole-rock workflow

- `Породы` opens a modern sample/object workspace rather than the editing forms;
- the established forms remain available as `Редактор пород`;
- workspace tabs cover Overview, Whole-rock chemistry, Trace elements, Isotopes, Minerals, Photos, Diagrams, Interpretation and Provenance;
- exact workspace → editor handoff uses rock ID, not display-name matching;
- Interpretation updates only description/notes and never rewrites measured chemistry or isotope rows;
- sample cards export reproducible XLSX and JSON with chemistry/isotopes/provenance/data-health/links/image metadata and do not expose internal `project_id`.

## Project membership and mineral links

- rock↔mineral links are validated through `project_dataset_links`, so linked global-library datasets are valid when they are accessible to the project;
- an inaccessible/orphaned historical link is surfaced as a warning rather than silently loaded;
- saving links refuses inaccessible datasets;
- Rhodes screening refuses to read any linked mineral dataset that is no longer accessible to the active project;
- the canonical schema column is `relationship`; the historic runtime `relation` mismatch is closed.

## Whole-rock provenance and partial imports

- method/source remain stored per analyte;
- a trace-element update does not replace method/source on untouched major-element rows;
- aggregate passport `chemistry_method` and `laboratory` accumulate unique values rather than becoming the last import only;
- repeated identical methods/laboratories do not duplicate in the passport;
- blank mapped bulk-import metadata means “not supplied”, not “erase the curated passport”; explicit clearing remains an editor action;
- imports and manual edits reject non-finite numeric values instead of persisting NaN/Inf as scientific measurements.

## Isotopes and data health

- isotope systems count only determinations with finite values;
- incomplete/non-finite isotope rows are visible as warnings, not positive data-health badges;
- age and isotope numeric fields share the same finite-value boundary.

## Comparison and plotting

- exact rock focus uses `_rock_plot_group` presentation metadata and never overwrites `Источник данных`;
- source filters operate on true provenance;
- massif/lithology and per-sample visibility filters hide data only in the current view and never delete it;
- the focused sample can be compared against literature while remaining visually distinct;
- TAS, Harker/binary, REE/Spider, isotope and Rhodes workflows remain available.

## Preserved earlier guarantees

- `physical_point_safety` still prevents cross-image label identity inference;
- `import_runtime` still attaches detected analytical Method before persistence;
- work-context filters still intersect selectors;
- auto-pipeline still validates project dataset membership;
- v0.15.4 project switching still clears transient identity-bearing state while preserving settings/styles;
- universal intake remains project-token scoped;
- v0.15.3 Publication Composer and v0.15.4 Grain Profile routes/wrappers remain active.

## Release condition

Merge only when the current release head passes:

- Rock workspace regression;
- Grain profile regression;
- Publication composer regression;
- v0.15.1 silent-error regression;
- full Windows verification;
- Guided analysis workflow verification;
- Thermodynamics regression;
- Amphibole diagnostics verification;
- Input/search/workflow regression;
- Product guidance verification;
- Desktop UI regression.
