"""Standalone validation script for Day 15 Checkpoint 3 (analytical engines)."""
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from backend.dataset_registry import DatasetRegistry
from backend.ingestion import DatasetIngestor
from backend.metrics import MetricsEngine
from backend.trends import TrendEngine
from backend.contribution import ContributionAnalyzer
from backend.anomaly import AnomalyDetector

SANDBOX = Path("/tmp/visora_day15_sandbox_cp3")
PASS, FAIL = [], []


def check(name, condition):
    if condition:
        PASS.append(name)
        print(f"PASS: {name}")
    else:
        FAIL.append(name)
        print(f"FAIL: {name}")


def make_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def main():
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SANDBOX.mkdir(parents=True)

    db_file = str(SANDBOX / "visora.db")
    storage_dir = str(SANDBOX / "datasets")

    registry = DatasetRegistry(db_file=db_file, storage_dir=storage_dir)
    registry.connect()
    ingestor = DatasetIngestor(db_file=db_file)
    ingestor.connect()

    # --- Dataset A: business schema (sales-like) ---
    csv_a = SANDBOX / "a.csv"
    make_csv(csv_a, {
        "Order Date": [
            "2024-01-01", "2024-01-15", "2024-02-01", "2024-02-15",
            "2024-03-01", "2024-03-15", "2024-04-01", "2024-04-15",
        ],
        "Category": ["Office", "Tech", "Office", "Tech", "Office", "Tech", "Office", "Tech"],
        "Sales": [100, 200, 150, 400, 120, 180, 160, 190],
        "Profit": [10, 20, 15, 18, 12, 22, 3000, 19],  # 3000 is a deliberate outlier
    })
    ds_a = registry.register_upload("a.csv", csv_a)
    meta_a = registry.get_dataset(ds_a)
    ingestor.ingest_csv(meta_a["stored_path"], meta_a["table_name"])
    table_a = meta_a["table_name"]

    # --- Dataset B: unrelated schema (no business fields) ---
    csv_b = SANDBOX / "b.csv"
    make_csv(csv_b, {
        "Employee": ["Alice", "Bob", "Carol"],
        "Department": ["Eng", "Eng", "Sales"],
        "Salary": [90000, 95000, 70000],
    })
    ds_b = registry.register_upload("b.csv", csv_b)
    meta_b = registry.get_dataset(ds_b)
    ingestor.ingest_csv(meta_b["stored_path"], meta_b["table_name"])
    table_b = meta_b["table_name"]

    metrics = MetricsEngine(db_file)
    metrics.connect()
    trends = TrendEngine(db_file)
    trends.connect()
    contributions = ContributionAnalyzer(db_file)
    contributions.connect()
    anomalies = AnomalyDetector(db_file)
    anomalies.connect()

    # Dataset A produces A results
    check("CP3: MetricsEngine sum on A", metrics.get_sum("Sales", table_name=table_a) == 1500)
    a_monthly = trends.get_monthly_metrics(table_name=table_a)
    check("CP3: TrendEngine works on A (has Order Date/Sales)", len(a_monthly) == 4)
    a_contrib = contributions.analyze("Category", "Sales", table_name=table_a)
    check("CP3: ContributionAnalyzer works on A", len(a_contrib) == 2)
    a_anomalies = anomalies.detect_z_score("Profit", table_name=table_a)
    check("CP3: AnomalyDetector finds the Profit outlier in A", any(row[1] == 3000 for row in a_anomalies))

    # Dataset B produces B results / graceful "unsupported" for business-specific engines
    check("CP3: MetricsEngine sum on B (different column)", metrics.get_sum("Salary", table_name=table_b) == 255000)
    check("CP3: MetricsEngine sum on B missing column returns None, no crash", metrics.get_sum("Sales", table_name=table_b) is None)
    b_monthly = trends.get_monthly_metrics(table_name=table_b)
    check("CP3: TrendEngine on B (no Order Date/Sales) returns [] not crash", b_monthly == [])
    supported_b, reason_b = trends.check_support(table_name=table_b)
    check("CP3: TrendEngine explains why B is unsupported", supported_b is False and "Order Date" in reason_b)
    b_contrib = contributions.analyze("Department", "Salary", table_name=table_b)
    check("CP3: ContributionAnalyzer works on B's own schema", len(b_contrib) == 2)
    b_contrib_bad = contributions.analyze("Category", "Sales", table_name=table_b)
    check("CP3: ContributionAnalyzer on B with A's fields returns [] not crash", b_contrib_bad == [])

    # Switching A -> B -> A: no stale results
    a_monthly_again = trends.get_monthly_metrics(table_name=table_a)
    check("CP3: switching A->B->A: A results identical and not stale", a_monthly == a_monthly_again)
    check("CP3: A and B use different tables (isolation)", table_a != table_b)

    # Unsupported analyses never crash (explicit try/except sanity net)
    try:
        anomalies.detect_z_score("Department", table_name=table_b)  # non-numeric text column
        crashed = False
    except Exception:
        crashed = True
    check("CP3: AnomalyDetector on non-numeric column does not crash", crashed is False)

    # Legacy `sales` table behavior remains functional
    legacy_conn = sqlite3.connect(db_file)
    pd.DataFrame({
        "Order Date": ["2024-01-01", "2024-02-01"],
        "Category": ["Office", "Tech"],
        "Sales": [500, 700],
        "Profit": [50, 70],
    }).to_sql("sales", legacy_conn, if_exists="replace", index=False)
    legacy_conn.close()

    legacy_sum = metrics.get_sum("Sales")  # no table_name -> defaults to "sales"
    check("CP3: legacy sales workflow (default table_name) still works", legacy_sum == 1200)
    legacy_monthly = trends.get_monthly_metrics()
    check("CP3: legacy TrendEngine default still works", len(legacy_monthly) == 2)
    legacy_growth = trends.calculate_growth(legacy_monthly)
    check("CP3: legacy calculate_growth algorithm unchanged", legacy_growth[1][3] == 40.0)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED CHECKS:")
        for name in FAIL:
            print(" -", name)
        sys.exit(1)


if __name__ == "__main__":
    main()
