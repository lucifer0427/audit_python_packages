"""稽核 API 路由"""

import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.models.schemas import AuditReport, AuditResult, PackageInfo
from app.services import (
    osv_client,
    parser,
    pip_audit_runner,
    pypi_client,
    report_generator,
    translator,
)
from app.utils.sanitizer import sanitize_for_table

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["audit"])


@router.post("/audit")
async def run_audit(file: UploadFile, python_version: str = Form(default="")):
    """上傳 requirements.txt 執行資安稽核

    Args:
        file: requirements.txt 檔案
        python_version: 目標 Python 版本 (如 "3.12")，用於篩選 Windows AMD64 安裝檔
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供檔案")

    # 讀取上傳檔案
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="檔案內容為空")

    logger.info("收到稽核請求: %s (%d bytes)", file.filename, len(content))

    # 1. 解析 requirements.txt
    try:
        packages = parser.parse_requirements(content)
    except Exception as e:
        logger.error("解析失敗: %s", e)
        raise HTTPException(status_code=400, detail=f"檔案解析失敗: {e}")

    if not packages:
        raise HTTPException(status_code=400, detail="未解析到任何套件")

    # 2. 查詢 PyPI 取得套件資訊 (傳入 python_version 篩選平台安裝檔)
    pypi_data: dict[str, dict] = {}
    for pkg in packages:
        info = pypi_client.get_package_info(pkg.name, pkg.version, python_version or None)
        pypi_data[pkg.name] = info

    # 3. 解析版本 (若 requirements 中未指定精確版本，用 PyPI 回傳的)
    resolved_packages = _resolve_versions(packages, pypi_data)

    # 4. 查詢 OSV 漏洞
    osv_results: dict[str, list] = {}
    for name, version in resolved_packages.items():
        vulns = osv_client.query_vulnerabilities(name, version)
        if vulns:
            osv_results[name] = vulns

    # 5. 執行 pip-audit (補充掃描)
    requirements_text = content.decode("utf-8", errors="replace")
    pip_audit_results = pip_audit_runner.run_pip_audit(requirements_text)

    # 6. 合併漏洞結果
    merged_vulns = _merge_vulnerabilities(osv_results, pip_audit_results)

    # 7. 翻譯功能摘要
    translate_items = [
        {"name": pkg.name, "summary": pypi_data.get(pkg.name, {}).get("summary", "")}
        for pkg in packages
    ]
    translations = translator.translate_summaries(translate_items)

    # 8. 組裝稽核結果
    audit_results = []
    for idx, pkg in enumerate(packages, 1):
        info = pypi_data.get(pkg.name, {})
        version = resolved_packages.get(pkg.name, pkg.version or "unknown")
        pkg_vulns = merged_vulns.get(pkg.name.lower(), [])
        snyk_url = f"{settings.SNYK_BASE_URL}/{pkg.name}"

        if pkg_vulns:
            snyk_status = f"{len(pkg_vulns)} 個漏洞"
        else:
            snyk_status = "Pass"

        audit_results.append(
            AuditResult(
                index=idx,
                name=pkg.name,
                version=version,
                summary_en=info.get("summary", ""),
                summary_zh=sanitize_for_table(
                    translations.get(pkg.name, "Python 套件。")
                ),
                license_type=info.get("license", "N/A"),
                source_repo=info.get("source_repo"),
                vulnerabilities=pkg_vulns,
                snyk_url=snyk_url,
                snyk_status=snyk_status,
                download_url=info.get("download_url", ""),
                download_filename=info.get("download_filename", ""),
            )
        )

    # 9. 生成報告
    vuln_count = sum(1 for r in audit_results if r.vulnerabilities)
    report = AuditReport(
        report_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source_file=file.filename,
        total_packages=len(audit_results),
        vuln_count=vuln_count,
        python_version=python_version or "未指定",
        platform="Windows AMD64",
        packages=audit_results,
    )

    md_path, pdf_path = report_generator.generate_report(report)

    return JSONResponse(
        content={
            "message": "稽核完成",
            "total_packages": len(audit_results),
            "vuln_packages": vuln_count,
            "report_file": md_path.name,
            "download_url": f"/api/reports/{md_path.name}",
            "pdf_download_url": f"/api/reports/{pdf_path.name}",
        }
    )


@router.get("/reports")
async def list_reports():
    """列出所有已生成的稽核報告"""
    reports_dir = settings.REPORTS_DIR
    if not reports_dir.exists():
        return {"reports": []}

    files = sorted(reports_dir.glob("*.md"), reverse=True)
    return {
        "reports": [
            {
                "filename": f.name,
                "size": f.stat().st_size,
                "created": datetime.fromtimestamp(f.stat().st_mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "download_url": f"/api/reports/{f.name}",
                "pdf_download_url": f"/api/reports/{f.with_suffix('.pdf').name}" if f.with_suffix('.pdf').exists() else None,
            }
            for f in files
        ]
    }


@router.get("/reports/{filename}")
async def download_report(filename: str):
    """下載指定稽核報告"""
    filepath = settings.REPORTS_DIR / filename

    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="報告不存在")

    # 安全性檢查: 防止路徑穿越
    try:
        filepath.resolve().relative_to(settings.REPORTS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="禁止存取")

    media_type = "application/pdf" if filename.endswith(".pdf") else "text/markdown"

    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type=media_type,
    )


def _resolve_versions(
    packages: list[PackageInfo], pypi_data: dict[str, dict]
) -> dict[str, str]:
    """解析每個套件的實際版本"""
    resolved = {}
    for pkg in packages:
        if pkg.version:
            resolved[pkg.name] = pkg.version
        else:
            info = pypi_data.get(pkg.name, {})
            resolved[pkg.name] = info.get("version", "unknown")
    return resolved


def _merge_vulnerabilities(
    osv_results: dict[str, list],
    pip_audit_results: dict[str, list],
) -> dict[str, list]:
    """合併 OSV 和 pip-audit 的漏洞結果，去重"""
    merged: dict[str, list] = {}

    # 先加入 OSV 結果
    for name, vulns in osv_results.items():
        key = name.lower()
        merged[key] = list(vulns)

    # 合併 pip-audit 結果
    for name, vulns in pip_audit_results.items():
        key = name.lower()
        if key not in merged:
            merged[key] = list(vulns)
        else:
            existing_ids = {v.vuln_id for v in merged[key]}
            for v in vulns:
                if v.vuln_id not in existing_ids:
                    merged[key].append(v)

    return merged
