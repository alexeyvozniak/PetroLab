from pathlib import Path


ROOT = Path(__file__).resolve().parent
IMAGE_COMPONENTS = ROOT / "petrolab" / "ui" / "image_components.py"
DESIGN = ROOT / "docs" / "DESIGN.md"


def test_petrology_specific_image_types_are_first_class() -> None:
    source = IMAGE_COMPONENTS.read_text(encoding="utf-8")
    for label in (
        '"Шлиф PPL"',
        '"Шлиф XPL"',
        '"BSE"',
        '"SEM / EDS"',
        '"Карта элементов"',
    ):
        assert label in source


def test_photo_linking_uses_scientific_entity_language() -> None:
    source = IMAGE_COMPONENTS.read_text(encoding="utf-8")
    assert '"Уровень привязки"' in source
    assert '"Конкретный объект"' in source
    assert '"Выбрать все найденные"' in source
    assert "EPMA, EDS и LA-ICP-MS остаются отдельными наблюдениями" in source


def test_design_keeps_thin_section_photo_flow_p0() -> None:
    design = DESIGN.read_text(encoding="utf-8")
    assert "## Обязательный сценарий: фотография шлифа" in design
    assert "Это P0-сценарий" in design
    assert "Sample 19 ТР-1 -> шлиф TR1-A -> Grain 7 -> точки 112, 113, 118" in design
    assert "Сохранить и следующее фото" in design
