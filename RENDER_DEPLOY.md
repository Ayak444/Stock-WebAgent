Render 部署說明

此文件說明如何在 Render 上部署 Stock-WebAgent，並安全地管理環境變數與 secrets。

1) Build / Start 設定
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

2) 必須在 Render Dashboard 的 Environment Variables / Secrets 中設定以下機密：
- MAIAGENT_API_KEY (Secret)
- MAIAGENT_CHATBOT_ID (Secret)
- MAIAGENT_WEBCHAT_ID (Secret)
- SUPABASE_URL (Secret)
- SUPABASE_KEY (Secret)
- REDIS_PASSWORD (Secret)
- POSTGRES_URL or POSTGRES_* components (Secret)
- EMAIL_PASSWORD (Secret)
- GEMINI_API_KEY (Secret, if used)
- MULTION_API_KEY (Secret, if used)
- NEWS_API_KEY (Secret, if used)
- SENTRY_DSN (Secret, optional)
- STOCK_ALERT_WEBHOOK (Secret, optional)

3) 非敏感設定（可直接在 envVars 設值）
- REDIS_HOST, REDIS_PORT, REDIS_DB
- DB_PATH (history.db)
- ENVIRONMENT (production)
- TZ (Asia/Taipei)
- LOG_LEVEL (INFO)
- LOG_FORMAT (json)
- API_WORKERS (4)
- PYTHON_VERSION (3.11)

4) 使用 Secret Files
Render 支援上傳 Secret 文件，會於執行時掛載到 `/etc/secrets/<filename>`。如果你要上傳整個 `.env` 檔（不推薦），可在程式啟動時用 dotenv 讀取該檔案：

```python
from dotenv import load_dotenv
load_dotenv('/etc/secrets/.env')
```

5) 關於 scikit-learn 安裝
已將 `requirements.txt` 中的 `scikit-learn` 版本修正為 `1.4.1.post1`，以避免 pip 找不到確切釋出的問題。

6) 驗證部署
- 部署後查看 build logs，確認 `pip install -r requirements.txt` 成功。
- 應用啟動後，檢查 `/health` 或 `http://<your-app>.onrender.com/health`。

如需我代為提交這些 envVars 到 `render.yaml`（已完成）或協助在 Render Dashboard 設定 secrets，我可以繼續操作或給你一步步指引。