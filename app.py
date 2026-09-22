"""
Streamlit entry point for Visora BI.

`streamlit run app.py` launches the full dashboard defined in
frontend/dashboard.py. That file remains the single source of truth
for the UI -- this file does not duplicate or reimplement any of its
logic, it only launches it, so `streamlit run app.py` and
`streamlit run frontend/dashboard.py` render the exact same app.

The previous terminal-only execution flow that used to live here
(running the analytical engines directly against data/sales_data.csv
and printing results to stdout) has been relocated to
scripts/cli_report.py, so it no longer runs on Streamlit app startup.
Run it directly with:
    python scripts/cli_report.py
"""

import runpy
import sys
from pathlib import Path

DASHBOARD_PATH = Path(__file__).resolve().parent / "frontend" / "dashboard.py"

# When Streamlit runs frontend/dashboard.py directly, it puts that
# file's own directory (frontend/) on sys.path, which is how
# dashboard.py's "from components.upload import upload_csv" resolves.
# Running it via runpy from the repo root does not do that
# automatically, so it's added here -- this is the one adjustment
# needed to launch the same, unmodified dashboard from a different
# entry script.
frontend_dir = str(DASHBOARD_PATH.parent)
if frontend_dir not in sys.path:
    sys.path.insert(0, frontend_dir)

runpy.run_path(str(DASHBOARD_PATH), run_name="__main__")
