import os
import json
import re
import requests
from dotenv import load_dotenv

load_dotenv()

def get_sentiment_analysis(news_content: str):
    api_key = os.getenv("MAIAGENT_API_KEY")
    chatbot_id = os.getenv("MAIAGENT_CHATBOT_ID")
    base_url = os.getenv("MAIAGENT_BASE_URL", "https://api.maiagent.ai/api")
    if "maiagent.ai" in base_url:
        base_url = "https://api.maiagent.ai/api"
    
    api_url = f"{base_url}/chatbots/{chatbot_id}/completions"

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "message": {
            "content": (
                "你是一位資深台股宏觀分析師。請分析提供的新聞，並回傳嚴格的 JSON 格式。\n"
                "【絕對要求】：不要輸出任何 Markdown 標記 (如 ```json)、問候語或其他文字。只能輸出大括號包起來的 JSON 本身。\n"
                "要求：\n"
                "1. score: 0-100 的情緒分數。\n"
                "2. reasoning: 詳細解釋為何給出此分數（包含市場心理、利多利空抵銷邏輯）。\n"
                "3. news_analysis: 陣列，包含這五則新聞的 title, sentiment(多/空/中立), summary(摘要)。\n"
                "4. recommendations: 推薦標的。\n\n"
                f"新聞內容：{news_content}"
            )
        }
    }

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

        # 雙重去殼法：清除 Markdown 與多餘文字
        ai_content = str(ai_content).strip()
        ai_content = re.sub(r'```json\s*', '', ai_content, flags=re.IGNORECASE)
        ai_content = re.sub(r'```\s*', '', ai_content)
        
        start_idx = ai_content.find('{')
        end_idx = ai_content.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            clean_json = ai_content[start_idx:end_idx+1]
        else:
            clean_json = ai_content

        return parse_mai_result(clean_json)
        
    except Exception as e:
        print(f"Agent Request Error: {e}")
        return {
            "score": 50,
            "label": "中立",
            "definition": "暫時無法取得 AI 分析，維持中立觀點。",
            "reasoning": f"系統連線錯誤或 API 逾時: {str(e)}",
            "recommendations": [],
            "news_analysis": []
        }

def parse_mai_result(ai_json_str):
    try:
        data = json.loads(ai_json_str, strict=False)
        score = data.get("score", 50)
    except Exception as e:
        print(f"JSON Parse Error: {e}\nRaw Content: {ai_json_str}")
        score = 50
        data = {"reasoning": "AI 回傳格式異常，無法解析。"}
    
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