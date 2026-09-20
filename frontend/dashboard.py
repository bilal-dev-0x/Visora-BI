import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.express as px
import pandas as pd

from components.upload import upload_csv
from backend.analyzer import DataAnalyzer
from backend.insights import generate_insights

st.set_page_config(
    page_title="Visora BI",
    page_icon="📊",
    layout="wide"
)

st.title("Visora BI")
uploaded_file = upload_csv()
analyzer = None
if uploaded_file is not None:
    analyzer = DataAnalyzer(uploaded_file)
    analyzer.load_data()
    analyzer.get_basic_information()
    analyzer.get_quality_checks()
    analyzer.get_other_details()
st.caption("Turn messy business data into clear decisions.")

st.divider()

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Rows",
        len(analyzer.df) if uploaded_file is not None else "—"
    )

with col2:
    st.metric(
        "Columns",
        len(analyzer.columns) if uploaded_file is not None else "—"
    )

with col3:
    st.metric(
        "Missing Values",
        analyzer.total_missing_values if uploaded_file is not None else "—"
    )

with col4:
    st.metric(
        "Duplicate Rows",
        analyzer.duplicate_rows if uploaded_file is not None else "—"
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