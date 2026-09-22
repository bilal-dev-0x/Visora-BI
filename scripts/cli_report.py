"""
Legacy terminal-only report script.

This is the exact execution flow that used to live at the top level of
app.py (running the analytical engines directly against
data/sales_data.csv and printing results to stdout). It has been moved
here so it no longer runs as part of `streamlit run app.py` -- app.py
is now the Streamlit dashboard entry point.

Run it directly, from the repository root:
    python scripts/cli_report.py
"""

import sys
from pathlib import Path

# Allow running this script directly (python scripts/cli_report.py)
# from any working directory by putting the repo root on sys.path,
# the same way frontend/dashboard.py already does.
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.analyzer import DataAnalyzer
from backend.database import DataSetManager
from backend.metrics import MetricsEngine
from backend.trends import TrendEngine
from backend.contribution import ContributionAnalyzer
from backend.anomaly import AnomalyDetector

DATA_FILE = "data/sales_data.csv"
REPORT_FILE = "reports/sales_summary.json"
TEXT_FILE = "reports/"

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

db_df = database.get_data()
print("\nDatabase data:")
print(db_df.head())
print("\nDatabase rows:", len(db_df))
print("Cleaned rows:", len(analyzer.cleaned_df))
print("\nDatabase schema:")
for column in database.get_table_info():
    print(column)

metrics = MetricsEngine("data/visora.db")
metrics.connect()
print("\nTotal Sales:", metrics.get_sum("Sales"))
print("Average Profit:", metrics.get_average("Profit"))
group_by = metrics.get_grouped_metric("Category", "Sales", "SUM")
print(group_by)

trends = TrendEngine("data/visora.db")
trends.connect()
monthly_data = trends.get_monthly_metrics()
print("\nMonthly Metrics:")
for row in monthly_data:
    print(row)

growth_monthly = trends.calculate_growth(monthly_data)
print("\nMonthly Growth:")
for growth in growth_monthly:
    print(growth[0], "--->", growth[3])

moving_data = trends.calculate_moving_average(monthly_data)
print("\nMoving Average:")
for row in moving_data:
    print(row)

contributions = ContributionAnalyzer("data/visora.db")
contributions.connect()
sales_contribution = contributions.analyze("Category", "Sales")
print("\nSales Contribution by Category:")
for row in sales_contribution:
    print(row)

anomalies = AnomalyDetector("data/visora.db")
anomalies.connect()
sales_anomalies = anomalies.detect_z_score("Sales")
print("\nSales Anomalies:")
for row in sales_anomalies:
    print(row)
