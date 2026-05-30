# AGENTS.md — Python 依賴審計工具

本文件補充 [Rules.md](./Rules.md)，兩者皆須遵守。

## 開發指令

```bash
uvicorn app.main:app --reload                    # 開發伺服器
pytest tests/ -v                                  # 全部測試
pytest tests/<file>.py -v                         # 單檔測試
pytest <file>::<test_name> -v                     # 單一測試
coverage run -m pytest tests/ && coverage report  # 涵蓋率（threshold: 70%）
ruff check . --fix                                # lint
ruff format .                                     # format（雙引號, line-length=120）
pre-commit run --all-files                        # pre-commit
python e2e_test.py                                # e2e 測試
docker compose up -d --build                      # 正式部署
```

## 測試慣例

- 使用 `@pytest.mark.asyncio`，`asyncio_mode = "auto"`
- HTTP mock 優先使用 `unittest.mock.patch` context manager，而非 pytest mocks
- `conftest.py` 的 autouse fixture `mock_reports_dir` 會自動覆蓋 `settings.REPORTS_DIR` 為 `tmp_path`，勿自行覆寫

## 架構規範

- DI 鏈固定為：`httpx.AsyncClient` → `OSVClient` / `PyPIClient` → `TranslatorService(LLMClient)` → `AuditService(osv, pypi, translator)`
- Service 在 router 層每次請求實例化，不掛在 app.state
- TranslatorService 必須接收 `LLMClient` 而非直接操作 API

## 禁止事項

- 勿在 async route handler 中直接呼叫 blocking 操作（`subprocess.run`、`diskcache`、`Path.read_text`），應使用 `anyio.to_thread.run_sync`
- `subprocess.run` 必須加上 `timeout` 參數
- 勿假設平台為 `win_amd64` — 從 wheel 檔名解析平台時須支援多平台
- 使用者的輸入在 HTML 報表中必須跳脫（escape），防止 XSS
