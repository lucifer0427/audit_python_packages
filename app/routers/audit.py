"""稽核 API 路由
本模組定義所有與資安稽核相關的 API 端點，包括執行稽核、
列出報告、下載報告以及清理歷史紀錄。
"""

import logging
import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.services.audit_service import AuditService

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

    # 讀取檔案內容 (非同步)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="檔案內容為空")

    logger.info("收到稽核請求: %s (%d bytes)", file.filename, len(content))

    # 將複雜的業務邏輯委託給 AuditService 處理，保持路由層簡潔
    try:
        result = await AuditService.run_audit_flow(content, file.filename, python_version)
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

    # 取得所有 markdown 報告並進行排序
    files = sorted(reports_dir.glob("*.md"), reverse=True)
    return {
        "reports": [
            {
                "filename": f.name,
                "size": f.stat().st_size,
                "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
                "download_url": f"/api/reports/{f.name}",
                # 檢查對應的 PDF 檔案是否存在，若存在則提供下載連結
                "pdf_download_url": f"/api/reports/{f.with_suffix('.pdf').name}" if f.with_suffix('.pdf').exists() else None,
            }
            for f in files
        ]
    }


@router.get("/reports/{filename}")
async def download_report(filename: str):
    """
    下載指定稽核報告 (Markdown 或 PDF)
    """
    filepath = settings.REPORTS_DIR / filename

    # 檢查檔案是否存在且確實為檔案
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="報告不存在")

    # --- 安全性檢查：防止路徑穿越攻擊 (Path Traversal) ---
    # 確保請求的檔案路徑確實位於 REPORTS_DIR 之下，防止使用 ../ 存取系統敏感檔案
    try:
        filepath.resolve().relative_to(settings.REPORTS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="禁止存取")

    # 根據副檔名設定適當的 MIME 類型
    media_type = "application/pdf" if filename.endswith(".pdf") else "text/markdown"

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
        if f.is_file() and f.suffix in [".md", ".pdf"]:
            f.unlink()
            count += 1

    return {"message": f"已清空 {count} 個檔案"}
