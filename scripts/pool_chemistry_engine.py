import json
import sys
from pathlib import Path

import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent if (CURRENT_DIR.parent / "pool_engine").exists() else CURRENT_DIR
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
from pool_engine.test_values import collect_test_values
from pool_engine.recommendations import determine_statuses

SETTINGS_FILE = PROJECT_ROOT / "config" / "pool_weather_settings.json"

DEFAULT_POOL_GALLONS = 24000
DEFAULT_CHLORINE_STRENGTH_PERCENT = 10
DEFAULT_TEMP_F = 85.0


def log(message: str) -> None:
    print(message)


def load_settings() -> dict:
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)


def resolve_workbook_path(settings: dict) -> Path:
    workbook_path = Path(settings["workbook_path"])
    if workbook_path.is_absolute():
        return workbook_path
    return PROJECT_ROOT / workbook_path


def get_setting(settings: dict, key: str, default):
    return settings.get(key, default)


def main():
    settings = load_settings()
    workbook_path = resolve_workbook_path(settings)

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

    values, sources = collect_test_values(tests, latest, log_func=log)

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
        "Liquid Chlorine Needed (gal)": chlorine_gal,
        "Liquid Chlorine Strength %": chlorine_strength,
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
