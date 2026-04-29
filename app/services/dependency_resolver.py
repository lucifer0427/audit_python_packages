"""相依性解析服務
本模組提供解析 requirements.txt 並補足所有遞迴相依套件的功能。
"""

import logging
import subprocess
import tempfile
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
