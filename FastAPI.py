class NewsRequest(BaseModel):
    news_content: str

@app.post("/analyze_news")
def analyze_business_news(req: NewsRequest):
    analysis_prompt = f"""
    請閱讀以下財經新聞，並嚴格按照以下 JSON 格式回傳分析結果，不要加入任何其他文字：
    {{
        "summary": "一句話總結新聞核心",
        "sentiment": "利多 / 利空 / 中立",
        "impact_stocks": ["股票代號1", "股票代號2"],
        "reasoning": "簡述判斷原因"
    }}
    
    新聞內容：
    {req.news_content}
    """
    
    try:
        response = model.generate_content(analysis_prompt)
        return {"status": "success", "analysis": response.text}
    except Exception as e:
        return {"status": "error"}
