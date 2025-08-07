# File: agents/article_image_generator_agent.py

import sys
import os
import requests
import re
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote
from pathlib import Path

# Add the project root to the Python path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle


class ArticleImageGeneratorAgent(BaseAgent):
    """An agent that generates and adds relevant images to enriched articles using Pixabay API."""

    def __init__(
        self, pixabay_api_key: str, image_storage_path: str = "static/images/articles"
    ):
        super().__init__(llm=None, prompt=None, name="ArticleImageGeneratorAgent")
        self.pixabay_api_key = pixabay_api_key
        self.image_storage_path = Path(image_storage_path)
        self.image_storage_path.mkdir(parents=True, exist_ok=True)

    def _search_pixabay_image(
        self, search_term: str, language: str = "en"
    ) -> Optional[str]:
        """Search for a single relevant image from Pixabay."""
        try:
            # Clean and prepare search term
            clean_term = quote(search_term.lower().replace(",", " ").strip())

            # Map language codes for Pixabay
            lang_code = "fi" if language == "fi" else "en"

            url = f"https://pixabay.com/api/?key={self.pixabay_api_key}&q={clean_term}&safesearch=true&order=popular&image_type=photo&orientation=horizontal&per_page=3&editors_choice=true&lang={lang_code}"

            print(
                f"      - Searching Pixabay for: '{search_term}' (language: {lang_code})"
            )

            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("hits") and len(data["hits"]) > 0:
                hit = data["hits"][0]
                # Use 340px width for smaller file size
                image_url = hit["webformatURL"].replace("_640", "_340")
                print(f"      - Found image: {image_url}")
                return image_url
            else:
                print(f"      - No images found for: '{search_term}'")
                return None

        except Exception as e:
            print(f"      - Error searching Pixabay for '{search_term}': {e}")
            return None

    def _extract_image_placeholders(
        self, markdown_content: str
    ) -> List[Tuple[str, str]]:
        """Extract all image placeholders from markdown content.
        Returns list of tuples: (full_match, alt_text)
        """
        pattern = r"!\[([^\]]+)\]\(PLACEHOLDER_IMAGE\)"
        matches = re.findall(pattern, markdown_content)

        placeholders = []
        for match in matches:
            alt_text = match.strip()
            full_match = f"![{alt_text}](PLACEHOLDER_IMAGE)"
            placeholders.append((full_match, alt_text))

        print(f"    - Found {len(placeholders)} image placeholders")
        for i, (_, alt_text) in enumerate(placeholders, 1):
            print(f"      {i}. '{alt_text}'")

        return placeholders

    def _fallback_search_terms(self, categories: List[str], language: str) -> List[str]:
        """Generate fallback search terms based on article categories."""

        # Category to search term mapping
        category_mapping = {
            "politiikka": ["government", "politics", "finland"],
            "politics": ["government", "parliament", "voting"],
            "teknologia": ["technology", "computer", "innovation"],
            "technology": ["technology", "innovation", "digital"],
            "urheilu": ["sports", "athletics", "competition"],
            "sports": ["sports", "athletics", "stadium"],
            "talous": ["business", "economy", "finance"],
            "business": ["business", "economy", "meeting"],
            "terveys": ["health", "medical", "healthcare"],
            "health": ["healthcare", "medical", "hospital"],
            "ympäristö": ["nature", "environment", "green"],
            "environment": ["nature", "environment", "sustainability"],
        }

        fallback_terms = []
        for category in categories[:2]:  # Take first 2 categories
            category_lower = category.lower()
            if category_lower in category_mapping:
                fallback_terms.extend(
                    category_mapping[category_lower][:1]
                )  # Take first term

        # Generic fallback terms
        if not fallback_terms:
            fallback_terms = ["news", "information", "communication"]

    def _download_and_save_image(
        self, image_url: str, article_title: str, image_index: int
    ) -> Optional[str]:
        """Download image from Pixabay and save it locally."""
        try:
            # Create unique filename from article title
            from datetime import datetime

            # Clean title (first 20 chars, safe for filename)
            clean_title = article_title[:20].lower()
            clean_title = re.sub(
                r"[^a-z0-9\s]", "", clean_title
            )  # Remove special chars
            clean_title = re.sub(
                r"\s+", "_", clean_title.strip()
            )  # Replace spaces with underscore

            # Add date and image index
            date_str = datetime.now().strftime("%Y%m%d")
            filename = f"{clean_title}_{image_index}_{date_str}.jpg"
            local_path = self.image_storage_path / filename

            print(f"      - Downloading image to: {local_path}")

            # Download image
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()

            # Save image
            with open(local_path, "wb") as f:
                f.write(response.content)

            # Return relative URL for web usage
            web_url = f"/static/images/articles/{filename}"
            print(f"      - Saved as: {web_url}")

            return web_url

        except Exception as e:
            print(f"      - Error downloading image: {e}")
            return None

    def _process_article_images(self, article: EnrichedArticle) -> EnrichedArticle:
        """Process all images in an enriched article."""

        print(f"    - Processing images for: {article.enriched_title[:60]}...")

        # Extract all image placeholders
        placeholders = self._extract_image_placeholders(article.enriched_content)

        if not placeholders:
            print(f"    - No image placeholders found in article")
            return article

        # Process each placeholder
        updated_content = article.enriched_content
        hero_image_url = None
        successful_replacements = 0

        for i, (full_match, alt_text) in enumerate(placeholders):
            print(f"    - Processing image {i+1}/{len(placeholders)}: '{alt_text}'")

            # Search for image
            image_url = self._search_pixabay_image(alt_text, article.language)

            # If no image found, try fallback search terms
            if not image_url and article.categories:
                fallback_terms = self._fallback_search_terms(
                    article.categories, article.language
                )
                for fallback_term in fallback_terms:
                    print(f"      - Trying fallback term: '{fallback_term}'")
                    image_url = self._search_pixabay_image(
                        fallback_term, article.language
                    )
                    if image_url:
                        break

            if image_url:
                # Download image locally
                local_url = self._download_and_save_image(
                    image_url, article.enriched_title, i + 1
                )

                if local_url:
                    # Replace placeholder with local URL
                    replacement = f"![{alt_text}]({local_url})"
                    updated_content = updated_content.replace(full_match, replacement)
                    successful_replacements += 1

                    # Set first successful image as hero image
                    if hero_image_url is None:
                        hero_image_url = local_url
                        print(f"      - Set as hero image: {local_url}")

                    print(f"      - Successfully replaced placeholder {i+1}")
                else:
                    # Remove placeholder if download failed
                    updated_content = updated_content.replace(full_match, "")
                    print(f"      - Removed placeholder {i+1} (download failed)")
            else:
                # Remove placeholder if no image found
                updated_content = updated_content.replace(full_match, "")
                print(f"      - Removed placeholder {i+1} (no image found)")

        print(
            f"    - Successfully processed {successful_replacements}/{len(placeholders)} images"
        )

        # Create updated article
        article_data = article.model_dump()
        article_data.update(
            {"enriched_content": updated_content, "hero_image_url": hero_image_url}
        )
        enhanced_article = EnrichedArticle(**article_data)

        return enhanced_article

    def run(self, state: AgentState) -> AgentState:
        """Add relevant images to enriched articles."""

        print("ArticleImageGeneratorAgent: Starting to generate images for articles...")

        if not state.enriched_articles:
            print("ArticleImageGeneratorAgent: No enriched articles to process.")
            return state

        if not self.pixabay_api_key:
            print(
                "ArticleImageGeneratorAgent: No Pixabay API key provided. Skipping image generation."
            )
            return state

        print(
            f"ArticleImageGeneratorAgent: Processing {len(state.enriched_articles)} articles..."
        )

        enhanced_articles = []

        for i, article in enumerate(state.enriched_articles, 1):
            print(f"\n  - Processing article {i}/{len(state.enriched_articles)}")
            try:
                enhanced_article = self._process_article_images(article)
                enhanced_articles.append(enhanced_article)

            except Exception as e:
                print(f"    - Error processing article images: {e}")
                # Keep original article if image processing fails
                enhanced_articles.append(article)

        state.enriched_articles = enhanced_articles
        print(
            f"\nArticleImageGeneratorAgent: Completed image processing for {len(enhanced_articles)} articles"
        )

        return state


if __name__ == "__main__":
    from dotenv import load_dotenv
    from schemas.enriched_article import EnrichedArticle
    from schemas.agent_state import AgentState

    print("--- Testing ArticleImageGeneratorAgent in isolation ---")
    load_dotenv()

    # Get Pixabay API key from environment
    pixabay_key = os.getenv("PIXABAY_API_KEY")
    if not pixabay_key:
        print("❌ PIXABAY_API_KEY not found in environment variables")
        exit(1)

    # Create test enriched article with image placeholders
    test_article = EnrichedArticle(
        article_id="test-image-article",
        canonical_news_id=123,
        enriched_title="Finland's AI Strategy Test Article",
        enriched_content="""![main topic](PLACEHOLDER_IMAGE)

Finland has made significant investments in AI technology development.

![ai research](PLACEHOLDER_IMAGE)

The country plans to establish research centers across multiple cities.

### Future Developments

More developments are expected in the coming months.

![government building](PLACEHOLDER_IMAGE)

This initiative represents Finland's commitment to technological advancement.""",
        published_at="2024-08-06",
        source_domain="test.com",
        keywords=["Finland", "AI", "technology"],
        categories=["Technology", "Politics"],
        language="en",
        sources=["http://test.com"],
        references=[],
        locations=[],
        summary="Finland invests in AI technology development",
        enrichment_status="success",
        hero_image_url=None,  # Should be set by the agent
    )

    # Create test state
    test_state = AgentState(
        articles=[],
        plan=[],
        article_search_map={},
        canonical_ids={},
        enriched_articles=[test_article],
    )

    print(f"\nTest setup:")
    print(f"- Input articles: {len(test_state.enriched_articles)}")
    print(f"- Pixabay API key: {'✓' if pixabay_key else '✗'}")

    # Create and run the agent
    image_agent = ArticleImageGeneratorAgent(pixabay_key)

    print("\n--- Running ArticleImageGeneratorAgent ---")
    result_state = image_agent.run(test_state)
    print("--- Agent completed ---")

    # Print results
    print("\n--- Results ---")
    if result_state.enriched_articles:
        for i, article in enumerate(result_state.enriched_articles):
            print(f"\n=== ARTICLE {i+1} RESULTS ===")
            print(f"Title: {article.enriched_title}")
            print(f"Hero Image URL: {article.hero_image_url}")
            print(f"Categories: {article.categories}")

            # Count images in content
            image_count = article.enriched_content.count("![")
            placeholder_count = article.enriched_content.count("PLACEHOLDER_IMAGE")

            print(f"Images in content: {image_count}")
            print(f"Remaining placeholders: {placeholder_count}")

            print(f"\n--- UPDATED CONTENT ---")
            print(article.enriched_content)
            print(f"--- END CONTENT ---")
    else:
        print("No articles processed")

# Agent flow:
# ArticleGeneratorAgent -> ARTICLE_IMAGE_GENERATOR_AGENT (WE ARE HERE) -> ArticleStorerAgent
