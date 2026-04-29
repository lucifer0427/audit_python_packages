"""OSV (Open Source Vulnerabilities) API 客戶端
負責與 Google OSV 資料庫互動，查詢指定 PyPI 套件版本的已知漏洞資訊。
"""

import logging
import httpx
import diskcache

from app.config import settings
from app.models.schemas import VulnerabilityInfo

logger = logging.getLogger(__name__)

class OSVClient:
    """
    OSV API 客戶端類別
    透過注入的 httpx.AsyncClient 執行非同步漏洞查詢。
    """

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        # 使用持久化快取，存放在報告目錄下的 .cache/osv
        self._cache = diskcache.Cache(settings.REPORTS_DIR / ".cache" / "osv")

    async def query_vulnerabilities(self, name: str, version: str) -> list[VulnerabilityInfo]:
        """
        查詢指定套件版本的已知漏洞
        
        本方法實作了「快取優先」策略：首先嘗試從磁碟快取讀取結果，若不存在則呼叫外部 OSV API。
        這能大幅降低對 Google API 的依賴並提升重複掃描時的反應速度。
        """
        cache_key = (name, version)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # OSV API 要求使用 POST 請求並傳送特定的 JSON Payload
        payload = {
            "package": {
                "name": name,
                "ecosystem": "PyPI",
            },
            "version": version,
        }

        try:
            resp = await self._client.post(
                settings.OSV_API_URL,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.error("OSV 查詢失敗 [%s==%s]: %s", name, version, e)
            return []

        # 提取 API 回傳的漏洞列表 (vulns)
        vulns = data.get("vulns", [])
        results = []

        for vuln in vulns:
            vuln_id = vuln.get("id", "UNKNOWN")
            # 優先取 summary，若無則取 details 欄位作為漏洞描述
            summary = vuln.get("summary", vuln.get("details", "無描述"))

            # 解析漏洞的嚴重等級 (CVSS 分數)
            severity = self._extract_severity(vuln)

            # 為每個漏洞提供 Snyk 快速查詢連結，方便分析人員深入研究漏洞影響
            snyk_url = f"{settings.SNYK_BASE_URL}/{name}"

            results.append(
                VulnerabilityInfo(
                    vuln_id=vuln_id,
                    summary=summary[:200] if summary else "無描述", # 限制長度防止 Markdown 表格破版
                    severity=severity,
                    snyk_url=snyk_url,
                )
            )

        logger.info("[%s==%s] 發現 %d 個漏洞", name, version, len(results))
        
        # 將查詢結果儲存至磁碟快取，避免下次相同套件版本重複呼叫 API
        self._cache[cache_key] = results
        return results

    def _extract_severity(self, vuln: dict) -> str:
        """
        從 OSV 漏洞資料中提取嚴重等級
        優先尋找 CVSS 分數，其次尋找 database_specific 標記。
        """
        severity_list = vuln.get("severity", [])
        if severity_list:
            for sev in severity_list:
                score = sev.get("score")
                if score:
                    return self._cvss_to_level(score)

        # 從資料庫特定欄位推測等級
        db_specific = vuln.get("database_specific", {})
        if "severity" in db_specific:
            return db_specific["severity"]

        return "未知"

    def _cvss_to_level(self, score_str: str) -> str:
        """
        將 CVSS 向量或分數轉換為易讀的中文等級
        - 9.0+ : 嚴重 (Critical)
        - 7.0-8.9 : 高 (High)
        - 4.0-6.9 : 中 (Medium)
        - 0.0-3.9 : 低 (Low)
        """
        try:
            # 處理 CVSS 向量格式 (例如 "CVSS:3.1/AV:N/AC:L/...")
            if "/" in score_str and ":" in score_str:
                return f"CVSS: {score_str[:50]}"
            
            # 處理純數字分數
            score = float(score_str)
            if score >= 9.0:
                return "嚴重"
            if score >= 7.0:
                return "高"
            if score >= 4.0:
                return "中"
            return "低"
        except (ValueError, TypeError):
            # 若無法解析為數字，則直接回傳截斷後的原字串
            return score_str[:30] if score_str else "未知"
