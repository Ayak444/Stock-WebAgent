import os
import asyncio
from typing import Dict, Any
from crewai import Agent, Task, Crew, Process
from langchain_groq import ChatGroq

class StockCrewOrchestrator:
    """
    基於 CrewAI 的多代理台股分析協調器
    """
    def __init__(self):
        self.api_key = os.environ.get("MAIAGENT_API_KEY", "")
        
        # 為了避免 API Key 不存在時報錯，只有在啟用時才實例化 LLM
        self.enabled = bool(self.api_key)
        self.llm = None
        
        if self.enabled:
            # 使用 LangChain Groq 整合包
            self.llm = ChatGroq(
                api_key=self.api_key,
                model_name="llama-3.3-70b-versatile",
                temperature=0.1
            )

    def _create_agents(self) -> Dict[str, Agent]:
        """建立團隊成員 (Agents)"""
        
        news_analyst = Agent(
            role="資深台股宏觀分析師",
            goal="分析個股相關新聞的情緒，評估市場心理與多空抵銷邏輯",
            backstory="你擁有超過20年的台股市場分析經驗，擅長從紛雜的財經新聞中解讀散戶心理與主力動向，能給出精確的情緒評分。",
            verbose=True,
            allow_delegation=False,
            llm=self.llm
        )

        technical_analyst = Agent(
            role="資深技術分析師",
            goal="基於量化技術指標評估買賣信號與短線交易動能",
            backstory="你是一位純粹的量化交易員，只相信數據與指標。精通均線黃金交叉、RSI超買超賣以及MACD柱狀體變化，擅長捕捉市場轉折點。",
            verbose=True,
            allow_delegation=False,
            llm=self.llm
        )

        fund_manager = Agent(
            role="投資組合基金經理人",
            goal="整合情緒面與技術面分析，做出初步投資決策",
            backstory="你是團隊的最高決策者，負責控管整體風險。你需要平衡宏觀情緒與微觀技術指標，給出強力買進、偏多、觀察、偏空或強力賣出的初步操作建議，並制定停損策略。",
            verbose=True,
            allow_delegation=True,
            llm=self.llm
        )

        qa_error_reporter = Agent(
            role="系統風控與回報檢測員 (QA)",
            goal="檢測前置作業是否有誤，修復 JSON 格式與邏輯錯誤，產出最終穩定的 JSON 報告，並提供異常回報",
            backstory="你是團隊中的守門員，負責防範 AI 幻覺與資料格式崩潰。你非常擅長 JSON 格式的校對，能確保投資建議合乎邏輯，並且能抓出任何異常的數據點並進行回報。如果發現前面的決策有重大邏輯漏洞，你會自動修復它。",
            verbose=True,
            allow_delegation=False,
            llm=self.llm
        )

        return {
            "news_analyst": news_analyst,
            "technical_analyst": technical_analyst,
            "fund_manager": fund_manager,
            "qa_error_reporter": qa_error_reporter
        }

    def _run_crew_sync(self, ticker: str, name: str, price: float, cost: float, news_content: str, indicators: dict) -> str:
        """同步執行 CrewAI 流程 (給 asyncio.to_thread 呼叫)"""
        agents = self._create_agents()

        task_news = Task(
            description=f"分析股票 {ticker} {name} 的以下新聞內容：\n{news_content}\n評估綜合市場情緒，分析利多與利空因素。",
            expected_output="一份包含情緒得分（0-100）及詳細市場心理分析的文字報告。",
            agent=agents["news_analyst"]
        )

        task_tech = Task(
            description=f"評估股票 {ticker} {name} 現價 {price}（成本 {cost}）的量化指標：\n{indicators}\n分析當前趨勢、買賣動能與潛在支撐壓力位。",
            expected_output="一份包含技術指標解讀、風險評級與具體交易信號的量化評估報告。",
            agent=agents["technical_analyst"]
        )

        task_decision = Task(
            description=f"整合上述情緒分析與技術面報告。針對 {ticker} {name} 進行決策評估，並寫出詳細原因。",
            expected_output="一份完整的決策報告，包含推薦方向與風險警告。",
            agent=agents["fund_manager"],
            context=[task_news, task_tech]
        )

        task_qa = Task(
            description=(
                f"審查基金經理人的決策報告。檢測邏輯是否矛盾，並嚴格轉換為最終的 JSON 格式。\n"
                f"你必須確保產出的『僅有』 JSON 格式字串，不要加上 ```json 標記，也不要有其他廢話。\n"
                f"必要欄位：final_advice (限：強力買進|偏多|觀察|偏空|強力賣出), score (整數 0-100), reasoning (字串), risk_warnings (陣列), qa_status (字串，填寫 'Pass' 或發現的異常錯誤說明)"
            ),
            expected_output='{"final_advice": "偏多", "score": 65, "reasoning": "原因", "risk_warnings": ["風險"], "qa_status": "Pass"}',
            agent=agents["qa_error_reporter"],
            context=[task_decision]
        )

        stock_crew = Crew(
            agents=[agents["news_analyst"], agents["technical_analyst"], agents["fund_manager"], agents["qa_error_reporter"]],
            tasks=[task_news, task_tech, task_decision, task_qa],
            process=Process.sequential,
            verbose=True
        )

        result = stock_crew.kickoff()
        return str(result)

    async def run_analysis(self, ticker: str, name: str, price: float, cost: float, news_content: str, indicators: dict) -> str:
        """
        非同步包裝器：將 CrewAI 的同步阻塞任務放到背景 Thread Pool 中執行，
        以免卡死 FastAPI 的事件迴圈。
        """
        if not self.enabled:
            return '{"final_advice": "觀察", "score": 50, "reasoning": "MAIAGENT_API_KEY 未設定，使用預設值。", "risk_warnings": ["無 AI 支持"], "qa_status": "No API Key"}'

        # 透過 asyncio.to_thread 將同步的 _run_crew_sync 放進 ThreadPoolExecutor 執行
        return await asyncio.to_thread(
            self._run_crew_sync,
            ticker, name, price, cost, news_content, indicators
        )

# 全域單一實例
stock_crew_orchestrator = StockCrewOrchestrator()
