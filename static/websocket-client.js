/**
 * WebSocket 實時推送客戶端
 * 替代前端輪詢機制
 */

class StockWebSocketClient {
    constructor(baseUrl = window.location.origin) {
        this.baseUrl = baseUrl.replace(/^http/, 'ws');
        this.ws = null;
        this.clientId = null;
        this.subscriptions = new Set();
        this.messageHandlers = {};
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
    }

    /**
     * 連接到 WebSocket 伺服器
     */
    connect() {
        return new Promise((resolve, reject) => {
            try {
                this.ws = new WebSocket(`${this.baseUrl}/ws/live`);

                this.ws.onopen = () => {
                    console.log('✓ WebSocket 已連接');
                    this.reconnectAttempts = 0;
                    resolve();
                };

                this.ws.onmessage = (event) => {
                    try {
                        const message = JSON.parse(event.data);
                        this.handleMessage(message);
                    } catch (e) {
                        console.error('消息解析失敗:', e);
                    }
                };

                this.ws.onerror = (error) => {
                    console.error('WebSocket 錯誤:', error);
                    reject(error);
                };

                this.ws.onclose = () => {
                    console.warn('⚠ WebSocket 已斷開');
                    this.attemptReconnect();
                };
            } catch (e) {
                reject(e);
            }
        });
    }

    /**
     * 重新連接邏輯
     */
    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`正在重新連接... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
            setTimeout(() => {
                this.connect().catch(err => console.error('重連失敗:', err));
            }, this.reconnectDelay);
        } else {
            console.error('✗ WebSocket 連接已失敗，請刷新頁面');
        }
    }

    /**
     * 處理伺服器消息
     */
    handleMessage(message) {
        const { type, timestamp } = message;

        console.debug(`收到消息: ${type}`);

        switch (type) {
            case 'connection_established':
                this.clientId = message.client_id;
                console.log(`✓ 連接已建立，客戶端ID: ${this.clientId}`);
                break;

            case 'price_update':
                this.dispatchEvent('price_update', message);
                break;

            case 'analysis_result':
                this.dispatchEvent('analysis_result', message);
                break;

            case 'news_alert':
                this.dispatchEvent('news_alert', message);
                break;

            case 'market_status':
                this.dispatchEvent('market_status', message);
                break;

            case 'subscription_confirmed':
                console.log(`✓ ${message.status} 完成: ${message.ticker}`);
                break;

            case 'pong':
                // 心跳回應
                break;

            default:
                console.warn(`未知消息類型: ${type}`);
        }
    }

    /**
     * 訂閱股票實時行情
     */
    subscribe(ticker) {
        if (this.subscriptions.has(ticker)) {
            return;
        }

        this.subscriptions.add(ticker);
        this.sendMessage({
            type: 'subscribe',
            ticker: ticker
        });
    }

    /**
     * 取消訂閱
     */
    unsubscribe(ticker) {
        this.subscriptions.delete(ticker);
        this.sendMessage({
            type: 'unsubscribe',
            ticker: ticker
        });
    }

    /**
     * 發送消息到伺服器
     */
    sendMessage(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        } else {
            console.warn('WebSocket 未連接');
        }
    }

    /**
     * 註冊事件監聽器
     */
    on(eventType, handler) {
        if (!this.messageHandlers[eventType]) {
            this.messageHandlers[eventType] = [];
        }
        this.messageHandlers[eventType].push(handler);
    }

    /**
     * 取消事件監聽器
     */
    off(eventType, handler) {
        if (this.messageHandlers[eventType]) {
            const idx = this.messageHandlers[eventType].indexOf(handler);
            if (idx > -1) {
                this.messageHandlers[eventType].splice(idx, 1);
            }
        }
    }

    /**
     * 觸發事件
     */
    dispatchEvent(eventType, data) {
        if (this.messageHandlers[eventType]) {
            this.messageHandlers[eventType].forEach(handler => {
                try {
                    handler(data);
                } catch (e) {
                    console.error(`事件處理器出錯: ${e}`);
                }
            });
        }
    }

    /**
     * 發送心跳
     */
    ping() {
        this.sendMessage({ type: 'ping' });
    }

    /**
     * 獲取當前訂閱列表
     */
    getSubscriptions() {
        this.sendMessage({ type: 'get_subscriptions' });
    }

    /**
     * 斷開連接
     */
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}

// ===== 使用示例 =====
let wsClient = null;

async function initializeWebSocket() {
    wsClient = new StockWebSocketClient();

    // 連接到伺服器
    try {
        await wsClient.connect();

        // 註冊事件處理器
        wsClient.on('price_update', handlePriceUpdate);
        wsClient.on('analysis_result', handleAnalysisResult);
        wsClient.on('news_alert', handleNewsAlert);

        // 訂閱初始股票
        const initialTickers = ['2330.TW', '0050.TW', 'NVDA'];
        initialTickers.forEach(ticker => wsClient.subscribe(ticker));

        // 定期發送心跳保持連接
        setInterval(() => wsClient.ping(), 30000);

    } catch (e) {
        console.error('WebSocket 初始化失敗:', e);
    }
}

function handlePriceUpdate(message) {
    const { ticker, price, change_pct } = message;
    console.log(`📊 ${ticker}: $${price} (${change_pct > 0 ? '+' : ''}${change_pct}%)`);

    // TODO: 更新 UI（儀表板、圖表等）
    updatePriceDisplay(ticker, price, change_pct);
}

function handleAnalysisResult(message) {
    const { ticker, data } = message;
    console.log(`🔍 ${ticker} 分析結果:`, data);

    // TODO: 更新分析結果面板
    updateAnalysisPanel(ticker, data);
}

function handleNewsAlert(message) {
    const { ticker, news } = message;
    console.log(`📰 ${ticker} 新聞提醒:`, news);

    // TODO: 添加到新聞面板
    addNewsItem(news);
}

function updatePriceDisplay(ticker, price, changePct) {
    // 在儀表板中找到對應的價格元素並更新
    const priceElement = document.querySelector(`[data-ticker="${ticker}"] .price`);
    if (priceElement) {
        priceElement.textContent = `$${price}`;
        priceElement.classList.toggle('up', changePct > 0);
        priceElement.classList.toggle('down', changePct < 0);
    }
}

function updateAnalysisPanel(ticker, data) {
    // 更新分析結果面板
    console.log('更新分析結果:', ticker, data);
}

function addNewsItem(news) {
    // 添加新聞到面板
    console.log('添加新聞:', news);
}

// 在 DOM 加載完成時初始化
document.addEventListener('DOMContentLoaded', initializeWebSocket);

// 在頁面卸載時斷開連接
window.addEventListener('beforeunload', () => {
    if (wsClient) {
        wsClient.disconnect();
    }
});
