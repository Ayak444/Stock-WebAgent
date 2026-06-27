"""
GraphQL API 層
提供強類型的 GraphQL 查詢和變更
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import strawberry
from strawberry.types import ExecutionResult
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ============ GraphQL 類型定義 ============

@strawberry.type
class StockPrice:
    """股票價格類型"""
    ticker: str
    price: float
    change_percent: float
    timestamp: str


@strawberry.type
class Indicator:
    """技術指標類型"""
    name: str
    value: float
    signal: str  # "buy", "sell", "hold"


@strawberry.type
class AnalysisSignal:
    """分析信號類型"""
    type: str  # "moving_average", "rsi", "macd", etc.
    signal: str  # "bullish", "bearish", "neutral"
    strength: float  # 0-100


@strawberry.type
class StockAnalysis:
    """股票分析結果類型"""
    ticker: str
    name: str
    price: float
    score: int  # 0-100
    advice: str  # "偏多", "偏空", "觀望"
    signals: List[str]
    valuation: str
    profit_loss: float
    stop_loss: float
    exit_strategy: str
    confidence: float  # 0-1
    created_at: str
    cached: bool = False


@strawberry.type
class MacroIndicator:
    """宏觀指標類型"""
    name: str
    value: float
    change_percent: float
    description: str


@strawberry.type
class NewsItem:
    """新聞項目類型"""
    title: str
    content: str
    source: str
    sentiment: str  # "positive", "negative", "neutral"
    sentiment_score: float  # 0-100
    published_at: str
    url: str


@strawberry.type
class Portfolio:
    """投資組合類型"""
    ticker: str
    shares: int
    cost: float
    current_price: float
    total_cost: float
    current_value: float
    profit_loss: float
    profit_loss_percent: float


@strawberry.type
class SystemHealth:
    """系統健康狀態"""
    status: str  # "ok", "warning", "error"
    uptime_seconds: int
    memory_used_mb: float
    cache_hit_rate: float
    active_connections: int
    pending_tasks: int
    last_update: str


@strawberry.type
class CacheStats:
    """緩存統計"""
    total_keys: int
    memory_used_mb: float
    hit_rate: float
    evicted_items: int
    connected: bool


# ============ 查詢解析器 ============

@strawberry.type
class Query:
    """GraphQL 查詢"""
    
    @strawberry.field
    async def get_stock_price(self, ticker: str) -> Optional[StockPrice]:
        """獲取股票價格"""
        # 這將由 main.py 中的 resolver 實現
        logger.debug(f"Query: get_stock_price({ticker})")
        return None
    
    @strawberry.field
    async def get_stocks_prices(self, tickers: List[str]) -> List[StockPrice]:
        """獲取多個股票價格"""
        logger.debug(f"Query: get_stocks_prices({tickers})")
        return []
    
    @strawberry.field
    async def analyze_stock(self, ticker: str) -> Optional[StockAnalysis]:
        """分析單支股票"""
        logger.debug(f"Query: analyze_stock({ticker})")
        return None
    
    @strawberry.field
    async def analyze_stocks(self, tickers: List[str]) -> List[StockAnalysis]:
        """分析多支股票"""
        logger.debug(f"Query: analyze_stocks({tickers})")
        return []
    
    @strawberry.field
    async def get_macro_indicators(self) -> List[MacroIndicator]:
        """獲取宏觀指標"""
        logger.debug("Query: get_macro_indicators()")
        return []
    
    @strawberry.field
    async def search_news(self, keyword: str, limit: int = 10) -> List[NewsItem]:
        """搜索新聞"""
        logger.debug(f"Query: search_news({keyword}, limit={limit})")
        return []
    
    @strawberry.field
    async def get_portfolio(self) -> List[Portfolio]:
        """獲取投資組合"""
        logger.debug("Query: get_portfolio()")
        return []
    
    @strawberry.field
    async def get_system_health(self) -> SystemHealth:
        """獲取系統健康狀態"""
        logger.debug("Query: get_system_health()")
        return SystemHealth(
            status="ok",
            uptime_seconds=0,
            memory_used_mb=0,
            cache_hit_rate=0,
            active_connections=0,
            pending_tasks=0,
            last_update=datetime.now().isoformat()
        )
    
    @strawberry.field
    async def get_cache_stats(self) -> CacheStats:
        """獲取緩存統計"""
        logger.debug("Query: get_cache_stats()")
        return CacheStats(
            total_keys=0,
            memory_used_mb=0,
            hit_rate=0,
            evicted_items=0,
            connected=False
        )


# ============ 變更解析器 ============

@strawberry.type
class Mutation:
    """GraphQL 變更"""
    
    @strawberry.mutation
    async def clear_cache(self, pattern: str = "*") -> bool:
        """清除緩存"""
        logger.debug(f"Mutation: clear_cache(pattern={pattern})")
        return False
    
    @strawberry.mutation
    async def update_portfolio(
        self,
        ticker: str,
        shares: int,
        cost: float
    ) -> Optional[Portfolio]:
        """更新投資組合"""
        logger.debug(f"Mutation: update_portfolio({ticker}, {shares}, {cost})")
        return None
    
    @strawberry.mutation
    async def cancel_task(self, task_id: str) -> bool:
        """取消任務"""
        logger.debug(f"Mutation: cancel_task({task_id})")
        return False


# ============ 訂閱解析器 ============

@strawberry.type
class Subscription:
    """GraphQL 訂閱"""
    
    @strawberry.subscription
    async def on_price_update(self, ticker: str) -> str:
        """訂閱價格更新"""
        logger.debug(f"Subscription: on_price_update({ticker})")
        yield f"Price update for {ticker}"
    
    @strawberry.subscription
    async def on_analysis_complete(self, ticker: str) -> str:
        """訂閱分析完成"""
        logger.debug(f"Subscription: on_analysis_complete({ticker})")
        yield f"Analysis complete for {ticker}"


# 創建 GraphQL Schema
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription
)


# ============ 解析器實現 ============

class GraphQLResolvers:
    """GraphQL 解析器實現"""
    
    def __init__(self):
        self.async_provider = None
        self.orchestrator = None
        self.redis_cache = None
        self.cache_manager = None
    
    def set_dependencies(self, async_provider, orchestrator, redis_cache, cache_manager):
        """設置依賴注入"""
        self.async_provider = async_provider
        self.orchestrator = orchestrator
        self.redis_cache = redis_cache
        self.cache_manager = cache_manager
    
    async def resolve_get_stock_price(self, ticker: str) -> Optional[StockPrice]:
        """解析: 獲取股票價格"""
        if not self.async_provider:
            return None
        
        try:
            prices = await self.async_provider.get_multiple_prices([ticker])
            if prices:
                price_data = prices.get(ticker)
                if price_data:
                    return StockPrice(
                        ticker=ticker,
                        price=price_data.get('price', 0),
                        change_percent=price_data.get('change_percent', 0),
                        timestamp=datetime.now().isoformat()
                    )
        except Exception as e:
            logger.error(f"解析股票價格失敗: {e}")
        
        return None
    
    async def resolve_analyze_stock(self, ticker: str) -> Optional[StockAnalysis]:
        """解析: 分析股票"""
        if not self.orchestrator:
            return None
        
        try:
            # 檢查快取
            if self.redis_cache:
                cached = await self.redis_cache.get(f"analysis:{ticker}")
                if cached:
                    return StockAnalysis(
                        ticker=ticker,
                        name=cached.get('name', ''),
                        price=cached.get('price', 0),
                        score=cached.get('score', 0),
                        advice=cached.get('advice', ''),
                        signals=cached.get('signals', []),
                        valuation=cached.get('valuation', ''),
                        profit_loss=cached.get('pl', 0),
                        stop_loss=cached.get('sl', 0),
                        exit_strategy=cached.get('exit', ''),
                        confidence=cached.get('confidence', 0),
                        created_at=datetime.now().isoformat(),
                        cached=True
                    )
            
            # 執行分析
            result = await self.orchestrator.analyze_stock(
                ticker=ticker,
                name='',
                indicators={},
                news_content='',
                price=0,
                cost=0
            )
            
            if result.status == "success":
                return StockAnalysis(
                    ticker=ticker,
                    name=result.data.get('name', ''),
                    price=result.data.get('price', 0),
                    score=result.data.get('score', 0),
                    advice=result.data.get('advice', ''),
                    signals=result.data.get('signals', []),
                    valuation=result.data.get('valuation', ''),
                    profit_loss=result.data.get('pl', 0),
                    stop_loss=result.data.get('sl', 0),
                    exit_strategy=result.data.get('exit', ''),
                    confidence=result.confidence,
                    created_at=datetime.now().isoformat()
                )
        except Exception as e:
            logger.error(f"分析股票失敗: {e}")
        
        return None
    
    async def resolve_get_macro_indicators(self) -> List[MacroIndicator]:
        """解析: 獲取宏觀指標"""
        if not self.async_provider:
            return []
        
        try:
            macros = await self.async_provider.get_macro_indices()
            indicators = []
            
            for key, value in macros.items():
                indicators.append(MacroIndicator(
                    name=key,
                    value=float(value.get('price', 0)) if isinstance(value, dict) else float(value),
                    change_percent=float(value.get('change_percent', 0)) if isinstance(value, dict) else 0,
                    description=f"宏觀指標: {key}"
                ))
            
            return indicators
        except Exception as e:
            logger.error(f"獲取宏觀指標失敗: {e}")
            return []
    
    async def resolve_get_system_health(self) -> SystemHealth:
        """解析: 獲取系統健康狀態"""
        # 這應該從實際的系統監控獲取
        return SystemHealth(
            status="ok",
            uptime_seconds=0,
            memory_used_mb=0,
            cache_hit_rate=0,
            active_connections=0,
            pending_tasks=0,
            last_update=datetime.now().isoformat()
        )
    
    async def resolve_clear_cache(self, pattern: str = "*") -> bool:
        """解析: 清除緩存"""
        if not self.redis_cache:
            return False
        
        try:
            keys = await self.redis_cache.get_all_keys(pattern)
            for key in keys:
                await self.redis_cache.delete(key)
            logger.info(f"✓ 已清除 {len(keys)} 項緩存")
            return True
        except Exception as e:
            logger.error(f"清除緩存失敗: {e}")
            return False


# 全局解析器實例
graphql_resolvers = GraphQLResolvers()
