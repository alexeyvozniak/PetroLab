from __future__ import annotations

from io import BytesIO

import pandas as pd
from openpyxl import load_workbook

from petrolab.article_tables import article_table_xlsx_bytes, format_dataframe_for_article


def test_article_formatter_preserves_numeric_looking_identifiers() -> None:
    dataframe = pd.DataFrame(
        {
            "Sample": ["001", "010"],
            "Grain": ["007", "008"],
            "Point": ["03", "04"],
            "SiO2": [40.1234, 41.9876],
        }
    )

    result = format_dataframe_for_article(dataframe, preset_name="Lithos")

    assert result["Sample"].tolist() == ["001", "010"]
    assert result["Grain"].tolist() == ["007", "008"]
    assert result["Point"].tolist() == ["03", "04"]
    assert result["SiO2"].tolist() != dataframe["SiO2"].tolist()


def test_article_xlsx_repeats_header_when_preset_requests_it() -> None:
    dataframe = pd.DataFrame(
        {
            "Sample": ["001", "002"],
            "SiO2": [40.1, 41.2],
        }
    )

    data = article_table_xlsx_bytes(
        dataframe,
        preset_name="Lithos",
        title="Mineral compositions",
    )

    workbook = load_workbook(BytesIO(data))
    worksheet = workbook.active

    assert worksheet.print_title_rows == "$3:$3"
