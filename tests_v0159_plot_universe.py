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
    source_visibility = source.index("render_source_visibility_controls(")
    series_visibility = source.index("render_series_manager(")
    spec_membership = source.index("analysis_ids=universe_analysis_ids")
    assert capture < source_visibility < series_visibility < spec_membership

    # This is the scientific contract: Show/Hide and series visibility are presentation
    # operations. They may change plot_source, but never the membership carried by PlotSpec.
    forbidden = 'analysis_ids=tuple(plot_source["_analysis_id"]'
    assert forbidden not in source
    print("PetroLab 0.15.9 quick PlotSpec DataUniverse: OK")


if __name__ == "__main__":
    main()
