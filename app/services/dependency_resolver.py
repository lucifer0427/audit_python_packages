"""相依性解析服務
本模組提供解析 requirements.txt 並補足所有遞迴相依套件的功能。
"""

import hashlib
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

import diskcache

from app.config import settings

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600  # 1 hour TTL for cached resolutions


class _CacheProxy:
    """Proxy that re-creates diskcache.Cache when settings.REPORTS_DIR changes."""

    def __init__(self):
        self._impl: diskcache.Cache | None = None
        self._path: Path | None = None

    def _ensure(self) -> diskcache.Cache:
        path = settings.REPORTS_DIR / ".cache" / "dependency_resolver"
        if self._impl is None or self._path != path:
            self._impl = diskcache.Cache(path, disk=diskcache.JSONDisk)
            self._path = path
        return self._impl

    def __contains__(self, key: str) -> bool:
        return key in self._ensure()

    def __getitem__(self, key: str):
        return self._ensure()[key]

    def set(self, key: str, value, expire: int | None = None) -> None:
        self._ensure().set(key, value, expire=expire)

    def clear(self) -> None:
        self._ensure().clear()


_cache = _CacheProxy()


def _make_cache_key(requirements_content: bytes, python_version: str, platform: str = "") -> str:
    """Generate a deterministic cache key from the inputs."""
    raw = requirements_content.decode("utf-8", errors="replace") + "|" + python_version + "|" + platform
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_dependencies(requirements_content: bytes, python_version: str = "") -> tuple[bytes, list[tuple[str, str]]]:
    """
    解析 requirements.txt 並補足所有遞迴相依套件

    本服務利用 `uv pip compile` 的靜態解析能力，在不實際安裝套件的情況下，
    模擬指定 Python 版本環境，將-Direct Dependencies (直接依賴) 展開為
    -Full Dependency Tree (完整依賴樹)，確保稽核範圍涵蓋所有遞迴相依套件。

    Returns:
        tuple: (新的標準格式 requirements.txt 內容 bytes, 解析後的套件清單 [(name, version), ...])
    """
    cache_key = _make_cache_key(requirements_content, python_version)
    if cache_key in _cache:
        cached = _cache[cache_key]
        logger.info("相依性解析命中快取 (key=%s...)", cache_key[:8])
        return (cached[0].encode("utf-8"), [(n, v) for n, v in cached[1]])

    with tempfile.TemporaryDirectory() as tmpdir:
        # 在暫存目錄建立臨時檔案，避免污染工作目錄
        req_file = Path(tmpdir) / "requirements.txt"
        req_file.write_bytes(requirements_content)

        resolved_file = Path(tmpdir) / "resolved.txt"

        # 構建 uv 命令
        # -o: 指定輸出檔案路徑
        # --python-version: 關鍵參數，實現環境隔離 (Environmental Isolation)，
        # 允許在 Linux 伺服器上解析針對 Windows 或特定 Python 版本 (如 3.11) 的依賴
        cmd = ["uv", "pip", "compile", str(req_file), "-o", str(resolved_file)]
        if python_version:
            cmd.extend(["--python-version", python_version])

        try:
            logger.info("執行相依性解析 (using uv)...")
            # 執行外部進程並等待結果
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        except subprocess.TimeoutExpired:
            logger.error("uv 解析超時 (120s)")
            return requirements_content, []
        except subprocess.CalledProcessError as e:
            logger.error("uv 解析失敗: %s", e.stderr)
            # 若解析失敗 (如包含不存在的套件版本)，則回傳原內容，確保稽核流程能繼續進行
            return requirements_content, []

        if not resolved_file.exists():
            logger.error("uv 未生成解析檔案")
            return requirements_content, []

        resolved_packages = []

        # 解析 uv 產生的標準 requirements 格式 (package==version)
        for line in resolved_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            # 過濾掉空行與 uv 生成的註解 (以 # 開頭)
            if not line or line.startswith("#"):
                continue
            if "==" in line:
                name, version = line.split("==", 1)
                # 處理 Environment Markers (例如 ; python_version < '3.12')
                # 僅保留版本號部分，移除環境條件標記
                if ";" in version:
                    version = version.split(";", 1)[0].strip()
                resolved_packages.append((name.strip(), version.strip()))

        # 根據套件名稱進行字母排序，確保生成的報告具有一致性
        resolved_packages.sort(key=lambda x: x[0].lower())

        if not resolved_packages:
            logger.warning("uv 未解析出有效套件清單，回傳原內容")
            return requirements_content, []

        # 生成乾淨的標準 requirements.txt 格式內容 (移除 uv 的 # via 註釋，回歸標準格式)
        new_reqs_lines = [f"{name}=={version}" for name, version in resolved_packages]
        new_reqs_content = "\n".join(new_reqs_lines).encode("utf-8")

        logger.info("相依性解析完成，共解析出 %d 個套件", len(resolved_packages))
        _cache.set(cache_key, (new_reqs_content.decode("utf-8"), resolved_packages), expire=_CACHE_TTL)
        return new_reqs_content, resolved_packages


def get_offline_download_urls(
    requirements_content: bytes, python_version: str = "", platform: str = "win_amd64"
) -> dict[str, str]:
    """
    利用 pip --report 功能獲取指定平台與版本的精準下載連結

    Returns:
        dict: {package_name: download_url, ...}
    """
    cache_key = _make_cache_key(requirements_content, python_version, platform) + "_urls"
    if cache_key in _cache:
        cached = _cache[cache_key]
        logger.info("下載 URL 查詢命中快取 (key=%s...)", cache_key[:8])
        return cached

    with tempfile.TemporaryDirectory() as tmpdir:
        req_file = Path(tmpdir) / "requirements.txt"
        req_file.write_bytes(requirements_content)

        report_file = Path(tmpdir) / "report.json"

        # 構建 pip install --report 命令
        # --dry-run: 不實際安裝
        # --report: 產出 JSON 格式的解析報告
        # --platform: 指定目標平台 (如 win_amd64)
        # --python-version: 指定目標 Python 版本
        # --only-binary :all: 強制尋找 binary wheel 檔，避免觸發 source build 解析
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--dry-run",
            "--report",
            str(report_file),
            "--only-binary",
            ":all:",
            "-r",
            str(req_file),
        ]

        if platform:
            cmd.extend(["--platform", platform])
        if python_version:
            cmd.extend(["--python-version", python_version])

        try:
            logger.info("執行 pip report 以獲取下載連結 (platform=%s, py=%s)...", platform, python_version)
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        except subprocess.TimeoutExpired:
            logger.error("pip report 執行超時 (120s)")
            return {}
        except subprocess.CalledProcessError as e:
            logger.error("pip report 執行失敗: %s", e.stderr)
            return {}

        if not report_file.exists():
            logger.error("pip 未生成 report.json")
            return {}

        # 解析 report.json
        try:
            with open(report_file, encoding="utf-8") as f:
                report_data = json.load(f)

            download_urls = {}
            for install in report_data.get("install", []):
                name = install.get("metadata", {}).get("name")
                url = install.get("download_info", {}).get("url")
                if name and url:
                    download_urls[name.lower()] = url

            _cache.set(cache_key, download_urls, expire=_CACHE_TTL)
            return download_urls
        except (OSError, json.JSONDecodeError) as e:
            logger.error("解析 report.json 失敗: %s", e)
            return {}


def clear_cache():
    """Clear the dependency resolver cache."""
    _cache.clear()
    logger.info("相依性解析快取已清除")
