import pandas as pd


REQUIRED_COLUMNS = [
    "Comp_no",
    "Date",
    "CUR_MKT_CAP(HKD)",
    "BS_CUR_LIAB(HKD)",
    "BS_LT_BORROW(HKD)",
    "BS_TOT_LIAB2(HKD)",
    "BS_TOT_ASSET(HKD)",
    "Risk_Free_Rate",
]


def validate_required_columns(df: pd.DataFrame, dataset_name: str = "data") -> None:
    """
    Check that all required input columns exist.
    """
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing} for {dataset_name}"
        )


def validate_missing_values(df: pd.DataFrame, dataset_name: str = "data") -> None:
    """
    Check that required inputs do not contain missing values.
    """
    missing = df[REQUIRED_COLUMNS].isna().sum()
    missing = missing[missing > 0]

    if not missing.empty:
        raise ValueError(
            f"Missing values found:\n{missing} for {dataset_name}"
        )


def validate_numeric_values(df: pd.DataFrame, dataset_name: str = "data") -> None:
    """
    Check basic economic/data constraints.
    """

    if (df["CUR_MKT_CAP(HKD)"] <= 0).any():
        raise ValueError(f"CUR_MKT_CAP(HKD) must be greater than 0 for {dataset_name}.")

    if (df["BS_CUR_LIAB(HKD)"] < 0).any():
        raise ValueError(f"BS_CUR_LIAB(HKD) cannot be negative for {dataset_name}.")

    if (df["BS_LT_BORROW(HKD)"] < 0).any():
        raise ValueError(f"BS_LT_BORROW(HKD) cannot be negative for {dataset_name}.")

    if (df["BS_TOT_LIAB2(HKD)"] < 0).any():
        raise ValueError(f"BS_TOT_LIAB2(HKD) cannot be negative for {dataset_name}.")

    if (df["BS_TOT_ASSET(HKD)"] <= 0).any():
        raise ValueError(f"BS_TOT_ASSET(HKD) must be greater than 0 for {dataset_name}.")

    if (df["Risk_Free_Rate"] < 0).any():
        raise ValueError(f"Risk_Free_Rate cannot be negative for {dataset_name}.")


def validate_dates(df: pd.DataFrame, dataset_name: str = "data") -> None:
    """
    Check dates and duplicate observations.
    """
    dates = pd.to_datetime(df["Date"], errors="coerce")

    if dates.isna().any():
        raise ValueError(f"Invalid dates found for {dataset_name}.")

    # Duplicate date is only a problem for the same company.
    if df.duplicated(subset=["Comp_no", "Date"]).any():
        raise ValueError(
            f"Duplicate Comp_no-Date observations found for {dataset_name}."
        )


def validate_data(df: pd.DataFrame, dataset_name: str = "data") -> None:
    """
    Run all validation checks.
    """
    if df.empty:
        raise ValueError(f"Input dataset is empty for {dataset_name}.")

    validate_required_columns(df, dataset_name)
    validate_missing_values(df, dataset_name)
    validate_numeric_values(df, dataset_name)
    validate_dates(df, dataset_name)