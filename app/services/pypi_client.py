"""PyPI JSON API 客戶端

查詢套件的授權、摘要、原始碼倉庫、下載連結。
"""

import logging

import requests

from app.config import settings
from app.utils.sanitizer import clean_license

logger = logging.getLogger(__name__)


def get_package_info(name: str, version: str | None = None) -> dict:
    """查詢 PyPI 套件資訊

    Args:
        name: 套件名稱
        version: 指定版本 (None 則查最新版)

    Returns:
        {
            "version": str,
            "summary": str,
            "license": str,
            "source_repo": str | None,
            "download_url": str,
        }
    """
    url = f"{settings.PYPI_BASE_URL}/{name}/json"
    if version:
        url = f"{settings.PYPI_BASE_URL}/{name}/{version}/json"

    try:
        resp = requests.get(url, timeout=settings.REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning("PyPI 查詢失敗 [%s]: %s", name, e)
        return {
            "version": version or "unknown",
            "summary": "",
            "license": "N/A",
            "source_repo": None,
            "download_url": "",
        }

    info = data.get("info", {})
    resolved_version = info.get("version", version or "unknown")

    # 授權提取
    license_type = clean_license(
        info.get("license"),
        info.get("classifiers", []),
    )

    # 原始碼倉庫 URL
    source_repo = _extract_source_repo(info)

    # 離線下載連結 (優先 .whl)
    download_url = _extract_download_url(data, resolved_version, name)

    return {
        "version": resolved_version,
        "summary": info.get("summary", "") or "",
        "license": license_type,
        "source_repo": source_repo,
        "download_url": download_url,
    }


def _extract_source_repo(info: dict) -> str | None:
    """從 project_urls 或 home_page 提取原始碼倉庫 URL"""
    project_urls = info.get("project_urls") or {}

    # 按優先級搜尋
    url_keys = [
        "Source", "Source Code", "Repository", "GitHub",
        "Code", "Homepage", "Home",
    ]
    for key in url_keys:
        for pkey, purl in project_urls.items():
            if key.lower() in pkey.lower() and purl:
                return purl

    # Fallback: home_page
    home_page = info.get("home_page")
    if home_page and ("github.com" in home_page or "gitlab.com" in home_page):
        return home_page

    # 最後嘗試任何 project_url
    if project_urls:
        return next(iter(project_urls.values()))

    return home_page or None


def _extract_download_url(data: dict, version: str, name: str) -> str:
    """提取離線下載連結"""
    # 從 urls 找 wheel 或 sdist
    urls = data.get("urls", [])
    whl_url = None
    sdist_url = None

    for item in urls:
        filename = item.get("filename", "")
        url = item.get("url", "")
        if filename.endswith(".whl") and not whl_url:
            whl_url = url
        elif filename.endswith((".tar.gz", ".zip")) and not sdist_url:
            sdist_url = url

    if whl_url:
        return whl_url
    if sdist_url:
        return sdist_url

    # Fallback: PyPI 下載頁面
    return f"https://pypi.org/project/{name}/{version}/#files"
