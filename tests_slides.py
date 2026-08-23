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
            attach_image_to_slide_field,
            create_slide_field,
            create_slide_marker,
            field_geometry_from_corners,
            list_slide_fields,
            list_slide_images,
            list_slide_markers,
            list_field_images,
            register_linked_slide_image,
            register_managed_slide_image,
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

        square = field_geometry_from_corners((0.1, 0.2), (0.4, 0.7), shape="square")
        assert square["kind"] == "square"
        assert abs(float(square["width"]) - float(square["height"])) < 1e-9
        assert abs(float(square["width"]) - 0.5) < 1e-9
        try:
            field_geometry_from_corners((0.1, 0.2), (0.4, 0.7), shape="polygon")
        except ValueError as exc:
            assert "прямоугольник" in str(exc)
        else:
            raise AssertionError("arbitrary field shapes must be rejected")

        field_id = create_slide_field(
            project_id, slide_image_id=slide.id, name="Mica cluster",
            geometry={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        )
        try:
            create_slide_field(
                project_id, slide_image_id=slide.id, name="Contour",
                geometry={"vertices": [[0.1, 0.1], [0.2, 0.2], [0.1, 0.2]]},
            )
        except ValueError as exc:
            assert "Сложные контуры" in str(exc)
        else:
            raise AssertionError("contours must not be persisted as slide fields")
        marker_id = create_slide_marker(
            project_id, slide_image_id=slide.id, field_id=field_id, x_norm=0.25, y_norm=0.4,
            label="EDS-17",
        )
        markers = list_slide_markers(project_id, slide_image_id=slide.id)
        assert markers[0]["id"] == marker_id
        assert markers[0]["label"] == "EDS-17"
        overlay = render_slide_overlay(slide, markers, list_slide_fields(project_id, slide_image_id=slide.id))
        assert overlay.size[0] <= 2560 and overlay.size[1] <= 2560

        bse = register_managed_slide_image(
            project_id, filename="field-bse.png", data=original.read_bytes(), title="BSE-03", image_type="BSE",
        )
        attach_image_to_slide_field(project_id, field_id=field_id, image_id=bse.id)
        second_field = create_slide_field(
            project_id, slide_image_id=slide.id, name="Mica rim",
            geometry={"x": 0.5, "y": 0.2, "width": 0.2, "height": 0.2},
        )
        attach_image_to_slide_field(project_id, field_id=second_field, image_id=bse.id, move=True)
        assert list_field_images(project_id, field_id=field_id) == []
        assert [item.id for item in list_field_images(project_id, field_id=second_field)] == [bse.id]
        eds = register_managed_slide_image(
            project_id, filename="field-eds.png", data=original.read_bytes(), title="EDS-Si", image_type="EDS-карта",
        )
        try:
            attach_image_to_slide_field(project_id, field_id=field_id, image_id=eds.id)
        except ValueError as exc:
            assert "только отдельный BSE" in str(exc)
        else:
            raise AssertionError("an EDS map must stay a linked measurement, not a field BSE")

        moved = root / "moved" / "PG-12.tif"
        moved.parent.mkdir()
        original.rename(moved)
        assert not slide.original_available
        repaired = relink_slide_original(slide.id, moved)
        assert repaired.original_available

    print("slides tests: OK")


if __name__ == "__main__":
    main()
