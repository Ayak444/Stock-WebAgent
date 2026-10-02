"""資料模型定義"""
from dataclasses import dataclass
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator
from decimal import Decimal
import re


@dataclass
class StockTarget:
    id: str
    name: str
    type: str
    cost: float
    shares: int


# ========== API Request Models ==========
class TargetItem(BaseModel):
    id: str = Field(pattern=r'^[A-Za-z0-9.^=\-]{1,24}$')
    name: str
    type: str
    cost: float = Field(ge=0)
    shares: int = Field(ge=0)


class AnalyzeRequest(BaseModel):
    targets: List[TargetItem] = Field(min_length=1, max_length=20)
    mode: Literal["quick", "deep"] = "quick"


class ChatRequest(BaseModel):
    message: str


class NewsRequest(BaseModel):
    news_content: str


class BacktestRequest(BaseModel):
    ticker: str
    days: int = 180
    commission_rate: float = Field(default=0.001425, ge=0, lt=1)
    min_commission: float = Field(default=20, ge=0, le=100000)
    sell_tax_rate: float = Field(default=0.003, ge=0, lt=1)


class NewsSourceRequest(BaseModel):
    sources: Optional[List[str]] = None  # ['bloomberg', 'investing', 'ctee', 'udn']
    limit: int = Field(default=10, ge=1, le=20)


class ScreenerAnalyzeRequest(BaseModel):
    user_id: Optional[str] = None
    source: str = "manual"  # manual | portfolio
    targets: Optional[List[str]] = None
    filters: Optional[List[str]] = None
    
class SyncPortfolioRequest(BaseModel):
    user_id: Optional[str] = None  # Legacy clients may send it; server owns identity.
    portfolio: List["PortfolioItem"] = Field(default_factory=list, max_length=100)


class PortfolioItem(BaseModel):
    code: str
    type: Literal["台股", "ETF"]
    cost: Decimal = Field(ge=0, le=1000000000, allow_inf_nan=False, max_digits=18, decimal_places=6)
    shares: Decimal = Field(ge=0, le=1000000000, allow_inf_nan=False, max_digits=18, decimal_places=6)

    @field_validator("code")
    @classmethod
    def ticker(cls, value):
        value = value.strip().upper()
        if re.fullmatch(r"[0-9][0-9A-Z]{3,9}", value):
            value += ".TW"
        if not re.fullmatch(r"[0-9][0-9A-Z]{3,9}\.(TW|TWO)", value):
            raise ValueError("請輸入台股股票代號，例如 2330.TW")
        return value

SyncPortfolioRequest.model_rebuild()

class StressTestRecordRequest(BaseModel):
    user_id: Optional[str] = None
    scenario: str = Field(default="常規測試", max_length=200)
    result: dict = Field(default_factory=dict)

class TradeRequest(BaseModel):
    user_id: Optional[str] = None
    action: Literal["買入", "賣出"]
    ticker: str
    amount: Decimal = Field(gt=0, le=1000000000, allow_inf_nan=False, max_digits=18, decimal_places=6)
    price: Decimal = Field(gt=0, le=1000000000, allow_inf_nan=False, max_digits=18, decimal_places=6)

    @field_validator("ticker")
    @classmethod
    def supported_ticker(cls, value):
        return PortfolioItem.ticker(value)

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
