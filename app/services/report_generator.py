"""Jinja2 Markdown 稽核報告生成模組"""

import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

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


def generate_report(report: AuditReport) -> Path:
    """生成 Markdown 稽核報告

    Args:
        report: 完整稽核報告資料

    Returns:
        報告檔案路徑
    """
    template = _env.get_template("report.md.j2")

    content = template.render(
        report_date=report.report_date,
        source_file=report.source_file,
        total_packages=report.total_packages,
        vuln_count=report.vuln_count,
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
    logger.info("報告已生成: %s", filepath)
    return filepath
