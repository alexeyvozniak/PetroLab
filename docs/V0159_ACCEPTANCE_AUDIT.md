# PetroLab 0.15.9 — acceptance audit after PR #89

A green CI result is not sufficient if the final UI is awkward or screenshots are captured while Streamlit is still rerunning.

## Release blockers

1. Browser screenshots and geometry checks run only after Streamlit has finished the current rerun.
2. Primary research viewports complete at 1440×900, 1024×768, 968×516, 768×900 and 390×844.
3. Graphs expose a scientifically useful first result without silent scope expansion. Exact `analysis_id` membership survives reruns and presentation changes.
4. No visible Streamlit exception, global horizontal overflow or overlapping shell controls.
5. The release version advances so installed clients can actually detect the build as an update.

## Manual acceptance focus

- Home: hierarchy is obvious and primary actions are usable.
- Data: selected Sample/dataset and current section are obvious; the analyses section actually renders its table.
- Graphs: first plot is visible in the initial viewport, selectors remain readable at laptop widths, manual X/Y and source visibility remain available without overwhelming the first result.
- Add Data: Excel/CSV + images remains one normal route; scientific ambiguity is warned rather than guessed.
- Thin sections/images: physical context and analytical links are explicit and image annotation is never silently treated as Generation.

## Scientific invariants

`Textural zone`, `Work Group`, `Generation`, Selection, Hide and Exclude remain distinct states. UI simplification must not merge these meanings.
