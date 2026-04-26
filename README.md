# 🔒 Python Dependency Auditor V1.0

![Aesthetics](https://img.shields.io/badge/UI-Professional_Light-blue?style=for-the-badge)
![Performance](https://img.shields.io/badge/Performance-Parallel_&_Cache-green?style=for-the-badge)
![PDF](https://img.shields.io/badge/Report-PDF_&_Markdown-orange?style=for-the-badge)
![LLM](https://img.shields.io/badge/AI-Gemma_4_31B-purple?style=for-the-badge)

自動化 Python 套件資安稽核工具。專為企業環境設計，提供專業的淺色 UI 介面，解析 `requirements.txt` 後自動執行漏洞掃描、授權比對，並產出精美的繁體中文 Markdown 與 PDF 稽核報告。

## ✨ 功能特色

- 🎨 **專業商務 UI** — 全新設計的專業淺色主題 (Light Theme)，介面簡潔且美觀。
- ⚡ **極速並行處理** — 實現 PyPI 資訊與 OSV 漏洞的 **並行查詢 (Parallel Fetching)**，大幅縮短稽核時間。
- 🚀 **高效能快取** — 內建 **LRU Cache 機制**，避免對相同套件版本進行重複的網路請求。
- 📑 **多格式報告輸出** — 同時支援 **Markdown** 預覽與 **PDF** 匯出（內建 Noto Sans CJK TC 字型，已優化大檔案排版）。
- 🛡️ **深度安全稽核** — 整合 **OSV** 與 **pip-audit** 雙重掃描，提供直連 Snyk 的漏洞詳情。
- 🧠 **強大 AI 翻譯** — 支援 **Gemma-4 31B** 模型與 **Thinking (High)** 推理模式，精準翻譯套件功能摘要。
- 📦 **離線部署支援** — 自動篩選符合特定 Python 版本的 Windows AMD64 安裝檔下載連結。
- 📜 **歷史紀錄管理** — 內建歷史報告清單，支援一鍵檢視、下載與清空紀錄。
- 🐳 **Docker 全端部署** — 整合 Nginx 反向代理，提升穩定性並支援 600s 長時間連線處理。

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
| `GEMINI_API_KEY` | - | Gemini/Gemma API 金鑰 |
| `GEMINI_MODEL` | `gemma-4-31b-it` | 使用的高階 AI 模型 |
| `TZ` | `Asia/Taipei` | 系統時區設定 (預設台北) |
| `REQUEST_TIMEOUT` | `30` | 外部 API 請求超時時間 |

## 📁 專案結構

```
├── Dockerfile              # 多階段構建與字型安裝
├── docker-compose.yml       # 容器編排
├── nginx/
│   └── nginx.conf          # 反向代理與 600s 超時配置
├── app/
│   ├── main.py             # FastAPI 入口
│   ├── static/             # 專業淺色主題 CSS 與互動 JS
│   ├── templates/          # HTML 介面與 Jinja2 模板
│   ├── services/
│   │   ├── llm_client.py    # Gemma-4 Thinking 實作
│   │   ├── translator.py    # 翻譯排隊與 Fallback 機制
│   │   ├── report_generator.py # WeasyPrint PDF 渲染引擎
│   │   └── ...              # 其他稽核邏輯
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
