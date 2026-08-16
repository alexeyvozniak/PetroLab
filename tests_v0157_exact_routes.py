from __future__ import annotations

from pathlib import Path

from petrolab.ui.exact_route import clear_exact_route, persist_exact_route


def main() -> None:
    state: dict = {
        "incoming_a": ["a1", "a2", "a1"],
        "incoming_d": [10, "11", 10],
        "incoming_c": {"search": "rim"},
    }
    exact, datasets, context = persist_exact_route(
        state,
        incoming_analysis_key="incoming_a",
        incoming_dataset_key="incoming_d",
        incoming_context_key="incoming_c",
        persistent_analysis_key="persist_a",
        persistent_dataset_key="persist_d",
        persistent_context_key="persist_c",
    )
    assert exact == ["a1", "a2"]
    assert datasets == [10, 11]
    assert context == {"search": "rim"}

    # Simulate the page consuming routed keys. The next rerun must rehydrate the
    # exact scope rather than silently expanding to every row in the datasets.
    state.pop("incoming_a")
    state.pop("incoming_d")
    state.pop("incoming_c")
    exact, datasets, context = persist_exact_route(
        state,
        incoming_analysis_key="incoming_a",
        incoming_dataset_key="incoming_d",
        incoming_context_key="incoming_c",
        persistent_analysis_key="persist_a",
        persistent_dataset_key="persist_d",
        persistent_context_key="persist_c",
    )
    assert exact == ["a1", "a2"]
    assert state["incoming_a"] == ["a1", "a2"]
    assert state["incoming_d"] == [10, 11]
    assert state["incoming_c"] == {"search": "rim"}

    # A deliberate dataset-only navigation replaces the previous exact route.
    state.pop("incoming_a")
    state["incoming_d"] = [99]
    persist_exact_route(
        state,
        incoming_analysis_key="incoming_a",
        incoming_dataset_key="incoming_d",
        incoming_context_key="incoming_c",
        persistent_analysis_key="persist_a",
        persistent_dataset_key="persist_d",
        persistent_context_key="persist_c",
    )
    assert "persist_a" not in state
    assert "persist_d" not in state
    assert "persist_c" not in state

    clear_exact_route(
        state,
        persistent_analysis_key="persist_a",
        persistent_dataset_key="persist_d",
        persistent_context_key="persist_c",
    )

    # These pages own the state now; they must not be rebound by v0156.
    pages_init = Path("petrolab/ui/pages/__init__.py").read_text(encoding="utf-8")
    wrapper_block = pages_init.split("from .v0156_audit_wrappers import (", 1)[1].split(")", 1)[0]
    for name in ("render_analyses_page", "render_article_tables_page", "render_batch_edit_page"):
        assert name not in wrapper_block, name

    analyses = Path("petrolab/ui/pages/analyses_dashboard.py").read_text(encoding="utf-8")
    article = Path("petrolab/ui/pages/article_tables.py").read_text(encoding="utf-8")
    batch = Path("petrolab/ui/pages/batch_edit.py").read_text(encoding="utf-8")
    for text in (analyses, article, batch):
        assert "persist_exact_route(" in text
        assert "render_exact_route_banner(" in text

    assert "analysis_id[:8]" not in analyses
    print("v0.15.7 canonical exact-route gate: OK")


if __name__ == "__main__":
    main()
