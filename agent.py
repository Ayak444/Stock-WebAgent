import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

def get_sentiment_analysis(news_content: str):
    api_key = os.getenv("MAIAGENT_API_KEY")
    chatbot_id = os.getenv("MAIAGENT_CHATBOT_ID")
    base_url = os.getenv("MAIAGENT_BASE_URL", "https://api.maiagent.ai/api")
    
    api_url = f"{base_url}/chatbots/{chatbot_id}/completions"

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json"
    }

    prompt = (
        "你是一位資深台股宏觀分析師。請分析以下新聞，並嚴格只輸出 JSON 格式。\n"
        "絕不允許包含 Markdown 標記 (如 ```json)、問候語或其他任何非 JSON 的文字。\n\n"
        "格式要求：\n"
        "{\n"
        '  "score": (0到100的整數),\n'
        '  "reasoning": "詳細解釋為何給出此分數",\n'
        '  "news_analysis": [\n'
        '    { "title": "標題", "sentiment": "多或空或中立", "summary": "摘要" }\n'
        '  ],\n'
        '  "recommendations": [\n'
        '    { "name": "股票名稱", "code": "代碼", "reason": "原因" }\n'
        '  ]\n'
        "}\n\n"
        f"新聞內容：\n{news_content}"
    )

    payload = {"message": {"content": prompt}}

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=45)
        res_data = response.json()
        
        ai_content = ""
        if "message" in res_data and isinstance(res_data["message"], dict):
            ai_content = res_data["message"].get("content", "")
        elif "reply" in res_data:
            ai_content = res_data["reply"]
        else:
            ai_content = str(res_data)

        # 終極防呆：強制找出第一個 { 與最後一個 } 的內容
        start_idx = ai_content.find('{')
        end_idx = ai_content.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            clean_json = ai_content[start_idx:end_idx+1]
        else:
            clean_json = ai_content

        return parse_mai_result(clean_json)

    except Exception as e:
        print(f"Agent API Error: {e}")
        return parse_mai_result("{}")

def parse_mai_result(ai_json_str):
    try:
        # strict=False 允許處理 JSON 內的非法換行符號
        data = json.loads(ai_json_str, strict=False)
        score = data.get("score", 50)
    except Exception as e:
        print(f"JSON 解析失敗: {e}\n原始字串: {ai_json_str}")
        score = 50
        data = {}
    
    if score >= 70:
        label, defn = "極度貪婪", "市場過熱，建議分批獲利。"
    elif score >= 55:
        label, defn = "樂觀", "買盤積極，注意追高風險。"
    elif score >= 45:
        label, defn = "中立", "多空平衡，建議持有績優股。"
    else:
        label, defn = "恐懼", "市場低迷，可尋找低估標的。"

    return {
        "score": score,
        "label": label,
        "definition": defn,
        "reasoning": data.get("reasoning", "目前無詳細說明"),
        "recommendations": data.get("recommendations", []),
        "news_analysis": data.get("news_analysis", [])
    }