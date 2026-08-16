# PetroLab master backlog — post-v0.15.7

This document is the master product backlog for the next development stage after the v0.15.7 UX consolidation.

The target is not to imitate branding or visual styling. Each reference product governs the interaction pattern where it is strongest:

- **Airtable** → data/table workspace, views, linked records, search/filter/group/sort.
- **JMP** → linked scientific exploration, row state, brushing, selection persistence.
- **OriginPro** → scientific plots, graph objects, PlotSpec, series/layer management and multi-panel composition.

The primary product rule is: **do not add new top-level scientific modules while the core workflow below is still fragmented or inconsistent.** Prefer consolidation, deletion of duplicate workflows and progressive disclosure.

## Priority legend

- **P0** — core product behavior; blocks calling PetroLab a coherent scientific workspace.
- **P1** — high-value workflow polish; should follow immediately after P0.
- **P2** — advanced productivity/publishing improvements.

---

# A. Airtable reference — Data Workspace

## A1. Table-first core

- [ ] **P0** 1. Make the analysis table the main object of the Data page, not a preview under many controls.
- [ ] **P0** 2. Keep one compact toolbar directly above the table: `Search | Fields | Filter | Group | Sort | View`.
- [ ] **P0** 3. Filtering must never mutate source data or destroy Selection.
- [ ] **P1** 4. Add saved views of the same records, e.g. `All`, `Micas`, `LA-ICP-MS only`, `For paper`, `Poor QC`.
- [ ] **P0** 5. Allow hiding columns without deleting them.
- [ ] **P0** 6. Add column presets: `Basic`, `Microprobe`, `Trace`, `APFU`, `QC`, `All`.
- [ ] **P0** 7. Use human point identity such as `KIV-2 · gr3 · p17 · core`; never expose UUID as a primary label.
- [ ] **P0** 8. Treat Sample, Grain, Point, Generation, Work Group, Source/Article and Dataset as linked scientific entities, not accidental text columns.
- [ ] **P1** 9. Clicking/opening one row must reveal a detailed record without losing the current table view.
- [ ] **P1** 10. The record detail should show chemistry, APFU, Sample, Grain, Generation, Work Group, images, source, file/sheet/row and analytical method.
- [ ] **P0** 11. Bulk actions must operate only on explicitly selected rows.
- [ ] **P0** 12. Add `Select all visible`.
- [ ] **P0** 13. Add `Invert selection`.
- [ ] **P0** 14. Add `Clear selection`.
- [ ] **P1** 15. Source/article must be a first-class filter.
- [ ] **P1** 16. Support the workflow: find all apatites from Article A → select → plot → add apatites from Article B.
- [ ] **P1** 17. Allow temporarily hiding Article A from the current view without deleting data.
- [ ] **P0** 18. Support grouping by Sample, Grain, Generation, Work Group, Article, Dataset and Mineral.
- [ ] **P1** 19. Groups should be collapsible/readable rather than implemented as arbitrary technical columns.
- [ ] **P1** 20. Search across Sample, Grain, Point, Mineral, Generation, Article, file/source and key values.
- [ ] **P0** 21. `Recent data` on Home should open the canonical Data Workspace directly.
- [ ] **P0** 22. Back must restore the same dataset, view/filter, scroll/record context where practical, and Selection.

## A2. Import and provenance

- [ ] **P0** 23. Keep one universal import/drop zone, not several competing import pages.
- [ ] **P1** 24. Allow Excel/CSV/images/PDF to be dropped in the same intake workflow.
- [ ] **P0** 25. After Excel import, show preview and ask only for unresolved column mappings.
- [ ] **P0** 26. Normalize different element/oxide column orders across sheets automatically.
- [ ] **P0** 27. Recognize common aliases such as `FeO`, `FeOt`, `FeOtot`, `FeO*`, while showing the mapping to the user.
- [ ] **P0** 28. Keep trace-element units (`µg/g`, ppm) distinct from wt.% oxides.
- [ ] **P0** 29. If one sheet contains several Samples, require row→Sample staging before commit.
- [ ] **P1** 30. After loading multiple images, ask which Sample/Grain/Point each image belongs to.
- [ ] **P1** 31. One image may link to several points.
- [ ] **P1** 32. One point may have several linked images.
- [ ] **P0** 33. BMP/TIFF/JPEG/PNG should behave consistently in the UI while preserving the original source file.
- [ ] **P0** 34. Provide Undo for the last import.
- [ ] **P0** 35. Clearly separate `Remove from project` from `Delete from PetroLab`.
- [ ] **P0** 36. Preserve full provenance but keep technical provenance out of the default working surface.
- [ ] **P0** 37. Hide technical zero-row containers such as `Исходный mixed (разобрано)` from ordinary working selectors while retaining them for provenance/audit.
- [ ] **P0** 38. Never duplicate a Dataset merely to represent a temporary filter or scientific subset.

---

# B. JMP reference — linked scientific exploration

## B1. One canonical SelectionContext

- [ ] **P0** 39. There must be exactly one canonical `SelectionContext`.
- [ ] **P0** 40. Selecting rows in the table highlights the same analyses in every linked plot.
- [ ] **P0** 41. Selecting points on a plot highlights the corresponding table rows.
- [ ] **P0** 42. PCA must read the same SelectionContext.
- [ ] **P0** 43. Clustering must read/write the same SelectionContext.
- [ ] **P1** 44. Grain profile workflows must be able to consume the same SelectionContext.
- [ ] **P0** 45. Changing X/Y must not destroy the current selection.
- [ ] **P0** 46. Selection is not a Work Group.
- [ ] **P0** 47. Selection is not a Generation.
- [ ] **P0** 48. Selection is not a Filter.
- [ ] **P0** 49. Selection is not Hide.
- [ ] **P0** 50. Selection is not Exclude.
- [ ] **P0** 51. Selection operations must include `Replace | Add | Subtract`.
- [ ] **P0** 52. Plot tools must expose `Point | Rectangle | Lasso | Pan` directly.
- [ ] **P0** 53. Rectangle and Lasso must not be hidden only in the Plotly modebar.
- [ ] **P1** 54. Legend-category clicks should be able to select/highlight corresponding analyses where practical.
- [ ] **P1** 55. Additive selection should be obvious via explicit Add mode and/or a predictable modifier.
- [ ] **P1** 56. Subtract mode must remove only brushed/clicked analyses from Selection.

## B2. JMP-like row states

- [ ] **P0** 57. `Hide` hides analyses from plots but does not exclude them from calculations.
- [ ] **P0** 58. `Exclude` removes analyses from statistical/calculation scope without deleting source data.
- [ ] **P1** 59. Hidden and Excluded states may coexist.
- [ ] **P1** 60. If excluded points remain visible, their excluded state should be obvious.
- [ ] **P1** 61. Temporary plot labels must not alter Generation.
- [ ] **P1** 62. Temporary color/marker state must be separate from scientific classification.
- [ ] **P0** 63. After any Selection, show one consistent selection summary/action bar.
- [ ] **P0** 64. Shared Selection actions should include Work Group, Generation, XY, Multi-panel, PCA, Profile, APFU, Hide, Exclude and Export as context permits.

## B3. Interpretation workflow

- [ ] **P0** 65. Work Group is a reversible scientific hypothesis.
- [ ] **P0** 66. Generation is a more formal interpretation decision and must remain separate from Work Group.
- [ ] **P1** 67. A newly created Work Group should immediately appear consistently across linked views.
- [ ] **P1** 68. Generation changes should also propagate consistently across tables/plots.
- [ ] **P0** 69. Cluster → `Check on XY` must pass the exact same analysis IDs.
- [ ] **P0** 70. A cluster must never silently become a Generation.
- [ ] **P1** 71. PCA brushing must update the same SelectionContext.
- [ ] **P1** 72. Outlier/anomaly selection must be reversible.
- [ ] **P1** 73. Users should be able to compare a transient selection across several diagrams before saving it as Work Group.
- [ ] **P0** 74. Filter + Selection must compose correctly: removing a filter should not silently erase an existing Selection.
- [ ] **P1** 75. Use linked highlighting: selected points stay bright while non-selected context remains visible/de-emphasized.
- [ ] **P0** 76. Do not automatically filter a graph down to Selection; preserve geochemical context unless the user explicitly requests a subset view.
- [ ] **P0** 77. Selection should persist across page/view changes until explicitly cleared or intentionally replaced.

---

# C. OriginPro reference — scientific plots and multi-panel

## C1. PlotSpec as a scientific object

- [ ] **P0** 78. Every reusable graph should have a `PlotSpec`.
- [ ] **P0** 79. PlotSpec should preserve X, Y, data universe, visible series, grouping, symbols/styles, axes/log settings and scientific fields.
- [ ] **P0** 80. Navigation/rerun must not destroy PlotSpec.
- [ ] **P0** 81. `Add this plot to multi-panel` must reuse the existing PlotSpec.
- [ ] **P0** 82. The first multi-panel panel must be an exact logical copy of the source XY plot.
- [ ] **P0** 83. Adding a second panel must not modify the first panel.
- [ ] **P1** 84. Panels can be reordered.
- [ ] **P1** 85. Panels can be removed.
- [ ] **P1** 86. A panel can be duplicated and then edited independently.

## C2. Panel/Series managers

- [ ] **P0** 87. Multi-panel should use a compact Panel Manager, not 2–10 large configuration cards.
- [ ] **P0** 88. One Panel Manager row should expose panel number/order, X, Y, title and scale/log state.
- [ ] **P0** 89. Add a compact Series Manager analogous to Origin Object Manager.
- [ ] **P0** 90. One Series Manager row = scientific series/source/group.
- [ ] **P0** 91. Series must have Show/Hide.
- [ ] **P1** 92. Series draw order should be editable.
- [ ] **P1** 93. Show analysis count per series.
- [ ] **P1** 94. Hiding Article A in the manager should remove it from the relevant panels without deleting the analyses.
- [ ] **P0** 95. Hidden series remain present in the database/work context.
- [ ] **P1** 96. Support comparison workflow Article A + Article B → turn A off with one action.
- [ ] **P0** 97. Series labels must be human-readable, never dataset IDs or raw implementation names.

## C3. Scientific styling and axes

- [ ] **P1** 98. Scientific group styling should support marker, size, fill, outline and opacity at group/series level.
- [ ] **P1** 99. Multi-panel should support one shared legend where appropriate.
- [ ] **P1** 100. Allow common grouping across all panels.
- [ ] **P1** 101. Support shared X axes.
- [ ] **P1** 102. Support shared Y axes.
- [ ] **P1** 103. Allow an individual panel to override axis range.
- [ ] **P1** 104. Provide quick `Autoscale`, `Fit selected`, `Reset` actions.

## C4. Scientific fields/envelopes

- [ ] **P0** 105. Confidence ellipse is a first-class scientific graph object.
- [ ] **P0** 106. Convex hull is a first-class scientific graph object.
- [ ] **P0** 107. KDE envelope is a first-class scientific graph object.
- [ ] **P0** 108. Do not require ordinary users to edit raw polygon coordinates.
- [ ] **P2** 109. Manual geometry remains available only under advanced/technical controls.
- [ ] **P1** 110. Every field/envelope should be associated with a scientific group/selection definition.
- [ ] **P1** 111. If the underlying group changes, offer to recalculate the envelope.

## C5. Export and publication

- [ ] **P1** 112. Plot objects should retain data provenance/source information.
- [ ] **P1** 113. SVG export must avoid PowerClip-like broken clipping/curve artifacts in normal editing workflows.
- [ ] **P1** 114. PNG/SVG/PDF export should share the same scientific style specification.
- [ ] **P0** 115. Publication composer A/B/C is a different task from analytical multi-panel.
- [ ] **P0** 116. Analytical multi-panel works with live scientific data and linked selection.
- [ ] **P0** 117. Publication Composer assembles prepared plots/panels for publication output.
- [ ] **P0** 118. These two concepts must have distinct names and UI placement.

---

# D. Shared product language and visual system

- [ ] **P0** 119. Prefer one large working surface rather than card-heavy dashboards.
- [ ] **P1** 120. Make the desktop UI compact and scientific, closer to a workstation application than a landing page.
- [ ] **P1** 121. Minimize vertical scrolling for the most common actions.
- [ ] **P0** 122. Frequently used controls remain visible.
- [ ] **P0** 123. Rare/advanced controls live behind `Дополнительно` / `Технические сведения`.
- [ ] **P0** 124. Primary navigation contains only real user tasks.
- [ ] **P0** 125. Keep primary navigation to roughly 8–9 tasks.
- [ ] **P0** 126. Never expose `v0154`, wrapper, staging-state internals, UUID or session-state terminology in ordinary UI.
- [ ] **P0** 127. Project context should remain stable and should not be asked for repeatedly on every page.
- [ ] **P1** 128. The working surface should always make clear: current project, current data universe, visible row count and selection count.
- [ ] **P0** 129. Use one shared Selection action bar instead of unrelated action buttons across pages.
- [ ] **P0** 130. Use one scientific object language across the application: `Sample → Grain → Point → Work Group → Generation`.
- [ ] **P0** 131. Same action = same wording everywhere.
- [ ] **P0** 132. Back restores working state rather than merely changing route.
- [ ] **P1** 133. Avoid opening another page when a contextual action can be completed in the current workspace.
- [ ] **P1** 134. Home should contain `Continue`, a compact quick-action row, current project and recent data; no large dashboard-card explosion.
- [ ] **P1** 135. Global search should cover Sample, Grain, Mineral, Article/Source, Dataset, Image and Analysis.
- [ ] **P1** 136. Search results should be grouped by scientific entity type.
- [ ] **P1** 137. Search results should open the correct workspace with filter/context already prepared.
- [ ] **P1** 138. Example: `apatite + Smith 2024` → show analyses/images/Samples/source → `Open on plot`.
- [ ] **P0** 139. Every destructive action must explain its consequences and require explicit confirmation.
- [ ] **P0** 140. Scientific source values must never be overwritten by derived/calculated values.
- [ ] **P0** 141. APFU/derived results remain separate from raw chemistry.
- [ ] **P0** 142. Provenance must always remain available without dominating the default workspace.
- [ ] **P0** 143. PetroLab should feel like one application, not a collection of Streamlit pages written at different times.

---

# E. Master acceptance scenario

The following scenario is the principal product acceptance test for this backlog:

> A user selects several mica analyses in the table, compares them on several plots, hides one article/source, brushes additional points, checks PCA/clustering, creates a Work Group, approves a Generation and calculates APFU — **without ever having to re-identify which analyses are currently being studied**.

Acceptance requirements:

- the exact same immutable analysis IDs survive across table, XY, multi-panel, PCA/cluster, profile and formula/APFU workflows;
- Filter, Selection, Hide, Exclude, Work Group and Generation remain separate states/concepts;
- Back restores the relevant working context;
- no temporary subset requires dataset duplication;
- scientific raw data and provenance are preserved;
- ordinary user-facing labels remain human-readable;
- no new wrapper/bridge/monkey-patch layer is introduced to satisfy the scenario.

---

# F. Recommended implementation order

## Phase 1 — P0 consolidation

1. Finish canonical Data Workspace and SelectionContext contracts.
2. Finish linked selection across table/XY/multi-panel/PCA/cluster/profile.
3. Finish Filter/Selection/Hide/Exclude separation.
4. Finish canonical PlotSpec and XY→multi-panel handoff.
5. Finish canonical import/provenance workflow and remove active monkey-patch wrappers.
6. Finish Back/context restoration and human-readable labels.
7. Keep all destructive actions explicit and safe.

## Phase 2 — P1 productivity

1. Saved table views and richer search.
2. Linked record detail and source/article comparison workflows.
3. Legend-based selection and stronger linked highlighting.
4. Panel/Series managers, shared axes/legend and plot duplication.
5. Source-aware global search and direct context handoff.
6. Visual density/polish pass against Airtable/JMP/Origin patterns.

## Phase 3 — P2 advanced/publishing

1. Advanced manual graph geometry only where genuinely needed.
2. Publication-quality vector/export hardening.
3. Further publication-composer ergonomics and reusable style specifications.

---

# G. Definition of done for the master backlog

A backlog item is not complete merely because code exists. It is complete only when:

1. there is one canonical implementation owner for the behavior;
2. no competing legacy route/state/wrapper remains active for the same concept;
3. focused tests pass;
4. integration tests prove state handoff where relevant;
5. a real Streamlit/browser workflow is exercised for user-facing behavior where technically possible;
6. source data/provenance remains safe;
7. the behavior matches the designated reference model: Airtable for data, JMP for linked exploration, OriginPro for plots/composition.
