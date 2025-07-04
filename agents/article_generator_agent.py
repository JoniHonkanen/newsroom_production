# File: agents/article_generator_agent.py

import sys
import os
import datetime
from typing import List, Dict, Optional, Any

# Add the project root to the Python path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.feed_schema import CanonicalArticle
from schemas.article_plan_schema import NewsArticlePlan
from schemas.parsed_article import ParsedArticle
from schemas.enriched_article import EnrichedArticle, ArticleReference, LocationTag


ARTICLE_GENERATION_PROMPT = """
You are an expert news editor and content creator. Your task is to create an enriched version of a news article by combining the original article with additional web search results.

**Original Article Information:**
- Title: {original_title}
- Content: {original_content}
- Published: {published_at}
- Language: {language}

**Plans for Enrichment:**
- New Suggested Headline: {planned_headline}
- Summary: {planned_summary}
- Keywords: {planned_keywords}
- Categories: {planned_categories}

**Web Search Results:**
{web_search_results}

**Your Task:**
1. Create an enriched version of the article that expands on the original content using information from the web search results.
2. Maintain the same language as the original article ({language}).
3. Write in a professional, journalistic style that matches the original tone.
4. Incorporate relevant information from the web search results to add depth, context, and new perspectives.
5. Structure the article with appropriate headings, paragraphs, and a logical flow.
6. Keep the enriched content comprehensive but concise, with a focus on quality over quantity.
7. Make sure to maintain factual accuracy and journalistic integrity.
8. Identify any relevant geographic locations mentioned in the article (continent, country, region, and city).
9. Include references to any other articles that you mention in your content.
10. Tell the news story in your own words while preserving the original meaning and key facts.

Produce a fully formatted article in markdown format, ready for publication.
"""


class ArticleGeneratorAgent(BaseAgent):
    """An agent that generates enriched news articles by combining original content with web search results."""

    def __init__(self, llm):
        super().__init__(llm=llm, prompt=None, name="ArticleGeneratorAgent")
        self.structured_llm = self.llm.with_structured_output(EnrichedArticle)

    def _find_original_article(
        self, article_id: str, articles: List[CanonicalArticle]
    ) -> Optional[CanonicalArticle]:
        """Find the original article by its unique_id or link."""
        for article in articles:
            # Try both unique_id and link
            if (article.unique_id and article.unique_id == article_id) or (
                article.link == article_id
            ):
                return article
        return None

    def _format_web_search_results(
        self, results: List[ParsedArticle], article_id: str
    ) -> str:
        """Format web search results for the prompt."""
        if not results:
            return "No relevant web search results were found."

        formatted_results = []

        # Format each result with clear separation
        for i, result in enumerate(results, 1):
            article_section = f"--- Search Result {i} ---\n"
            article_section += f"Source: {result.domain}\n"

            # Add the full markdown content (with reasonable limit for very long articles)
            if result.markdown:
                max_content_length = 2000  # Reasonable limit while preserving context
                content = (
                    result.markdown[:max_content_length] + "...[content truncated]"
                    if len(result.markdown) > max_content_length
                    else result.markdown
                )
                article_section += f"Content:\n{content}\n"

            article_section += f"--- End of Search Result {i} ---\n"
            formatted_results.append(article_section)

        # Combine all results with clear separation
        return "\n\n".join(formatted_results)

    def run(self, state: AgentState) -> AgentState:
        """Runs the article generator agent on the provided state."""
        print("ArticleGeneratorAgent: Starting to generate enriched articles...")

        # Get the necessary data from the state - use direct access
        articles = state.articles
        plan_dicts = state.plan or []
        article_search_map = getattr(state, "article_search_map", {})
        canonical_ids = getattr(state, "canonical_ids", {})

        # Convert plan dicts back to NewsArticlePlan objects
        plans = [NewsArticlePlan(**plan_dict) for plan_dict in plan_dicts]

        if not articles or not plans:
            print("ArticleGeneratorAgent: No articles or plans to work with.")
            return state

        print(
            f"ArticleGeneratorAgent: Generating enriched articles for {len(plans)} plans..."
        )

        # Store the generated enriched articles
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

            # Check if we have a canonical ID for this article
            canonical_news_id = canonical_ids.get(article_id)
            if canonical_news_id:
                print(f"    - Using canonical_news_id: {canonical_news_id}")
            else:
                print(f"    - No canonical_news_id found for article: {article_id}")

            # Get web search results for this specific article
            web_search_results = article_search_map.get(article_id, [])
            print(
                f"    - Found {len(web_search_results)} web search results for this article"
            )

            # Format web search results
            formatted_results = self._format_web_search_results(
                web_search_results, article_id
            )

            # Filter relevant web search results for references
            relevant_search_results = [
                result
                for result in web_search_results
                if result.markdown and len(result.markdown.strip()) > 50
            ]

            # Format the original publication date
            published_date = (
                original_article.published_at
                if original_article.published_at
                else "Unknown publication date"
            )

            # Prepare the prompt
            prompt_content = ARTICLE_GENERATION_PROMPT.format(
                original_title=original_article.title,
                original_content=original_article.content or "",
                published_at=published_date,
                language=original_article.language or "en",
                planned_headline=plan.headline,
                planned_summary=plan.summary,
                planned_keywords=", ".join(plan.keywords),
                planned_categories=", ".join(plan.categories),
                web_search_results=formatted_results,
            )

            print("\n****TÄÄ TÄÄ TÄÄ***")
            print(prompt_content)

            try:
                # Generate the enriched article
                enriched_article = self.structured_llm.invoke(prompt_content)

                # Add canonical_news_id if available
                if canonical_news_id:
                    enriched_article.canonical_news_id = canonical_news_id

                # Ensure we have a references list
                if not enriched_article.references:
                    enriched_article.references = []

                # Add the original article as a reference if not already there
                try:
                    original_ref_exists = any(
                        ref.url == str(original_article.link)
                        for ref in enriched_article.references
                    )
                    if not original_ref_exists and original_article.link:
                        url_str = str(original_article.link)

                        new_ref = ArticleReference(
                            title=original_article.title,
                            url=url_str,
                        )
                        enriched_article.references.append(new_ref)
                        print(f"    - Added original article reference: {new_ref.url}")
                except Exception as e:
                    print(f"    - Error adding original reference: {e}")

                # Add web search results as references if not already there
                for result in relevant_search_results:
                    try:
                        # ParsedArticle doesn't have url, so we'll need to handle this differently
                        # For now, we'll create a reference using domain info
                        result_exists = any(
                            ref.source == result.domain
                            for ref in enriched_article.references
                        )
                        if not result_exists and result.domain:
                            new_ref = ArticleReference(
                                title=f"Content from {result.domain}",
                                url=f"https://{result.domain}",
                            )
                            enriched_article.references.append(new_ref)
                            print(f"    - Added reference: {new_ref.url}")
                    except Exception as e:
                        print(f"    - Error adding reference: {e}")

                # Add the generated article to our list
                enriched_articles.append(enriched_article)
                print(
                    f"    - Successfully generated enriched article with {len(enriched_article.enriched_content)} chars"
                )
            except Exception as e:
                print(f"    - Error generating enriched article: {e}")

        # Store the enriched articles in the state
        state.enriched_articles = enriched_articles

        print(
            f"\nArticleGeneratorAgent: Generated {len(enriched_articles)} enriched articles."
        )
        print("ArticleGeneratorAgent: Done.")
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

    # Create test data using real schemas
    test_article = CanonicalArticle(
        title="Finland's AI Strategy",
        link="http://test.fi/suomi-ai",
        unique_id="test-finland-ai",
        content="Finland aims to be a leader in AI. The government has announced plans to invest in AI research and education.",
        published_at="2023-01-15",
        language="en",
        source_domain="test.fi",
    )

    test_plan_dict = {
        "article_id": "test-finland-ai",
        "headline": "Finland Expands Its AI Leadership with New Investments",
        "summary": "Finland is strengthening its position in AI through increased funding and education initiatives.",
        "keywords": ["Finland", "AI", "investment", "education", "technology"],
        "categories": ["Technology", "Politics", "Education"],
        "web_search_queries": [
            "Finland AI strategy latest developments",
            "AI education programs Finland",
        ],
    }

    # Mock web search result
    test_web_result = ParsedArticle(
        markdown="Finland has announced a new 100 million euro investment in AI research centers. The initiative will focus on developing ethical AI applications in healthcare and education sectors.",
        domain="example.com",
    )

    # Set up mock state
    class MockAgentState:
        def __init__(self):
            self.articles = [test_article]
            self.plan = [test_plan_dict]  # List of dicts as it comes from LangGraph
            self.article_search_map = {"test-finland-ai": [test_web_result]}
            self.enriched_articles = []
            self.canonical_ids = {"test-finland-ai": 123}

    # Create and run the agent
    generator_agent = ArticleGeneratorAgent(llm)
    initial_state = MockAgentState()

    print("\n--- Invoking the agent's run method... ---")
    result_state = generator_agent.run(initial_state)
    print("--- Agent run completed. ---")

    print("\n--- Results ---")
    print(
        f"Enriched articles in state: {len(getattr(result_state, 'enriched_articles', []))}"
    )

    # Display the first enriched article if any were generated
    enriched_articles = getattr(result_state, "enriched_articles", [])
    if enriched_articles:
        article = enriched_articles[0]
        print("\nFirst Enriched Article:")
        print(f"Title: {article.enriched_title}")
        print(f"Content (first 200 chars): {article.enriched_content[:200]}...")
        if hasattr(article, "sources"):
            print(f"Sources: {', '.join(article.sources)}")
        print(f"References: {len(article.references)}")
