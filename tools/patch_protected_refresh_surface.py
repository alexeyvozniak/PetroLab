from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"target not found in {path}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


service = Path("petrolab/services/import_service.py")
replace_once(
    service,
    '''    detached_image_count: int = 0\n    positional_reused_count: int = 0\n''',
    '''    detached_image_count: int = 0\n    positional_reused_count: int = 0\n    positional_fallback_disabled: bool = False\n''',
)
replace_once(
    service,
    '''        detached_image_count=persistence.detached_image_count,\n        positional_reused_count=persistence.positional_reused_count,\n''',
    '''        detached_image_count=persistence.detached_image_count,\n        positional_reused_count=persistence.positional_reused_count,\n        positional_fallback_disabled=persistence.positional_fallback_disabled,\n''',
)

sources = Path("petrolab/ui/pages/sources.py")
replace_once(
    sources,
    '''                        if result.moved_rows_detected:\n                            st.info("Обнаружена перестановка/вставка строк: позиционный fallback был отключён для безопасности.")\n                        if result.positional_reused_count:\n''',
    '''                        if result.moved_rows_detected:\n                            st.info("Обнаружена перестановка/вставка строк: позиционный fallback был отключён для безопасности.")\n                        if result.positional_fallback_disabled:\n                            st.info(\n                                "Позиционное сопоставление по номеру строки отключено: в наборе уже есть "\n                                "изображения или история правок. ID сохраняются только при более надёжном совпадении."\n                            )\n                        if result.positional_reused_count:\n''',
)

import_test = Path("tests_import_service.py")
replace_once(
    import_test,
    '''assert positional_refresh.positional_reused_count == 1\nassert not positional_refresh.moved_rows_detected\n''',
    '''assert positional_refresh.positional_reused_count == 1\nassert not positional_refresh.positional_fallback_disabled\nassert not positional_refresh.moved_rows_detected\n''',
)

image_test = Path("tests_image_service.py")
replace_once(
    image_test,
    '''print("image service tests: OK")\n_tmp.cleanup()''',
    '''# A dataset without Sample/Grain/Point normally has only positional fallback after\n# a chemistry edit. Once an image is attached, that guess becomes unsafe and must be\n# disabled: the edited row receives a new ID and the old image link is detached.\nprotected_workbook = root / "protected_identity.xlsx"\nwith pd.ExcelWriter(protected_workbook, engine="openpyxl") as writer:\n    pd.DataFrame({"SiO2": [50.0, 51.0], "MgO": [10.0, 11.0]}).to_excel(\n        writer, sheet_name="Data", index=False\n    )\nprotected_dataset = import_linked_sheets(\n    project_id=project_id,\n    path=protected_workbook,\n    sheet_names=["Data"],\n    mineral_key="generic",\n    dataset_name="Protected identity",\n    header_row=1,\n).dataset_ids[0]\nprotected_before = load_dataset_dataframe(protected_dataset, include_meta=True)\nprotected_old_id = str(protected_before.iloc[0]["_analysis_id"])\nprotected_asset = create_image_assets(\n    project_id=project_id,\n    dataset_id=protected_dataset,\n    images=[ImagePayload("protected.png", image_bytes("PNG"))],\n    scope=ImageScope(SCOPE_ANALYSIS, analysis_ids=(protected_old_id,)),\n    kind="BSE",\n    title="protected",\n).asset_ids[0]\nprotected_path = Path(get_image_record(protected_asset)["stored_path"])\nwith pd.ExcelWriter(protected_workbook, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:\n    pd.DataFrame({"SiO2": [50.5, 51.0], "MgO": [10.0, 11.0]}).to_excel(\n        writer, sheet_name="Data", index=False\n    )\nprotected_refresh = refresh_dataset_from_source(protected_dataset)\nassert protected_refresh.positional_fallback_disabled\nassert protected_refresh.positional_reused_count == 0\nassert protected_refresh.reused_count == 1\nassert protected_refresh.new_count == 1\nassert protected_refresh.removed_count == 1\nassert protected_refresh.detached_image_count == 1\nprotected_after = load_dataset_dataframe(protected_dataset, include_meta=True)\nassert str(protected_after.iloc[0]["_analysis_id"]) != protected_old_id\nassert get_image_record(protected_asset)["analysis_ids"] == []\nassert protected_path.exists()\n\nprint("image service tests: OK")\n_tmp.cleanup()''',
)

print("protected refresh surface patch applied")
