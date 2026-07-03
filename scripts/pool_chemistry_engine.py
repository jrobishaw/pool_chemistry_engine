import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pool_engine.chemistry import (
    acid_recommendation,
    calc_csi,
    fc_targets,
    ppm_per_gallon,
)
from pool_engine.excel_io import (
    read_test_results,
    write_recommendations_and_pool_health,
)

SETTINGS_FILE = PROJECT_ROOT / "config" / "pool_weather_settings.json"

DEFAULT_POOL_GALLONS = 24000
DEFAULT_CHLORINE_STRENGTH_PERCENT = 10
DEFAULT_TEMP_F = 85.0

MANDATORY_TESTS = {
    "FC": "Free Chlorine",
    "CC": "Combined Chlorine",
    "pH": "pH",
}

OPTIONAL_TESTS = {
    "TC": "Total Chlorine",
    "CH": "Calcium Hardness",
    "TA": "Total Alkalinity",
    "CYA": "Cyanuric Acid",
    "Temp": "Water Temperature",
}

CARRY_FORWARD_TESTS = {
    "CYA": "Cyanuric Acid",
    "CH": "Calcium Hardness",
    "TA": "Total Alkalinity",
    "Temp": "Water Temperature",
}


def log(message: str) -> None:
    print(message)


def to_numeric_or_none(value):
    converted = pd.to_numeric(value, errors="coerce")
    if pd.isna(converted):
        return None
    return float(converted)


def load_settings() -> dict:
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)


def get_setting(settings: dict, key: str, default):
    return settings.get(key, default)


def get_latest_valid_value(tests: pd.DataFrame, column: str, latest_date):
    previous_rows = tests[tests["Date"] <= latest_date].copy()
    previous_rows[column] = pd.to_numeric(previous_rows[column], errors="coerce")
    valid_rows = previous_rows[previous_rows[column].notna()]

    if valid_rows.empty:
        return None, None

    latest_valid = valid_rows.sort_values("Date").iloc[-1]
    return float(latest_valid[column]), latest_valid["Date"]


def get_test_value(
    tests: pd.DataFrame,
    latest_row: pd.Series,
    column: str,
    display_name: str,
    mandatory: bool = False,
    allow_carry_forward: bool = False,
):
    latest_date = latest_row["Date"]
    raw_value = latest_row.get(column, None)
    value = to_numeric_or_none(raw_value)

    if value is not None:
        return value, "current", latest_date

    log(f"No numerical value present for {display_name}. Not including that test in direct current-row analysis.")

    if mandatory:
        raise SystemExit(
            f"ERROR: Mandatory test value missing for {display_name}. "
            f"Enter a numerical value in column '{column}' for the latest test row."
        )

    if allow_carry_forward:
        carried_value, carried_date = get_latest_valid_value(tests, column, latest_date)
        if carried_value is not None:
            log(
                f"Using most recent prior numerical value for {display_name}: "
                f"{carried_value} from {carried_date}."
            )
            return carried_value, "carried_forward", carried_date

        log(f"No prior numerical value found for {display_name}. This metric will be omitted.")

    return None, "missing", None


def determine_statuses(values: dict, targets: dict | None) -> tuple[str, list[str]]:
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


def main():
    settings = load_settings()
    workbook_path = Path(settings["workbook_path"])

    pool_gallons = int(get_setting(settings, "pool_gallons", DEFAULT_POOL_GALLONS))
    chlorine_strength = float(
        get_setting(settings, "chlorine_strength_percent", DEFAULT_CHLORINE_STRENGTH_PERCENT)
    )

    tests = read_test_results(workbook_path)

    if tests.empty:
        raise SystemExit("ERROR: No dated test results found in Test Results sheet.")

    latest = tests.iloc[-1]
    latest_date = latest["Date"]

    log(f"Analyzing latest pool test row: {latest_date}")

    values = {}
    sources = {}

    for column, display_name in MANDATORY_TESTS.items():
        value, source, source_date = get_test_value(
            tests,
            latest,
            column,
            display_name,
            mandatory=True,
            allow_carry_forward=False,
        )
        values[column] = value
        sources[f"{column} Source"] = source
        sources[f"{column} Source Date"] = source_date

    for column, display_name in OPTIONAL_TESTS.items():
        value, source, source_date = get_test_value(
            tests,
            latest,
            column,
            display_name,
            mandatory=False,
            allow_carry_forward=column in CARRY_FORWARD_TESTS,
        )
        values[column] = value
        sources[f"{column} Source"] = source
        sources[f"{column} Source Date"] = source_date

    fc = values["FC"]
    cc = values["CC"]
    ph = values["pH"]
    tc = values.get("TC")
    cya = values.get("CYA")
    ch = values.get("CH")
    ta = values.get("TA")
    temp = values.get("Temp") if values.get("Temp") is not None else DEFAULT_TEMP_F

    if values.get("Temp") is None:
        log(f"No numerical water temperature present. Using default temperature: {DEFAULT_TEMP_F}F for CSI only.")

    targets = fc_targets(cya) if cya is not None else None

    ppm_gal = ppm_per_gallon(chlorine_strength, pool_gallons)

    if targets:
        fc_needed = max(targets["Target FC High"] - fc, 0)
        chlorine_gal = round(fc_needed / ppm_gal, 2)
        minimum_fc = targets["Minimum FC"]
        target_fc_low = targets["Target FC Low"]
        target_fc_high = targets["Target FC High"]
    else:
        chlorine_gal = None
        minimum_fc = None
        target_fc_low = None
        target_fc_high = None
        log("No CYA value available. Chlorine target and dosing recommendation cannot be calculated.")

    acid = acid_recommendation(ph)

    csi = calc_csi(ph, ta, ch, cya, temp)

    if csi is None:
        log("CSI not calculated because pH, TA, CH, CYA, or Temp is missing.")

    fc_cya_ratio = round(fc / cya, 3) if cya and cya > 0 else None

    overall, reasons = determine_statuses(values, targets)
    action_reason = " ".join(reasons) if reasons else "No immediate corrective action needed."

    recommendations = pd.DataFrame([{
        "Date": latest_date,
        "Overall Status": overall,
        "Action Reason": action_reason,

        "FC": fc,
        "TC": tc if tc is not None else fc + cc,
        "CC": cc,
        "pH": ph,
        "CH": ch,
        "TA": ta,
        "CYA": cya,
        "Temp": values.get("Temp"),

        "Minimum FC": minimum_fc,
        "Target FC Low": target_fc_low,
        "Target FC High": target_fc_high,
        f"{chlorine_strength:g}% Liquid Chlorine Needed (gal)": chlorine_gal,

        "Acid Recommendation": acid,
        "CSI": csi,
        "FC/CYA Ratio": fc_cya_ratio,

        "Pool Gallons": pool_gallons,
        "Chlorine Strength %": chlorine_strength,
        "FC ppm per 1 gal Chlorine": round(ppm_gal, 2),

        **sources,
    }])

    pool_health = pd.DataFrame([{
        "Date": latest_date,
        "CSI": csi,
        "FC/CYA Ratio": fc_cya_ratio,
        "Daily FC Loss": "",
        "Days Since Filter Cleaning": "",
        "Days Since Water Added": "",
        "Notes": action_reason,
    }])

    write_recommendations_and_pool_health(workbook_path, recommendations, pool_health)

    log("Pool chemistry recommendations updated successfully.")
    log(f"Overall Status: {overall}")
    log(f"Reason: {action_reason}")

    if chlorine_gal is not None:
        log(f"Add {chlorine_strength:g}% liquid chlorine: {chlorine_gal} gallons")
    else:
        log("Liquid chlorine recommendation not calculated because CYA is unavailable.")

    log(f"Acid: {acid}")
    log(f"CSI: {csi}")


if __name__ == "__main__":
    main()