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


def generate_report(report: AuditReport) -> tuple[Path, Path]:
    """生成 Markdown 與 PDF 稽核報告

    Args:
        report: 完整稽核報告資料

    Returns:
        (markdown_filepath, pdf_filepath)
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
    )

    # 建立報告檔案
    reports_dir = settings.REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"{timestamp}_security_audit_report.md"

    # 若同日已有報告，加上序號
    filepath = reports_dir / filename
    counter = 1
    while filepath.exists():
        filename = f"{timestamp}_security_audit_report_{counter}.md"
        filepath = reports_dir / filename
        counter += 1

    filepath.write_text(content, encoding="utf-8")
    
    # 產生 PDF 版本
    pdf_filename = filename.replace(".md", ".pdf")
    pdf_filepath = reports_dir / pdf_filename
    
    # 將 Markdown 轉為 HTML (啟用 tables 等擴充套件)
    html_content = markdown.markdown(content, extensions=["tables", "fenced_code"])
    
    # 加入基礎 CSS 樣式讓 PDF 表格比較好看
    pdf_css = CSS(string='''
        @page { size: A4 landscape; margin: 1.5cm; }
        body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; font-size: 12px; color: #333; }
        h1, h2, h3 { color: #2c3e50; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f8f9fa; font-weight: bold; }
        tr:nth-child(even) { background-color: #fbfcfd; }
        a { color: #3498db; text-decoration: none; }
        blockquote { border-left: 4px solid #ccc; margin: 0; padding-left: 10px; color: #666; }
    ''')
    
    HTML(string=html_content).write_pdf(pdf_filepath, stylesheets=[pdf_css])

    logger.info("報告已生成: MD=%s, PDF=%s", filepath.name, pdf_filepath.name)
    return filepath, pdf_filepath
