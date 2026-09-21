# Agent Handoff: 可信回測基線與文案校正

## Work definition

- Objective: 使 MA20/RSI 回測具備可稽核訊號時間、現金成交、成本、來源及限制，避免舊快取假零與過強宣稱。
- In scope: 回測模型/API、日線來源 metadata、成本參數、UI 單位與文案、離線 fixture 測試。
- Out of scope: Sharpe、Sortino、CAGR、指數 benchmark、部位風險、walk-forward/OOS、AI Pareto testbed；見 docs/backtest-research-roadmap.md。
- Assumptions: NT$100,000、普通股示例費率、未還原日線、整數股、無融資放空。
- Dependencies: 現有行情來源、技術指標及 offline quality gate；前一 holder-alert 未提交修改完整保留。

## Acceptance criteria

- [x] AC-01: NT$100,000 現金帳戶，整數股，不融資或放空。
- [x] AC-02: t 日收盤 MA20/RSI 訊號僅於 t+1 Open 成交；末根訊號不成交。
- [x] AC-03: 可配置手續費率、最低手續費、賣出稅，普通股預設 0.1425% / NT$20 / 0.3%，NT$1 half-up。
- [x] AC-04: 買入含費最大可負擔股數，賣出扣費及稅。
- [x] AC-05: Buy & Hold 同窗首 Open 買入、末 Close 估值；outperformance 百分點。
- [x] AC-06: MDD 用扣費後日 equity；勝率只算已平倉 roundtrip，零筆 null。
- [x] AC-07: 維持舊回應欄位，新增幣別、資金、窗口、來源/as-of/價格基礎、成本、交易費稅及限制。
- [x] AC-08: 不用舊 backtest_results 快取；30/90/180/365 交易日及不同成本重算，超限 API 400，資料不足/過時/來源失敗明確 error。
- [x] AC-09: UI 成本輸入、NT$ / %pt / —、遠端文字 escape。
- [x] AC-10: 移除硬編未來事件，收斂絕對化宣稱，揭露日線/RSS/AI 降級及非投資建議。
- [x] AC-11: 純 fixture 離線測試涵蓋訊號時間、暖機、成本、benchmark、MDD、勝率、快取、來源日期與 UI。
- [x] AC-12: 未實作研究項目僅在 roadmap 設計，不宣稱已完成。

## Stage ownership

| Stage | Owner | Status |
| --- | --- | --- |
| Product | Product Agent | Complete |
| Developer | Developer Agent | Complete |
| Tester | Tester Agent | Pending independent verification |
| Reviewer | Reviewer Agent | Pending independent review |

## Revision identity

- Baseline/Developer HEAD: c73f4e60635f303c7c3eaa7f21b953dbec999cc6
- Staged binary patch SHA-256: pending final calculation
- Unstaged binary patch SHA-256: pending final calculation
- Untracked manifest SHA-256: pending final calculation
- Tested source-state ID: Pending Tester recomputation.
- Reviewed source-state ID: Pending Reviewer recomputation.
- Shared-workspace writer: Developer Agent（本階段唯一寫入者）

## Developer handoff

| File | Purpose |
| --- | --- |
| backtest.py | 現金帳戶、次日 Open、成本、benchmark、回撤、來源驗證 |
| data_provider.py | 日線 route metadata；回測 Yahoo 單請求及最多 24 月、6 worker 的官方備援，每次 HTTP 有讀取/容量上限 |
| models.py | 成本參數及邊界 |
| main.py | 回測逐請求重算，取消舊 hydration 排程；保留 holder-alert |
| static/index.html | 成本、單位、限制及可信首頁文案 |
| tests/test_backtest.py | 純 fixture 功能與靜態回歸 |
| docs/backtest-research-roadmap.md | 未實作研究項目 |

### Commands and results

| Command | Exit | Result |
| --- | ---: | --- |
| python -m scripts.offline_unittest tests.test_backtest -v | 0 | 18 tests passed，含極端賣出費用、零股、窗口預算與極端資料邊界 |
| python scripts/quality_gate.py | 0 | 32 Python files compiled; 93 tests passed, 1 platform skip |
| node --check (extracted static/index.html inline script) | 0 | JavaScript syntax passed |
| git diff --check | 0 | No whitespace errors |

## Test evidence

| AC | Check | Result |
| --- | --- | --- |
| 01/02/04 | next-open gap, last-bar signal, affordable shares, unfunded sale fail-closed, zero-share buy | Pass |
| 03 | fee half-up/minimum and configurable rates | Pass |
| 05 | same-window B&H and outperformance | Pass |
| 06 | fee-adjusted MDD and closed/zero roundtrip win rate | Pass |
| 07/08 | response/source validation, four window plans, 400 rejection, bounded HTTP and no legacy cache call | Pass |
| 09/10 | UI static escaping/copy and JS syntax | Pass |
| 11 | targeted and full offline regression | Pass |
| 12 | roadmap document | Developer complete; Tester pending |

## Manual operations

- No new environment variable, database migration, API key, or paid service required.
- After deployment, verify a recent ordinary-stock TWSE/TPEx window and the displayed source/as-of; provider availability is external.

## Known limitations and risks

- 未還原日線不含股利、拆股、流動性及實際滑價；ETF 與當沖稅費可能不同。
- 回測只支援 30/90/180/365 個交易日（外加 30 日暖機）。常態 Yahoo 為一次限時請求；若不足則最多 24 個官方月份、6 worker、四批。每請求採 1 秒 connect/1.5 秒 read idle timeout、2.5 秒逐位元組串流期限及 500 KB 上限，最壞來源等待預算 4 秒 ×（Yahoo 1 批 + 官方 4 批）約 20 秒，另有 JSON/排程開銷；前端 30 秒超時。slow-stream fixture 驗證期限觸發並關閉回應。來源不可用時 API 回明確錯誤，不製造績效。
- 極端有限手續費（超過資金）、股價低於 NT$0.01 或高於 NT$10 億與異常成交量會明確拒絕，防止量化/Decimal 錯誤。
- 極端低價賣出時，若最低手續費高於賣出收入加現金，回測以 sale_cost_unfunded 錯誤停止，附成交日期、成本與短缺額；不輸出負現金績效。
- 不構成投資建議，也不提供預測保證。

## Gate status

- [x] Developer local acceptance and feature/full quality gate.
- [ ] Independent Tester gate.
- [ ] Independent Reviewer gate (blocking count pending).
