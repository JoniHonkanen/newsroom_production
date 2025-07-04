# File: agents/article_generator_agent.py

import sys
import os
import datetime
from typing import List, Dict, Optional

# Add the project root to the Python path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.feed_schema import CanonicalArticle
from schemas.article_plan_schema import NewsArticlePlan
from schemas.parsed_article import ParsedArticle
from schemas.enriched_article import EnrichedArticle, ArticleReference, LLMArticleOutput


ARTICLE_GENERATION_PROMPT = """
You are an expert news editor and content creator. Your task is to create an enriched version of a news article by combining the original article with additional web search results.

**Original Article Information:**
- Content: {original_content}
- Published: {published_at}
- Language: {language}

**Plans for Enrichment:**
- Keywords: {planned_keywords}
- Categories: {planned_categories}

**Web Search Results:**
{web_search_results}

**Your Task:**
1. Create an enriched version of the article that expands on the original content using information from the web search results.
2. Maintain the same language as the original article ({language}), this is important!.
3. Write in a professional, journalistic style that matches the original tone.
4. Incorporate relevant information from the web search results to add depth, context, and new perspectives.
5. Structure the article with appropriate headings, paragraphs, and a logical flow.
6. Keep the enriched content comprehensive but concise, with a focus on quality over quantity.
7. Make sure to maintain factual accuracy and journalistic integrity.
8. Tell the news story in your own words while preserving the original meaning and key facts.

Produce a fully formatted article in markdown format, ready for publication.
"""


class ArticleGeneratorAgent(BaseAgent):
    """An agent that generates enriched news articles by combining original content with web search results."""

    def __init__(self, llm):
        super().__init__(llm=llm, prompt=None, name="ArticleGeneratorAgent")
        self.structured_llm = self.llm.with_structured_output(LLMArticleOutput)

    def _find_original_article(
        self, article_id: str, articles: List[CanonicalArticle]
    ) -> Optional[CanonicalArticle]:
        """Find the original article by its unique_id or link."""
        for article in articles:
            if (article.unique_id and article.unique_id == article_id) or (
                article.link == article_id
            ):
                return article
        return None

    def _format_web_search_results(self, results: List[ParsedArticle]) -> str:
        """Format web search results for the prompt."""
        if not results:
            return "No relevant web search results were found."

        formatted_results = []

        for i, result in enumerate(results, 1):
            article_section = f"--- Search Result {i} ---\n"
            article_section += f"Source: {result.domain}\n"

            if result.markdown:
                max_content_length = 2000
                content = (
                    result.markdown[:max_content_length] + "...[content truncated]"
                    if len(result.markdown) > max_content_length
                    else result.markdown
                )
                article_section += f"Content:\n{content}\n"

            article_section += f"--- End of Search Result {i} ---\n"
            formatted_results.append(article_section)

        return "\n\n".join(formatted_results)

    def run(self, state: AgentState) -> AgentState:
        """Runs the article generator agent on the provided state."""
        print("ArticleGeneratorAgent: Starting to generate enriched articles...")

        # Get data from state
        articles = state.articles
        plan_dicts = state.plan or []
        article_search_map = state.article_search_map
        canonical_ids = state.canonical_ids

        # Convert plan dicts back to NewsArticlePlan objects
        plans = [NewsArticlePlan(**plan_dict) for plan_dict in plan_dicts]

        if not articles or not plans:
            print("ArticleGeneratorAgent: No articles or plans to work with.")
            return state

        print(
            f"ArticleGeneratorAgent: Generating enriched articles for {len(plans)} plans..."
        )

        enriched_articles: List[EnrichedArticle] = []

        for plan in plans:
            article_id = plan.article_id
            print(f"\n  - Generating enriched article for: {article_id}")

            # Find the original article
            original_article = self._find_original_article(article_id, articles)
            if not original_article:
                print(
                    f"    - Original article not found for ID: {article_id}. Skipping."
                )
                continue

            # Get canonical ID
            canonical_news_id = canonical_ids.get(article_id)
            if canonical_news_id:
                print(f"    - Using canonical_news_id: {canonical_news_id}")

            # Get web search results for this article
            web_search_results = article_search_map.get(article_id, [])
            print(
                f"    - Found {len(web_search_results)} web search results for this article"
            )

            # Format web search results
            formatted_results = self._format_web_search_results(web_search_results)

            # Prepare the prompt
            prompt_content = ARTICLE_GENERATION_PROMPT.format(
                original_content=original_article.content or "",
                published_at=original_article.published_at
                or "Unknown publication date",
                language=original_article.language or "en",
                planned_keywords=", ".join(plan.keywords),
                planned_categories=", ".join(plan.categories),
                web_search_results=formatted_results,
            )

            try:
                # Generate using the simplified schema
                llm_output = self.structured_llm.invoke(prompt_content)

                # Create references from web search results
                article_references = []

                # Add original article as reference
                if original_article.link:
                    original_ref = ArticleReference(
                        title=original_article.title,
                        url=str(original_article.link),
                    )
                    article_references.append(original_ref)

                # Add web search results as references
                for result in web_search_results:
                    if (
                        result.url
                        and result.markdown
                        and len(result.markdown.strip()) > 50
                    ):
                        new_ref = ArticleReference(
                            title=f"Content from {result.domain}",
                            url=result.url,
                        )
                        article_references.append(new_ref)

                published_at_str = ""
                if original_article.published_at:
                    if isinstance(original_article.published_at, str):
                        published_at_str = original_article.published_at
                    else:
                        # Muunna datetime-objekti merkkijonoksi
                        published_at_str = original_article.published_at.isoformat()

                # Create the complete EnrichedArticle
                enriched_article = EnrichedArticle(
                    article_id=article_id,
                    canonical_news_id=canonical_news_id,
                    enriched_title=llm_output.enriched_title,
                    enriched_content=llm_output.enriched_content,
                    published_at=published_at_str,
                    source_domain=original_article.source_domain or "",
                    keywords=llm_output.keywords,
                    categories=plan.categories if hasattr(plan, "categories") else [],
                    language=original_article.language or "en",
                    sources=[
                        result.url
                        for result in web_search_results
                        if hasattr(result, "url")
                    ],
                    references=article_references,
                    locations=llm_output.locations,
                    summary=llm_output.summary,
                    enrichment_status="success",
                )

                enriched_articles.append(enriched_article)
                print(f"    - Successfully generated enriched article")

            except Exception as e:
                print(f"    - Error generating enriched article: {e}")

        state.enriched_articles = enriched_articles
        return state


# ======================================================================
# Standalone Test Runner
# ======================================================================
if __name__ == "__main__":
    from dotenv import load_dotenv
    from langchain.chat_models import init_chat_model

    print("--- Running ArticleGeneratorAgent in isolation for testing ---")
    load_dotenv()

    # Initialize the LLM
    llm = init_chat_model("gpt-4o-mini", model_provider="openai")

    # Create test data
    test_article = CanonicalArticle(
        title="Finland's AI Strategy",
        link="http://test.fi/suomi-ai",
        unique_id="test-finland-ai",
        content="Finland aims to be a leader in AI.",
        published_at="2023-01-15",
        language="en",
        source_domain="test.fi",
    )

    test_plan_dict = {
        "article_id": "test-finland-ai",
        "headline": "Finland Expands AI Leadership",
        "summary": "Finland strengthens AI position",
        "keywords": ["Finland", "AI"],
        "categories": ["Technology"],
        "web_search_queries": ["Finland AI strategy"],
    }

    test_web_result = ParsedArticle(
        markdown="Finland announced 100M euro AI investment.",
        domain="example.com",
        url="https://example.com/finland-ai",
    )

    # Mock state
    class MockAgentState:
        def __init__(self):
            self.articles = [test_article]
            self.plan = [test_plan_dict]
            self.article_search_map = {"test-finland-ai": [test_web_result]}
            self.enriched_articles = []
            self.canonical_ids = {"test-finland-ai": 123}

    # Test
    generator_agent = ArticleGeneratorAgent(llm)
    result_state = generator_agent.run(MockAgentState())

    print(f"Generated {len(result_state.enriched_articles)} enriched articles")
