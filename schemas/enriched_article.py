# File: schemas/enriched_article.py

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class ArticleReference(BaseModel):
    title: str = Field(description="The title of the referenced article.")
    url: str = Field(description="The original URL of the referenced article.")


# Location tags
class LocationTag(BaseModel):
    continent: Optional[str] = Field(description="Continent, e.g., 'Asia', 'Europe'")
    country: Optional[str] = Field(description="Country, e.g., 'Finland'")
    region: Optional[str] = Field(description="Region or state, e.g., 'Pirkanmaa'")
    city: Optional[str] = Field(description="City or locality, e.g., 'Akaa'")


class EnrichedArticle(BaseModel):
    """A fully enriched news article that combines original content with web search results."""

    article_id: str = Field(
        description="The unique identifier (URL) of the original article this is based on."
    )
    canonical_news_id: Optional[int] = Field(
        default=None, description="The canonical_news_id from the database if known"
    )
    enriched_title: str = Field(
        description="A new, enriched headline based on the original article and web search results."
    )
    enriched_content: str = Field(
        description="The enriched content of the news article, combining original information with web search results."
    )
    published_at: str = Field(
        description="The original publication date of the article."
    )
    generated_at: str = Field(
        description="The date when this enriched version was generated."
    )
    source_domain: str = Field(
        description="The domain where the original article was published."
    )
    keywords: List[str] = Field(description="Keywords describing the article content.")
    categories: List[str] = Field(description="Categories the article belongs to.")
    language: str = Field(description="The language of the article.")
    sources: List[str] = Field(
        description="URLs of the sources used to enrich the article."
    )
    references: Optional[List[ArticleReference]] = Field(
        default=None, description="References to articles mentioned in the content."
    )
    locations: Optional[List[LocationTag]] = Field(
        default=None, description="Geographic locations mentioned in the article."
    )
