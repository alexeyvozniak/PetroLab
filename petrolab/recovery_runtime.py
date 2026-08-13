from __future__ import annotations

from pathlib import Path

import pandas as pd


def install() -> None:
    from petrolab import db

    def ensure_dataset_rows(dataset_id: int) -> None:
        with db.connect() as con:
            count = int(con.execute(
                "SELECT COUNT(*) FROM analysis_rows WHERE dataset_id=?",
                (int(dataset_id),),
            ).fetchone()[0])
        if count:
            return

        dataset = db.get_dataset(int(dataset_id))
        source_path = Path(str(dataset.get("source_path") or ""))
        source_kind = str(dataset.get("source_kind") or "")

        # Never invent physical Excel row numbers from a CSV snapshot. If the actual
        # source still exists, recover from it so blank separator rows and sheet positions
        # are reconstructed by the normal import/refresh path.
        if source_path and str(source_path) not in {"", "."} and source_path.exists():
            from petrolab.services.import_service import refresh_dataset_from_source

            refresh_dataset_from_source(int(dataset_id))
            return

        # A linked/managed source that vanished is intentionally left unrecovered rather
        # than assigning guessed source_row values that could later be written back to the
        # wrong Excel row. Source status UI will expose the missing file.
        if source_kind in {"linked", "managed_copy"}:
            return

        csv_path = Path(str(dataset.get("csv_path") or ""))
        if not csv_path.exists():
            return
        dataframe = pd.read_csv(csv_path)
        db.replace_dataset_rows(
            int(dataset_id), dataframe, source_rows=[None] * len(dataframe)
        )

    db.ensure_dataset_rows = ensure_dataset_rows
