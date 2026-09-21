"""Day 15 Section 10 test matrix -- the 16-item edge case matrix required
by the spec, run against a throwaway sandbox."""
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

SANDBOX = Path("/tmp/visora_day15_full_matrix")
PASS, FAIL = [], []


def check(name, condition):
    if condition:
        PASS.append(name)
        print(f"PASS: {name}")
    else:
        FAIL.append(name)
        print(f"FAIL: {name}")


def upload_and_ingest(registry, ingestor, filename, path_or_df):
    if isinstance(path_or_df, pd.DataFrame):
        csv_path = SANDBOX / filename
        path_or_df.to_csv(csv_path, index=False)
    else:
        csv_path = path_or_df
    dataset_id = registry.register_upload(filename, csv_path)
    meta = registry.get_dataset(dataset_id)
    result = ingestor.ingest_csv(meta["stored_path"], meta["table_name"])
    registry.update_counts(dataset_id, result["row_count"], result["column_count"])
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

    # 1. numeric + categorical + date
    ds1, meta1, r1 = upload_and_ingest(registry, ingestor, "full.csv", pd.DataFrame({
        "Order Date": ["2024-01-01", "2024-02-01", "2024-03-01"],
        "Category": ["A", "B", "A"],
        "Sales": [10, 20, 30],
    }))
    check("1. numeric+categorical+date ingests cleanly", r1["ingested"] and r1["row_count"] == 3)

    # 2. no date column
    ds2, meta2, r2 = upload_and_ingest(registry, ingestor, "nodate.csv", pd.DataFrame({
        "Category": ["A", "B"], "Sales": [1, 2]
    }))
    check("2. no date column ingests cleanly", r2["ingested"])
    trends = TrendEngine(db_file); trends.connect()
    check("2. TrendEngine reports unsupported gracefully (no date)", trends.get_monthly_metrics(table_name=meta2["table_name"]) == [])

    # 3. no numeric columns
    ds3, meta3, r3 = upload_and_ingest(registry, ingestor, "nonumeric.csv", pd.DataFrame({
        "A": ["x", "y"], "B": ["p", "q"]
    }))
    check("3. no numeric columns ingests cleanly", r3["ingested"])
    metrics = MetricsEngine(db_file); metrics.connect()
    # SUM() over a TEXT column is valid SQLite (it just ignores non-numeric
    # text, yielding 0) -- the important thing is it never raises.
    try:
        text_sum = metrics.get_sum("A", table_name=meta3["table_name"])
        crashed = False
    except Exception:
        crashed = True
    check("3. MetricsEngine SUM on a non-numeric column does not crash", crashed is False)
    check("3. MetricsEngine on a genuinely missing column returns None", metrics.get_sum("NoSuchColumn", table_name=meta3["table_name"]) is None)

    # 4. no categorical columns
    ds4, meta4, r4 = upload_and_ingest(registry, ingestor, "nocat.csv", pd.DataFrame({
        "X": [1, 2, 3], "Y": [4.5, 5.5, 6.5]
    }))
    check("4. no categorical columns ingests cleanly", r4["ingested"] and r4["column_count"] == 2)

    # 5. missing values
    ds5, meta5, r5 = upload_and_ingest(registry, ingestor, "missing.csv", pd.DataFrame({
        "A": [1, None, 3], "B": ["x", "y", None]
    }))
    conn = sqlite3.connect(db_file)
    df5 = pd.read_sql_query(f'SELECT * FROM "{meta5["table_name"]}"', conn)
    check("5. missing values preserved as NULL (not corrupted)", df5["A"].isna().sum() == 1 and df5["B"].isna().sum() == 1)

    # 6. duplicate rows
    ds6, meta6, r6 = upload_and_ingest(registry, ingestor, "dupes.csv", pd.DataFrame({
        "A": [1, 1, 2], "B": ["x", "x", "y"]
    }))
    df6 = pd.read_sql_query(f'SELECT * FROM "{meta6["table_name"]}"', conn)
    check("6. duplicate rows not silently dropped", len(df6) == 3)

    # 7. header-only CSV
    header_only = SANDBOX / "header_only.csv"
    header_only.write_text("A,B,C\n")
    ds7, meta7, r7 = upload_and_ingest(registry, ingestor, "header_only.csv", header_only)
    check("7. header-only CSV does not crash and has 0 rows", r7["ingested"] and r7["row_count"] == 0)

    # 8. completely empty / zero-row dataset (zero-byte file)
    empty = SANDBOX / "empty.csv"
    empty.write_text("")
    ds8, meta8, r8 = upload_and_ingest(registry, ingestor, "empty.csv", empty)
    check("8. completely empty CSV handled gracefully (not ingested, clear reason)", not r8["ingested"] and bool(r8["reason"]))

    # 9. single-row dataset
    ds9, meta9, r9 = upload_and_ingest(registry, ingestor, "single.csv", pd.DataFrame({
        "A": [1], "B": ["x"]
    }))
    check("9. single-row dataset ingests cleanly", r9["ingested"] and r9["row_count"] == 1)

    # 10. high-cardinality categorical column
    ds10, meta10, r10 = upload_and_ingest(registry, ingestor, "highcard.csv", pd.DataFrame({
        "ID": [f"id_{i}" for i in range(500)], "Value": list(range(500))
    }))
    check("10. high-cardinality categorical column ingests cleanly", r10["ingested"] and r10["row_count"] == 500)

    # 11. same filename uploaded twice
    ds11a, meta11a, r11a = upload_and_ingest(registry, ingestor, "repeat.csv", pd.DataFrame({"A": [1]}))
    ds11b, meta11b, r11b = upload_and_ingest(registry, ingestor, "repeat.csv", pd.DataFrame({"A": [2, 3]}))
    check("11. same filename twice -> distinct dataset_ids", ds11a != ds11b)
    check("11. same filename twice -> distinct physical files", meta11a["stored_path"] != meta11b["stored_path"])
    df11a = pd.read_sql_query(f'SELECT * FROM "{meta11a["table_name"]}"', conn)
    df11b = pd.read_sql_query(f'SELECT * FROM "{meta11b["table_name"]}"', conn)
    check("11. same filename twice -> independent data (no overwrite)", len(df11a) == 1 and len(df11b) == 2)

    # 12. Dataset A -> B -> A (isolation, re-checked at full-matrix scale)
    df1_first = pd.read_sql_query(f'SELECT * FROM "{meta1["table_name"]}"', conn)
    # touch dataset B (2) then re-read A
    _ = pd.read_sql_query(f'SELECT * FROM "{meta2["table_name"]}"', conn)
    df1_again = pd.read_sql_query(f'SELECT * FROM "{meta1["table_name"]}"', conn)
    check("12. A -> B -> A: no cross-dataset contamination", df1_first.equals(df1_again))

    # 13. unsupported engine schema (contribution + anomaly on non-numeric schema)
    contributions = ContributionAnalyzer(db_file); contributions.connect()
    anomalies = AnomalyDetector(db_file); anomalies.connect()
    check("13. ContributionAnalyzer unsupported schema returns [] not crash",
          contributions.analyze("Category", "Sales", table_name=meta3["table_name"]) == [])
    check("13. AnomalyDetector unsupported schema returns [] not crash",
          anomalies.detect_z_score("Sales", table_name=meta3["table_name"]) == [])

    # 14. legacy sales workflow still functional
    pd.DataFrame({
        "Order Date": ["2024-01-01", "2024-02-01"],
        "Category": ["A", "B"],
        "Sales": [500, 700],
        "Profit": [50, 70],
    }).to_sql("sales", conn, if_exists="replace", index=False)
    check("14. legacy sales table default table_name still works", metrics.get_sum("Sales") == 1200)

    # 15. restart persistence (reopen registry against same db file)
    registry_restarted = DatasetRegistry(db_file=db_file, storage_dir=storage_dir)
    registry_restarted.connect()
    check("15. restart persistence: all datasets still listed", len(registry_restarted.list_datasets()) >= 12)

    # 16. physical file collision safety (uuid-based naming guarantees this structurally)
    all_meta = registry_restarted.list_datasets()
    stored_paths = [m["stored_path"] for m in all_meta]
    check("16. physical file collision safety: all stored paths unique", len(stored_paths) == len(set(stored_paths)))
    dataset_ids = [m["dataset_id"] for m in all_meta]
    check("16. dataset registry correctness: all dataset_ids unique", len(dataset_ids) == len(set(dataset_ids)))

    # SQL-injection-shaped column name safety (defense in depth, part of section 6)
    evil_col_df = pd.DataFrame({'A"; DROP TABLE sales; --': [1, 2], "B": [3, 4]})
    ds_evilcol, meta_evilcol, r_evilcol = upload_and_ingest(registry, ingestor, "evilcol.csv", evil_col_df)
    check("Section 6: malicious column name does not break ingestion", r_evilcol["ingested"])
    tables_after = pd.read_sql_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sales'", conn
    )
    check("Section 6: legacy sales table survives malicious column name", len(tables_after) == 1)

    conn.close()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED CHECKS:")
        for name in FAIL:
            print(" -", name)
        sys.exit(1)


if __name__ == "__main__":
    main()
