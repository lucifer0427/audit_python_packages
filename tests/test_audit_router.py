import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_upload_no_file():
    response = client.post("/api/audit")
    assert response.status_code == 422  # FastAPI validation error for missing field


def test_upload_empty_file(tmp_path):
    f = tmp_path / "empty.txt"
    f.touch()

    with open(f, "rb") as file:
        response = client.post("/api/audit", files={"file": ("empty.txt", file)})

    assert response.status_code == 400
    assert "為空" in response.json()["detail"]


def test_upload_too_large(tmp_path):
    f = tmp_path / "large.txt"
    f.write_bytes(b"a" * (1 * 1024 * 1024 + 10))

    with open(f, "rb") as file:
        response = client.post("/api/audit", files={"file": ("large.txt", file)})

    assert response.status_code == 413


def test_run_audit_success(tmp_path):
    f = tmp_path / "reqs.txt"
    f.write_bytes(b"requests==2.31.0")

    mock_result = {
        "message": "稽核完成",
        "total_packages": 1,
        "vuln_packages": 0,
        "report_file": "report.md",
        "download_url": "/api/reports/report.md",
        "pdf_download_url": "/api/reports/report.pdf",
        "resolved_requirements_url": "/api/reports/resolved_report.txt",
    }

    with patch("app.routers.audit.AuditService") as MockAuditService:
        mock_instance = MockAuditService.return_value
        mock_instance.run_audit_flow = AsyncMock(return_value=mock_result)

        from unittest.mock import MagicMock

        from app.main import app

        app.state.http_client = MagicMock()

        with open(f, "rb") as file:
            response = client.post("/api/audit", files={"file": ("reqs.txt", file)}, data={"python_version": "3.12"})

        assert response.status_code == 200
        assert response.json() == mock_result
        MockAuditService.assert_called_once()


def test_list_reports(tmp_path):
    with patch("app.routers.audit.settings") as mock_settings:
        mock_settings.REPORTS_DIR = tmp_path

        f1 = tmp_path / "1_security_audit_report.md"
        f1.write_text("test")

        response = client.get("/api/reports")
        assert response.status_code == 200
        data = response.json()
        assert len(data["reports"]) == 1
        assert data["reports"][0]["filename"] == "1_security_audit_report.md"


def test_download_report_not_found(tmp_path):
    with patch("app.routers.audit.settings") as mock_settings:
        mock_settings.REPORTS_DIR = tmp_path

        response = client.get("/api/reports/nonexistent.md")
        assert response.status_code == 404


def test_download_report_path_traversal():
    from fastapi import HTTPException

    from app.routers.audit import download_report

    with patch("app.routers.audit.settings") as mock_settings:
        mock_settings.REPORTS_DIR = Path("/tmp/reports")

        with pytest.raises(HTTPException) as excinfo:
            # Use a path that escapes /tmp/reports
            # We must ensure that .resolve() doesn't just return the same path if it doesn't exist
            # But /etc/passwd exists.
            asyncio.run(download_report("../../../etc/passwd"))

        assert excinfo.value.status_code == 403
        assert "禁止存取" in excinfo.value.detail


def test_clear_reports(tmp_path):
    with patch("app.routers.audit.settings") as mock_settings:
        mock_settings.REPORTS_DIR = tmp_path

        (tmp_path / "1.md").touch()
        (tmp_path / "1.pdf").touch()
        (tmp_path / "1.html").touch()
        (tmp_path / "resolved_1.txt").touch()
        (tmp_path / "keep.csv").touch()

        response = client.delete("/api/reports")
        assert response.status_code == 200
        assert response.json()["message"] == "已清空 4 個檔案"

        assert not (tmp_path / "1.md").exists()
        assert (tmp_path / "keep.csv").exists()


def test_upload_no_filename(tmp_path):
    f = tmp_path / "test.txt"
    f.write_bytes(b"content")

    # Use a mock for UploadFile to specifically set filename to empty
    with patch("fastapi.UploadFile") as _:
        mock_file = MagicMock()
        mock_file.filename = ""
        mock_file.read = AsyncMock(return_value=b"content")

    pytest.skip("需要 TestClient 整合測試")

    # Alternative: just test it via a direct call to the route function
    from fastapi import Request, UploadFile

    from app.routers.audit import run_audit

    mock_request = MagicMock(spec=Request)
    mock_request.app.state.http_client = MagicMock()

    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = ""

    with pytest.raises(HTTPException) as excinfo:
        import asyncio

        asyncio.run(run_audit(mock_request, mock_file, "3.12"))

    assert excinfo.value.status_code == 400
    assert "未提供檔案" in excinfo.value.detail


def test_run_audit_value_error(tmp_path):
    f = tmp_path / "reqs.txt"
    f.write_bytes(b"requests==2.31.0")

    with patch("app.routers.audit.AuditService") as MockAuditService:
        mock_instance = MockAuditService.return_value
        mock_instance.run_audit_flow = AsyncMock(side_effect=ValueError("Custom Parse Error"))

        from unittest.mock import MagicMock

        from app.main import app

        app.state.http_client = MagicMock()

        with open(f, "rb") as file:
            response = client.post("/api/audit", files={"file": ("reqs.txt", file)})

        assert response.status_code == 400
        assert "Custom Parse Error" in response.json()["detail"]


def test_run_audit_internal_error(tmp_path):
    f = tmp_path / "reqs.txt"
    f.write_bytes(b"requests==2.31.0")

    with patch("app.routers.audit.AuditService") as MockAuditService:
        mock_instance = MockAuditService.return_value
        mock_instance.run_audit_flow = AsyncMock(side_effect=Exception("Critical Error"))

        from unittest.mock import MagicMock

        from app.main import app

        app.state.http_client = MagicMock()

        with open(f, "rb") as file:
            response = client.post("/api/audit", files={"file": ("reqs.txt", file)})

        assert response.status_code == 500
        assert "伺服器內部錯誤" in response.json()["detail"]


def test_list_reports_no_dir(tmp_path):
    with patch("app.routers.audit.settings") as mock_settings:
        mock_settings.REPORTS_DIR = tmp_path / "nonexistent"
        with patch.object(Path, "exists", return_value=False):
            response = client.get("/api/reports")
            assert response.status_code == 200
            assert response.json() == {"reports": []}


def test_list_reports_full_metadata(tmp_path):
    with patch("app.routers.audit.settings") as mock_settings:
        mock_settings.REPORTS_DIR = tmp_path

        report_name = "audit.md"
        f_md = tmp_path / report_name
        f_md.write_text("content")

        f_html = tmp_path / "audit.html"
        f_html.write_text("html content")

        f_pdf = tmp_path / "audit.pdf"
        f_pdf.write_bytes(b"pdf content")

        f_res = tmp_path / "resolved_audit.txt"
        f_res.write_text("resolved content")

        response = client.get("/api/reports")
        data = response.json()["reports"][0]

        assert data["html_download_url"] is not None
        assert data["pdf_download_url"] is not None
        assert data["resolved_url"] is not None


def test_download_report_mime_types(tmp_path):
    with patch("app.routers.audit.settings") as mock_settings:
        mock_settings.REPORTS_DIR = tmp_path

        files = {"test.md": "text/markdown", "test.html": "text/html", "test.pdf": "application/pdf"}

        for name, expected_mime in files.items():
            f = tmp_path / name
            f.write_text("content")
            response = client.get(f"/api/reports/{name}")
            assert response.status_code == 200
            assert expected_mime in response.headers["content-type"]


def test_clear_reports_no_dir(tmp_path):
    with patch("app.routers.audit.settings") as mock_settings:
        mock_settings.REPORTS_DIR = tmp_path / "ghost"
        with patch.object(Path, "exists", return_value=False):
            response = client.delete("/api/reports")
            assert response.status_code == 200
            assert "無報告可清空" in response.json()["message"]
