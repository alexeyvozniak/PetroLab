from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "petrolab" / "ui"
PAGES = UI / "pages"


def main() -> None:
    smart = (UI / "smart_plot_start.py").read_text(encoding="utf-8")
    plots = (PAGES / "plots_dashboard.py").read_text(encoding="utf-8")
    intake = (UI / "intake_workflow.py").read_text(encoding="utf-8")
    selection = (UI / "selection_components.py").read_text(encoding="utf-8")
    statistics = (PAGES / "statistics.py").read_text(encoding="utf-8")
    search = (PAGES / "global_search.py").read_text(encoding="utf-8")

    # Plot scope is graph-local, stable across Streamlit reruns and never a one-shot pop.
    for marker in [
        "def consume_plot_scope(",
        "def clear_exact_plot_scope(",
        "_petrolab_plot_scope_analysis_ids",
        "_petrolab_plot_scope_dataset_ids",
    ]:
        assert marker in smart, marker
    assert 'pop("workflow_plot_analysis_ids"' not in plots
    assert "consume_plot_scope(" in plots
    assert '"Весь набор"' in plots

    # Every action that claims to open an exact scientific subset on XY must seed
    # both dataset and immutable analysis membership rather than only navigate.
    assert "seed_import_plot_handoff" in intake
    assert "seed_selection_plot_handoff" in selection
    assert "seed_selection_plot_handoff" in statistics
    assert 'origin="Кластеры"' in statistics
    assert "cluster_dataset_ids" in statistics and "cluster_ids" in statistics

    # Search already carries exact IDs; keep this until it is moved to the same helper.
    for marker in [
        'st.session_state["workflow_plot_dataset_ids"] = dataset_ids',
        'st.session_state["workflow_plot_analysis_ids"] = analysis_ids',
        'st.session_state["workflow_plot_context"] = context',
    ]:
        assert marker in search, marker

    # Progressive XY is mandatory: no front-door mode split before seeing a graph.
    for obsolete in ["Быстрое построение", "Расширенный редактор", "Режим XY"]:
        assert obsolete not in plots, obsolete
    assert '"＋ Добавить диаграмму"' in plots
    assert '"Настроить подробнее"' in plots

    print("IgPet/ioGAS exact scientific handoff contract: OK")


if __name__ == "__main__":
    main()
