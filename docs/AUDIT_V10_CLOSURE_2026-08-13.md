# PetroLab audit v10 — closure matrix

Дата повторной проверки: 2026-08-13. Основа: `PetroLab_MASTER_AUDIT_AND_IDEAS_v10_2026-08-13.md`.

Статусы ниже относятся к фактическому пользовательскому пути PetroLab. `Core` означает, что инвариант защищён в доменном/service/repository-слое; `UI` — что риск закрыт на публичном workflow; `CI` — что поведение покрывается существующим regression/Windows/browser suite. Roadmap `U-01…U-79` намеренно не смешивается с багами `A-01…A-100`.

## A-01…A-100

| Пункт | Статус | Что проверено / исправлено |
|---|---|---|
| A-01 | CLOSED · Core | decimal comma и `<0,01` распознаются; BDL/n.d./trace сохраняются; неизвестный непустой текст в chemistry блокирует импорт вместо silent NaN. |
| A-02 | CLOSED · Core | bare FeO/Fe2O3 требует явного FeO/FeOt и Fe2O3/Fe2O3t mapping. |
| A-03 | CLOSED · Core | QC хранит `Σ компонентов raw`, `Поправка O=F,Cl`, `Σ corrected`; старый `Σ оксидов` — compatibility alias corrected total. |
| A-04 | CLOSED · UI/Core | generated QC и derived columns защищены от редактирования как source chemistry. |
| A-05 | CLOSED · Core | refresh сохраняет `updated_at` неизменённой строки; formula freshness не стареет от простого reread. |
| A-06 | CLOSED · Core/UI | export metadata/images ограничены выбранными datasets, recipes/profiles — соответствующими projects. |
| A-07 | CLOSED · Core/UI | mineral выбирается per sheet. |
| A-08 | CLOSED · Core/UI | header row выбирается per sheet. |
| A-09 | CLOSED · Core | canonical duplicate scientific columns — import blocker. |
| A-10 | CLOSED · UI | stale recipe с исчезнувшими datasets не раскрывается на «все данные»; предлагается явный reset. |
| A-11 | CLOSED · UI | пустой mineral multiselect = пустая выборка, не «все минералы». |
| A-12 | CLOSED · Core | quick search использует literal `regex=False`. |
| A-13 | CLOSED · UI | scientific pattern assigns one deterministic style per group; rows in one group share color/linestyle. |
| A-14 | CLOSED · UI | generic interactive/publication XY use shared deterministic style map. |
| A-15 | CLOSED · UI | active project is global sidebar context. |
| A-16 | CLOSED · UI | «Последние наборы» использует newest-first/head, не tail. |
| A-17 | CLOSED · UI | 3000/5000/120 caps explicitly disclosed with guidance to refine filter. |
| A-18 | CLOSED · UI | image field-link limited to Sample/Grain/Generation/Point. |
| A-19 | CLOSED · UI/Core | linked mode explicitly says reverse sync only XLSX/XLSM; CSV/XLS are not promised bidirectional sync. |
| A-20 | CLOSED · UI | default outlier method from Settings is used by advanced XY unless recipe overrides it. |
| A-21 | CLOSED · UI/Core | PCA with <2 rows is blocked with explanation. |
| A-22 | CLOSED · UI/Core | cluster slider maximum follows actual sample count; <2 rows blocked. |
| A-23 | CLOSED · UI | image deletion requires confirmation. |
| A-24 | CLOSED · UI | sidebar/page names normalized. |
| A-25 | CLOSED · UI | «Что нового» vs «История правок данных» explicitly separated. |
| A-26 | CLOSED · UI | two-stage workspace navigation removed; flat grouped sidebar. |
| A-27 | CLOSED · Core/UI | whole-rock composition editor is replace semantics; deleted rows are removed. |
| A-28 | CLOSED · Core | whole-rock Mg# does not reinterpret Fe2O3 as Fe2+. |
| A-29 | CLOSED · Core | bulk whole-rock update merges with existing chemistry instead of erasing unspecified analytes. |
| A-30 | CLOSED · UI | pattern Y label follows selected normalization reference. |
| A-31 | CLOSED · UI | manual scientific XY axes clear preset title/axis text instead of retaining misleading literature title. |
| A-32 | CLOSED · UI | grouped boxplot with multiple Y is explicitly blocked/warned, not silently ungrouped. |
| A-33 | CLOSED · UI | ternary recipe restores figure/point/font/marker/grid/legend/DPI/spine settings through keyed state reset. |
| A-34 | CLOSED · Core | Excel article tables set print-title/repeat header rows. |
| A-35 | CLOSED · UI | `spine_width` exposed in shared figure controls. |
| A-36 | CLOSED · UI | scientific histogram/boxplot expose SVG as well as PNG. |
| A-37 | CLOSED · Core | rock–dataset links reject cross-project relationships. |
| A-38 | CLOSED · Core | duplicate whole-rock analytes after canonicalization are blockers, not first-wins. |
| A-39 | CLOSED · Core/UI | empty manual whole-rock row is not stored as NULL analyte. |
| A-40 | CLOSED · UI | source citation/overlay suppressed once axes no longer match literature preset. |
| A-41 | CLOSED · Core | workbook hash checked before every reverse write. |
| A-42 | CLOSED · Core | entire multi-sheet book preflighted before persistence; rollback on later failure. |
| A-43 | CLOSED · Core | dataset/CSV persistence cleans partial rows/files on failure. |
| A-44 | CLOSED · Core | refresh identity logic accounts for interpretation/work-group state; unsafe positional fallback disabled when needed. |
| A-45 | CLOSED · Core/UI | detached images can be repaired in gallery by relinking existing asset to valid points; file is not re-uploaded. |
| A-46 | CLOSED · Core | point-scope image with zero surviving links is marked detached. |
| A-47 | CLOSED · Core | formula persistence independently aligns by immutable `_analysis_id`, never dataframe position. |
| A-48 | CLOSED · Core | repository validates claimed dataset_id against analysis ownership. |
| A-49 | CLOSED · Core | Excel sync uses compare-and-set against expected old cell value. |
| A-50 | CLOSED · Core | `.petrolab_tmp` removed in `finally`; workbook always closed. |
| A-51 | CLOSED · UI/Core | ternary preset normalization is applied as default and restored from recipe. |
| A-52 | CLOSED · UI/Core | preset availability/projection is row/mineral-aware, not only union-of-columns aware. |
| A-53 | CLOSED · Core | Morimoto pyroxene projection excludes non-Quad rows. |
| A-54 | CLOSED · Core | ternary non-finite components are discarded before normalization. |
| A-55 | CLOSED · Core | statistics converts ±inf to missing before imputation/scaling. |
| A-56 | CLOSED · Core/UI | editable source columns are intersection of physical source schemas across selected datasets. |
| A-57 | CLOSED · Public UI | REE/spider user workflow requires known concentration units even without normalization; bare-unit elements are not offered. Low-level helper remains deliberately general for internal callers. |
| A-58 | CLOSED · Core | managed browser upload has `sync_enabled=False`; never a reverse-sync target. |
| A-59 | CLOSED · UI | managed upload shown as internal PetroLab working copy, distinct from linked user source; refresh only on real linked sources. |
| A-60 | CLOSED · UI/Core | ternary preset availability checks real valid rows via dataframe-aware API. |
| A-61 | CLOSED · Core | normalized patterns exclude elements lacking a valid reference coefficient. |
| A-62 | CLOSED · UI/Core | log export filters non-positive values; UI count explicitly states it is before log-axis validity rather than claiming a final count. |
| A-63 | CLOSED · UI | missing group label normalized to «Без группы» for interactive/publication paths. |
| A-64 | CLOSED · Core/CI | storage bootstrap creates/migrates rock tables on clean data dir; migration tests cover it. |
| A-65 | CLOSED · Core/CI | import is source-only; registry import does not silently persist Mg# derived chemistry. |
| A-66 | CLOSED · Core/UI | derived Mg# is not editable as source and follows formula freshness. |
| A-67 | CLOSED · Core | no import/formula Mg# collision: source-only contract avoids duplicate semantic Mg# columns. |
| A-68 | CLOSED · Core/CI | storage bootstrap is centralized and migration/integrity tests verify schema parity. |
| A-69 | CLOSED · Core | edited field scope that no longer matches analyses becomes detached rather than silently linked. |
| A-70 | CLOSED · Contract | batch image docs now state real guarantee: full prevalidation + compensating rollback; no false claim of ACID atomicity across FS+SQLite. |
| A-71 | CLOSED · Core | change comparison handles NaN and ±inf explicitly. |
| A-72 | CLOSED · UI | applying/replacing recipe resets keyed widget state so saved settings actually restore. |
| A-73 | CLOSED · UI | manual exclusions beyond first 3000 are preserved explicitly and never silently dropped on resave. |
| A-74 | CLOSED · UI | dataset labels contain unique DB identity to avoid collisions. |
| A-75 | CLOSED · Service | after manual source edit, generated QC is refreshed without another source timestamp; recovery CSV is atomically refreshed from SQLite. Maintenance failure is returned as a warning, primary SQLite remains source of truth. |
| A-76 | CLOSED · Core | CSV recovery no longer invents physical Excel source rows. |
| A-77 | CLOSED · Core | failed managed import removes orphan managed source and partial datasets. |
| A-78 | CLOSED · UI | deleting a plot recipe also clears active loaded recipe/excluded-point session state. |
| A-79 | CLOSED · Core/UI | row-level missing critical measured oxide/Fe marks formula invalid and nulls derived values rather than treating blank as measured zero. |
| A-80 | CLOSED · Core | structural formula boundary rejects negative, non-finite, arbitrary text and censored values until explicitly resolved. |
| A-81 | CLOSED · Core | missing F/Cl is not silently identical to measured zero for OH-dependent interpretation. |
| A-82 | CLOSED · Core/UI | formula freshness and formula validity are separate counters (`current/stale/valid/invalid/legacy unknown`). |
| A-83 | CLOSED · UI | formula page summarizes invalid rows over full dataset before save, independent of preview head. |
| A-84 | CLOSED · Public UI | publication XY wrapper removes ±inf on linear axes as well as log axes. |
| A-85 | CLOSED · Core | pattern needs at least two positive finite elements per curve. |
| A-86 | CLOSED · Core/UI | whole-rock import requires/normalizes explicit units; no silent unknown-unit bulk concentrations. |
| A-87 | CLOSED · Core | Droop redox is blocked when measured Fe3 is already supplied. |
| A-88 | CLOSED · Core | all-Fe2 mode mass-converts measured ferric iron into FeO-equivalent only within that explicit model. |
| A-89 | CLOSED · Core | apatite classification with unresolved F/Cl/OH is withheld rather than defaulted to hydroxylapatite. |
| A-90 | CLOSED · Core | Sample/Grain/Point identifiers are excluded from numeric rounding; leading zeros survive. |
| A-91 | CLOSED · UI/Core | MAD/IQR can be computed within Work Group/Generation/Dataset/Mineral/Sample instead of only global mixture. |
| A-92 | CLOSED · Core/Provenance | formula contract is explicit: all recognized measured oxide columns participate in base formula; actual inputs used are persisted in provenance instead of unused `allowed_oxides` metadata. |
| A-93 | CLOSED · Core | carbonate formula supports FeOt input. |
| A-94 | CLOSED · Core | carbonate outputs `X_Fe3` on actual 1- or 2-cation normalization basis. |
| A-95 | CLOSED · Core | Henderson nepheline conservatively rejects FeO/FeOt rather than silently losing Fe2+. |
| A-96 | CLOSED · Core | MinPlot titanite explicitly converts Fe source to ferric calculation basis while preserving source Fe column. |
| A-97 | CLOSED · Core | garnet result labels `Simplified_endmember_sum` and QC completeness instead of presenting simplified budget as universal full closure. |
| A-98 | CLOSED · Core | garnet dominant-endmember classification is withheld when omitted Ti/Zr/Hf/V/Nb/Sn/U Y-site budget is nonzero. |
| A-99 | CLOSED · UI | no fallback to all mineral-specific scientific presets when selected minerals have no matching scheme. |
| A-100 | CLOSED · UI | optional `render_hint()` reads `show_help_hints`; settings/source guidance uses it, while QC/provenance/warnings remain always visible. |

## UX / dashboard verification

- Persistent project context and flat grouped sidebar are active; two-stage navigation removed.
- Home is task-oriented project dashboard, not an instruction page.
- Analyses page is toolbar-first with column views and point card.
- XY page is plot-first with a separate advanced editor; quick/advanced Plotly widgets have independent state.
- Image import is a two-column batch wizard; gallery is a grid, destructive image delete has confirmation, detached links have repair workflow.
- Shared design tokens, page headers, badges, focus states, responsive rules and compact/comfortable density are centralized.
- Projects are workspace cards; Settings are tabbed; Help is searchable; program release notes and scientific data edit history are separate concepts.
- Scientific plots retain provenance only while their axes/reference actually match the cited scheme.
- Destructive image actions are confirmed. Recipe deletion clears active state; recipe/profile deletion confirmation remains a UX polish candidate rather than a scientific-integrity blocker.

## Roadmap boundary

`U-01…U-79` are product-development ideas, not audit defects. They remain a roadmap (e.g. undo, command palette, richer project lifecycle, additional scientific modules) unless implemented independently. They are intentionally not marked «fixed» here.

## Remaining non-A technical note

`SaveResult.warnings` can report a rare post-save maintenance failure (generated-QC/recovery-snapshot refresh). The primary SQLite save is still correct. A dedicated post-rerun warning flash in the analyses dashboard is desirable UI polish; it is not one of A-01…A-100 and does not affect primary data correctness.
