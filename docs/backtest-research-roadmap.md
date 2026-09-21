# 回測研究後續規劃

目前基線只處理單一股票、MA20/RSI 收盤訊號、次日開盤整數股現金成交與普通股示例成本。歷史績效不能推論未來，也不構成投資建議。

後續研究：
1. Sharpe、Sortino、CAGR：先定義無風險利率、年化交易日、無交易日及區間處理，再以固定 fixture 驗算。
2. 指數 benchmark：同交易窗口、幣別及價格基礎，揭露股利與追蹤誤差。
3. 部位風險：可配置單筆上限、停損與滑價模型，先處理缺乏盤中成交資訊。
4. Walk-forward / OOS：預先固定資料切分、搜尋空間及重訓節奏，防止測試區間參與參數選擇。
5. AI Agent routing Pareto testbed：評估延遲（latency）、API 費用（API cost）、模型品質（model quality）、可靠性（reliability）、任務複雜度（task complexity）與信心校準（confidence）；這些是 AI 路由面向，不以交易報酬、回撤或券商成本代替。現有 Yahoo→TWSE 行情路由及 Groq 單模型隔離／quick-deep 降級僅是目前機制；候選 AI 路由尚未實作，也沒有實測證據可稱 Pareto 最適。

研究設計：建立去識別的離線任務集，依複雜度與失效情境分層，版本化真值與盲評 rubric；採時序 train/dev/OOS 切分，固定模型、prompt、路由 policy 與 seed，避免洩漏。量測盲評品質、延遲 p50/p95、tokens、按版本化價目表估算 API 費用、成功／降級／timeout 率，以及信心校準和 coverage；比較現有 quick/deep、always quick、always deep 與候選路由，在預先設定的品質下限及延遲／費用預算下，用 paired bootstrap 信賴區間辨識 Pareto 非支配解，不以單一混合分數宣稱全域最優。

上述均為研究設計，尚未實作或驗證。
