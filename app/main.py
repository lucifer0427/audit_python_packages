"""FastAPI 應用入口
本模組負責初始化 FastAPI 應用程式、設定中介軟體 (Middleware)、
管理全域資源 (如 HTTP 客戶端) 以及註冊 API 路由。
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import audit
from app.utils.ratelimit import InMemoryRateLimiter, RateLimitMiddleware

# 設定全域日誌格式，包含時間戳記、日誌層級、模組名稱與訊息
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    應用程式生命週期管理 (Lifespan)
    負責在伺服器啟動前初始化全域資源 (例如 HTTP 客戶端、快取目錄)，
    並在伺服器關閉後正確釋放資源，避免記憶體洩漏或連線殘留。
    """
    # --- 啟動階段 (Startup) ---
    # 快取首頁 HTML 內容至全域變數，避免每次使用者訪問根路徑時都重新從磁碟讀取--
    global _index_html
    template_path = Path(__file__).parent / "templates" / "upload.html"
    _index_html = template_path.read_text(encoding="utf-8")

    # 確保報告儲存目錄及其快取子目錄存在，若不存在則遞迴建立 (mkdir -p)
    settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (settings.REPORTS_DIR / ".cache").mkdir(parents=True, exist_ok=True)

    # 建立一個全域共用的 AsyncClient 實例並掛載到 app.state
    # 這樣可以實現連線池 (Connection Pooling)，大幅減少建立 TCP/TLS 連線的開銷
    # 設定統一的超時時間，防止外部 API (如 PyPI, OSV) 響應過慢導致伺服器執行緒被卡死
    client = httpx.AsyncClient(timeout=httpx.Timeout(settings.REQUEST_TIMEOUT))
    app.state.http_client = client

    logger.info("Python Dependency Auditor V1.0 已啟動")
    logger.info("翻譯模式: %s", settings.TRANSLATION_MODE)
    logger.info("報告目錄: %s", settings.REPORTS_DIR)

    yield  # 伺服器進入運行狀態，在此處等待停止訊號

    # --- 關閉階段 (Shutdown) ---
    # 伺服器停止時，正確關閉共用 HTTP 客戶端，釋放所有開啟的網路連線
    await app.state.http_client.aclose()
    logger.info("應用程式正在關閉...")


app = FastAPI(
    title="Python Dependency Auditor",
    description="自動化 Python 套件資安稽核工具",
    version="1.0.0",
    lifespan=lifespan,  # 綁定生命週期管理器
)

# 設定跨來源資源共用 (CORS)
# 避免前端在不同域名下調用 API 時被瀏覽器攔截
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # 僅允許設定檔中定義的域名訪問
    allow_credentials=True,
    allow_methods=["*"],  # 允許所有 HTTP 方法 (GET, POST, etc.)
    allow_headers=["*"],  # 允許所有請求標頭
)

# 速率限制中介軟體 (僅對 POST /api/audit 生效)
_rate_limiter = InMemoryRateLimiter(max_requests=10000, window_seconds=60)
app.add_middleware(RateLimitMiddleware, limiter=_rate_limiter)

# 配置靜態檔案服務 (CSS, JS)
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 註冊稽核相關的 API 路由
app.include_router(audit.router)

# 首頁 HTML 快取 (由 lifespan 初始化)
_index_html: str = ""


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index():
    """
    首頁路由 — 回傳啟動時快取的上傳介面 HTML
    """
    return HTMLResponse(content=_index_html)
