# 🔒 Python Dependency Auditor V1.0

自動化 Python 套件資安稽核工具。透過 Docker 容器化技術，解析 `requirements.txt`，自動採集套件的授權資訊、漏洞狀況、原始碼溯源與離線下載路徑，產出繁體中文 Markdown 稽核報告。

## ✨ 功能特色

- 📦 **套件解析** — 自動偵測 UTF-8/UTF-16 編碼，解析 requirements.txt
- ⚖️ **授權掃描** — 透過 PyPI API 取得 License，比對原始碼倉庫
- 🛡️ **漏洞稽核** — 串接 OSV + pip-audit 雙重掃描，產出 Snyk 連結
- 📝 **中文翻譯** — 內建 100+ 套件字典，可選用 OpenAI/Gemini AI 翻譯
- 📊 **Markdown 報告** — Jinja2 模板引擎產出專業稽核報告
- 🐳 **Docker 部署** — Nginx 反向代理 + FastAPI 後端

## 🚀 快速開始

### 1. 環境設定

```bash
# 複製並編輯環境變數
cp .env.example .env
# 編輯 .env (設定翻譯模式與 API Key)
```

### 2. 啟動服務

```bash
docker compose up -d --build
```

### 3. 使用

瀏覽器開啟 http://localhost，上傳 `requirements.txt` 即可。

或使用 API：
```bash
curl -X POST -F "file=@requirements.txt" http://localhost/api/audit
```

## ⚙️ 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `TRANSLATION_MODE` | `builtin` | 翻譯模式: `builtin` / `openai` / `gemini` |
| `OPENAI_API_KEY` | - | OpenAI API 金鑰 (選用) |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI 模型 |
| `GEMINI_API_KEY` | - | Gemini API 金鑰 (選用) |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini 模型 |

## 📁 專案結構

```
├── Dockerfile
├── docker-compose.yml
├── nginx/nginx.conf
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py             # 設定管理
│   ├── routers/audit.py      # API 路由
│   ├── services/
│   │   ├── parser.py         # 檔案解析
│   │   ├── pypi_client.py    # PyPI API
│   │   ├── osv_client.py     # OSV 漏洞查詢
│   │   ├── pip_audit_runner.py
│   │   ├── llm_client.py     # LLM 客戶端
│   │   ├── translator.py     # 翻譯模組
│   │   └── report_generator.py
│   ├── templates/
│   └── static/
└── tests/
```

## 🔌 API 端點

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/` | 上傳介面 |
| `POST` | `/api/audit` | 執行稽核 |
| `GET` | `/api/reports` | 列出報告 |
| `GET` | `/api/reports/{filename}` | 下載報告 |

## 📄 License

MIT
