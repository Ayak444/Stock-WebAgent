# 多路由第一版：部署與手工事項

程式已接入：日線 Yahoo 主路由、上市台股 TWSE 備援、5 分鐘有來源快取、資料品質檢查、quick/deep 分流、Groq 故障隔離及後端 route 日誌。此文件不代表正式環境已部署。

## 你需要手工完成

1. **Groq**：撤銷曾放入版本控制或失效的 Key，產生新 Key；到 Render → 服務 → Environment 更新 `GROQ_API_KEY`，並設定 `GROQ_MODEL=openai/gpt-oss-120b`。不要把 Key 貼進對話、前端或 Git。若仍設有舊 `MAIAGENT_API_KEY`，移除以免誤用。更新後重新部署／重啟服務。
2. **Supabase**：在專案設定確認 `SUPABASE_URL` 及後端專用 `SUPABASE_KEY`（以 `.env.example` 實際欄位為準），同步到 Render；曾提交的 secret key 請輪替。前端不可使用 secret/service-role Key。
3. **登入資料表**：先備份、比對 `migrations/001_auth_store.sql` 與現有資料庫，再於 Supabase SQL Editor 執行適用的遷移。若有重複 Email 或既有不同欄位，先處理資料衝突。這次路由本身不需要新資料表。
4. **Render**：部署此版本，維持一個 Uvicorn worker；基本環境變數為 `GROQ_API_KEY`、`SUPABASE_URL`、`SUPABASE_KEY`、`TZ=Asia/Taipei`、`PYTHON_VERSION=3.11.11`，監控功能另依下節設定 `DISCORD_WEBHOOK_URL` 與三個 `HOLDER_ALERT_*` 欄位。啟動命令 `uvicorn main:app --host 0.0.0.0 --port $PORT`。`PORT` 由 Render 自動提供，不要手動固定。快取與熔斷目前是單程序狀態，多副本需後續共用 Redis。
   專案同時包含 `.python-version`，避免 Render 在既有服務未同步 Blueprint 時改用預設 Python 3.14。若建置日誌仍顯示 3.14，刪除服務上覆寫的 `PYTHON_VERSION` 後重新加入 `3.11.11`，再 Clear build cache & deploy。
5. **驗收**：確認 `/health` 及 `/health/auth`；再用自己的帳號登入。若仍出現 Failed to fetch，檢查瀏覽器 Network 的 API 網址、HTTP 狀態及 Render 同時間日誌。不要分享密碼、Authorization header 或完整連線設定。
6. 測試快速分析不需 Groq；深度分析成功時 `ai_route.used=true`。失效 Key 下仍應得到技術結果，`ai_route.reason` 指出退回原因。Render 日誌搜尋 `route task=` 檢查選路。

## 大戶增持 × 量能放大監控

這項功能預設 `HOLDER_ALERT_ENABLED=false`、`HOLDER_ALERT_DRY_RUN=true`，不會自動發送。請依序完成：

1. 先備份 Supabase，再在 SQL Editor 執行 `migrations/002_holder_volume_alerts.sql`。確認三張表 `holder_alert_snapshots`、`holder_alert_events`、`holder_alert_state` 已建立、RLS 已啟用，而且沒有 anon/authenticated policy。遷移可重複執行。
2. Render Environment 新增 `HOLDER_ALERT_TICKERS`。格式只能是逗號分隔的 4–6 位數台股代號並帶市場尾碼，例如 `2330.TW,6488.TWO`；去重後最多 20 檔。
3. 保持 `HOLDER_ALERT_ENABLED=true`、`HOLDER_ALERT_DRY_RUN=true` 部署一次。20:30（Asia/Taipei）後啟動會補跑；檢查 `/api/holder-alerts/status`、`/health` 摘要與 Supabase snapshots/state。dry-run 不應出現 event，也不應送 Discord。
4. 在 Discord 建立專用 Webhook，將 URL 只填入 Render 的 `DISCORD_WEBHOOK_URL` secret 欄位。不要貼到原始碼、前端、SQL、日誌或對話。
5. dry-run 驗收成功後才把 `HOLDER_ALERT_DRY_RUN=false` 並重新部署。通知會停用 mentions，HTTP 最長等待 10 秒；已送事件同檔 7 日內冷卻，失敗事件至少 6 小時後才可重試。
6. Render Free 服務休眠時不會在 20:30 自行喚醒。若必須準時執行，需使用不休眠方案或由外部排程在 20:30 後呼叫一般健康網址喚醒服務；啟動補跑與資料庫鎖會避免同一程序重複執行，但仍應維持單一 Uvicorn worker。

狀態 API 與 `/health` 只讀取程序記憶體，不查詢外部服務，也不回傳 webhook、Supabase 設定或上游錯誤。任何資料庫寫入或事件 claim 失敗都會停止該檔通知；請先修復 migration/權限，再等下一輪執行。

## 操作與界線

`POST /analyze` 保持原 targets 格式，新增 `mode: "quick" | "deep"`，預設 quick。最多 20 檔；deep 只對前 5 檔使用 AI，其他回傳技術分析及 budget_limit。日線價格與指標使用同一資料日期，不冒充即時報價。

回應增加 `route`（source、asof、degraded、from_cache、failed_sources、price_basis）與 `ai_route`。K 線也回傳 route。上市 `.TW` 才能走 TWSE；`.TWO`、海外股目前只有 Yahoo。官方備援最多 13 個月，較長區間只能走 Yahoo。歷史資料是未還原 OHLCV，不適合直接視為含股息總報酬。

資料最新日超過 7 個日曆天或起始缺口超過 10 天即拒絕，長假、停牌、新上市可能顯示無資料；目前尚未接入交易日曆。不回傳過期快取。每個行情來源上限 20 秒。Groq 401/403 停用至 Key 更新或程序重啟；429 冷卻 30–300 秒；連續三次其他錯誤冷卻 60 秒。AI 輸出分數及格式驗證失敗會退回技術分析。

本版不是自我學習最佳化演算法，也未完成全站權限改造、上櫃官方備援或正式環境連線驗收。登入根因仍須以實際部署的 `/health/auth`、登入 HTTP 回應和服務日誌確認。

## 每帳號成交量放大 Discord 通知

**目前 `/health/auth` 回傳 HTTP 503、`auth_store=not_configured`；在 Render 完成 Supabase 設定前，登入及每帳號通知不可用。** 收盤日線成交量須達前 15–20 個交易日正成交量中位數的 `VOLUME_ALERT_MULTIPLIER` 倍（預設 1.5），行情最後日期必須是台北時間當天才會發送。每帳號最多 20 檔。

1. 在 Render 設定正確同一專案的 `SUPABASE_URL` 與後端 `SUPABASE_KEY`（service role / secret）。先確認 `/health/auth` 回傳 ready。
2. 備份 Supabase，在 SQL Editor 執行 `migrations/003_account_volume_alerts.sql`。確認兩張新表 RLS 已開啟，且 anon/authenticated 無權讀寫。
3. 在 Render 產生互相獨立的 `AUTH_SESSION_SECRET`（至少 32 字元）及 `ALERT_WEBHOOK_ENCRYPTION_KEY`（執行 `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 取得，**不要把輸出貼到對話或提交到 Git**）。遺失 Fernet 金鑰後，先前儲存的 Webhook 無法解密，需用戶重新輸入。
4. 設定 `VOLUME_ALERT_ENABLED=true`，視需求調整 `VOLUME_ALERT_MULTIPLIER`（大於 1），儲存並部署。`VOLUME_ALERT_TICKERS` 是舊全域設定，個人通知不再使用；`DISCORD_WEBHOOK_URL` 仍供其他全域任務使用，個人通知不會借用。
5. 每位使用者登入網站，在「成交量通知設定」填入 `2330.TW,6488.TWO` 之類的股票代號，以及自己頻道的官方 HTTPS Discord Webhook。網址在伺服器加密保存，讀取設定只顯示是否存在，不顯示原文。

每日 20:30 Asia/Taipei 執行，20:30–21:30 內啟動可補跑。同一帳號、股票、交易日的成功發送由資料庫去重；發送失敗可重試。Discord 已接受訊息、但資料庫尚未記錄成功時，仍可能因重試重送。Render Free 休眠可能錯過排程；需要準時通知應使用常駐服務或外部排程。
