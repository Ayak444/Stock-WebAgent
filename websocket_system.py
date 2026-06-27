"""
WebSocket 實時推送系統
替代前端輪詢機制，實現服務器主動推送實時行情
"""
import json
import asyncio
from typing import Dict, List, Set
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    管理所有活躍的 WebSocket 連接
    支持廣播和點對點消息
    """
    def __init__(self):
        self.active_connections: Dict[str, List] = {}  # room_id -> [websocket...]
        self.user_subscriptions: Dict[str, Set[str]] = {}  # client_id -> {ticker...}
        self.lock = asyncio.Lock()
    
    async def connect(self, websocket, room_id: str = "default"):
        """新增連接"""
        await websocket.accept()
        
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        
        self.active_connections[room_id].append(websocket)
        logger.info(f"客戶端已連接到 {room_id}，共 {len(self.active_connections[room_id])} 個連接")
    
    async def disconnect(self, websocket, room_id: str = "default"):
        """移除連接"""
        if room_id in self.active_connections:
            try:
                self.active_connections[room_id].remove(websocket)
                logger.info(f"客戶端已斷開 {room_id}，剩餘 {len(self.active_connections[room_id])} 個連接")
            except ValueError:
                pass
    
    async def subscribe(self, client_id: str, ticker: str):
        """訂閱特定股票"""
        if client_id not in self.user_subscriptions:
            self.user_subscriptions[client_id] = set()
        
        self.user_subscriptions[client_id].add(ticker)
        logger.debug(f"客戶端 {client_id} 已訂閱 {ticker}")
    
    async def unsubscribe(self, client_id: str, ticker: str):
        """取消訂閱"""
        if client_id in self.user_subscriptions:
            self.user_subscriptions[client_id].discard(ticker)
    
    async def broadcast(self, message: dict, room_id: str = "default"):
        """廣播消息到房間"""
        if room_id not in self.active_connections:
            return
        
        message['timestamp'] = datetime.now().isoformat()
        msg_text = json.dumps(message, ensure_ascii=False)
        
        dead_connections = []
        for connection in self.active_connections[room_id]:
            try:
                await connection.send_text(msg_text)
            except Exception as e:
                logger.warning(f"發送消息失敗: {e}")
                dead_connections.append(connection)
        
        # 清理失效連接
        for conn in dead_connections:
            try:
                self.active_connections[room_id].remove(conn)
            except ValueError:
                pass
    
    async def send_to_client(self, websocket, message: dict):
        """發送消息到特定客戶端"""
        try:
            message['timestamp'] = datetime.now().isoformat()
            await websocket.send_text(json.dumps(message, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"發送消息到客戶端失敗: {e}")
    
    def get_connection_count(self, room_id: str = "default") -> int:
        """取得房間連接數"""
        return len(self.active_connections.get(room_id, []))
    
    def get_stats(self) -> dict:
        """取得連接統計"""
        total = sum(len(conns) for conns in self.active_connections.values())
        subscriptions = sum(len(tickers) for tickers in self.user_subscriptions.values())
        
        return {
            "total_connections": total,
            "rooms": len(self.active_connections),
            "total_subscriptions": subscriptions,
            "room_details": {
                room: len(conns)
                for room, conns in self.active_connections.items()
            }
        }


class PriceStreamBroadcaster:
    """
    行情數據實時推送器
    定期推送股票實時行情到所有連接的客戶端
    """
    def __init__(self, ws_manager: WebSocketManager):
        self.ws_manager = ws_manager
        self.streaming = False
        self.stream_task = None
        self.price_cache = {}  # 用於比較變化
    
    async def start_streaming(self, data_provider, interval: int = 5):
        """
        啟動實時推送
        interval: 推送間隔（秒）
        """
        self.streaming = True
        self.stream_task = asyncio.create_task(
            self._stream_loop(data_provider, interval)
        )
        logger.info("行情推送已啟動")
    
    async def stop_streaming(self):
        """停止實時推送"""
        self.streaming = False
        if self.stream_task:
            self.stream_task.cancel()
            try:
                await self.stream_task
            except asyncio.CancelledError:
                pass
        logger.info("行情推送已停止")
    
    async def _stream_loop(self, data_provider, interval: int):
        """推送循環"""
        while self.streaming:
            try:
                # 收集所有訂閱的股票代碼
                all_tickers = set()
                for tickers in self.ws_manager.user_subscriptions.values():
                    all_tickers.update(tickers)
                
                if not all_tickers:
                    await asyncio.sleep(interval)
                    continue
                
                # 並行獲取所有股票的實時價格
                prices = await data_provider.get_multiple_prices(list(all_tickers))
                
                # 推送價格更新
                for ticker, price in prices.items():
                    if price is not None:
                        # 檢查價格是否有變化
                        old_price = self.price_cache.get(ticker)
                        if old_price is None or abs(price - old_price) > 0.01:
                            self.price_cache[ticker] = price
                            
                            # 計算漲跌幅
                            change_pct = 0
                            if old_price:
                                change_pct = ((price - old_price) / old_price) * 100
                            
                            message = {
                                "type": "price_update",
                                "ticker": ticker,
                                "price": round(price, 2),
                                "change_pct": round(change_pct, 2)
                            }
                            
                            await self.ws_manager.broadcast(message, room_id="prices")
                
                await asyncio.sleep(interval)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"推送循環出現錯誤: {e}")
                await asyncio.sleep(interval)
    
    async def push_analysis_result(self, ticker: str, analysis: dict):
        """推送分析結果"""
        message = {
            "type": "analysis_result",
            "ticker": ticker,
            "data": analysis
        }
        await self.ws_manager.broadcast(message, room_id="analysis")
    
    async def push_news_alert(self, ticker: str, news: dict):
        """推送新聞警報"""
        message = {
            "type": "news_alert",
            "ticker": ticker,
            "news": news
        }
        await self.ws_manager.broadcast(message, room_id="news")
    
    async def push_market_status(self, status: dict):
        """推送市場狀態"""
        message = {
            "type": "market_status",
            "data": status
        }
        await self.ws_manager.broadcast(message, room_id="market")


class WebSocketMessageHandler:
    """
    WebSocket 客戶端消息處理器
    """
    def __init__(self, ws_manager: WebSocketManager):
        self.ws_manager = ws_manager
    
    async def handle_message(self, websocket, client_id: str, message: str):
        """
        處理客戶端消息
        支持的消息類型：subscribe, unsubscribe, ping
        """
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "subscribe":
                ticker = data.get("ticker")
                if ticker:
                    await self.ws_manager.subscribe(client_id, ticker)
                    response = {
                        "type": "subscription_confirmed",
                        "ticker": ticker,
                        "status": "subscribed"
                    }
                    await self.ws_manager.send_to_client(websocket, response)
            
            elif msg_type == "unsubscribe":
                ticker = data.get("ticker")
                if ticker:
                    await self.ws_manager.unsubscribe(client_id, ticker)
                    response = {
                        "type": "subscription_confirmed",
                        "ticker": ticker,
                        "status": "unsubscribed"
                    }
                    await self.ws_manager.send_to_client(websocket, response)
            
            elif msg_type == "ping":
                response = {"type": "pong", "timestamp": datetime.now().isoformat()}
                await self.ws_manager.send_to_client(websocket, response)
            
            elif msg_type == "get_subscriptions":
                subscriptions = self.ws_manager.user_subscriptions.get(client_id, set())
                response = {
                    "type": "subscriptions",
                    "data": list(subscriptions)
                }
                await self.ws_manager.send_to_client(websocket, response)
        
        except json.JSONDecodeError:
            logger.warning(f"無效的 JSON 消息: {message}")
        except Exception as e:
            logger.error(f"處理消息出現錯誤: {e}")


# 全局 WebSocket 管理器實例
ws_manager = WebSocketManager()
msg_handler = WebSocketMessageHandler(ws_manager)
price_broadcaster = None  # 在 main.py 初始化


async def initialize_websocket_system(data_provider):
    """初始化 WebSocket 系統"""
    global price_broadcaster
    price_broadcaster = PriceStreamBroadcaster(ws_manager)
    await price_broadcaster.start_streaming(data_provider, interval=5)


async def shutdown_websocket_system():
    """關閉 WebSocket 系統"""
    global price_broadcaster
    if price_broadcaster:
        await price_broadcaster.stop_streaming()
