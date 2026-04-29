import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.models.schemas import AuditReport, AuditResult
from app.services.report_generator import generate_report

def test_generate_report(tmp_path):
    with patch("app.services.report_generator.settings") as mock_settings:
        mock_settings.REPORTS_DIR = tmp_path
        with patch("app.services.report_generator.HTML") as mock_html:
            report = AuditReport(
                report_date="2023-10-27 12:00:00",
                source_file="req.txt",
                total_packages=1,
                vuln_count=0,
                packages=[
                    AuditResult(
                        index=1,
                        name="requests",
                        version="2.31.0",
                        summary_en="HTTP",
                        summary_zh="HTTP"
                    )
                ],
                added_packages=["urllib3"]
            )
            md, html, pdf, reqs = generate_report(report, b"requests==2.31.0\nurllib3==2.0.0")
    
    assert md.exists()
    assert md.name.endswith(".md")
    assert html.exists()
    assert pdf.name.endswith(".pdf")
    assert reqs is not None
    assert reqs.exists()
    assert "urllib3" in md.read_text("utf-8")
    assert "<html" in html.read_text("utf-8")
    mock_html.assert_called_once()

def test_generate_report_collision(tmp_path):
    with patch("app.services.report_generator.settings") as mock_settings:
        mock_settings.REPORTS_DIR = tmp_path
        with patch("app.services.report_generator.HTML"), \
             patch("app.services.report_generator.datetime") as mock_datetime:
            
            # Fix timestamp to force collision
            fixed_now = MagicMock()
            fixed_now.strftime.return_value = "20230101_120000"
            mock_datetime.now.return_value = fixed_now
            
            report = AuditReport(
                report_date="2023-10-27 12:00:00",
                source_file="req.txt",
                total_packages=1,
                vuln_count=0,
                packages=[],
                added_packages=[]
            )
            
            # Create first report
            md1, _, _, _ = generate_report(report)
            assert md1.name == "20230101_120000_security_audit_report.md"
            
            # Create second report with same timestamp
            md2, _, _, _ = generate_report(report)
            assert md2.name == "20230101_120000_security_audit_report_1.md"
            assert md1.exists()
            assert md2.exists()
