# 🔒 Python Dependency Auditor V1.0

![Aesthetics](https://img.shields.io/badge/UI-Professional_Light-blue?style=for-the-badge)
![Performance](https://img.shields.io/badge/Performance-Async_IO_&_Gather-green?style=for-the-badge)
![PDF](https://img.shields.io/badge/Report-PDF_&_Markdown-orange?style=for-the-badge)
![LLM](https://img.shields.io/badge/AI-Gemma_/_GPT-purple?style=for-the-badge)

自動化 Python 套件資安稽核工具。專為企業環境設計，提供專業的淺色 UI 介面，解析 `requirements.txt` 後自動執行漏洞掃描、授權比對，並產出精美的繁體中文 Markdown 與 PDF 稽核報告。

## ✨ 功能特色

- 🎨 **專業商務 UI** — 全新設計的專業淺色主題 (Light Theme)，介面簡潔且美觀。
- ⚡ **全非同步架構** — 基於 FastAPI **Lifespan** 與 **httpx** 的原生非同步 IO，極大化並行效能。
- 🚀 **高效能異步快取** — 整合 **async-lru** 機制，針對頻繁的 API 查詢提供非同步執行緒安全的快取。
- 📑 **多格式報告輸出** — 同時支援 **Markdown** 預覽與 **PDF** 匯出（內建 Noto Sans CJK TC 字型，已優化大檔案排版）。
- 🛡️ **深度安全稽核** — 整合 **OSV** 與 **pip-audit** 雙重掃描，並透過邏輯解耦的 **AuditService** 統一管理。
- 🧠 **健壯的 AI 翻譯** — 支援 **GPT-4o** / **Gemini-2.0** 批次翻譯，具備強大的 JSON 異常解析 Fallback 機制。
- 🔒 **安全性增強** — 支援 **CORS 來源限制** (ALLOWED_ORIGINS) 與路徑穿越 (Path Traversal) 防護。
- 🐳 **Docker 全端部署** — 整合 Nginx 反向代理，支援 600s 長時間連線處理。

## 🚀 快速開始

### 1. 環境設定

```bash
# 複製並編輯環境變數
cp .env.example .env
```

在 `.env` 中設定你的 API Key 與翻譯模式：
```ini
TRANSLATION_MODE=gemini  # 或 builtin
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemma-4-31b-it
```

### 2. 啟動服務

```bash
docker compose up -d --build
```

### 3. 使用方式

1. 瀏覽器開啟 `http://localhost`。
2. 選擇目標 **Python 版本** (用於篩選安裝檔)。
3. 上傳 `requirements.txt`。
4. 點擊 **[執行稽核]**，稍待片刻即可預覽 Markdown 或下載 PDF。

## ⚙️ 環境變數說明

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `TRANSLATION_MODE` | `builtin` | 翻譯模式: `builtin` / `openai` / `gemini` |
| `ALLOWED_ORIGINS` | `["*"]` | CORS 允許來源 (JSON 陣列格式) |
| `GEMINI_API_KEY` | - | Gemini API 金鑰 |
| `OPENAI_API_KEY` | - | OpenAI API 金鑰 |
| `REQUEST_TIMEOUT` | `30` | 外部 API 請求超時時間 (秒) |

## 📁 專案結構

```
├── Dockerfile              # 多階段構建與字型安裝
├── docker-compose.yml       # 容器編排
├── nginx/
│   └── nginx.conf          # 反向代理與 600s 超時配置
├── app/
│   ├── main.py             # FastAPI 入口 (Lifespan & Middleware)
│   ├── static/             # 專業淺色主題 CSS 與互動 JS
│   ├── templates/          # HTML 介面與 Jinja2 模板
│   ├── services/
│   │   ├── audit_service.py # 核心稽核流程封裝 (解耦層)
│   │   ├── llm_client.py    # OpenAI/Gemini 非同步實作
│   │   ├── osv_client.py    # OSV API 與 async-lru 快取
│   │   ├── pypi_client.py   # PyPI 資訊查詢與平台篩選
│   │   └── ...              # 其他輔助模組
│   └── reports/            # 報告產出目錄 (對應 Volume)
```

## 🔌 API 端點摘要

- `GET /`: 網頁上傳介面
- `POST /api/audit`: 執行非同步稽核 (支援超時處理與並行優化)
- `GET /api/reports`: 取得歷史稽核紀錄
- `DELETE /api/reports`: 清空所有歷史報告

---
## 📄 License
MIT © 2026
