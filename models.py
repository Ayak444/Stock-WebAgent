from pydantic import BaseModel
from typing import List, Optional

class StockTarget:
    def __init__(self, id, name, type, cost, shares):
        self.id = id
        self.name = name
        self.type = type
        self.cost = cost
        self.shares = shares

# ========== API Request Models ==========
class TargetItem(BaseModel):
    id: str
    name: str
    type: str = "STOCK"
    cost: float = 0
    shares: int = 0

class AnalyzeRequest(BaseModel):
    targets: List[TargetItem]

class NewsRequest(BaseModel):
    news_content: str

class ChatRequest(BaseModel):
    message: str

class BacktestRequest(BaseModel):
    ticker: str
    name: Optional[str] = ""
    days: int = 365
