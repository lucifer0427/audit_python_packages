"""稽核 API 路由
本模組定義所有與資安稽核相關的 API 端點，包括執行稽核、
列出報告、下載報告以及清理歷史紀錄。
"""

import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.services.audit_service import AuditService
from app.services.osv_client import OSVClient
from app.services.pypi_client import PyPIClient
from app.services.llm_client import create_llm_client
from app.services.translator import TranslatorService

logger = logging.getLogger(__name__)

# 定義 API 路由前綴為 /api，並將此路由歸類在 "audit" 標籤下
router = APIRouter(prefix="/api", tags=["audit"])


@router.post("/audit")
async def run_audit(
    request: Request,
    file: UploadFile,
    python_version: str = Form(default="")
):
    """
    上傳 requirements.txt 執行資安稽核
    
    流程：接收檔案 -> 呼叫 AuditService 執行完整流程 -> 回傳結果摘要
    """
    # 基本驗證：檢查是否有上傳檔案
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供檔案")

    # 讀取檔案內容 (非同步)，限制大小防止 OOM
    MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="檔案過大，上限為 1MB")
    if not content:
        raise HTTPException(status_code=400, detail="檔案內容為空")

    logger.info("收到稽核請求: %s (%d bytes)", file.filename, len(content))

    # 將複雜的業務邏輯委託給 AuditService 處理，保持路由層簡潔
    try:
        # --- 相依性注入 (Dependency Injection) ---
        # 從 app.state 中獲取共用的 HTTP 客戶端
        http_client = request.app.state.http_client
        
        # 實例化各個服務組件
        osv_client_inst = OSVClient(http_client)
        pypi_client_inst = PyPIClient(http_client)
        
        # 根據設定建立 LLM 客戶端
        llm_client_inst = create_llm_client(
            settings.TRANSLATION_MODE, 
            api_key=settings.GEMINI_API_KEY if settings.TRANSLATION_MODE == "gemini" else settings.OPENAI_API_KEY,
            model=settings.GEMINI_MODEL if settings.TRANSLATION_MODE == "gemini" else settings.OPENAI_MODEL
        )
        
        translator_inst = TranslatorService(llm_client_inst)
        
        # 注入依賴項並建立 AuditService 實例
        audit_service = AuditService(
            osv_client=osv_client_inst, 
            pypi_client=pypi_client_inst, 
            translator=translator_inst
        )
        
        result = await audit_service.run_audit_flow(content, file.filename, python_version)
        return JSONResponse(content=result)
    except ValueError as e:
        # 捕捉業務邏輯拋出的驗證錯誤 (如解析失敗)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 捕捉未預期的伺服器錯誤，並記錄詳細堆疊追蹤 (Stack Trace)
        logger.exception("稽核過程發生未預期錯誤: %s", e)
        raise HTTPException(status_code=500, detail="伺服器內部錯誤")


@router.get("/reports")
async def list_reports():
    """
    列出所有已生成的稽核報告
    掃描 reports 目錄下的所有 .md 檔案，並按時間倒序排列。
    """
    reports_dir = settings.REPORTS_DIR
    if not reports_dir.exists():
        return {"reports": []}

    # 取得所有 markdown 報告並進行排序 (排除 resolved_ 前綴的相依性檔案)
    files = sorted([f for f in reports_dir.glob("*.md") if not f.name.startswith("resolved_")], reverse=True)
    return {
        "reports": [
            {
                "filename": f.name,
                "size": f.stat().st_size,
                "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
                "download_url": f"/api/reports/{f.name}",
                "html_download_url": f"/api/reports/{f.with_suffix('.html').name}" if f.with_suffix('.html').exists() else None,
                # 檢查對應的 PDF 檔案是否存在，若存在則提供下載連結
                "pdf_download_url": f"/api/reports/{f.with_suffix('.pdf').name}" if f.with_suffix('.pdf').exists() else None,
                # 檢查對應的解析後 requirements.txt 是否存在
                "resolved_url": f"/api/reports/resolved_{f.name.replace('.md', '.txt')}" if (reports_dir / f"resolved_{f.name.replace('.md', '.txt')}").exists() else None,
            }
            for f in files
        ]
    }


@router.get("/reports/{filename}")
async def download_report(filename: str):
    """
    下載指定稽核報告 (Markdown 或 PDF)
    """
    # --- 安全性檢查：先防止路徑穿越攻擊 (Path Traversal) ---
    # 確保請求的檔案路徑確實位於 REPORTS_DIR 之下，防止使用 ../ 存取系統敏感檔案
    filepath = (settings.REPORTS_DIR / filename).resolve()
    if not filepath.is_relative_to(settings.REPORTS_DIR.resolve()):
        raise HTTPException(status_code=403, detail="禁止存取")

    # 檢查檔案是否存在且確實為檔案
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="報告不存在")

    # 根據副檔名設定適當的 MIME 類型
    media_type = "application/pdf" if filename.endswith(".pdf") else "text/html" if filename.endswith(".html") else "text/markdown"

    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type=media_type,
    )


@router.delete("/reports")
async def clear_reports():
    """
    清空所有歷史報告 (刪除 .md 與 .pdf 檔案)
    """
    reports_dir = settings.REPORTS_DIR
    if not reports_dir.exists():
        return {"message": "無報告可清空"}

    count = 0
    # 遍歷並刪除符合條件的報告檔案
    for f in reports_dir.glob("*"):
        if f.is_file() and f.suffix in [".md", ".pdf", ".html", ".txt"]:
            f.unlink()
            count += 1

    return {"message": f"已清空 {count} 個檔案"}
