from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from schemas.article_plan_schema import NewsArticlePlan
from schemas.enriched_article import EnrichedArticle
from schemas.feed_schema import CanonicalArticle
from schemas.parsed_article import ParsedArticle

# Shared state between the agents


class AgentState(BaseModel):
    articles: List[CanonicalArticle] = Field(default_factory=list)
    plan: Optional[List[Dict[str, Any]]] = None  
    article_search_map: Dict[str, List[ParsedArticle]] = Field(default_factory=dict)
    canonical_ids: Dict[str, int] = Field(default_factory=dict)
    enriched_articles: List[EnrichedArticle] = Field(default_factory=list)
