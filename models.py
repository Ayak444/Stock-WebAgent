"""資料模型定義"""
from dataclasses import dataclass
from typing import List, Optional
from pydantic import BaseModel

#
@dataclass
class StockTarget:
    id: str
    name: str
    type: str
    cost: float
    shares: int


# ========== API Request Models ==========
class TargetItem(BaseModel):
    id: str
    name: str
    type: str
    cost: float
    shares: int


class AnalyzeRequest(BaseModel):
    targets: List[TargetItem]


class ChatRequest(BaseModel):
    message: str


class NewsRequest(BaseModel):
    news_content: str


class BacktestRequest(BaseModel):
    ticker: str
    days: int = 180


class NewsSourceRequest(BaseModel):
    sources: Optional[List[str]] = None  # ['bloomberg', 'investing', 'ctee', 'udn']
    limit: int = 10
