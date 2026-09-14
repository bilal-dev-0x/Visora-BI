import json
from pathlib import Path
from datetime import date
import datetime

import sqlite3
import pandas as pd


DATA_FILE = "data/sales_data.csv"
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

        self.product_names = []
        self.categories = []
        self.regions = []

        self.earliest_date = None
        self.latest_date = None

        self.summary = {}

        self.cleaned_df = None

    def load_data(self):
        self.df = pd.read_csv(self.data_file)
        self.df["Order Date"] = pd.to_datetime(
            self.df["Order Date"]
        )

    def get_basic_information(self):
        self.columns = self.df.columns.tolist()

        self.numeric_columns = (
            self.df
            .select_dtypes(include=["number"])
            .columns
            .tolist()
        )

    def get_quality_checks(self):
        self.total_missing_values = int(
            self.df.isnull().sum().sum()
        )

        self.columns_with_missing_values = (
            self.df.columns[
                self.df.isnull().any()
            ].tolist()
        )

        self.duplicate_rows = int(
            self.df.duplicated().sum()
        )

        self.completely_empty_rows = int(
            self.df.isnull().all(axis=1).sum()
        )

    def get_column_health(self):
        column_details = []

        for column in self.df.columns:
            missing_count = int(
                self.df[column].isnull().sum()
            )

            unique_count = int(
                self.df[column].nunique()
            )

            column_details.append({
                "Column": column,
                "Missing": missing_count,
                "Unique": unique_count,
                "Type": str(self.df[column].dtype),
                "Missing Percentage": round(
                    (missing_count / len(self.df)) * 100,
                    2
                )
            })
        return column_details

    def get_numeric_statistics(self):
        numeric_details = []

        for column in self.numeric_columns:
            numeric_details.append({
                "Column": column,
                "Mean": float(
                    self.df[column].mean()
                ),
                "Median": float(
                    self.df[column].median()
                ),
                "Standard Deviation": float(
                    self.df[column].std()
                ),
                "Min": float(
                    self.df[column].min()
                ),
                "Max": float(
                    self.df[column].max()
                )
            })

        return numeric_details

    def get_other_details(self):
        self.product_names = (
            self.df["Product Name"]
            .dropna()
            .unique()
            .tolist()
        )

        self.categories = (
            self.df["Category"]
            .dropna()
            .unique()
            .tolist()
        )

        self.regions = (
            self.df["Region"]
            .dropna()
            .unique()
            .tolist()
        )

        self.earliest_date = str(
            self.df["Order Date"].min().date()
        )

        self.latest_date = str(
            self.df["Order Date"].max().date()
        )

    def build_report(self):
        self.summary = {
            date.today().isoformat(): {
                "Dataset Summary": {
                    "Total Rows": int(len(self.df)),
                    "Total Columns": int(len(self.df.columns))
                },

                "Quality Checks": {
                    "Total Missing Values":
                        self.total_missing_values,
                    "Duplicate Rows":
                        self.duplicate_rows,
                    "Rows with All Missing Values":
                        self.completely_empty_rows
                },

                "Columns Health": {
                    "Columns": self.columns,
                    "Columns with Missing Values":
                        self.columns_with_missing_values,
                    "Column Details":
                        self.get_column_health()
                },

                "Numeric Column Statistics": {
                    "Columns": self.numeric_columns,
                    "Column Details":
                        self.get_numeric_statistics()
                },

                "Issues Detected": {
                    "Missing Values Detected":
                        self.total_missing_values > 0,
                    "Duplicate Rows Detected":
                        self.duplicate_rows > 0,
                    "Rows with All Missing Values Detected":
                        self.completely_empty_rows > 0
                },

                "Other Details": {
                    "Unique Product Names":
                        self.product_names,
                    "Unique Categories":
                        self.categories,
                    "Unique Regions":
                        self.regions,
                    "Earliest Date":
                        self.earliest_date,
                    "Latest Date":
                        self.latest_date
                }
            }
        }

    def export_report(self):
        report_path = Path(REPORT_FILE)
        report_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        timestamp = datetime.datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        text_file_path = (
            Path(TEXT_FILE)
            / f"sales_summary-{timestamp}.txt"
        )

        text_file_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(
            report_path,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                self.summary,
                file,
                indent=4
            )

        with open(
            report_path,
            "r",
            encoding="utf-8"
        ) as file:
            loaded_summary = json.load(file)

        with open(
            text_file_path,
            "w",
            encoding="utf-8"
        ) as file:
            file.write(
                json.dumps(
                    loaded_summary,
                    indent=4
                )
            )

        print("\nHealth report generated successfully:")
        print(report_path)

    def clean_data(self):
        df = self.df.copy()

        for column in df.columns:
            if df[column].isnull().any():

                if pd.api.types.is_numeric_dtype(df[column]):
                    df[column] = df[column].fillna(
                        df[column].median()
                    )

                elif pd.api.types.is_datetime64_any_dtype(df[column]):
                    df = df.dropna(subset=[column])

                else:
                    df[column] = df[column].fillna("Unknown")
        self.cleaned_df = df

class DataSetManager:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)

    def create_tables(self, df):
        cursor = self.conn.cursor()
        columns = []

        for column in df.columns:
            dtype = str(df[column].dtype)
            if "int" in dtype:
                sql_type = "INTEGER"
            elif "float" in dtype:
                sql_type = "REAL"
            else:
                sql_type = "TEXT"

            column_definition = f'"{column}" {sql_type}'
            columns.append(column_definition)

        columns_sql = ", ".join(columns)
        sql_createtable_query = f"""CREATE TABLE IF NOT EXISTS sales(
                                    {columns_sql}
                                    )"""

        cursor.execute(sql_createtable_query)
        self.conn.commit()

    def insert_data(self, df):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM sales")
        self.conn.commit()

        df.to_sql(
            "sales",
            self.conn,
            if_exists="append",
            index=False
        )

    def get_data(self):
        query = "SELECT * FROM sales"
        return pd.read_sql_query(query, self.conn)

    def get_table_info(self):
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(sales)")
        return cursor.fetchall()

class MetricsEngine:

    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)

    def get_sum(self, column):
        query = f'SELECT SUM("{column}") FROM sales'
        cursor = self.conn.cursor()
        cursor.execute(query)
        result = cursor.fetchone()
        return result[0]

    def get_average(self, column):
        query = f'SELECT AVG("{column}") FROM sales'
        cursor = self.conn.cursor()
        cursor.execute(query)
        result = cursor.fetchone()
        return result[0]

    def get_grouped_metric(self, group_column, metric_column, aggregation):

        allowed_aggregations = ["SUM", "AVG", "MIN", "MAX", "COUNT"]

        if aggregation not in allowed_aggregations:
            raise ValueError("Unsupported aggregation")

        query = f'''
            SELECT "{group_column}", {aggregation}("{metric_column}")
            FROM sales
            GROUP BY "{group_column}"
        '''

        cursor = self.conn.cursor()
        cursor.execute(query)

        return cursor.fetchall()

class TrendEngine:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)

    def get_monthly_metrics(self):
        query = '''
            SELECT
                strftime('%Y-%m', "Order Date") AS month,
                SUM("Sales") AS total_sales,
                SUM("Profit") AS total_profit
            FROM sales
            GROUP BY month
            ORDER BY month
        '''

        cursor = self.conn.cursor()
        cursor.execute(query)

        return cursor.fetchall()

    def calculate_growth(self, monthly_data):
        growth_data = []
        previous_sales = None

        for month, sales, profit in monthly_data:
            if previous_sales is None:
                growth = None
            else:
                growth = round(((sales - previous_sales) / previous_sales) * 100, 2)

            growth_data.append((month, sales, profit, growth))
            previous_sales = sales

        return growth_data

    def calculate_moving_average(self, monthly_data, window=3):
        moving_data = []
        sales_window = []

        for month, sales, profit in monthly_data:
            sales_window.append(sales)

            if len(sales_window) < window:
                moving_average = None
            else:
                moving_average = round(
                    sum(sales_window) / window,
                    2
                )

                sales_window.pop(0)

            moving_data.append(
                (month, sales, moving_average)
            )

        return moving_data

analyzer = DataAnalyzer(DATA_FILE)

analyzer.load_data()
analyzer.get_basic_information()
analyzer.get_quality_checks()
analyzer.get_other_details()
analyzer.build_report()
analyzer.export_report()
analyzer.clean_data()

database = DataSetManager("data/visora.db")
database.connect()
database.create_tables(analyzer.cleaned_df)
database.insert_data(analyzer.cleaned_df)

database.insert_data(analyzer.cleaned_df)

db_df = database.get_data()

print("\nDatabase data:")
print(db_df.head())

print("\nDatabase rows:", len(db_df))
print("Cleaned rows:", len(analyzer.cleaned_df))

print("\nDatabase schema:")
for column in database.get_table_info(): print(column)

metrics = MetricsEngine("data/visora.db")
metrics.connect()

total_sales = metrics.get_sum("Sales")

print("\nTotal Sales:", total_sales)

average_profit = metrics.get_average("Profit")

print("Average Profit:", average_profit)

group_by = metrics.get_grouped_metric(
    "Category",
    "Sales",
    "SUM"
)

print(group_by)

trends = TrendEngine("data/visora.db")
trends.connect()

monthly_data = trends.get_monthly_metrics()

print("\nMonthly Metrics:")

for row in monthly_data: print(row)

growth_monthly = trends.calculate_growth(monthly_data)

print("\nMonthly Growth:")
for growth in growth_monthly: print(growth[0], "--->", growth[3])

moving_data = trends.calculate_moving_average(monthly_data)

print("\nMoving Average:")

for row in moving_data:
    print(row)