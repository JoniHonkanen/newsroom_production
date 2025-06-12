from enum import Enum
from pydantic import BaseModel

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
