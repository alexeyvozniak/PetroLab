from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


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
image_components = _read("petrolab/ui/image_components.py")
for marker in [
    "def analysis_id_labels(",
    "def render_multi_point_controls(",
    "limit = 5000",
    "valid_previous",
    'for column in ("Sample", "Grain", "Generation", "Point")',
    "semantic field-link",
]:
    assert marker in image_components, marker
assert not (ROOT / "petrolab" / "ui" / "image_page_policy.py").exists()
assert not (ROOT / "petrolab" / "ui" / "pages" / "images.py").exists()

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
    "missing column",
    "missing Fe column",
]:
    assert marker in formula_service, marker

from petrolab.services.formula_service import calculate_formula_safe
missing_mg = calculate_formula_safe(
    pd.DataFrame([{"SiO2": 40.0, "FeO": 10.0}]),
    "olivine",
    "ol_4o_fe2",
).data.iloc[0]
assert not bool(missing_mg["formula_valid"])
assert "missing column MgO" in str(missing_mg["formula_invalid_reason"])
for derived_name in ("Fo", "Fa"):
    if derived_name in missing_mg.index:
        assert pd.isna(missing_mg[derived_name])

missing_fe = calculate_formula_safe(
    pd.DataFrame([{"SiO2": 40.0, "MgO": 20.0}]),
    "olivine",
    "ol_4o_fe2",
).data.iloc[0]
assert not bool(missing_fe["formula_valid"])
assert "missing Fe column" in str(missing_fe["formula_invalid_reason"])

derived = _read("petrolab/derived.py")
for marker in ["formula_valid", "invalid_rows", "stale_rows", "current_rows", "_analysis_id"]:
    assert marker in derived, marker

# Redox/OH policies remain explicit rather than silently reinterpreting Fe or missing halogens (A-81/A-87/A-88/A-89/A-95/A-96).
formula_policy = _read("petrolab/minerals/formula_policy.py")
for marker in [
    "Метод Droop нельзя применять",
    "FeO-equivalent",
    "Henderson 32-O",
    "MinPlot-титанит",
    "F/Cl измерены не полностью",
    "Apatite X-anion field unresolved",
]:
    assert marker in formula_policy, marker

# Ternary preset availability and normalization are tied to actual rows/minerals (A-51/A-52/A-60).
ternary_controls = _read("petrolab/ui/ternary_controls.py")
for marker in [
    "available_ternary_presets(dataframe)",
    "preset.normalization",
    'st.session_state["ternary_normalization"]',
    "apply_preset_projection(dataframe, preset)",
]:
    assert marker in ternary_controls, marker

# Whole-rock concentrations with unknown units are a hard blocker, not a warning (A-38/A-86).
rock_runtime = _read("petrolab/rock_runtime.py")
for marker in [
    'descriptor.quantity_kind == "element_unknown_unit"',
    "содержит числовые концентрации элемента без единицы",
    "Для элемента",
    "укажите единицу концентрации",
]:
    assert marker in rock_runtime, marker
from petrolab.services.rock_service import canonicalize_rock_row
try:
    canonicalize_rock_row(pd.Series({"La": 12.0}))
except ValueError as exc:
    assert "единиц" in str(exc).lower()
else:
    raise AssertionError("Bare whole-rock element concentration without a unit must be blocked")
composition, units, _ = canonicalize_rock_row(pd.Series({"La ppm": 12.0}))
assert composition == {"La [µg/g]": 12.0}
assert units == {"La [µg/g]": "µg/g"}

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
assert "analysis_components" in analyses
assert not (ROOT / "petrolab" / "ui" / "pages" / "analyses.py").exists()

# Dataset selector identity and article-table labels must not silently collapse/round IDs (A-74/A-90).
dataframe_utils = _read("petrolab/dataframe_utils.py")
assert 'f\' · ID {int(dataset["id"])}\'' in dataframe_utils
article_tables = _read("petrolab/article_tables.py")
for marker in [
    "IDENTIFIER_COLUMNS",
    '"Sample"',
    '"Grain"',
    '"Point"',
    "if _is_identifier(column):",
    "Numeric-looking IDs",
    "ws.print_title_rows",
]:
    assert marker in article_tables, marker

# Destructive actions are explicit UI actions, not runtime monkeypatches (A-23 plus final audit UX closure).
app = _read("app.py")
destructive_actions = _read("petrolab/ui/destructive_actions.py")
plot_actions = _read("petrolab/ui/plot_actions.py")
rocks = _read("petrolab/ui/pages/rocks.py")
for marker in ["def confirm_then(", "def render_pending(", "_pending_destructive_"]:
    assert marker in destructive_actions, marker
for marker in [
    'confirm_then("plot_recipe"', 'confirm_then("style_profile"', 'confirm_then("work_group"',
    "loaded_recipe = None", 'pop("style_profile_select", None)', "render_plot_confirmations",
]:
    assert marker in plot_actions, marker
for marker in [
    'action_key = f"rock_links_{rock_id}"', "pending_key(action_key)",
    "confirm_then(action_key, link_target", 'confirm_then("rock_image"',
    "set_mineral_links as _set_mineral_links", "delete_rock_image as _delete_rock_image",
]:
    assert marker in rocks, marker
assert not (ROOT / "petrolab" / "ui" / "destructive_page_policy.py").exists()
assert not (ROOT / "petrolab" / "ui" / "pages" / "plots.py").exists()

# Plot/science safeguards now have direct owners; runtime page policies are forbidden
# (A-10/A-13/A-20/A-30/A-32/A-36/A-57/A-73/A-78/A-91/A-99).
assert not list((ROOT / "petrolab" / "ui").glob("*_page_policy.py"))
xy_components = _read("petrolab/ui/xy_components.py")
for marker in [
    "default_outlier_method",
    "Внутри групп",
    "hidden_saved",
    "sanitize_xy_rows",
    'key="petrolab_quick_interactive_plot"',
    'key="petrolab_advanced_interactive_plot"',
    "from petrolab.ui.plot_actions import clear_work_group",
]:
    assert marker in xy_components, marker
assert "from petrolab.ui.pages import plots" not in xy_components
advanced_xy = _read("petrolab/ui/pages/plots_advanced.py")
for marker in [
    "Сохранённый рецепт ссылается на наборы",
    "loaded_recipe = None",
    "render_outlier_controls",
    "render_advanced_interactive",
    "В график входит",
    "from petrolab.ui.plot_actions import (",
]:
    assert marker in advanced_xy, marker
assert "from petrolab.ui.pages import plots" not in advanced_xy
science = _read("petrolab/ui/pages/science_plots.py")
for marker in [
    "require_known_units=True",
    "def _mineral_filtered_presets(",
    "Grouped boxplot требует ровно один числовой параметр",
    "def _apply_pattern_group_styles(",
    "_PATTERN_YLABELS",
    "def _sync_science_axis_defaults(",
    "matches_preset",
    'key="hist_svg"',
    'key="box_svg"',
]:
    assert marker in science, marker
for old_bootstrap in [
    "install_science_page_policy", "install_image_page_policy", "install_plot_page_policy",
    "install_destructive_page_policy", "install_import_page_policy",
]:
    assert old_bootstrap not in app, old_bootstrap

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
