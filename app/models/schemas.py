"""Pydantic 資料模型定義"""

from pydantic import BaseModel


class PackageInfo(BaseModel):
    """解析自 requirements.txt 的套件資訊"""

    name: str
    version: str | None = None
    version_spec: str | None = None  # 原始版本規格 (==, >=, ~= 等)


class VulnerabilityInfo(BaseModel):
    """漏洞資訊"""

    vuln_id: str
    summary: str
    severity: str | None = None
    snyk_url: str | None = None


class AuditResult(BaseModel):
    """單一套件的稽核結果"""

    index: int
    name: str
    version: str
    summary_en: str = ""  # 英文功能摘要 (原始)
    summary_zh: str = ""  # 中文功能摘要
    license_type: str = "N/A"  # 授權類型
    source_repo: str | None = None  # 原始碼倉庫
    vulnerabilities: list[VulnerabilityInfo] = []
    snyk_url: str = ""  # Snyk 稽核頁面
    snyk_status: str = "Pass"  # "Pass" / "X個漏洞"
    download_url: str = ""  # 離線下載連結
    download_filename: str = ""  # 下載檔案名稱


class AuditReport(BaseModel):
    """完整稽核報告"""

    report_date: str
    source_file: str
    total_packages: int
    vuln_count: int
    python_version: str = ""  # 使用者選擇的 Python 版本
    platform: str = "win_amd64"  # 目標平台
    packages: list[AuditResult]
