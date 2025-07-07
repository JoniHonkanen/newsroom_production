from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from schemas.enriched_article import EnrichedArticle
from schemas.feed_schema import CanonicalArticle
from schemas.parsed_article import ParsedArticle

# Shared state between the agents


class AgentState(BaseModel):
    articles: List[CanonicalArticle] = Field(default_factory=list) #ARTICLES FETCHED FROM THE FEED
    plan: Optional[List[Dict[str, Any]]] = None #PLANS FOR FETCHED ARTICLES 
    article_search_map: Dict[str, List[ParsedArticle]] = Field(default_factory=dict)
    canonical_ids: Dict[str, int] = Field(default_factory=dict) # MAP OF ARTICLE URLS TO THEIR CANONICAL IDs
    enriched_articles: List[EnrichedArticle] = Field(default_factory=list) # GENERATED & ENRICHED ARTICLES
    reviewed_articles: List[Any] = Field(default_factory=list) # ARTICLES THAT HAVE BEEN REVIEWED BY THE EDITOR IN CHIEF
