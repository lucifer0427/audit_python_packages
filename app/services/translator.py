"""功能摘要翻譯服務
 
根據設定選擇 builtin / OpenAI / Gemini 進行翻譯。
失敗時自動 fallback 到 builtin 模式。
"""

import logging
import re

from app.config import settings
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ===== 內建翻譯字典 (Top 100+ 常見套件) =====
BUILTIN_TRANSLATIONS: dict[str, str] = {
    "requests": "專業的 HTTP 請求庫，支援連線池與 SSL 驗證。",
    "flask": "輕量級 Web 框架，適合快速建構 API 與網頁應用。",
    "django": "全功能 Web 框架，內建 ORM、認證與管理後台。",
    "fastapi": "高效能非同步 Web 框架，自動生成 API 文件。",
    "numpy": "高效能數值運算函式庫，支援多維陣列操作。",
    "pandas": "資料分析處理函式庫，提供 DataFrame 結構化操作。",
    "scipy": "科學計算函式庫，涵蓋最佳化、統計與訊號處理。",
    "matplotlib": "資料視覺化繪圖函式庫，支援靜態與互動式圖表。",
    "pillow": "影像處理函式庫，支援開啟、編輯與儲存多種格式。",
    "sqlalchemy": "Python SQL 工具包與 ORM，支援多種資料庫引擎。",
    "celery": "分散式任務佇列系統，支援非同步與排程任務。",
    "redis": "Redis 資料庫 Python 客戶端，支援快取與訊息佇列。",
    "pytest": "功能強大的測試框架，支援插件與參數化測試。",
    "boto3": "AWS 官方 SDK，操作 S3、EC2 等雲端服務。",
    "cryptography": "密碼學工具包，提供對稱/非對稱加密與憑證處理。",
    "pydantic": "資料驗證與設定管理，使用 Python 型別提示。",
    "uvicorn": "高效能 ASGI 伺服器，支援 HTTP/1.1 與 WebSocket。",
    "gunicorn": "UNIX 環境 WSGI HTTP 伺服器，支援多 worker。",
    "jinja2": "現代化模板引擎，支援模板繼承與自動轉義。",
    "aiohttp": "非同步 HTTP 客戶端/伺服器框架。",
    "httpx": "新世代 HTTP 客戶端，支援同步與非同步請求。",
    "beautifulsoup4": "HTML/XML 解析函式庫，方便進行網頁抓取。",
    "scrapy": "高效能網路爬蟲框架，支援資料擷取與管線處理。",
    "lxml": "高效能 XML/HTML 處理函式庫，支援 XPath 查詢。",
    "paramiko": "SSH2 協定實作，支援遠端連線與檔案傳輸。",
    "psycopg2": "PostgreSQL 資料庫介面卡，符合 DB-API 2.0 規範。",
    "pymongo": "MongoDB 官方 Python 驅動程式。",
    "elasticsearch": "Elasticsearch 官方 Python 客戶端。",
    "docker": "Docker Engine API 的 Python 客戶端函式庫。",
    "kubernetes": "Kubernetes API 的 Python 客戶端函式庫。",
    "pyyaml": "YAML 解析與序列化函式庫。",
    "toml": "TOML 格式解析與序列化函式庫。",
    "click": "命令列介面建構工具，支援巢狀命令與參數解析。",
    "typer": "現代化 CLI 建構工具，基於型別提示自動生成。",
    "rich": "終端機富文字格式化函式庫，支援表格與語法高亮。",
    "tqdm": "快速可擴展的進度條函式庫。",
    "loguru": "簡化的 Python 日誌函式庫。",
    "sentry-sdk": "Sentry 錯誤追蹤 SDK，即時監控應用程式異常。",
    "marshmallow": "物件序列化與反序列化函式庫，含資料驗證。",
    "werkzeug": "WSGI 工具函式庫，Flask 的底層引擎。",
    "starlette": "輕量級 ASGI 框架，FastAPI 的底層引擎。",
    "alembic": "SQLAlchemy 資料庫遷移工具。",
    "black": "Python 程式碼自動格式化工具。",
    "ruff": "高效能 Python linter 與格式化工具。",
    "mypy": "Python 靜態型別檢查工具。",
    "coverage": "程式碼測試覆蓋率量測工具。",
    "setuptools": "Python 套件建置與分發工具。",
    "wheel": "Python 套件 wheel 格式建置工具。",
    "pip": "Python 套件管理工具。",
    "virtualenv": "Python 虛擬環境建立工具。",
    "poetry": "Python 套件管理與建置工具，整合依賴管理。",
    "twine": "PyPI 套件上傳工具。",
    "sphinx": "Python 文件自動生成工具。",
    "mkdocs": "以 Markdown 撰寫的專案文件產生器。",
    "jsonschema": "JSON Schema 驗證函式庫。",
    "pyjwt": "JSON Web Token 編碼與解碼函式庫。",
    "python-jose": "JOSE 標準實作，含 JWT、JWS, JWE 支援。",
    "passlib": "密碼雜湊處理函式庫，支援多種演算法。",
    "bcrypt": "bcrypt 密碼雜湊函式庫。",
    "python-dotenv": "從 .env 檔案載入環境變數。",
    "python-multipart": "HTTP multipart 請求解析函式庫。",
    "aiofiles": "非同步檔案 I/O 操作函式庫。",
    "orjson": "高效能 JSON 序列化與反序列化函式庫。",
    "ujson": "超快速 JSON 編碼/解碼器。",
    "msgpack": "MessagePack 高效二進位序列化函式庫。",
    "protobuf": "Google Protocol Buffers 序列化框架。",
    "grpcio": "gRPC 高效能遠端過程呼叫框架。",
    "websockets": "WebSocket 客戶端/伺服器函式庫。",
    "tornado": "高效能非同步網路框架與 Web 伺服器。",
    "twisted": "事件驅動網路程式設計框架。",
    "fabric": "SSH 遠端部署與系統管理自動化工具。",
    "ansible": "IT 自動化平台，支援組態管理與部署。",
    "tensorflow": "機器學習與深度學習開源框架。",
    "torch": "深度學習研究框架，支援動態計算圖。",
    "scikit-learn": "機器學習函式庫，含分類、迴歸與聚類演算法。",
    "transformers": "最先進的自然語言處理模型函式庫。",
    "openai": "OpenAI API 官方 Python 客戶端。",
    "langchain": "大型語言模型應用開發框架。",
    "opencv-python": "電腦視覺與影像處理函式庫。",
    "networkx": "圖論與複雜網路分析函式庫。",
    "sympy": "符號數學運算函式庫。",
    "dateutil": "日期時間處理擴充函式庫。",
    "python-dateutil": "日期時間處理擴充函式庫。",
    "pytz": "世界時區定義與轉換函式庫。",
    "arrow": "人性化的日期時間處理函式庫。",
    "pendulum": "易用的日期時間處理函式庫，支援時區。",
    "certifi": "Mozilla CA 憑證套件，用於 SSL/TLS 驗證。",
    "urllib3": "功能完整的 HTTP 客戶端，含連線池管理。",
    "charset-normalizer": "字元編碼自動偵測函式庫。",
    "idna": "國際化域名應用程式 (IDNA) 處理函式庫。",
    "packaging": "Python 套件版本解析與比較工具。",
    "six": "Python 2/3 相容性工具函式庫。",
    "typing-extensions": "Python 型別提示向後相容擴充。",
    "attrs": "Python 類別屬性簡化定義工具。",
    "dataclasses": "資料類別裝飾器與函式工具。",
    "more-itertools": "進階迭代器工具函式庫。",
    "decorator": "Python 裝飾器簡化工具。",
    "wrapt": "函式裝飾器與猴子修補工具。",
    "pluggy": "插件管理與掛鉤系統框架。",
    "tenacity": "通用重試函式庫，支援指數退避策略。",
    "apscheduler": "進階 Python 排程器，支援 Cron 表達式。",
    "pip-audit": "Python 套件資安漏洞掃描工具。",
    "safety": "Python 依賴安全性檢查工具。",
    "bandit": "Python 程式碼安全性靜態分析工具。",
    "google-genai": "Google Gemini AI API 官方 Python 客戶端。",
    "pydantic-settings": "Pydantic 設定管理擴充，支援環境變數載入。",
}
 
# ===== 規則式翻譯用的詞彙對照表 =====
TERM_MAP: dict[str, str] = {
    "library": "函式庫",
    "framework": "框架",
    "toolkit": "工具包",
    "utility": "工具",
    "utilities": "工具集",
    "client": "客戶端",
    "server": "伺服器",
    "parser": "解析器",
    "validator": "驗證器",
    "serializer": "序列化器",
    "wrapper": "包裝器",
    "adapter": "介面卡",
    "driver": "驅動程式",
    "plugin": "插件",
    "extension": "擴充套件",
    "middleware": "中介軟體",
    "database": "資料庫",
    "caching": "快取",
    "cache": "快取",
    "logging": "日誌",
    "testing": "測試",
    "debugging": "除錯",
    "deployment": "部署",
    "authentication": "認證",
    "authorization": "授權",
    "encryption": "加密",
    "compression": "壓縮",
    "configuration": "設定",
    "monitoring": "監控",
    "scheduling": "排程",
    "asynchronous": "非同步",
    "async": "非同步",
    "concurrent": "並行",
    "distributed": "分散式",
    "lightweight": "輕量級",
    "high-performance": "高效能",
    "simple": "簡易",
    "powerful": "強大的",
    "modern": "現代化",
    "fast": "快速",
    "secure": "安全",
    "robust": "穩健",
    "flexible": "彈性",
    "scalable": "可擴展",
    "implementation": "實作",
    "interface": "介面",
    "bindings": "綁定",
    "integration": "整合",
}
 
 
class TranslatorService:
    """
    翻譯服務類別
    負責將套件的英文摘要翻譯為繁體中文。
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self.llm_client = llm_client

    async def translate_summaries(self, items: list[dict]) -> dict[str, str]:
        """批次翻譯套件功能摘要
        
        Args:
            items: [{"name": "pkg_name", "summary": "English summary"}]
        
        Returns:
            {"pkg_name": "中文摘要"}
        """
        results: dict[str, str] = {}
        
        # 先用內建字典填入已知翻譯
        pending_items = []
        for item in items:
            name = item["name"].lower()
            if name in BUILTIN_TRANSLATIONS:
                results[item["name"]] = BUILTIN_TRANSLATIONS[name]
            else:
                pending_items.append(item)
        
        # 若有未翻譯的且擁有 LLM 客戶端，嘗試 LLM 翻譯
        if pending_items and self.llm_client:
            llm_results = await self._try_llm_translate(pending_items)
            if llm_results:
                results.update(llm_results)
                # 更新 pending_items，移除已翻譯的
                pending_items = [
                    item for item in pending_items
                    if item["name"] not in llm_results
                ]
        
        # 剩餘的用規則式翻譯
        for item in pending_items:
            results[item["name"]] = self._rule_based_translate(item["summary"])
        
        return results

    async def _try_llm_translate(self, items: list[dict]) -> dict[str, str]:
        """嘗試使用注入的 LLM 客戶端翻譯，失敗則回傳空字典"""
        try:
            result = await self.llm_client.translate_summaries(items)
            logger.info("LLM 翻譯完成: %d/%d 個套件", len(result), len(items))
            return result
        except Exception as e:
            logger.error("LLM 翻譯失敗: %s，fallback 到 builtin 模式", e)
            return {}

    def _rule_based_translate(self, summary: str) -> str:
        """規則式翻譯: 詞彙替換 + 截斷"""
        if not summary:
            return "Python 套件。"
        
        text = summary.strip()
        
        # 移除開頭常見的冗餘片語
        prefixes_to_remove = [
            r"^A\s+",
            r"^An\s+",
            r"^The\s+",
            r"^Python\s+",
        ]
        for prefix in prefixes_to_remove:
            text = re.sub(prefix, "", text, flags=re.IGNORECASE)
        
        # 詞彙替換
        for en, zh in TERM_MAP.items():
            text = re.sub(rf"\b{re.escape(en)}\b", zh, text, flags=re.IGNORECASE)
        
        # 截斷到 30 字以內
        if len(text) > 30:
            text = text[:27] + "..."
        
        # 確保結尾有句號
        if not text.endswith(("。", ".", "...", "！")):
            text += "。"
        
        # 如果替換後仍有大量英文殘留，標記為未完全翻譯
        alpha_chars = sum(1 for c in text if c.isascii() and c.isalpha())
        if len(text) > 5 and alpha_chars / max(len(text), 1) > 0.7:
            text = f"{text} (原文)"
        
        return text
