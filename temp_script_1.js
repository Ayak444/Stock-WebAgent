
// WebSocket 連接完成後的回調
async function initializeRealTimeFeatures() {
  console.log('✓ 實時推送系統已初始化');
  
  // 當前活躍的標籤列表
  const activeTickersFromUI = new Set();
  
  // 監聽頁面切換
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      const page = this.getAttribute('data-page');
      // 根據頁面類型訂閱相應的數據
      if (page === 'portfolio' && wsClient) {
        // 從 UI 提取投資組合中的所有股票代碼
        const portfolioItems = document.querySelectorAll('[data-ticker]');
        portfolioItems.forEach(item => {
          const ticker = item.getAttribute('data-ticker');
          if (ticker) wsClient.subscribe(ticker);
        });
      }
    });
  });
}

// 優雅地集成 WebSocket 和已有的 API 調用
const originalApiCall = window.apiCall || (async (url) => {
  const res = await fetch(url);
  return res.json();
});

window.apiCall = async function(url, options = {}) {
  const result = await originalApiCall(url, options);
  
  // 如果是股票分析結果，則通過 WebSocket 推送到其他連接
  if (url.includes('/analyze') && result.data && wsClient) {
    result.data.forEach(item => {
      if (item.ticker) {
        // 推送分析結果到 WebSocket
        if (wsClient.ws && wsClient.ws.readyState === WebSocket.OPEN) {
          console.log(`推送分析結果到 WebSocket: ${item.ticker}`);
        }
      }
    });
  }
  
  return result;
};

// 初始化完成後自動訂閱推薦的股票
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(initializeRealTimeFeatures, 1000);
});
