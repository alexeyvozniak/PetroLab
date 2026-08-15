from __future__ import annotations

import html
from collections.abc import Iterable

import streamlit as st


def _escape(value: object) -> str:
    return html.escape(str(value or ""))


def _details(text: str, css_class: str, *, label: str = "ⓘ") -> str:
    if not text:
        return ""
    return (
        f'<details class="{css_class}">'
        f'<summary title="Подробнее" aria-label="Подробнее">{_escape(label)}</summary>'
        f'<div>{_escape(text)}</div>'
        "</details>"
    )


def render_page_header(
    title: str,
    description: str = "",
    *,
    eyebrow: str = "",
    context: str = "",
) -> None:
    parts = ['<header class="petrolab-page-header">']
    if eyebrow:
        parts.append(f'<div class="petrolab-eyebrow">{_escape(eyebrow)}</div>')
    parts.append('<div class="petrolab-page-title-row">')
    parts.append(f'<h1 class="petrolab-page-title">{_escape(title)}</h1>')
    if description:
        parts.append(_details(description, "petrolab-page-help"))
    parts.append("</div>")
    if context:
        parts.append(f'<div class="petrolab-context-line">{_escape(context)}</div>')
    parts.append("</header>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_section_header(title: str, note: str = "") -> None:
    help_html = _details(note, "petrolab-section-help") if note else ""
    st.markdown(
        '<div class="petrolab-section-header">'
        '<div class="petrolab-section-title-wrap">'
        f'<h2 class="petrolab-section-title">{_escape(title)}</h2>{help_html}'
        '</div></div>',
        unsafe_allow_html=True,
    )


def render_badges(items: Iterable[tuple[str, str]]) -> None:
    badges = []
    for label, tone in items:
        tone = tone if tone in {"accent", "success", "warning", "danger", "neutral"} else "neutral"
        badges.append(f'<span class="petrolab-badge {tone}">{_escape(label)}</span>')
    if badges:
        st.markdown('<div class="petrolab-badges">' + "".join(badges) + "</div>", unsafe_allow_html=True)


def render_hint(text: str) -> None:
    """Optional guidance hidden behind a small info disclosure; never use for QC/errors/warnings."""
    from petrolab.settings_service import load_settings

    if bool(load_settings().get("show_help_hints", True)) and str(text or "").strip():
        st.markdown(_details(str(text), "petrolab-inline-help"), unsafe_allow_html=True)


def render_card(title: str, body: str = "", *, meta: str = "", active: bool = False) -> None:
    active_class = " petrolab-card-active" if active else ""
    st.markdown(
        f'<div class="petrolab-card{active_class}">'
        f'<div class="petrolab-card-title">{_escape(title)}</div>'
        + (f'<div class="petrolab-card-meta">{_escape(meta)}</div>' if meta else "")
        + (f'<div>{_escape(body)}</div>' if body else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def render_result_count(count: int, noun: str = "точек") -> None:
    render_badges([(f"{int(count):,}".replace(",", " ") + f" {noun}", "neutral")])


def render_danger_intro(text: str) -> None:
    st.markdown(
        f'<div class="petrolab-danger-zone"><strong>Опасная зона</strong><br>'
        f'<span class="petrolab-card-meta">{_escape(text)}</span></div>',
        unsafe_allow_html=True,
    )
