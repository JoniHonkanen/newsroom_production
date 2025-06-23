from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class ContentBlock(BaseModel):
    type: Literal["headline", "intro", "text", "subheading", "image"] = Field(
        description="Type of content: 'headline' for the main article title, 'intro' for lead paragraph, 'text' for body, 'subheading' for section title, 'image' for media reference."
    )
    content: str = Field(
        description="The actual content of the block: plain text, subheading text, or image description/URL."
    )


class ContentBlockWeb(BaseModel):
    type: Literal["title", "subheading", "text", "image", "list", "quote"]
    content: str  # Sisältö, esim. teksti, kuvan url, tms.
    caption: Optional[str] = None  # Kuvateksti kuvablokeille
    items: Optional[List[str]] = None  # Lista, jos tyyppi on "list"
