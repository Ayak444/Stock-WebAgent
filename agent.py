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

    payload = {
        "message": {
            "content": f"你是一位專業的台股分析師。請分析提供的新聞，回傳 JSON 格式：{{\"score\": 分數, \"recommendations\": [{{\"name\": \"股票名稱\", \"code\": \"代碼\", \"reason\": \"原因\"}}]}}\n\n新聞內容：{news_content}"
        }
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        res_data = response.json()
        
        if "message" in res_data and isinstance(res_data["message"], dict):
            ai_content = res_data["message"].get("content", "")
        elif "reply" in res_data:
            ai_content = res_data["reply"]
        else:
            ai_content = str(res_data)

        if ai_content.startswith("```"):
            parts = ai_content.split("```")
            if len(parts) >= 2:
                ai_content = parts[1]
            if ai_content.startswith("json"):
                ai_content = ai_content[4:]

        return parse_mai_result(ai_content.strip())
    except Exception as e:
        print(e)
        return {
            "score": 50,
            "label": "中立",
            "definition": "暫時無法取得 AI 分析，維持中立觀點。",
            "recommendations": []
        }

def parse_mai_result(ai_json_str):
    try:
        data = json.loads(ai_json_str)
        score = data.get("score", 50)
    except Exception:
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
        "recommendations": data.get("recommendations", [])
    }