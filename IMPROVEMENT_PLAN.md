# 🛠️ Python Dependency Auditor 改善計畫

本文件旨在根據資安稽核、品質檢查與架構評估的結果，制定系統性的優化路徑。目標在於消除安全漏洞、解決效能阻塞並提升系統的可維護性。

## 📌 優先級定義
- **P0 (Critical)**: 必須立即修復的安全漏洞或會導致系統崩潰的重大缺陷。
- **P1 (Important)**: 影響使用者體驗、系統擴展性或穩定性的重要優化。
- **P2 (Optimization)**: 提升程式碼品質、可維護性或增加測試覆蓋率的優化。

---

## 🔴 P0: 安全性與穩定性 (Security & Stability)

### 1. 修復 HTML 報告 XSS 漏洞
- **問題**: `source_file`, `python_version`, `platform` 等使用者輸入直接渲染至 HTML 報告，可導致 XSS 攻擊。
- **對策**: 
    - 導入 `markupsafe` 或使用 `jinja2` 的自動轉義功能。
    - 確保所有渲染至報告的變數均經過 HTML Escaping 處理。

### 2. 實作子進程超時限制 (Subprocess Timeout)
- **問題**: `uv pip compile` 與 `pip install --report` 缺乏超時設定，可能導致 DoS 攻擊。
- **對策**: 
    - 為 `app/services/dependency_resolver.py` 中所有 `subprocess.run` 呼叫加入 `timeout` 參數 (建議 60-120s)。
    - 捕捉 `subprocess.TimeoutExpired` 並回傳適當的錯誤訊息。

### 3. 解決事件迴圈阻塞 (Event Loop Blocking)
- **問題**: 在 `async` 路由中直接呼叫同步阻塞函數 (`subprocess.run`, `diskcache`, `Path.read_text`)，導致單一請求阻塞全服。
- **對策**: 
    - 使用 `anyio.to_thread.run_sync` 將阻塞呼叫移至線程池執行。
    - 評估將 `diskcache` 替換為非同步快取方案或封裝於線程池中。

---

## 🟡 P1: 架構與效能 (Architecture & Performance)

### 1. 導入非同步任務調度 (Job Orchestration)
- **問題**: 稽核流程採請求-響應模式，大型專案易導致 HTTP Timeout。
- **對策**: 
    - 實作 `POST /api/audit` $\to$ 回傳 `job_id` $\to$ 背景執行 $\to$ `GET /api/audit/status/{job_id}` 查詢結果。
    - 使用 `FastAPI.BackgroundTasks` 或整合 Celery/Redis。

### 2. 平台參數化 (Platform Parameterization)
- **問題**: `PyPIClient` 中硬編碼 `win_amd64`，限制了跨平台支持的靈活性。
- **對策**: 
    - 將 `win_amd64` 改為從請求參數或設定檔動態傳入。
    - 優化 `_extract_download_url` 邏輯，使其根據目標平台動態匹配 Wheel 標籤。

### 3. 增加解析階段快取
- **問題**: 每次請求均重新執行 `uv` 解析，對重複內容造成資源浪費。
- **對策**: 
    - 對 `(requirements_content, python_version, platform)` 進行雜湊，將解析結果快取至 `diskcache`。

---

## 🔵 P2: 維護性與品質 (Maintainability & Quality)

### 1. 重構 `AuditService.run_audit_flow`
- **問題**: 方法過長 (150+ 行)，違反單一職責原則。
- **對策**: 
    - 將流程拆分為 `_resolve_deps()`, `_fetch_metadata()`, `_scan_vulns()`, `_generate_reports()` 等私有方法。

### 2. 實作 API 頻率限制 (Rate Limiting)
- **問題**: 缺乏對 `/api/audit` 的限制，易導致 LLM API 成本激增或伺服器過載。
- **對策**: 
    - 導入 `slowapi` 或在 Nginx 層設定 `limit_req`。

### 3. 擴充整合測試 (E2E Testing)
- **問題**: 目前以單元測試為主，缺乏完整流水線的驗證。
- **對策**: 
    - 建立 E2E 測試套件，模擬從檔案上傳到 PDF 生成的完整過程。
    - 加入針對異常 `requirements.txt` 格式的邊界測試。

---

## ✅ 驗證基準 (Success Criteria)
- [ ] **安全**: 使用 `<script>` 檔名上傳，確認 HTML 報告中該內容被轉義，無 JS 執行。
- [ ] **穩定**: 執行一個長時間解析的請求時，另一個簡單請求（如 `/`）仍能立即回應。
- [ ] **效能**: 同一內容第二次請求時，解析時間從秒級降至毫秒級 (快取生效)。
- [ ] **功能**: 能成功為 Linux 平台獲取正確的 `.whl` 下載連結。
