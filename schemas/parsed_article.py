# schemas/parsed_article.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ParsedArticle(BaseModel):
    """Simplified result from article parsing - only what we actually use."""
    markdown: str
    published: Optional[datetime] = None
    domain: Optional[str] = None