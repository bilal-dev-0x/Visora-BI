"""Focused validation for the Analytical Intelligence layer.

Covers the generalized MetricsEngine, TrendEngine, ContributionAnalyzer,
AnomalyDetector, plus their exposure through backend/capabilities.py and
backend/analysis_context.py, across the required Dataset A-H matrix.

Mirrors the style/sandboxing approach of
tests/backend_integration_validation.py -- never touches the real
data/visora.db or data/datasets/.

Run with: python tests/analytical_intelligence_validation.py
"""
import json
import shutil
import sys
from pathlib import Path
from tempfile import gettempdir

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from backend.analysis_context import analyze_dataset
from backend.anomaly import AnomalyDetector
from backend.capabilities import CapabilityDetector
from backend.contribution import ContributionAnalyzer
from backend.dataset_registry import DatasetRegistry
from backend.ingestion import DatasetIngestor
from backend.metrics import MetricsEngine
from backend.trends import TrendEngine

SANDBOX = Path(gettempdir()) / "visora_analytical_intelligence_sandbox"
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


def is_json_safe(obj):
    """True if obj serializes with strict JSON (allow_nan=False) --
    i.e. it contains no NaN/Infinity/-Infinity anywhere. Plain
    json.dumps() would happily emit those (Python's json module allows
    them by default); allow_nan=False is what actually enforces valid,
    interoperable JSON here."""
    try:
        json.dumps(obj, allow_nan=False)
        return True
    except ValueError:
        return False


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

    metrics = MetricsEngine(db_file); metrics.connect()
    trends = TrendEngine(db_file); trends.connect()
    contributions = ContributionAnalyzer(db_file); contributions.connect()
    anomalies = AnomalyDetector(db_file); anomalies.connect()

    # =====================================================================
    # Dataset A -- business dataset: Date, Product, Segment, Location,
    # Units, Revenue (non-"Order Date"/"Sales" business schema)
    # =====================================================================
    _, meta_a, _ = upload_and_ingest(registry, ingestor, "a.csv", pd.DataFrame({
        "Date": [
            "2024-01-05", "2024-01-20", "2024-02-05", "2024-02-20",
            "2024-03-05", "2024-03-20", "2024-04-05", "2024-04-20",
        ],
        "Product": ["Widget", "Gadget", "Widget", "Gadget", "Widget", "Gadget", "Widget", "Gadget"],
        "Segment": ["Retail", "Wholesale", "Retail", "Wholesale", "Retail", "Wholesale", "Retail", "Wholesale"],
        "Location": ["North", "South", "North", "South", "North", "South", "North", "South"],
        "Units": [10, 20, 15, 40, 12, 18, 16, 19],
        "Revenue": [1000, 2000, 1500, 4000, 1200, 9000, 1600, 1900],  # 9000 is a deliberate outlier
    }))
    table_a = meta_a["table_name"]

    # -- generic metrics (no hardcoded dependency on "Sales") --
    check("A: MetricsEngine SUM(Revenue)", metrics.get_sum("Revenue", table_name=table_a) == 22200)
    check("A: MetricsEngine AVG(Units)", round(metrics.get_average("Units", table_name=table_a), 2) == 18.75)
    check("A: MetricsEngine MIN(Revenue)", metrics.get_min("Revenue", table_name=table_a) == 1000)
    check("A: MetricsEngine MAX(Revenue)", metrics.get_max("Revenue", table_name=table_a) == 9000)
    check("A: MetricsEngine COUNT(Revenue)", metrics.get_count("Revenue", table_name=table_a) == 8)
    check(
        "A: MetricsEngine grouped Product -> Revenue",
        dict(metrics.get_grouped_metric("Product", "Revenue", "SUM", table_name=table_a))
        == {"Widget": 5300, "Gadget": 16900}
    )
    check(
        "A: MetricsEngine grouped Location -> Units",
        dict(metrics.get_grouped_metric("Location", "Units", "SUM", table_name=table_a))
        == {"North": 53, "South": 97}
    )
    check(
        "A: MetricsEngine grouped Product -> Revenue (AVG)",
        dict(metrics.get_grouped_metric("Product", "Revenue", "AVG", table_name=table_a))
        == {"Widget": 5300 / 4, "Gadget": 16900 / 4}
    )
    check(
        "A: MetricsEngine grouped Product -> Revenue (MIN)",
        dict(metrics.get_grouped_metric("Product", "Revenue", "MIN", table_name=table_a))
        == {"Widget": 1000, "Gadget": 1900}
    )
    check(
        "A: MetricsEngine grouped Product -> Revenue (MAX)",
        dict(metrics.get_grouped_metric("Product", "Revenue", "MAX", table_name=table_a))
        == {"Widget": 1600, "Gadget": 9000}
    )
    check(
        "A: MetricsEngine grouped Product -> Revenue (COUNT)",
        dict(metrics.get_grouped_metric("Product", "Revenue", "COUNT", table_name=table_a))
        == {"Widget": 4, "Gadget": 4}
    )

    # -- capability detection recognizes Date + Revenue as a valid trend
    # capability, even though it isn't "Order Date" + "Sales" --
    cap_a = detector.detect(table_a)
    check("A: trends available via generic Date+Revenue pair", cap_a["trends"]["available"] is True)
    check("A: trends picked a real date column", cap_a["trends"]["date_column"] == "Date")
    check("A: trends picked a real numeric measure", cap_a["trends"]["measure_column"] in ("Units", "Revenue"))

    # -- Date -> Revenue trend --
    monthly_revenue = trends.get_monthly_metrics_generic("Date", "Revenue", table_name=table_a)
    check("A: Date->Revenue trend has 4 months", len(monthly_revenue) == 4)
    check("A: Date->Revenue trend totals match", [value for _period, value in monthly_revenue] == [3000, 5500, 10200, 3500])

    # -- Date -> Units trend --
    monthly_units = trends.get_monthly_metrics_generic("Date", "Units", table_name=table_a)
    check("A: Date->Units trend has 4 months", len(monthly_units) == 4)
    check("A: Date->Units trend totals match", [value for _period, value in monthly_units] == [30, 55, 30, 35])

    # -- growth --
    growth_revenue = trends.calculate_growth_generic(monthly_revenue)
    check("A: growth first period has no comparison", growth_revenue[0]["growth_reason"] == "no_previous_period")
    check(
        "A: growth second period is a normal positive growth calc",
        growth_revenue[1]["growth_percent"] == round(((5500 - 3000) / 3000) * 100, 2)
    )
    check(
        "A: growth third period reflects the revenue spike",
        growth_revenue[2]["growth_percent"] == round(((10200 - 5500) / 5500) * 100, 2)
    )
    check(
        "A: growth fourth period is negative (spike receded)",
        growth_revenue[3]["growth_percent"] < 0
    )
    check("A: growth never emits NaN/Infinity", is_json_safe(growth_revenue))

    # -- moving average --
    moving_avg = trends.calculate_moving_average_generic(monthly_revenue, window=3)
    check(
        "A: moving average is None before the window fills, with an explicit reason",
        moving_avg[0]["moving_average"] is None and moving_avg[0]["moving_average_reason"] == "insufficient_periods"
        and moving_avg[1]["moving_average"] is None and moving_avg[1]["moving_average_reason"] == "insufficient_periods"
    )
    check(
        "A: moving average matches a manual 3-period average once the window fills",
        moving_avg[2]["moving_average"] == round((3000 + 5500 + 10200) / 3, 2)
        and moving_avg[2]["moving_average_reason"] is None
    )
    check("A: moving average never emits NaN/Infinity", is_json_safe(moving_avg))

    # -- moving average: a missing value inside an otherwise-full window
    # must NOT silently average just the observed values (that would be
    # indistinguishable from a real full-window average) -- it must
    # report None with an explicit reason instead, recovering only once
    # the missing value has fully slid out of the window.
    monthly_with_gap = [
        ("2024-01", 100), ("2024-02", None), ("2024-03", 300),
        ("2024-04", 300), ("2024-05", 300),
    ]
    moving_avg_gap = trends.calculate_moving_average_generic(monthly_with_gap, window=3)
    check(
        "A: moving average with a missing value in the window reports None + explicit reason, not a partial average",
        moving_avg_gap[2]["moving_average"] is None
        and moving_avg_gap[2]["moving_average_reason"] == "missing_value_in_window"
        and moving_avg_gap[3]["moving_average"] is None
        and moving_avg_gap[3]["moving_average_reason"] == "missing_value_in_window"
    )
    check(
        "A: moving average recovers a real average once the missing value has fully slid out of the window",
        moving_avg_gap[4]["moving_average"] == 300.0 and moving_avg_gap[4]["moving_average_reason"] is None
    )

    # -- period comparison: both the zero-baseline case (Dataset F, below)
    # and a normal, non-zero comparison here --
    normal_comparison = trends.compare_last_two_periods_generic(monthly_revenue)
    check(
        "A: normal period comparison reports a real change_percent, no reason",
        normal_comparison["available"] is True and normal_comparison["reason"] is None
        and normal_comparison["change_percent"] == round(((3500 - 10200) / 10200) * 100, 2)
    )

    # -- contribution: percentage, ranking, top-N, bottom-N --
    contrib = contributions.analyze_with_metadata("Product", "Revenue", table_name=table_a)
    check("A: contribution supported", contrib["supported"] is True)
    check("A: contribution has 2 categories ranked", [row["rank"] for row in contrib["breakdown"]] == [1, 2])
    check("A: contribution percentages sum to ~100", abs(sum(row["percent"] for row in contrib["breakdown"]) - 100) < 0.1)
    contrib_top1 = contributions.analyze_with_metadata("Product", "Revenue", table_name=table_a, top_n=1)
    check("A: contribution top-1 returns exactly 1 row, flagged truncated", len(contrib_top1["breakdown"]) == 1 and contrib_top1["rows_truncated"] is True)
    check("A: contribution top-1 is the higher-revenue product", contrib_top1["breakdown"][0]["category"] == "Gadget")
    contrib_bottom1 = contributions.analyze_with_metadata("Product", "Revenue", table_name=table_a, bottom_n=1)
    check("A: contribution bottom-1 is the lower-revenue product", contrib_bottom1["breakdown"][0]["category"] == "Widget")

    # -- anomaly output: metric, value, baseline, z_score, row reference, reason --
    anomaly_result = anomalies.detect_with_context("Revenue", table_name=table_a)
    check("A: anomaly detection status is ok", anomaly_result["status"] == "ok")
    check("A: anomaly detection flags the 9000 outlier", any(row["value"] == 9000 for row in anomaly_result["anomalies"]))
    outlier = next(row for row in anomaly_result["anomalies"] if row["value"] == 9000)
    check(
        "A: anomaly evidence includes metric/baseline/z_score/row_id/reason",
        outlier["metric"] == "Revenue" and outlier["baseline"] == anomaly_result["mean"]
        and isinstance(outlier["z_score"], float) and outlier["row_id"] is not None and bool(outlier["reason"])
    )

    # -- full unified context stays JSON-safe with the new richer shape --
    context_a = analyze_dataset(table_a, meta_a["stored_path"], db_file=db_file, dataset_metadata=meta_a)
    check("A: full context is JSON serializable", is_json_safe(context_a))
    check("A: context trends available with 4 months", context_a["trends"]["available"] and len(context_a["trends"]["data"]["monthly"]) == 4)
    check("A: context metrics include min/max/count", {"min", "max", "count"}.issubset(context_a["metrics"]["data"]["Revenue"].keys()))
    check("A: context contribution includes rank", all("rank" in row for row in context_a["contribution"]["data"]["breakdown"]))
    check(
        "A: context anomalies flag the Revenue outlier with evidence",
        context_a["anomalies"]["available"]
        and any(row["value"] == 9000 and "baseline" in row for row in context_a["anomalies"]["data"].get("Revenue", []))
    )

    # =====================================================================
    # Dataset B -- generic non-date dataset: Employee, Department, Salary
    # =====================================================================
    _, meta_b, _ = upload_and_ingest(registry, ingestor, "b.csv", pd.DataFrame({
        "Employee": ["Alice", "Bob", "Carol", "Dave", "Erin", "Frank", "Grace", "Heidi"],
        "Department": ["Eng", "Eng", "Eng", "Eng", "Sales", "Sales", "Sales", "Sales"],
        "Salary": [90000, 95000, 92000, 91000, 70000, 72000, 71000, 260000],  # 260000 is a deliberate outlier
    }))
    table_b = meta_b["table_name"]

    check("B: MetricsEngine SUM(Salary)", metrics.get_sum("Salary", table_name=table_b) == 841000)
    check(
        "B: MetricsEngine grouped Department -> Salary",
        dict(metrics.get_grouped_metric("Department", "Salary", "SUM", table_name=table_b))
        == {"Eng": 368000, "Sales": 473000}
    )

    contrib_b = contributions.analyze_with_metadata("Department", "Salary", table_name=table_b)
    check("B: contribution supported on generic schema", contrib_b["supported"] is True)
    check("B: contribution ranked with 2 categories", contrib_b["total_categories"] == 2)

    anomaly_b = anomalies.detect_with_context("Salary", table_name=table_b)
    check("B: anomaly detection flags the 260000 outlier", any(row["value"] == 260000 for row in anomaly_b["anomalies"]))

    cap_b = detector.detect(table_b)
    check(
        "B: trend unavailable with a clear reason (no date column at all)",
        cap_b["trends"]["available"] is False and bool(cap_b["trends"]["reason"])
    )
    check("B: trend capability reports no date/measure column picked", cap_b["trends"]["date_column"] is None)

    context_b = analyze_dataset(table_b, meta_b["stored_path"], db_file=db_file, dataset_metadata=meta_b)
    check("B: full context is JSON serializable", is_json_safe(context_b))
    check("B: context trends cleanly unsupported with a reason", context_b["trends"]["available"] is False and bool(context_b["trends"]["reason"]))

    # =====================================================================
    # Dataset C -- no numeric columns
    # =====================================================================
    _, meta_c, _ = upload_and_ingest(registry, ingestor, "c.csv", pd.DataFrame({
        "Name": ["Alice", "Bob", "Carol"],
        "City": ["NYC", "LA", "Chicago"],
    }))
    table_c = meta_c["table_name"]
    cap_c = detector.detect(table_c)
    check("C: metrics unavailable with clear reason", cap_c["metrics"]["available"] is False and bool(cap_c["metrics"]["reason"]))
    check("C: anomaly unavailable with clear reason", cap_c["anomaly"]["available"] is False and bool(cap_c["anomaly"]["reason"]))
    check("C: trend unavailable with clear reason", cap_c["trends"]["available"] is False and bool(cap_c["trends"]["reason"]))

    context_c = analyze_dataset(table_c, meta_c["stored_path"], db_file=db_file, dataset_metadata=meta_c)
    check("C: full context is JSON serializable", is_json_safe(context_c))
    check("C: context metrics cleanly unsupported (graceful, not a crash)", context_c["metrics"]["available"] is False)
    check("C: context anomalies cleanly unsupported (graceful, not a crash)", context_c["anomalies"]["available"] is False)

    # =====================================================================
    # Dataset D -- constant numeric values
    # =====================================================================
    _, meta_d, _ = upload_and_ingest(registry, ingestor, "d.csv", pd.DataFrame({
        "Category": ["A", "B", "C", "D"],
        "Value": [50, 50, 50, 50],
    }))
    table_d = meta_d["table_name"]

    anomaly_d = anomalies.detect_with_context("Value", table_name=table_d)
    check("D: no divide-by-zero -- reports zero_variance status, not a crash", anomaly_d["status"] == "zero_variance")
    check("D: no invalid anomaly values produced", anomaly_d["anomalies"] == [] and anomaly_d["standard_deviation"] == 0.0)
    check("D: zero-variance result is still JSON-safe", is_json_safe(anomaly_d))

    context_d = analyze_dataset(table_d, meta_d["stored_path"], db_file=db_file, dataset_metadata=meta_d)
    check("D: full context is JSON serializable, no crash on constant column", is_json_safe(context_d))
    check(
        "D: constant-column anomaly detection safely reports no anomalies",
        context_d["anomalies"]["available"] and context_d["anomalies"]["data"]["Value"] == []
    )

    # =====================================================================
    # Dataset E -- missing periods (a month is skipped in the date data)
    # =====================================================================
    _, meta_e, _ = upload_and_ingest(registry, ingestor, "e.csv", pd.DataFrame({
        "Date": ["2024-01-10", "2024-01-20", "2024-04-05", "2024-04-15"],  # Feb/Mar skipped
        "Revenue": [1000, 1200, 900, 1100],
    }))
    table_e = meta_e["table_name"]

    monthly_e = trends.get_monthly_metrics_generic("Date", "Revenue", table_name=table_e)
    check("E: only the actually observed periods are present (no fabricated months)", [p for p, _v in monthly_e] == ["2024-01", "2024-04"])
    growth_e = trends.calculate_growth_generic(monthly_e)
    check(
        "E: growth across the gap is explicitly flagged, not silently computed as monthly",
        growth_e[1]["growth_reason"] == "non_adjacent_period" and growth_e[1]["period_gap_months"] == 3
    )
    check("E: no growth percent is fabricated across the gap", growth_e[1]["growth_percent"] is None)
    check("E: missing-period growth output stays JSON-safe", is_json_safe(growth_e))

    # =====================================================================
    # Dataset F -- zero baseline (previous period's total is exactly 0)
    # =====================================================================
    _, meta_f, _ = upload_and_ingest(registry, ingestor, "f.csv", pd.DataFrame({
        "Date": ["2024-01-05", "2024-01-20", "2024-02-05", "2024-02-20"],
        "Revenue": [0, 0, 500, 700],
    }))
    table_f = meta_f["table_name"]

    monthly_f = trends.get_monthly_metrics_generic("Date", "Revenue", table_name=table_f)
    check("F: zero-baseline monthly totals computed cleanly", [v for _p, v in monthly_f] == [0, 1200])
    growth_f = trends.calculate_growth_generic(monthly_f)
    check(
        "F: zero baseline produces an explicit reason instead of dividing by zero",
        growth_f[1]["growth_reason"] == "zero_baseline" and growth_f[1]["growth_percent"] is None
    )
    check("F: zero-baseline growth output stays JSON-safe (no Infinity)", is_json_safe(growth_f))

    comparison_f = trends.compare_last_two_periods_generic(monthly_f)
    check("F: period comparison also reports zero_baseline explicitly", comparison_f["available"] is True and comparison_f["reason"] == "zero_baseline")

    # =====================================================================
    # Dataset G -- high-cardinality dimension (1,000+ unique IDs)
    # =====================================================================
    _, meta_g, _ = upload_and_ingest(registry, ingestor, "g.csv", pd.DataFrame({
        "Organization Id": [f"org_{i}" for i in range(1200)],
        "Value": list(range(1200)),
    }))
    table_g = meta_g["table_name"]

    contrib_g = contributions.analyze_with_metadata("Organization Id", "Value", table_name=table_g, max_categories=500)
    check("G: high-cardinality dimension is rejected, not silently exploded", contrib_g["supported"] is False)
    check("G: rejection reports rows_truncated + a clear reason", contrib_g["rows_truncated"] is True and bool(contrib_g["reason"]))
    check(
        "G: exact category count is intentionally NOT computed for a rejected high-cardinality "
        "dimension (a second full-table COUNT(DISTINCT) scan would defeat the point of the guard)",
        contrib_g["total_categories"] is None
    )
    check("G: no million-row breakdown was built", contrib_g["breakdown"] == [])
    # A dimension just under the cap is accepted normally and still gets
    # an exact category count (no LIMIT truncation happened).
    contrib_g_ok = contributions.analyze_with_metadata("Organization Id", "Value", table_name=table_g, max_categories=2000)
    check("G: a dimension under the cap is accepted with an exact category count", contrib_g_ok["supported"] is True and contrib_g_ok["total_categories"] == 1200)

    # =====================================================================
    # Dataset I -- compact numeric date encoding (YYYYMMDD as plain
    # integers, e.g. 20240105). pandas' CSV reader reads this as a bare
    # int64 column, so without dedicated handling it would be invisible
    # to every date-based capability -- the concrete "Date -> []" bug
    # this suite was written to catch and pin down.
    # =====================================================================
    _, meta_i, _ = upload_and_ingest(registry, ingestor, "i.csv", pd.DataFrame({
        "Date": [20240105, 20240120, 20240205, 20240220],
        "Revenue": [1000, 1200, 900, 1100],
    }))
    table_i = meta_i["table_name"]

    cap_i = detector.detect(table_i)
    check("I: compact YYYYMMDD int column is classified as a date column, not numeric", cap_i["date_columns"] == ["Date"])
    check("I: compact YYYYMMDD int column is NOT also counted as a numeric measure", "Date" not in cap_i["numeric_columns"])
    check("I: trend capability is available via the recovered date column", cap_i["trends"]["available"] is True and cap_i["trends"]["date_column"] == "Date")

    monthly_i = trends.get_monthly_metrics_generic("Date", "Revenue", table_name=table_i)
    check("I: compact-date trend produces correct monthly totals", [v for _p, v in monthly_i] == [2200, 2000])

    # A genuinely numeric 8-digit column (not a valid calendar date for
    # ~96% of possible values) must NOT be misclassified as a date --
    # false-positive resistance for the same detection path.
    _, meta_i2, _ = upload_and_ingest(registry, ingestor, "i2.csv", pd.DataFrame({
        "Organization Id": [88231045, 77123456, 99012399, 12345678, 55667788],
        "Value": [1, 2, 3, 4, 5],
    }))
    table_i2 = meta_i2["table_name"]
    cap_i2 = detector.detect(table_i2)
    check("I: a genuine 8-digit ID column is NOT misclassified as a date", "Organization Id" not in cap_i2["date_columns"])
    check("I: a genuine 8-digit ID column stays numeric", "Organization Id" in cap_i2["numeric_columns"])

    # =====================================================================
    # Dataset H -- NaN / Infinity / missing observations
    # =====================================================================
    _, meta_h, _ = upload_and_ingest(registry, ingestor, "h.csv", pd.DataFrame({
        "Category": ["A", "B", "C", "D", "E"],
        "Value": [10.0, float("nan"), float("inf"), float("-inf"), 12.0],
    }))
    table_h = meta_h["table_name"]

    anomaly_h = anomalies.detect_with_context("Value", table_name=table_h)
    check("H: NaN/Infinity rows are skipped, not crashed on", anomaly_h["supported"] is True)
    check("H: NaN/Infinity never leak into the anomaly result", is_json_safe(anomaly_h))

    context_h = analyze_dataset(table_h, meta_h["stored_path"], db_file=db_file, dataset_metadata=meta_h)
    check("H: full context is JSON serializable with NaN/Infinity source data", is_json_safe(context_h))
    check("H: no NaN/Infinity leaked into the serialized context", is_json_safe(context_h))

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED CHECKS:")
        for name in FAIL:
            print(" -", name)
        sys.exit(1)


if __name__ == "__main__":
    main()
