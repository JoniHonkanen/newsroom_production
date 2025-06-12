from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
import feedparser
from datetime import datetime, timezone
from typing import Any


class FeedReaderAgent(BaseAgent):
    print("FeedReaderAgent KUTSUTAAN")

    def __init__(self, feed_url: str, max_news: int = 10):
        # dummy agent, no LLM or prompt needed
        super().__init__(llm=None, prompt=None, name="FeedReaderAgent")
        self.feed_url = feed_url
        self.max_news = max_news

    def run(self, state: AgentState) -> AgentState:
        print(f"\n{self.name}: FETCHING ARTICLES")
        articles = self.fetch_rss_feed(self.feed_url, self.max_news)
        # Yhdistetään aiemmat ja uudet artikkelit
        state.articles.extend(articles)
        return state

    @staticmethod
    def fetch_rss_feed(url: str, max_news: int) -> list[dict[str, Any]]:
        print(f"Fetching RSS feed from {url} with max {max_news} articles")
        feed = feedparser.parse(url)
        print(f"Feed title: {feed.feed.get('title', 'No title')}")
        news_list = []
        for i, entry in enumerate(feed.entries[:max_news], 1):
            title = FeedReaderAgent.clean_text(entry.get("title", "No title"))
            summary = FeedReaderAgent.clean_text(entry.get("summary", "No summary"))
            published = FeedReaderAgent.parse_rss_datetime(entry)
            link = entry.get("link", "No link")
            guid_url = entry.get("id", "") or entry.get("id", "")
            unique_id = FeedReaderAgent.extract_id_from_guid(guid_url)
            news_list.append(
                {
                    "title": title,
                    "summary": summary,
                    "published": published,
                    "link": link,
                    "unique_id": unique_id,
                }
            )
        print(f"Fetched {len(news_list)} articles from the feed.")
        print("First article:", news_list[0] if news_list else "No articles found")
        return news_list

    # Clean up text by removing unwanted characters
    @staticmethod
    def clean_text(text: str) -> str:
        return (
            text.replace("\u00ad", "")
            .replace("\u200b", "")
            .replace("\xa0", " ")
            .strip()
        )

    # Extract unique ID from GUID URL, handling both full URLs and simple IDs
    @staticmethod
    def extract_id_from_guid(guid_url: str) -> str:
        if not guid_url:
            return "No id"
        if "://" in guid_url:
            return guid_url.rstrip("/").split("/")[-1]
        return guid_url.strip()

    # Parse the published date from the RSS entry, returning ISO format
    @staticmethod
    def parse_rss_datetime(entry) -> str:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")
        return "1970-01-01T00:00:00Z"
