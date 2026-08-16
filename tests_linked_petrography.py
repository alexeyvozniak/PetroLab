from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

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


def test_related_links_require_explicit_analysis_link() -> None:
    images = [
        SimpleNamespace(id=5, thin_section_id=50, title="BSE-01", image_type="BSE"),
        SimpleNamespace(id=6, thin_section_id=None, title="Loose image", image_type="Другое"),
    ]
    entities = [{"id": 50, "kind": "thin_section", "name": "KIV-2-1"}]
    markers = [
        {
            "id": 7,
            "slide_image_id": 5,
            "label": "P-7",
            "entity_name": "",
            "x_norm": 0.25,
            "y_norm": 0.40,
            "analysis_ids": ["epma-7", "la-7"],
        },
        {
            "id": 8,
            "slide_image_id": 5,
            "label": "epma-7",  # same text, but no explicit analysis link
            "entity_name": "",
            "x_norm": 0.75,
            "y_norm": 0.70,
            "analysis_ids": ["unrelated"],
        },
        {
            "id": 9,
            "slide_image_id": 6,
            "label": "loose",
            "entity_name": "",
            "x_norm": 0.1,
            "y_norm": 0.1,
            "analysis_ids": ["epma-7"],
        },
    ]
    with (
        patch.object(bridge, "list_slide_images", return_value=images),
        patch.object(bridge, "list_entities", return_value=entities),
        patch.object(bridge, "list_slide_markers", return_value=markers),
    ):
        links = bridge.related_thin_section_markers(1, ("epma-7",))

    assert len(links) == 1
    link = links[0]
    assert link.marker_id == 7
    assert link.slide_image_id == 5
    assert link.thin_section_id == 50
    assert link.analysis_ids == ("epma-7", "la-7")
    assert link.display_label == "KIV-2-1 · BSE-01 · P-7"


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
        test_related_links_require_explicit_analysis_link,
        test_ui_contract_keeps_one_selection_context,
    )
    for test in tests:
        test()
    print("PetroLab linked petrography P0: OK")


if __name__ == "__main__":
    main()
