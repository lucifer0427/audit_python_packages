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
    解析 requirements.txt 並補足所有相依套件
    
    使用 uv pip compile 功能來獲取完整的相依樹而不需要實際安裝。
    
    Returns:
        tuple: (新的 requirements.txt 內容 bytes, 解析後的套件清單 [(name, version), ...])
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        req_file = Path(tmpdir) / "requirements.txt"
        req_file.write_bytes(requirements_content)
        
        resolved_file = Path(tmpdir) / "resolved.txt"
        
        # 構建 uv 命令
        # -o: 指定輸出檔案
        # --python-version: 針對特定 Python 版本解析 (環境隔離)
        cmd = ["uv", "pip", "compile", str(req_file), "-o", str(resolved_file)]
        if python_version:
            cmd.extend(["--python-version", python_version])
            
        try:
            logger.info("執行相依性解析 (using uv)...")
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.error("uv 解析失敗: %s", e.stderr)
            # 如果解析失敗，回傳原內容，避免整個流程中斷
            return requirements_content, []

        if not resolved_file.exists():
            logger.error("uv 未生成解析檔案")
            return requirements_content, []

        resolved_packages = []
        
        # 解析 uv 產生的 requirements 格式 (package==version)
        for line in resolved_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "==" in line:
                name, version = line.split("==", 1)
                # 處理可能存在的環境標記 (Environment Markers)
                if ";" in version:
                    version = version.split(";", 1)[0].strip()
                resolved_packages.append((name.strip(), version.strip()))

        # 根據名稱排序
        resolved_packages.sort(key=lambda x: x[0].lower())
        
        # 生成乾淨的 requirements.txt 內容 (移除 uv 的 # via 註釋，回歸標準格式)
        new_reqs_lines = [f"{name}=={version}" for name, version in resolved_packages]
        new_reqs_content = "\n".join(new_reqs_lines).encode("utf-8")
        
        logger.info("相依性解析完成，共解析出 %d 個套件", len(resolved_packages))
        return new_reqs_content, resolved_packages
