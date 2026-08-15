from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ORDER_MODES = {
    "selection": "Порядок выбранных analysis_id / строк",
    "explicit": "Числовая колонка порядка",
    "label_number": "Номер из подписи точки",
    "distance": "Готовое расстояние",
    "geometry": "Расстояние по координатам",
}


@dataclass(frozen=True)
class GrainProfileResult:
    dataframe: pd.DataFrame
    x_label: str
    order_mode: str
    normalized: bool
    reversed_direction: bool


_LABEL_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _exact_selection(dataframe: pd.DataFrame, analysis_ids: list[str] | tuple[str, ...] | None) -> pd.DataFrame:
    if not analysis_ids:
        return dataframe.copy()
    if "_analysis_id" not in dataframe.columns:
        raise ValueError("Для точного профиля в таблице отсутствует _analysis_id")
    wanted = list(dict.fromkeys(str(value) for value in analysis_ids if str(value)))
    if not wanted:
        return dataframe.iloc[0:0].copy()
    ids = dataframe["_analysis_id"].astype(str)
    duplicates = ids[ids.isin(wanted) & ids.duplicated(keep=False)]
    if not duplicates.empty:
        raise ValueError("Один analysis_id встречается в исходной таблице несколько раз")
    by_id = {str(row["_analysis_id"]): row for _, row in dataframe.loc[ids.isin(wanted)].iterrows()}
    missing = [analysis_id for analysis_id in wanted if analysis_id not in by_id]
    if missing:
        raise ValueError(f"В текущей выборке отсутствуют analysis_id: {', '.join(missing[:5])}")
    return pd.DataFrame([by_id[analysis_id] for analysis_id in wanted]).reset_index(drop=True)


def _numeric_series(dataframe: pd.DataFrame, column: str, label: str) -> pd.Series:
    if not column or column not in dataframe.columns:
        raise ValueError(f"Не выбрана колонка: {label}")
    values = pd.to_numeric(dataframe[column], errors="coerce")
    if values.isna().any():
        bad = int(values.isna().sum())
        raise ValueError(f"В колонке «{column}» нечисловых/пустых значений: {bad}")
    numeric = values.astype(float)
    finite = np.isfinite(numeric.to_numpy(dtype=float))
    if not bool(np.all(finite)):
        raise ValueError(f"В колонке «{column}» есть бесконечные/некорректные числовые значения")
    return numeric


def _unique_order(values: pd.Series, label: str) -> None:
    duplicated = values.duplicated(keep=False)
    if duplicated.any():
        examples = ", ".join(str(value) for value in values[duplicated].head(5).tolist())
        raise ValueError(f"Порядок «{label}» неоднозначен: повторяются значения {examples}")


def _numbers_from_labels(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if not column or column not in dataframe.columns:
        raise ValueError("Не выбрана колонка с подписями точек")
    parsed: list[float] = []
    for value in dataframe[column]:
        matches = _LABEL_NUMBER_RE.findall(str(value or ""))
        if not matches:
            parsed.append(np.nan)
        else:
            parsed.append(float(matches[-1].replace(",", ".")))
    result = pd.Series(parsed, index=dataframe.index, dtype=float)
    if result.isna().any():
        raise ValueError(
            f"Не удалось извлечь номер из {int(result.isna().sum())} подписей в колонке «{column}»"
        )
    return result


def _normalized_x(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return values
    if not bool(np.all(np.isfinite(values))):
        raise ValueError("Координата профиля содержит бесконечное/некорректное значение")
    minimum = float(np.min(values))
    shifted = values - minimum
    maximum = float(np.max(shifted))
    if maximum <= 0:
        return np.zeros(len(values), dtype=float)
    return shifted / maximum


def prepare_grain_profile(
    dataframe: pd.DataFrame,
    *,
    analysis_ids: list[str] | tuple[str, ...] | None = None,
    order_mode: str = "selection",
    order_column: str = "",
    label_column: str = "",
    distance_column: str = "",
    x_column: str = "",
    y_column: str = "",
    coordinate_frame_column: str = "",
    normalize_distance: bool = False,
    reverse: bool = False,
) -> GrainProfileResult:
    """Prepare one scientifically explicit traverse through a grain."""
    if dataframe.empty:
        raise ValueError("Нет точек для профиля")
    if order_mode not in ORDER_MODES:
        raise ValueError(f"Неизвестный режим порядка профиля: {order_mode}")

    work = _exact_selection(dataframe, analysis_ids)
    if work.empty:
        raise ValueError("Точный отбор не содержит точек")

    x_label = "Номер точки"
    if order_mode == "selection":
        ordered = work.reset_index(drop=True)
        raw_x = np.arange(len(ordered), dtype=float)
    elif order_mode == "explicit":
        order = _numeric_series(work, order_column, "порядок точек")
        _unique_order(order, order_column)
        ordered = work.assign(_profile_sort=order).sort_values("_profile_sort", kind="mergesort").reset_index(drop=True)
        raw_x = np.arange(len(ordered), dtype=float)
        x_label = str(order_column)
    elif order_mode == "label_number":
        order = _numbers_from_labels(work, label_column)
        _unique_order(order, label_column)
        ordered = work.assign(_profile_sort=order).sort_values("_profile_sort", kind="mergesort").reset_index(drop=True)
        raw_x = np.arange(len(ordered), dtype=float)
        x_label = f"Порядок по {label_column}"
    elif order_mode == "distance":
        distance = _numeric_series(work, distance_column, "расстояние")
        _unique_order(distance, distance_column)
        ordered = work.assign(_profile_sort=distance).sort_values("_profile_sort", kind="mergesort").reset_index(drop=True)
        sorted_distance = pd.to_numeric(ordered[distance_column], errors="raise").to_numpy(dtype=float)
        raw_x = sorted_distance - float(np.min(sorted_distance))
        x_label = str(distance_column)
    else:
        if not coordinate_frame_column or coordinate_frame_column not in work.columns:
            raise ValueError("Для геометрического профиля укажите колонку системы координат/изображения")
        frame_values = work[coordinate_frame_column].fillna("").astype(str).str.strip()
        if (frame_values == "").any() or int(frame_values.nunique(dropna=False)) != 1:
            raise ValueError("Геометрический профиль разрешён только внутри одной системы координат")
        order = _numeric_series(work, order_column, "порядок точек для геометрии")
        _unique_order(order, order_column)
        x_values = _numeric_series(work, x_column, "X координата")
        y_values = _numeric_series(work, y_column, "Y координата")
        ordered = work.assign(
            _profile_sort=order,
            _profile_coord_x=x_values,
            _profile_coord_y=y_values,
        ).sort_values("_profile_sort", kind="mergesort").reset_index(drop=True)
        coordinates = ordered[["_profile_coord_x", "_profile_coord_y"]].to_numpy(dtype=float)
        if len(coordinates) <= 1:
            raw_x = np.zeros(len(coordinates), dtype=float)
        else:
            steps = np.sqrt(np.sum(np.diff(coordinates, axis=0) ** 2, axis=1))
            raw_x = np.concatenate(([0.0], np.cumsum(steps)))
        x_label = "Расстояние по профилю"

    raw_x = np.asarray(raw_x, dtype=float)
    if not bool(np.all(np.isfinite(raw_x))):
        raise ValueError("Расстояние профиля содержит бесконечное/некорректное значение")
    if reverse:
        ordered = ordered.iloc[::-1].reset_index(drop=True)
        reversed_x = raw_x[::-1]
        raw_x = float(np.max(reversed_x)) - reversed_x if len(reversed_x) else reversed_x

    plot_x = _normalized_x(raw_x) if normalize_distance else raw_x
    ordered = ordered.copy()
    ordered["_profile_order"] = np.arange(1, len(ordered) + 1, dtype=int)
    ordered["_profile_x"] = plot_x
    drop_internal = [column for column in ["_profile_sort", "_profile_coord_x", "_profile_coord_y"] if column in ordered.columns]
    if drop_internal:
        ordered = ordered.drop(columns=drop_internal)

    if normalize_distance:
        x_label = "Нормированное расстояние (0–1)"
    elif order_mode in {"selection", "explicit", "label_number"}:
        x_label = "Порядок точек"

    return GrainProfileResult(
        dataframe=ordered,
        x_label=x_label,
        order_mode=order_mode,
        normalized=bool(normalize_distance),
        reversed_direction=bool(reverse),
    )


def build_grain_profile_figure(
    result: GrainProfileResult,
    y_columns: list[str] | tuple[str, ...],
    *,
    zones: list[dict] | None = None,
    font_family: str = "Arial",
    font_size: float = 9.0,
    marker_size: float = 4.5,
    line_width: float = 1.1,
    grid: bool = False,
):
    dataframe = result.dataframe
    selected = [str(column) for column in y_columns if str(column) in dataframe.columns]
    if not selected:
        raise ValueError("Не выбрана ни одна величина Y для профиля")
    x = pd.to_numeric(dataframe["_profile_x"], errors="coerce")
    if x.isna().any() or not bool(np.all(np.isfinite(x.to_numpy(dtype=float)))):
        raise ValueError("Внутренняя координата профиля повреждена")

    with plt.rc_context({"font.family": font_family, "font.size": font_size}):
        figure, axis = plt.subplots(figsize=(7.2, 3.8), constrained_layout=True)
        for zone in zones or []:
            try:
                start = float(zone.get("start"))
                end = float(zone.get("end"))
            except (TypeError, ValueError):
                continue
            if not (np.isfinite(start) and np.isfinite(end)):
                continue
            if end < start:
                start, end = end, start
            axis.axvspan(start, end, alpha=0.08, zorder=0)
            label = str(zone.get("label") or "").strip()
            if label:
                axis.text((start + end) / 2.0, 0.98, label, transform=axis.get_xaxis_transform(), ha="center", va="top", fontsize=max(6.0, font_size - 1.0))

        for column in selected:
            y = pd.to_numeric(dataframe[column], errors="coerce").astype(float)
            y = y.where(np.isfinite(y), np.nan)
            if y.notna().sum() == 0:
                raise ValueError(f"В серии «{column}» нет конечных числовых значений")
            axis.plot(
                x.to_numpy(dtype=float),
                y.to_numpy(dtype=float),
                marker="o",
                markersize=float(marker_size),
                linewidth=float(line_width),
                label=column,
            )
        axis.set_xlabel(result.x_label)
        axis.set_ylabel("Значение")
        if len(selected) > 1:
            axis.legend(frameon=False)
        if grid:
            axis.grid(True, alpha=0.18)
        axis.tick_params(direction="out")
        return figure


def grain_profile_recipe(
    result: GrainProfileResult,
    *,
    y_columns: list[str] | tuple[str, ...],
    analysis_ids: list[str] | tuple[str, ...] | None = None,
    zones: list[dict] | None = None,
) -> dict:
    dataframe = result.dataframe
    ids = []
    if "_analysis_id" in dataframe.columns:
        ids = dataframe["_analysis_id"].astype(str).tolist()
    elif analysis_ids:
        ids = [str(value) for value in analysis_ids]
    return {
        "recipe_version": 1,
        "kind": "grain_profile",
        "analysis_ids": ids,
        "order_mode": result.order_mode,
        "normalized": result.normalized,
        "reversed_direction": result.reversed_direction,
        "x_label": result.x_label,
        "y_columns": [str(value) for value in y_columns],
        "zones": list(zones or []),
    }


def recipe_json_bytes(recipe: dict) -> bytes:
    return json.dumps(recipe, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def figure_bytes(figure, format_name: str = "svg", dpi: int = 600) -> bytes:
    fmt = str(format_name).lower()
    if fmt not in {"svg", "png"}:
        raise ValueError("Профиль экспортируется в SVG или PNG")
    buffer = io.BytesIO()
    figure.savefig(buffer, format=fmt, dpi=int(dpi), bbox_inches="tight")
    return buffer.getvalue()
