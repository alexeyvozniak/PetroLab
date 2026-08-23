from pathlib import Path


ROOT = Path(__file__).resolve().parent
SELECTION_COMPONENTS = (ROOT / "petrolab" / "ui" / "selection_components.py").read_text(encoding="utf-8")
LINKED_VIEWS = (ROOT / "petrolab" / "ui" / "pages" / "linked_views.py").read_text(encoding="utf-8")
LINKED_PANELS = (ROOT / "petrolab" / "ui" / "linked_panels.py").read_text(encoding="utf-8")


def main() -> None:
    # A graph selection must state its outcome in user language and must never
    # be confused with QC exclusion or deleting a measurement.
    for marker in [
        "Новый отбор", "Добавить к отбору", "Убрать из отбора",
        "Это не QC-исключение и не удаление данных.",
        "selection_action_description", "selection_action_label",
    ]:
        assert marker in SELECTION_COMPONENTS, marker
    for marker in [
        "Применить выделение", "Сейчас выделено на графиках:",
        "selection_action_label", "Очистить рабочую выборку", "set_selection",
    ]:
        assert marker in LINKED_VIEWS, marker
    assert "Текущий режим:" in LINKED_PANELS
    print("v0.16 contextual selection UX gate: OK")


if __name__ == "__main__":
    main()
