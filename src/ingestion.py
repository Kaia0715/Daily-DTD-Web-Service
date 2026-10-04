import warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    module="yfinance"
)

import requests
import pandas as pd
import yfinance as yf
import time
from io import BytesIO
from bs4 import BeautifulSoup

HKMA_MONTHLY_URL = (
    "https://api.hkma.gov.hk/public/"
    "market-data-and-statistics/"
    "monthly-statistical-bulletin/"
    "efbn/efbn-yield-daily"
)

HKMA_DAILY_BASE_URL = (
    "https://www.hkma.gov.hk/eng/"
    "data-publications-and-research/"
    "data-and-statistics/"
    "daily-monetary-statistics"
)


# ============================================================
# 1. Historical data from Monthly Statistical Bulletin
# ============================================================

def fetch_hkma_monthly_12m_rates(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Fetch historical 364-day EFB yields from the HKMA
    Monthly Statistical Bulletin API.

    Returns rates in percentage units:
        2.94 means 2.94%.
    """

    start_date = pd.Timestamp(start_date)
    end_date = pd.Timestamp(end_date)

    rows = []

    offset = 0
    page_size = 500

    while True:

        params = {
            "offset": offset,
            "pagesize": page_size,
        }

        response = requests.get(
            HKMA_MONTHLY_URL,
            params=params,
            timeout=(10, 10),
        )

        response.raise_for_status()

        records = response.json()["result"]["records"]

        if not records:
            break

        rows.extend(records)

        if len(records) < page_size:
            break

        offset += page_size

    if not rows:
        return pd.DataFrame(
            columns=["Date", "Risk_Free_Rate", "Rate_Source"]
        )

    df = pd.DataFrame(rows)

    df["Date"] = pd.to_datetime(
        df["end_of_day"]
    )

    df["Risk_Free_Rate"] = pd.to_numeric(
        df["efb_364d"],
        errors="coerce",
    )

    df = df.loc[
        (df["Date"] >= start_date)
        & (df["Date"] <= end_date),
        ["Date", "Risk_Free_Rate"],
    ].copy()

    df["Rate_Source"] = "HKMA_MSB_364D"

    return (
        df
        .dropna(subset=["Risk_Free_Rate"])
        .sort_values("Date")
        .drop_duplicates("Date")
        .reset_index(drop=True)
    )

# ============================================================
# 2. Latest data from HKMA Website download
# ============================================================
def build_hkma_daily_page_url(
    date: pd.Timestamp,
) -> str:

    date = pd.Timestamp(date)

    return (
        f"{HKMA_DAILY_BASE_URL}/"
        f"{date:%Y/%m}/"
        f"ms-{date:%Y%m%d}/"
    )

def find_indicative_pricing_excel(
    date: pd.Timestamp,
) -> str | None:
    """
    Find the HKMA Indicative Pricings Excel file
    for a given date.

    Expected filename:
        YYYYMMDD_INDICATIVE_PRICINGS.xlsx
    """

    date = pd.Timestamp(date)

    page_url = build_hkma_daily_page_url(date)

    response = requests.get(
        page_url,
        timeout=(10, 30),
    )

    # No page on weekends / holidays
    if response.status_code == 404:
        return None

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    expected_filename = (
        f"{date:%Y%m%d}_INDICATIVE_PRICINGS.xlsx"
    )

    for link in soup.find_all("a", href=True):

        href = link["href"]

        if href.lower().endswith(
            expected_filename.lower()
        ):
            return requests.compat.urljoin(
                page_url,
                href,
            )

    return None

def download_indicative_pricing_excel(
    date: pd.Timestamp,
) -> pd.DataFrame | None:

    excel_url = find_indicative_pricing_excel(date)

    if excel_url is None:
        return None

    response = requests.get(
        excel_url,
        timeout=(10, 30),
    )

    response.raise_for_status()

    return pd.read_excel(
        BytesIO(response.content),
        sheet_name="BILLS",
        header=None,
    )

def extract_12m_from_indicative_pricing(
    raw: pd.DataFrame,
    date: pd.Timestamp,
) -> pd.DataFrame:
    """
    Extract the 12-month EFB yield from an HKMA
    Indicative Pricing Excel file.

    The BILLS sheet is expected to have:
        Column B: Issue No.
        Column D: Maturity
        Column F: Yield (%)

    The longest-maturity bill is the last valid row
    and represents the 12-month benchmark EFB.
    """

    date = pd.Timestamp(date)

    # raw was loaded with header=None.
    #
    # Excel column F -> pandas column index 5
    yield_col = pd.to_numeric(
        raw.iloc[:, 5],
        errors="coerce",
    )

    # Find rows containing an actual numeric yield
    valid_rows = yield_col.notna()

    if not valid_rows.any():
        raise ValueError(
            f"No valid EFB yield found for {date.date()}"
        )

    # Last valid observation in column F
    last_idx = yield_col[valid_rows].index[-1]

    rate = yield_col.loc[last_idx]

    return pd.DataFrame({
        "Date": [date],
        "Risk_Free_Rate": [rate],
        "Rate_Source": ["HKMA_Indicative_Pricing"],
    })

def fetch_hkma_indicative_12m_rates(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:

    start_date = pd.Timestamp(start_date)
    end_date = pd.Timestamp(end_date)

    results = []

    for date in pd.date_range(
        start=start_date,
        end=end_date,
        freq="D",
    ):

        # Skip weekends immediately
        if date.weekday() >= 5:
            continue

        try:
            raw = download_indicative_pricing_excel(
                date
            )

            # Could be public holiday
            if raw is None:
                continue

            observation = (
                extract_12m_from_indicative_pricing(
                    raw,
                    date,
                )
            )

            results.append(observation)

        except requests.RequestException as e:
            raise RuntimeError(
                f"Failed to retrieve HKMA data "
                f"for {date.date()}"
            ) from e

        # Be polite to HKMA server
        time.sleep(0.2)

    if not results:
        return pd.DataFrame(
            columns=[
                "Date",
                "Risk_Free_Rate",
                "Rate_Source",
            ]
        )

    return (
        pd.concat(
            results,
            ignore_index=True,
        )
        .sort_values("Date")
        .reset_index(drop=True)
    )

def fetch_hkma_12m_rates(
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Retrieve HKMA 12-month EFB yields.

    Strategy
    --------
    1. Try the HKMA Monthly Statistical Bulletin API.

    2. If the API succeeds:
       - use the API historical series wherever available;
       - use HKMA Indicative Pricing Excel files for dates
         after the latest API observation.

    3. If the API is unavailable due to a transient server
       or network error (e.g. HTTP 502 or timeout):
       - retrieve the entire requested period from the
         HKMA Daily Monetary Statistics archive.

    Returns
    -------
    pd.DataFrame
        Date
        Risk_Free_Rate
        Rate_Source
    """

    start_date = pd.Timestamp(start_date)
    end_date = pd.Timestamp(end_date)

    if start_date > end_date:
        raise ValueError(
            "start_date must not be after end_date."
        )

    # ==================================================
    # 1. Try Monthly Statistical Bulletin API
    # ==================================================

    try:

        historical = fetch_hkma_monthly_12m_rates(
            start_date=start_date,
            end_date=end_date,
        )

    except (
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.HTTPError,
    ) as e:

        print(
            "HKMA Monthly Statistical Bulletin API "
            f"unavailable ({type(e).__name__})."
        )

        print(
            "Falling back to HKMA Daily Monetary "
            "Statistics archive for the full period."
        )

        # ==============================================
        # API unavailable:
        # use website for entire requested period
        # ==============================================

        return fetch_hkma_indicative_12m_rates(
            start_date=start_date,
            end_date=end_date,
        )

    # ==================================================
    # 2. API succeeded
    # ==================================================

    if historical.empty:

        archive_start = start_date

    else:

        latest_historical_date = (
            historical["Date"].max()
        )

        archive_start = (
            latest_historical_date
            + pd.Timedelta(days=1)
        )

    # ==================================================
    # 3. API already covers entire requested period
    # ==================================================

    if archive_start > end_date:
        return (
            historical
            .sort_values("Date")
            .reset_index(drop=True)
        )

    # ==================================================
    # 4. Fill recent gap using HKMA website
    # ==================================================

    recent = fetch_hkma_indicative_12m_rates(
        start_date=archive_start,
        end_date=end_date,
    )

    # ==================================================
    # 5. Combine
    # ==================================================

    combined = pd.concat(
        [historical, recent],
        ignore_index=True,
    )

    combined = (
        combined
        .sort_values("Date")
        .drop_duplicates(
            subset=["Date"],
            keep="first",
        )
        .reset_index(drop=True)
    )

    return combined

# daily market cap
def fetch_market_cap(
    ticker: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Fetch daily market capitalization for a date range.

    Market capitalization is calculated as:
        daily closing price × current shares outstanding

    Notes
    -----
    - The same current shares outstanding is applied to all
      historical dates in the requested period. (checked that it hasn't changed since 2026-01-01 till 2026-10-03)
    - yfinance's end date is exclusive, so one day is added
      internally.
    - Market capitalization is returned in HKD million.

    Returns
    -------
    pd.DataFrame
        Date
        CUR_MKT_CAP(HKD)
    """

    stock = yf.Ticker(ticker)

    start_date = pd.Timestamp(start_date)
    end_date = pd.Timestamp(end_date)

    if start_date > end_date:
        raise ValueError(
            "start_date must not be after end_date."
        )

    # yfinance end date is exclusive
    end_exclusive = (
        end_date + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")

    # ------------------------------------------
    # 1. Fetch daily closing prices
    # ------------------------------------------

    prices = stock.history(
        start=start_date.strftime("%Y-%m-%d"),
        end=end_exclusive,
        auto_adjust=False,
        actions=False,
    )

    if prices.empty:
        raise ValueError(
            f"No market data returned for {ticker}"
        )

    # ------------------------------------------
    # 2. Current shares outstanding
    # ------------------------------------------

    shares_outstanding = stock.fast_info["shares"]

    if shares_outstanding is None:
        raise ValueError(
            "Unable to retrieve shares outstanding."
        )

    # ------------------------------------------
    # 3. Calculate market cap
    # ------------------------------------------

    result = prices.reset_index()

    result["Date"] = (
        pd.to_datetime(result["Date"])
        .dt.tz_localize(None)
        .dt.normalize()
    )

    result["CUR_MKT_CAP(HKD)"] = (
        result["Close"]
        * shares_outstanding
        / 1_000_000
    )

    return (
        result[
            [
                "Date",
                "CUR_MKT_CAP(HKD)",
            ]
        ]
        .sort_values("Date")
        .reset_index(drop=True)
    )

if __name__ == "__main__":
    df1 = fetch_hkma_12m_rates(
        '2026-01-01',
        '2026-01-14',
    )

    print(df1)

    # df2 = fetch_market_cap(
    #     '3900.HK',
    #     '2026-08-15',
    #     '2026-09-15',
    # )
    
    # print(df2)