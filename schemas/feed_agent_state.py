from typing import Dict, Any
from pydantic import BaseModel

class FeedState(BaseModel):
    url: str
    last_modified: str | None = None
    etag: str | None = None
    updated: bool = False
    last_checked: str | None = None
    last_processed_id: str | None = None 
    last_processed_published: str | None = None
