import hashlib
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.express as px
import pandas as pd

from components.upload import upload_csv
from backend.analyzer import DataAnalyzer
from backend.analysis_context import analyze_dataset
from backend.ai_service import generate_ai_insights
from backend.config import MAX_UPLOAD_SIZE_BYTES, MAX_UPLOAD_SIZE_MB
from backend.insights import generate_insights
from backend.dataset_registry import DatasetRegistry
from backend.ingestion import DatasetIngestor

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


registry = get_registry()
ingestor = get_ingestor()

st.title("Visora BI")

uploaded_file = upload_csv()

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
            st.session_state["selected_dataset_id"] = dataset_id
            st.session_state["dataset_history_select"] = dataset_id

st.sidebar.subheader("Dataset History")
datasets = registry.list_datasets()

selected_dataset_id = st.session_state.get("selected_dataset_id")
if datasets:
    dataset_ids = {entry["dataset_id"] for entry in datasets}
    if selected_dataset_id not in dataset_ids:
        selected_dataset_id = datasets[0]["dataset_id"]
        st.session_state["selected_dataset_id"] = selected_dataset_id

    for dataset in datasets:
        dataset_id = dataset["dataset_id"]
        if st.sidebar.button(
            dataset["original_filename"],
            key=f"dataset_history_{dataset_id}",
            type="primary" if dataset_id == selected_dataset_id else "secondary",
            use_container_width=True,
        ):
            st.session_state["selected_dataset_id"] = dataset_id
            st.rerun()
else:
    st.sidebar.info("No datasets yet. Upload a CSV to get started.")

if st.sidebar.button("Clear History", use_container_width=True):
    st.session_state["confirm_clear_history"] = True

if st.session_state.get("confirm_clear_history"):
    st.sidebar.warning("Permanently delete all saved datasets and files?")
    confirm_col, cancel_col = st.sidebar.columns(2)
    if confirm_col.button("Confirm", type="primary", use_container_width=True):
        registry.clear_datasets()
        st.session_state["selected_dataset_id"] = None
        st.session_state["processed_upload_key"] = None
        st.session_state["confirm_clear_history"] = False
        st.rerun()
    if cancel_col.button("Cancel", use_container_width=True):
        st.session_state["confirm_clear_history"] = False
        st.rerun()

analyzer = None
selected_dataset = None
if selected_dataset_id:
    # Selecting a dataset from history loads it straight from persisted
    # local storage -- no re-upload required.
    selected_dataset = registry.get_dataset(selected_dataset_id)
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
                key="primary_category_column"
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

analysis_context = None
if selected_dataset is not None:
    # Computed once here and reused by both the AI Business Insights
    # section below and the raw backend-verification section further
    # down, so the dataset is only run through the analytical
    # orchestration layer a single time per rerun.
    analysis_context = analyze_dataset(
        selected_dataset["table_name"],
        selected_dataset["stored_path"],
        dataset_metadata=selected_dataset,
    )

st.divider()
st.subheader("Business Insights (AI)")
st.caption(
    "AI explains VISORA's own calculated metrics, trends, contribution, and "
    "anomaly results -- it never calculates business numbers on its own."
)

if selected_dataset is None or analysis_context is None:
    st.info("Upload or select a dataset to view AI-generated business insights.")
else:
    file_size_bytes = Path(selected_dataset["stored_path"]).stat().st_size
    ai_result = generate_ai_insights(analysis_context, file_size_bytes=file_size_bytes)

    if ai_result.source == "ai":
        st.success(f"Generated by {ai_result.provider_used}")
        st.markdown(ai_result.text)
    else:
        if ai_result.ai_skipped_reason == "size_threshold_exceeded":
            st.info(
                "This dataset is larger than the AI context threshold, so these "
                "insights were generated directly from VISORA's analytical engine "
                "without sending data to an AI provider."
            )
        elif ai_result.ai_skipped_reason == "not_configured":
            st.info(
                "No AI provider is configured. Showing insights generated directly "
                "from VISORA's analytical engine."
            )
        else:
            st.warning(
                "AI providers are currently unavailable. VISORA generated these "
                "insights from its analytical engine instead:"
            )
        st.markdown(ai_result.text)

        if ai_result.attempts:
            with st.expander("Provider attempt details"):
                for attempt in ai_result.attempts:
                    st.caption(f"{attempt.provider_name}: {attempt.category} -- {attempt.message}")

st.divider()
st.subheader("Backend Analysis (Day 1 verification)")
st.caption(
    "Raw output of the new backend orchestration layer "
    "(backend/analysis_context.py), for manual verification only."
)

if selected_dataset is None or analysis_context is None:
    st.info("Upload or select a dataset to see backend analysis output.")
else:
    st.write(f"Dataset: {selected_dataset['original_filename']}")

    with st.expander("Capabilities", expanded=True):
        st.json(analysis_context["capabilities"])

    with st.expander("Metrics"):
        st.json(analysis_context["metrics"])

    with st.expander("Trends"):
        st.json(analysis_context["trends"])

    with st.expander("Contribution"):
        st.json(analysis_context["contribution"])

    with st.expander("Anomalies"):
        st.json(analysis_context["anomalies"])

    with st.expander("Full analytical context (JSON)"):
        st.json(analysis_context)