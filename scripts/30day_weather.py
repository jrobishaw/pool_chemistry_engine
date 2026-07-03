import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

SETTINGS_FILE = "config/pool_weather_settings.json"
TIMEZONE = "America/Chicago"
DAYS_BACK = 30
RECORD_LIMIT = 288  # Ambient max per request


def load_settings():
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)


def fetch_ambient_data(api_key, application_key, mac_address, end_date_ms):
    url = f"https://api.ambientweather.net/v1/devices/{mac_address}"

    params = {
        "apiKey": api_key,
        "applicationKey": application_key,
        "endDate": end_date_ms,
        "limit": RECORD_LIMIT,
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def main():
    settings = load_settings()

    api_key = settings["api_key"]
    application_key = settings["application_key"]
    mac_address = settings["mac_address"]

    all_records = []

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=DAYS_BACK)

    current_end = end_time

    while current_end > start_time:
        end_date_ms = int(current_end.timestamp() * 1000)

        data = fetch_ambient_data(
            api_key=api_key,
            application_key=application_key,
            mac_address=mac_address,
            end_date_ms=end_date_ms,
        )

        if not data:
            break

        all_records.extend(data)

        oldest_dateutc = min(record["dateutc"] for record in data)
        current_end = datetime.fromtimestamp(oldest_dateutc / 1000, tz=timezone.utc) - timedelta(milliseconds=1)

        time.sleep(1)  # Be polite to the API

    if not all_records:
        raise SystemExit("No Ambient Weather data returned.")

    df = pd.DataFrame(all_records)

    df = df.drop_duplicates(subset=["dateutc"]).sort_values("dateutc")

    df["LocalDateTime"] = (
        pd.to_datetime(df["dateutc"], unit="ms", utc=True)
        .dt.tz_convert(TIMEZONE)
        .dt.tz_localize(None)
    )

    df["Date"] = df["LocalDateTime"].dt.date

    cutoff_date = (datetime.now() - timedelta(days=DAYS_BACK)).date()
    df = df[df["Date"] >= cutoff_date]

    summary = df.groupby("Date").agg(
        **{
            "UV Index Max": ("uv", "max"),
            "Rainfall": ("dailyrainin", "max"),
            "Solar Radiation Peak": ("solarradiation", "max"),
            "AvgTempF": ("tempf", "mean"),
            "AvgHumidity": ("humidity", "mean"),
            "MaxWindGustMPH": ("windgustmph", "max"),
        }
    ).reset_index()

    summary = summary.round({
        "UV Index Max": 2,
        "Rainfall": 2,
        "Solar Radiation Peak": 2,
        "AvgTempF": 2,
        "AvgHumidity": 2,
        "MaxWindGustMPH": 2,
    })

    output_file = Path("data/ambient_30day_weather_summary.xlsx")
    summary.to_excel(output_file, index=False)

    print("30-day Ambient Weather summary created successfully.")
    print(f"Rows: {len(summary)}")
    print(f"Output: {output_file.resolve()}")


if __name__ == "__main__":
    main()
