import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent if (CURRENT_DIR.parent / "pool_engine").exists() else CURRENT_DIR
sys.path.insert(0, str(PROJECT_ROOT))

from pool_engine.state_builder import build_pool_state

SETTINGS_FILE = PROJECT_ROOT / "config" / "pool_weather_settings.json"


def load_settings() -> dict:
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)


def resolve_workbook_path(settings: dict) -> Path:
    workbook_path = Path(settings["workbook_path"])
    if workbook_path.is_absolute():
        return workbook_path
    return PROJECT_ROOT / workbook_path


def main():
    settings = load_settings()
    workbook_path = resolve_workbook_path(settings)
    pool = build_pool_state(workbook_path)

    print("PoolState built successfully.")
    print(f"Status: {pool.recommendation.overall_status}")
    print(f"Reason: {pool.recommendation.action_reason}")
    print(f"FC: {pool.chemistry.fc}")
    print(f"pH: {pool.chemistry.ph}")
    print(f"CSI: {pool.chemistry.csi}")
    print(f"Liquid chlorine needed: {pool.recommendation.liquid_chlorine_needed_gal} gal")
    print(f"Latest weather date: {pool.weather.date}")
    print(f"UV max: {pool.weather.uv_index_max}")


if __name__ == "__main__":
    main()
