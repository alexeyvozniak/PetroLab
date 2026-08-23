"""A failing second sheet must not leave the first one imported."""
from __future__ import annotations

import io
import os
import tempfile
import time
import gc
from pathlib import Path

import pandas as pd


def main() -> None:
    temporary = tempfile.TemporaryDirectory(prefix="petrolab_import_atomic_")
    try:
        tmp = temporary.name
        os.environ["PETROLAB_DATA_DIR"] = str(Path(tmp) / "data")
        from petrolab.db import list_datasets, create_project
        from petrolab.services import import_runtime, import_service

        workbook = io.BytesIO()
        with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
            pd.DataFrame({"Sample": ["PG-1"], "SiO2": [40.0]}).to_excel(writer, sheet_name="One", index=False)
            pd.DataFrame({"Sample": ["PG-2"], "SiO2": [41.0]}).to_excel(writer, sheet_name="Two", index=False)

        import_runtime.install()
        original = import_runtime._persist_one
        calls = 0

        def fail_after_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            result = original(*args, **kwargs)
            if calls == 2:
                raise RuntimeError("simulated disk failure after second sheet")
            return result

        import_runtime._persist_one = fail_after_second
        project_id = create_project("Atomic import", "")
        try:
            try:
                import_service.import_uploaded_sheets(
                    project_id=project_id, file_bytes=workbook.getvalue(), filename="two-sheets.xlsx",
                    sheet_names=["One", "Two"], mineral_key="generic", dataset_name="Two sheets", header_row=1,
                )
            except RuntimeError as exc:
                assert "simulated disk failure" in str(exc)
            else:
                raise AssertionError("forced failure must escape the import")
        finally:
            import_runtime._persist_one = original
        assert list_datasets(project_id) == [], "partial datasets survived a failed multi-sheet import"
        source_dir = Path(os.environ["PETROLAB_DATA_DIR"]) / "projects" / str(project_id)
        assert not list(source_dir.rglob("two-sheets.xlsx")) if source_dir.exists() else True
    finally:
        # SQLite can release its final handle asynchronously on Windows.  This
        # keeps the portable test focused on atomic import semantics, not an OS
        # timing artefact during temporary-directory removal.
        gc.collect()
        for attempt in range(20):
            try:
                temporary.cleanup()
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.1)
    print("atomic import tests: OK")


if __name__ == "__main__":
    main()
