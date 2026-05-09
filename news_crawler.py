import feedparser
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

RSS_SOURCES = {
    "bloomberg": {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss", "emoji": "🌐"},
    "investing": {"name": "Investing.com", "url": "https://tw.investing.com/rss/news.rss", "emoji": "💹"},
    "ctee": {"name": "工商時報", "url": "https://ctee.com.tw/feed", "emoji": "📰"},
    "udn_money": {"name": "經濟日報", "url": "https://money.udn.com/rssfeed/news/1001/5591/5612?ch=money", "emoji": "💰"},
    "udn_stock": {"name": "經濟日報-股市", "url": "https://money.udn.com/rssfeed/news/1001/5590/12017?ch=money", "emoji": "📊"},
    "cnyes": {"name": "鉅亨網", "url": "https://api.cnyes.com/media/api/v1/newslist/category/tw_stock?limit=20", "emoji": "🔔"}
}

class NewsCrawler:
    @staticmethod
    def fetch_all(sources=None, limit_per_source=5):
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
            except Exception:
                continue

        cutoff_ts = int(time.time()) - (3 * 24 * 3600)
        filtered_news = [n for n in all_news if n.get('published_ts', 0) >= cutoff_ts]
        filtered_news.sort(key=lambda x: x.get('published_ts', 0), reverse=True)
        return filtered_news

    @staticmethod
    def _fetch_rss(source_key: str, limit: int = 5):
        src = RSS_SOURCES[source_key]
        feed = feedparser.parse(src['url'], request_headers=HEADERS)
        result = []
        for entry in feed.entries[:limit]:
            pub_ts = 0
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_ts = int(time.mktime(entry.published_parsed))
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                pub_ts = int(time.mktime(entry.updated_parsed))
            summary = entry.get('summary', '')
            if summary:
                soup = BeautifulSoup(summary, 'html.parser')
                summary = soup.get_text().strip()[:200]
            result.append({
                "source": src['name'], "emoji": src['emoji'], "title": entry.get('title', '').strip(),
                "link": entry.get('link', ''), "summary": summary,
                "published": datetime.fromtimestamp(pub_ts).strftime('%Y-%m-%d %H:%M') if pub_ts else '',
                "published_ts": pub_ts
            })
        return result

    @staticmethod
    def _fetch_cnyes(limit: int = 10):
        try:
            url = f"https://api.cnyes.com/media/api/v1/newslist/category/tw_stock?limit={limit}"
            r = requests.get(url, headers=HEADERS, timeout=10)
            data = r.json()
            items = data.get("items", {}).get("data", [])
            result = []
            for item in items:
                pub_ts = item.get("publishAt", 0)
                result.append({
                    "source": "鉅亨網", "emoji": "🔔", "title": item.get("title", "").strip(),
                    "link": f"https://news.cnyes.com/news/id/{item.get('newsId', '')}", "summary": item.get("summary", "")[:200],
                    "published": datetime.fromtimestamp(pub_ts).strftime('%Y-%m-%d %H:%M') if pub_ts else '',
                    "published_ts": pub_ts
                })
            return result
        except Exception:
            return []

    @staticmethod
    def fetch_article_content(url: str, max_length: int = 3000):
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.encoding = r.apparent_encoding
            soup = BeautifulSoup(r.text, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()
            main = (soup.find('article') or soup.find('main') or soup.find(class_=['article-body', 'post-content', 'entry-content', 'content']))
            text = main.get_text(separator='\n', strip=True) if main else soup.get_text(separator='\n', strip=True)
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            return '\n'.join(lines)[:max_length]
        except Exception:
            return ""