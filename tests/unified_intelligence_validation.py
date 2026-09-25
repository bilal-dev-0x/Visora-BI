"""Standalone validation for unified orchestration
(backend/pipeline.py), the evidence layer (backend/evidence.py),
deterministic prioritization (backend/prioritization.py), the
structured AI result (backend/ai_service.py's
generate_structured_ai_insights), report file lifecycle
(backend/report_store.py + selective deletion in
backend/dataset_registry.py), and chart type selection
(backend/chart_selection.py).

Mirrors the pass/fail-list, sandboxed style of the other
tests/*_validation.py scripts -- never touches the real
data/visora.db, data/datasets/, or reports/.
"""

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

SANDBOX = Path("/tmp/visora_unified_intelligence_sandbox")
PASS, FAIL = [], []


def check(name, condition):
    if condition:
        PASS.append(name)
        print(f"PASS: {name}")
    else:
        FAIL.append(name)
        print(f"FAIL: {name}")


def _fresh_sandbox():
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SANDBOX.mkdir(parents=True)
    (SANDBOX / "reports").mkdir()
    return SANDBOX


def upload_and_ingest(registry, ingestor, filename, df_or_path):
    if isinstance(df_or_path, pd.DataFrame):
        csv_path = SANDBOX / filename
        df_or_path.to_csv(csv_path, index=False)
    else:
        csv_path = df_or_path
    dataset_id = registry.register_upload(filename, csv_path)
    meta = registry.get_dataset(dataset_id)
    result = ingestor.ingest_csv(meta["stored_path"], meta["table_name"])
    registry.update_counts(dataset_id, result["row_count"], result["column_count"])
    return dataset_id, result


def main():
    from backend.dataset_registry import DatasetRegistry
    from backend.ingestion import DatasetIngestor
    from backend import evidence as evidence_mod
    from backend import prioritization as prioritization_mod
    from backend import ai_service
    from backend import report_store
    from backend import pipeline
    from backend import chart_selection

    _fresh_sandbox()
    db_file = str(SANDBOX / "visora.db")
    reports_dir = SANDBOX / "reports"

    registry = DatasetRegistry(db_file=db_file, storage_dir=str(SANDBOX / "datasets"))
    registry.connect()
    ingestor = DatasetIngestor(db_file=db_file)
    ingestor.connect()

    # ------------------------------------------------------------------
    # 1. Unified orchestration -- a normal, well-formed dataset
    # ------------------------------------------------------------------
    sales_df = pd.DataFrame({
        "Order Date": pd.date_range("2024-01-01", periods=24, freq="MS"),
        "Category": (["Tech", "Office", "Furniture"] * 8),
        "Sales": [100, 120, 90, 400, 130, 95, 150, 140, 92, 160, 133, 96,
                  170, 150, 98, 180, 155, 99, 900, 160, 101, 200, 165, 102],
    })
    dataset_id, ingest_result = upload_and_ingest(registry, ingestor, "sales.csv", sales_df)
    check("Unified: normal dataset ingests successfully", ingest_result["ingested"])

    with patch.object(report_store, "REPORTS_DIR", reports_dir):
        report = pipeline.analyze_dataset(dataset_id, registry=registry, db_file=db_file)

    check("Unified: unified report has status success", report.get("status") == "success")
    check("Unified: unified report carries dataset/metrics/trends/contribution/anomalies",
          all(key in report for key in ("dataset", "metrics", "trends", "contribution", "anomalies")))
    check("Unified: unified report carries evidence layer", "evidence" in report and isinstance(report["evidence"], list))
    check("Unified: unified report carries prioritized_findings", "prioritized_findings" in report)
    check("Unified: unified report carries structured ai_analysis",
          "ai_analysis" in report and "summary" in report["ai_analysis"] and "insights" in report["ai_analysis"])
    check("Unified: JSON-serializable end to end", bool(json.dumps(report)))

    # Evidence should have picked up the concentration (Tech dominates?)
    # and/or the outlier Sales values (400, 900) as anomalies.
    evidence_types = {item["type"] for item in report["evidence"]}
    check("Unified: evidence includes at least one anomaly or trend or concentration item",
          bool(evidence_types & {"anomaly", "trend", "concentration", "quality"}))

    # Prioritized findings must be sorted Critical -> Low.
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    priorities = [order[item["priority"]] for item in report["prioritized_findings"]]
    check("Unified: prioritized findings are sorted critical->low", priorities == sorted(priorities))

    # ------------------------------------------------------------------
    # 2. Report file lifecycle -- single current JSON, dataset-specific TXT
    # ------------------------------------------------------------------
    current_json_path = report_store.current_json_path(reports_dir)
    check("Unified: current unified JSON report file was written", current_json_path.exists())

    dataset_row = registry.get_dataset(dataset_id)
    txt_path = report_store.txt_report_path(dataset_row, reports_dir)
    check("Unified: dataset-specific TXT report file was written", txt_path.exists())
    check("Unified: TXT report filename is NOT the generic 'analysis.txt'", txt_path.name != "analysis.txt")
    check("Unified: TXT report filename is dataset-specific (not a shared name)",
          "sales" in txt_path.name.lower())

    txt_before = txt_path.read_text(encoding="utf-8")
    with patch.object(report_store, "REPORTS_DIR", reports_dir):
        pipeline.analyze_dataset(dataset_id, registry=registry, db_file=db_file)
    files_matching = list(reports_dir.glob(f"{txt_path.stem}*.txt"))
    check("Unified: re-analyzing the same dataset does not accumulate a second TXT file",
          len(files_matching) == 1)

    # ------------------------------------------------------------------
    # 3. Second dataset -- multi-dataset isolation
    # ------------------------------------------------------------------
    customers_df = pd.DataFrame({"Employee": ["Alice", "Bob", "Cara"], "Salary": [90000, 95000, 88000]})
    dataset_id_2, _ = upload_and_ingest(registry, ingestor, "customers.csv", customers_df)
    with patch.object(report_store, "REPORTS_DIR", reports_dir):
        report_2 = pipeline.analyze_dataset(dataset_id_2, registry=registry, db_file=db_file)
    dataset_row_2 = registry.get_dataset(dataset_id_2)
    txt_path_2 = report_store.txt_report_path(dataset_row_2, reports_dir)
    check("Unified: second dataset gets its OWN, differently-named TXT report",
          txt_path_2.exists() and txt_path_2 != txt_path)
    check("Unified: dataset B report status is success", report_2.get("status") == "success")

    # ------------------------------------------------------------------
    # 4. Selective deletion + report cleanup -- deleting A never touches B
    # ------------------------------------------------------------------
    with patch.object(report_store, "REPORTS_DIR", reports_dir):
        deleted = pipeline.delete_dataset_and_report(dataset_id, registry=registry, db_file=db_file)
    check("Unified: delete_dataset_and_report returns the deleted dataset row", deleted is not None)
    check("Unified: deleting dataset A removes its TXT report", not txt_path.exists())
    check("Unified: deleting dataset A does NOT remove dataset B's TXT report", txt_path_2.exists())
    check("Unified: deleting dataset A removes it from the registry", registry.get_dataset(dataset_id) is None)
    check("Unified: deleting dataset A leaves dataset B in the registry", registry.get_dataset(dataset_id_2) is not None)

    missing_result = pipeline.delete_dataset_and_report("not-a-real-id", registry=registry, db_file=db_file)
    check("Unified: deleting a nonexistent dataset_id returns None instead of raising", missing_result is None)

    # ------------------------------------------------------------------
    # 5. Missing dataset in analyze_dataset() itself
    # ------------------------------------------------------------------
    ghost_report = pipeline.analyze_dataset("not-a-real-id", registry=registry, db_file=db_file, persist=False)
    check("Unified: analyzing a missing dataset_id returns an error report, not an exception",
          ghost_report.get("status") == "error" and ghost_report.get("error"))

    # ------------------------------------------------------------------
    # 6. Edge-case datasets never crash the pipeline
    # ------------------------------------------------------------------
    edge_cases = {
        "empty.csv": None,          # truly 0-byte file
        "header_only.csv": pd.DataFrame(columns=["A", "B"]),
        "single_row.csv": pd.DataFrame({"A": [1], "B": ["x"]}),
        "no_numeric.csv": pd.DataFrame({"A": ["x", "y", "z"], "B": ["p", "q", "r"]}),
        "constant.csv": pd.DataFrame({"A": [5, 5, 5, 5, 5], "B": ["x", "y", "x", "y", "x"]}),
        "high_cardinality.csv": pd.DataFrame({
            "id": [f"id_{i}" for i in range(200)],
            "value": list(range(200)),
        }),
    }

    for filename, df in edge_cases.items():
        csv_path = SANDBOX / filename
        if df is None:
            csv_path.write_text("", encoding="utf-8")
        else:
            df.to_csv(csv_path, index=False)

        dataset_id_edge = registry.register_upload(filename, csv_path)
        meta = registry.get_dataset(dataset_id_edge)
        ingest_result = ingestor.ingest_csv(meta["stored_path"], meta["table_name"])
        registry.update_counts(dataset_id_edge, ingest_result["row_count"], ingest_result["column_count"])

        try:
            with patch.object(report_store, "REPORTS_DIR", reports_dir):
                edge_report = pipeline.analyze_dataset(dataset_id_edge, registry=registry, db_file=db_file)
            crashed = False
        except Exception as exc:  # pragma: no cover - the whole point is that this never happens
            crashed = True
            edge_report = None

        check(f"Unified edge case ({filename}): pipeline never raises", not crashed)
        if not crashed:
            check(f"Unified edge case ({filename}): result has a status field",
                  edge_report is not None and "status" in edge_report)
            check(f"Unified edge case ({filename}): result is JSON-serializable", bool(json.dumps(edge_report)))

    # ------------------------------------------------------------------
    # 7. Evidence + prioritization unit checks
    # ------------------------------------------------------------------
    fake_context = {
        "dataset": {"row_count": 100, "column_count": 5},
        "data_quality": {"total_missing_values": 300, "duplicate_rows": 60, "completely_empty_rows": 2},
        "trends": {
            "available": True,
            "data": {
                "measure_column": "Sales", "date_column": "Order Date",
                "growth": [{"period": "2024-02", "value": 100, "growth_percent": 60.0, "growth_reason": None}],
                "period_comparison": {"available": True, "change_percent": 60.0, "current_period": "2024-02"},
            },
        },
        "contribution": {
            "available": True,
            "data": {"dimension": "Category", "measure": "Sales", "breakdown": [{"category": "Tech", "value": 900, "percent": 85.0, "rank": 1}]},
        },
        "anomalies": {
            "available": True,
            "data": {"Sales": [{"row_id": 1, "metric": "Sales", "value": 900, "baseline": 120.0, "z_score": 4.5, "deviation": 780, "context": {}, "reason": "..."}]},
        },
    }
    evidence = evidence_mod.build_evidence(fake_context)
    check("Unified evidence: extreme missingness produces quality evidence",
          any(item["type"] == "quality" and item.get("issue") == "missing_values" for item in evidence))
    check("Unified evidence: extreme duplicates produces quality evidence",
          any(item["type"] == "quality" and item.get("issue") == "duplicate_rows" for item in evidence))
    check("Unified evidence: strong growth produces trend evidence",
          any(item["type"] == "trend" for item in evidence))
    check("Unified evidence: high concentration produces concentration evidence",
          any(item["type"] == "concentration" for item in evidence))
    check("Unified evidence: strong anomaly produces anomaly evidence",
          any(item["type"] == "anomaly" for item in evidence))
    check("Unified evidence: every item has a stable id", all("id" in item for item in evidence))

    prioritized = prioritization_mod.prioritize_evidence(evidence)
    check("Unified prioritization: z=4.5 anomaly is Critical",
          next(item for item in prioritized if item["type"] == "anomaly")["priority"] == "critical")
    check("Unified prioritization: 60% missing is Critical",
          next(item for item in prioritized if item.get("issue") == "missing_values")["priority"] == "critical")
    check("Unified prioritization: 85% concentration is Critical",
          next(item for item in prioritized if item["type"] == "concentration")["priority"] == "critical")
    priorities_sorted = [order[item["priority"]] for item in prioritized]
    check("Unified prioritization: output is sorted critical->low", priorities_sorted == sorted(priorities_sorted))

    empty_evidence = evidence_mod.build_evidence({})
    check("Unified evidence: malformed/empty context returns [] instead of raising", empty_evidence == [])
    check("Unified prioritization: empty evidence returns []", prioritization_mod.prioritize_evidence([]) == [])

    # ------------------------------------------------------------------
    # 8. Structured AI result -- no provider configured -> local fallback
    # ------------------------------------------------------------------
    with patch("backend.ai_service.load_provider_chain", return_value=[]):
        structured = ai_service.generate_structured_ai_insights(fake_context, evidence, prioritized)
    check("Unified structured AI: no provider -> local_fallback source", structured.source == "local_fallback")
    check("Unified structured AI: local fallback still produces insights from evidence",
          len(structured.result["insights"]) == len(prioritized))
    check("Unified structured AI: local fallback result is JSON-serializable", bool(json.dumps(structured.result)))

    # Oversized file -> must skip AI entirely without attempting a call.
    with patch("backend.ai_service.load_provider_chain") as mocked_chain:
        oversized = ai_service.generate_structured_ai_insights(
            fake_context, evidence, prioritized, file_size_bytes=999_999_999,
        )
    check("Unified structured AI: oversized context skips AI (size_threshold_exceeded)",
          oversized.ai_skipped_reason == "size_threshold_exceeded" and not oversized.ai_attempted)
    check("Unified structured AI: oversized context never touches the provider chain", not mocked_chain.called)

    # ------------------------------------------------------------------
    # 9. Structured AI result -- malformed / well-formed provider responses
    # ------------------------------------------------------------------
    from backend.config import ProviderConfig

    configured = [ProviderConfig(slot="provider_1", kind="openai_compatible", api_key="key", model="gpt-x", base_url="https://api.example.com")]

    class _FakeProvider:
        name = "FakeProvider"

        def __init__(self, text):
            self._text = text

        def complete(self, system, prompt):
            return self._text

    malformed_text = "not json at all {{{"
    with patch("backend.ai_service.load_provider_chain", return_value=configured), \
         patch("backend.ai_service.build_provider", return_value=_FakeProvider(malformed_text)):
        malformed_result = ai_service.generate_structured_ai_insights(fake_context, evidence, prioritized)
    check("Unified structured AI: malformed provider JSON falls back safely (no crash)",
          malformed_result.source == "local_fallback")

    good_evidence_id = evidence[0]["id"] if evidence else None
    good_payload = json.dumps({
        "summary": "Sales grew sharply and Tech dominates the category mix.",
        "insights": [{
            "id": good_evidence_id, "title": "Strong growth", "type": "trend",
            "priority": "critical",  # deliberately wrong -- must be overridden by the pinned evidence priority
            "explanation": "Sales rose significantly period over period.",
            "evidence": [good_evidence_id],
        }],
        "risks": ["Sales concentration in one category is a risk if demand shifts."],
        "opportunities": ["Growth momentum could be reinforced with more Tech inventory."],
    })
    with patch("backend.ai_service.load_provider_chain", return_value=configured), \
         patch("backend.ai_service.build_provider", return_value=_FakeProvider(good_payload)):
        good_result = ai_service.generate_structured_ai_insights(fake_context, evidence, prioritized)
    check("Unified structured AI: well-formed JSON is parsed as source=ai", good_result.source == "ai")
    check("Unified structured AI: insight priority is pinned to the evidence's own deterministic priority, not the model's",
          good_result.result["insights"][0]["priority"] ==
          next(item for item in prioritized if item["id"] == good_evidence_id)["priority"])
    valid_ids = {item["id"] for item in evidence}
    check("Unified structured AI: evidence attached to insights always resolves to a real evidence item",
          all(e["id"] in valid_ids for insight in good_result.result["insights"] for e in insight["evidence"]))

    fenced_payload = "```json\n" + good_payload + "\n```"
    with patch("backend.ai_service.load_provider_chain", return_value=configured), \
         patch("backend.ai_service.build_provider", return_value=_FakeProvider(fenced_payload)):
        fenced_result = ai_service.generate_structured_ai_insights(fake_context, evidence, prioritized)
    check("Unified structured AI: markdown-fenced JSON is still parsed correctly", fenced_result.source == "ai")

    # ------------------------------------------------------------------
    # 10. AI provider failure modes still yield a usable structured result
    # ------------------------------------------------------------------
    from backend.ai_providers import AIProviderError

    class _RaisingProvider:
        name = "RaisingProvider"

        def complete(self, system, prompt):
            raise AIProviderError("RaisingProvider", "timeout", "Request timed out.")

    with patch("backend.ai_service.load_provider_chain", return_value=configured), \
         patch("backend.ai_service.build_provider", return_value=_RaisingProvider()):
        timeout_result = ai_service.generate_structured_ai_insights(fake_context, evidence, prioritized)
    check("Unified structured AI: provider timeout falls back to local, deterministic BI still works",
          timeout_result.source == "local_fallback" and timeout_result.ai_attempted)

    # ------------------------------------------------------------------
    # 11. Chart type selection -- data-aware validation
    # ------------------------------------------------------------------
    check("Unified chart: Line supported with date+numeric",
          chart_selection.is_chart_type_supported("Line", ["Order Date"], [], ["Sales"]))
    check("Unified chart: Line NOT supported without a date column",
          not chart_selection.is_chart_type_supported("Line", [], ["Category"], ["Sales"]))
    check("Unified chart: Bar supported with category+numeric",
          chart_selection.is_chart_type_supported("Bar", [], ["Category"], ["Sales"]))
    check("Unified chart: Scatter requires two numeric columns",
          chart_selection.is_chart_type_supported("Scatter", [], [], ["A", "B"])
          and not chart_selection.is_chart_type_supported("Scatter", [], [], ["A"]))
    supported, reason = chart_selection.validate_chart_selection("Pie", numeric_columns_selected=0, has_category=True)
    check("Unified chart: invalid selection returns a clear reason instead of crashing",
          not supported and isinstance(reason, str) and reason)
    check("Unified chart: default suggestion is Line for date+numeric schema",
          chart_selection.suggest_default_chart_type(["Order Date"], [], ["Sales"]) == "Line")
    check("Unified chart: default suggestion is Bar for category+numeric schema",
          chart_selection.suggest_default_chart_type([], ["Category"], ["Sales"]) == "Bar")

    # ------------------------------------------------------------------
    # 12. Dashboard still runs end to end with the unified pipeline
    # ------------------------------------------------------------------
    dashboard_sandbox = Path("/tmp/visora_unified_dashboard_sandbox")
    if dashboard_sandbox.exists():
        shutil.rmtree(dashboard_sandbox)
    repo_root = Path(__file__).resolve().parent.parent
    shutil.copytree(repo_root, dashboard_sandbox, ignore=shutil.ignore_patterns(".git", "tests", "data", "reports"))
    (dashboard_sandbox / "data").mkdir()
    (dashboard_sandbox / "reports").mkdir()

    import os
    old_cwd = os.getcwd()
    old_path = list(sys.path)
    try:
        os.chdir(dashboard_sandbox)
        sys.path.insert(0, str(dashboard_sandbox))
        for mod_name in list(sys.modules):
            if mod_name.startswith("backend") or mod_name.startswith("frontend") or mod_name == "components":
                del sys.modules[mod_name]

        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(dashboard_sandbox / "frontend" / "dashboard.py"), default_timeout=30)
        app.run()
        check("Unified dashboard: runs cleanly with no datasets", len(app.exception) == 0)

        from backend.dataset_registry import DatasetRegistry as SandboxRegistry
        from backend.ingestion import DatasetIngestor as SandboxIngestor

        sandbox_registry = SandboxRegistry(
            db_file=str(dashboard_sandbox / "data" / "visora.db"),
            storage_dir=str(dashboard_sandbox / "data" / "datasets"),
        )
        sandbox_registry.connect()
        sandbox_ingestor = SandboxIngestor(db_file=str(dashboard_sandbox / "data" / "visora.db"))
        sandbox_ingestor.connect()

        csv_path = dashboard_sandbox / "data" / "sales.csv"
        sales_df.to_csv(csv_path, index=False)
        sandbox_dataset_id = sandbox_registry.register_upload("sales.csv", csv_path)
        sandbox_meta = sandbox_registry.get_dataset(sandbox_dataset_id)
        sandbox_ingest_result = sandbox_ingestor.ingest_csv(sandbox_meta["stored_path"], sandbox_meta["table_name"])
        sandbox_registry.update_counts(
            sandbox_dataset_id, sandbox_ingest_result["row_count"], sandbox_ingest_result["column_count"],
        )

        app2 = AppTest.from_file(str(dashboard_sandbox / "frontend" / "dashboard.py"), default_timeout=30)
        app2.run()
        check("Unified dashboard: runs cleanly with a real dataset selected", len(app2.exception) == 0)

        subheaders = [element.value for element in app2.subheader] if hasattr(app2, "subheader") else []
        check("Unified dashboard: shows a Prioritized Findings section", any("Prioritized Findings" in text for text in subheaders))
        check("Unified dashboard: shows a Reports section (TXT download)", any("Reports" in text for text in subheaders))
        check("Unified dashboard: shows a Chart Explorer section", any("Chart Explorer" in text for text in subheaders))

        txt_written = list((dashboard_sandbox / "reports").glob("sales_*.txt"))
        check("Unified dashboard: selecting a dataset writes its dataset-specific TXT report", len(txt_written) == 1)
    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_path
        for mod_name in list(sys.modules):
            if mod_name.startswith("backend") or mod_name.startswith("frontend") or mod_name == "components":
                del sys.modules[mod_name]

    # ------------------------------------------------------------------
    # Final result
    # ------------------------------------------------------------------
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED CHECKS:")
        for name in FAIL:
            print(f" - {name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
