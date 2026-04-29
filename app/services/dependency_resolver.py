"""相依性解析服務
本模組提供解析 requirements.txt 並補足所有遞迴相依套件的功能。
"""

import json
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

def resolve_dependencies(requirements_content: bytes, python_version: str = "") -> tuple[bytes, list[tuple[str, str]]]:
    """
    解析 requirements.txt 並補足所有相依套件
    
    使用 pip install --dry-run --report 功能來獲取完整的相依樹而不需要實際安裝。
    
    Returns:
        tuple: (新的 requirements.txt 內容 bytes, 解析後的套件清單 [(name, version), ...])
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        req_file = Path(tmpdir) / "requirements.txt"
        req_file.write_bytes(requirements_content)
        
        report_file = Path(tmpdir) / "report.json"
        
        # 構建 pip 命令
        # --dry-run: 不實際安裝
        # --report: 生成 JSON 格式的解析報告
        cmd = [
            "pip", "install", 
            "--dry-run", 
            "--report", str(report_file), 
            "-r", str(req_file)
        ]
        
        # 如果有指定 python_version，這裡較難直接透過 pip 命令指定，
        # 因為 pip 運行在當前環境。在實際部署中，可能需要不同的容器或 venv。
        # 但為了本功能的實現，我們假設當前環境能代表目標版本或使用 PyPI 資訊。
        
        try:
            logger.info("執行相依性解析...")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.error("pip 解析失敗: %s", e.stderr)
            # 如果解析失敗，回傳原內容，避免整個流程中斷
            return requirements_content, []

        if not report_file.exists():
            logger.error("pip 未生成報告檔案")
            return requirements_content, []

        with open(report_file, "r", encoding="utf-8") as f:
            report_data = json.load(f)

        resolved_packages = []
        # 從 report.json 的 'install' 列表中提取所有套件
        for entry in report_data.get("install", []):
            metadata = entry.get("metadata", {})
            name = metadata.get("name")
            version = metadata.get("version")
            if name and version:
                resolved_packages.append((name, version))

        # 根據名稱排序
        resolved_packages.sort(key=lambda x: x[0].lower())

        # 生成新的 requirements.txt 內容
        new_reqs_lines = [f"{name}=={version}" for name, version in resolved_packages]
        new_reqs_content = "\n".join(new_reqs_lines).encode("utf-8")

        logger.info("相依性解析完成，共解析出 %d 個套件", len(resolved_packages))
        return new_reqs_content, resolved_packages
