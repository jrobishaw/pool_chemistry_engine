import json
import requests
import pandas as pd
from pathlib import Path

SETTINGS_FILE = "config/pool_weather_settings.json"
TIMEZONE = "America/Chicago"

with open(SETTINGS_FILE, "r") as f:
    settings = json.load(f)

api_key = settings["api_key"]
application_key = settings["application_key"]
mac = settings["mac_address"]
workbook_path = Path(settings["workbook_path"])

url = f"https://api.ambientweather.net/v1/devices/{mac}"

params = {
    "apiKey": api_key,
    "applicationKey": application_key,
    "limit": 288
}

response = requests.get(url, params=params, timeout=30)
response.raise_for_status()

new_df = pd.DataFrame(response.json())

if new_df.empty:
    raise SystemExit("No weather data returned from Ambient Weather.")

# Convert Ambient UTC milliseconds to local Excel-safe datetime
new_df["LocalDateTime"] = (
    pd.to_datetime(new_df["dateutc"], unit="ms", utc=True)
    .dt.tz_convert(TIMEZONE)
    .dt.tz_localize(None)
)

new_df["Date"] = new_df["LocalDateTime"].dt.date

# Drop Ambient's built-in 'date' field if present to avoid confusion
if "date" in new_df.columns:
    new_df = new_df.drop(columns=["date"])

# Read existing Weather Raw if it exists
try:
    existing_df = pd.read_excel(workbook_path, sheet_name="Weather Raw")
except Exception:
    existing_df = pd.DataFrame()

# Append and deduplicate
if not existing_df.empty:
    combined_df = pd.concat([existing_df, new_df], ignore_index=True)
else:
    combined_df = new_df.copy()

combined_df = (
    combined_df
    .drop_duplicates(subset=["dateutc"], keep="last")
    .sort_values("LocalDateTime")
    .reset_index(drop=True)
)

# Make sure Date is a date, not mixed object/string
combined_df["LocalDateTime"] = pd.to_datetime(combined_df["LocalDateTime"])
combined_df["Date"] = combined_df["LocalDateTime"].dt.date

# Build daily summary
summary = combined_df.groupby("Date").agg(
    HighTempF=("tempf", "max"),
    AvgTempF=("tempf", "mean"),
    MaxUV=("uv", "max"),
    MaxSolarRadiation=("solarradiation", "max"),
    DailyRainIn=("dailyrainin", "max"),
    MaxWindGustMPH=("windgustmph", "max"),
    AvgHumidity=("humidity", "mean")
).reset_index()

# Round summary values
for col in summary.columns:
    if col != "Date":
        summary[col] = summary[col].round(2)

# Build simplified Weather Data sheet for pool analysis
weather_data = summary.rename(columns={
    "HighTempF": "High Temp",
    "MaxUV": "UV Index Max",
    "DailyRainIn": "Rainfall",
    "MaxSolarRadiation": "Solar Radiation Peak"
})[
    [
        "Date",
        "High Temp",
        "UV Index Max",
        "Rainfall",
        "Solar Radiation Peak",
        "AvgTempF",
        "AvgHumidity",
        "MaxWindGustMPH"
    ]
]

# Write sheets back to workbook
with pd.ExcelWriter(workbook_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
    combined_df.to_excel(writer, sheet_name="Weather Raw", index=False)
    summary.to_excel(writer, sheet_name="Weather Daily Summary", index=False)
    weather_data.to_excel(writer, sheet_name="Weather Data", index=False)

print(f"Weather data updated successfully.")
print(f"Total raw records: {len(combined_df)}")
print(f"Daily summary rows: {len(summary)}")
