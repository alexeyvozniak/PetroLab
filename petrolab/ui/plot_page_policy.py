from __future__ import annotations

_GROUP_COLORS = (
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
)


def install() -> None:
    from petrolab.ui.pages import plots as page

    def style_map_from_df(dataframe):
        styles = {}
        for index, (_, row) in enumerate(dataframe.iterrows()):
            styles[str(row["Группа"])] = {
                "marker": row["Маркер"],
                "size_multiplier": float(row["Размер ×"]),
                "alpha": float(row["Alpha"]),
                "filled": bool(row["Заливка"]),
                "color": _GROUP_COLORS[index % len(_GROUP_COLORS)],
            }
        return styles

    page._style_map_from_df = style_map_from_df

    # The dashboard renders quick and advanced XY tabs in one Streamlit pass. The first
    # workspace is intentionally lightweight and gets its own widget key; the second keeps
    # the full legacy selection/grouping workflow unchanged.
    if not hasattr(page, "_petrolab_original_interactive_workspace"):
        page._petrolab_original_interactive_workspace = page._render_interactive_workspace
    original_workspace = page._petrolab_original_interactive_workspace
    page._petrolab_workspace_call_index = 0

    def dashboard_workspace(
        dataframe,
        project_id,
        x,
        y,
        group_col,
        x_label,
        y_label,
        title,
        log_x,
        log_y,
        style_map,
    ):
        call_index = int(page._petrolab_workspace_call_index)
        page._petrolab_workspace_call_index = call_index + 1
        if call_index > 0:
            return original_workspace(
                dataframe, project_id, x, y, group_col, x_label, y_label,
                title, log_x, log_y, style_map,
            )

        page.st.subheader("Интерактивный график")
        page.st.caption(
            "Кликните точку или выделите область рамкой/лассо. Для исключения точек, "
            "рабочих групп и подробной карточки используйте «Расширенный редактор»."
        )
        figure = page.build_interactive_scatter(
            dataframe,
            x,
            y,
            group_col,
            x_label=x_label,
            y_label=y_label,
            title=title,
            log_x=log_x,
            log_y=log_y,
            style_map=style_map,
        )
        event = page.st.plotly_chart(
            figure,
            width="stretch",
            theme=None,
            key="petrolab_quick_interactive_plot",
            on_select="rerun",
            selection_mode=("points", "box", "lasso"),
            config={"displaylogo": False, "scrollZoom": True},
        )
        selected_ids = page.selected_analysis_ids(event)
        if selected_ids:
            page.st.caption(f"Выбрано точек: {len(selected_ids)}.")

    page._render_interactive_workspace = dashboard_workspace

    # Keep all small page-level compatibility policies behind one UI bootstrap invoked by app.py.
    from petrolab.ui.image_page_policy import install as install_image_page_policy
    install_image_page_policy()
