# PetroLab 0.15.9 — acceptance audit after PR #89

This hardening pass exists because a green CI result is not sufficient if the final UI is still awkward or screenshots are captured while Streamlit is rerunning.

## Release blockers

1. Browser screenshots and geometry checks must run only after Streamlit has finished the current rerun.
2. Every primary research viewport must complete at 1440×900, 1024×768, 968×516, 768×900 and 390×844; an incomplete artifact set is a failed visual audit, not a success.
3. Graphs must expose a scientifically useful first result without silent scope expansion. Exact `analysis_id` membership survives reruns and presentation changes.
4. No visible Streamlit exception, global horizontal overflow or overlapping shell controls.
5. The release version must advance so installed clients can actually detect the build as an update.

## Manual acceptance focus

- Home: hierarchy is obvious; no duplicated action dominates the screen.
- Data: selected Sample/dataset and current section are obvious; useful content appears after the selector rather than a misleading blank canvas.
- Graphs: first plot is visually dominant; selectors are readable at laptop widths; manual X/Y and source visibility remain available without overwhelming the first result.
- Add Data: Excel/CSV + images remains one normal route; scientific ambiguity is warned rather than guessed.
- Thin sections/images: physical context and analytical links are explicit and no image annotation is silently treated as Generation.

## Scientific invariants

`Textural zone`, `Work Group`, `Generation`, Selection, Hide and Exclude remain distinct states. UI simplification must not merge these meanings.
