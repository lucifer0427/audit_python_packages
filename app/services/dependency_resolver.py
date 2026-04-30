"""相依性解析服務
本模組提供解析 requirements.txt 並補足所有遞迴相依套件的功能。
"""

import logging
import subprocess
import tempfile
import json
from pathlib import Path

logger = logging.getLogger(__name__)

def resolve_dependencies(requirements_content: bytes, python_version: str = "") -> tuple[bytes, list[tuple[str, str]]]:
    """
    解析 requirements.txt 並補足所有遞迴相依套件
    
    本服務利用 `uv pip compile` 的靜態解析能力，在不實際安裝套件的情況下，
    模擬指定 Python 版本環境，將-Direct Dependencies (直接依賴) 展開為 
    -Full Dependency Tree (完整依賴樹)，確保稽核範圍涵蓋所有遞迴相依套件。
    
    Returns:
        tuple: (新的標準格式 requirements.txt 內容 bytes, 解析後的套件清單 [(name, version), ...])
    """
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
            subprocess.run(cmd, capture_output=True, text=True, check=True)
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
        return new_reqs_content, resolved_packages


def get_offline_download_urls(requirements_content: bytes, python_version: str = "", platform: str = "win_amd64") -> dict[str, str]:
    """
    利用 pip --report 功能獲取指定平台與版本的精準下載連結
    
    Returns:
        dict: {package_name: download_url, ...}
    """
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
            "pip", "install", 
            "--dry-run", 
            "--report", str(report_file), 
            "--only-binary", ":all:", 
            "-r", str(req_file)
        ]
        
        if platform:
            cmd.extend(["--platform", platform])
        if python_version:
            cmd.extend(["--python-version", python_version])
            
        try:
            logger.info("執行 pip report 以獲取下載連結 (platform=%s, py=%s)...", platform, python_version)
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.error("pip report 執行失敗: %s", e.stderr)
            return {}

        if not report_file.exists():
            logger.error("pip 未生成 report.json")
            return {}

        # 解析 report.json
        try:
            with open(report_file, "r", encoding="utf-8") as f:
                report_data = json.load(f)
            
            download_urls = {}
            for install in report_data.get("install", []):
                name = install.get("metadata", {}).get("name")
                url = install.get("download_info", {}).get("url")
                if name and url:
                    download_urls[name.lower()] = url
            
            return download_urls
        except (json.JSONDecodeError, IOError) as e:
            logger.error("解析 report.json 失敗: %s", e)
            return {}

