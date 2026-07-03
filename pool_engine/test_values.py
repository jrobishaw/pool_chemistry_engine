import pandas as pd


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


def to_numeric_or_none(value):
    converted = pd.to_numeric(value, errors="coerce")
    if pd.isna(converted):
        return None
    return float(converted)


def get_latest_valid_value(tests, column, latest_date):
    previous_rows = tests[tests["Date"] <= latest_date].copy()
    previous_rows[column] = pd.to_numeric(previous_rows[column], errors="coerce")
    valid_rows = previous_rows[previous_rows[column].notna()]

    if valid_rows.empty:
        return None, None

    latest_valid = valid_rows.sort_values("Date").iloc[-1]
    return float(latest_valid[column]), latest_valid["Date"]


def get_test_value(
    tests,
    latest_row,
    column,
    display_name,
    log_func=print,
    mandatory=False,
    allow_carry_forward=False,
):
    latest_date = latest_row["Date"]
    raw_value = latest_row.get(column, None)
    value = to_numeric_or_none(raw_value)

    if value is not None:
        return value, "current", latest_date

    log_func(f"No numerical value present for {display_name}. Not including that test in direct current-row analysis.")

    if mandatory:
        raise SystemExit(
            f"ERROR: Mandatory test value missing for {display_name}. "
            f"Enter a numerical value in column '{column}' for the latest test row."
        )

    if allow_carry_forward:
        carried_value, carried_date = get_latest_valid_value(tests, column, latest_date)
        if carried_value is not None:
            log_func(f"Using most recent prior numerical value for {display_name}: {carried_value} from {carried_date}.")
            return carried_value, "carried_forward", carried_date

        log_func(f"No prior numerical value found for {display_name}. This metric will be omitted.")

    return None, "missing", None


def collect_test_values(tests, latest_row, log_func=print):
    values = {}
    sources = {}

    for column, display_name in MANDATORY_TESTS.items():
        value, source, source_date = get_test_value(
            tests,
            latest_row,
            column,
            display_name,
            log_func=log_func,
            mandatory=True,
            allow_carry_forward=False,
        )
        values[column] = value
        sources[f"{column} Source"] = source
        sources[f"{column} Source Date"] = source_date

    for column, display_name in OPTIONAL_TESTS.items():
        value, source, source_date = get_test_value(
            tests,
            latest_row,
            column,
            display_name,
            log_func=log_func,
            mandatory=False,
            allow_carry_forward=column in CARRY_FORWARD_TESTS,
        )
        values[column] = value
        sources[f"{column} Source"] = source
        sources[f"{column} Source Date"] = source_date

    return values, sources
