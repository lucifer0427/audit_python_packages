"""OSV (Open Source Vulnerabilities) API 客戶端

查詢 PyPI 套件的已知漏洞。
"""

import logging

import requests
from functools import lru_cache

from app.config import settings
from app.models.schemas import VulnerabilityInfo

logger = logging.getLogger(__name__)


@lru_cache(maxsize=256)
def query_vulnerabilities(name: str, version: str) -> list[VulnerabilityInfo]:
    """查詢指定套件版本的已知漏洞

    Args:
        name: 套件名稱
        version: 套件版本

    Returns:
        漏洞資訊列表
    """
    payload = {
        "package": {
            "name": name,
            "ecosystem": "PyPI",
        },
        "version": version,
    }

    try:
        resp = requests.post(
            settings.OSV_API_URL,
            json=payload,
            timeout=settings.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning("OSV 查詢失敗 [%s==%s]: %s", name, version, e)
        return []

    vulns = data.get("vulns", [])
    results = []

    for vuln in vulns:
        vuln_id = vuln.get("id", "UNKNOWN")
        summary = vuln.get("summary", vuln.get("details", "無描述"))

        # 提取嚴重性
        severity = _extract_severity(vuln)

        # 建構 Snyk URL
        snyk_url = f"{settings.SNYK_BASE_URL}/{name}"

        results.append(
            VulnerabilityInfo(
                vuln_id=vuln_id,
                summary=summary[:200] if summary else "無描述",
                severity=severity,
                snyk_url=snyk_url,
            )
        )

    logger.info("[%s==%s] 發現 %d 個漏洞", name, version, len(results))
    return results


def _extract_severity(vuln: dict) -> str:
    """從 OSV 漏洞資料提取嚴重等級"""
    severity_list = vuln.get("severity", [])
    if severity_list:
        for sev in severity_list:
            score = sev.get("score")
            if score:
                return _cvss_to_level(score)

    # 從 database_specific 或 ecosystem_specific 推測
    db_specific = vuln.get("database_specific", {})
    if "severity" in db_specific:
        return db_specific["severity"]

    return "未知"


def _cvss_to_level(score_str: str) -> str:
    """CVSS 向量轉嚴重等級 (簡化判斷)"""
    try:
        # 嘗試從 CVSS 向量提取分數
        # 格式可能是 "CVSS:3.1/AV:N/..." 或純數字
        if "/" in score_str and ":" in score_str:
            return f"CVSS: {score_str[:30]}"
        score = float(score_str)
        if score >= 9.0:
            return "嚴重"
        if score >= 7.0:
            return "高"
        if score >= 4.0:
            return "中"
        return "低"
    except (ValueError, TypeError):
        return score_str[:30] if score_str else "未知"
