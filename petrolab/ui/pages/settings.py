from __future__ import annotations

import json
import platform
from datetime import datetime
from pathlib import Path

import streamlit as st

from petrolab import __version__
from petrolab.db import ASSETS_DIR, BACKUPS_DIR, DATA_DIR, DB_PATH
from petrolab.extended_plotting import NORMALIZATION_REFERENCES
from petrolab.settings_service import load_settings, save_settings
from petrolab.ui.layout import render_hint, render_page_header
from petrolab.ui.navigation import navigate
from petrolab.visualization_presets import FIGURE_PRESETS, POINT_STYLE_PRESETS, TABLE_PRESETS


def _index(options, value, fallback=0):
    return options.index(value) if value in options else fallback


def _format_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            return f"{value:.0f} {unit}" if unit == "Б" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} ГБ"


def _folder_summary(folder: Path) -> tuple[int, int, str]:
    if not folder.exists():
        return 0, 0, "ещё нет файлов"
    files = [path for path in folder.rglob("*") if path.is_file()]
    size = sum(path.stat().st_size for path in files)
    if not files:
        return 0, size, "ещё нет файлов"
    latest = max(files, key=lambda path: path.stat().st_mtime)
    stamp = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
    return len(files), size, f"последний: {latest.name} · {stamp}"


def _diagnostic_report(settings: dict, include_paths: bool) -> bytes:
    backup_count, backup_size, backup_latest = _folder_summary(BACKUPS_DIR)
    asset_count, asset_size, _ = _folder_summary(ASSETS_DIR)
    report = {
        "application": "PetroLab",
        "version": __version__,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "preferences": settings,
        "storage": {
            "database_exists": DB_PATH.exists(),
            "database_size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
            "backup_files": backup_count,
            "backup_size_bytes": backup_size,
            "latest_backup": backup_latest,
            "asset_files": asset_count,
            "asset_size_bytes": asset_size,
        },
        "contains": "Только технические сведения и локальные предпочтения. Анализы, изображения и содержимое Excel не включены.",
    }
    if include_paths:
        report["storage"]["data_directory"] = str(DATA_DIR)
        report["storage"]["backups_directory"] = str(BACKUPS_DIR)
    return json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")


def _render_data_safety_tab(settings: dict) -> None:
    render_hint("Здесь показаны правила, которые защищают данные. Их нельзя ослабить случайным переключателем.")
    st.subheader("Связанный Excel")
    st.success("Обратная запись выполняется только по явной команде из «Анализов».")
    st.caption(
        "Перед записью PetroLab проверяет, не изменился ли исходный файл, и создаёт резервную копию. "
        "Автоматическое обновление из Excel не выполняется."
    )

    backup_count, backup_size, backup_latest = _folder_summary(BACKUPS_DIR)
    asset_count, asset_size, _ = _folder_summary(ASSETS_DIR)
    st.subheader("Локальное хранилище")
    data, backups, assets = st.columns(3)
    data.metric("Рабочая база", _format_size(DB_PATH.stat().st_size if DB_PATH.exists() else 0))
    backups.metric("Резервные копии Excel", backup_count, _format_size(backup_size))
    assets.metric("Файлы изображений", asset_count, _format_size(asset_size))
    st.caption(f"Папка данных: {DATA_DIR}")
    st.caption(f"Резервные копии: {backup_latest}")
    if st.button("Открыть перенос и резервные копии проектов", key="settings_open_project_archives"):
        navigate("projects")
        st.rerun()

    st.subheader("Диагностический отчёт")
    include_paths = st.checkbox(
        "Включить локальные пути к файлам",
        value=False,
        key="settings_diagnostics_include_paths",
        help="Оставьте выключенным, если отправляете отчёт другому человеку.",
    )
    st.download_button(
        "Скачать диагностический отчёт",
        data=_diagnostic_report(settings, include_paths),
        file_name="petrolab-diagnostics.json",
        mime="application/json",
        key="settings_download_diagnostics",
    )
    st.caption("В отчёте нет анализов, изображений и содержимого Excel.")


def _render_advanced_tab() -> None:
    st.caption("Редкие технические действия. Они не меняют научные данные.")
    with st.expander("Обслуживание интерфейса", expanded=False):
        st.caption("Кэш ускоряет открытие страниц. Очистка может сделать следующее открытие немного медленнее.")
        if st.button("Очистить временный кэш", key="settings_clear_cache"):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.success("Временный кэш очищен. Данные проектов не изменялись.")
    with st.expander("Техническая информация", expanded=False):
        st.code(
            f"PetroLab {__version__}\nPython {platform.python_version()}\nБаза: {DB_PATH.name}",
            language=None,
        )
        st.caption("Экспериментальные научные режимы не включаются глобально: они открываются только в соответствующем рабочем инструменте и не меняют исходные данные автоматически.")


def render_settings_page() -> None:
    render_page_header(
        "Настройки",
        "Устойчивые предпочтения приложения. Проекты, источники, фильтры и рабочие выборки настраиваются в своём рабочем контексте.",
        eyebrow="Система",
    )
    settings = load_settings()
    interface_tab, figures_tab, analysis_tab, safety_tab, advanced_tab = st.tabs([
        "Интерфейс", "Графики и таблицы", "Расчёты", "Данные и безопасность", "Расширенные",
    ])

    with interface_tab:
        density_labels = {"Комфортная": "comfortable", "Компактная": "compact"}
        current_density = str(settings.get("ui_density", "comfortable"))
        density_label = st.segmented_control(
            "Плотность интерфейса", list(density_labels),
            default="Компактная" if current_density == "compact" else "Комфортная",
        )
        show_help = st.checkbox("Показывать поясняющие подсказки", value=bool(settings.get("show_help_hints", True)))
        show_sample_location_prompt = st.checkbox(
            "Напоминать о местонахождении при открытии карточки образца",
            value=bool(settings.get("show_sample_location_prompt", True)),
            help="Напоминание не блокирует работу. Текущую локацию и историю всегда можно открыть в карточке образца.",
        )
        check_updates = st.checkbox(
            "Проверять наличие новой версии", value=bool(settings.get("check_updates_automatically", True)),
            help="Раз в несколько часов ПетроЛаб запрашивает у GitHub только номер публичной версии. Данные проектов, Excel и изображения не передаются.",
        )
        render_hint("Компактный режим уменьшает отступы, но не размер текста и элементов управления.")

    with figures_tab:
        figure_options = list(FIGURE_PRESETS)
        point_options = list(POINT_STYLE_PRESETS)
        figure = st.selectbox(
            "Шаблон рисунка по умолчанию", figure_options,
            index=_index(figure_options, settings.get("default_figure_preset", "Lithos")),
        )
        point = st.selectbox(
            "Стиль точек по умолчанию", point_options,
            format_func=lambda key: POINT_STYLE_PRESETS[key].title,
            index=_index(point_options, settings.get("default_point_style", "balanced")),
        )
        preview = POINT_STYLE_PRESETS[point]
        render_hint("Маркеры: " + "  ".join(preview.markers[:8]))
        table_options = list(TABLE_PRESETS)
        table = st.selectbox(
            "Шаблон таблицы по умолчанию", table_options,
            index=_index(table_options, settings.get("default_table_preset", "Lithos")),
        )
        render_hint("Шаблон задаёт стартовое оформление, но не удаляет научные колонки.")

    with analysis_tab:
        references = list(NORMALIZATION_REFERENCES)
        ree_ref = st.selectbox(
            "Нормировка REE по умолчанию", references,
            index=_index(references, settings.get("default_ree_reference", references[1]), 1),
        )
        outlier_options = ["MAD", "IQR", "NONE"]
        outlier_labels = {"MAD": "MAD — робастный z-score", "IQR": "IQR — правило Тьюки", "NONE": "Не искать автоматически"}
        outlier = st.selectbox(
            "Поиск выбросов по умолчанию", outlier_options,
            index=_index(outlier_options, settings.get("default_outlier_method", "MAD")),
            format_func=lambda value: outlier_labels[value],
        )
        render_hint("Автоматический поиск выбросов только отмечает точки и не удаляет данные.")

    with safety_tab:
        _render_data_safety_tab(settings)

    with advanced_tab:
        _render_advanced_tab()

    st.divider()
    if st.button("Сохранить настройки", type="primary"):
        save_settings({
            "default_figure_preset": figure,
            "default_table_preset": table,
            "default_point_style": point,
            "ui_density": density_labels.get(density_label or "Комфортная", "comfortable"),
            "show_help_hints": show_help,
            "show_sample_location_prompt": show_sample_location_prompt,
            "check_updates_automatically": check_updates,
            "default_ree_reference": ree_ref,
            "default_outlier_method": outlier,
        })
        st.success("Настройки сохранены.")
        st.rerun()
