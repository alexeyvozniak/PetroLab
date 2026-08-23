from __future__ import annotations

import inspect

import pandas as pd

from petrolab.ui.pages.plots_dashboard import _analysis_universe_ids, _quick_workspace


def main() -> None:
    frame = pd.DataFrame(
        {
            "_analysis_id": ["a-1", "a-2", "a-1", "  a-3  ", ""],
            "Источник": ["A", "A", "A", "B", "B"],
        }
    )
    assert _analysis_universe_ids(frame) == ("a-1", "a-2", "a-3")
    assert _analysis_universe_ids(pd.DataFrame({"SiO2": [40.0]})) == ()

    source = inspect.getsource(_quick_workspace)
    capture = source.index("universe_analysis_ids = _analysis_universe_ids(dataframe)")
    mineral_picker = source.index("selected_minerals = st.multiselect(")
    search_filter = source.index("dataframe = apply_quick_filter(dataframe, query)")
    manifest_membership = source.index('"analysis_universe_ids": universe_analysis_ids')
    assert capture < mineral_picker < search_filter < manifest_membership

    # Mineral and text controls are presentation choices.  The publication
    # manifest keeps the eligible scientific universe, so the recipe remains
    # reproducible after a view is narrowed.
    print("PetroLab 0.16.0 quick plot DataUniverse: OK")


if __name__ == "__main__":
    main()
