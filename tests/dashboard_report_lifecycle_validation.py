"""Regression validation for dashboard/report deletion and Streamlit reruns.

Runs entirely in a temporary sandbox and exercises both the backend
lifecycle and the real Streamlit dashboard through AppTest. No real
project database, uploaded dataset, or report file is touched.
"""

import gc
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

PASS, FAIL = [], []


def check(name, condition):
    if condition:
        PASS.append(name)
        print(f"PASS: {name}")
    else:
        FAIL.append(name)
        print(f"FAIL: {name}")


def _table_names(db_file):
    with closing(sqlite3.connect(db_file)) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }


def _current_dataset_id(current_path):
    if not current_path.exists():
        return None
    return json.loads(current_path.read_text(encoding="utf-8"))["dataset"]["dataset_id"]


def _stored_path(root, dataset):
    path = Path(dataset["stored_path"])
    return path if path.is_absolute() else root / path


def _make_dataset(root, registry, ingestor, filename, value_offset=0):
    source_dir = root / "inputs"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / filename
    pd.DataFrame(
        {
            "Order Date": pd.date_range("2024-01-01", periods=4, freq="MS"),
            "Category": ["Tech", "Office", "Tech", "Office"],
            "Sales": [100 + value_offset, 120 + value_offset, 900 + value_offset, 130 + value_offset],
            "Quantity": [1 + value_offset, 2 + value_offset, 8 + value_offset, 3 + value_offset],
        }
    ).to_csv(source_path, index=False)

    dataset_id = registry.register_upload(filename, source_path)
    dataset = registry.get_dataset(dataset_id)
    result = ingestor.ingest_csv(dataset["stored_path"], dataset["table_name"])
    registry.update_counts(dataset_id, result["row_count"], result["column_count"])
    return dataset_id, registry.get_dataset(dataset_id)


def _backend_lifecycle_checks(root, db_file, reports_dir, registry, ingestor, pipeline, report_store):
    current_path = report_store.current_json_path(reports_dir)

    dataset_a_id, dataset_a = _make_dataset(root, registry, ingestor, "alpha.csv", 0)
    dataset_b_id, dataset_b = _make_dataset(root, registry, ingestor, "beta.csv", 1000)
    txt_a = report_store.txt_report_path(dataset_a, reports_dir)
    txt_b = report_store.txt_report_path(dataset_b, reports_dir)

    pipeline.analyze_dataset(dataset_a_id, registry=registry, db_file=db_file)
    pipeline.analyze_dataset(dataset_b_id, registry=registry, db_file=db_file)
    check("Backend lifecycle: selective fixtures create distinct TXT reports", txt_a.exists() and txt_b.exists())
    check("Backend lifecycle: current report initially represents dataset B", _current_dataset_id(current_path) == dataset_b_id)

    before_tables = _table_names(db_file)
    missing = pipeline.delete_dataset_and_report("missing-dataset-id", registry=registry, db_file=db_file)
    check("Backend lifecycle: deleting a nonexistent dataset is a no-op", missing is None)
    check("Backend lifecycle: nonexistent deletion keeps both registry rows", {row["dataset_id"] for row in registry.list_datasets()} == {dataset_a_id, dataset_b_id})
    check("Backend lifecycle: nonexistent deletion keeps both stored files", _stored_path(root, dataset_a).exists() and _stored_path(root, dataset_b).exists())
    check("Backend lifecycle: nonexistent deletion keeps both tables", {dataset_a["table_name"], dataset_b["table_name"]}.issubset(before_tables))
    check("Backend lifecycle: nonexistent deletion keeps both TXT reports and current JSON", txt_a.exists() and txt_b.exists() and _current_dataset_id(current_path) == dataset_b_id)

    pipeline.delete_dataset_and_report(dataset_a_id, registry=registry, db_file=db_file)
    check("Backend lifecycle: selective delete removes A registry row", registry.get_dataset(dataset_a_id) is None)
    check("Backend lifecycle: selective delete removes A stored CSV", not _stored_path(root, dataset_a).exists())
    check("Backend lifecycle: selective delete removes A analytical table", dataset_a["table_name"] not in _table_names(db_file))
    check("Backend lifecycle: selective delete removes only A TXT report", not txt_a.exists() and txt_b.exists())
    check("Backend lifecycle: deleting non-current A keeps current B report valid", _current_dataset_id(current_path) == dataset_b_id)
    check("Backend lifecycle: selective delete leaves B registry/file/table intact", registry.get_dataset(dataset_b_id) is not None and _stored_path(root, dataset_b).exists() and dataset_b["table_name"] in _table_names(db_file))

    pipeline.delete_dataset_and_report(dataset_b_id, registry=registry, db_file=db_file)
    check("Backend lifecycle: deleting current B removes current JSON", not current_path.exists())
    check("Backend lifecycle: deleting last B empties registry", registry.list_datasets() == [])
    check("Backend lifecycle: deleting last B removes B TXT/file/table", not txt_b.exists() and not _stored_path(root, dataset_b).exists() and dataset_b["table_name"] not in _table_names(db_file))

    dataset_c_id, dataset_c = _make_dataset(root, registry, ingestor, "gamma.csv", 2000)
    dataset_d_id, dataset_d = _make_dataset(root, registry, ingestor, "delta.csv", 3000)
    txt_c = report_store.txt_report_path(dataset_c, reports_dir)
    txt_d = report_store.txt_report_path(dataset_d, reports_dir)
    pipeline.analyze_dataset(dataset_c_id, registry=registry, db_file=db_file)
    pipeline.analyze_dataset(dataset_d_id, registry=registry, db_file=db_file)

    unrelated_report = reports_dir / "unrelated-report.txt"
    unrelated_report.write_text("do not delete", encoding="utf-8")
    with closing(sqlite3.connect(db_file)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sales (value INTEGER)")
        conn.execute("INSERT INTO sales (value) VALUES (1)")
        conn.commit()

    cleared = pipeline.clear_datasets_and_reports(registry=registry, db_file=db_file)
    check("Backend lifecycle: clear history reports its intended dataset count", cleared == 2)
    check("Backend lifecycle: clear history empties registry rows", registry.list_datasets() == [])
    check("Backend lifecycle: clear history removes all registered stored files", not _stored_path(root, dataset_c).exists() and not _stored_path(root, dataset_d).exists())
    check("Backend lifecycle: clear history removes all registered analytical tables", dataset_c["table_name"] not in _table_names(db_file) and dataset_d["table_name"] not in _table_names(db_file))
    check("Backend lifecycle: clear history removes all registered TXT reports", not txt_c.exists() and not txt_d.exists())
    check("Backend lifecycle: clear history removes current JSON", not current_path.exists())
    check("Backend lifecycle: clear history preserves the SQLite database", Path(db_file).exists())
    check("Backend lifecycle: clear history preserves the legacy sales table", "sales" in _table_names(db_file))
    check("Backend lifecycle: clear history leaves unrelated report files untouched", unrelated_report.exists())
    unrelated_report.unlink()

    dataset_e_id, dataset_e = _make_dataset(root, registry, ingestor, "error-case.csv", 4000)
    txt_e = report_store.txt_report_path(dataset_e, reports_dir)
    pipeline.analyze_dataset(dataset_e_id, registry=registry, db_file=db_file)
    lifecycle_error = None
    with patch.object(report_store, "delete_txt_report", side_effect=PermissionError("report is locked")):
        try:
            pipeline.delete_dataset_and_report(dataset_e_id, registry=registry, db_file=db_file)
        except pipeline.DatasetLifecycleError as exc:
            lifecycle_error = exc
    check("Backend lifecycle: report permission failure raises a visible lifecycle error", lifecycle_error is not None and "error-case.csv" in str(lifecycle_error))
    check("Backend lifecycle: failed report cleanup does not pretend registry deletion succeeded", registry.get_dataset(dataset_e_id) is not None)
    check("Backend lifecycle: failed report cleanup retains stored CSV and table", _stored_path(root, dataset_e).exists() and dataset_e["table_name"] in _table_names(db_file))
    check("Backend lifecycle: failed report cleanup retains the TXT file for diagnosis", txt_e.exists())
    pipeline.clear_datasets_and_reports(registry=registry, db_file=db_file)
    check("Backend lifecycle: cleanup fixture is fully removed", registry.list_datasets() == [] and not current_path.exists())


def _button_with_key(app, key):
    return app.get_by_key(key)


def _button_with_label(app, label):
    return next(button for button in app.sidebar.button if button.label == label)


def _selectbox_with_label(app, label):
    return next(selectbox for selectbox in app.selectbox if selectbox.label == label)


def _csv_bytes(value_offset):
    buffer = io.StringIO()
    pd.DataFrame(
        {
            "Order Date": pd.date_range("2024-01-01", periods=4, freq="MS"),
            "Category": ["Tech", "Office", "Tech", "Office"],
            "Sales": [100 + value_offset, 120 + value_offset, 900 + value_offset, 130 + value_offset],
            "Quantity": [1 + value_offset, 2 + value_offset, 8 + value_offset, 3 + value_offset],
        }
    ).to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def _ui_lifecycle_checks(
    root,
    db_file,
    reports_dir,
    registry,
    ingestor,
    pipeline,
    report_store,
    analyze_spy,
    ai_spy,
    delete_spy,
    clear_spy,
    provider,
):
    from streamlit.testing.v1 import AppTest

    dashboard_path = Path(__file__).resolve().parent.parent / "frontend" / "dashboard.py"
    app = AppTest.from_file(str(dashboard_path), default_timeout=30)
    app.run()
    check("UI lifecycle: dashboard starts with no datasets", not app.exception and registry.list_datasets() == [])

    app.file_uploader[0].upload("ui-a.csv", _csv_bytes(5000), "text/csv").run()
    dataset_a_id = app.session_state["selected_dataset_id"]
    dataset_a = registry.get_dataset(dataset_a_id)
    check("UI lifecycle: uploading A performs the unified pipeline once", not app.exception and analyze_spy.call_count == 1 and ai_spy.call_count == 1)
    check("UI lifecycle: uploaded A produces current and TXT reports", _current_dataset_id(report_store.current_json_path(reports_dir)) == dataset_a_id and report_store.txt_report_path(dataset_a, reports_dir).exists())

    app.file_uploader[0].upload("ui-b.csv", _csv_bytes(6000), "text/csv").run()
    dataset_b_id = app.session_state["selected_dataset_id"]
    dataset_b = registry.get_dataset(dataset_b_id)
    check("UI lifecycle: uploading B performs exactly one additional analysis", not app.exception and analyze_spy.call_count == 2 and ai_spy.call_count == 2 and provider.calls == 2)
    check("UI lifecycle: uploaded B becomes the selected current report", _current_dataset_id(report_store.current_json_path(reports_dir)) == dataset_b_id)

    reingested_b = ingestor.ingest_csv(dataset_b["stored_path"], dataset_b["table_name"])
    registry.update_counts(dataset_b_id, reingested_b["row_count"], reingested_b["column_count"])
    app.run()
    check("UI lifecycle: re-ingesting the selected dataset invalidates the old analysis snapshot", not app.exception and analyze_spy.call_count == 3 and ai_spy.call_count == 3 and provider.calls == 3 and analyze_spy.call_args.args[0] == dataset_b_id)

    app.run()
    check("UI lifecycle: an unrelated bare rerun does not rerun pipeline or AI", analyze_spy.call_count == 3 and ai_spy.call_count == 3 and provider.calls == 3)

    chart_type = _selectbox_with_label(app, "Chart Type")
    chart_type.select("Bar").run()
    check("UI lifecycle: chart selection does not rerun pipeline or AI", not app.exception and analyze_spy.call_count == 3 and ai_spy.call_count == 3 and provider.calls == 3)

    app.download_button[0].click().run()
    check("UI lifecycle: report download does not rerun pipeline or AI", not app.exception and analyze_spy.call_count == 3 and ai_spy.call_count == 3 and provider.calls == 3)

    _button_with_key(app, f"dataset_history_{dataset_a_id}").click().run()
    check("UI lifecycle: selecting another dataset performs one required analysis", analyze_spy.call_count == 4 and ai_spy.call_count == 4 and provider.calls == 4)
    check("UI lifecycle: newly analyzed dataset owns current report", _current_dataset_id(report_store.current_json_path(reports_dir)) == dataset_a_id)

    _button_with_key(app, f"dataset_history_{dataset_b_id}").click().run()
    check("UI lifecycle: switching back performs analysis for the newly selected dataset", analyze_spy.call_count == 5 and ai_spy.call_count == 5 and provider.calls == 5)
    check("UI lifecycle: switched dataset owns current report", _current_dataset_id(report_store.current_json_path(reports_dir)) == dataset_b_id)

    _button_with_key(app, f"dataset_history_{dataset_a_id}").click().run()
    check("UI lifecycle: selecting A again performs one fresh selected-version analysis", analyze_spy.call_count == 6 and ai_spy.call_count == 6 and provider.calls == 6)
    check("UI lifecycle: final selected A owns current report before deletion", _current_dataset_id(report_store.current_json_path(reports_dir)) == dataset_a_id)

    app.sidebar.multiselect(key="datasets_to_delete").set_value([dataset_a_id]).run()
    _button_with_key(app, "delete_selected_btn").click().run()
    check("UI lifecycle: opening selective confirmation does not delete or analyze", not app.exception and delete_spy.call_count == 0 and analyze_spy.call_count == 6)

    calls_before_delete = analyze_spy.call_count
    _button_with_key(app, "confirm_delete_selected_btn").click().run()
    check("UI lifecycle: one Confirm click performs exactly one selective deletion", delete_spy.call_count == 1 and delete_spy.call_args.args[0] == dataset_a_id)
    check("UI lifecycle: selective delete has no first-click Streamlit exception", not app.exception)
    check("UI lifecycle: selective delete does not trigger another pipeline/AI call", analyze_spy.call_count == calls_before_delete and ai_spy.call_count == 6 and provider.calls == 6)
    check("UI lifecycle: selective delete clears the multiselect safely", app.session_state["datasets_to_delete"] == [])
    check("UI lifecycle: deleting selected dataset leaves no stale selected id", app.session_state["selected_dataset_id"] is None)
    check("UI lifecycle: deleted dataset disappears from sidebar", "ui-a.csv" not in [button.label for button in app.sidebar.button])
    check("UI lifecycle: selective delete removes A row/file/table/TXT", registry.get_dataset(dataset_a_id) is None and not _stored_path(root, dataset_a).exists() and dataset_a["table_name"] not in _table_names(db_file) and not report_store.txt_report_path(dataset_a, reports_dir).exists())
    check("UI lifecycle: deleting current A removes current JSON", not report_store.current_json_path(reports_dir).exists())
    check("UI lifecycle: selective delete leaves every B artifact intact", registry.get_dataset(dataset_b_id) is not None and _stored_path(root, dataset_b).exists() and dataset_b["table_name"] in _table_names(db_file) and report_store.txt_report_path(dataset_b, reports_dir).exists())

    _button_with_key(app, f"dataset_history_{dataset_b_id}").click().run()
    check("UI lifecycle: explicit survivor selection performs one analysis", analyze_spy.call_count == 7 and ai_spy.call_count == 7 and provider.calls == 7)

    _button_with_label(app, "Clear History").click().run()
    check("UI lifecycle: opening clear confirmation does not delete or analyze", not app.exception and clear_spy.call_count == 0 and analyze_spy.call_count == 7)
    _button_with_key(app, "confirm_clear_history_btn").click().run()
    check("UI lifecycle: one Confirm click performs exactly one clear operation", clear_spy.call_count == 1)
    check("UI lifecycle: clear history has no Streamlit exception", not app.exception)
    check("UI lifecycle: clear history does not trigger pipeline or AI", analyze_spy.call_count == 7 and ai_spy.call_count == 7 and provider.calls == 7)
    check("UI lifecycle: clear history empties registry/files/tables", registry.list_datasets() == [] and not _stored_path(root, dataset_b).exists() and dataset_b["table_name"] not in _table_names(db_file))
    check("UI lifecycle: clear history removes B TXT and current JSON", not report_store.txt_report_path(dataset_b, reports_dir).exists() and not report_store.current_json_path(reports_dir).exists())
    check("UI lifecycle: clear history clears selected state and confirmation flags", app.session_state["selected_dataset_id"] is None and not app.session_state["confirm_clear_history"])
    check("UI lifecycle: clear history returns the UI to the empty state", any("No datasets yet" in item.value for item in app.sidebar.info))

    app.run()
    check("UI lifecycle: retained uploader does not re-register data after clear", registry.list_datasets() == [] and analyze_spy.call_count == 7 and provider.calls == 7)
    check("UI lifecycle: clear history resets the uploader widget generation", app.file_uploader[0].value is None and app.session_state["processed_upload_key"] is None and app.session_state["upload_widget_version"] > 0)
    check("UI lifecycle: no stale deleted dataset remains after a final rerun", not app.exception and "ui-a.csv" not in [button.label for button in app.sidebar.button] and "ui-b.csv" not in [button.label for button in app.sidebar.button])


def main():
    old_cwd = Path.cwd()
    temp_base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Temp" / "opencode"
    temp_base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="visora_lifecycle_", dir=temp_base))
    os.chdir(root)

    registry = None
    ingestor = None
    try:
        from backend import ai_service, pipeline, report_store
        from backend.config import ProviderConfig
        from backend.dataset_registry import DatasetRegistry
        from backend.ingestion import DatasetIngestor

        db_file = str(root / "data" / "visora.db")
        reports_dir = root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        registry = DatasetRegistry(db_file=db_file, storage_dir=str(root / "data" / "datasets"))
        registry.connect()
        ingestor = DatasetIngestor(db_file=db_file)
        ingestor.connect()

        class FakeProvider:
            name = "RegressionProvider"

            def __init__(self):
                self.calls = 0

            def complete(self, system, prompt):
                self.calls += 1
                return json.dumps(
                    {
                        "summary": "Validated structured summary.",
                        "insights": [],
                        "risks": [],
                        "opportunities": [],
                    }
                )

        provider = FakeProvider()
        provider_config = ProviderConfig(
            slot="provider_1",
            kind="openai_compatible",
            api_key="test-key",
            model="test-model",
            base_url="https://example.invalid/v1",
            label="RegressionProvider",
        )

        real_analyze = pipeline.analyze_dataset
        real_delete = pipeline.delete_dataset_and_report
        real_clear = pipeline.clear_datasets_and_reports
        real_structured_ai = pipeline.generate_structured_ai_insights

        with (
            patch.object(ai_service, "load_provider_chain", return_value=[provider_config]),
            patch.object(ai_service, "build_provider", return_value=provider),
            patch.object(pipeline, "generate_structured_ai_insights", wraps=real_structured_ai) as ai_spy,
            patch.object(pipeline, "analyze_dataset", wraps=real_analyze) as analyze_spy,
            patch.object(pipeline, "delete_dataset_and_report", wraps=real_delete) as delete_spy,
            patch.object(pipeline, "clear_datasets_and_reports", wraps=real_clear) as clear_spy,
        ):
            _backend_lifecycle_checks(
                root, db_file, reports_dir, registry, ingestor, pipeline, report_store,
            )
            analyze_spy.reset_mock()
            ai_spy.reset_mock()
            delete_spy.reset_mock()
            clear_spy.reset_mock()
            provider.calls = 0
            _ui_lifecycle_checks(
                root,
                db_file,
                reports_dir,
                registry,
                ingestor,
                pipeline,
                report_store,
                analyze_spy,
                ai_spy,
                delete_spy,
                clear_spy,
                provider,
            )
    finally:
        os.chdir(old_cwd)
        st.cache_resource.clear()
        st.cache_data.clear()
        gc.collect()
        if registry is not None and getattr(registry, "conn", None) is not None:
            try:
                registry.conn.close()
            except Exception:
                pass
        if ingestor is not None and getattr(ingestor, "conn", None) is not None:
            try:
                ingestor.conn.close()
            except Exception:
                pass
        gc.collect()
        shutil.rmtree(root)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED CHECKS:")
        for name in FAIL:
            print(f" - {name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
