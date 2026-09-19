import streamlit as st


def upload_csv():
    uploaded_file = st.file_uploader(
        "Upload your CSV file",
        type=["csv"]
    )

    return uploaded_file