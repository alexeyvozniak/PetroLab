from __future__ import annotations


def install() -> None:
    """Install the remaining science-plot compatibility guards once per process."""
    from petrolab.ui.pages import science_plots as science

    if getattr(science, "_petrolab_science_policy_installed", False):
        return

    def strict_presets(dataframe):
        presets = {
            key: preset
            for key, preset in science.SCIENTIFIC_PLOT_PRESETS.items()
            if preset.plot_type == "xy"
        }
        if "Минерал" not in dataframe.columns:
            return presets
        present = set(dataframe["Минерал"].dropna().astype(str))
        return {
            key: preset
            for key, preset in presets.items()
            if preset.mineral_key is None
            or science.MINERAL_PRESET_ALIASES.get(
                str(preset.mineral_key), str(preset.mineral_key)
            ) in present
        }

    science._mineral_filtered_presets = strict_presets

    original_available = science.available_elements
    science.available_elements = (
        lambda dataframe, preferred, *, require_known_units=False, reference=None:
        original_available(
            dataframe,
            preferred,
            require_known_units=True,
            reference=reference,
        )
    )

    original_pattern = science.build_pattern_figure
    ylabel_by_ref = {
        "Без нормировки": "Concentration [µg/g equivalent]",
        "CI-хондрит · McDonough & Sun (1995)": "Sample / CI chondrite",
        "Primitive mantle · Sun & McDonough (1989)": "Sample / primitive mantle",
    }
    line_styles = ("-", "--", ":", "-.")

    def consistent_pattern(pattern, *, labels=None, group=None, **kwargs):
        reference = science.st.session_state.get("pattern_ref")
        if reference in ylabel_by_ref:
            kwargs["ylabel"] = ylabel_by_ref[reference]
        figure = original_pattern(pattern, labels=labels, group=group, **kwargs)
        if group is None or pattern.data.empty or not figure.axes:
            return figure
        groups = (
            group.reindex(pattern.data.index)
            .astype("string")
            .fillna("Без группы")
            .replace("", "Без группы")
        )
        names = list(dict.fromkeys(groups.tolist()))
        colors = science.plt.rcParams["axes.prop_cycle"].by_key().get("color", ["black"])
        styles = {
            name: (colors[index % len(colors)], line_styles[index % len(line_styles)])
            for index, name in enumerate(names)
        }
        for line, name in zip(figure.axes[0].lines, groups.tolist()):
            color, linestyle = styles[name]
            if kwargs.get("monochrome", False):
                line.set_color("black")
                line.set_linestyle(linestyle)
            else:
                line.set_color(color)
        return figure

    science.build_pattern_figure = consistent_pattern

    original_xy = science._render_scientific_xy

    def strict_xy(dataframe):
        preset_id = science.st.session_state.get("science_xy_preset")
        preset = strict_presets(dataframe).get(preset_id)
        if preset is None:
            return original_xy(dataframe)
        x = science.st.session_state.get("science_xy_x")
        y = science.st.session_state.get("science_xy_y")
        if x is None or y is None:
            return original_xy(dataframe)
        numeric = science.numeric_candidates(dataframe)
        matches = (
            x in science._axis_candidates(dataframe, preset.x, numeric)
            and y in science._axis_candidates(dataframe, preset.y, numeric)
        )
        if matches:
            return original_xy(dataframe)

        science.st.session_state["science_xy_title"] = ""
        science.st.session_state["science_xy_xlabel"] = str(x)
        science.st.session_state["science_xy_ylabel"] = str(y)
        original_caption = science.st.caption
        original_info = science.st.info
        original_builder = science.build_scientific_xy_figure

        def caption(text, *args, **kwargs):
            value = str(text)
            if value.startswith("Источник схемы:") or value.startswith("Overlay:"):
                return None
            return original_caption(text, *args, **kwargs)

        def builder(*args, **kwargs):
            kwargs["overlay_id"] = None
            return original_builder(*args, **kwargs)

        science.st.caption = caption
        science.st.info = lambda *args, **kwargs: None
        science.build_scientific_xy_figure = builder
        try:
            result = original_xy(dataframe)
        finally:
            science.st.caption = original_caption
            science.st.info = original_info
            science.build_scientific_xy_figure = original_builder
        original_caption(
            "Пользовательские оси: литературное название, source citation и overlay preset'а отключены."
        )
        return result

    science._render_scientific_xy = strict_xy

    original_box_builder = science.build_boxplot_figure

    def explicit_box_builder(dataframe, value_columns, *, group_column=None, **kwargs):
        if group_column and len(value_columns) > 1:
            science.st.warning(
                "Grouped boxplot требует ровно один числовой параметр. "
                "График не построен: выберите один Y или отключите группировку."
            )
            figure, axis = science.plt.subplots(
                figsize=kwargs.get("figure_size", (8.0, 5.0))
            )
            axis.text(
                0.5,
                0.5,
                "Выберите один Y для grouped boxplot",
                ha="center",
                va="center",
                transform=axis.transAxes,
            )
            axis.set_axis_off()
            return figure
        return original_box_builder(
            dataframe,
            value_columns,
            group_column=group_column,
            **kwargs,
        )

    science.build_boxplot_figure = explicit_box_builder

    def add_svg_export(renderer, *, prefix: str, filename: str):
        def wrapped(dataframe):
            original_close = science.plt.close

            def close(figure=None):
                if figure is not None:
                    dpi = int(science.st.session_state.get(f"{prefix}_dpi", 600))
                    science.st.download_button(
                        "SVG",
                        science.figure_bytes(figure, "svg", dpi),
                        file_name=f"{filename}.svg",
                        mime="image/svg+xml",
                        key=f"{prefix}_svg",
                    )
                return original_close(figure)

            science.plt.close = close
            try:
                return renderer(dataframe)
            finally:
                science.plt.close = original_close

        return wrapped

    science._render_histogram = add_svg_export(
        science._render_histogram,
        prefix="hist",
        filename="histogram",
    )
    science._render_boxplot = add_svg_export(
        science._render_boxplot,
        prefix="box",
        filename="boxplot",
    )
    science._petrolab_science_policy_installed = True
