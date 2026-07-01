import json
import math
from pathlib import Path
import pandas as pd

SETTINGS_FILE = "pool_weather_settings.json"
POOL_GALLONS = 24000
CHLORINE_STRENGTH_PERCENT = 10


def to_number(df, cols):
    for col in cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fc_targets(cya):
    return {
        "Minimum FC": round(cya * 0.075, 1),
        "Target FC Low": round(cya * 0.10, 1),
        "Target FC High": round(cya * 0.13, 1),
    }


def ppm_per_gallon(percent, gallons):
    return (percent * 10000) / gallons


def calc_csi(ph, ta, ch, cya, temp_f, salt=0, tds=1000):
    """
    Approximate Calcite Saturation Index / Langelier-style calculation.
    Useful for pool trend monitoring.

    Inputs:
      ph      = measured pH
      ta      = total alkalinity ppm
      ch      = calcium hardness ppm
      cya     = cyanuric acid ppm
      temp_f  = water temperature F
      salt    = salt ppm, optional
      tds     = total dissolved solids ppm, optional baseline
    """

    if ch <= 0 or ta <= 0:
        return None

    # CYA-adjusted carbonate alkalinity approximation.
    # At normal pool pH, roughly 1/3 of CYA contributes to measured TA.
    carbonate_alkalinity = ta - (cya * 0.33)
    carbonate_alkalinity = max(carbonate_alkalinity, 1)

    temp_c = (temp_f - 32) * 5 / 9

    # TDS approximation. If salt is known, include it.
    adjusted_tds = max(tds + salt, 1)

    # Langelier-style factors
    A = (math.log10(adjusted_tds) - 1) / 10
    B = -13.12 * math.log10(temp_c + 273) + 34.55
    C = math.log10(ch) - 0.4
    D = math.log10(carbonate_alkalinity)

    saturation_ph = (9.3 + A + B) - (C + D)
    csi = ph - saturation_ph

    return round(csi, 2)

def main():
    with open(SETTINGS_FILE, "r") as f:
        settings = json.load(f)

    workbook_path = Path(settings["workbook_path"])

    tests = pd.read_excel(workbook_path, sheet_name="Test Results")
    tests["Date"] = pd.to_datetime(tests["Date"], errors="coerce")

    numeric_cols = ["FC", "TC", "CC", "pH", "CH", "TA", "CYA", "Temp"]
    tests = to_number(tests, numeric_cols)

    complete = tests.dropna(subset=["Date", "FC", "CC", "pH", "CH", "TA", "CYA"])
    if complete.empty:
        raise SystemExit("No complete test rows found.")

    latest = complete.sort_values("Date").iloc[-1]

    fc = float(latest["FC"])
    tc = float(latest["TC"]) if not pd.isna(latest["TC"]) else fc + float(latest["CC"])
    cc = float(latest["CC"])
    ph = float(latest["pH"])
    ch = float(latest["CH"])
    ta = float(latest["TA"])
    cya = float(latest["CYA"])
    temp = float(latest["Temp"]) if not pd.isna(latest["Temp"]) else 85.0

    targets = fc_targets(cya)
    ppm_gal = ppm_per_gallon(CHLORINE_STRENGTH_PERCENT, POOL_GALLONS)
    fc_needed = max(targets["Target FC High"] - fc, 0)
    chlorine_gal = round(fc_needed / ppm_gal, 2)

    reasons = []
    if fc < targets["Minimum FC"]:
        reasons.append("FC is below minimum for current CYA.")
    if ph > 8.0:
        reasons.append("pH is high; lower pH before making other balance changes.")
    if ch < 200:
        reasons.append("CH is low for plaster/gunite and may make water aggressive.")
    if cc > 0.5:
        reasons.append("CC is elevated; possible oxidation demand.")
    if cya > 60:
        reasons.append("CYA is high; avoid routine trichlor tablet use.")

    overall = "Action Needed" if reasons else "Good"
    acid = (
        "Start with 1 quart muriatic acid, circulate, retest." if ph >= 8.2 else
        "Start with 24 oz muriatic acid, circulate, retest." if ph >= 8.0 else
        "Start with 16 oz muriatic acid, circulate, retest." if ph > 7.8 else
        "No acid needed."
    )

    csi = calc_csi(ph, ta, ch, cya, temp)
    fc_cya_ratio = round(fc / cya, 3) if cya > 0 else None

    recommendations = pd.DataFrame([{
        "Date": latest["Date"].date(),
        "Overall Status": overall,
        "Action Reason": " ".join(reasons) if reasons else "No immediate corrective action needed.",
        "FC": fc,
        "TC": tc,
        "CC": cc,
        "CYA": cya,
        **targets,
        "10% Liquid Chlorine Needed (gal)": chlorine_gal,
        "pH": ph,
        "Acid Recommendation": acid,
        "TA": ta,
        "CH": ch,
        "Temp": temp,
        "CSI": csi,
        "FC/CYA Ratio": fc_cya_ratio,
        "Pool Gallons": POOL_GALLONS,
        "Chlorine Strength %": CHLORINE_STRENGTH_PERCENT,
        "FC ppm per 1 gal Chlorine": round(ppm_gal, 2),
    }])

    pool_health = pd.DataFrame([{
        "Date": latest["Date"].date(),
        "CSI": csi,
        "FC/CYA Ratio": fc_cya_ratio,
        "Daily FC Loss": "",
        "Days Since Filter Cleaning": "",
        "Days Since Water Added": "",
        "Notes": recommendations.loc[0, "Action Reason"],
    }])

    # Append Pool Health history instead of replacing it
    try:
        existing_pool_health = pd.read_excel(workbook_path, sheet_name="Pool Health")
    except Exception:
        existing_pool_health = pd.DataFrame()

    if not existing_pool_health.empty:
        combined_pool_health = pd.concat(
            [existing_pool_health, pool_health],
            ignore_index=True
        )
    else:
        combined_pool_health = pool_health.copy()

    # Prevent duplicate entries for the same test date
    combined_pool_health["Date"] = pd.to_datetime(combined_pool_health["Date"], errors="coerce")
    combined_pool_health = (
        combined_pool_health
        .drop_duplicates(subset=["Date"], keep="last")
        .sort_values("Date")
        .reset_index(drop=True)
    )

    with pd.ExcelWriter(workbook_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        recommendations.to_excel(writer, sheet_name="Pool Recommendations", index=False)
        combined_pool_health.to_excel(writer, sheet_name="Pool Health", index=False)

    print("Pool chemistry recommendations updated successfully.")
    print(f"Overall Status: {overall}")
    print(f"Reason: {recommendations.loc[0, 'Action Reason']}")
    print(f"Add 10% liquid chlorine: {chlorine_gal} gallons")
    print(f"Acid: {acid}")
    print(f"CSI: {csi}")


if __name__ == "__main__":
    main()
