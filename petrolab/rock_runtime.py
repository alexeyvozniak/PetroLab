from __future__ import annotations

import numpy as np
import pandas as pd

from petrolab.column_schema import describe_header


def install() -> None:
    from petrolab.repositories import rock_repository as repo
    from petrolab.services import rock_service as service

    def canonicalize_rock_row(row: pd.Series, excluded_columns: set[str] | None = None):
        excluded = excluded_columns or set()
        composition: dict[str, float] = {}
        units: dict[str, str] = {}
        source_columns: dict[str, str] = {}
        warnings: list[str] = []
        for column, raw_value in row.items():
            if str(column) in excluded:
                continue
            descriptor = describe_header(column)
            if descriptor.quantity_kind not in {"oxide", "trace_element", "element_concentration", "element_unknown_unit"}:
                continue
            numeric = pd.to_numeric(pd.Series([raw_value]), errors="coerce").iloc[0]
            if pd.isna(numeric):
                continue
            canonical = descriptor.canonical_name
            if canonical in composition:
                raise ValueError(
                    f"Колонки «{source_columns[canonical]}» и «{column}» обе обозначают {canonical}. "
                    "Выберите один источник компонента до импорта."
                )
            composition[canonical] = float(numeric) * float(descriptor.to_canonical_factor)
            units[canonical] = descriptor.canonical_unit or descriptor.source_unit
            source_columns[canonical] = str(column)
            if descriptor.warning:
                warnings.append(f"{column}: {descriptor.warning}")
        return composition, units, warnings

    def existing_composition(rock_id: int):
        frame = repo.get_composition(int(rock_id))
        if frame.empty:
            return {}, {}
        composition = {
            str(row["analyte"]): float(row["value"])
            for _, row in frame.iterrows() if pd.notna(row.get("value"))
        }
        units = {
            str(row["analyte"]): str(row.get("unit") or "")
            for _, row in frame.iterrows() if str(row.get("analyte") or "").strip()
        }
        return composition, units

    def import_rocks_wide(
        dataframe: pd.DataFrame, *, project_id: int, name_column: str,
        metadata_columns: dict[str, str] | None = None,
        chemistry_method: str = "", laboratory: str = "", source: str = "",
        on_conflict: str = "update",
    ):
        if name_column not in dataframe.columns:
            raise ValueError(f"Колонка названия породы «{name_column}» отсутствует")
        if on_conflict not in {"update", "skip", "error"}:
            raise ValueError("Неизвестная политика совпадающих названий пород")
        names = service._clean_import_names(dataframe, name_column)
        existing = {str(rock["name"]): rock for rock in repo.list_rocks(project_id)}
        conflicts = sorted(name for name in names if name in existing)
        if conflicts and on_conflict == "error":
            raise ValueError("Такие породы уже есть в проекте: " + ", ".join(conflicts[:20]))
        metadata_columns = metadata_columns or {}
        excluded = {name_column, *metadata_columns.values()}
        warnings: list[str] = []
        prepared: list[dict] = []
        for _, row in dataframe.iterrows():
            raw_name = row.get(name_column, "")
            if pd.isna(raw_name):
                continue
            name = str(raw_name).strip()
            if not name:
                continue
            metadata = {
                key: row.get(column, "") for key, column in metadata_columns.items()
                if column in dataframe.columns
            }
            metadata["chemistry_method"] = chemistry_method
            metadata["laboratory"] = laboratory
            composition, units, row_warnings = canonicalize_rock_row(row, excluded)
            warnings.extend(f"{name}: {message}" for message in row_warnings)
            if on_conflict == "update" and name in existing:
                old_composition, old_units = existing_composition(int(existing[name]["id"]))
                old_composition.update(composition)
                old_units.update(units)
                composition, units = old_composition, old_units
            prepared.append({"name": name, "metadata": metadata, "composition": composition, "units": units})
        created, updated, skipped = repo.apply_rock_import_batch(
            project_id, prepared, on_conflict=on_conflict,
            chemistry_method=chemistry_method, source=source,
        )
        return service.RockImportResult(created, updated, skipped, tuple(warnings))

    def canonical_manual(row: dict):
        analyte = repo._text(row.get("analyte")).strip()
        numeric = repo._nullable_float(row.get("value"))
        if not analyte or numeric is None:
            return None
        unit = repo._text(row.get("unit")).strip()
        direct = describe_header(analyte)
        base = direct.canonical_name.split(" [", 1)[0]
        descriptor = describe_header(f"{base} [{unit}]" if unit else analyte)
        if descriptor.quantity_kind in {"oxide", "trace_element", "element_concentration"}:
            analyte = descriptor.canonical_name
            numeric *= float(descriptor.to_canonical_factor)
            unit = descriptor.canonical_unit or descriptor.source_unit
        return {
            "analyte": analyte, "value": numeric, "unit": unit,
            "method": repo._text(row.get("method")), "source": repo._text(row.get("source")),
        }

    def upsert_composition_values(rock_id: int, rows):
        prepared = []
        seen: set[str] = set()
        for raw in rows:
            row = canonical_manual(dict(raw))
            if row is None:
                continue
            if row["analyte"] in seen:
                raise ValueError(f"Компонент {row['analyte']} указан несколько раз")
            seen.add(row["analyte"])
            prepared.append(row)
        now = repo._utcnow()
        with repo.rock_connection() as con:
            con.execute("DELETE FROM rock_compositions WHERE rock_id=?", (int(rock_id),))
            con.executemany(
                "INSERT INTO rock_compositions(rock_id, analyte, value, unit, method, source, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(int(rock_id), row["analyte"], row["value"], row["unit"], row["method"], row["source"], now) for row in prepared],
            )

    def set_mineral_links(rock_id: int, dataset_ids):
        ids = sorted({int(value) for value in dataset_ids})
        with repo.rock_connection() as con:
            rock = con.execute("SELECT project_id FROM rock_samples WHERE id=?", (int(rock_id),)).fetchone()
            if rock is None:
                raise ValueError("Порода больше не существует")
            project_id = int(rock["project_id"])
            if ids:
                marks = ",".join("?" for _ in ids)
                rows = con.execute(f"SELECT id, project_id FROM datasets WHERE id IN ({marks})", ids).fetchall()
                found = {int(row["id"]): int(row["project_id"]) for row in rows}
                if any(dataset_id not in found for dataset_id in ids):
                    raise ValueError("Часть mineral datasets больше не существует")
                if any(found[dataset_id] != project_id for dataset_id in ids):
                    raise ValueError("Нельзя связать породу с dataset другого проекта")
            con.execute("DELETE FROM rock_mineral_links WHERE rock_id=?", (int(rock_id),))
            now = repo._utcnow()
            con.executemany(
                "INSERT INTO rock_mineral_links(rock_id, dataset_id, relation, notes, created_at) VALUES (?, ?, ?, ?, ?)",
                [(int(rock_id), dataset_id, "same_sample", "", now) for dataset_id in ids],
            )

    def total_fe_as_feo(composition: dict[str, float]):
        feot = service._finite_value(composition, "FeOt")
        if feot is not None:
            return feot
        fe2o3t = service._finite_value(composition, "Fe2O3t")
        if fe2o3t is not None:
            return fe2o3t * service.FE2O3_TO_FEO_EQUIVALENT
        feo = service._finite_value(composition, "FeO")
        if feo is None:
            return None
        fe2o3 = service._finite_value(composition, "Fe2O3")
        return feo + (fe2o3 or 0.0) * service.FE2O3_TO_FEO_EQUIVALENT

    service.canonicalize_rock_row = canonicalize_rock_row
    service.import_rocks_wide = import_rocks_wide
    service._total_fe_as_feo = total_fe_as_feo
    repo.upsert_composition_values = upsert_composition_values
    repo.set_mineral_links = set_mineral_links
