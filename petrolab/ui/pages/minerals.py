from __future__ import annotations

import streamlit as st

from petrolab.minerals.registry import MINERALS
from petrolab.minerals.formulae import methods_for


def render_minerals_page() -> None:
    st.title("Минералогические модули")
    st.caption("Здесь перечислены доступные минералоспецифические модули и область их применения.")
    for key, module in MINERALS.items():
        if key == "generic":
            continue
        methods = methods_for(key)
        with st.expander(f"{module.name_ru} · {module.group_ru}"):
            st.write(module.description)
            if methods:
                st.success(f"APFU: доступно методик — {len(methods)}.")
                for method in methods:
                    st.caption(f"• {method.title_ru} · {method.normalization_ru}")
            else:
                st.warning(
                    "APFU пока не добавлена: PetroLab сохраняет химию и позволяет работать с "
                    "точками, но не подставляет формулу по похожему минералу."
                )
