import math


def fc_targets(cya: float) -> dict:
    return {
        "Minimum FC": round(cya * 0.075, 1),
        "Target FC Low": round(cya * 0.10, 1),
        "Target FC High": round(cya * 0.13, 1),
    }


def ppm_per_gallon(percent: float, gallons: int) -> float:
    return (percent * 10000) / gallons


def acid_recommendation(ph: float) -> str:
    if ph >= 8.2:
        return "Start with 1 quart muriatic acid, circulate 30-60 minutes, retest."
    if ph >= 8.0:
        return "Start with 24 oz muriatic acid, circulate 30-60 minutes, retest."
    if ph > 7.8:
        return "Start with 16 oz muriatic acid, circulate 30-60 minutes, retest."
    return "No acid needed."


def calc_csi(ph, ta, ch, cya, temp_f, salt=0, tds=1000):
    if None in [ph, ta, ch, cya, temp_f]:
        return None
    if ch <= 0 or ta <= 0:
        return None

    carbonate_alkalinity = max(ta - (cya * 0.33), 1)
    temp_c = (temp_f - 32) * 5 / 9
    adjusted_tds = max(tds + salt, 1)

    a = (math.log10(adjusted_tds) - 1) / 10
    b = -13.12 * math.log10(temp_c + 273) + 34.55
    c = math.log10(ch) - 0.4
    d = math.log10(carbonate_alkalinity)

    saturation_ph = (9.3 + a + b) - (c + d)
    return round(ph - saturation_ph, 2)
