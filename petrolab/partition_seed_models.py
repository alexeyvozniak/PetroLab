"""Explicit, source-scoped seed models.  Calling this function never overwrites user models."""
from petrolab.partitioning import create_partition_model, list_partition_models
_LAT_SOURCE={"citation":"LaTourrette, Hervig & Holloway (1995), EPSL 135, 13–30","doi":"10.1016/0012-821X(95)00146-4","data_index":"GERM Kd database, citation id 155","measurement":"experimental"}
_MODELS=[
 ("LaTourrette 1995 — phlogopite / basanite melt","phlogopite","silicate_melt",{"Li":0.064,"Be":0.95,"F":2.0,"Rb":2.48,"Sr":0.159,"Y":0.018,"Zr":0.017,"Nb":0.088,"Ba":3.68,"La":0.028,"Nd":0.012,"Gd":0.016,"Hf":0.19,"Pb":0.1,"Th":0.0014,"U":0.0011}),
 ("LaTourrette 1995 — amphibole / basanite melt","amphibole","silicate_melt",{"Be":0.124,"F":1.65,"Na":0.73,"Rb":0.2,"Sr":0.298,"Y":0.52,"Zr":0.127,"Nb":0.159,"Ba":0.16,"La":0.055,"Ce":0.096,"Pr":0.17,"Nd":0.25,"Gd":0.32,"Ho":0.62,"Er":0.57,"Tm":0.51,"Yb":0.43,"Hf":0.33,"Pb":0.04,"Th":0.0039,"U":0.0041}),
]
def seed_initial_alkaline_models()->list[int]:
    existing={x["name"] for x in list_partition_models()}
    made=[]
    for name,mineral,counter,values in _MODELS:
        if name not in existing:
            made.append(create_partition_model(name,mineral,counter,"fixed_table",values,source=_LAT_SOURCE,applicability={"rock":"natural basanite","mode":"proxy allowed; applicability warning outside basanite","units":"element concentration ratios"}))
    return made
