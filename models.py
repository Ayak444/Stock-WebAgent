"""資料模型定義"""
from dataclasses import dataclass
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


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
    cost: float = Field(ge=0)
    shares: int = Field(ge=0)


class AnalyzeRequest(BaseModel):
    targets: List[TargetItem]


class ChatRequest(BaseModel):
    message: str


class NewsRequest(BaseModel):
    news_content: str


class BacktestRequest(BaseModel):
    ticker: str
    days: int = Field(default=180, ge=30, le=3650)


class NewsSourceRequest(BaseModel):
    sources: Optional[List[str]] = None  # ['bloomberg', 'investing', 'ctee', 'udn']
    limit: int = Field(default=10, ge=1, le=20)


class ScreenerAnalyzeRequest(BaseModel):
    user_id: Optional[str] = None
    source: str = "manual"  # manual | portfolio
    targets: Optional[List[str]] = None
    filters: Optional[List[str]] = None
    
class SyncPortfolioRequest(BaseModel):
    user_id: str
    portfolio: List[dict] = Field(default_factory=list)

class StressTestRecordRequest(BaseModel):
    user_id: str = "default_user"
    scenario: str = "常規測試"
    result: dict = Field(default_factory=dict)

class TradeRequest(BaseModel):
    user_id: str
    action: Literal["買入", "賣出"]
    ticker: str
    amount: float = Field(gt=0)
    price: float = Field(gt=0)

class AuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)
    name: Optional[str] = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("請輸入有效的電子郵件")
        return value

class Recommendation(BaseModel):
    name: str
    code: str
    reason: str

class NewsDigest(BaseModel):
    title: str
    sentiment: str 
    summary: str 

class SentimentResponse(BaseModel):
    score: int
    label: str
    definition: str
    reasoning: str
    recommendations: List[Recommendation]
    news_analysis: List[NewsDigest]
