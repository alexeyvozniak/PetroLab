from __future__ import annotations


def install() -> None:
    """Replace the placeholder amphibole classifier with conservative IMA screening."""
    from petrolab.minerals import classification as target
    from petrolab.minerals.amphibole_ima import HAWTHORNE_2012, LOCOCK_2014, attach_amphibole_ima_diagnostics

    if getattr(target, "_amphibole_ima_screening_installed", False):
        return

    def classify_amphibole(dataframe):
        enriched = attach_amphibole_ima_diagnostics(dataframe)
        result = target._empty_decisions(enriched)
        for index, row in result.iterrows():
            subgroup = str(row.get("amp_B_subgroup", "") or "")
            root = str(row.get("amp_root_field", "") or "")
            candidate = str(row.get("amp_root_charge_candidate", "") or "")
            site_qc = str(row.get("amp_site_QC", "") or "")
            fe3_explicit = bool(row.get("amp_Fe3_explicit", False))
            w_status = str(row.get("amp_W_status", "") or "")
            detail = str(row.get("amp_classification_note", "") or "")

            if site_qc == "норма" and subgroup and subgroup != "unclassified":
                field = f"{subgroup} amphibole · B-site subgroup"
                level = "IMA 2012 site/subgroup screening"
                if root:
                    field += f" · {root}"
                    level = "IMA 2012 root charge-field screening"
                elif candidate:
                    field += " · root charge field withheld"
            else:
                field = "Amphibole · site/subgroup screening unresolved"
                level = "IMA 2012 diagnostic unavailable"

            note_parts = [
                "Formal amphibole species is deliberately not assigned by this screening layer.",
                f"Site QC: {site_qc or 'unavailable'}.",
                f"Fe3+ explicit: {'yes' if fe3_explicit else 'no'}.",
                f"W: {w_status or 'unresolved'}.",
            ]
            if candidate and not root:
                note_parts.append(f"Tentative charge-node candidate: {candidate}.")
            if detail:
                note_parts.append(detail)

            target._set_decision(
                result,
                index,
                target.ClassificationDecision(
                    species="",
                    field=field,
                    level=level,
                    method=f"{HAWTHORNE_2012}; {LOCOCK_2014}",
                    note=" ".join(note_parts),
                ),
            )
        return result

    target._classify_amphibole = classify_amphibole
    target._amphibole_ima_screening_installed = True
