# PetroLab linked petrography P0

Round trip: plot Selection → exact analysis ids → physical thin-section points → highlighted image location → same Selection back in plots/table/statistics.

Scientific invariants:
- Textural zone ≠ Work Group ≠ Generation.
- Selection ≠ Hide ≠ Exclude.
- No physical identity is inferred from labels alone.
- One physical point may link multiple analytical observations (for example EPMA + LA-ICP-MS).
- Exact analysis scope never broadens silently.
- PPL/XPL/BSE coordinates are not shared without explicit registration.

P0 acceptance:
1. Plot Selection exposes `Open on thin section` only when exact physical links exist.
2. One linked physical point opens directly; multiple points use a deterministic chooser.
3. PetroLab opens the exact thin section and image and highlights linked marker coordinates.
4. Selecting a marker sets canonical Selection to all analyses linked to that physical point.
5. `Open in plots` carries exact analysis ids through Smart Start without scope broadening.
6. Returning between plots/table/thin section preserves canonical Selection.
