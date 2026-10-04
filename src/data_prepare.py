from __future__ import annotations

import pandas as pd

from src.ingestion import (
    fetch_hkma_12m_rates,
    fetch_market_cap,
)
from src.validation import validate_data


COMPANY_ID = 23286
TICKER = "3900.HK"


FINANCIAL_COLUMNS = [
    "BS_CUR_LIAB(HKD)",
    "BS_LT_BORROW(HKD)",
    "BS_TOT_LIAB2(HKD)",
    "BS_TOT_ASSET(HKD)",
]


def load_historical_inputs(path: str) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        dtype={"Comp_no": str},
    )

    df["Date"] = pd.to_datetime(
        df["Date"].astype(str),
        format="%Y%m%d",
    )

    return df.sort_values("Date")

def load_financial_updates(path: str) -> pd.DataFrame:
    """
    Load financial statement updates.

    Expected columns:
        Comp_no
        Available_Date
        BS_CUR_LIAB(HKD)
        BS_LT_BORROW(HKD)
        BS_TOT_LIAB2(HKD)
        BS_TOT_ASSET(HKD)
    """

    financials = pd.read_csv(
        path,
        dtype={"Comp_no": str},
    )

    financials["Available_Date"] = pd.to_datetime(
        financials["Available_Date"].astype(str),
        format="%Y%m%d")
    
    return financials

def prepare_incremental_inputs(
    historical_path: str,
    financial_updates_path: str,
    cutoff_date: str,
) -> pd.DataFrame:

    # -------------------------------------------------
    # 0. Load historical inputs
    # -------------------------------------------------

    historical = load_historical_inputs(
        historical_path
    )

    last_historical_date = historical["Date"].max()

    start_date = (
        last_historical_date + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")

    print(
        f"Updating from {start_date} "
        f"through {cutoff_date}"
    )

    # -------------------------------------------------
    # 1. Market data
    # -------------------------------------------------

    market = fetch_market_cap(
        ticker=TICKER,
        start_date=start_date,
        end_date=cutoff_date,
    )

    # Market observations define trading days.
    new = market[
        ["Date", "CUR_MKT_CAP(HKD)"]
    ].copy()

    # -------------------------------------------------
    # 2. Risk-free rate
    # -------------------------------------------------

    rates = fetch_hkma_12m_rates(
        start_date=start_date,
        end_date=cutoff_date,
    )

    new = new.merge(
        rates,
        on="Date",
        how="left",
        validate="one_to_one",
    )

    new["Risk_Free_Rate"] = (
        new["Risk_Free_Rate"].ffill()
    )

    # If first new trading day has no rate,
    # use the latest historical rate.
    if (
        not new.empty
        and pd.isna(new.iloc[0]["Risk_Free_Rate"])
    ):
        last_rate = (
            historical["Risk_Free_Rate"]
            .dropna()
            .iloc[-1]
        )

        new["Risk_Free_Rate"] = (
            new["Risk_Free_Rate"].fillna(last_rate)
        )

    # -------------------------------------------------
    # 3. Financial statements
    # -------------------------------------------------

    financials = load_financial_updates(
        financial_updates_path
    )

    # Keep only this company.
    financials = financials[
        financials["Comp_no"] == str(COMPANY_ID)
    ].copy()

    financials = financials.sort_values(
        "Available_Date"
    )

    # Company ID must exist before merge_asof.
    new["Comp_no"] = str(COMPANY_ID)

    # For each trading day, use the latest financial
    # statement that was available on or before that day.
    new = pd.merge_asof(
        new.sort_values("Date"),
        financials[
            [
                "Comp_no",
                "Available_Date",
                *FINANCIAL_COLUMNS,
            ]
        ],
        left_on="Date",
        right_on="Available_Date",
        by="Comp_no",
        direction="backward",
    )

    new = new.drop(
        columns=["Available_Date"]
    )

    # -------------------------------------------------
    # 5. Match original column order
    # -------------------------------------------------

    new = new[
        [
            "Comp_no",
            "Date",
            "CUR_MKT_CAP(HKD)",
            "BS_CUR_LIAB(HKD)",
            "BS_LT_BORROW(HKD)",
            "BS_TOT_LIAB2(HKD)",
            "BS_TOT_ASSET(HKD)",
            "Risk_Free_Rate"
        ]
    ]

    # -------------------------------------------------
    # 6. Validation
    # -------------------------------------------------

    validate_data(new, 'new data')

    return new

def update_dataset(
    historical_path: str,
    financial_updates_path: str,
    output_path: str,
    cutoff_date: str,
) -> pd.DataFrame:

    historical = load_historical_inputs(
        historical_path
    )

    new = prepare_incremental_inputs(
        historical_path=historical_path,
        financial_updates_path=financial_updates_path,
        cutoff_date=cutoff_date,
    )

    # Preserve historical records.
    #
    # Only dates after the supplied historical cutoff
    # are appended.
    last_historical_date = historical["Date"].max()

    new = new[
        new["Date"] > last_historical_date
    ].copy()

    combined = pd.concat(
        [historical, new],
        ignore_index=True,
    )

    combined = (
        combined
        .sort_values(["Comp_no", "Date"])
        .drop_duplicates(
            subset=["Comp_no", "Date"],
            keep="first",
        )
        .reset_index(drop=True)
    )

    validate_data(combined, 'combined data')

    combined["Date"] = (
        combined["Date"]
        .dt.strftime("%Y%m%d")
        .astype(int)
    )

    combined.to_csv(
        output_path,
        index=False,
    )

    return combined

if __name__ == "__main__":
    df = update_dataset(
        historical_path="data/raw/historical_inputs.csv",
        financial_updates_path="data/raw/financial_updates.csv",
        output_path="data/processed/dtd_inputs.csv",
        cutoff_date="2026-01-14",
    )
