"""PyPI JSON API 客戶端
負責查詢 PyPI 官方 API 以獲取套件的元數據 (Metadata)，
包括授權協議、功能摘要、原始碼倉庫連結以及針對特定平台的安裝檔下載連結。
"""

import logging

import anyio
import diskcache
import httpx

from app.config import settings
from app.models.schemas import PyPIPackageData
from app.utils.sanitizer import clean_license

logger = logging.getLogger(__name__)


class PyPIClient:
    """
    PyPI API 客戶端類別
    透過注入的 httpx.AsyncClient 獲取套件詳細資訊。
    """

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        # 使用持久化快取，存放在報告目錄下的 .cache/pypi
        self._cache = diskcache.Cache(settings.REPORTS_DIR / ".cache" / "pypi", disk=diskcache.JSONDisk)

    def _version_to_cp_tags(self, python_version: str) -> list[str]:
        """
        將 Python 版本字串 (如 "3.12" 或 "3.13t") 轉換為 CPython wheel tag (如 ["cp312", "cp313t"])
        用於後續篩選最適合目標環境的安裝檔案。
        """
        if not python_version:
            return []

        # 處理 3.14t 這種格式
        has_t = python_version.endswith("t")
        clean_version = python_version[:-1] if has_t else python_version

        parts = clean_version.split(".")
        if len(parts) >= 2:
            major, minor = parts[0], parts[1]
            tag = f"cp{major}{minor}"
            if has_t:
                tag += "t"
            return [tag]
        return []

    async def get_package_info(
        self,
        name: str,
        version: str | None = None,
        python_version: str | None = None,
    ) -> PyPIPackageData:
        """
        查詢 PyPI 套件詳細資訊

        本方法實作了「快取優先」策略，使用 (名稱, 版本, Python版本) 作為 Key，
        大幅降低重複查詢 PyPI API 的次數，減少網路延遲。

        Args:
            name: 套件名稱
            version: 指定版本，若為 None 則查詢最新穩定版
            python_version: 目標 Python 版本，用於精準篩選 Windows AMD64 的安裝檔 (.whl)
        """
        cache_key = (name, version, python_version)
        cached = await anyio.to_thread.run_sync(lambda: cache_key in self._cache)
        if cached:
            return await anyio.to_thread.run_sync(lambda: self._cache[cache_key])

        # 根據是否指定版本建構 PyPI JSON API URL
        url = f"{settings.PYPI_BASE_URL}/{name}/json"
        if version:
            url = f"{settings.PYPI_BASE_URL}/{name}/{version}/json"

        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.error("PyPI 查詢失敗 [%s]: %s", name, e)
            # 當 API 查詢失敗時，回傳一個預設的空資料物件，防止整個稽核流程崩潰
            result = PyPIPackageData(
                version=version or "unknown",
                summary="",
                license="N/A",
                source_repo=None,
                download_url="",
                download_filename="",
            )
            return result

        info = data.get("info", {})
        resolved_version = info.get("version", version or "unknown")

        # 1. 授權提取：調用 clean_license 工具函數，綜合判斷 license 欄位、Trove classifiers 與新版 license_expression
        license_type = clean_license(
            info.get("license"),
            info.get("classifiers", []),
            info.get("license_expression"),
        )

        # 2. 原始碼倉庫提取：從 project_urls 中使用優先級算法尋找最可能的 GitHub/GitLab 連結
        source_repo = self._extract_source_repo(info)

        # 3. 下載連結提取：依據指定平台 (Windows AMD64) 與 Python 版本篩選最佳的 wheel (.whl) 檔案
        download_url, download_filename = self._extract_download_url(data, resolved_version, name, python_version)

        result = PyPIPackageData(
            version=resolved_version,
            summary=info.get("summary", "") or "",
            license=license_type,
            source_repo=source_repo,
            download_url=download_url,
            download_filename=download_filename,
        )

        # 將結果儲存至磁碟快取，提升後續重複請求的效能
        await anyio.to_thread.run_sync(lambda: self._cache.__setitem__(cache_key, result))
        return result

    def _is_repo_url(self, url: str) -> bool:
        """判斷 URL 是否指向已知的程式碼託管平台 (GitHub, GitLab, etc.)"""
        repo_hosts = ["github.com", "gitlab.com", "bitbucket.org", "codeberg.org"]
        url_lower = url.lower()
        return any(host in url_lower for host in repo_hosts)

    def _extract_source_repo(self, info: dict) -> str | None:
        """
        從 PyPI 資訊中提取最可能的原始碼倉庫 URL
        """
        project_urls = info.get("project_urls") or {}

        # 第一優先: 明確標為 Source/Repository 的 Key
        source_keys = ["Source", "Source Code", "Repository", "GitHub", "Code"]
        for key in source_keys:
            for pkey, purl in project_urls.items():
                if key.lower() in pkey.lower() and purl and self._is_repo_url(purl):
                    return purl

        # 第二優先: Homepage 但必須是 git 託管平台
        homepage_keys = ["Homepage", "Home"]
        for key in homepage_keys:
            for pkey, purl in project_urls.items():
                if key.lower() in pkey.lower() and purl and self._is_repo_url(purl):
                    return purl

        # 第三優先: home_page 欄位
        home_page = info.get("home_page")
        if home_page and self._is_repo_url(home_page):
            return home_page

        # 最後兜底: 掃描所有 project_urls 尋找任何 git 連結
        for purl in project_urls.values():
            if purl and self._is_repo_url(purl):
                url_lower = purl.lower()
                if "/issues" in url_lower or "/releases" in url_lower:
                    continue
                return purl

        return None

    def _extract_download_url(
        self,
        data: dict,
        version: str,
        name: str,
        python_version: str | None = None,
        target_platform: str = "",
    ) -> tuple[str, str]:
        """
        提取離線下載連結，優先匹配指定平台 (預設 Windows AMD64)
        """
        urls = data.get("urls", [])
        if not urls:
            fallback = f"https://pypi.org/project/{name}/{version}/#files"
            return (fallback, "")

        requested_cp_tags = self._version_to_cp_tags(python_version) if python_version else []
        is_freethreaded_requested = bool(python_version and "t" in python_version)

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
                # Wheel 檔名格式: {dist}-{ver}(-{build})?-{py}-{abi}-{plat}.whl
                parts = fn_lower[:-4].split("-")
                if len(parts) >= 5:
                    # 正常格式，倒數三個部分分別是 python tag, abi tag, platform tag
                    py_tags = parts[-3].split(".")
                    abi_tags = parts[-2].split(".")
                    platform_tag = parts[-1]
                elif len(parts) == 4:
                    # 某些測試或舊格式可能只有 4 部分 (缺少 ABI)
                    py_tags = parts[-2].split(".")
                    abi_tags = ["none"]
                    platform_tag = parts[-1]
                else:
                    continue

                # 檢查是否為 freethreaded (ABI 標籤以 't' 結尾，如 cp313t)
                is_freethreaded_wheel = any(t.endswith("t") and t.startswith("cp") for t in py_tags + abi_tags)

                # 核心修正：如果用戶沒要求 freethreaded，則跳過帶有 't' 標籤的 wheel
                # 避免 cp314 誤匹配到 cp314t
                if is_freethreaded_wheel and not is_freethreaded_requested:
                    continue

                if not target_platform:
                    any_whl.append((url, filename))
                elif target_platform in platform_tag:
                    if requested_cp_tags and any(tag in py_tags or tag in abi_tags for tag in requested_cp_tags):
                        exact_win_amd64.append((url, filename))
                    else:
                        any_win_amd64.append((url, filename))
                elif "none-any" in py_tags or "none-any" in abi_tags:
                    universal_whl.append((url, filename))
                else:
                    any_whl.append((url, filename))
            elif fn_lower.endswith((".tar.gz", ".zip")):
                sdist.append((url, filename))

        # 按優先級排序返回
        for candidates in [exact_win_amd64, universal_whl, any_win_amd64, any_whl, sdist]:
            if candidates:
                url, filename = candidates[0]
                return (url, filename)

        fallback = f"https://pypi.org/project/{name}/{version}/#files"
        return (fallback, "")
