import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.express as px
import pandas as pd

from components.upload import upload_csv
from backend.analyzer import DataAnalyzer
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
    # Persist the upload (Checkpoint 1) and load it into its own SQLite
    # table (Checkpoint 2) so it's available to the analytical engines
    # and survives across reruns/restarts, instead of living only in the
    # Streamlit upload buffer.
    dataset_id = registry.register_upload(uploaded_file.name, uploaded_file)
    dataset = registry.get_dataset(dataset_id)
    ingest_result = ingestor.ingest_csv(dataset["stored_path"], dataset["table_name"])
    registry.update_counts(dataset_id, ingest_result["row_count"], ingest_result["column_count"])
    if not ingest_result["ingested"]:
        st.warning(
            f"'{dataset['original_filename']}' was saved, but couldn't be loaded for "
            f"further analysis: {ingest_result['reason']}"
        )
    st.session_state["selected_dataset_id"] = dataset_id

st.sidebar.subheader("Dataset History")
datasets = registry.list_datasets()

selected_dataset_id = None
if datasets:
    dataset_ids = [entry["dataset_id"] for entry in datasets]
    dataset_labels = {
        entry["dataset_id"]: (
            f'{entry["original_filename"]} '
            f'({entry["created_at"][:19].replace("T", " ")})'
        )
        for entry in datasets
    }
    remembered_id = st.session_state.get("selected_dataset_id")
    default_index = dataset_ids.index(remembered_id) if remembered_id in dataset_ids else 0
    selected_dataset_id = st.sidebar.selectbox(
        "Load a previous dataset",
        dataset_ids,
        index=default_index,
        format_func=lambda dataset_id: dataset_labels.get(dataset_id, dataset_id),
        key="dataset_history_select"
    )
    st.session_state["selected_dataset_id"] = selected_dataset_id
else:
    st.sidebar.info("No datasets yet. Upload a CSV to get started.")

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
    st.subheader("Quick Actions")
    st.button("Upload Dataset")

    st.markdown("---")
    st.subheader("Data Health")

    if analyzer is not None:
        quality_score = 100
        quality_score -= analyzer.total_missing_values
        quality_score -= analyzer.duplicate_rows * 2
        quality_score -= analyzer.completely_empty_rows * 5
        quality_score = max(quality_score, 0)

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