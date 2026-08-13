from __future__ import annotations

import html
from collections.abc import Iterable

import streamlit as st


def _escape(value: object) -> str:
    return html.escape(str(value or ""))


def render_page_header(
    title: str,
    description: str = "",
    *,
    eyebrow: str = "",
    context: str = "",
) -> None:
    parts = ['<div class="petrolab-page-header">']
    if eyebrow:
        parts.append(f'<div class="petrolab-eyebrow">{_escape(eyebrow)}</div>')
    parts.append(f'<div class="petrolab-page-title">{_escape(title)}</div>')
    if description:
        parts.append(f'<div class="petrolab-page-lead">{_escape(description)}</div>')
    if context:
        parts.append(f'<div class="petrolab-context-line">{_escape(context)}</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_section_header(title: str, note: str = "") -> None:
    note_html = f'<div class="petrolab-section-note">{_escape(note)}</div>' if note else ""
    st.markdown(
        '<div class="petrolab-section-header">'
        f'<div class="petrolab-section-title">{_escape(title)}</div>'
        f'{note_html}</div>',
        unsafe_allow_html=True,
    )


def render_badges(items: Iterable[tuple[str, str]]) -> None:
    badges = []
    for label, tone in items:
        tone = tone if tone in {"accent", "success", "warning", "danger", "neutral"} else "neutral"
        badges.append(f'<span class="petrolab-badge {tone}">{_escape(label)}</span>')
    if badges:
        st.markdown('<div class="petrolab-badges">' + "".join(badges) + "</div>", unsafe_allow_html=True)


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
