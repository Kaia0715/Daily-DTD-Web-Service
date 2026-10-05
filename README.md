# Greentown China DTD Calculation

This project extends the historical Distance-to-Default (DTD) dataset
for Greentown China Holdings Limited and provides a Streamlit interface
for running the update and calculation pipeline.

## Project Structure

AIDF/
├── app.py                         # Streamlit application entry point
├── run_app.bat                    # Windows launcher for the Streamlit application
├── README.md                      
├── requirements.txt               
├── documentation.docx   
├── documentation.pdf            
│
├── data/
│   ├── raw/
│   │   ├── historical_inputs.csv          # Historical input data provided by CRI
│   │   ├── full_historical_dtd_output.csv # Historical CRI DTD reference output
│   │   ├── parameters.csv                 
│   │   └── financial_updates.csv          # Manually prepared financial-statement updates
│   │
│   └── processed/
│       ├── dtd_inputs.csv                 # Combined inputs used for DTD calculation
│       ├── dtd_output.csv                 # Calculated DTD results
│       ├── comparison.csv                 # Comparison result with CRI DTD
│       └── financial_statement_check.xlsx # Manual check for analysis
│
├── src/
│   ├── ingestion.py               # External data retrieval
│   ├── data_prepare.py            # Input preparation and incremental updates
│   ├── validation.py              # Input data validation
│   └── dtd.py                     # Asset-value and DTD calculation
│
└── notebooks/
    └── comparison.ipynb           # DTD comparison and diagnostic analysis

## Installation

Install the required Python packages:

pip install -r requirements.txt

## Running the Application

After installing the required dependencies, double-click:

`run_app.bat`

Alternatively, from the project root directory run:

`python -m streamlit run app.py`

The Streamlit application allows the user to select a cutoff date,
and select whether to update from raw(first time) or processed data(daily increment).

For daily updates, it is recommended to run the application after 4:30 p.m. Hong Kong time to allow sufficient time for the latest Hong Kong stock-market closing data to become available through Yahoo Finance.