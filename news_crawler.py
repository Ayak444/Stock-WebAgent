"""
新聞爬蟲：Bloomberg、Investing.com、工商時報、經濟日報
所有來源都用 RSS（穩定不被擋）
"""
import feedparser
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

# ========== RSS 來源 ==========
RSS_SOURCES = {
    "bloomberg": {
        "name": "Bloomberg",
        "url": "https://feeds.bloomberg.com/markets/news.rss",
        "emoji": "🌐"
    },
    "investing": {
        "name": "Investing.com",
        "url": "https://tw.investing.com/rss/news.rss",
        "emoji": "💹"
    },
    "ctee": {
        "name": "工商時報",
        "url": "https://ctee.com.tw/feed",
        "emoji": "📰"
    },
    "udn_money": {
        "name": "經濟日報",
        "url": "https://money.udn.com/rssfeed/news/1001/5591/5612?ch=money",
        "emoji": "💰"
    },
    "udn_stock": {
        "name": "經濟日報-股市",
        "url": "https://money.udn.com/rssfeed/news/1001/5590/12017?ch=money",
        "emoji": "📊"
    },
    "cnyes": {
        "name": "鉅亨網",
        "url": "https://api.cnyes.com/media/api/v1/newslist/category/tw_stock?limit=20",
        "emoji": "🔔"
    }
}


class NewsCrawler:

    @staticmethod
    def fetch_all(sources=None, limit_per_source=5):
        """抓取所有來源的新聞"""
        if sources is None:
            sources = list(RSS_SOURCES.keys())

        all_news = []
        for key in sources:
            if key not in RSS_SOURCES:
                continue
            try:
                if key == "cnyes":
                    news = NewsCrawler._fetch_cnyes(limit_per_source)
                else:
                    news = NewsCrawler._fetch_rss(key, limit_per_source)
                all_news.extend(news)
                time.sleep(0.5)
            except Exception as e:
                print(f"[News] {key} 失敗: {e}")
                continue

        # 按時間排序（新→舊）
        all_news.sort(key=lambda x: x.get('published_ts', 0), reverse=True)
        return all_news

    @staticmethod
    def _fetch_rss(source_key: str, limit: int = 5):
        """通用 RSS 抓取"""
        src = RSS_SOURCES[source_key]
        feed = feedparser.parse(src['url'], request_headers=HEADERS)

        result = []
        for entry in feed.entries[:limit]:
            # 嘗試多種時間欄位
            pub_ts = 0
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_ts = int(time.mktime(entry.published_parsed))
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                pub_ts = int(time.mktime(entry.updated_parsed))

            # 摘要（去 HTML）
            summary = entry.get('summary', '')
            if summary:
                soup = BeautifulSoup(summary, 'html.parser')
                summary = soup.get_text().strip()[:200]

            result.append({
                "source": src['name'],
                "emoji": src['emoji'],
                "title": entry.get('title', '').strip(),
                "link": entry.get('link', ''),
                "summary": summary,
                "published": datetime.fromtimestamp(pub_ts).strftime('%Y-%m-%d %H:%M') if pub_ts else '',
                "published_ts": pub_ts
            })
        return result

    @staticmethod
    def _fetch_cnyes(limit: int = 10):
        """鉅亨網台股新聞（JSON API）"""
        try:
            url = f"https://api.cnyes.com/media/api/v1/newslist/category/tw_stock?limit={limit}"
            r = requests.get(url, headers=HEADERS, timeout=10)
            data = r.json()
            items = data.get("items", {}).get("data", [])

            result = []
            for item in items:
                pub_ts = item.get("publishAt", 0)
                result.append({
                    "source": "鉅亨網",
                    "emoji": "🔔",
                    "title": item.get("title", "").strip(),
                    "link": f"https://news.cnyes.com/news/id/{item.get('newsId', '')}",
                    "summary": item.get("summary", "")[:200],
                    "published": datetime.fromtimestamp(pub_ts).strftime('%Y-%m-%d %H:%M') if pub_ts else '',
                    "published_ts": pub_ts
                })
            return result
        except Exception as e:
            print(f"[Cnyes] {e}")
            return []

    @staticmethod
    def fetch_article_content(url: str, max_length: int = 3000):
        """抓取單篇文章全文"""
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.encoding = r.apparent_encoding
            soup = BeautifulSoup(r.text, 'html.parser')

            # 移除不需要的元素
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()

            # 嘗試找主要內容（常見的 article / main / content）
            main = (soup.find('article') or
                    soup.find('main') or
                    soup.find(class_=['article-body', 'post-content', 'entry-content', 'content']))

            text = main.get_text(separator='\n', strip=True) if main else soup.get_text(separator='\n', strip=True)

            # 清理多餘空行
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            return '\n'.join(lines)[:max_length]
        except Exception as e:
            print(f"[Article] {url}: {e}")
            return ""
