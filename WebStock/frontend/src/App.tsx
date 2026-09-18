import { useState, useEffect } from 'react';
import './App.css';
import { Activity, LayoutDashboard, Settings, TrendingUp, BarChart2, Zap } from 'lucide-react';
import axios from 'axios';
import { Chart } from './Chart';

const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');

function App() {
  const [isAwakening, setIsAwakening] = useState(true);
  const [progress, setProgress] = useState(0);
  
  const [stockList, setStockList] = useState<any[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('AAPL');
  const [stockDetails, setStockDetails] = useState<any>(null);
  const [searchTerm, setSearchTerm] = useState('');

  // Indicator Toggles State
  const [indicators, setIndicators] = useState({
    kd: false,
    macd: true,
    rsi: true,
    bias: false,
  });

  const toggleIndicator = (key: keyof typeof indicators) => {
    setIndicators(prev => ({ ...prev, [key]: !prev[key] }));
  };

  // Cold Start Animation & Initial Data Fetch
  useEffect(() => {
    if (isAwakening) {
      const interval = setInterval(() => {
        setProgress((prev) => {
          if (prev >= 100) {
            clearInterval(interval);
            setTimeout(() => setIsAwakening(false), 500);
            return 100;
          }
          return prev + Math.random() * 15;
        });
      }, 400);

      // Fetch basic list
      axios.get(`${API_BASE}/api/stocks`)
        .then(res => {
          setStockList(res.data.data);
          // Auto-select first stock if AAPL is not present
          if (res.data.data.length > 0 && !res.data.data.find((s: any) => s.symbol === 'AAPL')) {
            setSelectedSymbol(res.data.data[0].symbol);
          }
        })
        .catch(err => console.error("API Error:", err));

      return () => clearInterval(interval);
    }
  }, [isAwakening]);

  // Fetch detailed historical data when symbol changes
  useEffect(() => {
    if (selectedSymbol) {
      axios.get(`${API_BASE}/api/stocks/${selectedSymbol}`)
        .then(res => setStockDetails(res.data))
        .catch(err => console.error("API Error:", err));
    }
  }, [selectedSymbol]);

  if (isAwakening) {
    return (
      <div className="loading-overlay">
        <div className="aurora-bg"></div>
        <Activity size={48} color="#00F2FE" />
        <div className="loading-text">正在啟動量化分析引擎...</div>
        <div className="progress-container">
          <div 
            className="progress-bar-fill" 
            style={{ width: `${Math.min(progress, 100)}%`, transition: 'width 0.4s ease-out' }}
          ></div>
        </div>
      </div>
    );
  }

  // Safe extract for rendering
  const quotes = stockDetails?.quotes || [];
  const latestQuote = quotes.length > 0 ? quotes[quotes.length - 1] : null;
  const prevQuote = quotes.length > 1 ? quotes[quotes.length - 2] : null;
  
  let change = 0;
  let changePct = 0;
  if (latestQuote && prevQuote) {
    change = latestQuote.close - prevQuote.close;
    changePct = (change / prevQuote.close) * 100;
  }
  const isPositive = change >= 0;

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header glass-panel">
        <div className="header-title">Nexus Quant</div>
        <input 
          type="text" 
          className="search-bar" 
          placeholder="輸入股票代碼 (e.g., AAPL, 2330.TW)..." 
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </header>

      {/* Main Grid Content */}
      <main className="main-content">
        
        {/* Left Panel */}
        <div className="side-panel glass-panel hidden-mobile">
          <div className="panel-header">
            <LayoutDashboard size={18} style={{ marginRight: '8px', verticalAlign: 'middle' }} />
            自選清單 & 即時訊號
          </div>
          <div className="panel-body">
            {stockList.length === 0 ? (
              <p style={{ color: 'var(--color-text-secondary)' }}>載入中...</p>
            ) : (
              stockList.filter(s => s.symbol.toLowerCase().includes(searchTerm.toLowerCase())).map(stock => (
                <div 
                  key={stock.symbol} 
                  style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between', 
                    padding: '12px 8px', 
                    borderBottom: '1px solid var(--bg-glass-border)',
                    cursor: 'pointer',
                    background: selectedSymbol === stock.symbol ? 'rgba(0, 242, 254, 0.1)' : 'transparent',
                    borderRadius: '4px'
                  }}
                  onClick={() => setSelectedSymbol(stock.symbol)}
                >
                  <span style={{ fontWeight: selectedSymbol === stock.symbol ? 'bold' : 'normal' }}>{stock.symbol}</span>
                  <span style={{ color: stock.latest_signal === 'SELL' ? 'var(--color-sell)' : 'var(--color-buy)' }}>
                    {stock.win_rate}% 勝率 ({stock.latest_signal || 'N/A'})
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Center Panel (Chart) */}
        <div className="chart-panel glass-panel">
          <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div>
              <span style={{ fontSize: '20px', fontWeight: 'bold' }}>
                {stockDetails?.symbol || selectedSymbol} 
              </span>
              <span style={{ marginLeft: '16px', color: 'var(--color-text-secondary)' }}>
                {stockList.find(s => s.symbol === selectedSymbol)?.name || 'Loading...'}
              </span>
            </div>
            {latestQuote && (
              <div style={{ textAlign: 'right' }}>
                <div style={{ color: isPositive ? 'var(--color-buy)' : 'var(--color-sell)', fontSize: '24px', fontWeight: 'bold' }}>
                  $ {Number(latestQuote.close).toFixed(2)}
                </div>
                <div style={{ color: isPositive ? 'var(--color-buy)' : 'var(--color-sell)', fontSize: '14px' }}>
                  {isPositive ? '+' : ''}{Number(change).toFixed(2)} ({isPositive ? '+' : ''}{Number(changePct).toFixed(2)}%)
                </div>
              </div>
            )}
          </div>
          
          <div className="panel-body" style={{ width: '100%' }}>
            {stockDetails?.quotes ? (
              <Chart data={stockDetails.quotes} />
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '450px' }}>
                <p style={{ color: 'var(--color-text-secondary)' }}>載入圖表中...</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Panel (Analysis & Sandbox) */}
        <div className="side-panel glass-panel">
          <div className="panel-header">
            <Settings size={18} style={{ marginRight: '8px', verticalAlign: 'middle' }} />
            綜合分析與沙盒參數
          </div>
          
          <div className="panel-body" style={{ paddingRight: '8px' }}>
            
            {/* 1. 成交量與動能分析 */}
            <div style={{ marginBottom: '24px' }}>
              <h4 style={{ color: 'var(--color-text-secondary)', marginBottom: '12px', display: 'flex', alignItems: 'center' }}>
                <BarChart2 size={16} style={{ marginRight: '6px' }} /> 成交量動能
              </h4>
              <div style={{ background: 'rgba(0,0,0,0.2)', padding: '12px', borderRadius: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold' }}>
                    {latestQuote ? (Number(latestQuote.volume) / 1000000).toFixed(1) + 'M' : '-'}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>最新成交量</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ color: '#FF9900', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Zap size={14} /> 爆大量 (2.5x)
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>20日均量: 23.1M</div>
                </div>
              </div>
            </div>

            {/* 2. 多空情緒儀表板 */}
            <div style={{ marginBottom: '24px' }}>
              <h4 style={{ color: 'var(--color-text-secondary)', marginBottom: '12px', display: 'flex', alignItems: 'center' }}>
                <TrendingUp size={16} style={{ marginRight: '6px' }} /> 綜合市場情緒
              </h4>
              <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden', display: 'flex' }}>
                <div style={{ width: '30%', background: 'var(--color-sell)' }}></div>
                <div style={{ width: '20%', background: '#8B95A5' }}></div>
                <div style={{ width: '50%', background: 'var(--color-buy)' }}></div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginTop: '6px' }}>
                <span style={{ color: 'var(--color-sell)' }}>偏空 (30%)</span>
                <span style={{ color: 'var(--color-text-secondary)' }}>中立</span>
                <span style={{ color: 'var(--color-buy)' }}>偏多 (50%)</span>
              </div>
            </div>

            {/* 3. 技術指標沙盒 */}
            <div style={{ borderTop: '1px solid var(--bg-glass-border)', paddingTop: '20px' }}>
              <h4 style={{ color: 'var(--color-text-secondary)', marginBottom: '16px' }}>技術指標疊加 (副圖與訊號)</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                  <input type="checkbox" checked={indicators.macd} onChange={() => toggleIndicator('macd')} style={{ marginRight: '12px', accentColor: 'var(--color-buy)', width: '16px', height: '16px' }} />
                  <span style={{ flexGrow: 1 }}>MACD (平滑異同移動平均)</span>
                  {indicators.macd && <span style={{ color: 'var(--color-buy)', fontSize: '12px' }}>黃金交叉</span>}
                </label>
                <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                  <input type="checkbox" checked={indicators.rsi} onChange={() => toggleIndicator('rsi')} style={{ marginRight: '12px', accentColor: 'var(--color-buy)', width: '16px', height: '16px' }} />
                  <span style={{ flexGrow: 1 }}>RSI (相對強弱指標)</span>
                  {indicators.rsi && <span style={{ color: 'var(--color-text-secondary)', fontSize: '12px' }}>數值: 58 (中立)</span>}
                </label>
                <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                  <input type="checkbox" checked={indicators.kd} onChange={() => toggleIndicator('kd')} style={{ marginRight: '12px', accentColor: 'var(--color-buy)', width: '16px', height: '16px' }} />
                  <span style={{ flexGrow: 1 }}>KD (隨機指標)</span>
                  {indicators.kd && <span style={{ color: 'var(--color-sell)', fontSize: '12px' }}>高檔超買</span>}
                </label>
                <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                  <input type="checkbox" checked={indicators.bias} onChange={() => toggleIndicator('bias')} style={{ marginRight: '12px', accentColor: 'var(--color-buy)', width: '16px', height: '16px' }} />
                  <span style={{ flexGrow: 1 }}>乖離率 (Bias Ratio)</span>
                  {indicators.bias && <span style={{ color: 'var(--color-buy)', fontSize: '12px' }}>負乖離過大 (可搶反彈)</span>}
                </label>
              </div>
            </div>

            {/* 4. 回測數據摘要 */}
            <div style={{ borderTop: '1px solid var(--bg-glass-border)', paddingTop: '20px', marginTop: '20px' }}>
               <h4 style={{ color: 'var(--color-text-secondary)', marginBottom: '16px' }}>策略回測摘要</h4>
               <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  <div>
                    <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>歷史勝率</div>
                    <div style={{ fontSize: '24px', color: 'var(--color-buy)', fontWeight: '700' }}>
                      {stockDetails?.backtest?.win_rate || '-'}%
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>最大回落</div>
                    <div style={{ fontSize: '24px', color: 'var(--color-sell)', fontWeight: '700' }}>
                      {stockDetails?.backtest?.max_drawdown || '-'}%
                    </div>
                  </div>
               </div>
            </div>

          </div>
        </div>

      </main>
    </div>
  );
}

export default App;
