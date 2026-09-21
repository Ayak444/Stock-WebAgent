"""Discord Webhook 通知"""
import os
import requests
from datetime import datetime

class DiscordNotifier:
    def __init__(self, webhook_url=None, transport=None):
        self.webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "") if webhook_url is None else webhook_url
        self.transport = transport or requests.post
        self.enabled = bool(self.webhook_url)

    def _post(self, payload: dict) -> bool:
        if not self.enabled:
            print("[Discord] 未設定 DISCORD_WEBHOOK_URL 環境變數，跳過發送")
            return False
            
        try:
            safe_payload = {**payload, "allowed_mentions": {"parse": []}}
            resp = self.transport(
                self.webhook_url,
                json=safe_payload,
                timeout=(3, 7),
                allow_redirects=False,
            )
            if isinstance(resp, bool):
                return resp
            status_code = getattr(resp, "status_code", None)
            if type(status_code) is not int or not 200 <= status_code < 300:
                safe_status = status_code if type(status_code) is int else "invalid"
                print(f"[Discord] 發送失敗: HTTP {safe_status}")
                return False
            print("[Discord] 通知發送成功")
            return True
        except Exception as exc:
            print(f"[Discord] 發送失敗: {type(exc).__name__}")
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

    def send_holder_volume_alert(self, result: dict, event_key: str) -> bool:
        periods = result.get("holder_periods", [])
        ratios = " → ".join(
            f"{item.get('date')}: {float(item.get('ratio', 0)):.2f}%"
            for item in periods
        )
        volume = result.get("volume", {})
        route = volume.get("route", {})
        message = "\n".join([
            f"標的：{result.get('ticker', '')}",
            f"大戶三期：{ratios}",
            f"三期增幅：{float(result.get('holder_increase_pp', 0)):.2f} 個百分點",
            f"量能倍數：{float(volume.get('volume_multiple', 0)):.2f}x（最新 {int(volume.get('latest_volume', 0)):,} / 前期中位數 {float(volume.get('baseline_median_volume', 0)):,.0f}）",
            f"行情路由：{route.get('source') or 'unknown'}；行情日：{volume.get('market_date') or 'unknown'}；集保日：{result.get('holder_date') or 'unknown'}",
            f"事件 ID：{event_key}",
            "此訊息僅為資料監控，不構成投資建議。",
        ])[:1800]
        return self.send_alert("大戶增持 × 量能放大監控", message, "warning")

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
