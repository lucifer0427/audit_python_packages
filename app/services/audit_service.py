"""稽核業務邏輯服務層
本模組封裝了從解析 requirements.txt 到生成最終報告的完整工作流 (Workflow)，
將路由層與底層 API 客戶端解耦。
"""

import asyncio
import logging
from datetime import datetime

from app.config import settings
from app.models.schemas import AuditReport, AuditResult, PackageInfo
from app.services.osv_client import OSVClient
from app.services.pypi_client import PyPIClient
from app.services.translator import TranslatorService
from app.services import (
    parser,
    pip_audit_runner,
    report_generator,
)
from app.utils.sanitizer import sanitize_for_table

logger = logging.getLogger(__name__)

class AuditService:
    """
    稽核服務類別
    提供實例方法來執行一套標準化的套件資安稽核流程。
    """

    def __init__(
        self, 
        osv_client: OSVClient, 
        pypi_client: PyPIClient, 
        translator: TranslatorService
    ):
        self.osv_client = osv_client
        self.pypi_client = pypi_client
        self.translator = translator

    async def run_audit_flow(self, file_content: bytes, filename: str, python_version: str = "") -> dict:
        """
        執行完整的稽核流程工作流
        
        步驟詳述：
        1. 解析檔案 $\to$ 2. 獲取 PyPI 資訊 $\to$ 3. 版本解析 $\to$ 4. 查詢 OSV 漏洞 $\to$ 
        5. 執行 pip-audit $\to$ 6. 合併漏洞 $\to$ 7. LLM 翻譯摘要 $\to$ 8. 組裝結果 $\to$ 9. 生成報告
        """
        
        # 1. 解析 requirements.txt
        try:
            original_packages = parser.parse_requirements(file_content)
        except Exception as e:
            logger.error("解析 requirements 失敗: %s", e)
            raise ValueError(f"檔案解析失敗: {e}")

        if not original_packages:
            raise ValueError("未解析到任何套件")

        # 1.5 補足相依套件 (Dependency Resolution)
        from app.services import dependency_resolver
        resolved_reqs_content, resolved_pkgs_list = dependency_resolver.resolve_dependencies(file_content, python_version)
        
        # 計算新增的套件 (不在原始清單中的套件)
        original_names = {pkg.name.lower() for pkg in original_packages}
        added_packages = [name for name, version in resolved_pkgs_list if name.lower() not in original_names]
        
        if resolved_pkgs_list:
            packages = [PackageInfo(name=n, version=v) for n, v in resolved_pkgs_list]
            logger.info("已將相依套件補足，目前總數: %d, 新增: %d", len(packages), len(added_packages))
        else:
            packages = original_packages

        # 2. 查詢 PyPI 取得套件資訊 (非同步併發)
        pypi_tasks = [
            self.pypi_client.get_package_info(pkg.name, pkg.version, python_version or None)
            for pkg in packages
        ]
        pypi_results = await asyncio.gather(*pypi_tasks)
        
        pypi_data: dict[str, dict] = {}
        for idx, pkg in enumerate(packages):
            # pypi_client.get_package_info returns a TypedDict
            pypi_data[pkg.name] = pypi_results[idx]

        # 3. 解析版本
        resolved_packages = self._resolve_versions(packages, pypi_data)

        # 4. 查詢 OSV 漏洞 (非同步併發)
        osv_tasks = [
            self.osv_client.query_vulnerabilities(name, version)
            for name, version in resolved_packages.items()
        ]
        osv_query_results = await asyncio.gather(*osv_tasks)
        
        osv_results: dict[str, list] = {}
        for idx, name in enumerate(resolved_packages.keys()):
            vulns = osv_query_results[idx]
            if vulns:
                osv_results[name] = vulns

        # 5. 執行 pip-audit (補充掃描)
        audit_text = resolved_reqs_content.decode("utf-8", errors="replace") if 'resolved_reqs_content' in locals() else file_content.decode("utf-8", errors="replace")
        pip_audit_results = pip_audit_runner.run_pip_audit(audit_text)

        # 6. 合併漏洞結果
        merged_vulns = self._merge_vulnerabilities(osv_results, pip_audit_results)

        # 7. 翻譯功能摘要 (非同步)
        translate_items = [
            {"name": pkg.name, "summary": pypi_data.get(pkg.name, {}).get("summary", "")}
            for pkg in packages
        ]
        translations = await self.translator.translate_summaries(translate_items)

        # 8. 組裝稽核結果
        audit_results = []
        for idx, pkg in enumerate(packages, 1):
            info = pypi_data.get(pkg.name, {})
            version = resolved_packages.get(pkg.name, pkg.version or "unknown")
            pkg_vulns = merged_vulns.get(pkg.name.lower(), [])
            snyk_url = f"{settings.SNYK_BASE_URL}/{pkg.name}"

            snyk_status = f"{len(pkg_vulns)} 個漏洞" if pkg_vulns else "Pass"

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
            report_date=datetime.now().isoformat(timespec="seconds"),
            source_file=filename,
            total_packages=len(audit_results),
            vuln_count=vuln_count,
            python_version=python_version or "未指定",
            platform="Windows AMD64",
            packages=audit_results,
            added_packages=added_packages,
        )

        md_path, html_path, pdf_path, resolved_path = report_generator.generate_report(
            report, resolved_reqs_content if 'resolved_reqs_content' in locals() else None
        )
        
        logger.info("稽核完成: %s, 發現 %d 個風險套件", filename, vuln_count)

        return {
            "message": "稽核完成",
            "total_packages": len(audit_results),
            "vuln_packages": vuln_count,
            "report_file": md_path.name,
            "download_url": f"/api/reports/{md_path.name}",
            "html_download_url": f"/api/reports/{html_path.name}",
            "pdf_download_url": f"/api/reports/{pdf_path.name}",
            "resolved_requirements_url": f"/api/reports/{resolved_path.name}" if resolved_path else None,
        }

    def _resolve_versions(self, packages: list[PackageInfo], pypi_data: dict[str, dict]) -> dict[str, str]:
        resolved = {}
        for pkg in packages:
            if pkg.version:
                resolved[pkg.name] = pkg.version
            else:
                info = pypi_data.get(pkg.name, {})
                resolved[pkg.name] = info.get("version", "unknown")
        return resolved

    def _merge_vulnerabilities(self, osv_results: dict[str, list], pip_audit_results: dict[str, list]) -> dict[str, list]:
        merged: dict[str, list] = {}
        for name, vulns in osv_results.items():
            merged[name.lower()] = list(vulns)

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
