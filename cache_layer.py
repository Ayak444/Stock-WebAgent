"""
高效能緩存系統
支持內存緩存 + 可選的 Redis 後端
用於存儲：歷史 K 線、技術指標、新聞數據、情緒分析結果
"""
import json
import hashlib
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List
import threading
import weakref


class CacheEntry:
    """單筆緩存項"""
    def __init__(self, value: Any, ttl_seconds: int = 3600):
        self.value = value
        self.created_at = datetime.now()
        self.ttl_seconds = ttl_seconds
    
    def is_expired(self) -> bool:
        age = (datetime.now() - self.created_at).total_seconds()
        return age > self.ttl_seconds


class MemoryCache:
    """
    基于 Python dict 的內存緩存
    線程安全，支持過期時間管理
    """
    def __init__(self, max_size: int = 10000):
        self.store: Dict[str, CacheEntry] = {}
        self.max_size = max_size
        self.lock = threading.RLock()
        self.access_count = {}  # LRU 計數
        self.finalizers = weakref.WeakKeyDictionary()
    
    def get(self, key: str) -> Optional[Any]:
        """取得緩存，自動過期檢查"""
        with self.lock:
            if key not in self.store:
                return None
            
            entry = self.store[key]
            if entry.is_expired():
                del self.store[key]
                return None
            
            # 更新 LRU 計數
            self.access_count[key] = self.access_count.get(key, 0) + 1
            return entry.value
    
    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """設置緩存"""
        with self.lock:
            # 檢查是否超過容量
            if len(self.store) >= self.max_size and key not in self.store:
                self._evict_lru()
            
            self.store[key] = CacheEntry(value, ttl_seconds)
            self.access_count[key] = 0
    
    def delete(self, key: str) -> None:
        """刪除緩存"""
        with self.lock:
            if key in self.store:
                del self.store[key]
            if key in self.access_count:
                del self.access_count[key]
    
    def clear(self) -> None:
        """清空所有緩存"""
        with self.lock:
            self.store.clear()
            self.access_count.clear()
    
    def _evict_lru(self) -> None:
        """驅逐最少使用項"""
        if not self.store:
            return
        
        # 找出訪問次數最少的 key
        lru_key = min(self.access_count.keys(), 
                     key=lambda k: self.access_count.get(k, 0))
        if lru_key in self.store:
            del self.store[lru_key]
        if lru_key in self.access_count:
            del self.access_count[lru_key]
    
    def cleanup_expired(self) -> int:
        """清理過期項，返回清理數量"""
        with self.lock:
            expired_keys = [k for k, v in self.store.items() if v.is_expired()]
            for k in expired_keys:
                del self.store[k]
                if k in self.access_count:
                    del self.access_count[k]
            return len(expired_keys)


class CacheManager:
    """
    統一的緩存管理介面
    自動分類存儲不同類型的數據
    """
    def __init__(self):
        self.memory_cache = MemoryCache(max_size=10000)
        
        # 緩存分類
        self.kline_cache = {}       # K 線數據
        self.indicators_cache = {}  # 技術指標
        self.news_cache = {}        # 新聞數據
        self.sentiment_cache = {}   # 情緒分析結果
        self.analysis_cache = {}    # 完整分析結果
    
    def get_kline_key(self, ticker: str, days: int) -> str:
        """生成 K 線緩存 key"""
        return f"kline:{ticker}:{days}"
    
    def get_indicators_key(self, ticker: str) -> str:
        """生成技術指標緩存 key"""
        return f"indicators:{ticker}"
    
    def get_news_key(self, source: str, limit: int) -> str:
        """生成新聞緩存 key"""
        return f"news:{source}:{limit}"
    
    def get_sentiment_key(self, ticker: str) -> str:
        """生成情緒分析緩存 key"""
        return f"sentiment:{ticker}"
    
    def get_analysis_key(self, ticker: str, cost: float = 0) -> str:
        """生成分析結果緩存 key"""
        cost_hash = hashlib.md5(str(cost).encode()).hexdigest()[:8]
        return f"analysis:{ticker}:{cost_hash}"
    
    # ===== K 線數據緩存 =====
    def get_kline(self, ticker: str, days: int):
        """取得 K 線數據"""
        key = self.get_kline_key(ticker, days)
        return self.memory_cache.get(key)
    
    def set_kline(self, ticker: str, days: int, df, ttl: int = 86400):
        """
        存儲 K 線數據
        ttl 默認 24 小時（歷史數據不變）
        """
        key = self.get_kline_key(ticker, days)
        # 轉換 DataFrame 為可序列化格式，確保保留 Date 索引
        if hasattr(df, 'reset_index'):
            temp_df = df.copy()
            if temp_df.index.name is None:
                temp_df.index.name = 'Date'
            df_dict = temp_df.reset_index().to_dict('records')
        else:
            df_dict = df
            
        self.memory_cache.set(key, df_dict, ttl)
    
    # ===== 技術指標緩存 =====
    def get_indicators(self, ticker: str):
        """取得技術指標"""
        key = self.get_indicators_key(ticker)
        return self.memory_cache.get(key)
    
    def set_indicators(self, ticker: str, indicators: Dict, ttl: int = 3600):
        """
        存儲技術指標
        ttl 默認 1 小時（市場開盤時會頻繁更新）
        """
        key = self.get_indicators_key(ticker)
        self.memory_cache.set(key, indicators, ttl)
    
    # ===== 新聞數據緩存 =====
    def get_news(self, source: str, limit: int):
        """取得新聞列表"""
        key = self.get_news_key(source, limit)
        return self.memory_cache.get(key)
    
    def set_news(self, source: str, limit: int, news_list: List, ttl: int = 1800):
        """
        存儲新聞數據
        ttl 默認 30 分鐘
        """
        key = self.get_news_key(source, limit)
        self.memory_cache.set(key, news_list, ttl)
    
    # ===== 情緒分析結果緩存 =====
    def get_sentiment(self, ticker: str):
        """取得情緒分析結果"""
        key = self.get_sentiment_key(ticker)
        return self.memory_cache.get(key)
    
    def set_sentiment(self, ticker: str, sentiment_data: Dict, ttl: int = 3600):
        """
        存儲情緒分析結果
        ttl 默認 1 小時
        """
        key = self.get_sentiment_key(ticker)
        self.memory_cache.set(key, sentiment_data, ttl)
    
    # ===== 完整分析結果緩存 =====
    def get_analysis(self, ticker: str, cost: float = 0):
        """取得完整分析結果"""
        key = self.get_analysis_key(ticker, cost)
        return self.memory_cache.get(key)
    
    def set_analysis(self, ticker: str, analysis_data: Dict, cost: float = 0, 
                     ttl: int = 1800):
        """
        存儲完整分析結果
        ttl 默認 30 分鐘
        """
        key = self.get_analysis_key(ticker, cost)
        self.memory_cache.set(key, analysis_data, ttl)
    
    # ===== 管理操作 =====
    def invalidate_ticker(self, ticker: str) -> int:
        """清空某支股票的所有緩存"""
        keys_to_delete = []
        for key in self.memory_cache.store.keys():
            if ticker in key:
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            self.memory_cache.delete(key)
        
        return len(keys_to_delete)
    
    def get_stats(self) -> Dict:
        """取得緩存統計信息"""
        return {
            "total_items": len(self.memory_cache.store),
            "max_size": self.memory_cache.max_size,
            "usage_percent": (len(self.memory_cache.store) / self.memory_cache.max_size * 100)
                            if self.memory_cache.max_size > 0 else 0,
            "expired_count": sum(1 for v in self.memory_cache.store.values() if v.is_expired())
        }
    
    def cleanup_expired(self) -> int:
        """清理所有過期項"""
        return self.memory_cache.cleanup_expired()


# 全局緩存實例
cache_manager = CacheManager()
