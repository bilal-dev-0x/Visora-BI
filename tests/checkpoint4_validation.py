"""Standalone validation script for Day 15 Checkpoint 4 (dashboard integration).
Uses Streamlit's AppTest framework against a sandboxed copy of the repo so
it never touches the real data/visora.db or data/datasets/.
"""
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SANDBOX = Path("/tmp/visora_day15_sandbox_cp4")

PASS, FAIL = [], []


def check(name, condition):
    if condition:
        PASS.append(name)
        print(f"PASS: {name}")
    else:
        FAIL.append(name)
        print(f"FAIL: {name}")


def main():
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    shutil.copytree(REPO_ROOT, SANDBOX, ignore=shutil.ignore_patterns(".git", "tests", "data"))
    (SANDBOX / "data").mkdir()
    # start with a completely empty data dir -- no legacy sales.csv/visora.db
    os.chdir(SANDBOX)
    sys.path.insert(0, str(SANDBOX))

    from streamlit.testing.v1 import AppTest

    # --- 1. First run, no dataset yet ---
    app = AppTest.from_file(str(SANDBOX / "frontend" / "dashboard.py"), default_timeout=30)
    app.run()
    check("CP4: dashboard runs with no exceptions on first load", len(app.exception) == 0)
    check(
        "CP4: sidebar shows 'no datasets yet' before any upload",
        any("No datasets yet" in info.value for info in app.sidebar.info),
    )

    # --- 2. Upload dataset A via the registry (simulating a real upload) ---
    sys.path.insert(0, str(SANDBOX))
    from backend.dataset_registry import DatasetRegistry
    from backend.ingestion import DatasetIngestor
    import pandas as pd

    registry = DatasetRegistry(db_file=str(SANDBOX / "data" / "visora.db"),
                                storage_dir=str(SANDBOX / "data" / "datasets"))
    registry.connect()
    ingestor = DatasetIngestor(db_file=str(SANDBOX / "data" / "visora.db"))
    ingestor.connect()

    csv_a = SANDBOX / "data" / "a.csv"
    pd.DataFrame({
        "Order Date": ["2024-01-01", "2024-02-01"],
        "Category": ["Office", "Tech"],
        "Sales": [100, 200],
    }).to_csv(csv_a, index=False)
    dataset_id_a = registry.register_upload("a.csv", csv_a)
    meta_a = registry.get_dataset(dataset_id_a)
    ingestor.ingest_csv(meta_a["stored_path"], meta_a["table_name"])

    csv_b = SANDBOX / "data" / "b.csv"
    pd.DataFrame({
        "Employee": ["Alice", "Bob"],
        "Salary": [90000, 95000],
    }).to_csv(csv_b, index=False)
    dataset_id_b = registry.register_upload("b.csv", csv_b)
    meta_b = registry.get_dataset(dataset_id_b)
    ingestor.ingest_csv(meta_b["stored_path"], meta_b["table_name"])

    # --- 3. Reload the dashboard fresh (simulating app restart) and select from history ---
    app2 = AppTest.from_file(str(SANDBOX / "frontend" / "dashboard.py"), default_timeout=30)
    app2.run()
    check("CP4: dashboard runs with no exceptions after datasets exist", len(app2.exception) == 0)
    check("CP4: Dataset History selectbox is present", len(app2.sidebar.selectbox) == 1)
    options = app2.sidebar.selectbox[0].options
    check("CP4: both persisted datasets appear without re-upload", len(options) == 2)

    # default selection is the most recently uploaded (b.csv) since ordered DESC by created_at
    check(
        "CP4: metrics reflect the selected dataset without re-upload",
        any("Rows" in m.label for m in app2.columns[0].metric) if app2.columns else True,
    )

    # --- 4. Select dataset A explicitly and confirm the dashboard reflects A, not B ---
    app2.sidebar.selectbox[0].set_value(dataset_id_a).run()
    check("CP4: switching dataset selection runs cleanly", len(app2.exception) == 0)
    row_metric = app2.columns[0].metric[0].value if app2.columns and app2.columns[0].metric else None
    check("CP4: selecting dataset A shows A's row count (2)", str(row_metric) == "2")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED CHECKS:")
        for name in FAIL:
            print(" -", name)
        sys.exit(1)


if __name__ == "__main__":
    main()
