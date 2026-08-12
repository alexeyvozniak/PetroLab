from __future__ import annotations

import io
import json
from pathlib import Path
from uuid import uuid4

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab import __version__
from petrolab.db import (
    ASSETS_DIR,
    DATA_DIR,
    META_COLUMNS,
    add_dataset,
    add_image_asset,
    create_project,
    delete_image_asset,
    delete_plot_recipe,
    delete_style_profile,
    ensure_storage,
    get_dataset,
    list_change_log,
    list_datasets,
    list_image_assets,
    list_plot_recipes,
    list_projects,
    list_style_profiles,
    load_dataset_dataframe,
    load_unified_analyses,
    replace_dataset_rows,
    save_plot_recipe,
    save_style_profile,
    update_analysis_values,
    update_dataset_metadata,
)
from petrolab.dataframe_utils import (
    apply_column_filters,
    apply_quick_filter,
    compute_changes,
    dataset_label,
    display_value,
    row_identity,
)
from petrolab.io_utils import (
    list_excel_sheets,
    list_excel_sheets_path,
    numeric_candidates,
    read_tabular_path,
    read_tabular_with_map,
    sha256_bytes,
    sha256_file,
)
from petrolab.minerals.formulae import calculate_formula, methods_for
from petrolab.minerals.registry import MINERALS, labels as mineral_labels
from petrolab.plot_presets import JOURNAL_PRESETS
from petrolab.plotting import MARKERS, build_scatter, figure_png_bytes, figure_svg_bytes
from petrolab.sources import reload_linked_source, source_status, sync_cell_changes

st.set_page_config(page_title="ПетроЛаб", page_icon="◈", layout="wide")
ensure_storage()

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1650px;}
    h1, h2, h3 {letter-spacing: -0.02em;}
    [data-testid="stMetric"] {border: 1px solid rgba(80,80,80,.14); padding: 12px; border-radius: 12px;}
    .small-note {font-size: .88rem; opacity: .75;}
    </style>
    """,
    unsafe_allow_html=True,
)

for key, default in {
    "working_df": None,
    "working_meta": {},
    "loaded_recipe": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

def project_selector(key: str = "project_select"):
    projects = list_projects()
    if not projects:
        st.info("Создайте первый проект.")
        return None
    mapping = {p["name"]: p for p in projects}
    selected_name = st.selectbox("Текущий проект", list(mapping), key=key)
    return mapping[selected_name]


def save_dataset(project_id: int, df: pd.DataFrame, dataset_name: str, mineral_key: str, source_filename: str, source_sheet: str, source_hash: str, column_map: dict, source_rows: list[int], source_path: str = "", source_kind: str = "upload", header_row: int = 1, sync_enabled: bool = False) -> int:
    project_dir = DATA_DIR / f"project_{project_id}"
    project_dir.mkdir(parents=True, exist_ok=True)
    csv_path = project_dir / f"dataset_{uuid4().hex}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    dataset_id = add_dataset(project_id=project_id, name=dataset_name, mineral_key=mineral_key, source_filename=source_filename, source_sheet=source_sheet, source_sha256=source_hash, csv_path=str(csv_path), row_count=len(df), source_path=source_path, source_kind=source_kind, header_row=header_row, column_map=column_map, sync_enabled=sync_enabled)
    replace_dataset_rows(dataset_id, df, source_rows=source_rows)
    return dataset_id


def safe_copy_upload(project_id: int, filename: str, data: bytes) -> Path:
    source_dir = DATA_DIR / f"project_{project_id}" / "managed_sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    clean_name = Path(filename).name
    target = source_dir / f"{uuid4().hex[:10]}_{clean_name}"
    target.write_bytes(data)
    return target


def collect_related_images(selected_row: pd.Series, project_id: int | None = None) -> list[dict]:
    assets = list_image_assets(project_id=project_id, dataset_id=int(selected_row.get("_dataset_id")))
    related = []
    selected_aid = str(selected_row.get("_analysis_id"))
    for asset in assets:
        if asset.get("analysis_id") == selected_aid:
            related.append(asset)
        elif asset.get("scope_type") == "Набор данных":
            related.append(asset)
        elif asset.get("scope_type") == "Значение поля" and asset.get("scope_column") in selected_row.index:
            if str(selected_row.get(asset["scope_column"])) == str(asset.get("scope_value")):
                related.append(asset)
    return related


def render_asset_gallery(assets: list[dict], max_items: int = 20, width: int = 650):
    if not assets:
        st.caption("Связанных изображений нет.")
        return
    for asset in assets[:max_items]:
        path = Path(asset["stored_path"])
        if path.exists():
            try:
                st.image(str(path), caption=asset["title"] or asset["original_filename"], width=width)
            except Exception:
                st.caption(asset["original_filename"])


def style_df_from_groups(groups: list[str], existing: dict | None = None) -> pd.DataFrame:
    existing = existing or {}
    rows = []
    for i, name in enumerate(groups):
        raw = existing.get(str(name), {})
        rows.append({"Группа": str(name), "Маркер": raw.get("marker", MARKERS[i % len(MARKERS)]), "Размер ×": float(raw.get("size_multiplier", 1.0) or 1.0), "Alpha": float(raw.get("alpha", 0.9) or 0.9), "Заливка": bool(raw.get("filled", True))})
    return pd.DataFrame(rows)


def style_map_from_df(df: pd.DataFrame) -> dict:
    styles = {}
    for _, row in df.iterrows():
        styles[str(row["Группа"])] = {"marker": row["Маркер"], "size_multiplier": float(row["Размер ×"]), "alpha": float(row["Alpha"]), "filled": bool(row["Заливка"])}
    return styles

with st.sidebar:
    st.title("◈ ПетроЛаб")
    st.caption(f"Русская версия · v{__version__}")
    page = st.radio("Раздел", ["Главная", "Проекты", "Источники и импорт", "Единая база", "Изображения", "Пересчёт формул", "Минералы", "Диаграммы", "Экспорт", "Журнал изменений"], label_visibility="collapsed")
    st.divider()
    st.caption("Локальная база SQLite. Анализы связываются с исходными Excel, а изображения — с набором, полем или отдельной точкой.")

if page == "Главная":
    st.title("ПетроЛаб")
    st.write("Единая локальная рабочая среда для минералогических и геохимических анализов.")
    all_datasets = list_datasets()
    all_projects = list_projects()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Проектов", len(all_projects))
    c2.metric("Наборов данных", len(all_datasets))
    c3.metric("Анализов", sum(int(d["row_count"]) for d in all_datasets))
    c4.metric("Минералов", len({d["mineral_key"] for d in all_datasets}))
    st.subheader("Новая графическая логика")
    st.write("В «Диаграммах» теперь есть журнальные шаблоны, фильтры по колонкам, сохранённые рецепты и профили маркеров по группам.")
    if all_datasets:
        view = pd.DataFrame(all_datasets)[["project_name", "name", "mineral_key", "row_count", "source_filename", "source_sheet", "source_kind"]].copy()
        view["mineral_key"] = view["mineral_key"].map(mineral_labels()).fillna(view["mineral_key"])
        view.columns = ["Проект", "Набор", "Минерал", "Строк", "Источник", "Лист", "Тип связи"]
        st.dataframe(view, width="stretch", hide_index=True)

elif page == "Проекты":
    st.title("Проекты")
    with st.form("new_project", clear_on_submit=True):
        name = st.text_input("Название проекта")
        description = st.text_area("Краткое описание")
        if st.form_submit_button("Создать проект", type="primary"):
            try:
                create_project(name, description)
                st.success(f"Проект «{name.strip()}» создан.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    projects = list_projects()
    if projects:
        st.dataframe(pd.DataFrame(projects)[["name", "description", "created_at"]], width="stretch", hide_index=True)

elif page == "Источники и импорт":
    st.title("Источники и импорт")
    project = project_selector("import_project")
    if project is None:
        st.stop()
    tab_linked, tab_upload, tab_sources = st.tabs(["Связать локальный файл", "Загрузить копию", "Связанные источники"])
    with tab_linked:
        st.subheader("Локальный Excel с двусторонней синхронизацией")
        st.info("Укажите полный путь к XLSX/XLSM/CSV. Тогда изменения из «Единой базы» можно записывать обратно в этот файл с резервной копией.")
        local_path_text = st.text_input("Полный путь к Excel/CSV", key="local_source_path")
        header_row = st.number_input("Строка заголовков", min_value=1, max_value=200, value=1, step=1, key="local_header_row")
        local_path = Path(local_path_text).expanduser() if local_path_text.strip() else None
        if local_path is not None:
            if not local_path.exists():
                st.error("Файл по указанному пути не найден.")
            elif local_path.suffix.lower() not in {".xlsx", ".xlsm", ".xls", ".csv"}:
                st.error("Поддерживаются XLSX, XLSM, XLS и CSV.")
            else:
                try:
                    if local_path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
                        sheets = list_excel_sheets_path(local_path)
                        selected_sheets = st.multiselect("Листы для импорта", sheets, default=sheets[:1])
                    else:
                        selected_sheets = [""]
                    mineral_key = st.selectbox("Минерал", list(MINERALS), format_func=lambda k: MINERALS[k].name_ru, key="linked_mineral")
                    base_name = st.text_input("Название набора", value=local_path.stem, key="linked_dataset_name")
                    if selected_sheets:
                        preview_df, _, _ = read_tabular_path(local_path, selected_sheets[0] or None, int(header_row))
                        preview_df = MINERALS[mineral_key].calculate(preview_df)
                        st.dataframe(preview_df.head(50), width="stretch", hide_index=True)
                    if st.button("Связать и импортировать выбранные листы", type="primary", key="link_local"):
                        created = []
                        for sheet in selected_sheets:
                            df, col_map, source_rows = read_tabular_path(local_path, sheet or None, int(header_row))
                            df = MINERALS[mineral_key].calculate(df)
                            name = base_name.strip() or local_path.stem
                            if len(selected_sheets) > 1:
                                name = f"{name} · {sheet}"
                            dataset_id = save_dataset(project["id"], df, name, mineral_key, local_path.name, sheet or "", sha256_file(local_path), col_map, source_rows, source_path=str(local_path.resolve()), source_kind="linked", header_row=int(header_row), sync_enabled=local_path.suffix.lower() in {".xlsx", ".xlsm"})
                            created.append(dataset_id)
                        st.success(f"Импортировано наборов: {len(created)}.")
                        st.rerun()
                except Exception as exc:
                    st.error(f"Не удалось прочитать источник: {exc}")
    with tab_upload:
        st.subheader("Импорт через браузер")
        uploaded = st.file_uploader("Excel или CSV", type=["xlsx", "xlsm", "xls", "csv"], key="upload_source")
        if uploaded is not None:
            file_bytes = uploaded.getvalue()
            upload_header_row = st.number_input("Строка заголовков", min_value=1, max_value=200, value=1, step=1, key="upload_header_row")
            if Path(uploaded.name).suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
                sheets = list_excel_sheets(file_bytes)
                selected_sheets = st.multiselect("Листы для импорта", sheets, default=sheets[:1], key="upload_sheets")
            else:
                selected_sheets = [""]
            mineral_key = st.selectbox("Минерал", list(MINERALS), format_func=lambda k: MINERALS[k].name_ru, key="upload_mineral")
            base_name = st.text_input("Название набора", value=Path(uploaded.name).stem, key="upload_dataset_name")
            if selected_sheets:
                preview, _, _ = read_tabular_with_map(file_bytes, uploaded.name, selected_sheets[0] or None, int(upload_header_row))
                preview = MINERALS[mineral_key].calculate(preview)
                st.dataframe(preview.head(50), width="stretch", hide_index=True)
            if st.button("Импортировать рабочую копию", type="primary", key="upload_import"):
                managed_path = safe_copy_upload(project["id"], uploaded.name, file_bytes)
                created = []
                for sheet in selected_sheets:
                    df, col_map, source_rows = read_tabular_with_map(file_bytes, uploaded.name, sheet or None, int(upload_header_row))
                    df = MINERALS[mineral_key].calculate(df)
                    name = base_name.strip() or Path(uploaded.name).stem
                    if len(selected_sheets) > 1:
                        name = f"{name} · {sheet}"
                    dataset_id = save_dataset(project["id"], df, name, mineral_key, uploaded.name, sheet or "", sha256_bytes(file_bytes), col_map, source_rows, source_path=str(managed_path), source_kind="managed_copy", header_row=int(upload_header_row), sync_enabled=managed_path.suffix.lower() in {".xlsx", ".xlsm"})
                    created.append(dataset_id)
                st.success(f"Импортировано наборов: {len(created)}.")
                st.rerun()
    with tab_sources:
        datasets = list_datasets(project["id"])
        if not datasets:
            st.info("В проекте пока нет источников.")
        for d in datasets:
            status, detail = source_status(d)
            icon = {"актуален": "✓", "изменён вне ПетроЛаба": "↻", "не найден": "!", "несвязанный": "·"}.get(status, "·")
            with st.expander(f"{icon} {d['name']} · {d['source_filename']} · {d['source_sheet'] or 'CSV/активный лист'}"):
                st.write(f"**Статус:** {status}")
                st.code(detail)
                if status == "изменён вне ПетроЛаба":
                    if st.button("Обновить базу из этого Excel", key=f"reload_{d['id']}"):
                        try:
                            df, mapping, source_rows, new_hash = reload_linked_source(int(d["id"]))
                            df = MINERALS.get(d["mineral_key"], MINERALS["generic"]).calculate(df)
                            replace_dataset_rows(int(d["id"]), df, source_rows=source_rows, preserve_ids_by_source_row=True)
                            update_dataset_metadata(int(d["id"]), source_sha256=new_hash, column_map_json=mapping, row_count=len(df))
                            st.success("База обновлена из источника.")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))

elif page == "Единая база":
    st.title("Единая база анализов")
    all_projects = list_projects()
    if not all_projects:
        st.info("Сначала создайте проект и импортируйте данные.")
        st.stop()
    scope = st.radio("Область", ["Один проект", "Все проекты"], horizontal=True)
    selected_project_id = None
    if scope == "Один проект":
        project = project_selector("db_project")
        if project is None:
            st.stop()
        selected_project_id = project["id"]
    datasets = list_datasets(selected_project_id)
    if not datasets:
        st.info("В выбранной области нет данных.")
        st.stop()
    labels = {dataset_label(d): int(d["id"]) for d in datasets}
    selected_labels = st.multiselect("Наборы данных", list(labels), default=list(labels))
    selected_ids = [labels[x] for x in selected_labels]
    if not selected_ids:
        st.stop()
    db_df = load_unified_analyses(selected_project_id, selected_ids)
    if db_df.empty:
        st.stop()
    query = st.text_input("Поиск по всей выбранной базе", key="db_search")
    shown = apply_quick_filter(db_df, query).copy()
    disabled_cols = [c for c in shown.columns if c in META_COLUMNS or str(c).startswith("_") or c in {"Σ оксидов", "QC суммы"}]
    edited = st.data_editor(shown, width="stretch", hide_index=True, height=650, disabled=disabled_cols, num_rows="fixed", key="unified_editor")
    changes = compute_changes(
        shown,
        edited,
        protected_columns=META_COLUMNS | {"Σ оксидов", "QC суммы"},
    )
    b1, b2 = st.columns(2)
    if b1.button("Сохранить изменения в базе", type="primary", disabled=not changes, width="stretch"):
        update_analysis_values(changes, synced_to_source=False)
        st.success("Изменения сохранены в базе.")
        st.rerun()
    if b2.button("Сохранить в базе и записать в Excel", disabled=not changes, width="stretch"):
        grouped = {}
        for ch in changes:
            grouped.setdefault(int(ch["dataset_id"]), []).append(ch)
        successful, failures = 0, []
        for dataset_id, ds_changes in grouped.items():
            d = get_dataset(dataset_id)
            try:
                if not d.get("sync_enabled"):
                    raise ValueError("обратная запись для этого источника отключена")
                mapping = json.loads(d.get("column_map_json") or "{}")
                writable = [ch for ch in ds_changes if ch["column_name"] in mapping]
                backup = sync_cell_changes(d, writable)
                update_analysis_values(ds_changes, synced_to_source=True, source_backup=backup)
                successful += 1
            except Exception as exc:
                failures.append(f"{d['name']}: {exc}")
        if successful:
            st.success(f"Синхронизировано источников: {successful}")
        for text in failures:
            st.error(text)
        if successful and not failures:
            st.rerun()
    with st.expander("Карточка точки и связанные изображения"):
        if not shown.empty:
            point_map = {f"{row_identity(row)} · {row.get('Источник', '')} · строка {row.get('_source_row', '—')} · {str(row['_analysis_id'])[:8]}": str(row["_analysis_id"]) for _, row in shown.head(3000).iterrows()}
            selected_point_label = st.selectbox("Точка", list(point_map), key="db_point_card")
            selected_aid = point_map[selected_point_label]
            selected_row = shown[shown["_analysis_id"].astype(str) == selected_aid].iloc[0]
            visible_columns = [c for c in shown.columns if not str(c).startswith("_")]
            point_properties = pd.DataFrame(
                {
                    "Параметр": visible_columns,
                    "Значение": [display_value(selected_row.get(c)) for c in visible_columns],
                }
            )
            st.dataframe(point_properties, width="stretch", hide_index=True, height=360)
            render_asset_gallery(collect_related_images(selected_row, project_id=selected_project_id))

elif page == "Изображения":
    st.title("Изображения и аналитические точки")
    project = project_selector("images_project")
    if project is None:
        st.stop()
    datasets = list_datasets(project["id"])
    if not datasets:
        st.stop()
    ds_map = {dataset_label(d): d for d in datasets}
    chosen = ds_map[st.selectbox("Набор данных", list(ds_map), key="img_dataset")]
    df = load_dataset_dataframe(int(chosen["id"]), include_meta=True)
    query = st.text_input("Найти точку/образец/зерно", key="img_search")
    filtered = apply_quick_filter(df, query)
    scope_type = st.radio("Привязать изображение к", ["Набор данных", "Значение поля", "Конкретная точка анализа"], horizontal=True)
    analysis_id = None
    scope_column = ""
    scope_value = ""
    if scope_type == "Значение поля":
        candidates = [c for c in filtered.columns if not str(c).startswith("_") and filtered[c].nunique(dropna=True) <= 300]
        if candidates:
            scope_column = st.selectbox("Поле", candidates)
            values = filtered[scope_column].dropna().astype(str).unique().tolist()
            scope_value = st.selectbox("Значение", values) if values else ""
    elif scope_type == "Конкретная точка анализа" and not filtered.empty:
        option_map = {f"{row_identity(row)} · строка {row.get('_source_row', '—')} · {str(row['_analysis_id'])[:8]}": str(row["_analysis_id"]) for _, row in filtered.head(3000).iterrows()}
        analysis_id = option_map[st.selectbox("Аналитическая точка", list(option_map))]
    kind = st.selectbox("Тип изображения", ["BSE", "EDS", "Оптическая микрофотография", "Карта элементов", "Фото образца", "Другое"])
    title = st.text_input("Подпись/название изображения")
    files = st.file_uploader("Изображения", type=["png", "jpg", "jpeg", "webp", "tif", "tiff"], accept_multiple_files=True, key="image_upload")
    if st.button("Привязать изображения", type="primary", disabled=not files):
        asset_dir = ASSETS_DIR / f"project_{project['id']}" / f"dataset_{chosen['id']}"
        asset_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for f in files or []:
            suffix = Path(f.name).suffix.lower()
            target = asset_dir / f"{uuid4().hex}{suffix}"
            target.write_bytes(f.getvalue())
            add_image_asset(project_id=project["id"], dataset_id=int(chosen["id"]), analysis_id=analysis_id, scope_type=scope_type, scope_column=scope_column, scope_value=scope_value, kind=kind, title=title.strip(), original_filename=f.name, stored_path=str(target))
            count += 1
        st.success(f"Привязано изображений: {count}.")
        st.rerun()
    st.subheader("Галерея набора")
    assets = list_image_assets(dataset_id=int(chosen["id"]))
    for asset in assets[:100]:
        with st.expander(f"{asset['kind']} · {asset['title'] or asset['original_filename']} · {asset['scope_type']}"):
            render_asset_gallery([asset], max_items=1, width=700)
            if st.button("Удалить привязку и файл", key=f"delete_asset_{asset['id']}"):
                delete_image_asset(int(asset["id"]))
                st.rerun()

elif page == "Пересчёт формул":
    st.title("Пересчёт структурных формул")
    project = project_selector("formula_project")
    if project is None:
        st.stop()
    datasets = list_datasets(project["id"])
    if not datasets:
        st.stop()
    mapping = {dataset_label(d): d for d in datasets}
    chosen = mapping[st.selectbox("Набор данных", list(mapping), key="formula_dataset")]
    methods = methods_for(chosen["mineral_key"])
    if not methods:
        st.warning("Для этого модуля пока нет валидированного минералоспецифического пересчёта.")
        st.stop()
    method_map = {m.id: m for m in methods}
    method = method_map[st.selectbox("Метод пересчёта", list(method_map), format_func=lambda mid: method_map[mid].title_ru)]
    raw_df = load_dataset_dataframe(int(chosen["id"]), include_meta=False)
    result = calculate_formula(raw_df, chosen["mineral_key"], method.id)
    st.dataframe(result.data.head(150), width="stretch", hide_index=True, height=560)

elif page == "Минералы":
    st.title("Минералогические модули")
    for key, module in MINERALS.items():
        if key != "generic":
            with st.expander(f"{module.name_ru} · {module.group_ru}"):
                st.write(module.description)

elif page == "Диаграммы":
    st.title("Диаграммы по всей базе")
    st.write("Здесь можно брать точки из разных Excel, сохранять рецепты рисунков, применять журнальные шаблоны и быстро фильтровать базу по колонкам.")
    scope = st.radio("Область данных", ["Один проект", "Все проекты"], horizontal=True, key="plot_scope")
    project_id = None
    if scope == "Один проект":
        current_project = project_selector("plot_project")
        if current_project is None:
            st.stop()
        project_id = current_project["id"]
    datasets = list_datasets(project_id)
    if not datasets:
        st.stop()
    recipe_records = list_plot_recipes(project_id)
    style_records = list_style_profiles(project_id)
    with st.expander("Сохранённые рецепты графиков", expanded=False):
        if recipe_records:
            recipe_map = {f"{r['name']} · {('общий' if r['project_id'] is None else 'проект')}": r for r in recipe_records}
            chosen_recipe_label = st.selectbox("Загрузить рецепт", ["—"] + list(recipe_map), key="recipe_select")
            c_load, c_del = st.columns(2)
            if chosen_recipe_label != "—":
                chosen_recipe = recipe_map[chosen_recipe_label]
                if c_load.button("Применить рецепт", key="load_recipe_btn"):
                    st.session_state.loaded_recipe = chosen_recipe["config"]
                    st.rerun()
                if c_del.button("Удалить рецепт", key="delete_recipe_btn"):
                    delete_plot_recipe(int(chosen_recipe["id"]))
                    st.success("Рецепт удалён.")
                    st.rerun()
    recipe = st.session_state.get("loaded_recipe") or {}
    ds_labels = {dataset_label(d): int(d["id"]) for d in datasets}
    default_labels = [label for label, did in ds_labels.items() if did in recipe.get("dataset_ids", list(ds_labels.values()))] if recipe else list(ds_labels)
    selected_labels = st.multiselect("Наборы для графика", list(ds_labels), default=default_labels, key="plot_datasets")
    selected_ids = [ds_labels[x] for x in selected_labels]
    if not selected_ids:
        st.stop()
    df = load_unified_analyses(project_id, selected_ids)
    if df.empty:
        st.stop()
    minerals = sorted(df["Минерал"].dropna().astype(str).unique())
    default_minerals = recipe.get("minerals", minerals) if recipe else minerals
    selected_minerals = st.multiselect("Минералы", minerals, default=[m for m in default_minerals if m in minerals], format_func=lambda k: MINERALS.get(k, MINERALS["generic"]).name_ru, key="plot_minerals")
    if selected_minerals:
        df = df[df["Минерал"].astype(str).isin(selected_minerals)]
    query = st.text_input("Быстрый строковый поиск", value=recipe.get("query", ""), key="plot_search")
    df = apply_quick_filter(df, query)
    with st.expander("Фильтры по колонкам", expanded=False):
        candidate_filter_columns = [c for c in df.columns if not str(c).startswith("_") and df[c].nunique(dropna=True) <= 100]
        preferred_filter_columns = [c for c in ["Проект", "Набор", "Минерал", "Источник", "Лист", "Group", "Type", "Generation", "Sample", "Grain"] if c in candidate_filter_columns]
        filter_choices = st.multiselect("Колонки для фильтрации", preferred_filter_columns + [c for c in candidate_filter_columns if c not in preferred_filter_columns], default=[c for c in recipe.get("column_filters", {}).keys() if c in candidate_filter_columns], key="column_filter_columns")
        chosen_filters = {}
        for col in filter_choices:
            values = sorted(df[col].dropna().astype(str).unique().tolist())
            defaults = [v for v in recipe.get("column_filters", {}).get(col, []) if v in values]
            chosen_filters[col] = st.multiselect(f"{col}", values, default=defaults, key=f"filter_vals_{col}")
        if chosen_filters:
            df = apply_column_filters(df, chosen_filters)
    numeric = numeric_candidates(df)
    if len(numeric) < 2:
        st.error("Недостаточно числовых колонок после применения фильтров.")
        st.stop()
    preset_names = list(JOURNAL_PRESETS)
    preset_default = recipe.get("journal_preset", "Свой") if recipe.get("journal_preset", "Свой") in JOURNAL_PRESETS else "Свой"
    preset = st.selectbox("Шаблон графика", preset_names, index=preset_names.index(preset_default), key="journal_preset")
    preset_cfg = JOURNAL_PRESETS[preset]
    categorical = [c for c in df.columns if not str(c).startswith("_") and c not in numeric and df[c].nunique(dropna=True) <= 80]
    preferred_groups = [c for c in ["Набор", "Минерал", "Источник", "Лист"] if c in df.columns]
    categorical = preferred_groups + [c for c in categorical if c not in preferred_groups]
    c1, c2, c3 = st.columns(3)
    x = c1.selectbox("Ось X", numeric, index=(numeric.index(recipe.get("x")) if recipe.get("x") in numeric else 0))
    y = c2.selectbox("Ось Y", numeric, index=(numeric.index(recipe.get("y")) if recipe.get("y") in numeric else min(1, len(numeric) - 1)))
    group_options = ["Без группировки"] + categorical
    group_default = recipe.get("group_col") if recipe.get("group_col") in categorical else "Без группировки"
    group = c3.selectbox("Группировка", group_options, index=group_options.index(group_default))
    group_col = None if group == "Без группировки" else group
    c4, c5, c6, c7 = st.columns(4)
    x_label = c4.text_input("Подпись X", value=recipe.get("x_label", x))
    y_label = c5.text_input("Подпись Y", value=recipe.get("y_label", y))
    marker_size = c6.slider("Размер маркеров", 10, 180, int(recipe.get("marker_size", preset_cfg["marker_size"])), 2)
    title = c7.text_input("Заголовок", value=recipe.get("title", ""))
    with st.expander("Оси, подписи и журнальное оформление", expanded=False):
        a1, a2, a3, a4 = st.columns(4)
        x_min = a1.number_input("X min", value=recipe.get("x_min", None), step=0.1)
        x_max = a2.number_input("X max", value=recipe.get("x_max", None), step=0.1)
        y_min = a3.number_input("Y min", value=recipe.get("y_min", None), step=0.1)
        y_max = a4.number_input("Y max", value=recipe.get("y_max", None), step=0.1)
        b1, b2, b3, b4 = st.columns(4)
        log_x = b1.checkbox("Логарифмическая X", value=recipe.get("log_x", False))
        log_y = b2.checkbox("Логарифмическая Y", value=recipe.get("log_y", False))
        show_grid = b3.checkbox("Сетка", value=recipe.get("show_grid", preset_cfg["show_grid"]))
        monochrome = b4.checkbox("Ч/б режим", value=recipe.get("monochrome", preset_cfg["monochrome"]))
        d1, d2, d3 = st.columns(3)
        show_legend = d1.checkbox("Показывать легенду", value=recipe.get("show_legend", preset_cfg["show_legend"]))
        annotate = d2.checkbox("Подписывать точки", value=recipe.get("annotate", False))
        label_candidates = [c for c in df.columns if not str(c).startswith("_") and df[c].nunique(dropna=True) <= max(200, len(df))]
        label_col_choice = d3.selectbox("Поле для подписи", ["—"] + label_candidates, index=(1 + label_candidates.index(recipe.get("label_col")) if recipe.get("label_col") in label_candidates else 0))
        label_col = None if label_col_choice == "—" else label_col_choice
        annotate_top_n = st.slider("Сколько точек подписывать", 1, 1000, int(recipe.get("annotate_top_n", 25))) if annotate and label_col else 0
        e1, e2, e3, e4 = st.columns(4)
        figure_width = e1.number_input("Ширина фигуры", min_value=3.0, max_value=20.0, value=float(recipe.get("figure_width", preset_cfg["figure_width"])), step=0.1)
        figure_height = e2.number_input("Высота фигуры", min_value=3.0, max_value=20.0, value=float(recipe.get("figure_height", preset_cfg["figure_height"])), step=0.1)
        font_size = e3.number_input("Размер шрифта", min_value=6.0, max_value=24.0, value=float(recipe.get("font_size", preset_cfg["font_size"])), step=0.5)
        tick_size = e4.number_input("Размер подписей делений", min_value=6.0, max_value=24.0, value=float(recipe.get("tick_size", preset_cfg["tick_size"])), step=0.5)
        f1, f2 = st.columns(2)
        spine_width = f1.number_input("Толщина осей", min_value=0.5, max_value=3.0, value=float(recipe.get("spine_width", preset_cfg["spine_width"])), step=0.1)
        title_size = f2.number_input("Размер заголовка", min_value=6.0, max_value=28.0, value=float(recipe.get("title_size", float(recipe.get("font_size", preset_cfg["font_size"])) + 1.0)), step=0.5)
    style_map = {}
    if group_col and group_col in df.columns:
        group_values = sorted([str(v) for v in df[group_col].dropna().astype(str).unique().tolist()])
        with st.expander("Профили маркеров по группам", expanded=False):
            profile_map = {f"{r['name']} · {r['grouping_column'] or 'без поля'}": r for r in style_records if not r['grouping_column'] or r['grouping_column'] == group_col}
            selected_profile = st.selectbox("Готовый профиль", ["—"] + list(profile_map), key="style_profile_select") if profile_map else "—"
            existing_style = profile_map[selected_profile]["styles"] if profile_map and selected_profile != "—" else recipe.get("style_map", {})
            style_editor = st.data_editor(style_df_from_groups(group_values, existing=existing_style), width="stretch", hide_index=True, column_config={"Маркер": st.column_config.SelectboxColumn("Маркер", options=MARKERS), "Размер ×": st.column_config.NumberColumn("Размер ×", min_value=0.2, max_value=5.0, step=0.1), "Alpha": st.column_config.NumberColumn("Alpha", min_value=0.1, max_value=1.0, step=0.05), "Заливка": st.column_config.CheckboxColumn("Заливка")}, key="style_editor")
            style_map = style_map_from_df(style_editor)
            s1, s2 = st.columns(2)
            profile_name = s1.text_input("Название профиля стилей", value=recipe.get("style_profile_name", ""), key="style_profile_name")
            save_scope_project = s2.checkbox("Сохранить как проектный профиль", value=True if project_id is not None else False, disabled=project_id is None)
            if st.button("Сохранить профиль стилей", key="save_style_profile"):
                save_style_profile(profile_name or f"Профиль {group_col}", group_col, style_map, project_id=project_id if save_scope_project else None)
                st.success("Профиль стилей сохранён.")
                st.rerun()
    needed = [x, y] + ([group_col] if group_col else []) + ([label_col] if label_col else [])
    base_cols = [c for c in ["_analysis_id", "_dataset_id", "_source_row", "Проект", "Набор", "Минерал", "Источник", "Лист"] if c in df.columns]
    plot_df = df[[c for c in base_cols + needed if c in df.columns]].copy()
    plot_df[x] = pd.to_numeric(plot_df[x], errors="coerce")
    plot_df[y] = pd.to_numeric(plot_df[y], errors="coerce")
    plot_df = plot_df.dropna(subset=[x, y])
    fig = build_scatter(plot_df, x, y, group_col, x_label=x_label, y_label=y_label, title=title, marker_size=marker_size, xlim=(x_min, x_max), ylim=(y_min, y_max), log_x=log_x, log_y=log_y, show_grid=show_grid, style_map=style_map, monochrome=monochrome, show_legend=show_legend, annotate=annotate, label_col=label_col, annotate_top_n=annotate_top_n, figure_size=(figure_width, figure_height), font_size=font_size, tick_size=tick_size, title_size=title_size, spine_width=spine_width)
    st.pyplot(fig, width="content")
    png = figure_png_bytes(fig, dpi=600)
    svg = figure_svg_bytes(fig)
    plt.close(fig)
    b1, b2, b3 = st.columns(3)
    b1.download_button("PNG · 600 dpi", png, file_name="petrolab_plot.png", mime="image/png", width="stretch")
    b2.download_button("SVG", svg, file_name="petrolab_plot.svg", mime="image/svg+xml", width="stretch")
    plot_excel = io.BytesIO()
    with pd.ExcelWriter(plot_excel, engine="openpyxl") as writer:
        plot_df.to_excel(writer, index=False, sheet_name="Точки графика")
        pd.DataFrame([{"journal_preset": preset, "x": x, "y": y, "group_col": group_col or "", "x_label": x_label, "y_label": y_label, "title": title, "marker_size": marker_size, "x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max, "log_x": log_x, "log_y": log_y, "show_grid": show_grid, "monochrome": monochrome, "show_legend": show_legend, "annotate": annotate, "label_col": label_col or "", "annotate_top_n": annotate_top_n, "figure_width": figure_width, "figure_height": figure_height, "font_size": font_size, "tick_size": tick_size, "spine_width": spine_width, "title_size": title_size, "query": query, "column_filters": json.dumps(chosen_filters, ensure_ascii=False)}]).to_excel(writer, index=False, sheet_name="Настройки")
    b3.download_button("Данные графика · Excel", plot_excel.getvalue(), file_name="petrolab_plot_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    with st.expander("Сохранить текущий рецепт графика", expanded=False):
        recipe_name = st.text_input("Название рецепта", value=recipe.get("name", ""), key="save_recipe_name")
        recipe_project = st.checkbox("Сохранить как проектный рецепт", value=True if project_id is not None else False, disabled=project_id is None)
        current_recipe = {"dataset_ids": selected_ids, "minerals": selected_minerals, "query": query, "column_filters": chosen_filters, "journal_preset": preset, "x": x, "y": y, "group_col": group_col, "x_label": x_label, "y_label": y_label, "title": title, "marker_size": marker_size, "x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max, "log_x": log_x, "log_y": log_y, "show_grid": show_grid, "monochrome": monochrome, "show_legend": show_legend, "annotate": annotate, "label_col": label_col, "annotate_top_n": annotate_top_n, "figure_width": figure_width, "figure_height": figure_height, "font_size": font_size, "tick_size": tick_size, "spine_width": spine_width, "title_size": title_size, "style_map": style_map}
        if st.button("Сохранить рецепт", key="save_recipe_button"):
            save_plot_recipe(recipe_name or f"{x} vs {y}", current_recipe, project_id=project_id if recipe_project else None)
            st.success("Рецепт сохранён.")
            st.rerun()
    st.subheader("Точки, вошедшие в график")
    st.dataframe(plot_df, width="stretch", hide_index=True, height=350)
    if not plot_df.empty:
        point_map = {f"{row_identity(row)} · {row.get('Источник', '')} · строка {row.get('_source_row', '—')}": str(row["_analysis_id"]) for _, row in plot_df.head(3000).iterrows()}
        chosen_point = st.selectbox("Открыть точку с графика", list(point_map), key="plot_point_select")
        selected_row = plot_df[plot_df["_analysis_id"].astype(str) == point_map[chosen_point]].iloc[0]
        render_asset_gallery(collect_related_images(selected_row, project_id=project_id), max_items=10, width=650)

elif page == "Экспорт":
    st.title("Экспорт общей базы")
    datasets = list_datasets()
    if not datasets:
        st.stop()
    ds_labels = {dataset_label(d): int(d["id"]) for d in datasets}
    selected = st.multiselect("Наборы", list(ds_labels), default=list(ds_labels))
    ids = [ds_labels[x] for x in selected]
    if not ids:
        st.stop()
    df = load_unified_analyses(dataset_ids=ids)
    st.dataframe(df.head(80), width="stretch", hide_index=True)
    export_df = df[[c for c in df.columns if not str(c).startswith("_")]].copy()
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Все анализы")
        pd.DataFrame(list_image_assets()).to_excel(writer, index=False, sheet_name="Изображения")
        recipes = list_plot_recipes()
        if recipes:
            pd.DataFrame([{"id": r["id"], "project_id": r["project_id"], "name": r["name"], "created_at": r["created_at"], "updated_at": r["updated_at"], "config": json.dumps(r["config"], ensure_ascii=False)} for r in recipes]).to_excel(writer, index=False, sheet_name="Рецепты графиков")
        profiles = list_style_profiles()
        if profiles:
            pd.DataFrame([{"id": r["id"], "project_id": r["project_id"], "name": r["name"], "grouping_column": r["grouping_column"], "created_at": r["created_at"], "updated_at": r["updated_at"], "styles": json.dumps(r["styles"], ensure_ascii=False)} for r in profiles]).to_excel(writer, index=False, sheet_name="Профили стилей")
    st.download_button("Единый Excel", excel_buf.getvalue(), file_name="PetroLab_единая_база.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

elif page == "Журнал изменений":
    st.title("Журнал изменений")
    rows = list_change_log(limit=2000)
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=700)
    else:
        st.caption("Изменений пока нет.")
