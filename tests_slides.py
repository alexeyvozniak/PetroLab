from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PIL import Image


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_slides_", ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        os.environ["PETROLAB_DATA_DIR"] = str(root / "data")

        from petrolab.db import create_project
        from petrolab.measurement_registry import create_entity
        from petrolab.slides import (
            STORAGE_LINKED,
            create_slide_field,
            create_slide_marker,
            list_slide_fields,
            list_slide_images,
            list_slide_markers,
            register_linked_slide_image,
            relink_slide_original,
            render_slide_overlay,
        )

        project_id = create_project("Slides", "")
        section_id = create_entity(project_id, kind="thin_section", name="PG-12")
        original = root / "PG-12.tif"
        Image.new("RGB", (3200, 1200), "#b9b3a8").save(original)

        slide = register_linked_slide_image(
            project_id, source_path=original, title="PG-12 full section", thin_section_id=section_id,
        )
        assert slide.storage_mode == STORAGE_LINKED
        assert slide.original_available
        assert slide.pixel_width == 3200 and slide.pixel_height == 1200
        assert Path(slide.preview_path).is_file()
        assert not slide.managed_path, "linked storage must not duplicate the TIFF"
        assert len(list_slide_images(project_id)) == 1

        field_id = create_slide_field(
            project_id, slide_image_id=slide.id, name="Mica cluster",
            geometry={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        )
        marker_id = create_slide_marker(
            project_id, slide_image_id=slide.id, field_id=field_id, x_norm=0.25, y_norm=0.4,
            label="EDS-17",
        )
        markers = list_slide_markers(project_id, slide_image_id=slide.id)
        assert markers[0]["id"] == marker_id
        assert markers[0]["label"] == "EDS-17"
        overlay = render_slide_overlay(slide, markers, list_slide_fields(project_id, slide_image_id=slide.id))
        assert overlay.size[0] <= 2560 and overlay.size[1] <= 2560

        moved = root / "moved" / "PG-12.tif"
        moved.parent.mkdir()
        original.rename(moved)
        assert not slide.original_available
        repaired = relink_slide_original(slide.id, moved)
        assert repaired.original_available

    print("slides tests: OK")


if __name__ == "__main__":
    main()
