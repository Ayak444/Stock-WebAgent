# 股金往來｜台股分析儀表板

整合台股日線、技術分析、策略回測、市場洞察與條件式 AI 分析的網頁專案。資料與模型輸出供研究與展示使用，不構成投資建議。

**[開啟線上網站](https://taiwan-stock-bot-urn9.onrender.com/)** · [查看 API 文件](https://taiwan-stock-bot-urn9.onrender.com/docs) · [GitHub 原始碼](https://github.com/Ayak444/Stock-WebAgent)

> 線上服務部署於 Render Free；閒置後首次開啟可能需要等待服務喚醒。

## 可以做什麼

| 功能 | 內容 |
| --- | --- |
| 個股技術分析與 K 線 | 檢視台股日線、技術指標與分析結果；行情以 Yahoo 為主要來源，上市股票可由 TWSE 備援。顯示資料日期與來源，並非即時報價。 |
| 策略回測 | 以 MA20／RSI 策略模擬交易，計入可調整的手續費、最低手續費與賣出交易稅，並與相同期間的買入持有結果比較。 |
| 市場洞察 | 查看個股快照、產業單日等權漲幅、集保「400 張以上」持股級距占比，以及最近 72 小時財經 RSS 提及較多的五檔股票。級距資料不能識別實際持有人；新聞提及數不代表搜尋熱度或成交量。 |
| 投資組合與風險 | 管理模擬投資組合、交易紀錄，並進行資產壓力測試。 |
| 新聞與選股 | 查看新聞摘要、市場情緒與關聯選股資訊；需要 AI 的分析依賴有效的 Groq API Key，服務不可用時部分流程會退回非 AI 結果或顯示狀態。 |
| 每帳號 Discord 成交量通知 | 使用者登入後各自設定股票清單與 Discord Webhook；開啟監控且資料與排程條件符合時，收盤後偵測成交量放大並通知。Webhook 在伺服器加密保存。 |
| 全域大戶增持 × 量能監控 | 可由管理者設定監控股票，在集保持股級距與成交量條件符合時發送 Discord 通知；此功能與每帳號通知分開設定，預設關閉且處於 dry-run。 |

回測目前**不含股利與實際滑價**，尚無 Sharpe、Sortino、CAGR、walk-forward 或樣本外驗證；結果不能代表未來績效。排程通知在 Render Free 休眠期間可能錯過執行，無法保證準時送達。

## 本機啟動

建議 Python 3.11。先在專案根目錄建立並啟用虛擬環境（Windows PowerShell：`.\.venv\Scripts\Activate.ps1`；macOS／Linux：`source .venv/bin/activate`），再參照 [`.env.example`](.env.example) 建立本機 `.env`：

```bash
python -m venv .venv
# 啟用 .venv 後執行以下兩行
python -m pip install -r requirements.txt
uvicorn main:app --reload
```

開啟 `http://127.0.0.1:8000/`。`.env` 與任何 API Key、密碼或 Webhook 都不要提交到 Git。未設定 Groq 時，快速技術分析仍可使用；帳號與需要儲存資料的功能則須完成 Supabase 設定。

## 部署與設定

根目錄的 [`render.yaml`](render.yaml) 定義 Render Web Service，啟動根目錄 FastAPI 應用。請在 Render Environment 私下設定：

| 變數 | 用途 |
| --- | --- |
| `SUPABASE_URL`、`SUPABASE_KEY` | 同一 Supabase 專案的 URL 與**後端專用** secret／service-role key；不可放入前端。 |
| `AUTH_SESSION_SECRET` | 登入 session 簽署用、至少 32 字元的隨機字串。 |
| `ALERT_WEBHOOK_ENCRYPTION_KEY` | Fernet 金鑰，用來加密每帳號的 Discord Webhook；更換後既有 Webhook 需重新輸入。 |
| `VOLUME_ALERT_ENABLED` | 設為 `true` 才啟用每帳號成交量通知；預設關閉。 |
| `GROQ_API_KEY` | 使用 Groq AI 分析時才需要。 |

`TZ=Asia/Taipei`、`PYTHON_VERSION=3.11.11` 與其他選用設定請參照 [`.env.example`](.env.example) 及 [`render.yaml`](render.yaml)。個人通知的股票與 Webhook 在**登入後的網站設定頁**填寫，不使用舊的全域 `VOLUME_ALERT_TICKERS`。通知還需要在 Supabase 執行 [`migrations/003_account_volume_alerts.sql`](migrations/003_account_volume_alerts.sql)；帳號資料結構參照 [`migrations/001_auth_store.sql`](migrations/001_auth_store.sql)。執行遷移前請先備份並比對既有資料庫，勿重跑含 `DROP TABLE` 的舊建表 SQL。

選用的**全域大戶監控**另需 [`migrations/002_holder_volume_alerts.sql`](migrations/002_holder_volume_alerts.sql)、`HOLDER_ALERT_TICKERS` 與管理者的 `DISCORD_WEBHOOK_URL`。`HOLDER_ALERT_ENABLED` 預設為 `false`、`HOLDER_ALERT_DRY_RUN` 預設為 `true`；請先驗證 dry-run，再視需求開啟發送。這些全域變數不會取代個人通知設定。

更多操作與排錯細節見 [`MANUAL_SETUP.md`](MANUAL_SETUP.md)。完成部署後，可檢查網站的 [`/health`](https://taiwan-stock-bot-urn9.onrender.com/health) 與 [`/health/auth`](https://taiwan-stock-bot-urn9.onrender.com/health/auth)。若登入查詢失敗，請確認 Supabase Data API 對後端角色開放、同專案金鑰及 `users` 表的後端權限；不要把 secret key 改成公開金鑰，或授權瀏覽器直接讀取使用者表。

## 驗證

專案的離線品質檢查不需要正式金鑰或網路：

```bash
python scripts/quality_gate.py
```
