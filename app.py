import json
from pathlib import Path
from datetime import date, time
import datetime

import pandas as pd


# ==============================
# Configuration
# ==============================

DATA_FILE = "data/sales_data.csv"
REPORT_FILE = "reports/sales_summary.json"
TEXT_FILE = "reports/"


# ==============================
# Load Dataset
# ==============================

df = pd.read_csv(DATA_FILE)

df["Order Date"] = pd.to_datetime(df["Order Date"])


# ==============================
# Basic Dataset Information
# ==============================

columns = df.columns.tolist()
numeric_columns = df.select_dtypes(include=["number"]).columns.tolist()


# ==============================
# Quality Checks
# ==============================

total_missing_values = int(df.isnull().sum().sum())
columns_with_missing_values = df.columns[df.isnull().any()].tolist()

duplicate_rows = int(df.duplicated().sum())
completely_empty_rows = int(df.isnull().all(axis=1).sum())


# ==============================
# Column Health
# ==============================

def get_column_health(df):
    column_details = []

    for column in df.columns:
        missing_count = int(df[column].isnull().sum())
        unique_count = int(df[column].nunique())

        column_details.append({
            "Column": column,
            "Missing": missing_count,
            "Unique": unique_count,
            "Type": str(df[column].dtype),
            "Missing Percentage": round(
                (missing_count / len(df)) * 100,
                2
            )
        })

    return column_details


# ==============================
# Numeric Statistics
# ==============================

def get_numeric_statistics(df, numeric_columns):
    numeric_details = []

    for column in numeric_columns:
        numeric_details.append({
            "Column": column,
            "Mean": float(df[column].mean()),
            "Median": float(df[column].median()),
            "Standard Deviation": float(df[column].std()),
            "Min": float(df[column].min()),
            "Max": float(df[column].max())
        })

    return numeric_details


# ==============================
# Other Dataset Details
# ==============================

product_names = df["Product Name"].dropna().unique().tolist()
categories = df["Category"].dropna().unique().tolist()
regions = df["Region"].dropna().unique().tolist()

earliest_date = str(df["Order Date"].min().date())
latest_date = str(df["Order Date"].max().date())


# ==============================
# Build Health Report
# ==============================

summary = {
    date.today().isoformat(): {
        "Dataset Summary": {
            "Total Rows": int(len(df)),
            "Total Columns": int(len(df.columns))
        },

        "Quality Checks": {
            "Total Missing Values": total_missing_values,
            "Duplicate Rows": duplicate_rows,
            "Rows with All Missing Values": completely_empty_rows
        },

        "Columns Health": {
            "Columns": columns,
            "Columns with Missing Values": columns_with_missing_values,
            "Column Details": get_column_health(df)
        },

        "Numeric Column Statistics": {
            "Columns": numeric_columns,
            "Column Details": get_numeric_statistics(
                df,
                numeric_columns
            )
        },

        "Issues Detected": {
            "Missing Values Detected": total_missing_values > 0,
            "Duplicate Rows Detected": duplicate_rows > 0,
            "Rows with All Missing Values Detected": completely_empty_rows > 0
        },

        "Other Details": {
            "Unique Product Names": product_names,
            "Unique Categories": categories,
            "Unique Regions": regions,
            "Earliest Date": earliest_date,
            "Latest Date": latest_date
        }}
}


# ==============================
# Export Report
# ==============================

report_path = Path(REPORT_FILE)
report_path.parent.mkdir(parents=True, exist_ok=True)

tnd = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
text_file_path = Path(TEXT_FILE) / f"sales_summary-{tnd}.txt"
text_file_path.parent.mkdir(parents=True, exist_ok=True)

with open(report_path, "w", encoding="utf-8") as file:
    json.dump(summary, file, indent=4)

with open(report_path, "r", encoding="utf-8") as file:
    loaded_summary = json.load(file)

with open(text_file_path, "w", encoding="utf-8") as file:
    file.write(json.dumps(loaded_summary, indent=4))

print(f"\nHealth report generated successfully:")
print(report_path)
