"""PyPI JSON API 客戶端

查詢套件的授權、摘要、原始碼倉庫、下載連結。
支援依 Python 版本與平台 (Windows AMD64) 篩選安裝檔。
"""

import logging
import re

import requests
from functools import lru_cache

from app.config import settings
from app.utils.sanitizer import clean_license

logger = logging.getLogger(__name__)

# Python 版本 → CPython tag 對照
# 例: "3.12" → ["cp312"], "3.10" → ["cp310"]
def _version_to_cp_tags(python_version: str) -> list[str]:
    """將 Python 版本字串轉換為 CPython wheel tag"""
    if not python_version:
        return []
    parts = python_version.split(".")
    if len(parts) >= 2:
        major, minor = parts[0], parts[1]
        return [f"cp{major}{minor}"]
    return []


@lru_cache(maxsize=128)
def get_package_info(
    name: str,
    version: str | None = None,
    python_version: str | None = None,
) -> dict:
    """查詢 PyPI 套件資訊

    Args:
        name: 套件名稱
        version: 指定版本 (None 則查最新版)
        python_version: 目標 Python 版本 (如 "3.12")，用於篩選 Windows AMD64 wheel

    Returns:
        {
            "version": str,
            "summary": str,
            "license": str,
            "source_repo": str | None,
            "download_url": str,
            "download_filename": str,
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
            "download_filename": "",
        }

    info = data.get("info", {})
    resolved_version = info.get("version", version or "unknown")

    # 授權提取 (優先 license_expression → license → classifiers)
    license_type = clean_license(
        info.get("license"),
        info.get("classifiers", []),
        info.get("license_expression"),
    )

    # 原始碼倉庫 URL
    source_repo = _extract_source_repo(info)

    # 離線下載連結 (依平台篩選)
    download_url, download_filename = _extract_download_url(
        data, resolved_version, name, python_version
    )

    return {
        "version": resolved_version,
        "summary": info.get("summary", "") or "",
        "license": license_type,
        "source_repo": source_repo,
        "download_url": download_url,
        "download_filename": download_filename,
    }


def _is_repo_url(url: str) -> bool:
    """判斷 URL 是否為程式碼託管平台的倉庫連結"""
    repo_hosts = ["github.com", "gitlab.com", "bitbucket.org", "codeberg.org"]
    url_lower = url.lower()
    return any(host in url_lower for host in repo_hosts)


def _extract_source_repo(info: dict) -> str | None:
    """從 project_urls 或 home_page 提取原始碼倉庫 URL

    只回傳真正的程式碼託管平台 (GitHub/GitLab/Bitbucket) 連結，
    過濾掉文件站、捐款頁、issue tracker 等非倉庫 URL。
    """
    project_urls = info.get("project_urls") or {}

    # 第一優先: 明確標為 Source/Repository 的 key
    source_keys = ["Source", "Source Code", "Repository", "GitHub", "Code"]
    for key in source_keys:
        for pkey, purl in project_urls.items():
            if key.lower() in pkey.lower() and purl and _is_repo_url(purl):
                return purl

    # 第二優先: Homepage 但必須是 git 託管平台
    homepage_keys = ["Homepage", "Home"]
    for key in homepage_keys:
        for pkey, purl in project_urls.items():
            if key.lower() in pkey.lower() and purl and _is_repo_url(purl):
                return purl

    # 第三優先: home_page 欄位 (也必須是 git 託管平台)
    home_page = info.get("home_page")
    if home_page and _is_repo_url(home_page):
        return home_page

    # 最後掃描所有 project_urls 找倉庫連結
    for purl in project_urls.values():
        if purl and _is_repo_url(purl):
            # 排除 issue tracker、release notes 等子路徑
            url_lower = purl.lower()
            if "/issues" in url_lower or "/releases" in url_lower:
                continue
            return purl

    return None


def _extract_download_url(
    data: dict,
    version: str,
    name: str,
    python_version: str | None = None,
) -> tuple[str, str]:
    """提取離線下載連結，優先匹配 Windows AMD64 平台

    搜尋優先順序:
    1. 精確匹配: cpXYZ-cpXYZ-win_amd64.whl (指定 Python 版本)
    2. 通用 wheel: py3-none-any.whl / py2.py3-none-any.whl
    3. 任意 win_amd64 wheel
    4. 任意 wheel
    5. sdist (.tar.gz / .zip)
    6. PyPI 下載頁面 fallback

    Returns:
        (download_url, filename) 元組
    """
    urls = data.get("urls", [])
    if not urls:
        fallback = f"https://pypi.org/project/{name}/{version}/#files"
        return (fallback, "")

    cp_tags = _version_to_cp_tags(python_version) if python_version else []

    # 分類收集
    exact_win_amd64 = []   # cpXYZ-win_amd64 精確匹配
    any_win_amd64 = []     # 任意 cp-win_amd64
    universal_whl = []     # py3-none-any / py2.py3-none-any
    any_whl = []           # 任意 wheel
    sdist = []             # 原始碼壓縮包

    for item in urls:
        filename = item.get("filename", "")
        url = item.get("url", "")
        fn_lower = filename.lower()

        if fn_lower.endswith(".whl"):
            # 解析 wheel filename: {name}-{ver}-{python}-{abi}-{platform}.whl
            if "win_amd64" in fn_lower:
                if cp_tags and any(tag in fn_lower for tag in cp_tags):
                    exact_win_amd64.append((url, filename))
                else:
                    any_win_amd64.append((url, filename))
            elif "none-any" in fn_lower:
                universal_whl.append((url, filename))
            else:
                any_whl.append((url, filename))
        elif fn_lower.endswith((".tar.gz", ".zip")):
            sdist.append((url, filename))

    # 按優先順序選擇
    for candidates in [exact_win_amd64, universal_whl, any_win_amd64, any_whl, sdist]:
        if candidates:
            url, filename = candidates[0]
            return (url, filename)

    # Fallback
    fallback = f"https://pypi.org/project/{name}/{version}/#files"
    return (fallback, "")
