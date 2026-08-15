from __future__ import annotations

from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from petrolab.grain_profiles import GrainProfileResult, prepare_grain_profile


@dataclass(frozen=True)
class GroupedGrainProfiles:
    group_column: str
    profiles: tuple[tuple[str, GrainProfileResult], ...]

    @property
    def analysis_ids(self) -> list[str]:
        values: list[str] = []
        for _, result in self.profiles:
            if "_analysis_id" in result.dataframe.columns:
                values.extend(result.dataframe["_analysis_id"].astype(str).tolist())
        return values


def prepare_grouped_grain_profiles(
    dataframe: pd.DataFrame,
    *,
    group_column: str,
    analysis_ids: list[str] | tuple[str, ...] | None = None,
    order_mode: str = "selection",
    order_column: str = "",
    label_column: str = "",
    distance_column: str = "",
    x_column: str = "",
    y_column: str = "",
    coordinate_frame_column: str = "",
    normalize_distance: bool = True,
    reverse: bool = False,
) -> GroupedGrainProfiles:
    if not group_column or group_column not in dataframe.columns:
        raise ValueError("Не выбрана колонка, разделяющая зерна")
    if "_analysis_id" not in dataframe.columns:
        raise ValueError("Для нескольких зерен требуется _analysis_id")

    work = dataframe.copy()
    if analysis_ids:
        wanted = list(dict.fromkeys(str(value) for value in analysis_ids if str(value)))
        ids = work["_analysis_id"].astype(str)
        if ids[ids.isin(wanted)].duplicated(keep=False).any():
            raise ValueError("Один analysis_id встречается в исходной таблице несколько раз")
        by_id = {str(row["_analysis_id"]): row for _, row in work.loc[ids.isin(wanted)].iterrows()}
        missing = [value for value in wanted if value not in by_id]
        if missing:
            raise ValueError("В текущей выборке отсутствуют analysis_id: " + ", ".join(missing[:5]))
        work = pd.DataFrame([by_id[value] for value in wanted]).reset_index(drop=True)

    groups = work[group_column].fillna("").astype(str).str.strip()
    if (groups == "").any():
        raise ValueError(f"В колонке «{group_column}» есть пустые значения; зерна нельзя разделить однозначно")
    unique_groups = list(dict.fromkeys(groups.tolist()))
    if len(unique_groups) < 2:
        raise ValueError("Для режима нескольких зерен нужны минимум две группы")

    prepared: list[tuple[str, GrainProfileResult]] = []
    for group_name in unique_groups:
        subset = work.loc[groups.eq(group_name)].copy()
        if len(subset) < 2:
            raise ValueError(f"В группе «{group_name}» меньше двух точек")
        ids = subset["_analysis_id"].astype(str).tolist()
        result = prepare_grain_profile(
            subset,
            analysis_ids=ids,
            order_mode=order_mode,
            order_column=order_column,
            label_column=label_column,
            distance_column=distance_column,
            x_column=x_column,
            y_column=y_column,
            coordinate_frame_column=coordinate_frame_column,
            normalize_distance=normalize_distance,
            reverse=reverse,
        )
        prepared.append((group_name, result))
    return GroupedGrainProfiles(group_column=str(group_column), profiles=tuple(prepared))


def build_grouped_grain_profile_figure(
    grouped: GroupedGrainProfiles,
    y_columns: list[str] | tuple[str, ...],
    *,
    display_mode: str = "overlay",
    font_family: str = "Arial",
    font_size: float = 9.0,
    marker_size: float = 4.0,
    line_width: float = 1.0,
    grid: bool = False,
):
    selected = [str(value) for value in y_columns if str(value)]
    if not selected:
        raise ValueError("Не выбрана ни одна величина Y для сравнения зерен")
    if display_mode not in {"overlay", "facets"}:
        raise ValueError("Неизвестный режим отображения нескольких зерен")

    with plt.rc_context({"font.family": font_family, "font.size": font_size}):
        if display_mode == "overlay":
            figure, axis = plt.subplots(figsize=(7.2, 4.2), constrained_layout=True)
            for group_name, result in grouped.profiles:
                frame = result.dataframe
                x = pd.to_numeric(frame["_profile_x"], errors="coerce").to_numpy(dtype=float)
                if not bool(np.all(np.isfinite(x))):
                    raise ValueError(f"Повреждена координата профиля группы «{group_name}»")
                for column in selected:
                    if column not in frame.columns:
                        raise ValueError(f"В группе «{group_name}» отсутствует серия «{column}»")
                    y = pd.to_numeric(frame[column], errors="coerce").astype(float)
                    y = y.where(np.isfinite(y), np.nan)
                    if y.notna().sum() == 0:
                        raise ValueError(f"В группе «{group_name}» для «{column}» нет конечных значений")
                    label = group_name if len(selected) == 1 else f"{group_name} · {column}"
                    axis.plot(x, y.to_numpy(dtype=float), marker="o", markersize=marker_size, linewidth=line_width, label=label)
            axis.set_xlabel(grouped.profiles[0][1].x_label)
            axis.set_ylabel(selected[0] if len(selected) == 1 else "Значение")
            axis.legend(frameon=False)
            if grid:
                axis.grid(True, alpha=0.18)
            axis.tick_params(direction="out")
            return figure

        rows = len(grouped.profiles)
        figure, axes = plt.subplots(rows, 1, figsize=(7.2, max(2.6, 2.5 * rows)), squeeze=False, sharex=True, constrained_layout=True)
        for index, (group_name, result) in enumerate(grouped.profiles):
            axis = axes[index, 0]
            frame = result.dataframe
            x = pd.to_numeric(frame["_profile_x"], errors="coerce").to_numpy(dtype=float)
            if not bool(np.all(np.isfinite(x))):
                raise ValueError(f"Повреждена координата профиля группы «{group_name}»")
            for column in selected:
                if column not in frame.columns:
                    raise ValueError(f"В группе «{group_name}» отсутствует серия «{column}»")
                y = pd.to_numeric(frame[column], errors="coerce").astype(float)
                y = y.where(np.isfinite(y), np.nan)
                if y.notna().sum() == 0:
                    raise ValueError(f"В группе «{group_name}» для «{column}» нет конечных значений")
                axis.plot(x, y.to_numpy(dtype=float), marker="o", markersize=marker_size, linewidth=line_width, label=column)
            axis.set_title(group_name, loc="left")
            axis.set_ylabel("Значение")
            if len(selected) > 1:
                axis.legend(frameon=False)
            if grid:
                axis.grid(True, alpha=0.18)
            axis.tick_params(direction="out")
        axes[-1, 0].set_xlabel(grouped.profiles[0][1].x_label)
        return figure


def grouped_profile_dataframe(grouped: GroupedGrainProfiles) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for group_name, result in grouped.profiles:
        frame = result.dataframe.copy()
        frame.insert(0, "_profile_group", group_name)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def grouped_grain_profile_recipe(
    grouped: GroupedGrainProfiles,
    *,
    y_columns: list[str] | tuple[str, ...],
    display_mode: str,
) -> dict:
    return {
        "recipe_version": 1,
        "kind": "grain_profile_grouped",
        "group_column": grouped.group_column,
        "display_mode": str(display_mode),
        "y_columns": [str(value) for value in y_columns],
        "groups": [
            {
                "name": group_name,
                "analysis_ids": result.dataframe["_analysis_id"].astype(str).tolist()
                if "_analysis_id" in result.dataframe.columns else [],
                "order_mode": result.order_mode,
                "normalized": result.normalized,
                "reversed_direction": result.reversed_direction,
                "x_label": result.x_label,
            }
            for group_name, result in grouped.profiles
        ],
    }
