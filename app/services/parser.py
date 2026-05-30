"""requirements.txt 解析模組

支援 UTF-8 / UTF-16 自動偵測，解析套件名稱與版本規格。
"""

import logging
import re

from app.models.schemas import PackageInfo

logger = logging.getLogger(__name__)

# 版本規格運算子
VERSION_OPERATORS = ("==", ">=", "<=", "!=", "~=", ">", "<", "===")


def detect_encoding(raw_bytes: bytes) -> str:
    """偵測檔案編碼 (BOM 優先)"""
    if raw_bytes.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if raw_bytes.startswith(b"\xfe\xff"):
        return "utf-16-be"
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    return "utf-8"


def parse_requirements(content: bytes | str) -> list[PackageInfo]:
    """解析 requirements.txt 內容

    本函數負責將原始的檔案內容轉換為結構化的 PackageInfo 物件清單。
    它支援自動編碼偵測，並能處理複雜的 requirements 格式，包括：
    - 移除註解與空行
    - 處理環境標記 (Environment Markers)
    - 處理套件擴展 (Extras, e.g., uvicorn[standard])
    - 解析版本運算子 (==, >=, etc.)

    Args:
        content: 檔案內容 (bytes 或 str)

    Returns:
        解析後的套件清單 (PackageInfo)
    """
    if content is None:
        return []
    if isinstance(content, bytes):
        # 針對 bytes 內容，優先偵測 BOM 以決定正確的解碼方式 (UTF-8 / UTF-16)
        encoding = detect_encoding(content)
        text = content.decode(encoding)
        if text.startswith("\ufeff"):
            text = text[1:]
    else:
        text = content

    packages = []
    for line_num, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()

        # 1. 過濾無效行：跳過空行、以 # 開頭的註解行、以及以 - 開頭的 pip 選項行 (如 -r, -e)
        if not line or line.startswith("#") or line.startswith("-"):
            continue

        # 2. 移除行內註解：將 "requests==2.31.0 # a great lib" 轉換為 "requests==2.31.0"
        if " #" in line:
            line = line[: line.index(" #")].strip()

        # 3. 移除環境標記：將 "requests==2.31.0; python_version < '3.12'" 轉換為 "requests==2.31.0"
        # 這是為了簡化後續的版本比對邏輯
        if ";" in line:
            line = line[: line.index(";")].strip()

        # 4. 處理套件擴展 (Extras)：將 "uvicorn[standard]==0.20.0" 轉換為 "uvicorn==0.20.0"
        # 我們僅關心基礎套件的安全性，不對 extras 進行單獨掃描
        extras_match = re.match(r"^([a-zA-Z0-9_.-]+)\[.*?\](.*)", line)
        if extras_match:
            line = extras_match.group(1) + extras_match.group(2)

        # 5. 解析套件名稱和版本號
        pkg_info = _parse_package_line(line, line_num)
        if pkg_info:
            packages.append(pkg_info)

    logger.info("解析完成: 共 %d 個套件", len(packages))
    return packages


def _parse_package_line(line: str, line_num: int) -> PackageInfo | None:
    """解析單一套件行"""
    # 嘗試匹配版本規格
    for op in sorted(VERSION_OPERATORS, key=len, reverse=True):
        if op in line:
            parts = line.split(op, 1)
            name = parts[0].strip()
            version_part = parts[1].strip()

            # 處理複合版本 (例: >=1.0,<2.0) 取第一個版本
            if "," in version_part:
                version_part = version_part.split(",")[0].strip()

            if not _is_valid_name(name):
                logger.warning("第 %d 行: 無效的套件名稱 '%s'", line_num, name)
                return None

            return PackageInfo(
                name=name,
                version=version_part if op == "==" else None,
                version_spec=f"{op}{version_part}",
            )

    # 無版本規格 — 純套件名稱
    name = line.strip()
    if not _is_valid_name(name):
        logger.warning("第 %d 行: 無效的套件名稱 '%s'", line_num, name)
        return None

    return PackageInfo(name=name)


def _is_valid_name(name: str) -> bool:
    """驗證套件名稱是否合法"""
    return bool(re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?$", name))
