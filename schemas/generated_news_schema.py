from pydantic import BaseModel, Field
from typing import List
from typing import Optional

from schemas.content_block import ContentBlock
from schemas.news_draft import Category

# These schemas are used when generating news articles based on existing content or ideas.
# This model is used when saving the generated news item to the database.


class ArticleReference(BaseModel):
    title: str = Field(description="The title of the referenced article.")
    url: str = Field(description="The original URL of the referenced article.")


# Location tags
class LocationTag(BaseModel):
    continent: Optional[str] = Field(description="Continent, e.g., 'Asia', 'Europe'")
    country: Optional[str] = Field(description="Country, e.g., 'Finland'")
    region: Optional[str] = Field(description="Region or state, e.g., 'Pirkanmaa'")
    city: Optional[str] = Field(description="City or locality, e.g., 'Akaa'")


# This model represents the generated news item, including its title, categories, and body content.
class GeneratedNewsItem(BaseModel):
    title: str = Field(description="The main headline of the generated news article.")
    body: List[ContentBlock] = Field(
        description="A structured list of content blocks that make up the body of the article."
    )
    category: List[Category] = Field(
        description="A list of thematic categories assigned to the article. Must include at least one relevant category from the predefined list. Multiple categories are allowed if applicable.",
    )
    keywords: List[str] = Field(
        description="Relevant terms derived from the article’s content and context. Include both directly mentioned and closely related concepts to support indexing, filtering, and retrieval."
    )
    location_tags: Optional[List[LocationTag]] = Field(
        default=None,
        description="A list of geographic or regional tags relevant to the article content, such as countries, cities, or regions.",
    )
    language: str = Field(
        description="The language code of the generated article content, e.g., 'fi', 'en' or 'sv' using ISO 639-1 language codes."
    )
    references: Optional[List[ArticleReference]] = Field(
        default=None,
        description="List of original and supporting articles used as sources. Includes titles and URLs.",
    )

    # pydantic will automatically convert enum values to their string representation!!!
    class Config:
        use_enum_values = True
