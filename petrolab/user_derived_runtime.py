from __future__ import annotations


def install() -> None:
    """Attach user-derived fields to the established read paths.

    The wrapper is deliberately additive: raw analysis_rows and rock_compositions are
    never modified. Every existing plot/table caller that already consumes the derived
    loaders receives the calculated columns automatically.
    """
    from petrolab import derived
    from petrolab.repositories import rock_repository
    from petrolab.user_derived import (
        _apply_fields,
        list_dataset_fields,
        list_rock_project_fields,
    )

    def apply_safely(frame, fields):
        """Never let a persisted custom definition shadow a measured/system column."""
        source_columns = {str(column) for column in frame.columns}
        active = [field for field in fields if field.enabled and field.name not in source_columns]
        blocked = [field for field in fields if field.enabled and field.name in source_columns]

        seeded = frame.copy()
        seeded.attrs.update(frame.attrs)
        units = dict(seeded.attrs.get("derived_units", {}) or {})
        # Seed declared units so formula chains retain dimensional semantics while a
        # dependency is materialized earlier in the same calculation pass.
        for field in active:
            if field.unit:
                units.setdefault(field.name, field.unit)
        seeded.attrs["derived_units"] = units
        result = _apply_fields(seeded, active)
        if blocked:
            warnings = list(result.attrs.get("user_derived_warnings", []) or [])
            warnings.extend(
                f"{field.name}: сохранённая формула отключена при чтении, потому что это имя теперь занято исходной/системной колонкой."
                for field in blocked
            )
            result.attrs["user_derived_warnings"] = list(dict.fromkeys(warnings))
        return result

    current_dataset_loader = derived.load_dataset_with_derived
    if not getattr(current_dataset_loader, "_petrolab_user_derived", False):
        original_dataset_loader = current_dataset_loader

        def load_dataset_with_user_derived(dataset_id: int, include_meta: bool = True):
            frame = original_dataset_loader(int(dataset_id), include_meta=include_meta)
            fields = list_dataset_fields(int(dataset_id), include_disabled=False)
            return apply_safely(frame, fields)

        load_dataset_with_user_derived._petrolab_user_derived = True
        load_dataset_with_user_derived._petrolab_original = original_dataset_loader
        derived.load_dataset_with_derived = load_dataset_with_user_derived

    current_column_loader = derived.active_derived_columns
    if not getattr(current_column_loader, "_petrolab_user_derived", False):
        original_column_loader = current_column_loader

        def active_derived_columns_with_user_fields(dataset_ids):
            ids = {int(value) for value in dataset_ids}
            columns = set(original_column_loader(ids))
            for dataset_id in ids:
                columns.update(
                    field.name
                    for field in list_dataset_fields(dataset_id, include_disabled=False)
                )
            return columns

        active_derived_columns_with_user_fields._petrolab_user_derived = True
        active_derived_columns_with_user_fields._petrolab_original = original_column_loader
        derived.active_derived_columns = active_derived_columns_with_user_fields

    current_rock_loader = rock_repository.composition_wide
    if not getattr(current_rock_loader, "_petrolab_user_derived", False):
        original_rock_loader = current_rock_loader

        def composition_wide_with_user_derived(project_id: int | None = None):
            frame = original_rock_loader(project_id)
            if project_id is None:
                return frame
            fields = list_rock_project_fields(int(project_id), include_disabled=False)
            return apply_safely(frame, fields)

        composition_wide_with_user_derived._petrolab_user_derived = True
        composition_wide_with_user_derived._petrolab_original = original_rock_loader
        rock_repository.composition_wide = composition_wide_with_user_derived
