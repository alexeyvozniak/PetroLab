from __future__ import annotations

import numpy as np
import pandas as pd

from petrolab.column_schema import describe_header


def install() -> None:
    from petrolab.repositories import rock_repository as repo
    from petrolab.services import rock_service as service

    def finite_nullable_float(value):
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(value, str) and not value.strip():
            return None
        numeric = float(value)
        if not np.isfinite(numeric):
            raise ValueError("Числовое значение породы должно быть конечным")
        return numeric

    def combine_metadata_values(old_value, new_value) -> str:
        """Accumulate summary metadata without replacing earlier provenance."""
        values: list[str] = []
        for raw in (old_value, new_value):
            text = str(raw or "").strip()
            if not text:
                continue
            for part in text.split(" | "):
                clean = part.strip()
                if clean and clean not in values:
                    values.append(clean)
        return " | ".join(values)

    def has_import_metadata_value(value) -> bool:
        """Blank bulk-import metadata means 'not supplied', never 'erase existing'."""
        if value is None:
            return False
        try:
            if pd.isna(value):
                return False
        except (TypeError, ValueError):
            pass
        if isinstance(value, str) and not value.strip():
            return False
        return True

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
            numeric = float(numeric)
            if not np.isfinite(numeric):
                raise ValueError(f"Колонка «{column}» содержит бесконечное/некорректное числовое значение")
            if descriptor.quantity_kind == "element_unknown_unit":
                raise ValueError(
                    f"Колонка «{column}» содержит числовые концентрации элемента без единицы. "
                    "Укажите ppm/µg/g, ppb/ng/g, ppt/pg/g или wt% в заголовке до импорта."
                )
            canonical = descriptor.canonical_name
            if canonical in composition:
                raise ValueError(
                    f"Колонки «{source_columns[canonical]}» и «{column}» обе обозначают {canonical}. "
                    "Выберите один источник компонента до импорта."
                )
            composition[canonical] = numeric * float(descriptor.to_canonical_factor)
            units[canonical] = descriptor.canonical_unit or descriptor.source_unit
            source_columns[canonical] = str(column)
            if descriptor.warning:
                warnings.append(f"{column}: {descriptor.warning}")
        return composition, units, warnings

    def existing_composition(rock_id: int):
        frame = repo.get_composition(int(rock_id))
        if frame.empty:
            return {}, {}, {}, {}
        composition = {
            str(row["analyte"]): float(row["value"])
            for _, row in frame.iterrows()
            if pd.notna(row.get("value")) and np.isfinite(float(row["value"]))
        }
        units = {
            str(row["analyte"]): str(row.get("unit") or "")
            for _, row in frame.iterrows() if str(row.get("analyte") or "").strip()
        }
        methods = {
            str(row["analyte"]): str(row.get("method") or "")
            for _, row in frame.iterrows() if str(row.get("analyte") or "").strip()
        }
        sources = {
            str(row["analyte"]): str(row.get("source") or "")
            for _, row in frame.iterrows() if str(row.get("analyte") or "").strip()
        }
        return composition, units, methods, sources

    def apply_rock_import_batch(
        project_id: int,
        prepared_rows,
        *,
        on_conflict: str,
        chemistry_method: str = "",
        source: str = "",
    ):
        """Atomic import preserving provenance for untouched analytes on partial update."""
        if on_conflict not in {"update", "skip", "error"}:
            raise ValueError("Неизвестная политика совпадающих названий пород")
        rows = list(prepared_rows)
        created: list[int] = []
        updated: list[int] = []
        skipped: list[str] = []
        with repo.rock_connection() as con:
            existing_rows = con.execute(
                "SELECT id, name FROM rock_samples WHERE project_id=?", (int(project_id),)
            ).fetchall()
            existing = {str(row["name"]): int(row["id"]) for row in existing_rows}
            for row in rows:
                name = str(row["name"]).strip()
                if not name:
                    raise ValueError("Название породы не может быть пустым")
                metadata = dict(row.get("metadata") or {})
                composition = dict(row.get("composition") or {})
                units = dict(row.get("units") or {})
                methods = dict(row.get("methods") or {})
                sources = dict(row.get("sources") or {})
                rock_id = existing.get(name)
                if rock_id is not None:
                    if on_conflict == "error":
                        raise ValueError(f"Порода «{name}» уже существует")
                    if on_conflict == "skip":
                        skipped.append(name)
                        continue
                    repo._update_rock_in_connection(con, rock_id, metadata)
                    updated.append(rock_id)
                else:
                    rock_id = repo._create_rock_in_connection(con, int(project_id), name, metadata)
                    existing[name] = rock_id
                    created.append(rock_id)
                con.execute("DELETE FROM rock_compositions WHERE rock_id=?", (int(rock_id),))
                now = repo._utcnow()
                for analyte, value in composition.items():
                    numeric = repo._nullable_float(value)
                    if numeric is None:
                        continue
                    con.execute(
                        "INSERT INTO rock_compositions(rock_id, analyte, value, unit, method, source, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            int(rock_id), str(analyte), numeric, str(units.get(str(analyte), "")),
                            str(methods.get(str(analyte), chemistry_method)),
                            str(sources.get(str(analyte), source)), now,
                        ),
                    )
        return tuple(created), tuple(updated), tuple(skipped)

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
                key: row.get(column)
                for key, column in metadata_columns.items()
                if column in dataframe.columns and has_import_metadata_value(row.get(column))
            }
            metadata["chemistry_method"] = chemistry_method
            metadata["laboratory"] = laboratory
            composition, units, row_warnings = canonicalize_rock_row(row, excluded)
            warnings.extend(f"{name}: {message}" for message in row_warnings)
            new_analytes = set(composition)
            methods = {analyte: chemistry_method for analyte in composition}
            sources = {analyte: source for analyte in composition}
            if on_conflict == "update" and name in existing:
                current_rock = existing[name]
                metadata["chemistry_method"] = combine_metadata_values(
                    current_rock.get("chemistry_method"), chemistry_method
                )
                metadata["laboratory"] = combine_metadata_values(
                    current_rock.get("laboratory"), laboratory
                )
                old_composition, old_units, old_methods, old_sources = existing_composition(int(current_rock["id"]))
                old_composition.update(composition)
                old_units.update(units)
                for analyte in new_analytes:
                    old_methods[analyte] = chemistry_method
                    old_sources[analyte] = source
                composition, units = old_composition, old_units
                methods, sources = old_methods, old_sources
            prepared.append({
                "name": name,
                "metadata": metadata,
                "composition": composition,
                "units": units,
                "methods": methods,
                "sources": sources,
            })
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
        if direct.quantity_kind == "element_unknown_unit" and not unit:
            raise ValueError(
                f"Для элемента {direct.canonical_name} укажите единицу концентрации "
                "(например, µg/g, ppb/ng/g, ppt/pg/g или wt%)."
            )
        base = direct.canonical_name.split(" [", 1)[0]
        descriptor = describe_header(f"{base} [{unit}]" if unit else analyte)
        if descriptor.quantity_kind in {"oxide", "trace_element", "element_concentration"}:
            analyte = descriptor.canonical_name
            numeric *= float(descriptor.to_canonical_factor)
            unit = descriptor.canonical_unit or descriptor.source_unit
        elif descriptor.quantity_kind == "element_unknown_unit":
            raise ValueError(f"Для элемента {base} не удалось определить единицу концентрации")
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
                rows = con.execute(
                    f"""
                    SELECT d.id, CASE WHEN l.dataset_id IS NULL THEN 0 ELSE 1 END AS accessible
                    FROM datasets d
                    LEFT JOIN project_dataset_links l
                      ON l.dataset_id=d.id AND l.project_id=?
                    WHERE d.id IN ({marks})
                    """,
                    (project_id, *ids),
                ).fetchall()
                found = {int(row["id"]): bool(row["accessible"]) for row in rows}
                if any(dataset_id not in found for dataset_id in ids):
                    raise ValueError("Часть mineral datasets больше не существует")
                inaccessible = [dataset_id for dataset_id in ids if not found[dataset_id]]
                if inaccessible:
                    raise ValueError(
                        "Нельзя связать породу с dataset, который не подключён к текущему проекту: "
                        + ", ".join(map(str, inaccessible[:8]))
                    )
            con.execute("DELETE FROM rock_mineral_links WHERE rock_id=?", (int(rock_id),))
            now = repo._utcnow()
            con.executemany(
                "INSERT INTO rock_mineral_links(rock_id, dataset_id, relationship, notes, created_at) VALUES (?, ?, ?, ?, ?)",
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

    repo._nullable_float = finite_nullable_float
    service.canonicalize_rock_row = canonicalize_rock_row
    service.import_rocks_wide = import_rocks_wide
    service._total_fe_as_feo = total_fe_as_feo
    repo.apply_rock_import_batch = apply_rock_import_batch
    repo.upsert_composition_values = upsert_composition_values
    repo.set_mineral_links = set_mineral_links
