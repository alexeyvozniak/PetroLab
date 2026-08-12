from __future__ import annotations

from pathlib import Path


APP_PATH = Path("app.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")

    text = replace_once(text, "    create_project,\n", "", "unused create_project import")
    text = replace_once(
        text,
        "from petrolab.minerals.registry import MINERALS, labels as mineral_labels\n",
        "from petrolab.minerals.registry import MINERALS\n",
        "mineral registry import",
    )
    text = replace_once(
        text,
        "from petrolab.sources import reload_linked_source, source_status, sync_cell_changes\n",
        "from petrolab.sources import reload_linked_source, source_status, sync_cell_changes\n"
        "from petrolab.ui.pages import render_home_page, render_projects_page\n",
        "UI page imports",
    )

    start = text.index('if page == "Главная":')
    end = text.index('elif page == "Источники и импорт":', start)
    replacement = (
        'if page == "Главная":\n'
        '    render_home_page()\n\n'
        'elif page == "Проекты":\n'
        '    render_projects_page()\n\n'
    )
    text = text[:start] + replacement + text[end:]

    forbidden = {
        "home page body": 'st.subheader("Новая графическая логика")',
        "project creation form": 'with st.form("new_project"',
        "create_project import": "    create_project,",
        "mineral_labels import": "mineral_labels",
    }
    for label, token in forbidden.items():
        if token in text:
            raise RuntimeError(f"{label} still present in app.py")

    if "render_home_page()" not in text or "render_projects_page()" not in text:
        raise RuntimeError("Page render calls were not installed")

    APP_PATH.write_text(text, encoding="utf-8")
    print(f"Extracted Home/Projects pages; app.py = {len(text.splitlines())} lines")


if __name__ == "__main__":
    main()
