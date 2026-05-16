import feedparser
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import time

# 增強 Headers 以減少被阻擋的機率
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.8,en-US;q=0.5,en;q=0.3",
    "Connection": "keep-alive",
}

# 更新為更穩定的 RSS 來源
RSS_SOURCES = {
    "yahoo_finance": {"name": "Yahoo 財經", "url": "https://tw.news.yahoo.com/rss/finance", "emoji": "📰"},
    "investing": {"name": "Investing", "url": "https://tw.investing.com/rss/news.rss", "emoji": "💹"},
    # 鉅亨網台股新聞 (如果原本的 API 失敗，可以考慮使用這個 RSS，但有時會被擋)
    # "cnyes_tw": {"name": "鉅亨網", "url": "https://news.cnyes.com/api/v3/news/category/tw_stock", "emoji": "🔔"}, 
}

class NewsCrawler:
    
    @staticmethod
    def fetch_rss(source_key: str, limit: int = 5) -> list:
        if source_key not in RSS_SOURCES:
            return []
            
        source_info = RSS_SOURCES[source_key]
        url = source_info["url"]
        
        try:
            # 加入 Timeout 設定
            feed = feedparser.parse(url)
            
            # 檢查是否解析成功
            if feed.bozo and hasattr(feed.bozo_exception, 'getMessage'):
                 print(f"Warning parsing {source_key}: {feed.bozo_exception.getMessage()}")
                 
            if not feed.entries:
                # 如果 feedparser 失敗，嘗試用 requests 抓取 XML 再給 feedparser 解析 (有時可繞過某些阻擋)
                print(f"Direct parsing failed for {source_key}, trying with requests...")
                response = requests.get(url, headers=HEADERS, timeout=10)
                if response.status_code == 200:
                    feed = feedparser.parse(response.content)
                else:
                    print(f"Failed to fetch {source_key} with requests: HTTP {response.status_code}")
                    return []

            result = []
            for entry in feed.entries[:limit]:
                # 處理時間格式
                pub_time_str = ""
                pub_ts = 0
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_ts = time.mktime(entry.published_parsed)
                    pub_time_str = datetime.fromtimestamp(pub_ts).strftime('%Y-%m-%d %H:%M')
                
                # 簡單清理 summary (移除 HTML 標籤)
                raw_summary = entry.get('summary', '')
                clean_summary = BeautifulSoup(raw_summary, "html.parser").get_text(separator=' ', strip=True) if raw_summary else ""
                
                result.append({
                    "source": source_info["name"],
                    "emoji": source_info["emoji"],
                    "title": entry.get("title", "").strip(),
                    "link": entry.get("link", ""),
                    "summary": clean_summary[:200] + "..." if len(clean_summary) > 200 else clean_summary,
                    "published": pub_time_str,
                    "published_ts": pub_ts
                })
            return result
        except Exception as e:
            print(f"Error fetching RSS {source_key}: {e}")
            return []

    @staticmethod
    def fetch_all(sources: list = None, limit_per_source: int = 5) -> list:
        all_news = []
        target_sources = sources if sources else list(RSS_SOURCES.keys())
        
        for key in target_sources:
            if key in RSS_SOURCES:
                news_items = NewsCrawler.fetch_rss(key, limit=limit_per_source)
                all_news.extend(news_items)
                
        # 依時間排序 (最新的在前面)
        all_news.sort(key=lambda x: x.get('published_ts', 0), reverse=True)
        return all_news

    @staticmethod
    def fetch_article_content(url: str, max_length: int = 3000):
        # 保持原有的擷取內文邏輯，用於深度分析 (雖然目前似乎較少用到)
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.encoding = r.apparent_encoding
            soup = BeautifulSoup(r.text, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()
            main = (soup.find('article') or soup.find('main') or soup.find(class_=['article-body', 'post-content', 'entry-content', 'content']))
            text = main.get_text(separator='\\n', strip=True) if main else soup.get_text(separator='\\n', strip=True)
            return text[:max_length]
        except Exception as e:
            print(f"Error fetching article content: {e}")
            return ""

# 本地測試用
if __name__ == "__main__":
    news = NewsCrawler.fetch_all(limit_per_source=2)
    for n in news:
        print(f"[{n['source']}] {n['title']}")