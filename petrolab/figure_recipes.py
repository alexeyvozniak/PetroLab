"""Reproducible multi-panel publication layouts.

The layout stores references to chart recipes rather than copied pixels.  A
cell may be an XY, ternary or spider panel; later rendering therefore starts
from the same data and settings that produced the panel.
"""
from __future__ import annotations

import json

from petrolab.db import _utcnow, connect


LAYOUTS = {"1 × 1": (1, 1), "2 × 1": (2, 1), "2 × 2": (2, 2), "3 × 2": (3, 2)}
PANEL_TYPES = ("XY", "Треугольная", "REE / Spider", "Внешний SVG/PNG")


def ensure_figure_recipe_schema() -> None:
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS figure_recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                layout_name TEXT NOT NULL,
                cells_json TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id,name),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )"""
        )
        con.commit()


def save_figure_recipe(project_id: int, *, name: str, layout_name: str, cells: list[dict], note: str = "") -> int:
    ensure_figure_recipe_schema()
    label = str(name).strip()
    if not label:
        raise ValueError("Назовите Figure Recipe")
    if layout_name not in LAYOUTS:
        raise ValueError("Неизвестная компоновка")
    capacity = LAYOUTS[layout_name][0] * LAYOUTS[layout_name][1]
    if len(cells) != capacity:
        raise ValueError("Количество панелей не соответствует выбранной сетке")
    for cell in cells:
        if str(cell.get("type") or "") not in PANEL_TYPES:
            raise ValueError("Неизвестный тип панели")
        if not str(cell.get("reference") or "").strip() and str(cell.get("type")) != "Внешний SVG/PNG":
            raise ValueError("Для каждой научной панели выберите сохранённый рецепт")
    now = _utcnow()
    with connect() as con:
        con.execute(
            """INSERT INTO figure_recipes(project_id,name,layout_name,cells_json,note,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?) ON CONFLICT(project_id,name) DO UPDATE SET
               layout_name=excluded.layout_name,cells_json=excluded.cells_json,note=excluded.note,updated_at=excluded.updated_at""",
            (int(project_id), label, layout_name, json.dumps(cells, ensure_ascii=False), str(note).strip(), now, now),
        )
        row = con.execute("SELECT id FROM figure_recipes WHERE project_id=? AND name=?", (int(project_id), label)).fetchone()
        con.commit()
    return int(row["id"])


def list_figure_recipes(project_id: int) -> list[dict]:
    ensure_figure_recipe_schema()
    with connect() as con:
        rows = con.execute("SELECT * FROM figure_recipes WHERE project_id=? ORDER BY updated_at DESC,id DESC", (int(project_id),)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["cells"] = json.loads(str(item.pop("cells_json") or "[]"))
        except json.JSONDecodeError:
            item["cells"] = []
        result.append(item)
    return result


def delete_figure_recipe(recipe_id: int) -> None:
    ensure_figure_recipe_schema()
    with connect() as con:
        con.execute("DELETE FROM figure_recipes WHERE id=?", (int(recipe_id),))
        con.commit()
