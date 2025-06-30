from pydantic import BaseModel, Field, HttpUrl
from typing import List, Literal
from enum import Enum
from typing import Optional
from datetime import datetime

from schemas.content_block import ContentBlockWeb

#This schema is used when planning news articles based on existing news content.

# Categories
class Category(str, Enum):
    WORLD = "World"
    POLITICS = "Politics"
    ECONOMY = "Economy"
    TECHNOLOGY = "Technology"
    SCIENCE = "Science"
    HEALTH = "Health"
    EDUCATION = "Education"
    CULTURE = "Culture"
    SPORTS = "Sports"
    ENTERTAINMENT = "Entertainment"
    WEATHER = "Weather"
    CRIME = "Crime"
    ENVIRONMENT = "Environment"
    LIFESTYLE = "Lifestyle"
    OPINION = "Opinion"
    LOCAL = "Local"
    BREAKING = "Breaking"


# This model is used to read news articles from the RSS feed and get ideas from them.
class NewsDraftPlan(BaseModel):
    summary: str = Field(description="A concise summary of the original news article.")
    idea: str = Field(description="A new news idea inspired by the summarized article.")
    categories: List[Category] = Field(
        description="A list of categories the article belongs to. At least one required."
    )
    keywords: List[str] = Field(
        description="Essential search terms or entities related to the article, e.g., names, places, topics."
    )
    language: str = Field(
        description="The language code of the article content, e.g., 'fi', 'en' or 'sv' using ISO 639-1 language codes."
    )
    published: Optional[str] = Field(
        description="ISO 8601 timestamp indicating when the article was originally published."
    )
    web_search_queries: List[str] = Field(
        description=(
            "Auto-generated search queries derived from the idea, summary, and keywords. "
            "Queries should focus on retrieving recent, relevant, and factual information to enrich the article. "
            "Prefer terms that help find up-to-date news, expert commentary, or official statements related to the topic."
            "Maximum 3 queries, so make them as good as possible."
        )
    )
    markdown: Optional[str] = Field(
        default=None, description="Original news as markdown format."
    )
    url: Optional[str] = Field(default=None, description="The full URL of the article.")

    # pydantic will automatically convert enum values to their string representation!!!
    class Config:
        use_enum_values = True


# This model is used to represent the content blocks of the generated news article.
# Each block can be of different types, such as 'intro', 'text', 'subheading', or 'image'.


# this for web search,
class StructuredSourceArticle(BaseModel):
    url: HttpUrl = Field(description="The full URL to the source article.")
    domain: str = Field(
        description="The domain name of the article's source, e.g. 'yle.fi'"
    )
    published: Optional[datetime] = Field(
        default=None,
        description="The publication timestamp of the article in ISO 8601 format, if available.",
    )
    content_blocks: List[ContentBlockWeb] = Field(
        description="A list of structured content blocks from the article."
    )
    markdown: str = Field(
        description="The same content rendered as Markdown, so LLMs could understand it better."
    )
