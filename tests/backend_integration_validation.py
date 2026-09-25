"""Focused validation for backend/capabilities.py (schema-driven
capability detection) and backend/analysis_context.py (the unified
analytical context orchestrator). Mirrors the style/sandboxing approach
of tests/checkpoint3_validation.py -- never touches the real
data/visora.db or data/datasets/.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from backend.analysis_context import analyze_dataset
from backend.capabilities import CapabilityDetector
from backend.dataset_registry import DatasetRegistry
from backend.ingestion import DatasetIngestor

SANDBOX = Path("/tmp/visora_capabilities_sandbox")
PASS, FAIL = [], []


def check(name, condition):
    if condition:
        PASS.append(name)
        print(f"PASS: {name}")
    else:
        FAIL.append(name)
        print(f"FAIL: {name}")


def upload_and_ingest(registry, ingestor, filename, df):
    csv_path = SANDBOX / filename
    df.to_csv(csv_path, index=False)
    dataset_id = registry.register_upload(filename, csv_path)
    meta = registry.get_dataset(dataset_id)
    result = ingestor.ingest_csv(meta["stored_path"], meta["table_name"])
    registry.update_counts(dataset_id, result["row_count"], result["column_count"])
    meta = registry.get_dataset(dataset_id)
    return dataset_id, meta, result


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

    detector = CapabilityDetector(db_file)
    detector.connect()

    # --- Dataset A: sales-like (Order Date, Category, Sales, Profit) ---
    _, meta_a, _ = upload_and_ingest(registry, ingestor, "a.csv", pd.DataFrame({
        "Order Date": [
            "2024-01-01", "2024-01-15", "2024-02-01", "2024-02-15",
            "2024-03-01", "2024-03-15", "2024-04-01", "2024-04-15",
        ],
        "Category": ["Office", "Tech", "Office", "Tech", "Office", "Tech", "Office", "Tech"],
        "Sales": [100, 200, 150, 400, 120, 180, 160, 190],
        "Profit": [10, 20, 15, 18, 12, 22, 3000, 19],
    }))
    cap_a = detector.detect(meta_a["table_name"])
    check("A: numeric detection works (Sales, Profit)", set(cap_a["numeric_columns"]) == {"Sales", "Profit"})
    check("A: categorical detection works (Category)", cap_a["categorical_columns"] == ["Category"])
    check("A: date detection works (Order Date)", cap_a["date_columns"] == ["Order Date"])
    check("A: metrics available", cap_a["metrics"]["available"] is True)
    check("A: trends available (has Order Date + Sales)", cap_a["trends"]["available"] is True)
    check("A: contribution available", cap_a["contribution"]["available"] is True)
    check("A: anomaly available", cap_a["anomaly"]["available"] is True)

    context_a = analyze_dataset(meta_a["table_name"], meta_a["stored_path"], db_file=db_file, dataset_metadata=meta_a)
    check("A: full context is JSON serializable", bool(json.dumps(context_a)))
    check("A: context metrics available with Sales/Profit sums", context_a["metrics"]["available"] and "Sales" in context_a["metrics"]["data"])
    check("A: context trends available with 4 months", context_a["trends"]["available"] and len(context_a["trends"]["data"]["monthly"]) == 4)
    check("A: context contribution available", context_a["contribution"]["available"])
    check(
        "A: context anomalies flag the Profit outlier",
        context_a["anomalies"]["available"] and any(row["value"] == 3000 for row in context_a["anomalies"]["data"].get("Profit", []))
    )

    # --- Dataset B: generic (Employee, Department, Salary) ---
    _, meta_b, _ = upload_and_ingest(registry, ingestor, "b.csv", pd.DataFrame({
        "Employee": ["Alice", "Bob", "Carol", "Dave"],
        "Department": ["Eng", "Eng", "Sales", "Sales"],
        "Salary": [90000, 95000, 70000, 72000],
    }))
    cap_b = detector.detect(meta_b["table_name"])
    check("B: numeric/categorical detection works", cap_b["numeric_columns"] == ["Salary"] and set(cap_b["categorical_columns"]) == {"Employee", "Department"})
    check("B: generic metrics available with Salary", cap_b["metrics"]["available"] is True)
    check("B: specialized trend analysis unsupported", cap_b["trends"]["available"] is False and "Order Date" in cap_b["trends"]["reason"])
    check(
        "B: contribution available with Department + Salary",
        cap_b["contribution"]["available"] and cap_b["contribution"]["dimension"] == "Department" and cap_b["contribution"]["measure"] == "Salary"
    )
    check("B: anomaly detection available on Salary", cap_b["anomaly"]["available"] is True)

    context_b = analyze_dataset(meta_b["table_name"], meta_b["stored_path"], db_file=db_file, dataset_metadata=meta_b)
    check("B: full context is JSON serializable", bool(json.dumps(context_b)))
    check("B: context trends cleanly unsupported with a reason", context_b["trends"]["available"] is False and bool(context_b["trends"]["reason"]))

    # --- Dataset C: no numeric columns ---
    _, meta_c, _ = upload_and_ingest(registry, ingestor, "c.csv", pd.DataFrame({
        "Name": ["Alice", "Bob"],
        "City": ["NYC", "LA"],
    }))
    cap_c = detector.detect(meta_c["table_name"])
    check("C: no crash on no-numeric schema", cap_c["exists"] is True)
    check("C: metrics unavailable with clear reason", cap_c["metrics"]["available"] is False and bool(cap_c["metrics"]["reason"]))
    check("C: anomaly unavailable with clear reason", cap_c["anomaly"]["available"] is False and bool(cap_c["anomaly"]["reason"]))

    context_c = analyze_dataset(meta_c["table_name"], meta_c["stored_path"], db_file=db_file, dataset_metadata=meta_c)
    check("C: full context is JSON serializable", bool(json.dumps(context_c)))
    check("C: context metrics cleanly unsupported", context_c["metrics"] == {"available": False, "data": None, "reason": cap_c["metrics"]["reason"]})

    # --- Dataset D: constant numeric values ---
    _, meta_d, _ = upload_and_ingest(registry, ingestor, "d.csv", pd.DataFrame({
        "Category": ["A", "B", "C", "D"],
        "Value": [50, 50, 50, 50],
    }))
    cap_d = detector.detect(meta_d["table_name"])
    check("D: anomaly capability still reports available (numeric col, enough rows)", cap_d["anomaly"]["available"] is True)

    context_d = analyze_dataset(meta_d["table_name"], meta_d["stored_path"], db_file=db_file, dataset_metadata=meta_d)
    check("D: full context is JSON serializable", bool(json.dumps(context_d)))
    check(
        "D: anomaly detection safely reports no anomalies for a constant column, not a crash",
        context_d["anomalies"]["available"] and context_d["anomalies"]["data"]["Value"] == []
    )

    # --- Dataset E: missing values ---
    _, meta_e, _ = upload_and_ingest(registry, ingestor, "e.csv", pd.DataFrame({
        "Category": ["A", "B", None, "D"],
        "Value": [10, None, 30, 40],
    }))
    context_e = analyze_dataset(meta_e["table_name"], meta_e["stored_path"], db_file=db_file, dataset_metadata=meta_e)
    check("E: context remains JSON serializable with missing values", bool(json.dumps(context_e)))
    check("E: no NaN/Infinity leaked into the serialized context", "NaN" not in json.dumps(context_e) and "Infinity" not in json.dumps(context_e))

    # --- Table that was never ingested: never crashes ---
    cap_missing = detector.detect("ds_doesnotexist00000000000000000")
    check("Missing table: capability detection reports unavailable, not a crash", cap_missing["exists"] is False)
    context_missing = analyze_dataset("ds_doesnotexist00000000000000000", meta_e["stored_path"], db_file=db_file)
    check("Missing table: analyze_dataset still returns a JSON-serializable context", bool(json.dumps(context_missing)))

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED CHECKS:")
        for name in FAIL:
            print(" -", name)
        sys.exit(1)


if __name__ == "__main__":
    main()
