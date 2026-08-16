from __future__ import annotations

import inspect

import petrolab.linked_petrography as bridge


def test_marker_selection_is_exact_and_multi_method() -> None:
    markers = [
        {"id": 1, "label": "P-1", "analysis_ids": ["epma-1", "la-1"], "x_norm": 0.10, "y_norm": 0.20},
        {"id": 2, "label": "P-2", "analysis_ids": ["epma-2"], "x_norm": 0.50, "y_norm": 0.50},
        {"id": 3, "label": "epma-1", "analysis_ids": ["other-3"], "x_norm": 0.80, "y_norm": 0.80},
    ]
    assert bridge.marker_ids_for_selection(markers, ("epma-1",)) == (1,)
    assert bridge.analysis_ids_for_marker(markers, 1) == ("epma-1", "la-1")
    assert bridge.analysis_ids_for_marker(markers, 999) == ()


def test_nearest_marker_uses_spatial_distance_not_label() -> None:
    markers = [
        {"id": 10, "label": "anything", "x_norm": 0.20, "y_norm": 0.30, "analysis_ids": ["a"]},
        {"id": 20, "label": "target", "x_norm": 0.80, "y_norm": 0.70, "analysis_ids": ["b"]},
    ]
    assert bridge.nearest_marker_id(markers, x_norm=0.205, y_norm=0.305, aspect_ratio=0.75) == 10
    assert bridge.nearest_marker_id(markers, x_norm=0.50, y_norm=0.50, aspect_ratio=0.75) is None


def test_related_lookup_is_explicit_and_indexed() -> None:
    source = inspect.getsource(bridge.related_thin_section_markers)
    assert "slide_marker_analysis_links selected_link" in source
    assert "selected_link.analysis_id IN" in source
    assert "slide_marker_analysis_links all_links" in source
    assert "JOIN physical_entities section" in source
    assert "list_slide_markers" not in source
    assert "Sample" not in source and "Point" not in source


def test_ui_contract_keeps_one_selection_context() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parent
    selection_ui = (root / "petrolab" / "ui" / "selection_components.py").read_text(encoding="utf-8")
    thin_ui = (root / "petrolab" / "ui" / "pages" / "thin_section_workspace.py").read_text(encoding="utf-8")

    assert "related_thin_section_markers" in selection_ui
    assert 'st.session_state["thin_section_focus_id_pending"]' in selection_ui
    assert 'st.session_state["thin_image_focus_id_pending"]' in selection_ui
    assert "set_selection(" in thin_ui
    assert "marker_ids_for_selection" in thin_ui
    assert "nearest_marker_id" in thin_ui
    assert "seed_selection_plot_handoff" in thin_ui
    assert 'analysis_ids=context.analysis_ids' in thin_ui


def main() -> None:
    tests = (
        test_marker_selection_is_exact_and_multi_method,
        test_nearest_marker_uses_spatial_distance_not_label,
        test_related_lookup_is_explicit_and_indexed,
        test_ui_contract_keeps_one_selection_context,
    )
    for test in tests:
        test()
    print("PetroLab linked petrography P0: OK")


if __name__ == "__main__":
    main()
