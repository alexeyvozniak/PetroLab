# PetroLab v0.15.7 — implementation status

Updated during the core UX consolidation. This file is a release checklist, not a substitute for tests.

Legend:
- ✅ implemented in `refactor/v0157-core-workflow`;
- 🧪 implemented, requires/under CI or browser verification before merge;
- 🟡 partial / compatibility layer still remains;
- ⛔ intentionally not implemented because a safe destructive contract is not yet proven.

## Audit / UX items

1. ✅ Duplicate Streamlit key in chemical selection — scoped keys + AppTest regression inherited from A1.
2. ✅ Back navigation — bounded history with route/context restore; AppTest + Selenium Back scenarios added.
3. ✅ Recent Data → object — recent dataset table has row selection and opens Workspace.
4. ✅ Persistent linked selection — canonical `SelectionContext` shared by table, XY, multi-panel and statistics.
5. ✅ Human identity — normal UI uses Sample / Grain / Point / Generation instead of UUID fragments in core workflows.
6. ✅ One selection action model — shared action panel for Work Group, Generation, Hide, Exclude and scientific handoffs.
7. ✅ Discoverable plot tools — Point / Rectangle / Lasso / Pan plus Replace / Add / Subtract.
8. ✅ Selection persists across views/axis changes by immutable `analysis_id` while remaining distinct from Filter.
9. ✅ Work Group actions centralized; XY no longer owns its own persistence logic.
10. ✅ Work Group suggestions can be project-scoped.
11. ✅ Grouping controls curated around scientific concepts, with `Other column…` as advanced fallback.
12. ✅ PCA participates in the same SelectionContext.
13. ✅ Cluster → selection → XY handoff without mandatory Work Group persistence.
14. ✅ `PlotSpec` carries a configured single XY into analytical multi-panel.
15. ✅ Analytical multi-panel and publication A/B/C composer are explicitly different workflows.
16. ✅ Group-field editor uses Confidence ellipse / Convex hull / KDE as normal UX; raw polygon coordinate editing removed from normal flow.
17. ✅ Grain profile exact-point selection is a table with checkboxes and visible chemistry.
18. ✅ Grain profile point order is editable/validated and can become the shared Selection.
19. ✅ Canonical Analysis Table Workspace: search, scientific column modes, grouping/filtering, checkbox selection and action panel.
20. ✅ Formula/APFU is reachable from the shared selection and can recalculate only the selected analysis IDs.
21. ✅ Primary navigation reduced to nine task-oriented entries.
22. ✅ “Mineralogical modules” and implementation-oriented routes removed from primary navigation; compatibility routes remain addressable.
23. 🟡 Add Data now has one visible intake entry; validated staging/provenance still uses an older compatibility integration internally and must be absorbed before the wrapper stack can be fully deleted.
24. ✅ BMP intake integrated: validate with Pillow, preserve original bytes, use in-memory PNG preview where necessary.
25. ✅ Row → Sample staging remains available in the unified intake path; UX now presents it as part of one import sequence rather than a separate product area.
26. ✅ Safe `Undo this import` removes the just-imported memberships from the current project without destroying the global dataset/source.
27. ✅ Safe dataset action `Remove from project` added to the Analysis Table Workspace with explicit confirmation.
28. 🟡 Fully resolved zero-row mixed source containers are recognized by `dataset_visibility.py`; wiring this policy through every remaining legacy selector is still pending.
29. ✅ Shared actions / human point labels / visible chemistry replace page-specific UUID-driven point pickers in the main scientific workflow.
30. 🧪 Test strategy upgraded: pure state regressions, Streamlit AppTest multi-step navigation and real Selenium navigation/viewport tests. Real Plotly drag/brushing E2E still needs one final isolated browser test after the core branch is stable.

## Architecture consolidation

### Direct canonical renderers now used
- Home
- Object / Data Workspace
- XY plots
- analytical multi-panel

These no longer route through the old chemical-selection / cluster wrapper chain.

### Compatibility debt still present
- Add Data staging/provenance/textural-zone integration;
- some thin-section/global-search/rock compatibility wrappers;
- a subset of v0.15.6 safety wrappers around pages whose destructive/exact-route behaviour has not yet been absorbed.

No new v0.15.7 wrapper/bridge/monkey-patch layer has been introduced.

## Safety decisions

### Implemented
- `Remove from project`: membership-only, preserves dataset, analyses, images, provenance and source.
- `Undo this import`: membership-only rollback for the recent import.
- Windows live in-place upgrade: verified on the dedicated installer branch and integrated into the core branch; pre-install shutdown only kills the exact embedded PetroLab Python runtime.

### Intentionally deferred
- ⛔ Global destructive `Delete dataset from PetroLab` is not exposed yet. It must not be implemented as a naked `DELETE` until every FK/file/journal relationship and shared-project membership consequence is audited and the user receives an exact impact preview.

## Remaining release blockers

1. Stabilize the latest core head under all CI workflows.
2. Fix any genuine runtime regressions rather than restoring stale wrapper/source-marker contracts.
3. Wire provenance-only mixed-container hiding through remaining legacy selectors.
4. Add one real-browser Plotly brushing regression: select points → change axes → same selection → open another linked view.
5. Audit and then either remove or formally quarantine the remaining compatibility wrappers.
6. Only after the above: final visual polish pass and release/version bump.

Do not merge this branch into `main` merely because source-marker tests are green. The release gate is the user workflow plus CI/browser behaviour.