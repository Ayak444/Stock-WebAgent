"""Discord Webhook 通知"""
import os
import requests
from datetime import datetime

class DiscordNotifier:
    def __init__(self):
        self.webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
        self.enabled = bool(self.webhook_url)

    def _post(self, payload: dict) -> bool:
        if not self.enabled:
            print("[Discord] 未設定 DISCORD_WEBHOOK_URL 環境變數，跳過發送")
            return False
            
        try:
            resp = requests.post(self.webhook_url, json=payload)
            resp.raise_for_status()
            print("[Discord] 通知發送成功")
            return True
        except Exception as e:
            print(f"[Discord] 發送失敗: {e}")
            return False

    def send(self, title: str, description: str = "", color: int = 0x3498db):
        """發送一般 Embed 訊息"""
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat()
        }
        return self._post({"embeds": [embed]})
        
    def send_alert(self, title: str, message: str, level: str = "info"):
        """發送即時告警（根據等級變更顏色）"""
        colors = {
            "info": 0x3498db,    # 藍色
            "success": 0x2ecc71, # 綠色
            "warning": 0xf1c40f, # 黃色
            "error": 0xe74c3c    # 紅色
        }
        color = colors.get(level.lower(), 0x3498db)
        return self.send(title, message, color)

    def format_analysis(self, results: list) -> str:
        """格式化分析結果為 Discord Markdown 字串"""
        lines = []
        for r in results:
            name = r.get('name', '')
            ticker = r.get('ticker', '')
            price = r.get('price', 0)
            score = r.get('score', 0)
            advice = r.get('advice', '')
            pl = r.get('pl', 0)
            
            lines.append(f"**{name} ({ticker})**")
            lines.append(f"• 價格: `${price}`")
            lines.append(f"• 評分: `{score}`")
            lines.append(f"• 建議: **{advice}**")
            pl_str = f"{pl:+.2f}%"
            if pl > 0:
                pl_str = f"📈 **{pl_str}**"
            elif pl < 0:
                pl_str = f"📉 **{pl_str}**"
            lines.append(f"• 損益: {pl_str}")
            lines.append("")
            
        return "\n".join(lines)
