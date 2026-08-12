from __future__ import annotations

import streamlit as st

from petrolab.minerals.registry import MINERALS


def render_minerals_page() -> None:
    st.title("Минералогические модули")
    st.caption("Здесь перечислены доступные минералоспецифические модули и область их применения.")
    for key, module in MINERALS.items():
        if key == "generic":
            continue
        with st.expander(f"{module.name_ru} · {module.group_ru}"):
            st.write(module.description)
