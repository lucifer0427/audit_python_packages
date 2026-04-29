import subprocess
import json
from unittest.mock import patch, MagicMock
import pytest
from app.services import pip_audit_runner
from app.models.schemas import VulnerabilityInfo

def test_run_pip_audit_success_with_vulns():
    mock_stdout = json.dumps({
        "dependencies": [
            {
                "name": "requests",
                "vulns": [
                    {"id": "CVE-1", "description": "Vuln 1 description"}
                ]
            },
            {
                "name": "django",
                "vulns": []
            }
        ]
    })
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout=mock_stdout, stderr="")
        results = pip_audit_runner.run_pip_audit("requests==2.31.0")
        
        assert "requests" in results
        assert len(results["requests"]) == 1
        assert results["requests"][0].vuln_id == "CVE-1"
        assert "django" not in results

def test_run_pip_audit_success_no_vulns():
    mock_stdout = json.dumps({
        "dependencies": [
            {"name": "requests", "vulns": []}
        ]
    })
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_stdout, stderr="")
        results = pip_audit_runner.run_pip_audit("requests==2.31.0")
        assert results == {}

def test_run_pip_audit_unexpected_return_code():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="Some error")
        results = pip_audit_runner.run_pip_audit("requests==2.31.0")
        assert results == {}

def test_run_pip_audit_empty_stdout():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="  ", stderr="")
        results = pip_audit_runner.run_pip_audit("requests==2.31.0")
        assert results == {}

def test_run_pip_audit_json_decode_error():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="invalid json", stderr="")
        results = pip_audit_runner.run_pip_audit("requests==2.31.0")
        assert results == {}

def test_run_pip_audit_timeout():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pip-audit", timeout=300)):
        results = pip_audit_runner.run_pip_audit("requests==2.31.0")
        assert results == {}

def test_run_pip_audit_file_not_found():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        results = pip_audit_runner.run_pip_audit("requests==2.31.0")
        assert results == {}
