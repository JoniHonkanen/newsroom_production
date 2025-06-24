from pydantic import BaseModel,Field
from typing import Any, List, Optional

from schemas.feed_schema import CanonicalArticle

# Shared state between the agents

class AgentState(BaseModel):
    articles: List[CanonicalArticle] = Field(default_factory=list)
    plan: Optional[Any] = None
