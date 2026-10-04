import numpy as np
import pandas as pd

from scipy.optimize import brentq
from scipy.stats import norm


TAU = 1.0


def load_parameters(path: str) -> pd.DataFrame:
    """
    Load supplied DTD parameters.

    Expected columns:
        COMPANY_ID
        REAL_DTD_DATE
        DTD_SIGMA
        DTD_WEIGHT
    """

    params = pd.read_csv(
        path,
        dtype={
            "COMPANY_ID": int,
            "REAL_DTD_DATE": str,
        },
    )

    params["REAL_DTD_DATE"] = pd.to_datetime(
        params["REAL_DTD_DATE"],
        format="%Y%m%d",
    )

    return params

def attach_parameters(
    inputs: pd.DataFrame,
    params: pd.DataFrame,
) -> pd.DataFrame:
    """
    Match sigma and delta to each calculation date.

    For dates beyond parameter coverage, carry forward
    the latest available parameter values.

    Adds:
        sigma
        delta
        parameter_date
        parameter_carried_forward
    """

    df = inputs.copy()
    p = params.copy()

    df["Comp_no"] = df["Comp_no"].astype("int64")
    p["COMPANY_ID"] = p["COMPANY_ID"].astype("int64")

    df["Date"] = pd.to_datetime(
        df["Date"].astype(str),
        format="%Y%m%d",
    )

    df = df.sort_values(["Comp_no", "Date"])
    p = p.sort_values(["COMPANY_ID", "REAL_DTD_DATE"])

    result = pd.merge_asof(
        df,
        p,
        left_on="Date",
        right_on="REAL_DTD_DATE",
        left_by="Comp_no",
        right_by="COMPANY_ID",
        direction="backward",
    )

    result["parameter_carried_forward"] = (
        result["Date"] > result["REAL_DTD_DATE"]
    )

    result = result.rename(
        columns={
            "DTD_SIGMA": "sigma",
            "DTD_WEIGHT": "delta",
            "REAL_DTD_DATE": "parameter_date",
        }
    )

    return result

def calculate_default_threshold(
    current_liabilities: float,
    long_term_borrowing: float,
    total_liabilities: float,
    delta: float,
) -> float:
    """
    Calculate default threshold L.

    OL = TL - CL - LTB
    L  = CL + 0.5 * LTB + delta * OL
    """

    other_liabilities = (
        total_liabilities
        - current_liabilities
        - long_term_borrowing
    )

    default_threshold = (
        current_liabilities
        + 0.5 * long_term_borrowing
        + delta * other_liabilities
    )

    return default_threshold

def solve_asset_value(
    equity_value: float,
    default_threshold: float,
    risk_free_rate: float,
    sigma: float,
    tau: float = TAU,
) -> float:
    """
    Solve implied asset value V from the Merton equity equation.

    E = V*N(d+) - L*exp(-r*tau)*N(d-)
    """

    def equity_difference(asset_value: float) -> float:

        d_plus = (
            np.log(asset_value / default_threshold)
            + (
                risk_free_rate
                + 0.5 * sigma**2
            ) * tau
        ) / (
            sigma * np.sqrt(tau)
        )

        d_minus = (
            d_plus
            - sigma * np.sqrt(tau)
        )

        implied_equity = (
            asset_value * norm.cdf(d_plus)
            - default_threshold
            * np.exp(-risk_free_rate * tau)
            * norm.cdf(d_minus)
        )

        return implied_equity - equity_value

    # Asset value must be positive.
    lower = 1e-8

    # Start with a reasonable upper bound.
    upper = (
        equity_value
        + default_threshold
    ) * 2

    # Expand upper bound until the root is bracketed.
    while equity_difference(upper) < 0:
        upper *= 2

        if upper > 1e12:
            raise ValueError(
                "Unable to bracket asset value solution."
            )

    asset_value = brentq(
        equity_difference,
        lower,
        upper,
        maxiter=100,
        xtol=1e-10,
    )

    return asset_value

def calculate_dtd(
    asset_value: float,
    default_threshold: float,
    sigma: float,
    tau: float = TAU,
) -> float:
    """
    Calculate Distance-to-Default.

    DTD = ln(V / L) / (sigma * sqrt(tau))
    """

    return (
        np.log(asset_value / default_threshold)
        / (sigma * np.sqrt(tau))
    )

def compute_dtd(
    inputs: pd.DataFrame,
    params: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute daily AV and DTD using supplied sigma and delta.
    """

    df = attach_parameters(
        inputs,
        params,
    )

    results = []

    for _, row in df.iterrows():

        try:
            # -----------------------------------------
            # 1. Convert risk-free rate
            # -----------------------------------------

            risk_free_rate = (
                row["Risk_Free_Rate"] / 100
            )

            # -----------------------------------------
            # 2. Default threshold
            # -----------------------------------------

            default_threshold = (
                calculate_default_threshold(
                    current_liabilities=row[
                        "BS_CUR_LIAB(HKD)"
                    ],
                    long_term_borrowing=row[
                        "BS_LT_BORROW(HKD)"
                    ],
                    total_liabilities=row[
                        "BS_TOT_LIAB2(HKD)"
                    ],
                    delta=row["delta"],
                )
            )

            # -----------------------------------------
            # 3. Solve implied asset value
            # -----------------------------------------

            asset_value = solve_asset_value(
                equity_value=row[
                    "CUR_MKT_CAP(HKD)"
                ],
                default_threshold=default_threshold,
                risk_free_rate=risk_free_rate,
                sigma=row["sigma"],
            )

            # -----------------------------------------
            # 4. Calculate DTD
            # -----------------------------------------

            dtd = calculate_dtd(
                asset_value=asset_value,
                default_threshold=default_threshold,
                sigma=row["sigma"],
            )

            calculation_status = "success"
            error_message = None

        except Exception as e:

            default_threshold = np.nan
            asset_value = np.nan
            dtd = np.nan

            calculation_status = "failed"
            error_message = str(e)

        results.append(
            {
                **row.to_dict(),
                "default_threshold": default_threshold,
                "asset_value": asset_value,
                "DTD": dtd,
                "calculation_status": calculation_status,
                "error_message": error_message,
            }
        )

    return pd.DataFrame(results)

if __name__ == "__main__":
    params = load_parameters(
    "data/raw/parameters.csv"
    )
    combined_data = pd.read_csv(
        "data/processed/dtd_inputs.csv")
    dtd_output = compute_dtd(
        inputs=combined_data,
        params=params,
    )
    print(dtd_output)