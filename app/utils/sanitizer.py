"""資料清洗工具 — 防止 Markdown 表格格式崩潰"""

import re


def sanitize_for_table(text: str | None) -> str:
    """清洗文字使其適合放入 Markdown 表格欄位

    - 換行符 → <br>
    - 表格衝突符號 | → /
    - 移除多餘空白
    """
    if not text:
        return ""
    result = text.replace("\n", "<br>").replace("\r", "")
    result = result.replace("|", "/")
    result = re.sub(r"\s+", " ", result).strip()
    return result


def truncate(text: str | None, max_len: int = 100) -> str:
    """超長字串截斷處理"""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def clean_license(raw_license: str | None, classifiers: list[str] | None = None) -> str:
    """從 PyPI 回傳的 license 或 classifiers 提取乾淨的授權名稱

    優先使用 license 欄位；若為空或過長，改從 Trove classifiers 提取。
    """
    # 嘗試從 license 欄位取得
    if raw_license and raw_license.strip() and raw_license.strip().upper() != "UNKNOWN":
        cleaned = raw_license.strip()
        # 若 license 欄位是完整 license 文本（太長），嘗試從中提取關鍵字
        if len(cleaned) > 100:
            # 常見 license 模式匹配
            patterns = [
                r"(MIT\s*License)",
                r"(Apache\s*(?:License)?\s*(?:,?\s*Version)?\s*2\.0)",
                r"(BSD\s*\d?-?(?:Clause)?\s*License)",
                r"(GNU\s*(?:General|Lesser)?\s*Public\s*License\s*v?\d?)",
                r"(GPL-?\d?(?:\.\d)?(?:\+)?)",
                r"(LGPL-?\d?(?:\.\d)?(?:\+)?)",
                r"(MPL-?\d?(?:\.\d)?)",
                r"(ISC\s*License)",
                r"(Unlicense)",
            ]
            for pattern in patterns:
                match = re.search(pattern, cleaned, re.IGNORECASE)
                if match:
                    return truncate(match.group(1), 100)
            return truncate(cleaned, 100)
        return cleaned

    # Fallback: 從 Trove classifiers 提取
    if classifiers:
        license_prefix = "License :: OSI Approved :: "
        for cls in classifiers:
            if cls.startswith(license_prefix):
                return cls[len(license_prefix):]
        # 更寬鬆的匹配
        for cls in classifiers:
            if cls.startswith("License :: "):
                parts = cls.split(" :: ")
                return parts[-1] if parts else cls

    return "N/A"
