from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.collaboration_merge import apply_collaboration_merge, plan_collaboration_merge
from petrolab.dataframe_utils import dataset_label
from petrolab.db import connect, list_accessible_datasets, list_projects
from petrolab.exchange_identity import get_exchange_workspace_uuid
from petrolab.exchange_package import ExchangeSelection, create_exchange_package, preview_exchange_package
from petrolab.measurement_registry import list_entities
from petrolab.repositories.image_repository import list_image_records
from petrolab.sample_registry import list_samples
from petrolab.selective_exchange_merge import apply_selective_exchange_merge
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project_id


_KIND_LABELS = {
    "thin_section": "шлиф",
    "grain": "зерно",
    "probe_point": "EDS/EPMA-точка",
    "la_crater": "LA-кратер",
    "aliquot": "аликвота",
}


def _project_key(value: str) -> str:
    return "".join(ch.casefold() for ch in str(value) if ch.isalnum())


def _package_kind(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        return str(manifest.get("package_kind") or "project")
    except Exception:
        return "project"


def _analysis_candidates(project_id: int, dataset_ids: list[int]) -> list[dict]:
    if not dataset_ids:
        return []
    marks = ",".join("?" for _ in dataset_ids)
    with connect() as con:
        rows = con.execute(
            f"""
            SELECT a.analysis_id,a.source_row,a.row_index,d.id AS dataset_id,d.name AS dataset_name,
                   d.mineral_key,d.source_sheet
            FROM project_dataset_links l
            JOIN datasets d ON d.id=l.dataset_id
            JOIN analysis_rows a ON a.dataset_id=d.id
            WHERE l.project_id=? AND d.id IN ({marks})
            ORDER BY d.name,a.row_index,a.analysis_id
            """,
            [int(project_id), *[int(value) for value in dataset_ids]],
        ).fetchall()
    return [dict(row) for row in rows]


def _render_send_package(project_id: int) -> None:
    st.subheader("Передать часть базы")
    st.caption(
        "Соберите маленький .petrolab-пакет для коллеги. PetroLab добавит только необходимый "
        "родительский контекст: Sample, сессию, provenance и связи выбранных объектов."
    )

    samples = list_samples(int(project_id))
    sample_labels = {
        f"{row['name']} · весь образец": int(row["id"])
        for row in samples
    }
    selected_sample_labels = st.multiselect(
        "Образцы целиком",
        list(sample_labels),
        key="exchange_full_samples",
        help="Выбирайте здесь Sample только если хотите передать всё, что к нему привязано.",
    )
    selected_sample_ids = [sample_labels[label] for label in selected_sample_labels]

    try:
        entities = list_entities(int(project_id))
    except Exception:
        entities = []
    entity_labels: dict[str, int] = {}
    for row in entities:
        kind = _KIND_LABELS.get(str(row.get("kind") or ""), str(row.get("kind") or "объект"))
        sample = str(row.get("sample_name") or "без Sample")
        parent = str(row.get("parent_name") or "").strip()
        trail = f" · внутри {parent}" if parent else ""
        label = f"{sample} · {kind}: {row['name']}{trail} · #{row['id']}"
        entity_labels[label] = int(row["id"])
    selected_entity_labels = st.multiselect(
        "Шлифы, зёрна и физические аналитические точки",
        list(entity_labels),
        key="exchange_entities",
        help="Выбор дочерней точки автоматически добавляет её шлиф/зерно как контекст, но не соседние точки.",
    )
    selected_entity_ids = [entity_labels[label] for label in selected_entity_labels]

    datasets = list_accessible_datasets(int(project_id))
    dataset_labels = {dataset_label(row): int(row["id"]) for row in datasets}
    selected_dataset_labels = st.multiselect(
        "Datasets целиком",
        list(dataset_labels),
        key="exchange_full_datasets",
        help="Здесь выбирается весь dataset со всеми его строками.",
    )
    selected_dataset_ids = [dataset_labels[label] for label in selected_dataset_labels]

    point_source_labels = st.multiselect(
        "Где искать отдельные EDS / EPMA / LA-точки",
        list(dataset_labels),
        key="exchange_point_sources",
        help="Этот выбор только открывает список точек ниже и сам по себе ничего не добавляет в пакет.",
    )
    point_source_ids = [dataset_labels[label] for label in point_source_labels]
    analyses = _analysis_candidates(int(project_id), point_source_ids)
    analysis_labels: dict[str, str] = {}
    for row in analyses:
        source_row = row.get("source_row")
        where = f"строка {source_row}" if source_row is not None else f"позиция {int(row['row_index']) + 1}"
        sheet = f" · {row['source_sheet']}" if row.get("source_sheet") else ""
        label = f"{row['dataset_name']}{sheet} · {where} · {str(row['analysis_id'])[:10]}"
        analysis_labels[label] = str(row["analysis_id"])
    selected_analysis_labels = st.multiselect(
        "Отдельные аналитические точки",
        list(analysis_labels),
        key="exchange_analysis_points",
    ) if analysis_labels else []
    selected_analysis_ids = [analysis_labels[label] for label in selected_analysis_labels]

    try:
        images = list_image_records(project_id=int(project_id))
    except Exception:
        images = []
    image_labels: dict[str, int] = {}
    for row in images:
        title = str(row.get("title") or row.get("original_filename") or f"Изображение {row['id']}")
        dataset = str(row.get("dataset_name") or "без dataset")
        linked = len(row.get("analysis_ids") or [])
        suffix = f" · {linked} точек" if linked else ""
        image_labels[f"{title} · {dataset}{suffix} · #{row['id']}"] = int(row["id"])
    selected_image_labels = st.multiselect(
        "Фотографии / BSE / изображения",
        list(image_labels),
        key="exchange_images",
    ) if image_labels else []
    selected_image_ids = [image_labels[label] for label in selected_image_labels]

    include_sources = st.checkbox(
        "Добавить исходные Excel-файлы выбранных datasets",
        value=False,
        key="exchange_include_sources",
    )
    include_related_images = st.checkbox(
        "Автоматически добавить изображения, уже привязанные к выбранным точкам",
        value=True,
        key="exchange_related_images",
    )

    selected_any = bool(
        selected_sample_ids or selected_entity_ids or selected_dataset_ids
        or selected_analysis_ids or selected_image_ids
    )
    if st.button(
        "Собрать пакет для коллеги",
        type="primary",
        disabled=not selected_any,
        key="exchange_build_package",
    ):
        selection = ExchangeSelection(
            sample_ids=tuple(selected_sample_ids),
            entity_ids=tuple(selected_entity_ids),
            dataset_ids=tuple(selected_dataset_ids),
            analysis_ids=tuple(selected_analysis_ids),
            image_asset_ids=tuple(selected_image_ids),
            include_sources=bool(include_sources),
            include_related_images=bool(include_related_images),
        )
        try:
            # Persist one source-workspace UUID before the DB snapshot. It lets a colleague
            # receive later additive packages without duplicating objects already imported.
            get_exchange_workspace_uuid()
            with tempfile.TemporaryDirectory(prefix="petrolab_exchange_ui_") as temp_dir:
                target = Path(temp_dir) / "fragment.petrolab"
                result = create_exchange_package(int(project_id), target, selection)
                payload = result.path.read_bytes()
            st.session_state["exchange_package_bytes"] = payload
            st.session_state["exchange_package_summary"] = {
                "samples": result.sample_count,
                "entities": result.entity_count,
                "datasets": result.dataset_count,
                "analyses": result.analysis_count,
                "images": result.image_count,
                "sources": result.source_count,
            }
        except Exception as exc:
            st.error(f"Не удалось собрать пакет: {exc}")

    payload = st.session_state.get("exchange_package_bytes")
    summary = st.session_state.get("exchange_package_summary")
    if isinstance(payload, (bytes, bytearray)) and isinstance(summary, dict):
        render_badges([
            (f"{summary['samples']} Sample", "neutral"),
            (f"{summary['entities']} шлифов/точек", "neutral"),
            (f"{summary['datasets']} datasets", "neutral"),
            (f"{summary['analyses']} анализов", "accent"),
            (f"{summary['images']} изображений", "neutral"),
        ])
        project_name = next(
            (str(row["name"]) for row in list_projects() if int(row["id"]) == int(project_id)),
            "project",
        )
        safe = "_".join(project_name.split()) or "project"
        st.download_button(
            "Скачать пакет .petrolab",
            bytes(payload),
            file_name=f"PetroLab_{safe}_fragment.petrolab",
            mime="application/zip",
            type="primary",
            key="exchange_download_package",
        )


def _render_receive_package() -> None:
    st.subheader("Принять данные коллеги")
    uploaded = st.file_uploader(
        "Пакет PetroLab (.petrolab)",
        type=["petrolab"],
        key="collab_archive",
    )
    if uploaded is None:
        st.caption("Можно принять как полный переносимый проект, так и маленький пакет отдельных образцов/точек.")
        return

    archive_bytes = uploaded.getvalue()
    with tempfile.NamedTemporaryFile(suffix=".petrolab", delete=False) as handle:
        handle.write(archive_bytes)
        temp_path = Path(handle.name)
    try:
        try:
            preview = preview_exchange_package(temp_path)
        except Exception as exc:
            st.error(f"Пакет не читается: {exc}")
            return

        projects = list_projects()
        if not projects:
            st.info("Сначала создайте проект, в который нужно добавить данные коллеги.")
            return

        incoming_key = _project_key(preview.project_name)
        exact_matches = [
            int(row["id"]) for row in projects
            if _project_key(str(row["name"])) == incoming_key and incoming_key
        ]
        active = active_project_id()
        target_ids = [int(row["id"]) for row in projects]
        suggested = exact_matches[0] if len(exact_matches) == 1 else (int(active) if active in target_ids else target_ids[0])
        index = target_ids.index(suggested)
        project_by_id = {int(row["id"]): row for row in projects}

        if len(exact_matches) == 1:
            st.info(
                f"Похоже, у вас уже есть проект «{project_by_id[exact_matches[0]]['name']}». "
                "Добавить новые образцы и точки в него?"
            )
        target_project_id = int(st.selectbox(
            "Куда добавить пакет",
            target_ids,
            index=index,
            format_func=lambda value: str(project_by_id[int(value)]["name"]),
            key="collab_target_project",
        ))

        try:
            plan = plan_collaboration_merge(temp_path, target_project_id)
        except Exception as exc:
            st.error(f"Пакет не готов к объединению: {exc}")
            return

        kind = _package_kind(archive_bytes)
        badges = [
            (plan.incoming_project_name, "accent"),
            (f"{preview.sample_count} Sample", "neutral"),
            (f"{preview.entity_count} шлифов/точек", "neutral"),
            (f"{preview.analysis_count} анализов", "neutral"),
            ("выборочный пакет" if kind == "selection" else "полный проект", "neutral"),
        ]
        render_badges(badges)

        st.subheader("Сопоставьте образцы")
        st.caption(
            "Похожее написание — подсказка, а не автоматическое склеивание. "
            "Новые образцы можно просто добавить в выбранный проект."
        )
        target_samples = list_samples(target_project_id)
        target_by_id = {int(row["id"]): row for row in target_samples}
        decisions: dict[int, int | None] = {}
        rows = []
        for item in plan.samples:
            likely = [
                target_by_id[sid]["name"]
                for sid in item.suggested_target_ids if sid in target_by_id
            ]
            rows.append({"Входящий Sample": item.name, "Похожие в проекте": ", ".join(likely) or "—"})
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        for item in plan.samples:
            options = [-1] + list(target_by_id)
            suggested_sample = item.suggested_target_ids[0] if len(item.suggested_target_ids) == 1 else -1
            choice_index = options.index(suggested_sample) if suggested_sample in options else 0
            choice = st.selectbox(
                item.name,
                options,
                index=choice_index,
                format_func=lambda value: (
                    "Добавить как новый Sample"
                    if value == -1 else f"Это уже: {target_by_id[int(value)]['name']}"
                ),
                key=f"collab_sample_{plan.archive_sha256}_{item.source_sample_id}_{target_project_id}",
                help="PetroLab не объединяет Sample только из-за похожего названия.",
            )
            decisions[item.source_sample_id] = None if int(choice) == -1 else int(choice)

        st.subheader("Проверка")
        if kind == "selection":
            st.info(
                "Это выборочный пакет. Уже полученные ранее объекты из того же PetroLab будут переиспользованы, "
                "а новые — добавлены. Существующие научные записи автоматически не перезаписываются."
            )
        else:
            st.info(
                "Будут перенесены научные данные и provenance с новыми внутренними ID. "
                "Настройки интерфейса и пересчитываемые derived-результаты не объединяются."
            )
        confirm = st.checkbox(
            f"Я проверил Sample и хочу добавить данные в «{project_by_id[target_project_id]['name']}»",
            key=f"collab_confirm_{plan.archive_sha256}_{target_project_id}",
        )
        if st.button(
            "Добавить в проект",
            type="primary",
            disabled=not confirm,
            key=f"collab_apply_{plan.archive_sha256}_{target_project_id}",
        ):
            try:
                if kind == "selection":
                    result = apply_selective_exchange_merge(temp_path, target_project_id, decisions)
                    st.success(
                        f"Добавлено в «{project_by_id[target_project_id]['name']}»: "
                        f"{result.sample_count} Sample в пакете, {result.analysis_count} анализов, "
                        f"{result.entity_count} шлифов/физических точек; "
                        f"переиспользовано ранее полученных объектов: {result.reused_count}."
                    )
                else:
                    result = apply_collaboration_merge(temp_path, target_project_id, decisions)
                    st.success(
                        f"Добавлен проект «{result.imported_project_name}»: {result.sample_count} Sample, "
                        f"{result.dataset_count} datasets, {result.analysis_count} анализов, "
                        f"{result.rock_count} записей пород, {result.study_count} источников."
                    )
                st.rerun()
            except Exception as exc:
                st.error(f"Объединение отменено без частичного импорта: {exc}")
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def render_collaboration_page() -> None:
    render_page_header(
        "Обмен и совместная работа",
        "Передавайте весь проект или только нужные Sample, шлифы, EDS/EPMA/LA-точки и изображения. При импорте PetroLab предлагает существующий проект, но ничего не склеивает молча.",
        eyebrow="Совместная работа",
    )
    send_tab, receive_tab = st.tabs(["Передать часть базы", "Принять пакет"])
    with send_tab:
        project_id = active_project_id()
        if project_id is None:
            st.info("Сначала выберите проект, из которого хотите передать данные.")
        else:
            _render_send_package(int(project_id))
    with receive_tab:
        _render_receive_package()