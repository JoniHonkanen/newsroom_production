# services/article_parser.py

from datetime import datetime
from urllib.parse import urlparse
from schemas.news_draft import StructuredSourceArticle
from typing import Optional
import trafilatura  # type: ignore


def to_structured_article(url: str) -> Optional[StructuredSourceArticle]:
    """
    Fetches an article from the given URL using Trafilatura, extracts the
    main content and metadata, and returns a structured representation
    with a combined Markdown output.
    """
    print(f"\n*** FETCHING AND PARSING WITH TRAFILATURA ***\nURL: {url}")

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        print(f"Error: Failed to fetch {url} with Trafilatura")
        return None

    # Extract metadata (title, date, etc.) first
    metadata = trafilatura.extract_metadata(downloaded)

    # Extract the main body of the article as Markdown
    main_content_markdown = trafilatura.extract(
        downloaded,
        include_formatting=True,
        include_links=False,
    )

    # Combine title from metadata with the main content
    final_markdown = ""
    article_title = ""
    if metadata and metadata.title:
        article_title = metadata.title.strip()
        final_markdown = f"# {article_title}\n\n"

    if main_content_markdown:
        final_markdown += main_content_markdown.strip()

    # If no content or title was found, consider it a failure
    if not final_markdown.strip():
        print(f"Error: Trafilatura could not extract title or main content from {url}")
        return None

    # Process publication date from metadata
    published_dt = None
    if metadata and metadata.date:
        try:
            # Handle 'Z' timezone format for ISO 8601 compatibility
            date_str = metadata.date.replace("Z", "+00:00")
            published_dt = datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            print(f"Warning: Could not parse date '{metadata.date}'")
            published_dt = None

    domain = urlparse(url).netloc.replace("www.", "")

    # TODO: BECAUSE WE CHANGED TO USE TRAFILATURA, MAYBE WE DON'T NEED CONTENT_BLOCKS ANYMORE?
    return StructuredSourceArticle(
        url=url,
        domain=domain,
        published=published_dt,
        content_blocks=[],
        markdown=final_markdown.strip(),
    )
