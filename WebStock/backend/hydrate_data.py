import yfinance as yf
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import gc
import os
from dotenv import load_dotenv
import datetime

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

TARGET_STOCKS = [
    {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology"},
    {"symbol": "MSFT", "name": "Microsoft Corp.", "sector": "Technology"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "sector": "Consumer Cyclical"},
    {"symbol": "NVDA", "name": "NVIDIA Corp.", "sector": "Technology"},
    {"symbol": "2330.TW", "name": "TSMC", "sector": "Technology"}
]

def calculate_backtest(df):
    """Calculate a reproducible MA20/MA60 strategy without synthetic metrics."""
    prices = df.sort_values('Date').copy()
    prices['SMA_20'] = prices['Close'].rolling(window=20).mean()
    prices['SMA_60'] = prices['Close'].rolling(window=60).mean()
    prices = prices.dropna(subset=['SMA_20', 'SMA_60'])
    if len(prices) < 2:
        raise ValueError("not enough history for MA20/MA60 backtest")

    signal = (prices['SMA_20'] > prices['SMA_60']).astype(int)
    position = signal.shift(1).fillna(0)
    daily_return = prices['Close'].pct_change().fillna(0)
    turnover = position.diff().abs().fillna(position.abs())
    strategy_return = position * daily_return - turnover * 0.001425
    equity = (1 + strategy_return).cumprod()
    drawdown = equity / equity.cummax() - 1

    entry_price = None
    closed_returns = []
    for idx in range(1, len(prices)):
        if signal.iloc[idx] == 1 and signal.iloc[idx - 1] == 0:
            entry_price = float(prices['Close'].iloc[idx])
        elif signal.iloc[idx] == 0 and signal.iloc[idx - 1] == 1 and entry_price:
            exit_price = float(prices['Close'].iloc[idx])
            closed_returns.append(exit_price / entry_price - 1)
            entry_price = None

    win_rate = (
        sum(value > 0 for value in closed_returns) / len(closed_returns) * 100
        if closed_returns else 0
    )
    latest_signal = 'BUY' if signal.iloc[-1] else 'NEUTRAL'
    return {
        'win_rate': round(win_rate, 2),
        'max_drawdown': round(float(drawdown.min()) * 100, 2),
        'total_return': round((float(equity.iloc[-1]) - 1) * 100, 2),
        'latest_signal': latest_signal,
    }

def hydrate_stock(conn, stock_info):
    symbol = stock_info["symbol"]
    print(f"[{symbol}] 開始處理歷史資料...")
    
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3y")
        
        if df.empty:
            print(f"[{symbol}] Yahoo Finance returned no data; skipped without writing synthetic prices.")
            return False
        df.reset_index(inplace=True)
        if df['Date'].dt.tz is not None:
            df['Date'] = df['Date'].dt.tz_convert(None)
    except Exception as e:
        print(f"[{symbol}] Yahoo Finance failed: {e}; skipped without writing synthetic prices.")
        return False

    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO stock_info (symbol, name, sector)
                VALUES (%s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE 
                SET last_updated = CURRENT_TIMESTAMP;
            """, (symbol, stock_info["name"], stock_info["sector"]))
        
        insert_data = []
        for _, row in df.iterrows():
            insert_data.append((
                symbol,
                row['Date'].date(),
                float(row['Open']),
                float(row['High']),
                float(row['Low']),
                float(row['Close']),
                int(row['Volume'])
            ))
            
        with conn.cursor() as cur:
            query = """
                INSERT INTO daily_quotes (symbol, date, open_price, high_price, low_price, close_price, volume)
                VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open_price = EXCLUDED.open_price,
                    high_price = EXCLUDED.high_price,
                    low_price = EXCLUDED.low_price,
                    close_price = EXCLUDED.close_price,
                    volume = EXCLUDED.volume;
            """
            execute_values(cur, query, insert_data)
        
        metrics = calculate_backtest(df)
        
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO backtest_results (symbol, strategy_name, win_rate, max_drawdown, total_return, latest_signal)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, strategy_name) DO UPDATE 
                SET calculated_at = CURRENT_TIMESTAMP, win_rate = EXCLUDED.win_rate;
            """, (
                symbol,
                'MA_Cross_20_60',
                metrics['win_rate'],
                metrics['max_drawdown'],
                metrics['total_return'],
                metrics['latest_signal'],
            ))
            
        conn.commit()
        print(f"[{symbol}] 處理完成！\n")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"[{symbol}] 發生錯誤: {e}\n")
        return False

def main():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        print("成功連線至 Supabase!\n")
    except Exception as e:
        print(f"連線至 Supabase 失敗: {e}")
        return

    for idx, stock in enumerate(TARGET_STOCKS):
        hydrate_stock(conn, stock)
        
        if (idx + 1) % 5 == 0:
            gc.collect()

    conn.close()
    print("所有歷史資料回填作業完畢！")

if __name__ == "__main__":
    main()
