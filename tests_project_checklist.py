from __future__ import annotations

import os
import tempfile
from pathlib import Path


_TMP = tempfile.TemporaryDirectory(prefix="petrolab_project_checklist_", ignore_cleanup_errors=True)
os.environ["PETROLAB_DATA_DIR"] = str(Path(_TMP.name) / "data")

from petrolab.db import add_dataset, create_project
from petrolab.project_checklist import (
    create_project_checklist_item,
    list_project_checklist_items,
    set_project_checklist_item_completed,
)


def main() -> None:
    project_id = create_project("Checklist")
    dataset_id = add_dataset(
        project_id, "LA-ICP-MS · 19 ТР-1", "phlogopite", "19tr1.xlsx", "LA",
        "hash", str(Path(_TMP.name) / "rows.csv"), 3,
    )
    item_id = create_project_checklist_item(
        project_id,
        title="Разобрать LA-ICP-MS для 19 ТР-1",
        note="Проверить названия фаз и Generation",
        dataset_id=dataset_id,
        target_route="analyses",
    )
    active = list_project_checklist_items(project_id)
    assert [int(item["id"]) for item in active] == [item_id]
    assert active[0]["dataset_name"] == "LA-ICP-MS · 19 ТР-1"
    assert active[0]["status"] == "open"

    assert set_project_checklist_item_completed(project_id, item_id, completed=True) is True
    assert list_project_checklist_items(project_id) == []
    done = list_project_checklist_items(project_id, completed=True)
    assert [int(item["id"]) for item in done] == [item_id]
    assert done[0]["completed_at"]

    assert set_project_checklist_item_completed(project_id, item_id, completed=False) is True
    assert [int(item["id"]) for item in list_project_checklist_items(project_id)] == [item_id]
    try:
        create_project_checklist_item(project_id, title="   ")
    except ValueError as exc:
        assert "Опишите" in str(exc)
    else:
        raise AssertionError("Empty checklist item must be rejected")
    print("project checklist tests: OK")


if __name__ == "__main__":
    main()
