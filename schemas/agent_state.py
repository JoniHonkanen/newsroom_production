from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from schemas.feed_schema import CanonicalArticle
from schemas.news_draft import StructuredSourceArticle
from schemas.enriched_article import EnrichedArticle

# Shared state between the agents

class AgentState(BaseModel):
    articles: List[CanonicalArticle] = Field(default_factory=list)
    plan: Optional[Any] = None
    web_search_results: List[StructuredSourceArticle] = Field(default_factory=list)
    enriched_articles: List[EnrichedArticle] = Field(default_factory=list)
    canonical_ids: Dict[str, int] = Field(default_factory=dict, description="Mapping from article URL to canonical_news_id")
    article_search_map: Dict[str, List[StructuredSourceArticle]] = Field(
        default_factory=dict,
        description="Maps article IDs to their specific web search results"
    )