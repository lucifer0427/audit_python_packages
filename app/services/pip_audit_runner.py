"""pip-audit CLI 包裝模組

透過 subprocess 呼叫 pip-audit 並解析 JSON 輸出。
"""

import json
import logging
import subprocess
import tempfile
from pathlib import Path

from app.models.schemas import VulnerabilityInfo

logger = logging.getLogger(__name__)


def run_pip_audit(requirements_content: str) -> dict[str, list[VulnerabilityInfo]]:
    """執行 pip-audit 掃描
    
    本函數透過 subprocess 呼叫外部 `pip-audit` CLI 工具，並解析其回傳的 JSON 輸出。
    pip-audit 能提供與 OSV API 不同維度的漏洞掃描結果，作為安全性分析的雙重驗證。

    Args:
        requirements_content: 欲掃描的 requirements.txt 文字內容
    
    Returns:
        {套件名稱: [漏洞列表]} 的字典
    """
    results: dict[str, list[VulnerabilityInfo]] = {}

    # 將掃描對象寫入暫存檔案，因為 pip-audit 的 -r 參數要求傳入檔案路徑而非字串
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as tmp:
        tmp.write(requirements_content)
        tmp_path = Path(tmp.name)

    try:
        # 構建 pip-audit 命令
        # --format json: 要求回傳 JSON 格式以便程式化解析
        # --progress-spinner off: 關閉進度動畫，避免雜訊污染 stdout 輸出
        cmd = [
            "pip-audit",
            "-r", str(tmp_path),
            "--format", "json",
            "--progress-spinner", "off",
        ]

        logger.info("執行 pip-audit: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300, # 設定 5 分鐘超時，防止某些複雜依賴導致掃描卡死
        )

        # pip-audit 回傳碼定義: 0 = 無漏洞, 1 = 發現漏洞, 其他 = 執行錯誤
        if proc.returncode not in (0, 1):
            logger.warning("pip-audit 非預期回傳碼 %d: %s", proc.returncode, proc.stderr)
            return results

        if not proc.stdout.strip():
            logger.info("pip-audit 無輸出")
            return results

        data = json.loads(proc.stdout)
        dependencies = data.get("dependencies", [])

        for dep in dependencies:
            name = dep.get("name", "")
            vulns = dep.get("vulns", [])

            if not vulns:
                continue

            vuln_list = []
            for v in vulns:
                vuln_list.append(
                    VulnerabilityInfo(
                        vuln_id=v.get("id", "UNKNOWN"),
                        summary=v.get("description", "無描述")[:200], # 截斷長度防止報告表格崩潰
                        severity=None,
                        snyk_url=None,
                    )
                )

            results[name.lower()] = vuln_list

    except subprocess.TimeoutExpired:
        logger.error("pip-audit 執行超時 (300s)")
    except json.JSONDecodeError as e:
        logger.error("pip-audit 輸出解析失敗: %s", e)
    except FileNotFoundError:
        logger.error("pip-audit 未安裝，跳過 CLI 掃描")
    finally:
        # 務必刪除暫存檔案，避免在伺服器上堆積大量垃圾檔案
        tmp_path.unlink(missing_ok=True)

    return results

