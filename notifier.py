"""Email 通知"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
#

class EmailNotifier:
    def __init__(self):
        self.sender = os.environ.get("EMAIL_SENDER", "")
        self.password = os.environ.get("EMAIL_PASSWORD", "")
        self.receiver = os.environ.get("EMAIL_RECEIVER", "")
        self.enabled = bool(self.sender and self.password and self.receiver)

    def send(self, subject: str, html_body: str):
        if not self.enabled:
            print("[Email] 未設定環境變數，跳過")
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender
            msg['To'] = self.receiver
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(self.sender, self.password)
                smtp.send_message(msg)
            print("[Email] 發送成功")
            return True
        except Exception as e:
            print(f"[Email] 失敗: {e}")
            return False

    def format_analysis(self, results: list):
        """格式化分析結果為 HTML"""
        html = "<h2>📊 今日台股分析報告</h2><table border='1' cellpadding='8' style='border-collapse:collapse'>"
        html += "<tr style='background:#333;color:#fff'><th>標的</th><th>價格</th><th>評分</th><th>建議</th><th>損益</th></tr>"
        for r in results:
            html += f"""<tr>
                <td>{r.get('name','')} ({r.get('ticker','')})</td>
                <td>${r.get('price',0)}</td>
                <td>{r.get('score',0)}</td>
                <td><b>{r.get('advice','')}</b></td>
                <td>{r.get('pl',0):+.2f}%</td>
            </tr>"""
        html += "</table>"
        return html
