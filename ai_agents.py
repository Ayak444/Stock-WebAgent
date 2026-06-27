"""
多代理 AI 決策系統
分離職責：新聞情緒分析 → 技術指標評估 → 高管決策
提升精準度，降低 AI 幻覺風險
"""
import os
import json
import re
import asyncio
from typing import Dict, List, Optional
import requests as http_requests
from dataclasses import dataclass
from cache_layer import cache_manager


@dataclass
class AgentResponse:
    """代理回應結構"""
    status: str  # success | error
    data: Dict
    confidence: float = 0.5
    error_msg: Optional[str] = None


class GroqAPIClient:
    """Groq API 統一客戶端"""
    def __init__(self):
        self.api_key = os.environ.get("MAIAGENT_API_KEY", "")
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.enabled = bool(self.api_key)
    
    async def call(self, system_prompt: str, user_message: str, 
                   temperature: float = 0.1, timeout: int = 45) -> str:
        """
        異步調用 Groq API
        """
        if not self.enabled:
            return ""
        
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": temperature,
            "top_p": 0.9,
            "max_tokens": 2048
        }
        
        try:
            # 在線程池中運行同步 HTTP 請求
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: http_requests.post(
                    self.base_url,
                    headers=self.headers,
                    json=payload,
                    timeout=timeout
                )
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            raise Exception(f"Groq API 調用失敗: {str(e)}")


class NewsAnalysisAgent:
    """
    新聞情緒分析代理
    職責：爬取新聞 → 情緒分析 → 生成推薦
    """
    def __init__(self):
        self.client = GroqAPIClient()
        self.cache_ttl = 3600  # 1 小時
    
    async def analyze_news(self, ticker: str, news_content: str) -> AgentResponse:
        """分析新聞情緒"""
        # 檢查緩存
        cached = cache_manager.get_sentiment(ticker)
        if cached:
            return AgentResponse(status="success", data=cached, confidence=0.95)
        
        if not self.client.enabled:
            return AgentResponse(
                status="error",
                data={},
                confidence=0.0,
                error_msg="AI API 未配置"
            )
        
        system_prompt = (
            "你是資深的台股宏觀分析師，專精新聞情緒分析。\n"
            "請分析新聞並回傳 JSON 格式結果。\n"
            "必須回傳的欄位：score (0-100), label (情感標籤), reasoning (詳細解釋), "
            "recommendations (推薦清單), news_analysis (新聞摘要)。\n"
            "只回傳合法 JSON，不要有任何 Markdown 標記或廢話。"
        )
        
        try:
            response_text = await self.client.call(
                system_prompt,
                f"新聞內容：\n{news_content}",
                temperature=0.1
            )
            
            # 清理 Markdown 標記
            json_str = self._extract_json(response_text)
            result = json.loads(json_str, strict=False)
            
            # 標準化格式
            standardized = self._standardize_sentiment(result)
            
            # 存入緩存
            cache_manager.set_sentiment(ticker, standardized, self.cache_ttl)
            
            return AgentResponse(
                status="success",
                data=standardized,
                confidence=0.85
            )
        except Exception as e:
            return AgentResponse(
                status="error",
                data={},
                confidence=0.0,
                error_msg=f"情緒分析失敗: {str(e)}"
            )
    
    @staticmethod
    def _extract_json(text: str) -> str:
        """從文本中提取 JSON"""
        text = re.sub(r'```json\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'```\s*', '', text)
        
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return text[start_idx:end_idx+1]
        return text
    
    @staticmethod
    def _standardize_sentiment(data: dict) -> dict:
        """標準化情緒分析結果"""
        score = int(data.get("score", 50))
        
        # 生成情感標籤
        if score >= 70:
            label, definition = "極度貪婪", "市場過熱，建議分批獲利"
        elif score >= 55:
            label, definition = "樂觀", "買盤積極，注意追高風險"
        elif score >= 45:
            label, definition = "中立", "多空平衡，建議持有績優股"
        else:
            label, definition = "恐懼", "市場低迷，可尋找低估標的"
        
        recommendations = []
        for r in data.get("recommendations", []):
            if isinstance(r, dict):
                recommendations.append({
                    "name": str(r.get("name", "未知")),
                    "code": str(r.get("code", "N/A")),
                    "reason": str(r.get("reason", ""))
                })
        
        news_analysis = []
        for n in data.get("news_analysis", []):
            if isinstance(n, dict):
                news_analysis.append({
                    "title": str(n.get("title", "")),
                    "sentiment": str(n.get("sentiment", "中立")),
                    "summary": str(n.get("summary", ""))
                })
        
        return {
            "score": score,
            "label": label,
            "definition": definition,
            "reasoning": str(data.get("reasoning", "")),
            "recommendations": recommendations,
            "news_analysis": news_analysis
        }


class TechnicalAnalysisAgent:
    """
    技術分析與風險評估代理
    職責：計算技術指標 → 評估風險 → 生成信號
    """
    def __init__(self):
        self.client = GroqAPIClient()
    
    async def evaluate_technical(self, ticker: str, indicators: dict, 
                                 price: float, cost: float = 0) -> AgentResponse:
        """
        綜合技術指標評估
        """
        if not self.client.enabled:
            # 回退到本地邏輯評估
            return self._local_technical_evaluation(indicators, price, cost)
        
        system_prompt = (
            "你是資深的技術分析師，精通台股交易。\n"
            "請基於提供的技術指標，評估買賣信號。\n"
            "回傳 JSON：risk_level (low|medium|high), entry_signal (buy|sell|hold), "
            "confidence (0-100), signals (清單), recommendation (建議)。"
        )
        
        indicators_text = json.dumps(indicators, ensure_ascii=False, indent=2)
        
        try:
            response_text = await self.client.call(
                system_prompt,
                f"股票代號：{ticker}\n現價：{price}\n成本：{cost}\n"
                f"技術指標：\n{indicators_text}",
                temperature=0.2
            )
            
            json_str = NewsAnalysisAgent._extract_json(response_text)
            result = json.loads(json_str, strict=False)
            
            return AgentResponse(
                status="success",
                data={
                    "risk_level": result.get("risk_level", "medium"),
                    "entry_signal": result.get("entry_signal", "hold"),
                    "confidence": int(result.get("confidence", 50)),
                    "signals": result.get("signals", []),
                    "recommendation": str(result.get("recommendation", ""))
                },
                confidence=0.80
            )
        except Exception as e:
            return AgentResponse(
                status="error",
                data={},
                confidence=0.0,
                error_msg=f"技術分析失敗: {str(e)}"
            )
    
    @staticmethod
    def _local_technical_evaluation(indicators: dict, price: float, 
                                    cost: float = 0) -> AgentResponse:
        """本地邏輯評估（無 AI）"""
        score = 50
        rsi = indicators.get('RSI', 50)
        macd = indicators.get('MACD', 0)
        signal = indicators.get('Signal', 0)
        ma20 = indicators.get('MA20', price)
        
        # 評分邏輯
        if price > ma20:
            score += 10
        if rsi > 70:
            score -= 15
        elif rsi < 30:
            score += 15
        if macd > signal:
            score += 10
        
        # 風險評估
        if rsi > 75 or rsi < 25:
            risk_level = "high"
        elif rsi > 70 or rsi < 30:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        # 信號判斷
        if score >= 65:
            entry_signal = "buy"
        elif score <= 35:
            entry_signal = "sell"
        else:
            entry_signal = "hold"
        
        return AgentResponse(
            status="success",
            data={
                "risk_level": risk_level,
                "entry_signal": entry_signal,
                "confidence": min(score, 100),
                "signals": [
                    f"RSI: {rsi:.1f}",
                    f"MACD: {macd:.4f}",
                    f"Price vs MA20: {price/ma20*100-100:+.1f}%"
                ],
                "recommendation": f"綜合評分：{score}/100"
            },
            confidence=0.75
        )


class ExecutiveDecisionAgent:
    """
    高管決策代理
    職責：統整所有分析 → 生成最終建議 → 風險提醒
    """
    def __init__(self):
        self.client = GroqAPIClient()
    
    async def make_final_decision(self, ticker: str, name: str,
                                  news_analysis: AgentResponse,
                                  tech_analysis: AgentResponse,
                                  price: float, cost: float = 0) -> AgentResponse:
        """
        整合所有分析，生成最終決策
        """
        if not self.client.enabled:
            return self._local_final_decision(ticker, news_analysis, tech_analysis)
        
        system_prompt = (
            "你是基金經理人，需要基於下述多個分析結果，做出最終投資決策。\n"
            "回傳 JSON：final_advice (強力買進|偏多|觀察|偏空|強力賣出), "
            "score (0-100), reasoning (詳細邏輯), risk_warnings (風險清單)。"
        )
        
        news_data = news_analysis.data if news_analysis.status == "success" else {}
        tech_data = tech_analysis.data if tech_analysis.status == "success" else {}
        
        prompt = (
            f"股票：{ticker} {name}\n"
            f"現價：{price}，成本：{cost}\n"
            f"新聞情緒分析：{json.dumps(news_data, ensure_ascii=False)}\n"
            f"技術面評估：{json.dumps(tech_data, ensure_ascii=False)}\n"
            f"請統整以上信息並給出最終建議。"
        )
        
        try:
            response_text = await self.client.call(
                system_prompt,
                prompt,
                temperature=0.2
            )
            
            json_str = NewsAnalysisAgent._extract_json(response_text)
            result = json.loads(json_str, strict=False)
            
            return AgentResponse(
                status="success",
                data={
                    "final_advice": result.get("final_advice", "觀察"),
                    "score": int(result.get("score", 50)),
                    "reasoning": str(result.get("reasoning", "")),
                    "risk_warnings": result.get("risk_warnings", []),
                    "news_sentiment": news_data.get("label", "中立"),
                    "tech_signal": tech_data.get("entry_signal", "hold"),
                    "combined_confidence": (news_analysis.confidence + tech_analysis.confidence) / 2
                },
                confidence=0.90
            )
        except Exception as e:
            return AgentResponse(
                status="error",
                data={},
                confidence=0.0,
                error_msg=f"決策生成失敗: {str(e)}"
            )
    
    @staticmethod
    def _local_final_decision(ticker: str, news_analysis: AgentResponse,
                             tech_analysis: AgentResponse) -> AgentResponse:
        """本地邏輯決策（無 AI）"""
        news_score = news_analysis.data.get("score", 50) if news_analysis.status == "success" else 50
        tech_signal = tech_analysis.data.get("entry_signal", "hold") if tech_analysis.status == "success" else "hold"
        
        # 結合新聞與技術面
        combined_score = (news_score + 50) / 2 if tech_signal == "hold" else news_score
        
        if combined_score >= 75:
            advice = "強力買進"
        elif combined_score >= 60:
            advice = "偏多"
        elif combined_score >= 40:
            advice = "觀察"
        elif combined_score >= 25:
            advice = "偏空"
        else:
            advice = "強力賣出"
        
        return AgentResponse(
            status="success",
            data={
                "final_advice": advice,
                "score": int(combined_score),
                "reasoning": f"新聞情緒 ({news_score:.0f}) 與技術面 ({tech_signal}) 綜合評估",
                "risk_warnings": ["無 AI 支持時使用本地邏輯"],
                "news_sentiment": news_analysis.data.get("label", "中立"),
                "tech_signal": tech_signal,
                "combined_confidence": 0.70
            },
            confidence=0.75
        )


class MultiAgentOrchestrator:
    """
    多代理協調器
    負責組調各個專職代理完成複雜分析任務
    """
    def __init__(self):
        self.news_agent = NewsAnalysisAgent()
        self.tech_agent = TechnicalAnalysisAgent()
        self.exec_agent = ExecutiveDecisionAgent()
    
    async def analyze_stock(self, ticker: str, name: str, indicators: dict,
                           news_content: str, price: float, cost: float = 0) -> dict:
        """
        完整股票分析工作流
        返回統合的分析結果
        """
        # 並行執行第一層分析（新聞 + 技術）
        news_task = self.news_agent.analyze_news(ticker, news_content)
        tech_task = self.tech_agent.evaluate_technical(ticker, indicators, price, cost)
        
        news_result, tech_result = await asyncio.gather(news_task, tech_task)
        
        # 第二層：高管決策
        final_result = await self.exec_agent.make_final_decision(
            ticker, name, news_result, tech_result, price, cost
        )
        
        return {
            "ticker": ticker,
            "name": name,
            "price": price,
            "news_analysis": news_result.data,
            "technical_analysis": tech_result.data,
            "final_decision": final_result.data,
            "overall_confidence": (news_result.confidence + tech_result.confidence + final_result.confidence) / 3,
            "timestamp": str(__import__('datetime').datetime.now())
        }


# 全局代理協調器實例
orchestrator = MultiAgentOrchestrator()
