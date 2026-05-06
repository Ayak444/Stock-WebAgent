# notifier.py — Email 通知版
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

class EmailNotifier:
    def __init__(self):
        self.smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self.sender = os.environ.get("EMAIL_SENDER", "")       # 寄件信箱
        self.password = os.environ.get("EMAIL_PASSWORD", "")   # 應用程式密碼（不是登入密碼）
        self.receiver = os.environ.get("EMAIL_RECEIVER", "")   # 收件信箱（可與寄件相同）

    def send(self, html_content, subject=None):
        """送出 HTML 格式 Email"""
        if not self.sender or not self.password or not self.receiver:
            print("[Email] 未設定完整環境變數，跳過寄送")
            return False
        
        try:
            subject = subject or f"📊 台股智能分析 - {datetime.now().strftime('%Y/%m/%d %H:%M')}"
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"台股分析機器人 <{self.sender}>"
            msg['To'] = self.receiver
            
            # 包裝成漂亮的 HTML
            html = self._wrap_html(html_content)
            msg.attach(MIMEText(html, 'html', 'utf-8'))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender, self.password)
                server.send_message(msg)
            
            print(f"[Email] 已寄送至 {self.receiver}")
            return True
        except Exception as e:
            print(f"[Email] 寄送失敗: {e}")
            return False
    
    def _wrap_html(self, content):
        """包裝成美觀的 HTML 郵件"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family:'Segoe UI','Microsoft JhengHei',sans-serif;background:#f5f7fa;margin:0;padding:20px;">
          <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
            <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:24px;color:#fff;">
              <h1 style="margin:0;font-size:22px;">📊 台股智能分析報告</h1>
              <p style="margin:8px 0 0;opacity:0.9;font-size:13px;">{datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
            </div>
            <div style="padding:24px;color:#333;line-height:1.7;">
              {content}
            </div>
            <div style="background:#f8f9fa;padding:16px;text-align:center;color:#888;font-size:12px;">
              此為系統自動發送，請勿直接回覆<br>
              Powered by Gemini AI
            </div>
          </div>
        </body>
        </html>
        """

# 保持舊名稱相容（讓 main.py 不用大改）
TelegramNotifier = EmailNotifier
