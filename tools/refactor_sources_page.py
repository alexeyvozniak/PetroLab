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

    text = replace_once(text, "from uuid import uuid4\n", "", "uuid4 import")
    for line in [
        "    DATA_DIR,\n",
        "    add_dataset,\n",
        "    replace_dataset_rows,\n",
        "    update_dataset_metadata,\n",
    ]:
        text = replace_once(text, line, "", f"unused db import {line.strip()}")

    io_start = text.index("from petrolab.io_utils import (")
    io_end = text.index(")\n", io_start) + 2
    io_block = text[io_start:io_end]
    if "numeric_candidates" not in io_block:
        raise RuntimeError("numeric_candidates missing from io_utils import block")
    text = text[:io_start] + "from petrolab.io_utils import numeric_candidates\n" + text[io_end:]

    text = replace_once(
        text,
        "from petrolab.sources import reload_linked_source, source_status, sync_cell_changes\n",
        "from petrolab.sources import sync_cell_changes\n",
        "sources import",
    )
    text = replace_once(
        text,
        "from petrolab.ui.pages import render_home_page, render_projects_page\n",
        "from petrolab.ui.pages import render_home_page, render_projects_page, render_sources_page\n",
        "page imports",
    )

    helper_start = text.index("def save_dataset(")
    helper_end = text.index("def collect_related_images(", helper_start)
    text = text[:helper_start] + text[helper_end:]

    source_start = text.index('elif page == "Источники и импорт":')
    source_end = text.index('elif page == "Единая база":', source_start)
    text = text[:source_start] + 'elif page == "Источники и импорт":\n    render_sources_page()\n\n' + text[source_end:]

    forbidden = [
        "def save_dataset(",
        "def safe_copy_upload(",
        "list_excel_sheets_path",
        "read_tabular_with_map",
        "reload_linked_source",
        'st.subheader("Локальный Excel с двусторонней синхронизацией")',
    ]
    for token in forbidden:
        if token in text:
            raise RuntimeError(f"old sources/import logic remained in app.py: {token}")
    if "render_sources_page()" not in text:
        raise RuntimeError("render_sources_page() was not wired into app.py")

    APP_PATH.write_text(text, encoding="utf-8")
    print(f"Extracted Sources/Import page; app.py = {len(text.splitlines())} lines")


if __name__ == "__main__":
    main()
