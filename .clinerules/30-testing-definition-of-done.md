# Testing and Definition of Done

Green CI is necessary but not sufficient. PetroLab v0.15.7 is complete only when real user workflows work end-to-end.

## Testing hierarchy
After each logical change:
1. run focused unit tests for changed services/state models;
2. run integration tests for the affected workflow;
3. run the existing full relevant test suite;
4. for user-facing changes, run a real browser E2E scenario that clicks actual widgets.

Do not accept tests that only search source files for strings as proof that a workflow works.

## Required E2E scenarios
The final branch must exercise these with a real Streamlit/browser session where technically possible:

1. Home → open a recent dataset → Back → return to Home with context intact.
2. Data table → filter Sample → select several rows → chemistry visible → create Work Group → selection remains selected.
3. XY → switch `Точка / Прямоугольник / Лассо` → select points → clear selection → no duplicate key or exception.
4. XY selection → create Work Group → change X/Y → same selected/grouped analyses remain identifiable.
5. XY → `Добавить этот график в набор панелей` → add second diagram → first panel settings remain intact.
6. Statistics/PCA or cluster → select/choose cluster → `Проверить на XY` → exact same analysis ids shown.
7. Multi-panel → selection on one panel → same ids highlighted on another → approve Generation.
8. Grain profile → select exact points using table checkboxes → set/reorder profile order → preview uses only those points.
9. Import Excel with two Sample blocks → assign different row ranges to different Sample values → commit → verify counts.
10. Upload BMP image → preview/link it → original BMP retained.
11. Import a deliberately bad dataset → undo/remove import safely without affecting unrelated datasets.
12. Formula/APFU from selected data → open calculation without navigating through unrelated modules.

## Regression requirements
- No `StreamlitDuplicateElementKey` in any primary route.
- No visible UUID/analysis_id as the main point label in primary workflows.
- No accidental broadening of an exact routed selection after rerun.
- No selection loss merely because the user changes axes, switches between table/plot/statistics, or presses Back.
- No destructive database change without confirmation.
- No silent deletion of source analyses because of QC/outlier logic.

## UX acceptance checks
For each changed primary screen, answer yes to all:
- Can a first-time user tell what the main action is within ~5 seconds?
- Are the current data scope and selection visible?
- Can the user inspect the chemistry of what is selected?
- Is there a clear next action after selection?
- Can the user go Back without reconstructing their work?
- Are advanced/internal options hidden by default?
- Are labels scientific/human-readable rather than implementation terminology?

## Completion report
Before claiming a phase complete, produce a concise report containing:
- audit items closed;
- files/architecture changed;
- tests run and exact result;
- remaining known UX gaps;
- any migration risk;
- screenshots or browser evidence for major UI flows when available.

Never claim an item is fixed solely because code was written. Demonstrate the user scenario.