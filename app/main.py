"""FastAPI 應用入口"""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import audit

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Python Dependency Auditor",
    description="自動化 Python 套件資安稽核工具",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 靜態檔案
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 註冊路由
app.include_router(audit.router)


@app.get("/", response_class=HTMLResponse)
async def index():
    """首頁 — 上傳介面"""
    template_path = Path(__file__).parent / "templates" / "upload.html"
    return HTMLResponse(content=template_path.read_text(encoding="utf-8"))


@app.on_event("startup")
async def startup_event():
    """啟動事件"""
    settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Python Dependency Auditor V1.0 已啟動")
    logger.info("翻譯模式: %s", settings.TRANSLATION_MODE)
    logger.info("報告目錄: %s", settings.REPORTS_DIR)
