"""
Persistent local dataset registry (Day 15 / Checkpoint 1).

Responsibilities of this module -- and only this module:
    * give every uploaded CSV a collision-safe unique identity (dataset_id)
    * persist the raw uploaded file to local disk under data/datasets/
    * record metadata about it (original filename, stored path, row/column
      counts, timestamps) in a `datasets` table inside the existing
      data/visora.db SQLite database

It does NOT parse business data into analytical tables -- that is
backend/ingestion.py's job (Checkpoint 2). Keeping the two separate means
a dataset can be registered (and browsable in "Dataset History") even if
ingestion into an analytical table later fails or is skipped.
"""

import hashlib
import re
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_SAFE_STEM_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _sanitize_stem(stem):
    """Turn an arbitrary filename stem into a filesystem-safe fragment.
    Uniqueness is never derived from this -- it's purely cosmetic, so the
    physical filename stays human-recognizable."""
    stem = _SAFE_STEM_RE.sub("_", stem).strip("_")
    return stem or "dataset"


class DatasetRegistry:
    def __init__(self, db_file="data/visora.db", storage_dir="data/datasets"):
        self.db_file = db_file
        self.storage_dir = Path(storage_dir)
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
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        Path(self.db_file).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_file, timeout=30)
        self._ensure_schema()
        return self.conn

    def _ensure_schema(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                table_name TEXT NOT NULL,
                sha256 TEXT,
                row_count INTEGER,
                column_count INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    @staticmethod
    def table_name_for(dataset_id):
        """Deterministically derive a safe SQLite table identifier from a
        dataset_id (a UUID4 string). Never derived from the original
        filename -- see backend/sql_safety.py for why that matters."""
        return "ds_" + dataset_id.replace("-", "")

    def register_upload(self, original_filename, source, row_count=None, column_count=None):
        """Persist an uploaded file to collision-safe local storage and
        record its metadata. `source` may be a filesystem path (str/Path),
        raw bytes, or a file-like object (e.g. Streamlit's UploadedFile).

        Returns the new dataset_id. Never overwrites an existing dataset:
        every call creates a brand new physical file and metadata row,
        even if `original_filename` repeats a previous upload.
        """
        dataset_id = str(uuid.uuid4())
        stem = _sanitize_stem(Path(str(original_filename)).stem)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        stored_filename = f"{stem}_{timestamp}_{dataset_id}.csv"
        stored_path = self.storage_dir / stored_filename

        self._write_source(source, stored_path)

        sha256 = hashlib.sha256(stored_path.read_bytes()).hexdigest()

        if row_count is None or column_count is None:
            row_count, column_count = self._count_rows_and_columns(stored_path)

        now = datetime.now(timezone.utc).isoformat()
        table_name = self.table_name_for(dataset_id)

        self.conn.execute(
            """
            INSERT INTO datasets (
                dataset_id, original_filename, stored_filename, stored_path,
                table_name, sha256, row_count, column_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_id,
                str(original_filename),
                stored_filename,
                str(stored_path),
                table_name,
                sha256,
                row_count,
                column_count,
                now,
                now,
            ),
        )
        self.conn.commit()
        return dataset_id

    @staticmethod
    def _write_source(source, stored_path):
        if hasattr(source, "read"):
            if hasattr(source, "seek"):
                try:
                    source.seek(0)
                except (OSError, ValueError):
                    pass
            data = source.read()
            if isinstance(data, str):
                data = data.encode("utf-8")
            stored_path.write_bytes(data)
        elif isinstance(source, (bytes, bytearray)):
            stored_path.write_bytes(bytes(source))
        else:
            shutil.copyfile(source, stored_path)

    @staticmethod
    def _count_rows_and_columns(csv_path):
        import pandas as pd

        try:
            frame = pd.read_csv(csv_path)
        except pd.errors.EmptyDataError:
            return 0, 0
        return int(len(frame)), int(len(frame.columns))

    def update_counts(self, dataset_id, row_count, column_count):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE datasets SET row_count = ?, column_count = ?, updated_at = ? "
            "WHERE dataset_id = ?",
            (row_count, column_count, now, dataset_id),
        )
        self.conn.commit()

    def list_datasets(self):
        cursor = self.conn.execute("SELECT * FROM datasets ORDER BY created_at DESC")
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_dataset(self, dataset_id):
        cursor = self.conn.execute(
            "SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [description[0] for description in cursor.description]
        return dict(zip(columns, row))
