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

    text = replace_once(
        text,
        "from petrolab.io_utils import (\n",
        "from petrolab.dataframe_utils import (\n"
        "    apply_column_filters,\n"
        "    apply_quick_filter,\n"
        "    compute_changes,\n"
        "    dataset_label,\n"
        "    display_value,\n"
        "    row_identity,\n"
        ")\n"
        "from petrolab.io_utils import (\n",
        "dataframe utility import",
    )
    text = replace_once(
        text,
        "from petrolab.plotting import MARKERS, build_scatter, figure_png_bytes, figure_svg_bytes\n",
        "from petrolab.plot_presets import JOURNAL_PRESETS\n"
        "from petrolab.plotting import MARKERS, build_scatter, figure_png_bytes, figure_svg_bytes\n",
        "plot preset import",
    )

    preset_start = text.index("JOURNAL_PRESETS = {")
    preset_end = text.index("\n\ndef project_selector", preset_start)
    text = text[:preset_start] + text[preset_end + 2 :]

    helpers_start = text.index("def row_identity")
    helpers_end = text.index("\n\ndef collect_related_images", helpers_start)
    text = text[:helpers_start] + text[helpers_end + 2 :]

    text = replace_once(
        text,
        "    changes = compute_changes(shown, edited)\n",
        "    changes = compute_changes(\n"
        "        shown,\n"
        "        edited,\n"
        "        protected_columns=META_COLUMNS | {\"Σ оксидов\", \"QC суммы\"},\n"
        "    )\n",
        "compute_changes call",
    )

    old_card = (
        '            st.dataframe(pd.DataFrame({"Параметр": [c for c in shown.columns if not str(c).startswith("_")], '
        '"Значение": [selected_row.get(c) for c in [c for c in shown.columns if not str(c).startswith("_")]]}), '
        'use_container_width=True, hide_index=True, height=360)'
    )
    new_card = (
        '            visible_columns = [c for c in shown.columns if not str(c).startswith("_")]\n'
        '            point_properties = pd.DataFrame(\n'
        '                {\n'
        '                    "Параметр": visible_columns,\n'
        '                    "Значение": [display_value(selected_row.get(c)) for c in visible_columns],\n'
        '                }\n'
        '            )\n'
        '            st.dataframe(point_properties, width="stretch", hide_index=True, height=360)'
    )
    text = replace_once(text, old_card, new_card, "point property table")

    text = text.replace("use_container_width=True", 'width="stretch"')
    text = text.replace("use_container_width=False", 'width="content"')

    forbidden = {
        "local JOURNAL_PRESETS": "JOURNAL_PRESETS = {",
        "local row_identity": "def row_identity",
        "local compute_changes": "def compute_changes",
        "deprecated use_container_width": "use_container_width",
    }
    for label, token in forbidden.items():
        if token in text:
            raise RuntimeError(f"{label} still present after refactor")

    APP_PATH.write_text(text, encoding="utf-8")
    print(f"Refactored app.py: {len(text.splitlines())} lines")


if __name__ == "__main__":
    main()
