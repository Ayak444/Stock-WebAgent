# Agent Handoff: 大戶增持 × 量能放大監控

## Work definition

- Objective: 每日以三期 TDCC 大戶持股趨勢與近期成交量放大條件監控指定台股，透過可稽核、冪等且預設安全的流程產生 Discord 通知。
- In scope: 嚴格環境設定、純計算、行情路由、TDCC 歷史聚合、20:30 排程與啟動補跑、Supabase migration/repository、dry-run、Discord、安全狀態 API、Render 與人工操作文件。
- Out of scope: 自動交易、投資推薦、盤中即時訊號、前端設定介面、付費排程服務。
- Assumptions: TDCC 分級 12–15 代表 400,001 股以上；行情量採未還原日線的成交量；部署維持單一 Uvicorn worker。

## Acceptance criteria

- [x] AC-01: `HOLDER_ALERT_TICKERS` 僅接受 4–6 位數及 `.TW`/`.TWO`，去重後最多 20 檔；預設停用且 dry-run。
- [x] AC-02: 以最近三個 distinct TDCC 日期加總分級 12–15，比例必須嚴格遞增且首尾至少增加 0.50 個百分點。
- [x] AC-03: 量能倍數採最新正成交量除以前 20 個正成交量中位數，至少需要 15 筆，門檻含 1.50 倍。
- [x] AC-04: 集保資料不得超過 14 日；行情日與集保日差必須介於 0–7 日。
- [x] AC-05: 每日 20:30 Asia/Taipei 執行，20:30 後啟動時依 state 補跑，並以程序內鎖及資料庫 lease lock 避免重入。
- [x] AC-06: migration 冪等建立 snapshots、events、state 三表；snapshot 使用 `(ticker, holder_date)` 主鍵，event key 唯一，三表啟用 RLS 且不建立 anon policy。
- [x] AC-07: 資料庫設定、鎖、snapshot 或 event 狀態寫入失敗時 fail closed，不發送通知或洩漏供應商錯誤。
- [x] AC-08: event key 為 `v1:{ticker}:{holder_date}`；sent 後同檔 7 日冷卻，failed/遺留 claimed 至少 6 小時後才可重試。
- [x] AC-09: dry-run 不 claim/建立 event、不送 Discord，只 upsert snapshot/state 並回報 `would_alert`。
- [x] AC-10: Discord 訊息包含三期比例、增幅、量能、route、日期、event ID、非投資建議；禁止 mentions，連線/讀取 timeout 合計 10 秒。
- [x] AC-11: 單檔上游或處理失敗不阻斷其他股票，使用穩定 reason code，整體回報 partial 且不含例外內容。
- [x] AC-12: `/api/holder-alerts/status` 與 `/health` 摘要只讀程序記憶體，不連網、不查 DB、不回傳 webhook 或 secret。
- [x] AC-13: `.env.example`、`render.yaml` 與 `MANUAL_SETUP.md` 記錄預設值、migration、dry-run 驗收、啟用順序及 Render Free 休眠限制。
- [x] AC-14: 沿用 MarketRouter、TDCC cache、DiscordNotifier 與 task queue；既有 notifier/endpoints 相容，不新增依賴。
- [x] AC-15: 邊界、時效、冪等、冷卻、重試、partial、秘密安全、migration 與完整 regression 具自動化證據，等待 Tester/Reviewer 獨立 gate。

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product | Product Agent | Complete | 2026-09-21 | 2026-09-21 | AC-01..AC-15 已交付 |
| Developer | Developer Agent | Complete | 2026-09-21 | 2026-09-21 | 等待獨立 Tester 驗證 |
| Tester | Tester Agent | Not started |  |  | 必須重算 source-state ID |
| Reviewer | Reviewer Agent | Not started |  |  | 僅審查 Tester 通過的相同狀態 |

## Revision identity

- Baseline commit: `c73f4e60635f303c7c3eaa7f21b953dbec999cc6`
- Developer HEAD: 未提交；完整 canonical source identity 由 Developer 停止寫入後提供。
- Tested source-state ID: Pending independent Tester recomputation.
- Reviewed source-state ID: Pending independent Reviewer recomputation.
- Shared-workspace writer: Developer Agent（本階段唯一寫入者）

## Developer handoff

### Changed files

| File | Purpose |
| --- | --- |
| `holder_volume_alerts.py` | config、TDCC/量能純計算、排程執行、冪等與 runtime status |
| `migrations/002_holder_volume_alerts.sql` | 三表、RLS、跨程序鎖與原子 event claim |
| `database.py` | fail-closed holder alert repository methods |
| `notifier.py` | 可注入 transport、timeout、mentions 禁用與監控訊息 |
| `market_insights.py` | 共用 raw TDCC TTL cache |
| `task_queue.py` | 向後相容的明確時區每日排程 |
| `main.py` | 20:30 排程、啟動補跑、status API 與 health 摘要 |
| `.env.example`, `render.yaml`, `MANUAL_SETUP.md` | 安全預設值與人工部署流程 |
| `tests/test_holder_volume_alerts.py` | feature、integration、security 與 migration 靜態測試 |

### Commands and results

| Command | Exit code | Result |
| --- | ---: | --- |
| `python -m scripts.offline_unittest discover -s tests -p test_holder_volume_alerts.py -v` | 0 | 25 feature tests passed |
| `python scripts/quality_gate.py` | 0 | 31 files compiled; 75 tests passed; 1 expected platform skip |
| migration structural Python assertion | 0 | 3 tables, 3 RLS, 3 PL/pgSQL bodies, 2 atomic row-count claims, service-role grant, no policy |
| `git diff --check` | 0 | Pass；僅 Git LF→CRLF working-copy 提示 |
| JavaScript check | N/A | 未修改前端或 JavaScript |

## Test evidence

| Acceptance criteria | Evidence | Developer result |
| --- | --- | --- |
| AC-01 | config default/validation/dedup/max tests | Pass |
| AC-02–04 | holder levels/distinct dates、0.50/1.50/15 筆邊界、stale/mismatch tests | Pass |
| AC-05 | Taipei 20:30 boundary、persisted catch-up test、main static integration | Pass |
| AC-06 | migration 三表/PK/RLS/atomic claim static test | Pass |
| AC-07–09 | DB fail-closed、dry-run、dedupe/cooldown/retry tests | Pass |
| AC-10 | injected notifier payload/timeout/mentions/error secrecy、204/302/429 與 redirect retry integration tests | Pass |
| AC-11 | two-ticker isolation and stable reason test | Pass |
| AC-12 | memory-only status/health test and static endpoint check | Pass |
| AC-13–14 | deployment docs/config static check and full regression | Pass |
| AC-15 | offline quality gate | Pass：75 tests；等待 Tester 獨立重跑 |

## Manual operations

1. 備份 Supabase，執行 `migrations/002_holder_volume_alerts.sql`，確認三表、RLS 與函式。
2. 在 Render 設定 `HOLDER_ALERT_TICKERS`，以 `HOLDER_ALERT_ENABLED=true`、`HOLDER_ALERT_DRY_RUN=true` 完成至少一輪驗收。
3. 建立專用 Discord Webhook，只把 URL 存入 Render `DISCORD_WEBHOOK_URL`。
4. 確認 dry-run 沒有 event/Discord 後，才把 `HOLDER_ALERT_DRY_RUN=false` 重新部署。
5. Render Free 休眠不保證 20:30 執行；若需準時，改用不休眠方案或外部喚醒。

## Risks and limitations

- TDCC 通常為週資料，通知時點受官方更新時間影響。
- Render Free 休眠期間排程不執行，僅能在程序再次啟動時補跑。
- Discord 傳送成功後、event `sent` 寫回前若資料庫故障，無法取得分散式交易的 exactly-once 保證；claimed 需等待六小時後才可恢復。
- 行情 loader 最多四檔並行；同步 DB、TDCC 與 Discord I/O 會移至 worker thread，避免阻塞 FastAPI event loop。

## Review evidence

- Correctness: Pending Reviewer.
- Security: Pending Reviewer.
- Performance: Pending Reviewer.
- Maintainability: Pending Reviewer.
- Blocking-issue count: Pending Reviewer.

## Gate status

- [x] Acceptance gate: Developer evidence涵蓋 AC-01..AC-15；等待 Tester 確認。
- [x] Test gate: Developer 完整 regression 通過；等待 Tester 對 canonical source state 獨立重跑。
- [ ] Review gate: Reviewer blocking count pending.
- [x] 人工 migration、Render、Discord 與 Free 休眠限制已記錄。

### Tester blocker rework

- Discord transport 只有明確 `200 <= status_code < 300` 才回傳成功；302、429 及無效 response 均回傳失敗，日誌只包含安全狀態分類，不包含 webhook URL 或 response body。
- 302 不會將 event 標為 sent，也不會啟動七日 cooldown；event 保持 failed，滿六小時後才可重新 claim。
- 精準覆蓋 204=True、302=False、429=False，以及 302 → 5:59 deferred → 6:00 retry → 204 sent 的 monitor 整合路徑。
- 非 bool transport 僅讀取 `status_code`；型別必須精確為 `int`（排除 `bool`），且完全不讀取或呼叫 `raise_for_status`、`text`、`content`、`url`、`reason`。
- Reviewer redirect blocker：transport 明確傳入 `allow_redirects=False`，因此 Requests 不會將原始 302/307/308 跟隨到另一個 URL 或重新 POST JSON；本地 `requests.Session` + `BaseAdapter` 測試以 307→假 204 重現，驗證只發出原始一次 POST、回傳失敗並維持安全日誌。
