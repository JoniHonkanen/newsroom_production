from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field

# Content blocks for news articles, used in both web and mobile contexts.

class ContentBlock(BaseModel):
    """Base content block structure for news articles."""
    order: int = Field(
        description="The position of this block in the article sequence."
    )
    type: Literal["headline", "intro", "text", "subheading", "image", "list", "quote"] = Field(
        description="Type of content: 'headline' for the main article title, 'intro' for lead paragraph, 'text' for body, 'subheading' for section title, 'image' for media reference, etc."
    )
    content: str = Field(
        description="The actual content of the block: plain text, subheading text, or image URL."
    )
    markdown: Optional[str] = Field(
        default=None, 
        description="Markdown representation of the content for language model processing."
    )
    html: Optional[str] = Field(
        default=None,
        description="HTML representation of the content for web display."
    )
    # Optional fields for specific content types
    alt: Optional[str] = Field(
        default=None, 
        description="Alternative text for image content."
    )
    caption: Optional[str] = Field(
        default=None,
        description="Caption text for images or quotes."
    )
    attribution: Optional[str] = Field(
        default=None,
        description="Attribution information for images or quotes."
    )
    items: Optional[List[str]] = Field(
        default=None,
        description="List items when type is 'list'."
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert the content block to a dictionary suitable for JSON serialization."""
        result = {
            "order": self.order,
            "type": self.type,
            "content": self.content
        }
        
        # Add optional fields if they exist
        if self.markdown:
            result["markdown"] = self.markdown
        if self.html:
            result["html"] = self.html
        if self.alt:
            result["alt"] = self.alt
        if self.caption:
            result["caption"] = self.caption
        if self.attribution:
            result["attribution"] = self.attribution
        if self.items:
            result["items"] = self.items
            
        return result


class ContentBlockWeb(BaseModel):
    """Content block structure specifically for web display."""
    order: int
    type: Literal["headline", "title", "subheading", "text", "image", "list", "quote"]
    content: str  # Content such as text, image URL, etc.
    html: Optional[str] = None  # HTML representation for web rendering
    caption: Optional[str] = None  # Caption for image blocks
    attribution: Optional[str] = None  # Attribution for image or quote blocks
    items: Optional[List[str]] = None  # List items when type is "list"
