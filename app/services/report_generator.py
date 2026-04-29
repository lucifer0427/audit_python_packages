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
    
    本函數負責將稽核結果物件轉化為可閱讀的最終文件。
    產出流程：Jinja2 模板渲染 $\to$ Markdown 檔案 $\to$ Markdown 轉 HTML $\to$ HTML 轉 PDF。
    
    Args:
        report: 包含所有稽核數據的 AuditReport 模型
        resolved_reqs: 解析後的完整遞迴相依性內容，用於提供下載
    
    Returns:
        (markdown_filepath, html_filepath, pdf_filepath, resolved_reqs_filepath)
    """
    # 1. 渲染 Markdown
    # 使用 Jinja2 模板將數據注入 report.md.j2，生成專業格式的 Markdown 文本
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

    # 2. 儲存 Markdown 檔案
    reports_dir = settings.REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 使用時間戳記作為檔名，避免多個使用者上傳時檔案衝突
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_security_audit_report.md"

    # 處理極端情況：若同一秒內產生多份報告，則加上序號 (_1, _2 ...)
    filepath = reports_dir / filename
    counter = 1
    while filepath.exists():
        filename = f"{timestamp}_security_audit_report_{counter}.md"
        filepath = reports_dir / filename
        counter += 1

    filepath.write_text(content, encoding="utf-8")
    
    # 3. 轉換為 HTML 格式
    # 使用 markdown 函式庫將 MD 轉為 HTML，並包裹在包含 GitHub-style CSS 的完整 HTML 頁面中
    # 這使得報告在瀏覽器中開啟時具有極佳的視覺效果
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

    # 4. 儲存解析後的 requirements.txt
    # 將 uv 解析出的完整依賴清單儲存為檔案，讓使用者可以下載並直接用於環境部署
    resolved_reqs_path = None
    if resolved_reqs:
        resolved_filename = f"resolved_{filename.replace('.md', '.txt')}"
        resolved_reqs_path = reports_dir / resolved_filename
        resolved_reqs_path.write_bytes(resolved_reqs)
    
    # 5. 生成 PDF 版本
    # 利用 WeasyPrint 將 HTML 內容渲染成 PDF。
    # 特別定義了 pdf_css 以確保 A4 橫向輸出 (landscape)，並配置 Noto Sans CJK TC 字型以防止中文破版。
    pdf_filename = filename.replace(".md", ".pdf")
    pdf_filepath = reports_dir / pdf_filename
    
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


