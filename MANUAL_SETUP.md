# 多路由第一版：部署與手工事項

程式已接入：日線 Yahoo 主路由、上市台股 TWSE 備援、5 分鐘有來源快取、資料品質檢查、quick/deep 分流、Groq 故障隔離及後端 route 日誌。此文件不代表正式環境已部署。

## 你需要手工完成

1. **Groq**：撤銷曾放入版本控制或失效的 Key，產生新 Key；到 Render → 服務 → Environment 更新 `GROQ_API_KEY`。不要把 Key 貼進對話、前端或 Git。若仍設有舊 `MAIAGENT_API_KEY`，移除以免誤用。更新後重新部署／重啟服務。
2. **Supabase**：在專案設定確認 `SUPABASE_URL` 及後端專用 `SUPABASE_KEY`（以 `.env.example` 實際欄位為準），同步到 Render；曾提交的 secret key 請輪替。前端不可使用 secret/service-role Key。
3. **登入資料表**：先備份、比對 `migrations/001_auth_store.sql` 與現有資料庫，再於 Supabase SQL Editor 執行適用的遷移。若有重複 Email 或既有不同欄位，先處理資料衝突。這次路由本身不需要新資料表。
4. **Render**：部署此版本，維持一個 Uvicorn worker；啟動命令 `uvicorn main:app --host 0.0.0.0 --port $PORT`。快取與熔斷目前是單程序狀態，多副本需後續共用 Redis。
5. **驗收**：確認 `/health` 及 `/health/auth`；再用自己的帳號登入。若仍出現 Failed to fetch，檢查瀏覽器 Network 的 API 網址、HTTP 狀態及 Render 同時間日誌。不要分享密碼、Authorization header 或完整連線設定。
6. 測試快速分析不需 Groq；深度分析成功時 `ai_route.used=true`。失效 Key 下仍應得到技術結果，`ai_route.reason` 指出退回原因。Render 日誌搜尋 `route task=` 檢查選路。

## 操作與界線

`POST /analyze` 保持原 targets 格式，新增 `mode: "quick" | "deep"`，預設 quick。最多 20 檔；deep 只對前 5 檔使用 AI，其他回傳技術分析及 budget_limit。日線價格與指標使用同一資料日期，不冒充即時報價。

回應增加 `route`（source、asof、degraded、from_cache、failed_sources、price_basis）與 `ai_route`。K 線也回傳 route。上市 `.TW` 才能走 TWSE；`.TWO`、海外股目前只有 Yahoo。官方備援最多 13 個月，較長區間只能走 Yahoo。歷史資料是未還原 OHLCV，不適合直接視為含股息總報酬。

資料最新日超過 7 個日曆天或起始缺口超過 10 天即拒絕，長假、停牌、新上市可能顯示無資料；目前尚未接入交易日曆。不回傳過期快取。每個行情來源上限 20 秒。Groq 401/403 停用至 Key 更新或程序重啟；429 冷卻 30–300 秒；連續三次其他錯誤冷卻 60 秒。AI 輸出分數及格式驗證失敗會退回技術分析。

本版不是自我學習最佳化演算法，也未完成全站權限改造、上櫃官方備援或正式環境連線驗收。登入根因仍須以實際部署的 `/health/auth`、登入 HTTP 回應和服務日誌確認。
