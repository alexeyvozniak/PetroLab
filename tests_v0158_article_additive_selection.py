from __future__ import annotations

from pathlib import Path

import pandas as pd


def _article_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "_analysis_id": ["a1", "a2", "b1", "b2", "x1"],
            "Минерал": ["apatite", "apatite", "apatite", "apatite", "phlogopite"],
            "Источник / статья": ["Article A", "Article A", "Article B", "Article B", "Article A"],
            "P2O5": [41.0, 42.0, 40.5, 41.5, 0.1],
        }
    )


def test_article_a_then_add_article_b_preserves_exact_selection() -> None:
    from petrolab.ui.selection_context import read_selection, set_selection

    frame = _article_rows()
    state: dict[str, object] = {}
    apatite = frame.loc[frame["Минерал"].eq("apatite")]
    article_a = apatite.loc[apatite["Источник / статья"].eq("Article A")]
    article_b = apatite.loc[apatite["Источник / статья"].eq("Article B")]

    set_selection(article_a["_analysis_id"].tolist(), origin="Article A", mode="replace", state=state)
    assert read_selection(state).analysis_ids == ("a1", "a2")

    # Switching the table filter itself does not touch Selection. The explicit
    # `+ Видимые` action is represented by canonical Add mode.
    set_selection(article_b["_analysis_id"].tolist(), origin="Article B", mode="add", state=state)
    assert read_selection(state).analysis_ids == ("a1", "a2", "b1", "b2")
    assert "x1" not in read_selection(state).analysis_ids


def test_table_exposes_explicit_add_visible_action() -> None:
    source = (Path(__file__).resolve().parent / "petrolab" / "ui" / "analysis_table.py").read_text(encoding="utf-8")
    assert '"+ Видимые"' in source
    assert 'key=f"{key_prefix}_add_visible"' in source
    assert 'mode="add"' in source
    assert "Добавить все строки текущего фильтра" in source


def main() -> None:
    test_article_a_then_add_article_b_preserves_exact_selection()
    test_table_exposes_explicit_add_visible_action()
    print("v0.15.8 Article A + Article B additive selection: OK")


if __name__ == "__main__":
    main()
