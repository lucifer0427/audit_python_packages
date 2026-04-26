"""PyPI JSON API 客戶端
負責查詢 PyPI 官方 API 以獲取套件的元數據 (Metadata)，
包括授權協議、功能摘要、原始碼倉庫連結以及針對特定平台的安裝檔下載連結。
"""

import logging
import re

import httpx
from async_lru import alru_cache

from app.config import settings
from app.utils.sanitizer import clean_license

logger = logging.getLogger(__name__)

def _version_to_cp_tags(python_version: str) -> list[str]:
    """
    將 Python 版本字串 (如 "3.12") 轉換為 CPython wheel tag (如 ["cp312"])
    用於後續篩選最適合目標環境的安裝檔案。
    """
    if not python_version:
        return []
    parts = python_version.split(".")
    if len(parts) >= 2:
        major, minor = parts[0], parts[1]
        return [f"cp{major}{minor}"]
    return []


# 全域客戶端實例，由 main.py 的 lifespan 初始化
_client: httpx.AsyncClient | None = None


def init_client(client: httpx.AsyncClient):
    """初始化全域 HTTP 客戶端"""
    global _client
    _client = client


@alru_cache(maxsize=128)
async def get_package_info(
    name: str,
    version: str | None = None,
    python_version: str | None = None,
) -> dict:
    """
    查詢 PyPI 套件詳細資訊
    
    Args:
        name: 套件名稱
        version: 指定版本，若為 None 則查詢最新穩定版
        python_version: 目標 Python 版本，用於篩選 Windows AMD64 的 wheel 檔案
    """
    if _client is None:
        logger.error("PyPI 客戶端未初始化")
        return {
            "version": version or "unknown",
            "summary": "",
            "license": "N/A",
            "source_repo": None,
            "download_url": "",
            "download_filename": "",
        }

    # 根據是否指定版本建構 API URL
    url = f"{settings.PYPI_BASE_URL}/{name}/json"
    if version:
        url = f"{settings.PYPI_BASE_URL}/{name}/{version}/json"

    try:
        resp = await _client.get(url)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        logger.error("PyPI 查詢失敗 [%s]: %s", name, e)
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

    # 1. 授權提取：透過 clean_license 綜合判斷 license 欄位與 classifiers
    license_type = clean_license(
        info.get("license"),
        info.get("classifiers", []),
        info.get("license_expression"),
    )

    # 2. 原始碼倉庫提取：從 project_urls 中尋找 GitHub/GitLab 等連結
    source_repo = _extract_source_repo(info)

    # 3. 下載連結提取：依據平台與 Python 版本篩選最佳的 .whl 檔案
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
    """判斷 URL 是否指向已知的程式碼託管平台 (GitHub, GitLab, etc.)"""
    repo_hosts = ["github.com", "gitlab.com", "bitbucket.org", "codeberg.org"]
    url_lower = url.lower()
    return any(host in url_lower for host in repo_hosts)


def _extract_source_repo(info: dict) -> str | None:
    """
    從 PyPI 資訊中提取最可能的原始碼倉庫 URL
    
    篩選邏輯：
    1. 優先找 key 包含 "Source", "Repository" 等字眼的 project_urls
    2. 其次尋找 Homepage 並確認是否為 git 平台
    3. 最後掃描所有 project_urls 並排除 issues/releases 等非倉庫路徑
    """
    project_urls = info.get("project_urls") or {}

    # 第一優先: 明確標為 Source/Repository 的 Key
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

    # 第三優先: home_page 欄位
    home_page = info.get("home_page")
    if home_page and _is_repo_url(home_page):
        return home_page

    # 最後兜底: 掃描所有 project_urls 尋找任何 git 連結
    for purl in project_urls.values():
        if purl and _is_repo_url(purl):
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
    """
    提取離線下載連結，優先匹配 Windows AMD64 平台
    
    篩選優先順序 (由高到低)：
    1. 精確匹配：對應 Python 版本且為 win_amd64 的 wheel (如 cp312-win_amd64)
    2. 通用 Wheel：跨版本的 wheel (如 py3-none-any)
    3. 任意 Win AMD64 Wheel：只要是 Windows 64位元即可
    4. 任意 Wheel：任何平台
    5. 原始碼包 (sdist)：.tar.gz 或 .zip
    6. Fallback：直接指向 PyPI 的檔案頁面
    """
    urls = data.get("urls", [])
    if not urls:
        fallback = f"https://pypi.org/project/{name}/{version}/#files"
        return (fallback, "")

    cp_tags = _version_to_cp_tags(python_version) if python_version else []

    # 建立分類桶，用於後續按優先級選擇
    exact_win_amd64 = []
    any_win_amd64 = []
    universal_whl = []
    any_whl = []
    sdist = []

    for item in urls:
        filename = item.get("filename", "")
        url = item.get("url", "")
        fn_lower = filename.lower()

        if fn_lower.endswith(".whl"):
            # 判斷是否為 Windows AMD64 平台
            if "win_amd64" in fn_lower:
                # 檢查是否匹配指定的 Python 版本 (cp tag)
                if cp_tags and any(tag in fn_lower for tag in cp_tags):
                    exact_win_amd64.append((url, filename))
                else:
                    any_win_amd64.append((url, filename))
            # 判斷是否為通用 Wheel (none-any)
            elif "none-any" in fn_lower:
                universal_whl.append((url, filename))
            else:
                any_whl.append((url, filename))
        elif fn_lower.endswith((".tar.gz", ".zip")):
            sdist.append((url, filename))

    # 按優先級順序回傳第一個匹配項
    for candidates in [exact_win_amd64, universal_whl, any_win_amd64, any_whl, sdist]:
        if candidates:
            url, filename = candidates[0]
            return (url, filename)

    # 若完全找不到適用的檔案，回傳 PyPI 檔案頁面
    fallback = f"https://pypi.org/project/{name}/{version}/#files"
    return (fallback, "")
