from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel


# For RSS feeds, we define categories to classify the type of news.
class FeedCategory(str, Enum):
    press_release = "press_release"
    news = "news"
    blog = "blog"
    event = "event"
    decision = "decision"
    other = "other"


class NewsFeedConfig(BaseModel):
    name: str
    extra_info: str | None = None
    feed_type: str
    category: FeedCategory
    origin: str | None = None
    url: str
    active: bool = True
    added_at: str | None = None
    modified_at: str | None = None


# State for a feed agent that processes news articles.


class FeedState(BaseModel):
    url: str
    last_modified: str | None = None
    etag: str | None = None
    updated: bool = False
    last_checked: str | None = None
    last_processed_id: str | None = None
    last_processed_published: str | None = None


class CanonicalArticle(BaseModel):
    title: str
    link: str
    summary: Optional[str] = None
    unique_id: Optional[str] = None
    content: Optional[str] = None
    published_at: Optional[str] = None
    source_domain: Optional[str] = None  # esim yle.fi
    language: Optional[str] = None
    article_type: Optional[str] = None
