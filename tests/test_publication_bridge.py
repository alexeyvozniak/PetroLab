from __future__ import annotations

from petrolab.ui.publication_bridge import add_publication_image_source


def test_publication_bridge_keeps_one_copy_of_same_mixed_layout() -> None:
    state: dict = {}

    first = add_publication_image_source(
        state,
        name="Linked binary + ternary + spider",
        image_bytes=b"mixed-layout",
        note="exact selection",
    )
    second = add_publication_image_source(
        state,
        name="Linked binary + ternary + spider",
        image_bytes=b"mixed-layout",
        note="exact selection",
    )

    assert first["source_id"] == second["source_id"]
    assert len(state["publication_composer_inbox"]) == 1
    assert state["publication_composer_inbox"][0]["group"] == "Графики PetroLab"
