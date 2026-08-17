from __future__ import annotations

from petrolab.ui import universal_intake_extensions
from petrolab.ui.source_sheet_image_wizard import render_source_sheet_image_wizard

from . import v0160_user_ux_hotfix as _ux_chain


def render_add_data_page() -> None:
    """Use the source-sheet analysis universe while preserving the explicit Next step."""
    original = universal_intake_extensions.render_image_wizard_multi_dataset
    universal_intake_extensions.render_image_wizard_multi_dataset = render_source_sheet_image_wizard
    try:
        _ux_chain.render_add_data_page()
    finally:
        universal_intake_extensions.render_image_wizard_multi_dataset = original
