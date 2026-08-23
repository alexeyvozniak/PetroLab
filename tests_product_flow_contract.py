from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "petrolab" / "ui"
PAGES = UI / "pages"


def main() -> None:
    smart = (UI / "smart_plot_start.py").read_text(encoding="utf-8")
    work_context = (UI / "work_context.py").read_text(encoding="utf-8")
    plots = (PAGES / "plots_dashboard.py").read_text(encoding="utf-8")
    plot_manager = (UI / "plot_manager.py").read_text(encoding="utf-8")
    intake = (UI / "intake_workflow.py").read_text(encoding="utf-8")
    selection = (UI / "selection_components.py").read_text(encoding="utf-8")
    statistics = (PAGES / "statistics.py").read_text(encoding="utf-8")
    search = (PAGES / "global_search.py").read_text(encoding="utf-8")

    # Plot scope is graph-local, stable across Streamlit reruns and never a one-shot pop.
    for marker in [
        "def consume_plot_scope(",
        "def clear_exact_plot_scope(",
        "def reset_quick_plot_presentation(",
        "def seed_plot_handoff(",
        "def xy_recommendations(",
        "def sync_xy_recommendation_state(",
        "def restore_quick_plot_state(",
        "_petrolab_plot_scope_analysis_ids",
        "_petrolab_plot_scope_dataset_ids",
        "_petrolab_plot_scope_work_context_revision",
        "WORK_CONTEXT_REVISION_KEY",
        'state.pop("_plots_show_advanced", None)',
        'state.pop("loaded_recipe", None)',
        "CURRENT_PLOT_SPEC_KEY",
    ]:
        assert marker in smart, marker
    for marker in [
        'WORK_CONTEXT_REVISION_KEY = "_petrolab_work_context_revision"',
        "def _bump_context_revision_if_changed(",
        "_bump_context_revision_if_changed(context)",
        "_bump_context_revision_if_changed(None)",
    ]:
        assert marker in work_context, marker
    assert 'pop("workflow_plot_analysis_ids"' not in plots
    # Product Design keeps the two deliberate entry points discussed with the
    # researcher: a quick plot from the exact selection and a full editor.
    # The exact handoff may not be consumed on the first rerun.
    for marker in [
        'st.session_state.get("workflow_plot_analysis_ids", [])',
        'st.session_state.get("selection_analysis_ids", [])',
        "Быстрое построение", "Расширенный редактор", "render_quick_interactive",
        "render_advanced_xy_workspace",
    ]:
        assert marker in plots, marker

    # The dedicated selection layer remains the common source of working-group
    # actions; it is intentionally not duplicated inside XY rendering.
    assert "def render_selection_panel(" in selection
    assert "set_work_group" in selection
    assert "render_selection_panel" not in plot_manager

    print("IgPet/ioGAS exact scientific handoff + WorkContext + compact/advanced round-trip contract: OK")


if __name__ == "__main__":
    main()
