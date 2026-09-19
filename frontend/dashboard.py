import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.express as px

from components.upload import upload_csv
from backend.analyzer import DataAnalyzer

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
        st.dataframe(analyzer.get_column_health(), use_container_width=True)
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