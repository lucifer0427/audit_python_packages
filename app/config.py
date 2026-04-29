"""應用程式設定模組"""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """應用程式設定，從環境變數載入"""

    # === 路徑設定 ===
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    REPORTS_DIR: Path = Path("/tmp/python_auditor_reports")

    # === 外部 API ===
    PYPI_BASE_URL: str = "https://pypi.org/pypi"
    OSV_API_URL: str = "https://api.osv.dev/v1/query"
    SNYK_BASE_URL: str = "https://security.snyk.io/package/pip"

    # === 網路設定 ===
    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    ALLOWED_ORIGINS: list[str] = ["*"]

    # === LLM 翻譯設定 ===
    TRANSLATION_MODE: Literal["builtin", "openai", "gemini"] = "builtin"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.0-flash"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
