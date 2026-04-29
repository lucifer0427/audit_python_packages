"""Jinja2 Markdown 稽核報告生成模組"""

import logging
from datetime import datetime
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS

from app.config import settings
from app.models.schemas import AuditReport
from app.utils.sanitizer import sanitize_for_table, truncate

logger = logging.getLogger(__name__)

# 初始化 Jinja2 環境
_template_dir = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_template_dir)),
    keep_trailing_newline=True,
)

# 註冊自訂 filter
_env.filters["sanitize"] = sanitize_for_table
_env.filters["truncate_text"] = truncate


def generate_report(report: AuditReport, resolved_reqs: bytes | None = None) -> tuple[Path, Path, Path, Path | None]:
    """生成 Markdown, HTML 與 PDF 稽核報告，以及更新後的 requirements.txt
    
    Args:
        report: 完整稽核報告資料
        resolved_reqs: 解析後的完整相依性內容
    
    Returns:
        (markdown_filepath, html_filepath, pdf_filepath, resolved_reqs_filepath)
    """
    template = _env.get_template("report.md.j2")


    content = template.render(
        report_date=report.report_date,
        source_file=report.source_file,
        total_packages=report.total_packages,
        vuln_count=report.vuln_count,
        python_version=report.python_version,
        platform=report.platform,
        packages=report.packages,
        added_packages=report.added_packages,
    )

    # 建立報告檔案
    reports_dir = settings.REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_security_audit_report.md"

    # 若同日已有報告，加上序號
    filepath = reports_dir / filename
    counter = 1
    while filepath.exists():
        filename = f"{timestamp}_security_audit_report_{counter}.md"
        filepath = reports_dir / filename
        counter += 1

    filepath.write_text(content, encoding="utf-8")
    
    # 將 Markdown 轉為 HTML (僅轉換一次，供 HTML 匯出與 PDF 共用)
    html_content = markdown.markdown(content, extensions=["tables", "fenced_code"])
    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Security Audit Report</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.5.0/github-markdown-light.min.css">
    <style>
        body {{ box-sizing: border-box; min-width: 200px; max-width: 980px; margin: 0 auto; padding: 45px; }}
        .markdown-body {{ box-sizing: border-box; min-width: 200px; max-width: 980px; margin: 0 auto; padding: 45px; }}
        @media print {{ .markdown-body {{ padding: 0; }} }}
    </style>
</head>
<body class="markdown-body">
    {html_content}
</body>
</html>"""
    html_filename = filename.replace(".md", ".html")
    html_filepath = reports_dir / html_filename
    html_filepath.write_text(full_html, encoding="utf-8")

    # 儲存解析後的 requirements.txt
    resolved_reqs_path = None
    if resolved_reqs:
        # 確保使用 .txt 副檔名
        resolved_filename = f"resolved_{filename.replace('.md', '.txt')}"
        resolved_reqs_path = reports_dir / resolved_filename
        resolved_reqs_path.write_bytes(resolved_reqs)
    
    # 產生 PDF 版本 (重用上方已轉換的 html_content)
    pdf_filename = filename.replace(".md", ".pdf")
    pdf_filepath = reports_dir / pdf_filename
    
    # 加入基礎 CSS 樣式讓 PDF 表格比較好看
    pdf_css = CSS(string='''
        @page { size: A4 landscape; margin: 1.5cm; }
        body { font-family: "Noto Sans CJK TC", "Microsoft JhengHei", "PingFang TC", "Helvetica Neue", Helvetica, Arial, sans-serif; font-size: 12px; color: #333; }
        h1, h2, h3 { color: #2c3e50; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f8f9fa; font-weight: bold; }
        tr:nth-child(even) { background-color: #fbfcfd; }
        a { color: #3498db; text-decoration: none; }
        blockquote { border-left: 4px solid #ccc; margin: 0; padding-left: 10px; color: #666; }
    ''')
    
    HTML(string=html_content).write_pdf(pdf_filepath, stylesheets=[pdf_css])
    
    logger.info("報告已生成: MD=%s, HTML=%s, PDF=%s, REQS=%s", filepath.name, html_filepath.name, pdf_filepath.name, resolved_reqs_path.name if resolved_reqs_path else "None")
    return filepath, html_filepath, pdf_filepath, resolved_reqs_path

