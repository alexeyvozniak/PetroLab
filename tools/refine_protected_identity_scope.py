from pathlib import Path

path = Path("petrolab/repositories/analysis_refresh_repository.py")
text = path.read_text(encoding="utf-8")
old = '''        has_images = con.execute(\n            "SELECT 1 FROM image_assets WHERE dataset_id=? LIMIT 1",\n            (int(dataset_id),),\n        ).fetchone() is not None\n        has_history = con.execute(\n            "SELECT 1 FROM change_log WHERE dataset_id=? LIMIT 1",\n            (int(dataset_id),),\n        ).fetchone() is not None\n        positional_fallback_disabled = has_images or has_history\n'''
new = '''        legacy_point_image = con.execute(\n            "SELECT 1 FROM image_assets WHERE dataset_id=? AND analysis_id IS NOT NULL LIMIT 1",\n            (int(dataset_id),),\n        ).fetchone() is not None\n        has_link_table = con.execute(\n            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='image_analysis_links'"\n        ).fetchone() is not None\n        linked_point_image = False\n        if has_link_table:\n            linked_point_image = con.execute(\n                """\n                SELECT 1\n                FROM image_analysis_links l\n                JOIN image_assets i ON i.id=l.asset_id\n                WHERE i.dataset_id=?\n                LIMIT 1\n                """,\n                (int(dataset_id),),\n            ).fetchone() is not None\n        has_point_images = legacy_point_image or linked_point_image\n        has_history = con.execute(\n            "SELECT 1 FROM change_log WHERE dataset_id=? AND analysis_id IS NOT NULL LIMIT 1",\n            (int(dataset_id),),\n        ).fetchone() is not None\n        positional_fallback_disabled = has_point_images or has_history\n'''
if old not in text:
    raise SystemExit("protected identity query block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("point-specific protected identity scope applied")
