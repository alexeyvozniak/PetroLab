from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def _ids(dataframe: pd.DataFrame) -> set[str]:
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        return set()
    return {str(value) for value in dataframe["_analysis_id"].dropna().tolist() if str(value)}


def table_scope_counts(
    universe: pd.DataFrame,
    visible: pd.DataFrame,
    selection_ids: Iterable[object] = (),
) -> dict[str, int]:
    """Count the three scopes users must not confuse in the Data Workspace.

    ``universe`` is the current dataset/work-object context, ``visible`` is the
    current Table View after search/filter, and Selection is the canonical
    cross-view analysis-ID set. Selection may legitimately extend outside the
    current universe after comparing several articles or datasets.
    """
    selected = {str(value) for value in selection_ids if str(value)}
    universe_ids = _ids(universe)
    visible_ids = _ids(visible)
    return {
        "universe": len(universe_ids) if universe_ids else len(universe),
        "visible": len(visible_ids) if visible_ids else len(visible),
        "selection": len(selected),
        "selection_here": len(selected & universe_ids) if universe_ids else 0,
        "selection_visible": len(selected & visible_ids) if visible_ids else 0,
        "selection_outside": len(selected - universe_ids) if universe_ids else len(selected),
    }


def table_scope_caption(counts: dict[str, int]) -> str:
    universe = int(counts.get("universe", 0))
    visible = int(counts.get("visible", 0))
    selection = int(counts.get("selection", 0))
    selection_here = int(counts.get("selection_here", 0))
    outside = int(counts.get("selection_outside", 0))
    parts = [f"Всего · {universe}", f"В виде · {visible}", f"Selection · {selection}"]
    if selection and selection_here != selection:
        parts.append(f"здесь · {selection_here}")
    if outside:
        parts.append(f"вне текущего контекста · {outside}")
    return " · ".join(parts)
