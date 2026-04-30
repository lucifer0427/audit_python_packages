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

    async def run_audit_flow(self, file_content: bytes, filename: str, python_version: str = "", platform: str = "win_amd64") -> dict:
        """
        執行完整的稽核流程工作流
        
        本方法定義了整個系統的核心流水線 (Pipeline)，將多個單一職責的服務組件串接起來。
        步驟詳述：
        1. 解析檔案 $\to$ 2. 補足遞迴相依套件 $\to$ 3. 獲取 PyPI 元數據 $\to$ 4. 版本確定 $\to$ 
        5. 查詢 OSV 漏洞庫 $\to$ 6. 執行 pip-audit 補充掃描 $\to$ 7. 合併去重漏洞 $\to$ 
        8. LLM 翻譯功能摘要 $\to$ 9. 組裝結果 $\to$ 10. 生成多格式報告
        """
        
        # 1. 解析 requirements.txt
        # 將原始 bytes 內容解析為套件清單 (PackageInfo)，此階段會處理編碼偵測與格式清洗
        try:
            original_packages = parser.parse_requirements(file_content)
        except Exception as e:
            logger.error("解析 requirements 失敗: %s", e)
            raise ValueError(f"檔案解析失敗: {e}")

        if not original_packages:
            raise ValueError("未解析到任何套件")

        # 1.5 補足相依套件 (Dependency Resolution)
        # 使用 uv pip compile 模擬環境解析，將「直接依賴」擴展為「完整依賴樹」，確保所有潛在風險套件都被掃描
        from app.services import dependency_resolver
        resolved_reqs_content, resolved_pkgs_list = dependency_resolver.resolve_dependencies(file_content, python_version)
        
        # 獲取精準的離線下載連結
        offline_urls = dependency_resolver.get_offline_download_urls(resolved_reqs_content, python_version, platform)
        
        # 計算新增的遞迴相依套件 (不在原始清單中的套件)，用於在報告中區分直接依賴與間接依賴
        original_names = {pkg.name.lower() for pkg in original_packages}
        added_packages = [name for name, version in resolved_pkgs_list if name.lower() not in original_names]
        
        if resolved_pkgs_list:
            packages = [PackageInfo(name=n, version=v) for n, v in resolved_pkgs_list]
            logger.info("已將相依套件補足，目前總數: %d, 新增: %d", len(packages), len(added_packages))
        else:
            packages = original_packages

        # 2. 查詢 PyPI 取得套件資訊 (非同步併發)
        # 使用 asyncio.gather 同時發起所有套件的 PyPI 查詢請求，避免循序請求導致的線性延遲
        pypi_tasks = [
            self.pypi_client.get_package_info(pkg.name, pkg.version, python_version or None)
            for pkg in packages
        ]
        pypi_results = await asyncio.gather(*pypi_tasks)
        
        pypi_data: dict[str, dict] = {}
        for idx, pkg in enumerate(packages):
            # 儲存 PyPI 回傳的詳細資訊 (如 License, Summary, Source Repo)
            pypi_data[pkg.name] = pypi_results[idx]

        # 3. 解析版本
        # 若原始 requirements 未指定版本，則使用 PyPI 回傳的最新穩定版作為掃描基準
        resolved_packages = self._resolve_versions(packages, pypi_data)

        # 4. 查詢 OSV 漏洞 (非同步併發)
        # 針對確定版本的套件，向 Google OSV API 查詢已知漏洞 (CVE/GHSA)
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
        # pip-audit 基於本地安裝的環境與 PyPI 數據庫，能發現某些 OSV API 可能遺漏的漏洞，作為雙重保險
        audit_text = resolved_reqs_content.decode("utf-8", errors="replace") if 'resolved_reqs_content' in locals() else file_content.decode("utf-8", errors="replace")
        pip_audit_results = pip_audit_runner.run_pip_audit(audit_text)

        # 6. 合併漏洞結果
        # 將 OSV 與 pip-audit 的結果合併，並根據漏洞 ID (Vuln ID) 進行去重，防止重複報告同一漏洞
        merged_vulns = self._merge_vulnerabilities(osv_results, pip_audit_results)

        # 7. 翻譯功能摘要 (非同步)
        # 將套件的英文摘要翻譯為繁體中文，提升非英文使用者的報告可讀性
        translate_items = [
            {"name": pkg.name, "summary": pypi_data.get(pkg.name, {}).get("summary", "")}
            for pkg in packages
        ]
        translations = await self.translator.translate_summaries(translate_items)

        # 8. 組裝稽核結果
        # 將所有分散的資訊 (PyPI, OSV, 翻譯, Snyk 連結) 整合為統一的 AuditResult 物件
        audit_results = []
        for idx, pkg in enumerate(packages, 1):
            info = pypi_data.get(pkg.name, {})
            version = resolved_packages.get(pkg.name, pkg.version or "unknown")
            pkg_vulns = merged_vulns.get(pkg.name.lower(), [])
            # 生成 Snyk 快速查詢連結，方便資安分析人員快速查閱第三方詳細分析
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
                    download_url=offline_urls.get(pkg.name.lower(), info.get("download_url", "")),
                    download_filename=info.get("download_filename", ""),
                )
            )

        # 9. 生成報告
        # 計算總漏洞數，組裝最終報告模型並調用報告生成器產出多種格式檔案 (MD, HTML, PDF)
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
