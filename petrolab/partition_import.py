"""Import tabular partition data without losing its literature identity."""
from __future__ import annotations
import pandas as pd
from petrolab.partitioning import create_partition_model

_ALIASES={"rock type":"rock_type","rock_type":"rock_type","mineral":"mineral","element":"element","elem":"element","value":"value","kd":"value","reference":"reference","doi":"doi","kd type":"kind","type":"kind","low":"low","high":"high","sd":"sd"}
def import_partition_table(dataframe:pd.DataFrame)->list[int]:
    renamed={c:_ALIASES.get(str(c).strip().casefold(),str(c).strip().casefold()) for c in dataframe.columns}
    df=dataframe.rename(columns=renamed)
    required={"rock_type","mineral","element","value","reference"}
    if not required.issubset(df.columns): raise ValueError("Нужны колонки Rock Type, Mineral, Element, Value, Reference")
    created=[]
    for keys,group in df.groupby(["rock_type","mineral","reference"],dropna=False):
        rock,mineral,reference=map(str,keys); values={}
        for _,row in group.iterrows():
            value=pd.to_numeric(row["value"],errors="coerce")
            if pd.notna(value): values[str(row["element"])]=float(value)
        if values:
            doi=str(group["doi"].dropna().iloc[0]) if "doi" in group and group["doi"].notna().any() else ""
            kind=str(group["kind"].dropna().iloc[0]) if "kind" in group and group["kind"].notna().any() else "imported"
            created.append(create_partition_model(f"{reference} — {mineral}/{rock} melt",mineral,"silicate_melt","fixed_table",values,source={"citation":reference,"doi":doi,"imported_kind":kind},applicability={"rock":rock,"import":"tabular; review before default use"}))
    return created
