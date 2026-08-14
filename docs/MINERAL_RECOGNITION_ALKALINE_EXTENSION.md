# Mineral Recognition v1.1 — alkaline–carbonatite extension

Scientific scope for the next recognition layer. This extension is deliberately conservative: a routine EPMA composition is promoted to a species only when chemistry is sufficient; otherwise PetroLab reports a group/chemical target and requires structural, volatile or trace-element evidence for a species-level name.

Priority additions:

- pyrochlore-supergroup / Nb-Ta-Ti oxide target (species-level names require full A/B-site chemistry and F/O/OH information);
- loparite/perovskite-related REE-Na-Ti oxide target;
- melilite-group target (akermanite–gehlenite chemistry; structural/species detail remains separate);
- pectolite / Na-Ca pyroxenoid target;
- wollastonite / Ca-silicate target;
- hydrogarnet / hydrous Ca-Al garnet-like target (routine EPMA alone cannot quantify H);
- zeolite-like Na-Ca-Al-Si targets including natrolite-group chemistry, reported conservatively because H2O is not measured by routine EPMA;
- additional alkaline/carbonatite accessory targets for Nb-Ta-Ti-REE-rich phases where measured oxides are diagnostic.

Validation requirements:

1. keep ruleset/reference versions and catalog hash in every suggestion;
2. add positive and hard-negative regression compositions for each new target;
3. never reduce a structural polymorph or hydration-state ambiguity to a species name from EPMA chemistry alone;
4. preserve `ambiguous` / `unresolved` as scientifically valid outputs;
5. keep the independent GEOROC family benchmark separate from species-level claims.
