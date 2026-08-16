from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN
from petrolab.dataframe_utils import display_value, human_point_label
from petrolab.db import META_COLUMNS, connect
from petrolab.mineral_assignments import assign_mineral, assignment_history
from petrolab.minerals.registry import MINERALS
from petrolab.thermodynamics import thermodynamic_records_for_analysis
from petrolab.ui.components import collect_related_images, render_asset_gallery
from petrolab.ui.navigation import navigate


PROTECTED_ANALYSIS_COLUMNS = META_COLUMNS | {
    "Σ оксидов",
    "QC суммы",
    "QC химии",
    "QC железа",
    WORK_GROUP_COLUMN,
}


def _analysis_dataset_id(analysis_id: str) -> int | None:
    with connect() as con:
        row = con.execute(
            "SELECT dataset_id FROM analysis_rows WHERE analysis_id=?",
            (str(analysis_id),),
        ).fetchone()
    return int(row["dataset_id"]) if row is not None else None


def _open_thermodynamics(analysis_id: str, dataset_ids: list[int] | None = None) -> None:
    st.session_state["thermodynamics_workspace_analysis_ids"] = [str(analysis_id)]
    clean_ids = [int(value) for value in (dataset_ids or []) if value is not None]
    if not clean_ids:
        resolved = _analysis_dataset_id(str(analysis_id))
        if resolved is not None:
            clean_ids = [resolved]
    if clean_ids:
        st.session_state["thermodynamics_workspace_dataset_ids"] = list(dict.fromkeys(clean_ids))
    navigate("thermobarometry")
    st.rerun()


def render_thermodynamic_panel(
    analysis_id: str,
    project_id: int | None,
    *,
    dataset_ids: list[int] | None = None,
    expanded: bool = False,
) -> None:
    """Render the small per-analysis '+' view requested for calculated thermodynamic parameters."""
    if project_id is None:
        return
    with st.expander("＋ Термодинамические параметры", expanded=expanded):
        records = thermodynamic_records_for_analysis(int(project_id), str(analysis_id))
        if not records:
            st.caption("Для этой точки ещё нет сохранённых T / P / fO₂ расчётов.")
            if st.button("Рассчитать", key=f"point_thermo_open_{analysis_id}"):
                _open_thermodynamics(str(analysis_id), dataset_ids)
            return

        rows = []
        for record in records:
            status = record.get("Thermodynamic status", record.get("Thermobarometry status", ""))
            rows.append({
                "Метод": record.get("Метод", ""),
                "Статус": status,
                "T, °C": record.get("T (°C)"),
                "P, kbar": record.get("P (kbar)", record.get("P assumption (kbar)")),
                "ΔFMQ": record.get("ΔFMQ"),
                "Актуальность": record.get("Актуальность", ""),
                "Run": record.get("run_id", ""),
                "Рассчитано": record.get("Рассчитано", ""),
            })
        view = pd.DataFrame(rows)
        st.dataframe(view, width="stretch", hide_index=True, height=min(300, 45 + 36 * len(view)))

        newest = records[0]
        details = {
            key: value for key, value in newest.items()
            if key not in {
                "_analysis_id", "Метод", "Тип", "Режим", "Актуальность", "Рассчитано",
                "run_id", "method_id",
            }
            and value not in (None, "")
        }
        if details:
            st.caption("Последний сохранённый расчёт")
            st.dataframe(
                pd.DataFrame({"Параметр": list(details), "Значение": [display_value(value) for value in details.values()]}),
                width="stretch", hide_index=True, height=min(360, 45 + 34 * len(details)),
            )
        if any(str(record.get("Актуальность")) == "Требует пересчёта" for record in records):
            st.warning("Есть расчёты, входная химия которых после сохранения изменилась. Они оставлены как история и помечены как требующие пересчёта.")
        if st.button("Открыть термодинамику", key=f"point_thermo_recalc_{analysis_id}"):
            _open_thermodynamics(str(analysis_id), dataset_ids)


def _human_point_map(dataframe: pd.DataFrame) -> dict[str, str]:
    """Build unique user-facing labels without leaking immutable database ids."""
    result: dict[str, str] = {}
    occurrences: dict[str, int] = {}
    for _, row in dataframe.head(3000).iterrows():
        base = human_point_label(row)
        source = str(row.get("Источник") or row.get("Набор") or "").strip()
        source_row = row.get("_source_row")
        parts = [base]
        if source:
            parts.append(source)
        if pd.notna(source_row):
            try:
                parts.append(f"строка {int(source_row)}")
            except (TypeError, ValueError):
                parts.append(f"строка {source_row}")
        label = " · ".join(part for part in parts if part)
        occurrences[label] = occurrences.get(label, 0) + 1
        if occurrences[label] > 1:
            label = f"{label} · вариант {occurrences[label]}"
        result[label] = str(row["_analysis_id"])
    return result


def render_point_card(dataframe: pd.DataFrame, project_id: int | None) -> None:
    if dataframe.empty:
        return

    point_map = _human_point_map(dataframe)
    if not point_map:
        return
    selected_label = st.selectbox("Точка", list(point_map), key="db_point_card")
    analysis_id = point_map[selected_label]
    selected_row = dataframe[dataframe["_analysis_id"].astype(str) == analysis_id].iloc[0]

    visible_columns = [column for column in dataframe.columns if not str(column).startswith("_")]
    properties = pd.DataFrame(
        {
            "Параметр": visible_columns,
            "Значение": [display_value(selected_row.get(column)) for column in visible_columns],
        }
    )
    st.dataframe(properties, width="stretch", hide_index=True, height=360)

    row_dataset_ids = []
    if "_dataset_id" in selected_row.index and pd.notna(selected_row.get("_dataset_id")):
        row_dataset_ids = [int(selected_row["_dataset_id"])]
    render_thermodynamic_panel(
        analysis_id,
        project_id,
        dataset_ids=row_dataset_ids,
    )

    with st.expander("Проверить минерал / исправить отнесение", expanded=False):
        dataset_mineral = str(selected_row.get("Минерал исходного набора") or selected_row.get("Минерал") or "")
        effective_mineral = str(selected_row.get("Минерал") or dataset_mineral)
        options = ["__dataset__"] + list(MINERALS)
        selected_key = st.selectbox(
            "Минерал для этой точки",
            options,
            index=options.index(effective_mineral) if effective_mineral in options else 0,
            format_func=lambda value: (
                "Вернуть минерал набора · " + dataset_mineral
                if value == "__dataset__"
                else MINERALS[value].name_ru
            ),
            key=f"point_mineral_{analysis_id}",
            help="Это не меняет исходный Excel и не удаляет анализ. Меняется только интерпретация точки с историей правок.",
        )
        reason = st.text_input(
            "Почему изменено · необязательно",
            value=str(selected_row.get("Комментарий переотнесения") or ""),
            placeholder="например, выброс на графике; проверено по BSE",
            key=f"point_mineral_reason_{analysis_id}",
        )
        target = None if selected_key == "__dataset__" else selected_key
        if st.button("Сохранить отнесение", key=f"save_point_mineral_{analysis_id}", width="stretch"):
            try:
                change = assign_mineral(analysis_id, target, reason=reason)
            except (KeyError, ValueError) as exc:
                st.error(str(exc))
            else:
                if change.changed:
                    st.success(
                        "Отнесение сохранено. Прежняя химия и исходный минерал набора сохранены; "
                        "APFU для несовпадающего минерала будет показан пустым до нового пересчёта."
                    )
                    st.rerun()
                else:
                    st.caption("Изменений нет.")
        history = assignment_history(analysis_id)
        if history:
            st.caption("История интерпретации точки")
            st.dataframe(
                pd.DataFrame(history).rename(columns={
                    "previous_mineral_key": "Было",
                    "mineral_key": "Стало",
                    "reason": "Комментарий",
                    "changed_at": "Когда",
                }),
                width="stretch", hide_index=True, height=min(260, 45 + 35 * len(history)),
            )

    render_asset_gallery(collect_related_images(selected_row, project_id=project_id))
