"""稽核業務邏輯服務層
本模組封裝了從解析 requirements.txt 到生成最終報告的完整工作流 (Workflow)，
將路由層與底層 API 客戶端解耦。
"""

import asyncio
import logging
from datetime import datetime

import anyio

from app.config import settings
from app.models.schemas import AuditReport, AuditResult, PackageInfo
from app.services import (
    parser,
    pip_audit_runner,
    report_generator,
)
from app.services.osv_client import OSVClient
from app.services.pypi_client import PyPIClient
from app.services.translator import TranslatorService
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
        translator: TranslatorService,
    ):
        self.osv_client = osv_client
        self.pypi_client = pypi_client
        self.translator = translator

    async def run_audit_flow(
        self, file_content: bytes, filename: str, python_version: str = "", platform: str = ""
    ) -> dict:
        """
        執行完整的稽核流程工作流

        本方法定義了整個系統的核心流水線 (Pipeline)，將多個單一職責的服務組件串接起來。
        步驟詳述：
        1. 解析檔案 -> 2. 補足遞迴相依套件 -> 3. 獲取 PyPI 元數據 -> 4. 版本確定 ->
        5. 查詢 OSV 漏洞庫 -> 6. 執行 pip-audit 補充掃描 -> 7. 合併去重漏洞 ->
        8. LLM 翻譯功能摘要 -> 9. 組裝結果 -> 10. 生成多格式報告
        """

        # 1. 解析 requirements.txt
        try:
            original_packages = parser.parse_requirements(file_content)
        except Exception as e:
            logger.error("解析 requirements 失敗: %s", e)
            raise ValueError(f"檔案解析失敗: {e}") from e

        if not original_packages:
            raise ValueError("未解析到任何套件")

        # 2. 補足相依套件
        resolved_reqs_content, packages, added_packages, offline_urls = await self._resolve_dependencies(
            file_content, python_version, platform, original_packages
        )

        # 3. 查詢 PyPI 取得套件資訊 (非同步併發)
        pypi_data = await self._fetch_pypi_metadata(packages, python_version)

        # 4. 解析版本
        resolved_packages = self._resolve_versions(packages, pypi_data)

        # 5. 查詢 OSV 漏洞 + pip-audit + 合併
        merged_vulns = await self._scan_vulnerabilities(resolved_packages, resolved_reqs_content, file_content)

        # 6. 翻譯功能摘要 (非同步)
        translations = await self._translate_summaries(packages, pypi_data)

        # 7. 組裝稽核結果
        audit_results = self._assemble_results(
            packages, pypi_data, resolved_packages, merged_vulns, offline_urls, translations
        )

        # 8. 生成報告
        return await self._generate_reports(
            audit_results, filename, python_version, platform, added_packages, resolved_reqs_content
        )

    async def _resolve_dependencies(
        self, file_content: bytes, python_version: str, platform: str, original_packages: list
    ) -> tuple[bytes | None, list, list, dict]:
        from app.services import dependency_resolver

        resolved_reqs_content: bytes | None = None
        resolved_pkgs_list: list = []
        _resolved = await anyio.to_thread.run_sync(
            dependency_resolver.resolve_dependencies, file_content, python_version
        )
        resolved_reqs_content, resolved_pkgs_list = _resolved

        offline_urls = await anyio.to_thread.run_sync(
            dependency_resolver.get_offline_download_urls, resolved_reqs_content, python_version, platform
        )

        original_names = {pkg.name.lower() for pkg in original_packages}
        added_packages = [name for name, version in resolved_pkgs_list if name.lower() not in original_names]

        if resolved_pkgs_list:
            packages = [PackageInfo(name=n, version=v) for n, v in resolved_pkgs_list]
            logger.info("已將相依套件補足，目前總數: %d, 新增: %d", len(packages), len(added_packages))
        else:
            packages = original_packages

        return resolved_reqs_content, packages, added_packages, offline_urls

    async def _fetch_pypi_metadata(self, packages: list, python_version: str) -> dict[str, dict]:
        pypi_tasks = [
            self.pypi_client.get_package_info(pkg.name, pkg.version, python_version or None) for pkg in packages
        ]
        pypi_results = await asyncio.gather(*pypi_tasks, return_exceptions=True)

        pypi_data: dict[str, dict] = {}
        for idx, pkg in enumerate(packages):
            if isinstance(pypi_results[idx], Exception):
                logger.error("PyPI 查詢失敗 [%s]: %s", pkg.name, pypi_results[idx])
                pypi_data[pkg.name] = {}
            else:
                pypi_data[pkg.name] = pypi_results[idx]

        return pypi_data

    async def _scan_vulnerabilities(
        self, resolved_packages: dict, resolved_reqs_content: bytes | None, file_content: bytes
    ) -> dict[str, list]:
        osv_tasks = [
            self.osv_client.query_vulnerabilities(name, version) for name, version in resolved_packages.items()
        ]
        osv_query_results = await asyncio.gather(*osv_tasks, return_exceptions=True)

        osv_results: dict[str, list] = {}
        for idx, name in enumerate(resolved_packages.keys()):
            if isinstance(osv_query_results[idx], Exception):
                logger.error("OSV 查詢失敗 [%s]: %s", name, osv_query_results[idx])
                continue
            vulns = osv_query_results[idx]
            if vulns:
                osv_results[name] = vulns

        if resolved_reqs_content is not None:
            audit_text = resolved_reqs_content.decode("utf-8", errors="replace")
        else:
            audit_text = file_content.decode("utf-8", errors="replace")
        pip_audit_results = await anyio.to_thread.run_sync(pip_audit_runner.run_pip_audit, audit_text)

        merged_vulns = self._merge_vulnerabilities(osv_results, pip_audit_results)
        return merged_vulns

    async def _translate_summaries(self, packages: list, pypi_data: dict) -> dict:
        translate_items = [
            {"name": pkg.name, "summary": pypi_data.get(pkg.name, {}).get("summary", "")} for pkg in packages
        ]
        translations = await self.translator.translate_summaries(translate_items)
        return translations

    def _assemble_results(
        self,
        packages: list,
        pypi_data: dict,
        resolved_packages: dict,
        merged_vulns: dict,
        offline_urls: dict,
        translations: dict,
    ) -> list:
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
                    summary_zh=sanitize_for_table(translations.get(pkg.name, "Python 套件。")),
                    license_type=info.get("license", "N/A"),
                    source_repo=info.get("source_repo"),
                    vulnerabilities=pkg_vulns,
                    snyk_url=snyk_url,
                    snyk_status=snyk_status,
                    download_url=offline_urls.get(pkg.name.lower(), info.get("download_url", "")),
                    download_filename=info.get("download_filename", ""),
                )
            )
        return audit_results

    async def _generate_reports(
        self,
        audit_results: list,
        filename: str,
        python_version: str,
        platform: str,
        added_packages: list,
        resolved_reqs_content: bytes | None,
    ) -> dict:
        vuln_count = sum(1 for r in audit_results if r.vulnerabilities)
        report = AuditReport(
            report_date=datetime.now().isoformat(timespec="seconds"),
            source_file=filename,
            total_packages=len(audit_results),
            vuln_count=vuln_count,
            python_version=python_version or "未指定",
            platform=platform,
            packages=audit_results,
            added_packages=added_packages,
        )

        md_path, html_path, pdf_path, resolved_path = await anyio.to_thread.run_sync(
            report_generator.generate_report,
            report,
            resolved_reqs_content if resolved_reqs_content is not None else None,
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

    def _merge_vulnerabilities(
        self, osv_results: dict[str, list], pip_audit_results: dict[str, list]
    ) -> dict[str, list]:
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
