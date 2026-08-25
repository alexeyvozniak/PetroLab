from __future__ import annotations

"""Reference-led linked plotting workspace.

The layout follows the approved PetroLab Product Design reference: one compact
selection toolbar, a left preselection tray, a clean grid of linked scientific
plots and a right encoding panel. Selection remains transient and non-destructive.
"""

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from petrolab.extended_plotting import NORMALIZATION_REFERENCES, REE_ORDER, build_pattern_figure, prepare_pattern
from petrolab.interactive_plotting import selected_analysis_ids
from petrolab.io_utils import numeric_candidates
from petrolab.selections import save_selection
from petrolab.ternary_data import prepare_ternary
from petrolab.ternary_plotting import build_interactive_ternary
from petrolab.ui.data_scope import render_analysis_scope
from petrolab.ui.layout import render_page_header
from petrolab.ui.selection_context import clear_selection, read_selection, set_selection


_COLORS = ("#0f7f82", "#2d63c8", "#e57a10", "#7d3bb8", "#c54852", "#64748b")
_SYMBOLS = ("circle", "square", "triangle-up", "diamond", "cross", "hexagon")


def _categorical_columns(frame: pd.DataFrame) -> list[str]:
    preferred = ["Generation", "Положение", "Textural zone", "Method", "Метод", "Минерал", "Mineral", "Источник", "Набор"]
    return [column for column in preferred if column in frame.columns and 1 < frame[column].nunique(dropna=True) <= 32]


def _default_numeric(numeric: list[str], *preferred: str, fallback: int = 0) -> str:
    lowered = {str(value).casefold(): value for value in numeric}
    for name in preferred:
        if name in numeric:
            return name
        match = lowered.get(name.casefold())
        if match is not None:
            return match
    return numeric[min(max(fallback, 0), len(numeric) - 1)] if numeric else ""


def _point_label(row: pd.Series) -> str:
    parts: list[str] = []
    for key in ("Sample", "Образец", "Point", "Точка", "Grain", "Зерно"):
        value = row.get(key)
        if value is not None and str(value).strip() and str(value).lower() != "nan":
            parts.append(str(value).strip())
    return " · ".join(parts[:3]) or str(row.get("_analysis_id") or "")[:10]


def _scatter(
    frame: pd.DataFrame,
    x: str,
    y: str,
    *,
    title: str,
    color_by: str | None,
    symbol_by: str | None,
    active: set[str],
    dragmode: str,
) -> go.Figure:
    work = frame.copy()
    work[x] = pd.to_numeric(work[x], errors="coerce")
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna(subset=[x, y])
    color_values = work[color_by].fillna("Без значения").astype(str) if color_by else pd.Series("Все", index=work.index)
    symbol_values = work[symbol_by].fillna("Без значения").astype(str) if symbol_by else pd.Series("Все", index=work.index)
    color_map = {value: _COLORS[index % len(_COLORS)] for index, value in enumerate(color_values.drop_duplicates())}
    symbol_map = {value: _SYMBOLS[index % len(_SYMBOLS)] for index, value in enumerate(symbol_values.drop_duplicates())}

    figure = go.Figure()
    for color_value in color_values.drop_duplicates():
        for symbol_value in symbol_values.drop_duplicates():
            subset = work[(color_values == color_value) & (symbol_values == symbol_value)]
            if subset.empty:
                continue
            custom = [[str(row["_analysis_id"]), _point_label(row)] for _, row in subset.iterrows()]
            selected = [index for index, item in enumerate(custom) if str(item[0]) in active]
            figure.add_trace(
                go.Scattergl(
                    x=subset[x],
                    y=subset[y],
                    mode="markers",
                    customdata=custom,
                    name=str(color_value) if not symbol_by else f"{color_value} · {symbol_value}",
                    selectedpoints=selected if active else None,
                    marker={
                        "color": color_map[str(color_value)],
                        "symbol": symbol_map[str(symbol_value)],
                        "size": 8,
                        "opacity": 0.86 if not active else 0.32,
                        "line": {"width": 0.7, "color": "#ffffff"},
                    },
                    selected={"marker": {"size": 11, "opacity": 1.0, "line": {"color": "#0f7f82", "width": 2}}},
                    unselected={"marker": {"opacity": 0.14}},
                    hovertemplate=f"<b>{x}</b>: %{{x:.5g}}<br><b>{y}</b>: %{{y:.5g}}<br>%{{customdata[1]}}<extra></extra>",
                )
            )
    figure.update_layout(
        height=330,
        margin={"l": 48, "r": 12, "t": 42, "b": 42},
        title={"text": title, "font": {"size": 14}},
        xaxis_title=x,
        yaxis_title=y,
        dragmode=dragmode,
        clickmode="event+select",
        showlegend=False,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"color": "#26364a", "size": 11},
    )
    figure.update_xaxes(gridcolor="#e7ecef", zeroline=False)
    figure.update_yaxes(gridcolor="#e7ecef", zeroline=False)
    return figure


def _ternary(frame: pd.DataFrame, a: str, b: str, c: str, active: set[str]) -> go.Figure | None:
    prepared = prepare_ternary(frame, a, b, c)
    if prepared.valid.empty:
        return None
    figure = build_interactive_ternary(prepared.valid, a_label=a, b_label=b, c_label=c, title="B  Тройная диаграмма")
    for trace in figure.data:
        custom = getattr(trace, "customdata", None)
        if custom is None:
            continue
        selected: list[int] = []
        for index, item in enumerate(custom):
            candidate = item[0] if isinstance(item, (list, tuple)) else item
            if str(candidate) in active:
                selected.append(index)
        if active:
            trace.selectedpoints = selected
            trace.selected = {"marker": {"size": 11, "opacity": 1.0, "line": {"color": "#0f7f82", "width": 2}}}
            trace.unselected = {"marker": {"opacity": 0.18}}
    figure.update_layout(
        height=330,
        margin={"l": 18, "r": 18, "t": 42, "b": 28},
        showlegend=False,
        paper_bgcolor="#ffffff",
        font={"color": "#26364a", "size": 11},
    )
    return figure


def _spider(frame: pd.DataFrame, active: set[str]) -> None:
    reference = NORMALIZATION_REFERENCES["CI-хондрит · McDonough & Sun (1995)"]
    pattern = prepare_pattern(frame, REE_ORDER, reference)
    if pattern.data.empty:
        st.info("Для REE-панели пока нет совместимых данных.")
        return
    figure = build_pattern_figure(
        pattern,
        title="C  REE-спайдер",
        ylabel="Порода / хондрит",
        log_y=True,
        show_legend=False,
        alpha=0.68,
    )
    ids = frame.loc[pattern.data.index, "_analysis_id"].astype(str).tolist()
    if figure.axes:
        for line, analysis_id in zip(figure.axes[0].lines, ids):
            if active and analysis_id not in active:
                line.set_alpha(0.12)
                line.set_color("#b8c1c8")
            elif analysis_id in active:
                line.set_alpha(1.0)
                line.set_linewidth(2.0)
                line.set_color("#0f7f82")
        figure.axes[0].grid(alpha=.18)
    figure.set_size_inches(5.6, 3.5)
    st.pyplot(figure, width="stretch")
    plt.close(figure)


def _apply_pending(pending: set[str], mode_label: str) -> None:
    mode = {"Заменить": "replace", "Добавить": "add", "Исключить": "subtract"}.get(mode_label, "replace")
    updated = set_selection(sorted(pending), origin="Построение · связанные панели", mode=mode)
    st.session_state["selection_analysis_ids"] = list(updated.analysis_ids)
    st.session_state["active_selection_analysis_ids"] = list(updated.analysis_ids)


def _panel_defaults(numeric: list[str]) -> tuple[str, str, str, str]:
    x_a = _default_numeric(numeric, "TiO2", "TiO₂", fallback=0)
    y_a = _default_numeric([item for item in numeric if item != x_a], "MgO", fallback=0)
    x_d = _default_numeric(numeric, "SiO2", "SiO₂", fallback=0)
    y_d = _default_numeric([item for item in numeric if item != x_d], "K2O", "K₂O", fallback=0)
    return x_a, y_a, x_d, y_d


def render_linked_views_reference_page() -> None:
    render_page_header(
        "Построение",
        "Связанные панели: выделение синхронизируется между диаграммами и не меняет исходные данные.",
        context="Связанные панели",
    )
    scope = render_analysis_scope("linked_views_reference", allow_all_projects=True)
    if scope is None:
        return
    frame = scope.dataframe
    if frame.empty or "_analysis_id" not in frame.columns:
        st.info("В текущей области нет анализов для построения.")
        return

    numeric = numeric_candidates(frame)
    if len(numeric) < 2:
        st.info("Нужны как минимум две числовые колонки.")
        return

    categories = _categorical_columns(frame)
    context = read_selection()
    available = set(frame["_analysis_id"].astype(str))
    active = set(context.analysis_ids) & available

    toolbar = st.columns([1.75, 1.55, .72, .86, .9])
    with toolbar[0]:
        interaction = st.segmented_control(
            "Выделение",
            ["Клик", "Рамка", "Лассо"],
            default="Лассо",
            key="pd_linked_interaction",
            label_visibility="collapsed",
        ) or "Лассо"
    with toolbar[1]:
        mode_label = st.segmented_control(
            "Действие",
            ["Заменить", "Добавить", "Исключить"],
            default="Заменить",
            key="pd_linked_mode",
            label_visibility="collapsed",
        ) or "Заменить"
    with toolbar[2]:
        panels = st.selectbox("Панелей", [4, 6], index=0, key="pd_linked_panels", label_visibility="collapsed")
    with toolbar[3]:
        if st.button("Очистить", width="stretch", disabled=not active, key="pd_linked_clear"):
            clear_selection()
            st.session_state["selection_analysis_ids"] = []
            st.session_state["active_selection_analysis_ids"] = []
            st.rerun()
    with toolbar[4]:
        st.caption(f"Выбрано {len(active)} точек")

    x_a, y_a, x_d, y_d = _panel_defaults(numeric)
    color_by: str | None = None
    symbol_by: str | None = None
    ternary_values: tuple[str, str, str] | None = tuple(numeric[:3]) if len(numeric) >= 3 else None

    with st.expander("Настроить панели", expanded=False):
        cfg = st.columns(4)
        x_a = cfg[0].selectbox("A · X", numeric, index=numeric.index(x_a), key="pd_a_x")
        a_y_options = [item for item in numeric if item != x_a]
        y_a = cfg[0].selectbox("A · Y", a_y_options, index=a_y_options.index(y_a) if y_a in a_y_options else 0, key="pd_a_y")
        x_d = cfg[1].selectbox("D · X", numeric, index=numeric.index(x_d), key="pd_d_x")
        d_y_options = [item for item in numeric if item != x_d]
        y_d = cfg[1].selectbox("D · Y", d_y_options, index=d_y_options.index(y_d) if y_d in d_y_options else 0, key="pd_d_y")
        color_choice = cfg[2].selectbox("Цвет", ["Без группировки", *categories], key="pd_linked_color")
        symbol_choice = cfg[3].selectbox("Значок", ["Без группировки", *categories], key="pd_linked_symbol")
        color_by = None if color_choice == "Без группировки" else color_choice
        symbol_by = None if symbol_choice == "Без группировки" else symbol_choice

        if len(numeric) >= 3:
            defaults = [
                _default_numeric(numeric, "F", fallback=0),
                _default_numeric(numeric, "Cl", fallback=1),
                _default_numeric(numeric, "OH", fallback=2),
            ]
            unique_defaults: list[str] = []
            for value in defaults:
                if value not in unique_defaults:
                    unique_defaults.append(value)
            for value in numeric:
                if len(unique_defaults) >= 3:
                    break
                if value not in unique_defaults:
                    unique_defaults.append(value)
            tcols = st.columns(3)
            a = tcols[0].selectbox("B · вершина A", numeric, index=numeric.index(unique_defaults[0]), key="pd_t_a")
            b_options = [value for value in numeric if value != a]
            b_default = unique_defaults[1] if unique_defaults[1] in b_options else b_options[0]
            b = tcols[1].selectbox("B · вершина B", b_options, index=b_options.index(b_default), key="pd_t_b")
            c_options = [value for value in numeric if value not in {a, b}]
            c_default = unique_defaults[2] if unique_defaults[2] in c_options else c_options[0]
            c = tcols[2].selectbox("B · вершина C", c_options, index=c_options.index(c_default), key="pd_t_c")
            ternary_values = (a, b, c)
        else:
            st.caption("Для тройной диаграммы нужны три числовые колонки. Остальные панели остаются доступными.")

    left, center, right = st.columns([1.05, 4.35, 1.18], gap="small")
    with left:
        with st.container(border=True):
            st.markdown('<div class="pd-panel-title">Предварительный отбор</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="pd-big-count">{len(active)}</div><div class="pd-screen-subtitle">точек</div>', unsafe_allow_html=True)
            if context.origin:
                st.markdown(f'<span class="pd-chip"><span class="pd-dot"></span>{context.origin}</span>', unsafe_allow_html=True)
            st.caption("Выбор синхронизирован во всех панелях" if active else "Выделите точки на интерактивной панели")
            group_name = st.text_input("Название группы", placeholder="Например, каймы флогопита", key="pd_group_name")
            can_save_group = bool(active and group_name.strip() and scope.project_id is not None)
            if st.button("Сохранить как рабочую группу", type="primary", width="stretch", disabled=not can_save_group, key="pd_save_group"):
                try:
                    save_selection(int(scope.project_id), name=group_name, analysis_ids=sorted(active), context={"origin": "linked_views_reference"})
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.success("Рабочая группа сохранена")
            if scope.project_id is None and active:
                st.caption("Именованную группу можно сохранить после выбора одного проекта.")
            st.caption("Исходные данные не изменяются")

    pending: set[str] = set()
    dragmode = "lasso" if interaction == "Лассо" else "select"
    selection_modes = ("points", "box", "lasso")

    with center:
        top = st.columns(2, gap="small")
        with top[0]:
            event = st.plotly_chart(
                _scatter(frame, x_a, y_a, title=f"A  {x_a} vs {y_a}", color_by=color_by, symbol_by=symbol_by, active=active, dragmode=dragmode),
                width="stretch",
                key="pd_linked_a",
                on_select="rerun",
                selection_mode=selection_modes,
                config={"displaylogo": False, "scrollZoom": True},
            )
            pending |= set(selected_analysis_ids(event))
        with top[1]:
            if ternary_values is None:
                with st.container(border=True):
                    st.markdown("**B  Тройная диаграмма**")
                    st.caption("Нужны три числовые компоненты.")
            else:
                ternary = _ternary(frame, *ternary_values, active)
                if ternary is None:
                    st.info("Для тройной диаграммы нет валидных строк.")
                else:
                    event = st.plotly_chart(
                        ternary,
                        width="stretch",
                        key="pd_linked_b",
                        on_select="rerun",
                        selection_mode=("points",),
                        config={"displaylogo": False},
                    )
                    pending |= set(selected_analysis_ids(event))

        bottom = st.columns(2, gap="small")
        with bottom[0]:
            _spider(frame, active)
        with bottom[1]:
            event = st.plotly_chart(
                _scatter(frame, x_d, y_d, title=f"D  {x_d} vs {y_d}", color_by=color_by, symbol_by=symbol_by, active=active, dragmode=dragmode),
                width="stretch",
                key="pd_linked_d",
                on_select="rerun",
                selection_mode=selection_modes,
                config={"displaylogo": False, "scrollZoom": True},
            )
            pending |= set(selected_analysis_ids(event))

        if int(panels) == 6:
            extra = st.columns(2, gap="small")
            e_x = _default_numeric(numeric, "Nb", fallback=0)
            e_y = _default_numeric([item for item in numeric if item != e_x], "Ta", fallback=0)
            f_x = _default_numeric(numeric, "Rb", fallback=0)
            f_y = _default_numeric([item for item in numeric if item != f_x], "Sr", fallback=0)
            with extra[0]:
                event = st.plotly_chart(
                    _scatter(frame, e_x, e_y, title=f"E  {e_x} vs {e_y}", color_by=color_by, symbol_by=symbol_by, active=active, dragmode=dragmode),
                    width="stretch", key="pd_linked_e", on_select="rerun", selection_mode=selection_modes, config={"displaylogo": False},
                )
                pending |= set(selected_analysis_ids(event))
            with extra[1]:
                event = st.plotly_chart(
                    _scatter(frame, f_x, f_y, title=f"F  {f_x} vs {f_y}", color_by=color_by, symbol_by=symbol_by, active=active, dragmode=dragmode),
                    width="stretch", key="pd_linked_f", on_select="rerun", selection_mode=selection_modes, config={"displaylogo": False},
                )
                pending |= set(selected_analysis_ids(event))

        if pending:
            apply_cols = st.columns([2.6, 1.15])
            apply_cols[0].caption(f"На графиках выделено {len(pending)} точек. Действие: {mode_label.lower()} текущую рабочую выборку.")
            if apply_cols[1].button(f"{mode_label} выборку", type="primary", width="stretch", key="pd_linked_apply"):
                _apply_pending(pending, mode_label)
                st.rerun()

    with right:
        with st.container(border=True):
            st.markdown('<div class="pd-panel-title">Кодировка</div>', unsafe_allow_html=True)
            st.caption(f"Цвет: {color_by or 'одинаковый'}")
            if color_by:
                for index, value in enumerate(frame[color_by].fillna("Без значения").astype(str).drop_duplicates().head(6)):
                    st.markdown(f'<span class="pd-chip"><span class="pd-dot" style="background:{_COLORS[index % len(_COLORS)]}"></span>{value}</span>', unsafe_allow_html=True)
            st.divider()
            st.caption(f"Значок: {symbol_by or 'одинаковый'}")
            if symbol_by:
                for value in frame[symbol_by].fillna("Без значения").astype(str).drop_duplicates().head(6):
                    st.markdown(f'<span class="pd-chip">{value}</span>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown('<div class="pd-panel-title">Связанный выбор</div>', unsafe_allow_html=True)
            st.markdown(f"**{len(active)} точек выделено**")
            st.caption("во всех панелях")
