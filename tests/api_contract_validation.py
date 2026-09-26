"""Contract validation for the FastAPI adapter (api/main.py).

Runs entirely inside a temporary sandbox: nothing in the real registry,
stored datasets, or reports/ directory is touched. Verifies that the API
is a thin transport layer over the existing backend and that failures are
human-readable JSON, never raw tracebacks.
"""

import gc
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PASS = []
FAIL = []


def check(name, condition, detail=""):
    if condition:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}" + (f" -- {detail}" if detail else ""))


def _csv_bytes():
    rows = ["Date,Region,Product,Units,Revenue"]
    regions = ["North", "South"]
    products = ["Alpha", "Beta"]
    units = [12, 18, 22, 31, 27, 35, 41, 38, 47, 52, 49, 58]
    for index, month in enumerate(range(1, 13)):
        for offset, region in enumerate(regions):
            for product_index, product in enumerate(products):
                value = units[(index + offset + product_index) % len(units)]
                rows.append(
                    f"2024-{month:02d}-{(index % 27) + 1:02d},{region},{product},"
                    f"{value},{value * (850 + product_index * 90)}"
                )
    return ("\n".join(rows) + "\n").encode("utf-8")


def main():
    old_cwd = Path.cwd()
    temp_base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Temp" / "opencode"
    temp_base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="visora_api_", dir=temp_base))
    os.chdir(root)

    try:
        from fastapi.testclient import TestClient

        from api.main import app
        from backend import report_store

        (root / "data").mkdir(parents=True, exist_ok=True)
        (root / "reports").mkdir(parents=True, exist_ok=True)

        with TestClient(app, raise_server_exceptions=False) as client:
            # ------------------------------------------------ health
            response = client.get("/api/v1/health")
            payload = response.json()
            check("API health returns 200 operational", response.status_code == 200 and payload.get("status") == "operational", str(payload)[:200])
            check("API health reports upload limit", payload.get("uploadLimitBytes", 0) > 0)
            check("API health reports AI mode without secrets", payload.get("ai", {}).get("mode") in {"local_fallback", "provider_chain"} and "api_key" not in json.dumps(payload))

            # ---------------------------------------------- empty state
            response = client.get("/api/v1/datasets")
            check("API dataset list is empty in sandbox", response.json().get("datasets") == [])
            response = client.get("/api/v1/overview")
            overview = response.json()
            check("API overview reports no analysis yet", overview.get("available") is False and overview.get("reason") == "no_analysis_yet", str(overview)[:200])

            # ---------------------------------------------- upload
            response = client.post(
                "/api/v1/datasets",
                files={"file": ("regional_sales.csv", _csv_bytes(), "text/csv")},
            )
            upload = response.json()
            check("API CSV upload returns 201/200 with dataset", response.status_code in {200, 201} and upload.get("dataset", {}).get("id"), str(upload)[:300])
            dataset_id = upload.get("dataset", {}).get("id")
            check("API CSV upload marks dataset ready", upload.get("dataset", {}).get("status") == "ready")
            check("API CSV upload has no warning for a good file", upload.get("warning") is None)

            # ---------------------------------------------- list + detail
            response = client.get("/api/v1/datasets")
            listed = response.json().get("datasets", [])
            check("API dataset list contains the upload", len(listed) == 1 and listed[0].get("id") == dataset_id)
            check("API dataset rows reflect ingested content", (listed[0].get("rowCount") or 0) > 0, str(listed[0]))

            response = client.get(f"/api/v1/datasets/{dataset_id}")
            detail = response.json()
            check("API dataset detail returns profile", response.status_code == 200 and detail.get("profile", {}).get("available") is True, str(detail)[:300])
            check("API dataset detail returns preview columns", len(detail.get("profile", {}).get("previewColumns", [])) >= 4)
            check("API dataset detail returns preview rows", len(detail.get("profile", {}).get("preview") or []) > 0)
            check("API dataset detail exposes quality metrics", isinstance(detail.get("profile", {}).get("quality"), dict))

            # ---------------------------------------------- analysis
            response = client.post(f"/api/v1/datasets/{dataset_id}/analyze")
            report = response.json().get("report", {})
            check("API analysis runs the unified pipeline", response.status_code == 200 and report.get("status") == "success", str(report.get("error"))[:300])
            check("API analysis carries prioritized findings", isinstance(report.get("prioritized_findings"), list) and len(report.get("prioritized_findings")) > 0)
            check("API analysis carries evidence", isinstance(report.get("evidence"), list) and len(report.get("evidence")) > 0)
            check("API analysis carries AI layer shape", isinstance(report.get("ai_analysis"), dict) and "summary" in report.get("ai_analysis"))
            check("API analysis targets the uploaded dataset", (report.get("dataset") or {}).get("dataset_id") == dataset_id)

            # ---------------------------------------------- reports
            response = client.get("/api/v1/reports")
            reports = response.json()
            check("API report list includes the TXT report", len(reports.get("reports", [])) == 1 and reports["reports"][0].get("kind") == "text", str(reports)[:300])
            check("API report list includes current unified report", (reports.get("current") or {}).get("kind") == "unified")

            response = client.get("/api/v1/reports/current")
            check("API current report returns unified JSON", response.status_code == 200 and response.json().get("status") == "success")

            response = client.get(f"/api/v1/reports/{dataset_id}/text")
            check("API TXT report downloads", response.status_code == 200 and "VISORA" in response.text and response.headers.get("content-type", "").startswith("text/plain"))

            # ---------------------------------------------- insights + overview
            response = client.get("/api/v1/insights")
            insights = response.json()
            check("API insights available after analysis", insights.get("available") is True and isinstance(insights.get("summary"), str), str(insights)[:300])
            check("API insights expose findings and evidence", isinstance(insights.get("findings"), list) and isinstance(insights.get("evidence"), list))
            check("API insights expose risks/opportunities lists", isinstance(insights.get("risks"), list) and isinstance(insights.get("opportunities"), list))

            response = client.get("/api/v1/overview")
            overview = response.json()
            check("API overview now available", overview.get("available") is True, str(overview)[:300])
            check("API overview KPIs are shaped for the UI", len(overview.get("kpis", [])) == 4 and all("label" in k and "value" in k for k in overview.get("kpis", [])))
            check("API overview includes trend series", isinstance(overview.get("trend", {}).get("series"), list))
            check("API overview includes contribution series", isinstance(overview.get("contribution", {}).get("series"), list), str(overview.get("contribution"))[:200])

            # ---------------------------------------------- error mapping
            response = client.post(
                "/api/v1/datasets",
                files={"file": ("notes.txt", b"hello world", "text/plain")},
            )
            error = response.json().get("error", {})
            check("API rejects non-CSV with 400", response.status_code == 400 and error.get("code") == "unsupported_file_type", str(response.json())[:300])
            check("API rejection message is human-readable", "csv" in (error.get("message") or "").lower(), str(error))

            response = client.get("/api/v1/datasets/does-not-exist")
            error = response.json().get("error", {})
            check("API missing dataset returns 404 envelope", response.status_code == 404 and error.get("code") == "dataset_not_found", str(response.json())[:300])

            binary = bytes(range(256)) * 8
            response = client.post(
                "/api/v1/datasets",
                files={"file": ("binary.csv", binary, "text/csv")},
            )
            malformed = response.json()
            check("API malformed CSV upload does not 500", response.status_code in {200, 201}, str(malformed)[:300])
            if response.status_code in {200, 201}:
                malformed_id = malformed.get("dataset", {}).get("id")
                check("API malformed CSV flagged needs_attention", malformed.get("dataset", {}).get("status") == "needs_attention" and bool(malformed.get("warning")), str(malformed)[:300])
                response = client.post(f"/api/v1/datasets/{malformed_id}/analyze")
                report = response.json().get("report", {})
                check("API analyzing malformed CSV yields structured error report", response.status_code == 200 and report.get("status") != "success" and bool(report.get("error")), str(report)[:300])
                client.delete(f"/api/v1/datasets/{malformed_id}")

            # ---------------------------------------------- Excel upload
            import pandas as pd

            xlsx_path = root / "regional_sales.xlsx"
            frame = pd.read_csv(io.BytesIO(_csv_bytes()))
            frame.to_excel(xlsx_path, index=False)
            response = client.post(
                "/api/v1/datasets",
                files={
                    "file": (
                        "regional_sales.xlsx",
                        xlsx_path.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
            xlsx_upload = response.json()
            check("API Excel upload returns 200 with dataset", response.status_code in {200, 201} and xlsx_upload.get("dataset", {}).get("id"), str(xlsx_upload)[:300])
            xlsx_id = xlsx_upload.get("dataset", {}).get("id")
            check("API Excel upload marks dataset ready", xlsx_upload.get("dataset", {}).get("status") == "ready" and (xlsx_upload.get("dataset", {}).get("rowCount") or 0) > 0, str(xlsx_upload)[:300])
            if xlsx_id:
                response = client.get(f"/api/v1/datasets/{xlsx_id}")
                check("API Excel dataset detail profiles successfully", response.status_code == 200 and response.json().get("profile", {}).get("available") is True, str(response.json())[:300])
                response = client.post(f"/api/v1/datasets/{xlsx_id}/analyze")
                report = response.json().get("report", {})
                check("API Excel analysis runs the unified pipeline", response.status_code == 200 and report.get("status") == "success", str(report.get("error"))[:300])
                response = client.delete(f"/api/v1/datasets/{xlsx_id}")
                check("API Excel dataset deletes cleanly", response.status_code == 200 and response.json().get("deleted") is True)

            # ---------------------------------------------- delete + clear
            txt_path = report_store.txt_report_path(
                {"dataset_id": dataset_id, "original_filename": "regional_sales.csv"}
            )
            response = client.delete(f"/api/v1/datasets/{dataset_id}")
            deletion = response.json()
            check("API delete returns confirmation", response.status_code == 200 and deletion.get("deleted") is True and deletion.get("removed_reports") >= 1, str(deletion))
            check("API delete removes the TXT report", not Path(txt_path).exists())
            check("API delete removes current report snapshot", report_store.load_current_json() is None)
            response = client.get(f"/api/v1/datasets/{dataset_id}")
            check("API delete makes dataset 404", response.status_code == 404)

            client.post("/api/v1/datasets", files={"file": ("regional_sales.csv", _csv_bytes(), "text/csv")})
            reuploaded = client.get("/api/v1/datasets").json().get("datasets", [])
            if reuploaded:
                client.post(f"/api/v1/datasets/{reuploaded[0]['id']}/analyze")
            response = client.post("/api/v1/history/clear")
            cleared = response.json()
            check("API clear history reports counts", response.status_code == 200 and cleared.get("deleted_datasets") == 1 and cleared.get("deleted_reports") >= 1, str(cleared))
            response = client.get("/api/v1/datasets")
            check("API clear history empties the registry", response.json().get("datasets") == [])
            response = client.get("/api/v1/reports/current")
            check("API clear history removes current report", response.status_code == 404)

            # ---------------------------------------------- contract hygiene
            openapi = client.get("/openapi.json").json()
            paths = openapi.get("paths", {})
            expected = [
                "/api/v1/health",
                "/api/v1/overview",
                "/api/v1/datasets",
                "/api/v1/datasets/{dataset_id}",
                "/api/v1/datasets/{dataset_id}/analyze",
                "/api/v1/reports",
                "/api/v1/reports/current",
                "/api/v1/reports/{dataset_id}/text",
                "/api/v1/history/clear",
                "/api/v1/insights",
            ]
            missing = [p for p in expected if p not in paths]
            check("API OpenAPI document exposes every public route", not missing, str(missing))
    finally:
        os.chdir(old_cwd)
        gc.collect()
        shutil.rmtree(root, ignore_errors=True)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED CHECKS:")
        for name in FAIL:
            print(f"  - {name}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
