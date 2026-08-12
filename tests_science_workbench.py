from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_science_") as tmp:
        root = Path(tmp)
        os.environ["PETROLAB_DATA_DIR"] = str(root / "data")

        from petrolab.article_tables import article_table_xlsx_bytes, format_dataframe_for_article
        from petrolab.db import create_project, ensure_storage
        from petrolab.extended_plotting import CI_CHONDRITE_1995, prepare_pattern
        from petrolab.repositories.rock_repository import (
            composition_wide,
            create_rock,
            get_composition,
            get_isotopes,
            replace_composition,
            replace_isotopes,
        )
        from petrolab.rock_plotting import build_tas_figure, figure_bytes
        from petrolab.scientific_overlays import XY_OVERLAYS, classify_grutter_g10
        from petrolab.services.rock_service import rhodes_equilibrium_fo, whole_rock_mg_number
        from petrolab.statistics import prepare_matrix, run_clustering, run_pca
        from petrolab.visualization_presets import FIGURE_PRESETS, POINT_STYLE_PRESETS, TABLE_PRESETS

        ensure_storage()
        project_id = create_project("Science test", "")
        rock_id = create_rock(project_id, "R1", massif="Kola", lithology="lamprophyre", age_ma=380.0)
        composition = {
            "SiO2": 44.0, "Na2O": 2.5, "K2O": 3.0, "MgO": 12.0, "FeOt": 10.0,
            "La [µg/g]": 23.7, "Ce [µg/g]": 61.3,
        }
        replace_composition(rock_id, composition, units={"La [µg/g]": "µg/g", "Ce [µg/g]": "µg/g"})
        stored = get_composition(rock_id)
        assert set(["SiO2", "MgO", "FeOt"]).issubset(set(stored["analyte"]))
        wide = composition_wide(project_id)
        assert len(wide) == 1 and float(wide.loc[0, "SiO2"]) == 44.0
        mgnum = whole_rock_mg_number(composition)
        assert 0.6 < mgnum < 0.8
        assert 80.0 < rhodes_equilibrium_fo(mgnum, 0.30) < 100.0

        isotopes = pd.DataFrame([
            {"system": "Sr", "ratio_name": "87Sr/86Sr", "value": 0.7032, "uncertainty": 0.00002,
             "initial_value": 0.7029, "age_ma_used": 380.0, "method": "TIMS", "laboratory": "Lab", "notes": ""}
        ])
        replace_isotopes(rock_id, isotopes)
        assert len(get_isotopes(rock_id)) == 1

        fig = build_tas_figure(wide)
        assert len(figure_bytes(fig, "png", 150)) > 1000

        traces = pd.DataFrame({"La [µg/g]": [23.7, 47.4], "Ce [µg/g]": [61.3, 122.6], "Pr": [9.28, 18.56]})
        normalized = prepare_pattern(traces, ["La", "Ce", "Pr"], CI_CHONDRITE_1995)
        assert normalized.elements == ("La", "Ce")
        assert "Pr" in normalized.missing_elements, "Unknown-unit bare trace element must not be normalized"
        assert np.allclose(normalized.data["La"].to_numpy(), [100.0, 200.0])
        raw = prepare_pattern(traces, ["Pr"], None)
        assert raw.elements == ("Pr",)

        features = pd.DataFrame({"A": [1.0, 1.1, 5.0, 5.1], "B": [2.0, 2.1, 8.0, 8.1]})
        prepared = prepare_matrix(features, ["A", "B"], scaler="standard")
        pca = run_pca(prepared, 2)
        assert pca.scores.shape == (4, 2)
        clusters = run_clustering(prepared, method="kmeans", n_clusters=2)
        assert clusters.labels.nunique() == 2

        table = format_dataframe_for_article(pd.DataFrame({"SiO2": [40.1234], "Rb [µg/g]": [123.456]}), preset_name="Lithos")
        assert float(table.loc[0, "SiO2"]) == 40.12
        payload = article_table_xlsx_bytes(table, preset_name="Lithos", title="Test")
        path = root / "table.xlsx"
        path.write_bytes(payload)
        workbook = load_workbook(path)
        assert "Table" in workbook.sheetnames

        assert {"Lithos", "ДАН", "Elsevier 1-column"}.issubset(FIGURE_PRESETS)
        assert {"balanced", "open", "bw"}.issubset(POINT_STYLE_PRESETS)
        assert "Lithos" in TABLE_PRESETS
        assert {"ilmenite_wyatt_kimberlite_curve", "garnet_grutter_g10_diagnostic"}.issubset(XY_OVERLAYS)

        garnet = pd.DataFrame({"CaO": [3.0], "Cr2O3": [6.0], "MnO": [0.2], "MgO": [20.0], "FeO": [8.0]})
        classification = classify_grutter_g10(garnet)
        assert classification.iloc[0] == "G10A diagnostic"

    print("science workbench tests: OK")


if __name__ == "__main__":
    main()
