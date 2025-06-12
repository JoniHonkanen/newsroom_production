from pydantic import BaseModel,Field
from typing import Any, List, Optional

class AgentState(BaseModel):
    articles: List[Any] = Field(default_factory=list)
    plan: Optional[Any] = None
