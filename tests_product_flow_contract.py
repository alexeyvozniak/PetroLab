from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "petrolab" / "ui"
PAGES = UI / "pages"


def main() -> None:
    smart = (UI / "smart_plot_start.py").read_text(encoding="utf-8")
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
        "def seed_plot_handoff(",
        "def xy_recommendations(",
        "def sync_xy_recommendation_state(",
        "def restore_quick_plot_state(",
        "_petrolab_plot_scope_analysis_ids",
        "_petrolab_plot_scope_dataset_ids",
        'state.pop("_plots_show_advanced", None)',
        'state.pop("loaded_recipe", None)',
        "CURRENT_PLOT_SPEC_KEY",
    ]:
        assert marker in smart, marker
    assert 'pop("workflow_plot_analysis_ids"' not in plots
    assert "consume_plot_scope(" in plots
    assert '"Весь набор"' in plots

    # Every action that claims to open a scientific subset on XY must use the
    # canonical membership handoff rather than merely navigating to the page.
    assert "seed_import_plot_handoff" in intake
    assert "seed_selection_plot_handoff" in selection
    assert "seed_selection_plot_handoff" in statistics
    assert 'origin="Кластеры"' in statistics
    assert "cluster_dataset_ids" in statistics and "cluster_ids" in statistics
    assert "seed_plot_handoff" in search
    assert 'notice="В график переданы точные результаты поиска."' in search
    assert '"query": str(st.session_state.get("global_search_query")' in search

    # Direct route-state writes outside the canonical helper would reintroduce
    # subtly different scientific membership semantics between screens.
    for source in (intake, selection, statistics, search):
        assert 'st.session_state["workflow_plot_analysis_ids"]' not in source

    # Progressive XY is mandatory: no front-door mode split before seeing a graph.
    for obsolete in ["Быстрое построение", "Расширенный редактор", "Режим XY"]:
        assert obsolete not in plots, obsolete
    for marker in [
        "xy_recommendations(",
        "sync_xy_recommendation_state(",
        '"График"',
        '"Рекомендовано ·',
        '"Другой график ·',
        '"Свои оси"',
        '"⇄"',
        '"＋ Добавить диаграмму"',
        '"Настроить подробнее"',
        'st.expander("Экспорт и публикация"',
    ]:
        assert marker in plots, marker
    assert "_mark_custom_axes" in plots, "manual axes must opt out of recommendation ownership"
    assert "_swap_quick_axes" in plots, "axis swap must be one action"

    # Advanced is a deeper view of the same PlotSpec, not a second workflow.
    for marker in [
        "read_current_plot_spec", "restore_quick_plot_state", '"← К обычному графику"',
        '"_quick_resume_dataset_ids"', "initial_visible_series=resume_visible", "widget_token=series_token",
    ]:
        assert marker in plots, marker
    for marker in ["initial_visible_series", "widget_token", "editor_key"]:
        assert marker in plot_manager, marker

    print("IgPet/ioGAS exact scientific handoff + compact/advanced round-trip contract: OK")


if __name__ == "__main__":
    main()
