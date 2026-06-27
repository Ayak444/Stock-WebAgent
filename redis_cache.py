"""
Redis 分布式緩存層
支持多實例部署和分布式訪問
"""

import json
import logging
import asyncio
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta
import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

logger = logging.getLogger(__name__)

class RedisCache:
    """Redis 分布式緩存實現"""
    
    def __init__(self, host: str = 'localhost', port: int = 6379, db: int = 0, 
                 password: Optional[str] = None, max_connections: int = 50):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.max_connections = max_connections
        self.redis_client: Optional[redis.Redis] = None
        self.connection_pool: Optional[ConnectionPool] = None
        
    async def connect(self) -> None:
        """連接到 Redis"""
        try:
            self.connection_pool = ConnectionPool.from_url(
                f"redis://:{self.password}@{self.host}:{self.port}/{self.db}" 
                if self.password 
                else f"redis://{self.host}:{self.port}/{self.db}",
                max_connections=self.max_connections,
                decode_responses=True
            )
            self.redis_client = redis.Redis(connection_pool=self.connection_pool)
            
            # 測試連接
            await self.redis_client.ping()
            logger.info(f"✓ Redis 已連接 ({self.host}:{self.port})")
        except Exception as e:
            logger.error(f"✗ Redis 連接失敗: {e}")
            raise
    
    async def disconnect(self) -> None:
        """斷開 Redis 連接"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("✓ Redis 已斷開")
    
    async def get(self, key: str) -> Optional[Any]:
        """獲取值"""
        if not self.redis_client:
            return None
        
        try:
            value = await self.redis_client.get(key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            logger.warning(f"Redis GET 失敗 ({key}): {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """設置值"""
        if not self.redis_client:
            return False
        
        try:
            # 將值序列化為 JSON
            json_value = json.dumps(value, default=str) if not isinstance(value, str) else value
            
            if ttl:
                await self.redis_client.setex(key, ttl, json_value)
            else:
                await self.redis_client.set(key, json_value)
            return True
        except Exception as e:
            logger.warning(f"Redis SET 失敗 ({key}): {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """刪除值"""
        if not self.redis_client:
            return False
        
        try:
            result = await self.redis_client.delete(key)
            return result > 0
        except Exception as e:
            logger.warning(f"Redis DELETE 失敗 ({key}): {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """檢查鍵是否存在"""
        if not self.redis_client:
            return False
        
        try:
            result = await self.redis_client.exists(key)
            return result > 0
        except Exception as e:
            logger.warning(f"Redis EXISTS 失敗 ({key}): {e}")
            return False
    
    async def increment(self, key: str, delta: int = 1) -> int:
        """增加計數器"""
        if not self.redis_client:
            return 0
        
        try:
            result = await self.redis_client.incrby(key, delta)
            return result
        except Exception as e:
            logger.warning(f"Redis INCR 失敗 ({key}): {e}")
            return 0
    
    async def get_all_keys(self, pattern: str = "*") -> List[str]:
        """獲取所有符合模式的鍵"""
        if not self.redis_client:
            return []
        
        try:
            keys = await self.redis_client.keys(pattern)
            return keys
        except Exception as e:
            logger.warning(f"Redis KEYS 失敗: {e}")
            return []
    
    async def flush_db(self) -> bool:
        """清空當前數據庫"""
        if not self.redis_client:
            return False
        
        try:
            await self.redis_client.flushdb()
            logger.info("✓ Redis 數據庫已清空")
            return True
        except Exception as e:
            logger.warning(f"Redis FLUSHDB 失敗: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """獲取緩存統計信息"""
        if not self.redis_client:
            return {}
        
        try:
            info = await self.redis_client.info()
            db_keys = await self.redis_client.dbsize()
            
            return {
                'connected': True,
                'total_keys': db_keys,
                'memory_used_mb': info.get('used_memory', 0) / 1024 / 1024,
                'connected_clients': info.get('connected_clients', 0),
                'commands_per_sec': info.get('instantaneous_ops_per_sec', 0),
                'evicted_keys': info.get('evicted_keys', 0),
                'hits': info.get('keyspace_hits', 0),
                'misses': info.get('keyspace_misses', 0),
            }
        except Exception as e:
            logger.warning(f"Redis 統計獲取失敗: {e}")
            return {}


class DistributedCacheManager:
    """分布式緩存管理器"""
    
    def __init__(self, redis_cache: Optional[RedisCache] = None):
        self.redis = redis_cache
        self.prefix = "stock_"
    
    async def set_kline(self, ticker: str, days: int, data: Any, ttl: int = 86400) -> bool:
        """存儲 K 線數據"""
        if not self.redis:
            return False
        
        key = f"{self.prefix}kline:{ticker}:{days}"
        return await self.redis.set(key, data, ttl)
    
    async def get_kline(self, ticker: str, days: int) -> Optional[Any]:
        """獲取 K 線數據"""
        if not self.redis:
            return None
        
        key = f"{self.prefix}kline:{ticker}:{days}"
        return await self.redis.get(key)
    
    async def set_sentiment(self, ticker: str, sentiment: Dict, ttl: int = 3600) -> bool:
        """存儲情緒分析結果"""
        if not self.redis:
            return False
        
        key = f"{self.prefix}sentiment:{ticker}"
        return await self.redis.set(key, sentiment, ttl)
    
    async def get_sentiment(self, ticker: str) -> Optional[Dict]:
        """獲取情緒分析結果"""
        if not self.redis:
            return None
        
        key = f"{self.prefix}sentiment:{ticker}"
        return await self.redis.get(key)
    
    async def set_analysis(self, ticker: str, analysis: Dict, ttl: int = 1800) -> bool:
        """存儲分析結果"""
        if not self.redis:
            return False
        
        key = f"{self.prefix}analysis:{ticker}"
        return await self.redis.set(key, analysis, ttl)
    
    async def get_analysis(self, ticker: str) -> Optional[Dict]:
        """獲取分析結果"""
        if not self.redis:
            return None
        
        key = f"{self.prefix}analysis:{ticker}"
        return await self.redis.get(key)
    
    async def increment_request_count(self, ticker: str) -> int:
        """增加請求計數"""
        if not self.redis:
            return 0
        
        key = f"{self.prefix}requests:{ticker}"
        return await self.redis.increment(key)
    
    async def clear_ticker_cache(self, ticker: str) -> bool:
        """清除特定股票的所有緩存"""
        if not self.redis:
            return False
        
        pattern = f"{self.prefix}*:{ticker}*"
        keys = await self.redis.get_all_keys(pattern)
        
        for key in keys:
            await self.redis.delete(key)
        
        logger.info(f"✓ 已清除 {ticker} 的 {len(keys)} 項緩存")
        return True


# 全局 Redis 實例
redis_cache: Optional[RedisCache] = None
distributed_cache_manager: Optional[DistributedCacheManager] = None


async def initialize_redis_cache(
    host: str = 'localhost',
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None,
    max_connections: int = 50
) -> bool:
    """初始化 Redis 緩存"""
    global redis_cache, distributed_cache_manager
    
    try:
        redis_cache = RedisCache(
            host=host,
            port=port,
            db=db,
            password=password,
            max_connections=max_connections
        )
        await redis_cache.connect()
        distributed_cache_manager = DistributedCacheManager(redis_cache)
        return True
    except Exception as e:
        logger.error(f"Redis 初始化失敗: {e}")
        return False


async def shutdown_redis_cache() -> None:
    """關閉 Redis 連接"""
    global redis_cache
    if redis_cache:
        await redis_cache.disconnect()


async def get_redis_cache() -> Optional[RedisCache]:
    """獲取 Redis 實例"""
    return redis_cache


async def get_distributed_cache_manager() -> Optional[DistributedCacheManager]:
    """獲取分布式緩存管理器"""
    return distributed_cache_manager
