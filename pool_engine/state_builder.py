from pathlib import Path
from typing import Optional

import pandas as pd

from pool_engine.models import (
    ChlorineTargets,
    PoolState,
    RecommendationState,
    WaterChemistry,
    WeatherState,
)

RECOMMENDATIONS_SHEET = "Pool Recommendations"
WEATHER_SHEET = "Weather Data"


def _to_float(value) -> Optional[float]:
    converted = pd.to_numeric(value, errors="coerce")
    if pd.isna(converted):
        return None
    return float(converted)


def _latest_row(workbook_path: Path, sheet_name: str) -> dict:
    try:
        df = pd.read_excel(workbook_path, sheet_name=sheet_name)
    except Exception:
        return {}

    if df.empty:
        return {}

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("Date")

    return df.iloc[-1].to_dict()


def _build_chemistry(row: dict) -> WaterChemistry:
    return WaterChemistry(
        test_date=pd.to_datetime(row.get("Date"), errors="coerce"),
        fc=_to_float(row.get("FC")),
        tc=_to_float(row.get("TC")),
        cc=_to_float(row.get("CC")),
        ph=_to_float(row.get("pH")),
        ta=_to_float(row.get("TA")),
        ch=_to_float(row.get("CH")),
        cya=_to_float(row.get("CYA")),
        temp_f=_to_float(row.get("Temp")),
        csi=_to_float(row.get("CSI")),
        fc_cya_ratio=_to_float(row.get("FC/CYA Ratio")),
    )


def _build_chlorine_targets(row: dict) -> ChlorineTargets:
    return ChlorineTargets(
        minimum_fc=_to_float(row.get("Minimum FC")),
        target_fc_low=_to_float(row.get("Target FC Low")),
        target_fc_high=_to_float(row.get("Target FC High")),
    )


def _build_recommendation(row: dict) -> RecommendationState:
    return RecommendationState(
        overall_status=str(row.get("Overall Status", "Unknown")),
        action_reason=str(row.get("Action Reason", "No recommendation available.")),
        liquid_chlorine_needed_gal=_to_float(row.get("Liquid Chlorine Needed (gal)")),
        liquid_chlorine_strength_percent=_to_float(row.get("Liquid Chlorine Strength %")),
        acid_recommendation=str(row.get("Acid Recommendation", "No acid recommendation available.")),
        chlorine_targets=_build_chlorine_targets(row),
    )


def _build_weather(row: dict) -> WeatherState:
    return WeatherState(
        date=pd.to_datetime(row.get("Date"), errors="coerce") if row else None,
        high_temp_f=_to_float(row.get("High Temp")) if row else None,
        uv_index_max=_to_float(row.get("UV Index Max")) if row else None,
        rainfall_in=_to_float(row.get("Rainfall")) if row else None,
        solar_radiation_peak=_to_float(row.get("Solar Radiation Peak")) if row else None,
        avg_temp_f=_to_float(row.get("AvgTempF")) if row else None,
        avg_humidity=_to_float(row.get("AvgHumidity")) if row else None,
        max_wind_gust_mph=_to_float(row.get("MaxWindGustMPH")) if row else None,
    )


def build_pool_state(workbook_path: Path) -> PoolState:
    """Build the canonical current pool state from workbook-generated sheets."""
    recommendation_row = _latest_row(workbook_path, RECOMMENDATIONS_SHEET)
    if not recommendation_row:
        raise ValueError("Pool Recommendations sheet is missing or empty. Run scripts/pool_chemistry_engine.py first.")

    weather_row = _latest_row(workbook_path, WEATHER_SHEET)

    return PoolState(
        chemistry=_build_chemistry(recommendation_row),
        recommendation=_build_recommendation(recommendation_row),
        weather=_build_weather(weather_row),
    )
