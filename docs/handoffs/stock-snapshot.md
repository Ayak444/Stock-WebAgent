# Agent Handoff: 個股多訊號決策摘要

## Work definition

- Objective: 在市場洞察頁提供單一台股的價格、產業相對表現、集保持股與新聞關注度摘要。
- In scope: 新增 snapshot API、可解釋的純計算、partial/unavailable 降級、既有 ticker UI 升級與自動化測試。
- Out of scope: 投資推薦分數、交易訊號、資料庫變更、新環境變數與部署。
- Assumptions: 產業比較使用官方普通股分類；新聞關注度以現有 RSS 最近 72 小時內容為準。
- Dependencies: 既有 requests、FastAPI、NewsCrawler 與 MarketInsightsService。

## Acceptance criteria

- [x] AC-01: `GET /api/market-insights/stock-snapshot/{ticker}` 支援純代號、`.TW`、`.TWO`，無效格式回傳 400。
- [x] AC-02: identity、price、industry_context、ownership、news_attention 均提供 available、as_of、source、methodology。
- [x] AC-03: 價格漲跌幅採 `change / (close - change) * 100`，拒絕非有限值及無效前收。
- [x] AC-04: 產業區提供 rank、total、mean、median、advancers、company_count 與 stock_minus_industry。
- [x] AC-05: ETF 或無官方產業分類時保留其他區塊並回傳 partial。
- [x] AC-06: ownership 沿用 TDCC 分級 12–15、1–3 與總計 17。
- [x] AC-07: 新聞每篇至多計一次、限制 72 小時、保留跨來源資訊、處理歧義名稱，零提及仍為 available。
- [x] AC-08: 上游部分失敗回傳 partial 與穩定代碼；全部不可用回傳 503，回應不含上游例外。
- [x] AC-09: 重用 lazy service 與 TTL cache，每個 snapshot request 的各 loader 至多呼叫一次，既有 endpoints 相容。
- [x] AC-10: UI 一次呈現四個訊號區塊、partial 與三項限制；遠端文字 escape，新聞 URL 經 safeNewsUrl 且使用 noopener noreferrer，版面響應式。
- [x] AC-11: 不新增依賴、環境變數、資料庫或秘密；功能測試與既有 regression 通過。

## Stage ownership

| Stage | Owner | Status | Started | Completed | Notes |
| --- | --- | --- | --- | --- | --- |
| Product | Product Agent | Complete | 2026-09-20 | 2026-09-20 | AC-01..AC-11 已交付 |
| Developer | Developer Agent | Complete | 2026-09-20 | 2026-09-20 | 等待獨立 Tester 驗證 |
| Tester | Tester Agent | Not started |  |  | 必須重算 source-state ID |
| Reviewer | Reviewer Agent | Not started |  |  | 僅審查 Tester 通過的相同狀態 |

## Revision identity

- Baseline commit: `24c67d788023887ded0004a8eef0ff825d40fc52`
- Developer HEAD commit: `24c67d788023887ded0004a8eef0ff825d40fc52`
- Staged patch SHA-256: 由 Supervisor 在 Developer 停止寫入後記錄於 transition message。
- Unstaged patch SHA-256: 由 Supervisor 在 Developer 停止寫入後記錄於 transition message。
- Untracked files and content SHA-256 manifest: 由 Supervisor 在 Developer 停止寫入後記錄於 transition message。
- Tested source-state ID: Pending independent Tester recomputation.
- Reviewed source-state ID: Pending independent Reviewer recomputation.
- Shared-workspace writer: Developer Agent（本階段唯一寫入者）

Source identity hashes are kept in the immutable stage-transition message because embedding a hash of this untracked handoff inside itself would change that hash.

## Developer handoff

### Changed files

| File | Purpose |
| --- | --- |
| `market_insights.py` | ticker 驗證、純計算、共享 loaders/cache 與 snapshot 聚合 |
| `main.py` | 新增 snapshot API 與安全 400/503 回應 |
| `news_crawler.py` | RSS 先以明確 timeout HTTP 抓取，再解析回應 bytes |
| `static/index.html` | 四區摘要 UI、安全渲染、partial 與限制說明 |
| `tests/test_market_insights.py` | 公式、完整/部分/失敗、新聞與 cache 測試 |
| `tests/test_stock_snapshot_api.py` | 200/400/503 API contract 測試 |
| `docs/handoffs/stock-snapshot.md` | 本輪交接紀錄 |

### Commands and results

| Command | Exit code | Result |
| --- | ---: | --- |
| `python -m scripts.offline_unittest discover -s tests -p test_market_insights.py -v` | 0 | 24 tests passed |
| `python scripts/quality_gate.py` | 0 | 29 files compiled; 50 tests passed; 1 platform skip |
| Inline JavaScript extraction piped to `node --check` | 0 | Syntax valid |

### Known limitations

- 產業排行要求至少三個有效成分股，樣本不足時該區不可用。
- RSS 回傳空集合時無法區分正常零文章與來源異常，因此保守標示該來源不可用。
- 各官方資料來源的更新時間不同，snapshot 不代表同一成交時點。

## Test evidence

| Acceptance criterion | Test case or check | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 | ticker normalization + API 400 | Pass | `test_ticker_normalization_and_validation`, `test_invalid_ticker_is_sanitized_400` |
| AC-02 | complete section metadata | Pass | `test_complete_snapshot_has_explainable_sections` |
| AC-03 | price formula and invalid previous close | Pass | `test_price_formula_and_invalid_previous_close` |
| AC-04 | industry rank/statistics/delta | Pass | `test_complete_snapshot_has_explainable_sections` |
| AC-05 | ETF without industry | Pass | `test_etf_without_industry_is_partial` |
| AC-06 | TDCC aggregation regression | Pass | `test_aggregates_large_and_small_holder_buckets` |
| AC-07 | zero mentions, 72h, dedupe, ambiguity, RSS UTC boundary | Pass | `test_zero_news_mentions_is_available`, `test_news_window_and_ambiguous_names`, `test_rss_utc_timestamp_preserves_72_hour_news_boundary` |
| AC-08 | single-source partial, all fail, sanitized 503 | Pass | snapshot and API failure tests |
| AC-09 | one loader call and full regression | Pass | `test_cached_loader_runs_once`, complete snapshot mocks, quality gate |
| AC-10 | static UI review + Node syntax | Pass pending Tester UI smoke | escaped text, safe URL attributes, responsive grid present |
| AC-11 | dependency/config diff + quality gate | Pass | no dependency, environment, or schema files changed |

### Full regression

- Command: `python scripts/quality_gate.py`
- Exit code: 0
- Summary: 29 Python files compiled; 50 tests passed; Windows-only absence of sendmsg caused one expected skip.

### Rework evidence

- Selected-market availability now follows only the matched TWSE or TPEx company/daily loader.
- `.TW` and `.TWO` daily failures return `price_upstream_unavailable` and `industry_upstream_unavailable` even when the other market is healthy.
- `.TW` and `.TWO` company failures keep valid price data while returning `industry_upstream_unavailable`.
- A suffix-less ticker first resolves its matching market and then uses that market's loader health.
- Covered by `test_tw_suffix_uses_only_twse_loader_health`, `test_two_suffix_uses_only_tpex_loader_health`, and `test_suffixless_ticker_uses_matched_market_health`.
- Six independent snapshot resources run through a shared eight-worker executor with a 12-second total response deadline; individual JSON and RSS requests have shorter timeouts.
- Deadline expiry maps to stable `*_upstream_timeout` codes while completed sections remain available; all expired sections preserve the existing 503 route behavior.
- Cache misses now use per-key single-flight coordination. Different keys do not hold a global loader lock, failures are not cached, and waiters are always released.
- HTTP JSON calls use a new request-local Session per loader, so Sessions are not shared across worker threads.
- Covered by `test_slow_optional_loader_returns_partial_within_deadline`, `test_all_slow_loaders_return_unavailable_and_settle`, `test_cached_loader_is_single_flight_across_threads`, `test_failed_cache_loader_is_not_cached_or_left_locked`, and `test_rss_is_fetched_with_timeout_before_bytes_are_parsed`.
- RSS `published_parsed` UTC tuples now use `calendar.timegm`, so the 72-hour news window is independent of the Render host timezone. The integration boundary test starts with mocked RSS bytes and feedparser tuples, then verifies 70-hour retention and 73-hour exclusion through `analyze_stock_news_attention`.

## Review evidence

- Correctness: Pending Reviewer.
- Security: Pending Reviewer.
- Performance: Pending Reviewer.
- Maintainability: Pending Reviewer.
- Blocking-issue count: Pending Reviewer.
- Non-blocking findings and disposition: Pending Reviewer.

## Manual operations

- After all gates pass, commit and push the reviewed source state so Render can redeploy it.
- No SQL, environment-variable, or secret changes are required.

## Risks

- Upstream schema changes can make one or more sections partial until field mappings are updated.
- News coverage is limited to the configured RSS sources and is an attention measure, not a market recommendation.
- A loader already running when the total deadline expires cannot be force-killed by Python; it remains bounded by the shared eight-worker executor and its per-source HTTP timeout, and late exceptions are consumed.

## Gate status

- [x] Acceptance gate: Developer evidence covers AC-01..AC-11; independent Tester confirmation pending.
- [x] Test gate: Developer quality gate passed; independent Tester full regression pending.
- [ ] Review gate: blocking-issue count is zero.
- [x] Manual deployment, database, and environment steps are documented.
