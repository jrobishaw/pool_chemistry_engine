from pathlib import Path

import pandas as pd


def read_test_results(workbook_path: Path) -> pd.DataFrame:
    """Read and normalize the Test Results worksheet."""
    tests = pd.read_excel(workbook_path, sheet_name="Test Results")
    tests["Date"] = pd.to_datetime(tests["Date"], errors="coerce")
    tests = tests.dropna(subset=["Date"]).sort_values("Date")
    return tests


def read_pool_health(workbook_path: Path) -> pd.DataFrame:
    """Read Pool Health history if it exists; otherwise return an empty dataframe."""
    try:
        return pd.read_excel(workbook_path, sheet_name="Pool Health")
    except Exception:
        return pd.DataFrame()


def append_pool_health(existing_pool_health: pd.DataFrame, pool_health: pd.DataFrame) -> pd.DataFrame:
    """Append a Pool Health row and de-duplicate by Date, keeping the latest row for each Date."""
    if not existing_pool_health.empty:
        combined_pool_health = pd.concat([existing_pool_health, pool_health], ignore_index=True)
    else:
        combined_pool_health = pool_health.copy()

    combined_pool_health["Date"] = pd.to_datetime(combined_pool_health["Date"], errors="coerce")
    combined_pool_health = (
        combined_pool_health
        .drop_duplicates(subset=["Date"], keep="last")
        .sort_values("Date")
        .reset_index(drop=True)
    )
    return combined_pool_health


def write_recommendations_and_pool_health(
    workbook_path: Path,
    recommendations: pd.DataFrame,
    pool_health: pd.DataFrame,
) -> None:
    """Write latest recommendations and append/update Pool Health history."""
    existing_pool_health = read_pool_health(workbook_path)
    combined_pool_health = append_pool_health(existing_pool_health, pool_health)

    with pd.ExcelWriter(workbook_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        recommendations.to_excel(writer, sheet_name="Pool Recommendations", index=False)
        combined_pool_health.to_excel(writer, sheet_name="Pool Health", index=False)
