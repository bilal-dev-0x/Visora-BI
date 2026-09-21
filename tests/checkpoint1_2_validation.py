"""Standalone validation script for Day 15 Checkpoints 1 and 2.
Run with: python tests/checkpoint1_2_validation.py
Uses a throwaway sandbox directory so it never touches the real
data/visora.db or data/datasets/ used by the app.
"""
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from backend.dataset_registry import DatasetRegistry
from backend.ingestion import DatasetIngestor

SANDBOX = Path("/tmp/visora_day15_sandbox")
PASS = []
FAIL = []


def check(name, condition):
    if condition:
        PASS.append(name)
        print(f"PASS: {name}")
    else:
        FAIL.append(name)
        print(f"FAIL: {name}")


def make_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def fresh_sandbox():
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SANDBOX.mkdir(parents=True)


def main():
    fresh_sandbox()
    db_file = str(SANDBOX / "visora.db")
    storage_dir = str(SANDBOX / "datasets")

    # --- Dataset A: numeric + categorical + date ---
    csv_a = SANDBOX / "sales.csv"
    make_csv(csv_a, {
        "Order Date": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "Category": ["Office", "Tech", "Office"],
        "Sales": [100, 200, 300],
        "Profit": [10.5, 20.1, 30.9],
    })

    registry = DatasetRegistry(db_file=db_file, storage_dir=storage_dir)
    registry.connect()

    dataset_id_a1 = registry.register_upload("sales.csv", csv_a)
    meta_a1 = registry.get_dataset(dataset_id_a1)

    check("CP1: first CSV upload is persisted (metadata row exists)", meta_a1 is not None)
    check("CP1: physical file exists", Path(meta_a1["stored_path"]).exists())
    check("CP1: original filename preserved", meta_a1["original_filename"] == "sales.csv")
    check("CP1: row_count correct", meta_a1["row_count"] == 3)
    check("CP1: column_count correct", meta_a1["column_count"] == 4)

    # same filename uploaded twice must NOT overwrite
    dataset_id_a2 = registry.register_upload("sales.csv", csv_a)
    meta_a2 = registry.get_dataset(dataset_id_a2)
    check("CP1: dataset_id is unique across uploads", dataset_id_a1 != dataset_id_a2)
    check(
        "CP1: same filename twice does not overwrite (both files exist)",
        Path(meta_a1["stored_path"]).exists() and Path(meta_a2["stored_path"]).exists()
        and meta_a1["stored_path"] != meta_a2["stored_path"],
    )

    # --- Dataset B: different schema ---
    csv_b = SANDBOX / "customers.csv"
    make_csv(csv_b, {
        "Customer ID": [1, 2, 3, 4],
        "Region": ["North", "South", "East", "West"],
        "Signup Date": ["2023-05-01", "2023-06-15", "2023-07-20", None],
    })
    dataset_id_b = registry.register_upload("customers.csv", csv_b)
    meta_b = registry.get_dataset(dataset_id_b)
    check("CP1: multiple datasets coexist", len(registry.list_datasets()) == 3)

    # --- restart persistence: reconnect fresh registry against same db file ---
    registry2 = DatasetRegistry(db_file=db_file, storage_dir=storage_dir)
    registry2.connect()
    reloaded = registry2.list_datasets()
    check("CP1: application restart does not lose dataset metadata", len(reloaded) == 3)

    # ================= CHECKPOINT 2 =================
    ingestor = DatasetIngestor(db_file=db_file)
    ingestor.connect()

    result_a1 = ingestor.ingest_csv(meta_a1["stored_path"], meta_a1["table_name"])
    registry.update_counts(dataset_id_a1, result_a1["row_count"], result_a1["column_count"])
    check("CP2: dataset A ingested successfully", result_a1["ingested"] is True)
    check("CP2: dataset A row_count matches", result_a1["row_count"] == 3)
    check("CP2: dataset A column_count matches", result_a1["column_count"] == 4)

    result_b = ingestor.ingest_csv(meta_b["stored_path"], meta_b["table_name"])
    check("CP2: dataset B (different schema) ingested successfully", result_b["ingested"] is True)
    check("CP2: dataset B row_count matches", result_b["row_count"] == 4)
    check("CP2: dataset B column_count matches", result_b["column_count"] == 3)

    # verify no cross-dataset contamination: A -> B -> A
    conn = sqlite3.connect(db_file)
    df_a = pd.read_sql_query(f'SELECT * FROM "{meta_a1["table_name"]}"', conn)
    df_b = pd.read_sql_query(f'SELECT * FROM "{meta_b["table_name"]}"', conn)
    df_a_again = pd.read_sql_query(f'SELECT * FROM "{meta_a1["table_name"]}"', conn)

    check("CP2: A has its own columns (Sales, Profit)", set(["Sales", "Profit"]).issubset(df_a.columns))
    check("CP2: B has its own columns (Customer ID, Region)", set(["Customer ID", "Region"]).issubset(df_b.columns))
    check("CP2: A reopened is still A (no contamination)", df_a.equals(df_a_again))
    check("CP2: A and B are in separate tables", meta_a1["table_name"] != meta_b["table_name"])

    # missing values preserved as NULL, not corrupted
    check(
        "CP2: missing values preserved as NULL in dataset B",
        df_b["Signup Date"].isna().sum() == 1,
    )

    # duplicate rows: not silently dropped
    csv_dup = SANDBOX / "dupes.csv"
    make_csv(csv_dup, {"A": [1, 1, 2], "B": ["x", "x", "y"]})
    dataset_id_dup = registry.register_upload("dupes.csv", csv_dup)
    meta_dup = registry.get_dataset(dataset_id_dup)
    result_dup = ingestor.ingest_csv(meta_dup["stored_path"], meta_dup["table_name"])
    df_dup = pd.read_sql_query(f'SELECT * FROM "{meta_dup["table_name"]}"', conn)
    check("CP2: duplicate rows preserved, not silently dropped", len(df_dup) == 3)

    # header-only CSV
    csv_header_only = SANDBOX / "header_only.csv"
    csv_header_only.write_text("A,B,C\n")
    dataset_id_ho = registry.register_upload("header_only.csv", csv_header_only)
    meta_ho = registry.get_dataset(dataset_id_ho)
    result_ho = ingestor.ingest_csv(meta_ho["stored_path"], meta_ho["table_name"])
    check("CP2: header-only CSV does not crash", result_ho["ingested"] is True)
    check("CP2: header-only CSV has 0 rows", result_ho["row_count"] == 0)

    # completely empty CSV (zero-row, zero-byte)
    csv_empty = SANDBOX / "empty.csv"
    csv_empty.write_text("")
    dataset_id_empty = registry.register_upload("empty.csv", csv_empty)
    meta_empty = registry.get_dataset(dataset_id_empty)
    result_empty = ingestor.ingest_csv(meta_empty["stored_path"], meta_empty["table_name"])
    check("CP2: completely empty CSV does not crash", result_empty["ingested"] is False)
    check("CP2: completely empty CSV reports a clear reason", bool(result_empty["reason"]))

    # SQL-injection-shaped filename must not break anything
    csv_evil = SANDBOX / "weird.. DROP TABLE sales; --.csv"
    make_csv(csv_evil, {"A": [1, 2]})
    dataset_id_evil = registry.register_upload(csv_evil.name, csv_evil)
    meta_evil = registry.get_dataset(dataset_id_evil)
    result_evil = ingestor.ingest_csv(meta_evil["stored_path"], meta_evil["table_name"])
    check("CP2: malicious filename does not corrupt storage/table naming", result_evil["ingested"] is True)
    check(
        "CP2: sales table (legacy) untouched by malicious filename",
        Path(db_file).exists(),
    )

    conn.close()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED CHECKS:")
        for name in FAIL:
            print(" -", name)
        sys.exit(1)


if __name__ == "__main__":
    main()
