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

    Args:
        requirements_content: requirements.txt 的文字內容

    Returns:
        {套件名稱: [漏洞列表]} 的字典
    """
    results: dict[str, list[VulnerabilityInfo]] = {}

    # 寫入暫存檔案
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as tmp:
        tmp.write(requirements_content)
        tmp_path = Path(tmp.name)

    try:
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
            timeout=300,
        )

        # pip-audit 回傳碼: 0=無漏洞, 1=有漏洞, 其他=錯誤
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
                        summary=v.get("description", "無描述")[:200],
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
        tmp_path.unlink(missing_ok=True)

    return results
