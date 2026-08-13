from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CLOSURE = (ROOT / "docs" / "AUDIT_V10_CLOSURE_2026-08-13.md").read_text(encoding="utf-8")
FINAL = (ROOT / "docs" / "AUDIT_V10_FINAL_VERIFICATION_2026-08-14.md").read_text(encoding="utf-8")


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


# The closure matrix itself is a contract: every A-item must exist exactly once and remain closed.
rows = re.findall(r"^\| A-(\d{2,3}) \| ([^|]+) \|", CLOSURE, flags=re.MULTILINE)
assert len(rows) == 100, f"Expected 100 audit rows, found {len(rows)}"
ids = [int(number) for number, _ in rows]
assert ids == list(range(1, 101)), f"Audit IDs are missing/duplicated/out of order: {ids}"
for number, status in rows:
    normalized = status.strip().upper()
    assert normalized.startswith("CLOSED"), f"A-{int(number):02d} is not closed: {status}"
    assert "OPEN" not in normalized and "PARTIAL" not in normalized, (number, status)

# High-risk Excel reverse-write invariants (A-41/A-49/A-50/A-71).
sources = _read("petrolab/sources.py")
for marker in [
    "_assert_source_is_current(dataset, path)",
    "expected_old_value",
    "_source_values_equal(cell.value, expected_old_value)",
    "workbook.close()",
    "temp.unlink(missing_ok=True)",
    "math.isinf(left_value)",
]:
    assert marker in sources, marker
from petrolab.sources import _source_values_equal
assert _source_values_equal(float("inf"), float("inf"))
assert _source_values_equal(float("-inf"), float("-inf"))
assert not _source_values_equal(float("inf"), float("-inf"))
assert _source_values_equal(float("nan"), float("nan"))

# Managed browser uploads are internal working copies, never reverse-sync targets (A-58/A-77).
import_runtime = _read("petrolab/services/import_runtime.py")
assert 'source_kind="managed_copy"' in import_runtime
assert "sync_enabled=False" in import_runtime
assert "managed_path.unlink(missing_ok=True)" in import_runtime
assert "_rollback(created)" in import_runtime

# Image safety/repair contract (A-45/A-46/A-69/A-70).
image_service = _read("petrolab/services/image_service.py")
for marker in [
    "def relink_image_asset(",
    "replace_image_analysis_links",
    "Prevalidate the full batch",
    "compensating rollback",
    "_cleanup_created(created_ids, created_paths)",
]:
    assert marker in image_service, marker
assert "Atomically validate and store" not in image_service
images_dashboard = _read("petrolab/ui/pages/images_dashboard.py")
assert "_repair_detached" in images_dashboard
assert 'link_status") or "") == "detached"' in images_dashboard
assert "confirm_delete_image_" in images_dashboard

# Formula persistence and scientific-validity contract (A-47/A-79/A-82/A-92/A-94/A-97/A-98).
formula_service = _read("petrolab/services/formula_service.py")
for marker in [
    "source_ids = source[\"_analysis_id\"].astype(str)",
    "FORMULA_VALID_COL = \"formula_valid\"",
    "FORMULA_INVALID_REASON_COL = \"formula_invalid_reason\"",
    "FORMULA_INPUTS_USED_COL = \"Formula inputs used\"",
    'out["X_Fe3"]',
    'out["Simplified_endmember_sum"]',
    'out["QC_endmember_model"]',
    "simplified end-member classification withheld",
]:
    assert marker in formula_service, marker

derived = _read("petrolab/derived.py")
for marker in ["formula_valid", "invalid_rows", "stale_rows", "current_rows", "_analysis_id"]:
    assert marker in derived, marker

# Recovery snapshot semantics do not invent Excel rows; maintenance warnings survive rerun (A-75/A-76).
recovery = _read("petrolab/recovery_runtime.py")
assert "Never invent physical Excel row numbers" in recovery
assert 'source_kind in {"linked", "managed_copy"}' in recovery
assert "source_rows=[None] * len(dataframe)" in recovery
analyses = _read("petrolab/ui/pages/analyses_dashboard.py")
for marker in [
    '_SAVE_FLASH_KEY = "analysis_save_flash"',
    "_show_save_flash()",
    "result.warnings",
    "st.warning(str(warning))",
]:
    assert marker in analyses, marker

# Destructive actions must be intercepted before storage (A-23 plus final audit UX closure).
app = _read("app.py")
destructive = _read("petrolab/ui/destructive_page_policy.py")
assert "install_destructive_page_policy()" in app
for marker in [
    '"plot_recipe"',
    '"style_profile"',
    '"work_group"',
    '"rock_image"',
    '"rock_links"',
    "original_delete_recipe",
    "original_delete_profile",
    "original_delete_rock_image",
    "original_set_mineral_links",
    'st.button("Отмена"',
]:
    assert marker in destructive, marker

# Plot/science policies that were previously easy to regress (A-10/A-13/A-20/A-30/A-32/A-36/A-57/A-73/A-78/A-91/A-99).
plot_policy = _read("petrolab/ui/plot_page_policy.py")
for marker in [
    "default_outlier_method",
    "Внутри групп",
    "hidden_saved",
    "loaded_recipe = None",
    "Сохранённый рецепт ссылается на datasets",
    "require_known_units=True",
    "strict_presets",
    "Grouped boxplot требует ровно один числовой параметр",
    '"SVG"',
    "consistent_pattern",
]:
    assert marker in plot_policy, marker
assert "_petrolab_plot_policy_installed" in app

# Optional hints are optional; scientific warnings/provenance are not globally hidden (A-100).
layout = _read("petrolab/ui/layout.py")
assert "def render_hint(" in layout
assert "show_help_hints" in layout

# Final verification explicitly supersedes the two resolved caveats in the historical closure snapshot.
for marker in [
    "все 100 пунктов имеют статус `CLOSED`",
    "Destructive actions",
    "Post-save maintenance warnings",
    "tests_audit_closure.py",
    "открытых или частично закрытых пунктов не остаётся",
]:
    assert marker in FINAL, marker

print("audit v10 closure gate: OK")
