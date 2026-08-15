from __future__ import annotations


def install() -> None:
    """Attach user-derived fields to the established read paths.

    The wrapper is deliberately additive: raw analysis_rows and rock_compositions are
    never modified. Every existing plot/table caller that already consumes the derived
    loaders receives the calculated columns automatically.
    """
    from petrolab import derived
    from petrolab.repositories import rock_repository
    from petrolab.user_derived import apply_dataset_fields, apply_rock_project_fields

    current_dataset_loader = derived.load_dataset_with_derived
    if not getattr(current_dataset_loader, "_petrolab_user_derived", False):
        original_dataset_loader = current_dataset_loader

        def load_dataset_with_user_derived(dataset_id: int, include_meta: bool = True):
            frame = original_dataset_loader(int(dataset_id), include_meta=include_meta)
            return apply_dataset_fields(frame, int(dataset_id))

        load_dataset_with_user_derived._petrolab_user_derived = True
        load_dataset_with_user_derived._petrolab_original = original_dataset_loader
        derived.load_dataset_with_derived = load_dataset_with_user_derived

    current_rock_loader = rock_repository.composition_wide
    if not getattr(current_rock_loader, "_petrolab_user_derived", False):
        original_rock_loader = current_rock_loader

        def composition_wide_with_user_derived(project_id: int | None = None):
            frame = original_rock_loader(project_id)
            if project_id is None:
                return frame
            return apply_rock_project_fields(frame, int(project_id))

        composition_wide_with_user_derived._petrolab_user_derived = True
        composition_wide_with_user_derived._petrolab_original = original_rock_loader
        rock_repository.composition_wide = composition_wide_with_user_derived
