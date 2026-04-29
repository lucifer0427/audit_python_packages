import os
from pathlib import Path

from unittest.mock import patch

from app.models.schemas import AuditReport, AuditResult
from app.services.report_generator import generate_report

def test_generate_report(tmp_path):
    # Mock settings.REPORTS_DIR
    with patch("app.services.report_generator.settings") as mock_settings:
        mock_settings.REPORTS_DIR = tmp_path
        
        # Mock WeasyPrint HTML to avoid system dependencies
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
    
    # Check content
    md_content = md.read_text("utf-8")
    assert "urllib3" in md_content
    
    html_content = html.read_text("utf-8")
    assert "<html" in html_content
    
    # WeasyPrint should have been called
    mock_html.assert_called_once()
