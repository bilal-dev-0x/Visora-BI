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


def page_status_text(app):
    """Collect visible dataset-status text from the dashboard."""
    parts = []

    for element in app.caption:
        parts.append(str(element.value))

    for element in app.info:
        parts.append(str(element.value))

    return "\n".join(parts)


def sidebar_warning_text(app):
    """Collect sidebar warning messages."""
    return "\n".join(
        str(element.value)
        for element in app.sidebar.warning
    )


def main():
    # ------------------------------------------------------------------
    # Create isolated sandbox
    # ------------------------------------------------------------------
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)

    shutil.copytree(
        REPO_ROOT,
        SANDBOX,
        ignore=shutil.ignore_patterns(".git", "tests", "data"),
    )

    (SANDBOX / "data").mkdir()

    os.chdir(SANDBOX)
    sys.path.insert(0, str(SANDBOX))

    from streamlit.testing.v1 import AppTest

    # ------------------------------------------------------------------
    # 1. First run with no datasets
    # ------------------------------------------------------------------
    app = AppTest.from_file(
        str(SANDBOX / "frontend" / "dashboard.py"),
        default_timeout=30,
    )
    app.run()

    check(
        "CP4: dashboard runs with no exceptions on first load",
        len(app.exception) == 0,
    )

    check(
        "CP4: sidebar shows 'no datasets yet' before any upload",
        any(
            "No datasets yet" in info.value
            for info in app.sidebar.info
        ),
    )

    # ------------------------------------------------------------------
    # 2. Create dataset A and B
    # ------------------------------------------------------------------
    from backend.dataset_registry import DatasetRegistry
    from backend.ingestion import DatasetIngestor
    import pandas as pd

    registry = DatasetRegistry(
        db_file=str(SANDBOX / "data" / "visora.db"),
        storage_dir=str(SANDBOX / "data" / "datasets"),
    )
    registry.connect()

    ingestor = DatasetIngestor(
        db_file=str(SANDBOX / "data" / "visora.db")
    )
    ingestor.connect()

    # Dataset A
    csv_a = SANDBOX / "data" / "a.csv"

    pd.DataFrame(
        {
            "Order Date": ["2024-01-01", "2024-02-01"],
            "Category": ["Office", "Tech"],
            "Sales": [100, 200],
        }
    ).to_csv(csv_a, index=False)

    dataset_id_a = registry.register_upload(
        "a.csv",
        csv_a,
    )

    meta_a = registry.get_dataset(dataset_id_a)

    ingestor.ingest_csv(
        meta_a["stored_path"],
        meta_a["table_name"],
    )

    # Dataset B
    csv_b = SANDBOX / "data" / "b.csv"

    pd.DataFrame(
        {
            "Employee": ["Alice", "Bob"],
            "Salary": [90000, 95000],
        }
    ).to_csv(csv_b, index=False)

    dataset_id_b = registry.register_upload(
        "b.csv",
        csv_b,
    )

    meta_b = registry.get_dataset(dataset_id_b)

    ingestor.ingest_csv(
        meta_b["stored_path"],
        meta_b["table_name"],
    )

    # ------------------------------------------------------------------
    # 3. Fresh dashboard run with persisted datasets
    # ------------------------------------------------------------------
    app2 = AppTest.from_file(
        str(SANDBOX / "frontend" / "dashboard.py"),
        default_timeout=30,
    )
    app2.run()

    check(
        "CP4: dashboard runs with no exceptions after datasets exist",
        len(app2.exception) == 0,
    )

    # New UI uses direct sidebar buttons instead of a selectbox.
    sidebar_button_labels = [
        button.label
        for button in app2.sidebar.button
    ]

    check(
        "CP4: dataset history uses direct sidebar buttons",
        "a.csv" in sidebar_button_labels
        and "b.csv" in sidebar_button_labels,
    )

    check(
        "CP4: persisted dataset A appears in history",
        "a.csv" in sidebar_button_labels,
    )

    check(
        "CP4: persisted dataset B appears in history",
        "b.csv" in sidebar_button_labels,
    )

    # Most recently uploaded dataset should be active.
    status_text = page_status_text(app2)

    check(
        "CP4: active dataset status shows B",
        "Analyzing: b.csv" in status_text,
    )

    check(
        "CP4: no-dataset state is not shown when datasets exist",
        "No dataset selected" not in status_text,
    )

    # ------------------------------------------------------------------
    # 4. Switch B -> A
    # ------------------------------------------------------------------
    a_button = next(
        (
            button
            for button in app2.sidebar.button
            if button.label == "a.csv"
        ),
        None,
    )

    check(
        "CP4: dataset A history button is available",
        a_button is not None,
    )

    if a_button is not None:
        a_button.click().run()

    check(
        "CP4: switching dataset via sidebar button runs cleanly",
        len(app2.exception) == 0,
    )

    status_after_switch = page_status_text(app2)

    check(
        "CP4: active dataset status changes to A",
        "Analyzing: a.csv" in status_after_switch,
    )

    # Confirm the dashboard actually switched to A.
    row_metric = None

    if app2.columns:
        for column in app2.columns:
            for metric in column.metric:
                if metric.label == "Rows":
                    row_metric = metric.value
                    break

            if row_metric is not None:
                break

    check(
        "CP4: selecting A shows A's row count (2)",
        str(row_metric) == "2",
    )

    # ------------------------------------------------------------------
    # 5. Clear History confirmation
    # ------------------------------------------------------------------
    clear_button = next(
        (
            button
            for button in app2.sidebar.button
            if button.label == "Clear History"
        ),
        None,
    )

    check(
        "CP4: Clear History button is present",
        clear_button is not None,
    )

    if clear_button is not None:
        clear_button.click().run()

    check(
        "CP4: clear history confirmation is shown",
        "Permanently delete all saved datasets and files?"
        in sidebar_warning_text(app2),
    )

    # The confirmation buttons are inside sidebar columns, so inspect
    # the sidebar column button elements rather than sidebar.button.
    confirm_button = None

    for column in app2.sidebar.columns:
        for button in column.button:
            if button.label == "Confirm":
                confirm_button = button
                break
        if confirm_button is not None:
            break

    check(
        "CP4: clear history confirmation button is present",
        confirm_button is not None,
    )

    if confirm_button is not None:
        confirm_button.click().run()

    check(
        "CP4: clear history completes without exceptions",
        len(app2.exception) == 0,
    )

    # After confirmation the app reruns and should immediately return
    # to the empty history state.
    check(
        "CP4: history returns to empty state immediately",
        any(
            "No datasets yet" in info.value
            for info in app2.sidebar.info
        ),
    )

    final_status = page_status_text(app2)

    check(
        "CP4: active dataset is cleared immediately",
        "No dataset selected" in final_status,
    )
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
