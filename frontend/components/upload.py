import streamlit as st


def upload_csv(key=None):
    uploaded_file = st.file_uploader(
        "Upload your CSV file",
        type=["csv"],
        key=key,
    )

    return uploaded_file