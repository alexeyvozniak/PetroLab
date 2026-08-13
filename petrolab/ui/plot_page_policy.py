from __future__ import annotations

_GROUP_COLORS = (
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
)


def install() -> None:
    from petrolab.ui.pages import plots as page

    def style_map_from_df(dataframe):
        styles = {}
        for index, (_, row) in enumerate(dataframe.iterrows()):
            styles[str(row["Группа"])] = {
                "marker": row["Маркер"],
                "size_multiplier": float(row["Размер ×"]),
                "alpha": float(row["Alpha"]),
                "filled": bool(row["Заливка"]),
                "color": _GROUP_COLORS[index % len(_GROUP_COLORS)],
            }
        return styles

    page._style_map_from_df = style_map_from_df

    # Keep all small page-level compatibility policies behind one UI bootstrap invoked by app.py.
    from petrolab.ui.image_page_policy import install as install_image_page_policy
    install_image_page_policy()
