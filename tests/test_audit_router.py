from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings

client = TestClient(app)

def test_upload_no_file():
    response = client.post("/api/audit")
    assert response.status_code == 422 # FastAPI validation error for missing field

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
        # Setup the mock instance and its run_audit_flow method
        mock_instance = MockAuditService.return_value
        mock_instance.run_audit_flow = AsyncMock(return_value=mock_result)
        
        # Inject http_client into app state
        from app.main import app
        from unittest.mock import MagicMock
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

def test_download_report_path_traversal(tmp_path):
    with patch("app.routers.audit.settings") as mock_settings:
        mock_settings.REPORTS_DIR = tmp_path
        
        # Try to access parent directory
        response = client.get("/api/reports/../etc/passwd")
        # Will likely return 403 or 404 depending on how it resolves
        assert response.status_code in [403, 404]

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
