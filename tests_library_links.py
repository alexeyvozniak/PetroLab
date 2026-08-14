from __future__ import annotations

import os
import tempfile
from pathlib import Path

# SQLite can briefly retain a file handle after a connection has been closed on
# Windows.  Test cleanup must not turn an otherwise successful regression into
# a platform-specific failure.
_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ["PETROLAB_DATA_DIR"] = str(Path(_tmp.name) / "petrolab_data")

from petrolab.db import (  # noqa: E402
    add_dataset,
    create_project,
    get_or_create_library_project,
    link_dataset_to_project,
    list_accessible_datasets,
)


def _dataset(project_id: int, name: str) -> int:
    return add_dataset(
        project_id, name, "phlogopite", "source.xlsx", "Data", "test-hash", "", 0,
    )


try:
    article = create_project("Por'ya Guba micas")
    turiy = create_project("Turiy Mys micas")
    library = get_or_create_library_project()
    own = _dataset(article, "Por'ya Guba")
    external = _dataset(turiy, "Turiy Mys")
    archived = _dataset(library, "Reference micas")

    link_dataset_to_project(article, external, "comparison")
    link_dataset_to_project(article, archived, "reference")
    visible = {int(row["id"]): int(row["linked_to_project"]) for row in list_accessible_datasets(article)}
    assert visible == {own: 0, external: 1, archived: 1}
    print("library link tests: OK")
finally:
    _tmp.cleanup()
