-- WebStock 系統資料庫結構 (PostgreSQL for Supabase)

-- 1. 股票基本資訊表 (Stock Metadata)
CREATE TABLE IF NOT EXISTS stock_info (
    symbol VARCHAR(20) PRIMARY KEY, -- 股票代碼 (e.g., 'AAPL', '2330.TW')
    name VARCHAR(100) NOT NULL,
    sector VARCHAR(50),
    is_active BOOLEAN DEFAULT true,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. 日線 K 線資料表 (Daily Quotes)
-- 由於這是時間序列資料且資料量大，我們對 symbol 與 date 建立複合主鍵與索引
CREATE TABLE IF NOT EXISTS daily_quotes (
    symbol VARCHAR(20) REFERENCES stock_info(symbol) ON DELETE CASCADE,
    date DATE NOT NULL,
    open_price NUMERIC(15, 4) NOT NULL,
    high_price NUMERIC(15, 4) NOT NULL,
    low_price NUMERIC(15, 4) NOT NULL,
    close_price NUMERIC(15, 4) NOT NULL,
    volume BIGINT NOT NULL,
    PRIMARY KEY (symbol, date)
);
-- 建立針對日期與代碼的查詢索引，加速前端畫圖讀取
CREATE INDEX IF NOT EXISTS idx_daily_quotes_symbol_date ON daily_quotes(symbol, date DESC);

-- 3. 策略回測結果快取表 (Backtest Results Cache)
-- 用於存放批次運算好的各項指標與回測數據，避免前端讀取時重複計算
CREATE TABLE IF NOT EXISTS backtest_results (
    symbol VARCHAR(20) REFERENCES stock_info(symbol) ON DELETE CASCADE,
    strategy_name VARCHAR(50) NOT NULL, -- 例如: 'MA_Cross_20_60'
    win_rate NUMERIC(5, 2), -- 勝率 (e.g., 68.50)
    max_drawdown NUMERIC(5, 2), -- 最大回落 (e.g., -12.40)
    total_return NUMERIC(10, 2), -- 總報酬率
    latest_signal VARCHAR(20), -- 最新訊號 (e.g., 'BUY', 'SELL', 'NEUTRAL')
    calculated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, strategy_name)
);

-- 4. 背景任務追蹤表 (Job Status Tracker)
-- 解決 Render 容器重啟導致任務揮發的關鍵防護表
CREATE TABLE IF NOT EXISTS job_status (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type VARCHAR(50) NOT NULL, -- 例如: 'DAILY_DATA_SYNC', 'BACKTEST_CALC'
    status VARCHAR(20) NOT NULL, -- 'PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED'
    progress_details TEXT, -- 存放 JSON 字串，例如 {"current_stock": "AAPL", "processed": 15, "total": 100}
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 自動更新 updated_at 欄位的觸發器函數
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_job_status_modtime
BEFORE UPDATE ON job_status
FOR EACH ROW EXECUTE PROCEDURE update_modified_column();
