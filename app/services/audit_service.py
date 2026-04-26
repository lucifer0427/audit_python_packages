"""稽核業務邏輯服務層
本模組封裝了從解析 requirements.txt 到生成最終報告的完整工作流 (Workflow)，
將路由層與底層 API 客戶端解耦。
"""

import asyncio
import logging
from datetime import datetime

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


class AuditService:
    """
    稽核服務類別
    提供靜態方法來執行一套標準化的套件資安稽核流程。
    """

    @staticmethod
    async def run_audit_flow(file_content: bytes, filename: str, python_version: str = "") -> dict:
        """
        執行完整的稽核流程工作流
        
        步驟詳述：
        1. 解析檔案 $\to$ 2. 獲取 PyPI 資訊 $\to$ 3. 版本解析 $\to$ 4. 查詢 OSV 漏洞 $\to$ 
        5. 執行 pip-audit $\to$ 6. 合併漏洞 $\to$ 7. LLM 翻譯摘要 $\to$ 8. 組裝結果 $\to$ 9. 生成報告
        """
        
        # 1. 解析 requirements.txt
        # 將上傳的 bytes 內容轉換為 PackageInfo 對象列表
        try:
            packages = parser.parse_requirements(file_content)
        except Exception as e:
            logger.error("解析 requirements 失敗: %s", e)
            raise ValueError(f"檔案解析失敗: {e}")

        if not packages:
            raise ValueError("未解析到任何套件")

        # 2. 查詢 PyPI 取得套件資訊 (非同步併發)
        # 使用 asyncio.gather 同時發起多個 API 請求，大幅縮短等待時間
        pypi_tasks = [
            pypi_client.get_package_info(pkg.name, pkg.version, python_version or None)
            for pkg in packages
        ]
        pypi_results = await asyncio.gather(*pypi_tasks)
        
        # 將結果映射回套件名稱
        pypi_data: dict[str, dict] = {}
        for idx, pkg in enumerate(packages):
            pypi_data[pkg.name] = pypi_results[idx]

        # 3. 解析版本
        # 若 requirements 中未指定版本 (例如僅寫 requests)，則使用 PyPI 回傳的最新版本
        resolved_packages = AuditService._resolve_versions(packages, pypi_data)

        # 4. 查詢 OSV 漏洞 (非同步併發)
        # 針對每個解析後的版本查詢 OSV 資料庫
        osv_tasks = [
            osv_client.query_vulnerabilities(name, version)
            for name, version in resolved_packages.items()
        ]
        osv_query_results = await asyncio.gather(*osv_tasks)
        
        osv_results: dict[str, list] = {}
        for idx, name in enumerate(resolved_packages.keys()):
            vulns = osv_query_results[idx]
            if vulns:
                osv_results[name] = vulns

        # 5. 執行 pip-audit (補充掃描)
        # pip-audit 是本地/官方的掃描工具，用來補足 OSV 可能遺漏的漏洞
        requirements_text = file_content.decode("utf-8", errors="replace")
        pip_audit_results = pip_audit_runner.run_pip_audit(requirements_text)

        # 6. 合併漏洞結果
        # 將 OSV 與 pip-audit 的結果合併，並根據 vuln_id 進行去重
        merged_vulns = AuditService._merge_vulnerabilities(osv_results, pip_audit_results)

        # 7. 翻譯功能摘要 (非同步)
        # 呼叫 LLM (OpenAI/Gemini) 將所有套件的英文摘要一次性翻譯為中文
        translate_items = [
            {"name": pkg.name, "summary": pypi_data.get(pkg.name, {}).get("summary", "")}
            for pkg in packages
        ]
        translations = await translator.translate_summaries(translate_items)

        # 8. 組裝稽核結果
        # 將所有收集到的資訊 (PyPI, OSV, 翻譯, 授權) 整合進 AuditResult 模型
        audit_results = []
        for idx, pkg in enumerate(packages, 1):
            info = pypi_data.get(pkg.name, {})
            version = resolved_packages.get(pkg.name, pkg.version or "unknown")
            pkg_vulns = merged_vulns.get(pkg.name.lower(), [])
            snyk_url = f"{settings.SNYK_BASE_URL}/{pkg.name}"

            # 判斷 Snyk 狀態：有漏洞則顯示數量，否則顯示 Pass
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
        # 計算漏洞總數並呼叫 report_generator 生成 Markdown 與 PDF 檔案
        vuln_count = sum(1 for r in audit_results if r.vulnerabilities)
        report = AuditReport(
            report_date=datetime.now().isoformat(timespec="seconds"),
            source_file=filename,
            total_packages=len(audit_results),
            vuln_count=vuln_count,
            python_version=python_version or "未指定",
            platform="Windows AMD64",
            packages=audit_results,
        )

        md_path, pdf_path = report_generator.generate_report(report)
        
        logger.info("稽核完成: %s, 發現 %d 個風險套件", filename, vuln_count)

        return {
            "message": "稽核完成",
            "total_packages": len(audit_results),
            "vuln_packages": vuln_count,
            "report_file": md_path.name,
            "download_url": f"/api/reports/{md_path.name}",
            "pdf_download_url": f"/api/reports/{pdf_path.name}",
        }

    @staticmethod
    def _resolve_versions(packages: list[PackageInfo], pypi_data: dict[str, dict]) -> dict[str, str]:
        """
        解析實際版本
        若 PackageInfo 中沒有版本號，則從 PyPI 查詢結果中獲取最新版本。
        """
        resolved = {}
        for pkg in packages:
            if pkg.version:
                resolved[pkg.name] = pkg.version
            else:
                info = pypi_data.get(pkg.name, {})
                resolved[pkg.name] = info.get("version", "unknown")
        return resolved

    @staticmethod
    def _merge_vulnerabilities(osv_results: dict[str, list], pip_audit_results: dict[str, list]) -> dict[str, list]:
        """
        合併漏洞結果
        將不同來源的漏洞列表合併，並透過 vuln_id 確保同一漏洞不會重複出現。
        """
        merged: dict[str, list] = {}
        # 先加入 OSV 結果
        for name, vulns in osv_results.items():
            merged[name.lower()] = list(vulns)

        # 合併 pip-audit 結果
        for name, vulns in pip_audit_results.items():
            key = name.lower()
            if key not in merged:
                merged[key] = list(vulns)
            else:
                # 僅加入尚未出現在 merged 列表中的漏洞
                existing_ids = {v.vuln_id for v in merged[key]}
                for v in vulns:
                    if v.vuln_id not in existing_ids:
                        merged[key].append(v)
        return merged
