"""Bridge reproducible Plotly views into the publication composer."""
from __future__ import annotations

import hashlib
from collections.abc import MutableMapping


def plotly_figure_png(figure, *, scale: int = 3) -> bytes:
    """Render an existing Plotly figure as a publication-composer source.

    The source is created from the same panel specification and current
    analysis selection used by the interactive view. Rendering requires the
    project's Plotly image backend (Kaleido); callers keep the failure visible.
    """
    import plotly.io as pio

    return bytes(pio.to_image(figure, format="png", scale=max(1, int(scale))))


def add_publication_image_source(
    state: MutableMapping,
    *,
    name: str,
    image_bytes: bytes,
    group: str = "Графики PetroLab",
    note: str = "",
) -> dict:
    """Append one immutable image source to the composer inbox without duplicates."""
    content = bytes(image_bytes)
    digest = hashlib.sha256(content).hexdigest()[:20]
    source = {
        "source_id": f"generated:{digest}",
        "source_name": str(name),
        "group": str(group),
        "note": str(note),
        "image_bytes": content,
    }
    inbox = [
        dict(item) for item in state.get("publication_composer_inbox", [])
        if isinstance(item, dict)
    ]
    if source["source_id"] not in {str(item.get("source_id")) for item in inbox}:
        inbox.append(source)
    state["publication_composer_inbox"] = inbox
    return source
