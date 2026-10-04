from pathlib import Path

import pandas as pd
import streamlit as st

from src.data_prepare import update_dataset
from src.dtd import load_parameters, compute_dtd

# ============================================================
# Paths
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

HISTORICAL_PATH = RAW_DIR / "historical_inputs.csv"
FINANCIAL_UPDATES_PATH = RAW_DIR / "financial_updates.csv"
PARAMETER_PATH = RAW_DIR / "parameters.csv"

DTD_INPUT_PATH = PROCESSED_DIR / "dtd_inputs.csv"
DTD_OUTPUT_PATH = PROCESSED_DIR / "dtd_output.csv"


# ============================================================
# Pipeline
# ============================================================

def run_pipeline(
    cutoff_date: str,
    mode: str,
    status=None,
) -> pd.DataFrame:

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 1. Choose base dataset
    if status:
        status.write("1/4 Selecting base dataset...")

    if mode == "historical":

        base_path = HISTORICAL_PATH

        if status:
            status.write(
                "Building from supplied historical inputs."
            )

    elif mode == "incremental":

        if not DTD_INPUT_PATH.exists():
            raise FileNotFoundError(
                "No processed DTD input dataset exists. "
                "Please build from historical data first."
            )

        base_path = DTD_INPUT_PATH

        if status:
            status.write(
                "Running incremental update from existing "
                "processed inputs."
            )

    else:
        raise ValueError(
            f"Unknown pipeline mode: {mode}"
        )

    # 2. Prepare inputs
    # Determine update date range
    base_df = pd.read_csv(base_path)

    base_df["Date"] = pd.to_datetime(
        base_df["Date"].astype(str)
    )

    last_existing_date = base_df["Date"].max()

    update_start_date = (
        last_existing_date + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")

    if status:
        status.write(
            f"2/4 Updating from {update_start_date} "
            f"through {cutoff_date}..."
        )

    prepared = update_dataset(
        historical_path=str(base_path),
        financial_updates_path=str(
            FINANCIAL_UPDATES_PATH
        ),
        output_path=str(DTD_INPUT_PATH),
        cutoff_date=cutoff_date,
    )

    # 3. Load parameters
    if status:
        status.write("3/4 Loading DTD parameters...")

    parameters = load_parameters(
        str(PARAMETER_PATH)
    )

    # 4. Compute DTD
    if status:
        status.write("4/4 Computing asset value and DTD...")

    result = compute_dtd(
        inputs=prepared,
        params=parameters,
    )

    result.to_csv(
        DTD_OUTPUT_PATH,
        index=False,
    )

    if status:
        status.write("Saving DTD results...")

    return result


# ============================================================
# Streamlit UI
# ============================================================

st.set_page_config(
    page_title="Greentown Daily DTD Service",
    page_icon="📊",
    layout="wide",
)

st.title("Greentown Daily DTD Service")

st.caption(
    "Greentown China Holdings Limited (03900.HK) | "
    "Company ID: 23286"
)

st.write(
    """
    This service updates daily model inputs, applies the supplied
    asset-volatility and liability-weight parameters, solves the
    implied asset value (AV), and calculates Distance-to-Default
    (DTD).
    """
)


# ============================================================
# Sidebar
# ============================================================

st.sidebar.header("Pipeline Controls")

cutoff_date = st.sidebar.date_input(
    "Cutoff date",
)

st.sidebar.subheader("Run Mode")

historical_button = st.sidebar.button(
    "Build from Raw (provided by CRI)",
    type="primary",
    width="stretch",
)

incremental_button = st.sidebar.button(
    "Build from Processed",
    width="stretch",
)


# ============================================================
# Run pipeline
# ============================================================

if historical_button:
    run_mode = "historical"

elif incremental_button:
    run_mode = "incremental"

else:
    run_mode = None


if run_mode is not None:

    cutoff_str = cutoff_date.strftime("%Y-%m-%d")

    try:

        if run_mode == "historical":
            mode_label = "historical build"
        else:
            mode_label = "incremental update"

        status = st.status(
            f"Running {mode_label} through {cutoff_str}...",
            expanded=True,
        )

        result = run_pipeline(
            cutoff_date=cutoff_str,
            mode=run_mode,
            status=status,
        )

        status.update(
            label=f"Pipeline completed through {cutoff_str}",
            state="complete",
            expanded=False,
        )

        st.success(
            f"Pipeline completed through {cutoff_str}."
        )

        # ----------------------------------------------------
        # Summary
        # ----------------------------------------------------

        successful = (
            result["calculation_status"]
            == "success"
        ).sum()

        failed = (
            result["calculation_status"]
            == "failed"
        ).sum()

        carried_forward = (
            result["parameter_carried_forward"]
            .fillna(False)
            .sum()
        )

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Observations",
            len(result),
        )

        col2.metric(
            "Successful",
            successful,
        )

        col3.metric(
            "Failed",
            failed,
        )

        col4.metric(
            "Parameter Carry-Forward",
            carried_forward,
        )

        # ----------------------------------------------------
        # Latest DTD
        # ----------------------------------------------------

        successful_result = result[
            result["calculation_status"]
            == "success"
        ].copy()

        if not successful_result.empty:

            latest = (
                successful_result
                .sort_values("Date")
                .iloc[-1]
            )

            st.subheader("Latest Result")

            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Date",
                pd.to_datetime(
                    latest["Date"]
                ).strftime("%Y-%m-%d"),
            )

            col2.metric(
                "Asset Value (HKD mn)",
                f'{latest["asset_value"]:,.2f}',
            )

            col3.metric(
                "DTD",
                f'{latest["DTD"]:.4f}',
            )

        # ----------------------------------------------------
        # DTD chart
        # ----------------------------------------------------

        st.subheader("DTD History")

        if not successful_result.empty:

            chart_data = (
                successful_result[
                    ["Date", "DTD"]
                ]
                .copy()
                .sort_values("Date")
                .set_index("Date")
            )

            st.line_chart(chart_data)

        # ----------------------------------------------------
        # Results table
        # ----------------------------------------------------

        st.subheader("Calculation Results")

        display_columns = [
            "Comp_no",
            "Date",
            "CUR_MKT_CAP(HKD)",
            "Risk_Free_Rate",
            "sigma",
            "delta",
            "default_threshold",
            "asset_value",
            "DTD",
            "parameter_date",
            "parameter_carried_forward",
            "calculation_status",
        ]

        display_columns = [
            column
            for column in display_columns
            if column in result.columns
        ]

        st.dataframe(
            result[display_columns]
            .sort_values(
                "Date",
                ascending=False,
            ),
            width="stretch",
            hide_index=True,
        )

        # ----------------------------------------------------
        # Failed calculations
        # ----------------------------------------------------

        failed_rows = result[
            result["calculation_status"]
            == "failed"
        ]

        if not failed_rows.empty:

            st.warning(
                f"{len(failed_rows)} calculation(s) failed."
            )

            st.dataframe(
                failed_rows[
                    [
                        "Date",
                        "calculation_status",
                        "error_message",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )

        # ----------------------------------------------------
        # Download
        # ----------------------------------------------------

        csv = result.to_csv(
            index=False
        ).encode("utf-8")

        st.download_button(
            label="Download DTD Results",
            data=csv,
            file_name="dtd_output.csv",
            mime="text/csv",
        )

    except Exception as exc:

        st.error(
            "Pipeline failed."
        )

        st.exception(exc)


# ============================================================
# Existing results
# ============================================================

elif DTD_OUTPUT_PATH.exists():

    st.info(
        "Showing the most recently saved pipeline results. "
        "Use the sidebar to run an update."
    )

    existing = pd.read_csv(
        DTD_OUTPUT_PATH
    )

    st.dataframe(
        existing.tail(20),
        width="stretch",
        hide_index=True,
    )

else:

    st.info(
        "No computed DTD output is available yet. "
        "Choose a cutoff date and run the pipeline."
    )