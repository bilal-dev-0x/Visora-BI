"""
CSV -> SQLite dataset ingestion (Day 15 / Checkpoint 2).

Takes a persisted CSV file (already registered by DatasetRegistry) and
loads it into its own SQLite table, named after the dataset_id
(ds_<uuid hex>), so the analytical engines have a concrete table to
query. This is intentionally independent of DataAnalyzer: DataAnalyzer
stays the structural/data-quality layer (Day 14), this module is the
persistence layer that feeds the analytical engines (Checkpoint 3).

Type handling:
    * integer / float columns keep their pandas dtype -> INTEGER / REAL
    * object columns that look like dates (a large majority parse
      cleanly) are converted to datetimes and stored as ISO text
    * everything else is stored as TEXT
    * NaN / NaT / +-inf are all normalized to SQL NULL on insert

Every uploaded dataset gets its own table, so re-ingesting a dataset_id
only ever replaces that dataset's own table -- it can never touch another
dataset's data or the legacy `sales` table.
"""

import sqlite3
import threading

import numpy as np
import pandas as pd

from backend.sql_safety import quote_identifier, safe_table_name

_DATE_LIKE_SUCCESS_RATIO = 0.9


def _infer_sqlite_type(series):
    if pd.api.types.is_bool_dtype(series):
        return "INTEGER"
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "TEXT"
    return "TEXT"


def _try_parse_dates(series):
    """Best-effort, schema-agnostic date detection for an object column.
    Only converts the column if a large majority of its non-null values
    parse cleanly as dates -- otherwise it is left untouched as text, so
    a column like "Product Code" full of a few date-shaped values isn't
    silently coerced."""
    non_null = series.dropna()
    if non_null.empty:
        return series
    parsed_non_null = pd.to_datetime(non_null, errors="coerce", format="mixed")
    success_ratio = parsed_non_null.notna().mean()
    if success_ratio >= _DATE_LIKE_SUCCESS_RATIO:
        return pd.to_datetime(series, errors="coerce", format="mixed")
    return series


def prepare_dataframe_for_sqlite(df):
    """Return a copy of df with generic type inference applied. Does not
    mutate the original DataFrame."""
    prepared = df.copy()
    for column in prepared.columns:
        if prepared[column].dtype == object:
            prepared[column] = _try_parse_dates(prepared[column])
        if pd.api.types.is_float_dtype(prepared[column]):
            prepared[column] = prepared[column].replace([np.inf, -np.inf], np.nan)
    return prepared


class DatasetIngestor:
    def __init__(self, db_file="data/visora.db"):
        self.db_file = db_file
        self._thread_state = threading.local()
        self.conn = None

    @property
    def conn(self):
        connection = getattr(self._thread_state, "connection", None)
        if connection is None:
            self.connect()
            connection = self._thread_state.connection
        return connection

    @conn.setter
    def conn(self, connection):
        self._thread_state.connection = connection

    def connect(self):
        self.conn = sqlite3.connect(self.db_file, timeout=30)
        return self.conn

    def ingest_csv(self, csv_path, table_name):
        """Load csv_path into table_name, replacing any existing content
        of that table. Never raises on an empty/header-only/malformed
        CSV -- returns a result dict describing what happened instead."""
        table_name = safe_table_name(table_name)

        try:
            raw = pd.read_csv(csv_path)
        except pd.errors.EmptyDataError:
            return {
                "ingested": False,
                "reason": "The file has no header or content to ingest.",
                "row_count": 0,
                "column_count": 0,
            }

        if raw.shape[1] == 0:
            return {
                "ingested": False,
                "reason": "The file has no columns to ingest.",
                "row_count": 0,
                "column_count": 0,
            }

        prepared = prepare_dataframe_for_sqlite(raw)
        self._create_table(prepared, table_name)
        self._insert(prepared, table_name)

        return {
            "ingested": True,
            "reason": None,
            "row_count": int(len(prepared)),
            "column_count": int(len(prepared.columns)),
        }

    def _create_table(self, df, table_name):
        cursor = self.conn.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS {quote_identifier(table_name)}")
        columns_sql = ", ".join(
            f"{quote_identifier(column)} {_infer_sqlite_type(df[column])}"
            for column in df.columns
        )
        cursor.execute(f"CREATE TABLE {quote_identifier(table_name)} ({columns_sql})")
        self.conn.commit()

    def _insert(self, df, table_name):
        if df.empty:
            return
        insertable = df.copy()
        for column in insertable.columns:
            if pd.api.types.is_datetime64_any_dtype(insertable[column]):
                is_null = insertable[column].isna()
                insertable[column] = insertable[column].dt.strftime("%Y-%m-%d %H:%M:%S")
                insertable.loc[is_null, column] = None
        insertable = insertable.astype(object).where(pd.notnull(insertable), None)
        insertable.to_sql(table_name, self.conn, if_exists="append", index=False)

    def drop_table(self, table_name):
        table_name = safe_table_name(table_name)
        self.conn.execute(f"DROP TABLE IF EXISTS {quote_identifier(table_name)}")
        self.conn.commit()
