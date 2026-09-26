"""Format-aware table readers for the upload types VISORA supports.

Ingestion (backend/ingestion.py), row/column counting
(backend/dataset_registry.py), and the structural data-quality pass
(backend/analyzer.py) all need to turn a persisted upload into a pandas
DataFrame. Dispatching on the stored file's extension in ONE place keeps
that decision in the backend -- the API/UI layer never parses data
itself -- and means a new format only has to be taught here.

Supported formats come from backend/config.py::SUPPORTED_UPLOAD_EXTENSIONS
so there is a single declared list of what VISORA accepts.
"""

from pathlib import Path

import pandas as pd

from backend.config import SUPPORTED_UPLOAD_EXTENSIONS

SUPPORTED_EXTENSIONS = frozenset(
    f".{str(extension).lstrip('.').lower()}" for extension in SUPPORTED_UPLOAD_EXTENSIONS
)
EXCEL_EXTENSIONS = frozenset({".xlsx", ".xlsm"})
CSV_EXTENSIONS = SUPPORTED_EXTENSIONS - EXCEL_EXTENSIONS


class UnreadableFileError(Exception):
    """A file with a supported extension could not be parsed into a table.

    The message is intentionally user-facing: callers surface it as the
    human-readable `reason` on a failed ingestion instead of raising a
    raw parser exception at the UI.
    """


def normalize_suffix(suffix, default: str = ".csv") -> str:
    """Map an arbitrary filename suffix to a supported one (defaulting
    to .csv) so persisted storage always keeps a readable, dispatchable
    extension."""
    value = str(suffix or "").strip().lower()
    if value and not value.startswith("."):
        value = f".{value}"
    return value if value in SUPPORTED_EXTENSIONS else default


def read_table(path):
    """Read `path` into a DataFrame using the reader for its extension.

    Raises :class:`pd.errors.EmptyDataError` unchanged (callers give it
    a specific "no header or content" message) and wraps every other
    parse failure in :class:`UnreadableFileError`.
    """
    suffix = Path(str(path)).suffix.lower()

    if suffix in EXCEL_EXTENSIONS:
        try:
            return pd.read_excel(path, engine="openpyxl")
        except pd.errors.EmptyDataError:
            raise
        except ImportError as exc:  # pragma: no cover - openpyxl is a dependency
            raise UnreadableFileError(
                "Excel support needs the openpyxl package. Install it, or upload a CSV file."
            ) from exc
        except Exception as exc:
            raise UnreadableFileError(
                "The Excel file could not be read. Check that it is a valid .xlsx workbook."
            ) from exc

    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        raise
    except Exception as exc:
        # Covers content that isn't actually CSV -- e.g. a binary file
        # (xlsx/pdf/image/...) saved or renamed with a .csv extension.
        raise UnreadableFileError(
            "The file could not be read as CSV. VISORA supports CSV and Excel (.xlsx) files."
        ) from exc
