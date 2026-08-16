# PetroLab: linked petrography workflow

See branch history for the full product contract. This branch implements the linked scientific round trip:

**plot Selection → exact analysis ids → physical thin-section points → highlighted image location → back to the same Selection in plots/table/statistics.**

Scientific invariants:
- Textural zone, Work Group and Generation remain distinct;
- Selection, Hide and Exclude remain distinct;
- no physical identity is inferred from labels alone;
- one physical point may link several analytical observations (e.g. EPMA + LA-ICP-MS);
- exact analysis scope must never broaden silently;
- PPL/XPL/BSE coordinates are not treated as shared until explicit registration exists.

P0 acceptance:
1. A plot Selection with linked physical markers offers `Open on thin section`.
2. One marker opens directly; multiple markers use a compact chooser.
3. The exact image and thin section open and corresponding marker(s) are highlighted.
4. Selecting a marker sets canonical Selection to all analyses linked to that physical point.
5. `Open in plots` reuses compatible DataUniverse or passes an exact analysis scope.
6. Returning to plots preserves Selection and does not broaden membership.
