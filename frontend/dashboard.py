import hashlib
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.express as px
import pandas as pd

from components.upload import upload_csv
from backend.analyzer import DataAnalyzer
from backend.config import MAX_UPLOAD_SIZE_BYTES, MAX_UPLOAD_SIZE_MB
from backend.insights import generate_insights
from backend.dataset_registry import DatasetRegistry
from backend.ingestion import DatasetIngestor
from backend.pipeline import (
    analyze_dataset as run_pipeline,
    clear_datasets_and_reports,
    delete_dataset_and_report,
)
from backend import report_store
from backend.chart_selection import (
    CHART_TYPES,
    is_chart_type_supported,
    suggest_default_chart_type,
    validate_chart_selection,
)

st.set_page_config(
    page_title="Visora BI",
    page_icon="📊",
    layout="wide"
)


@st.cache_resource
def get_registry():
    registry = DatasetRegistry()
    registry.connect()
    return registry


@st.cache_resource
def get_ingestor():
    ingestor = DatasetIngestor()
    ingestor.connect()
    return ingestor


def _dataset_analysis_signature(dataset):
    """Return immutable inputs that change when this dataset is re-ingested."""
    try:
        stat = Path(dataset["stored_path"]).stat()
        file_signature = f"{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        file_signature = "missing"
    return "|".join(
        str(dataset.get(field) or "")
        for field in ("dataset_id", "sha256", "updated_at", "table_name")
    ) + f"|{file_signature}"


def _invalidate_analysis_cache(dataset_ids=None):
    snapshot = st.session_state.get("analysis_snapshot")
    if not isinstance(snapshot, dict):
        return
    if dataset_ids is None or snapshot.get("dataset_id") in set(dataset_ids):
        st.session_state.pop("analysis_snapshot", None)


def _reset_upload_buffer():
    """Start a fresh uploader widget so a retained upload is not re-registered."""
    st.session_state["upload_widget_version"] = (
        st.session_state.get("upload_widget_version", 0) + 1
    )
    st.session_state["processed_upload_key"] = None
    st.session_state["processed_dataset_id"] = None
    st.session_state["dataset_history_select"] = None


def _select_dataset(dataset_id):
    st.session_state["selected_dataset_id"] = dataset_id


def _request_clear_history():
    st.session_state["confirm_clear_history"] = True


def _cancel_clear_history():
    st.session_state["confirm_clear_history"] = False


def _confirm_clear_history(registry):
    st.session_state["confirm_clear_history"] = False
    try:
        deleted_count = clear_datasets_and_reports(registry=registry)
    except Exception as exc:
        st.session_state["deletion_error"] = f"Could not clear dataset history: {exc}"
        return

    _invalidate_analysis_cache()
    _reset_upload_buffer()
    st.session_state["selected_dataset_id"] = None
    st.session_state["datasets_to_delete"] = []
    st.session_state["pending_dataset_ids"] = []
    st.session_state["deletion_notice"] = (
        f"Deleted {deleted_count} dataset(s), their stored files and tables, "
        "and their associated reports."
    )


def _request_selective_deletion():
    selected_ids = list(st.session_state.get("datasets_to_delete", []))
    if selected_ids:
        st.session_state["pending_dataset_ids"] = selected_ids
        st.session_state["confirm_delete_selected"] = True


def _cancel_selective_deletion():
    st.session_state["confirm_delete_selected"] = False
    st.session_state["pending_dataset_ids"] = []


def _confirm_selective_deletion(registry):
    pending_ids = list(st.session_state.get("pending_dataset_ids", []))
    st.session_state["confirm_delete_selected"] = False
    st.session_state["pending_dataset_ids"] = []
    st.session_state["datasets_to_delete"] = []

    errors = []
    resolved_ids = []
    deleted_count = 0
    for dataset_id in pending_ids:
        try:
            deleted = delete_dataset_and_report(dataset_id, registry=registry)
            resolved_ids.append(dataset_id)
            if deleted is not None:
                deleted_count += 1
        except Exception as exc:
            errors.append(str(exc))

    if resolved_ids:
        _invalidate_analysis_cache(resolved_ids)
        if st.session_state.get("processed_dataset_id") in resolved_ids:
            _reset_upload_buffer()
        if st.session_state.get("selected_dataset_id") in resolved_ids:
            st.session_state["selected_dataset_id"] = None

    if errors:
        st.session_state["deletion_error"] = " ".join(errors)
    elif deleted_count:
        st.session_state["deletion_notice"] = (
            f"Deleted {deleted_count} dataset(s) and their associated reports."
        )
    elif pending_ids:
        st.session_state["deletion_notice"] = (
            "The selected dataset(s) were already absent; no unrelated data was removed."
        )


def _get_or_run_pipeline(dataset, registry):
    """Run the expensive unified pipeline only for a new selected version."""
    dataset_id = dataset["dataset_id"]
    signature = _dataset_analysis_signature(dataset)
    snapshot = st.session_state.get("analysis_snapshot")
    if (
        isinstance(snapshot, dict)
        and snapshot.get("dataset_id") == dataset_id
        and snapshot.get("signature") == signature
    ):
        return snapshot["report"]

    report = run_pipeline(dataset_id, registry=registry)
    st.session_state["analysis_snapshot"] = {
        "dataset_id": dataset_id,
        "signature": signature,
        "report": report,
    }
    return report


registry = get_registry()
ingestor = get_ingestor()

st.session_state.setdefault("processed_upload_key", None)
st.session_state.setdefault("processed_dataset_id", None)
st.session_state.setdefault("upload_widget_version", 0)
st.session_state.setdefault("confirm_clear_history", False)
st.session_state.setdefault("confirm_delete_selected", False)
st.session_state.setdefault("pending_dataset_ids", [])
st.session_state.setdefault("analysis_snapshot", None)

st.title("Visora BI")

if st.session_state.get("deletion_error"):
    st.error(st.session_state.pop("deletion_error"))
if st.session_state.get("deletion_notice"):
    st.success(st.session_state.pop("deletion_notice"))

uploaded_file = upload_csv(
    key=f"csv_uploader_{st.session_state['upload_widget_version']}"
)

if uploaded_file is not None:
    # File-size policy (Day 3): reject anything over the upload cap
    # gracefully -- before it is ever persisted, ingested, or handed to
    # any analytical engine -- rather than letting a huge file crash or
    # stall the app.
    if uploaded_file.size > MAX_UPLOAD_SIZE_BYTES:
        uploaded_mb = uploaded_file.size / (1024 * 1024)
        st.error(
            f"'{uploaded_file.name}' is {uploaded_mb:,.1f} MB, which exceeds the "
            f"{MAX_UPLOAD_SIZE_MB} MB upload limit. Please upload a smaller CSV file."
        )
    else:
        # Persist the upload (Checkpoint 1) and load it into its own SQLite
        # table (Checkpoint 2) so it's available to the analytical engines
        # and survives across reruns/restarts, instead of living only in the
        # Streamlit upload buffer.
        upload_key = hashlib.sha256(uploaded_file.getvalue()).hexdigest()
        if st.session_state.get("processed_upload_key") != upload_key:
            dataset_id = registry.register_upload(uploaded_file.name, uploaded_file)
            dataset = registry.get_dataset(dataset_id)
            ingest_result = ingestor.ingest_csv(dataset["stored_path"], dataset["table_name"])
            registry.update_counts(dataset_id, ingest_result["row_count"], ingest_result["column_count"])
            if not ingest_result["ingested"]:
                st.warning(
                    f"'{dataset['original_filename']}' was saved, but couldn't be loaded for "
                    f"further analysis: {ingest_result['reason']}"
                )
            st.session_state["processed_upload_key"] = upload_key
            st.session_state["processed_dataset_id"] = dataset_id
            st.session_state["selected_dataset_id"] = dataset_id
            st.session_state["dataset_history_select"] = dataset_id

st.sidebar.subheader("Dataset History")
datasets = registry.list_datasets()

selection_was_initialized = "selected_dataset_id" in st.session_state
selected_dataset_id = st.session_state.get("selected_dataset_id")
if datasets:
    dataset_ids = {entry["dataset_id"] for entry in datasets}
    if not selection_was_initialized:
        # Only a genuinely fresh session auto-selects the newest dataset.
        # An explicit None means the user deleted the selected dataset;
        # do not silently analyze a fallback during the delete rerun.
        selected_dataset_id = datasets[0]["dataset_id"]
        st.session_state["selected_dataset_id"] = selected_dataset_id
    elif selected_dataset_id is not None and selected_dataset_id not in dataset_ids:
        _invalidate_analysis_cache([selected_dataset_id])
        selected_dataset_id = None
        st.session_state["selected_dataset_id"] = None

    for dataset in datasets:
        dataset_id = dataset["dataset_id"]
        st.sidebar.button(
            dataset["original_filename"],
            key=f"dataset_history_{dataset_id}",
            type="primary" if dataset_id == selected_dataset_id else "secondary",
            use_container_width=True,
            on_click=_select_dataset,
            args=(dataset_id,),
        )
else:
    if selected_dataset_id is not None:
        _invalidate_analysis_cache([selected_dataset_id])
        selected_dataset_id = None
        st.session_state["selected_dataset_id"] = None
    st.sidebar.info("No datasets yet. Upload a CSV to get started.")

st.sidebar.button(
    "Clear History",
    key="clear_history_btn",
    use_container_width=True,
    on_click=_request_clear_history,
)

if st.session_state.get("confirm_clear_history"):
    st.sidebar.warning("Permanently delete all saved datasets and files?")
    confirm_col, cancel_col = st.sidebar.columns(2)
    confirm_col.button(
        "Confirm",
        type="primary",
        key="confirm_clear_history_btn",
        use_container_width=True,
        on_click=_confirm_clear_history,
        args=(registry,),
    )
    cancel_col.button(
        "Cancel",
        key="cancel_clear_history_btn",
        use_container_width=True,
        on_click=_cancel_clear_history,
    )

if datasets:
    st.sidebar.markdown("---")
    st.sidebar.caption("Selective deletion")
    dataset_labels = {
        dataset["dataset_id"]: dataset["original_filename"] for dataset in datasets
    }
    datasets_to_delete = st.sidebar.multiselect(
        "Select datasets to delete",
        options=list(dataset_labels.keys()),
        format_func=lambda dataset_id: dataset_labels.get(dataset_id, dataset_id),
        key="datasets_to_delete",
    )
    st.sidebar.button(
        "Delete Selected",
        key="delete_selected_btn",
        disabled=not datasets_to_delete,
        use_container_width=True,
        on_click=_request_selective_deletion,
    )

    pending_dataset_ids = st.session_state.get("pending_dataset_ids", [])
    if st.session_state.get("confirm_delete_selected") and pending_dataset_ids:
        st.sidebar.warning(
            f"Permanently delete {len(pending_dataset_ids)} selected dataset(s) "
            "and their reports?"
        )
        del_confirm_col, del_cancel_col = st.sidebar.columns(2)
        del_confirm_col.button(
            "Confirm",
            type="primary",
            key="confirm_delete_selected_btn",
            use_container_width=True,
            on_click=_confirm_selective_deletion,
            args=(registry,),
        )
        del_cancel_col.button(
            "Cancel",
            key="cancel_delete_selected_btn",
            use_container_width=True,
            on_click=_cancel_selective_deletion,
        )

analyzer = None
selected_dataset = None
if selected_dataset_id:
    # Selecting a dataset from history loads it straight from persisted
    # local storage -- no re-upload required.
    selected_dataset = registry.get_dataset(selected_dataset_id)
    if selected_dataset is None:
        missing_dataset_id = selected_dataset_id
        selected_dataset_id = None
        st.session_state["selected_dataset_id"] = None
        _invalidate_analysis_cache([missing_dataset_id])

if selected_dataset is not None:
    analyzer = DataAnalyzer(selected_dataset["stored_path"])
    analyzer.load_data()
    analyzer.get_basic_information()
    analyzer.get_quality_checks()
    analyzer.get_other_details()
    st.sidebar.caption(f"Analyzing: {selected_dataset['original_filename']}")

if selected_dataset is not None:
    st.info(f"Analyzing: {selected_dataset['original_filename']}")
else:
    st.info("No dataset selected - upload a CSV to begin analysis.")

st.caption("Turn messy business data into clear decisions.")

st.divider()

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Rows",
        len(analyzer.df) if analyzer is not None else "—"
    )

with col2:
    st.metric(
        "Columns",
        len(analyzer.columns) if analyzer is not None else "—"
    )

with col3:
    st.metric(
        "Missing Values",
        analyzer.total_missing_values if analyzer is not None else "—"
    )

with col4:
    st.metric(
        "Duplicate Rows",
        analyzer.duplicate_rows if analyzer is not None else "—"
    )

st.divider()

left, right = st.columns([2, 1])

with left:
    st.subheader("Dataset Overview")
    if analyzer is not None:
        st.dataframe(analyzer.get_column_health(), width="stretch")
    else:
        st.info("Upload a CSV file to begin analysis.")

with right:
    st.markdown("---")
    st.subheader("Data Health")

    if analyzer is not None:
        total_rows = max(len(analyzer.df), 1)
        total_cells = max(len(analyzer.df) * len(analyzer.df.columns), 1)

        missing_ratio = analyzer.total_missing_values / total_cells
        duplicate_ratio = analyzer.duplicate_rows / total_rows
        empty_row_ratio = analyzer.completely_empty_rows / total_rows

        quality_score = 100
        quality_score -= missing_ratio * 50
        quality_score -= duplicate_ratio * 30
        quality_score -= empty_row_ratio * 20

        quality_score = round(max(quality_score, 0), 1)

        st.metric("Data Quality Score", f"{quality_score}/100")

        if (
            analyzer.total_missing_values == 0
            and analyzer.duplicate_rows == 0
            and analyzer.completely_empty_rows == 0
        ):
            st.write("Dataset looks healthy.")
        else:
            st.write("Dataset needs attention.")

        st.metric("Duplicate Rows", analyzer.duplicate_rows)
        st.metric("Completely Empty Rows", analyzer.completely_empty_rows)
    else:
        st.info("Upload a CSV file to assess data health.")

st.divider()
st.subheader("Analytical Insights")

if analyzer is None:
    st.info("Upload a CSV file to view analytical insights.")
else:
    insights = generate_insights(analyzer)
    if insights:
        insight_columns = st.columns(len(insights))
        for insight_column, insight in zip(insight_columns, insights):
            with insight_column:
                with st.container(border=True):
                    st.markdown(f"**{insight['title']}**")
                    if insight["type"] == "success":
                        st.success(insight["message"])
                    elif insight["type"] == "warning":
                        st.warning(insight["message"])
                    else:
                        st.info(insight["message"])
    else:
        st.info("No analytical insights are available for this dataset.")

st.divider()
st.subheader("Primary Charts")

if analyzer is None:
    st.info("Upload a CSV file to view structural charts.")
else:
    chart_left, chart_right = st.columns(2)

    with chart_left:
        st.markdown("**Category distribution**")
        if analyzer.categorical_columns:
            selected_category = st.selectbox(
                "Categorical column",
                analyzer.categorical_columns,
                key=f"primary_category_column_{selected_dataset_id}"
            )
            chart_data = analyzer.get_categorical_distributions()[selected_category]

            if not chart_data:
                st.info(f"No values are available for {selected_category}.")
            else:
                figure = px.bar(
                    chart_data,
                    x="Category",
                    y="Frequency",
                    title=f"Frequency by {selected_category}"
                )
                st.plotly_chart(figure, width="stretch")
        else:
            st.info("No categorical columns are available.")

    with chart_right:
        st.markdown("**Numeric statistics**")
        if analyzer.numeric_columns:
            numeric_statistics = analyzer.get_numeric_statistics()
            if numeric_statistics:
                chart_data = pd.DataFrame(numeric_statistics).melt(
                    id_vars="Column",
                    value_vars=["Mean", "Median"],
                    var_name="Statistic",
                    value_name="Value"
                ).dropna(subset=["Value"])

            if not numeric_statistics or chart_data.empty:
                st.info("No numeric values are available for statistics.")
            else:
                figure = px.bar(
                    chart_data,
                    x="Column",
                    y="Value",
                    color="Statistic",
                    barmode="group",
                    title="Mean and median by numeric column"
                )
                st.plotly_chart(figure, width="stretch")
        else:
            st.info("No numeric columns are available.")

final_report = None
if selected_dataset is not None:
    # One backend call produces one complete structured intelligence
    # result (Day 4). The session snapshot reuses it across unrelated
    # widget reruns and reruns automatically when this dataset's immutable
    # version signature changes.
    final_report = _get_or_run_pipeline(selected_dataset, registry)

st.divider()
st.subheader("Prioritized Findings")
st.caption(
    "Evidence-based, deterministic priority (Critical/High/Medium/Low) -- "
    "AI explains these findings, it never decides their priority."
)

if selected_dataset is None or final_report is None:
    st.info("Upload or select a dataset to view prioritized findings.")
elif final_report["status"] != "success":
    st.error(final_report.get("error") or "This dataset could not be analyzed.")
else:
    findings = final_report.get("prioritized_findings") or []
    if not findings:
        st.info("No notable findings were detected for this dataset.")
    else:
        priority_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        for finding in findings:
            icon = priority_icon.get(finding.get("priority"), "⚪")
            st.markdown(f"{icon} **{finding.get('priority', 'low').upper()}** -- {finding.get('title')}")

st.divider()
st.subheader("Business Insights (AI)")
st.caption(
    "AI explains VISORA's own calculated metrics, trends, contribution, and "
    "anomaly results -- it never calculates business numbers on its own."
)

if selected_dataset is None or final_report is None:
    st.info("Upload or select a dataset to view AI-generated business insights.")
elif final_report["status"] != "success":
    st.error(final_report.get("error") or "This dataset could not be analyzed.")
else:
    ai_analysis = final_report.get("ai_analysis") or {}

    if ai_analysis.get("source") == "ai":
        st.success(f"Generated by {ai_analysis.get('provider_used')}")
    else:
        skipped_reason = ai_analysis.get("ai_skipped_reason")
        if skipped_reason == "size_threshold_exceeded":
            st.info(
                "This dataset is larger than the AI context threshold, so these "
                "insights were generated directly from VISORA's analytical engine "
                "without sending data to an AI provider."
            )
        elif skipped_reason == "not_configured":
            st.info(
                "No AI provider is configured. Showing insights generated directly "
                "from VISORA's analytical engine."
            )
        else:
            st.warning(
                "AI providers are currently unavailable. VISORA generated these "
                "insights from its analytical engine instead:"
            )

    st.markdown(ai_analysis.get("summary") or "No summary available.")

    if ai_analysis.get("risks"):
        with st.expander("Risks", expanded=False):
            for risk in ai_analysis["risks"]:
                st.write(f"- {risk}")

    if ai_analysis.get("opportunities"):
        with st.expander("Opportunities", expanded=False):
            for opportunity in ai_analysis["opportunities"]:
                st.write(f"- {opportunity}")

st.divider()
st.subheader("Reports")

if selected_dataset is None or final_report is None:
    st.info("Upload or select a dataset to export its report.")
elif final_report["status"] != "success":
    st.error(final_report.get("error") or "This dataset could not be analyzed.")
else:
    # The TXT report is dataset-specific and is written when this
    # dataset version is actually analyzed -- never a shared/generic filename, and
    # it disappears once this dataset (or its report) no longer
    # exists, per Day 4's report-lifecycle requirements. The raw
    # reports/ folder is never exposed directly; this download button
    # is the only user-facing access path to it.
    txt_path = report_store.txt_report_path(selected_dataset)
    if txt_path.exists():
        st.download_button(
            "Download TXT Report",
            data=txt_path.read_text(encoding="utf-8"),
            file_name=txt_path.name,
            mime="text/plain",
            use_container_width=True,
            on_click="ignore",
        )
    else:
        st.info("No TXT report is available for this dataset yet.")

st.divider()
st.subheader("Chart Explorer")

if analyzer is None:
    st.info("Upload a CSV file to build a chart.")
else:
    date_columns = analyzer.date_columns
    categorical_columns = analyzer.categorical_columns
    numeric_columns = analyzer.numeric_columns

    default_chart_type = suggest_default_chart_type(date_columns, categorical_columns, numeric_columns)
    chart_type = st.selectbox(
        "Chart Type",
        CHART_TYPES,
        index=CHART_TYPES.index(default_chart_type),
        key=f"chart_type_select_{selected_dataset_id}",
    )

    if not is_chart_type_supported(chart_type, date_columns, categorical_columns, numeric_columns):
        supported, reason = validate_chart_selection(chart_type)
        st.info(reason or f"{chart_type} charts aren't supported for this dataset's columns.")
    elif chart_type == "Line":
        x_column = st.selectbox(
            "Date column", date_columns, key=f"chart_line_x_{selected_dataset_id}"
        )
        y_column = st.selectbox(
            "Measure", numeric_columns, key=f"chart_line_y_{selected_dataset_id}"
        )
        supported, reason = validate_chart_selection(chart_type, numeric_columns_selected=1, has_date=True)
        if not supported:
            st.info(reason)
        else:
            chart_data = analyzer.df[[x_column, y_column]].dropna().sort_values(x_column)
            if chart_data.empty:
                st.info("No data is available to plot for this selection.")
            else:
                figure = px.line(chart_data, x=x_column, y=y_column, title=f"{y_column} over {x_column}")
                st.plotly_chart(figure, width="stretch")
    elif chart_type in ("Bar", "Pie"):
        x_column = st.selectbox(
            "Category", categorical_columns, key=f"chart_cat_x_{selected_dataset_id}"
        )
        y_column = st.selectbox(
            "Measure", numeric_columns, key=f"chart_cat_y_{selected_dataset_id}"
        )
        supported, reason = validate_chart_selection(chart_type, numeric_columns_selected=1, has_category=True)
        if not supported:
            st.info(reason)
        else:
            grouped = analyzer.df.groupby(x_column, dropna=False)[y_column].sum().reset_index()
            if grouped.empty:
                st.info("No data is available to plot for this selection.")
            elif chart_type == "Bar":
                figure = px.bar(grouped, x=x_column, y=y_column, title=f"{y_column} by {x_column}")
                st.plotly_chart(figure, width="stretch")
            else:
                figure = px.pie(grouped, names=x_column, values=y_column, title=f"{y_column} share by {x_column}")
                st.plotly_chart(figure, width="stretch")
    elif chart_type == "Scatter":
        x_column = st.selectbox(
            "X (numeric)", numeric_columns, key=f"chart_scatter_x_{selected_dataset_id}"
        )
        remaining_numeric = [c for c in numeric_columns if c != x_column] or numeric_columns
        y_column = st.selectbox(
            "Y (numeric)", remaining_numeric, key=f"chart_scatter_y_{selected_dataset_id}"
        )
        supported, reason = validate_chart_selection(chart_type, numeric_columns_selected=2)
        if not supported:
            st.info(reason)
        else:
            chart_data = analyzer.df[[x_column, y_column]].dropna()
            if chart_data.empty:
                st.info("No data is available to plot for this selection.")
            else:
                figure = px.scatter(chart_data, x=x_column, y=y_column, title=f"{y_column} vs. {x_column}")
                st.plotly_chart(figure, width="stretch")

st.divider()
st.subheader("Backend Analysis (Day 1 verification)")
st.caption(
    "Raw output of the unified backend pipeline "
    "(backend/pipeline.py, built on backend/analysis_context.py), for manual verification only."
)

if selected_dataset is None or final_report is None:
    st.info("Upload or select a dataset to see backend analysis output.")
else:
    st.write(f"Dataset: {selected_dataset['original_filename']}")

    with st.expander("Capabilities", expanded=True):
        st.json(final_report["capabilities"])

    with st.expander("Metrics"):
        st.json(final_report["metrics"])

    with st.expander("Trends"):
        st.json(final_report["trends"])

    with st.expander("Contribution"):
        st.json(final_report["contribution"])

    with st.expander("Anomalies"):
        st.json(final_report["anomalies"])

    with st.expander("Evidence"):
        st.json(final_report["evidence"])

    with st.expander("Prioritized findings"):
        st.json(final_report["prioritized_findings"])

    with st.expander("Full unified report (JSON)"):
        st.json(final_report)