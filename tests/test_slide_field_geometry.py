from petrolab.slides import _normalise_rectangle_geometry, is_bse_image_type


def test_slide_field_geometry_accepts_only_rectangles_and_squares() -> None:
    rectangle = _normalise_rectangle_geometry(
        {"kind": "rectangle", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
    )
    square = _normalise_rectangle_geometry(
        {"kind": "square", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.3}
    )

    assert rectangle["kind"] == "rectangle"
    assert square["kind"] == "square"


def test_bse_type_is_explicit() -> None:
    assert is_bse_image_type("BSE")
    assert not is_bse_image_type("PPL")
    assert not is_bse_image_type("EDS-карта")
