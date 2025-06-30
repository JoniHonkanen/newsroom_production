from pydantic import BaseModel, Field
from typing import Any, List, Optional

from schemas.feed_schema import CanonicalArticle
from schemas.news_draft import StructuredSourceArticle
from schemas.enriched_article import EnrichedArticle

# Shared state between the agents

class AgentState(BaseModel):
    articles: List[CanonicalArticle] = Field(default_factory=list)
    plan: Optional[Any] = None
    web_search_results: List[StructuredSourceArticle] = Field(default_factory=list)
    enriched_articles: List[EnrichedArticle] = Field(default_factory=list)
    stored_article_ids: List[int] = Field(default_factory=list)
