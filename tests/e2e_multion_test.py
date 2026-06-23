import os
import sys
import time
from multion.client import MultiOn

sys.stdout.reconfigure(encoding='utf-8')

# 您可以切換測試網址：
# 正式環境 URL：https://ayak4-trading-strategy-bot-l4oa.onrender.com
# 開發環境 URL (需透過 ngrok)：http://<your-ngrok-id>.ngrok.io
TARGET_URL = "https://ayak4-trading-strategy-bot-l4oa.onrender.com"

def run_automated_test():
    api_key = os.environ.get("MULTION_API_KEY")
    if not api_key:
        print("❌ 錯誤：找不到 MULTION_API_KEY 環境變數。")
        print("請先前往 MultiOn 後台取得 API Key，並設定到環境變數中再執行此腳本。")
        return

    client = MultiOn(api_key=api_key)

    print(f"🚀 啟動 AI Agent 網站巡檢...")
    print(f"🔗 目標網址：{TARGET_URL}")
    
    try:
        # 1. 建立瀏覽器會話
        session = client.sessions.create(
            url=TARGET_URL,
            local=False # 使用 MultiOn 雲端瀏覽器運行
        )
        session_id = session.session_id
        print(f"✅ 成功建立 Session (ID: {session_id})")

        # 2. 步驟一：檢查 Landing Page 首頁佈局與按鈕
        print("\n🔍 步驟一：檢查首頁「功能特點」排版與登入視窗邏輯...")
        step1_res = client.sessions.step(
            session_id=session_id,
            cmd=(
                "請先觀察網頁，確認有沒有看到「四大核心功能」等功能特點的四宮格文字排版，確認版面是否整齊且沒有重疊。"
                "接著，點擊畫面上寫著「立即登入使用 ➔」的按鈕。"
                "檢查點擊後是否有順利跳出『登入』視窗。"
                "如果在視窗內看到信箱跟密碼欄位，請在信箱輸入 'test@example.com'，密碼輸入 '123456'，並點擊視窗內的『登入』按鈕。"
            )
        )
        print(f"🤖 Agent 回報: {step1_res.message}")

        # 3. 步驟二：檢查登入結果與錯誤捕捉
        print("\n🔍 步驟二：檢查業務邏輯與連線異常...")
        step2_res = client.sessions.step(
            session_id=session_id,
            cmd=(
                "檢查畫面上是否有跳出紅色的「登入失敗」、「系統連線失敗」或「404」等異常錯誤提示。"
                "如果登入失敗，請告訴我看到的錯誤訊息是什麼。"
                "最後請試著點擊右上角的「功能特點」按鈕，確認網頁有沒有平滑捲動到下方功能介紹區塊。"
            )
        )
        print(f"🤖 Agent 最終報告: {step2_res.message}")

        # 4. 判斷與截圖
        final_msg = step2_res.message.lower()
        if "錯誤" in final_msg or "異常" in final_msg or "失敗" in final_msg or "error" in final_msg or "fail" in final_msg:
            print("\n🚨 [警報] Agent 發現網站異常或登入失敗！")
            screenshot = client.sessions.screenshot(session_id=session_id)
            print(f"📸 異常畫面截圖連結: {screenshot.screenshot_url}")
        else:
            print("\n✅ [正常] 網站核心功能與排版檢查初步通過。")

    except Exception as e:
        print(f"\n❌ 測試過程發生非預期錯誤：{e}")
    finally:
        # 5. 關閉會話
        if 'session_id' in locals():
            try:
                client.sessions.close(session_id=session_id)
                print("\n🔒 會話已關閉，巡檢結束。")
            except:
                pass

if __name__ == "__main__":
    run_automated_test()
