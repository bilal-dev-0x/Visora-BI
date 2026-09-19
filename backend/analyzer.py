import json
from pathlib import Path
from datetime import date
import datetime
import pandas as pd

REPORT_FILE = "reports/sales_summary.json"
TEXT_FILE = "reports/"

class DataAnalyzer:

    def __init__(self, data_file):
        self.data_file = data_file
        self.df = None
        self.columns = []
        self.numeric_columns = []
        self.total_missing_values = 0
        self.columns_with_missing_values = []
        self.duplicate_rows = 0
        self.completely_empty_rows = 0
        self.date_columns = []
        self.categorical_columns = []
        self.summary = {}
        self.cleaned_df = None

    def load_data(self):
        self.df = pd.read_csv(self.data_file)
        if "Order Date" in self.df.columns:
            self.df["Order Date"] = pd.to_datetime(self.df["Order Date"])

    def get_basic_information(self):
        self.columns = self.df.columns.tolist()
        self.numeric_columns = self.df.select_dtypes(include=["number"]).columns.tolist()

    def get_quality_checks(self):
        self.total_missing_values = int(self.df.isnull().sum().sum())
        self.columns_with_missing_values = self.df.columns[self.df.isnull().any()].tolist()
        self.duplicate_rows = int(self.df.duplicated().sum())
        self.completely_empty_rows = int(self.df.isnull().all(axis=1).sum())

    def get_column_health(self):
        column_details = []
        for column in self.df.columns:
            missing_count = int(self.df[column].isnull().sum())
            unique_count = int(self.df[column].nunique())
            column_details.append({
                "Column": column,
                "Missing": missing_count,
                "Unique": unique_count,
                "Type": str(self.df[column].dtype),
                "Missing Percentage": round((missing_count / len(self.df)) * 100, 2)
            })
        return column_details

    def get_numeric_statistics(self):
        numeric_details = []
        for column in self.numeric_columns:
            numeric_details.append({
                "Column": column,
                "Mean": float(self.df[column].mean()),
                "Median": float(self.df[column].median()),
                "Standard Deviation": float(self.df[column].std()),
                "Min": float(self.df[column].min()),
                "Max": float(self.df[column].max())
            })
        return numeric_details

    def get_other_details(self):
        self.date_columns = self.df.select_dtypes(
            include=["datetime"]
        ).columns.tolist()

        self.categorical_columns = self.df.select_dtypes(
            include=["object", "category"]
        ).columns.tolist()

    def build_report(self):
        self.summary = {
            date.today().isoformat(): {
                "Dataset Summary": {
                    "Total Rows": int(len(self.df)),
                    "Total Columns": int(len(self.df.columns))
                },
                "Quality Checks": {
                    "Total Missing Values": self.total_missing_values,
                    "Duplicate Rows": self.duplicate_rows,
                    "Rows with All Missing Values": self.completely_empty_rows
                },
                "Columns Health": {
                    "Columns": self.columns,
                    "Columns with Missing Values": self.columns_with_missing_values,
                    "Column Details": self.get_column_health()
                },
                "Numeric Column Statistics": {
                    "Columns": self.numeric_columns,
                    "Column Details": self.get_numeric_statistics()
                },
                "Issues Detected": {
                    "Missing Values Detected": self.total_missing_values > 0,
                    "Duplicate Rows Detected": self.duplicate_rows > 0,
                    "Rows with All Missing Values Detected": self.completely_empty_rows > 0
                },
                "Other Details": {
                    "Date Columns": self.date_columns,
                    "Categorical Columns": self.categorical_columns
                }
            }
        }

    def export_report(self):
        report_path = Path(REPORT_FILE)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        text_file_path = Path(TEXT_FILE) / f"sales_summary-{timestamp}.txt"
        text_file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, "w", encoding="utf-8") as file:
            json.dump(self.summary, file, indent=4)

        with open(report_path, "r", encoding="utf-8") as file:
            loaded_summary = json.load(file)

        with open(text_file_path, "w", encoding="utf-8") as file:
            file.write(json.dumps(loaded_summary, indent=4))

        print("\nHealth report generated successfully:")
        print(report_path)

    def clean_data(self):
        df = self.df.copy()
        for column in df.columns:
            if df[column].isnull().any():
                if pd.api.types.is_numeric_dtype(df[column]):
                    df[column] = df[column].fillna(df[column].median())
                elif pd.api.types.is_datetime64_any_dtype(df[column]):
                    df = df.dropna(subset=[column])
                else:
                    df[column] = df[column].fillna("Unknown")
        self.cleaned_df = df