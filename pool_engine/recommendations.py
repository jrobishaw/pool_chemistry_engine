from typing import List, Optional, Tuple


def determine_statuses(values: dict, targets: Optional[dict]) -> Tuple[str, List[str]]:
    """Determine overall pool status and action reasons from current values and FC targets."""
    reasons = []

    fc = values.get("FC")
    cc = values.get("CC")
    ph = values.get("pH")
    ch = values.get("CH")
    cya = values.get("CYA")

    if targets and fc is not None:
        if fc < targets["Minimum FC"]:
            reasons.append("FC is below minimum for current CYA.")
    elif cya is None:
        reasons.append("CYA unavailable; FC target cannot be fully evaluated.")

    if cc is not None and cc > 0.5:
        reasons.append("CC is elevated; possible organic/oxidation demand.")

    if ph is not None and ph > 8.0:
        reasons.append("pH is high; lower pH before making other balance changes.")

    if ch is not None and ch < 200:
        reasons.append("CH is low for plaster/gunite and may make water aggressive.")

    if cya is not None and cya > 60:
        reasons.append("CYA is high; avoid routine trichlor tablet use.")

    if cya is not None and cya < 30:
        reasons.append("CYA is low; chlorine will burn off quickly in sun.")

    overall = "Action Needed" if reasons else "Good"
    return overall, reasons
