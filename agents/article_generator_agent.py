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
from schemas.news_draft import StructuredSourceArticle
from schemas.enriched_article import EnrichedArticle, ArticleReference, LocationTag
from pydantic import BaseModel


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

Produce a fully formatted article in markdown format, ready for publication.
"""


class ArticleGeneratorAgent(BaseAgent):
    """An agent that generates enriched news articles by combining original content with web search results."""

    def __init__(self, llm):
        super().__init__(llm=llm, prompt=None, name="ArticleGeneratorAgent")
        self.structured_llm = self.llm.with_structured_output(EnrichedArticle)

    def _find_original_article(self, article_id: str, articles: List[CanonicalArticle]) -> Optional[CanonicalArticle]:
        """Find the original article by its ID."""
        for article in articles:
            if article.link == article_id:
                return article
        return None

    def _format_web_search_results(self, results: List[StructuredSourceArticle], article_id: str) -> str:
        """Format web search results for the prompt."""
        # Create a list to collect relevant search results for this article
        relevant_results = []
        
        # Get summaries of the web search results relevant to this article
        for result in results:
            # Simple approach: just summarize each result
            summary = f"Source: {result.domain} - {result.url}\n"
            
            # Add a brief excerpt from the markdown (first 200 characters)
            if result.markdown:
                excerpt = result.markdown[:200] + "..." if len(result.markdown) > 200 else result.markdown
                summary += f"Excerpt: {excerpt}\n\n"
            
            relevant_results.append(summary)
        
        # Combine all results into a single string
        if relevant_results:
            return "\n".join(relevant_results)
        else:
            return "No relevant web search results were found."

    def run(self, state: AgentState) -> AgentState:
        """Runs the article generator agent on the provided state."""
        print("ArticleGeneratorAgent: Starting to generate enriched articles...")
        
        # Get the necessary data from the state
        articles = getattr(state, "articles", [])
        plans = getattr(state, "plan", [])
        web_search_results = getattr(state, "web_search_results", [])
        canonical_ids = getattr(state, "canonical_ids", {})
        
        if not articles or not plans:
            print("ArticleGeneratorAgent: No articles or plans to work with.")
            return state
        
        print(f"ArticleGeneratorAgent: Generating enriched articles for {len(plans)} plans...")
        
        # Store the generated enriched articles
        enriched_articles = []
        
        for plan in plans:
            article_id = plan.article_id
            print(f"\n  - Generating enriched article for: {article_id}")
            
            # Find the original article
            original_article = self._find_original_article(article_id, articles)
            if not original_article:
                print(f"    - Original article not found for ID: {article_id}. Skipping.")
                continue
            
            # Check if we have a canonical ID for this article
            canonical_news_id = canonical_ids.get(article_id)
            if canonical_news_id:
                print(f"    - Using canonical_news_id: {canonical_news_id}")
            else:
                print(f"    - No canonical_news_id found for article: {article_id}")
            
            # Format web search results
            formatted_results = self._format_web_search_results(web_search_results, article_id)
            
            # Collect relevant web search results for references
            relevant_search_results = []
            for result in web_search_results:
                # Only include results with meaningful content
                if result.markdown and len(result.markdown.strip()) > 50:  # Skip very short or empty results
                    relevant_search_results.append(result)
            
            # Current date in ISO format
            current_date = datetime.datetime.now().isoformat()
            
            # Format the original publication date
            published_date = (
                original_article.published_at
                if original_article.published_at 
                else "Unknown publication date"
            )
            
            # Prepare the prompt
            prompt_content = ARTICLE_GENERATION_PROMPT.format(
                original_title=original_article.title,
                original_content=original_article.content,
                published_at=published_date,
                language=getattr(original_article, "language", "en"),
                planned_headline=plan.headline,
                planned_summary=plan.summary,
                planned_keywords=", ".join(plan.keywords),
                planned_categories=", ".join(plan.categories),
                web_search_results=formatted_results
            )
            
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
                    # Debug print
                    print(f"    - Debug: Original article link type: {type(original_article.link)}")
                    
                    # Check if this URL already exists
                    original_ref_exists = any(ref.url == str(original_article.link) for ref in enriched_article.references)
                    if not original_ref_exists and original_article.link:
                        # Varmistetaan, että URL on merkkijono, ei HttpUrl-objekti
                        url_str = str(original_article.link) if hasattr(original_article.link, '__str__') else original_article.link
                        print(f"    - Debug: Original URL string is now type: {type(url_str)}")
                        
                        new_ref = ArticleReference(
                            title=original_article.title,
                            url=url_str,
                            source=original_article.source_domain
                        )
                        enriched_article.references.append(new_ref)
                        print(f"    - Added original article reference: {new_ref.url} ({type(new_ref.url)})")
                except Exception as e:
                    print(f"    - Error adding original reference: {e}")
                
                # Add web search results as references if not already there
                for result in relevant_search_results:
                    try:
                        # Debug print
                        print(f"    - Debug: Adding reference with URL type: {type(result.url)}")
                        
                        # Check if this URL already exists
                        result_exists = any(ref.url == str(result.url) for ref in enriched_article.references)
                        if not result_exists and result.url:
                            # Varmistetaan, että URL on merkkijono, ei HttpUrl-objekti
                            url_str = str(result.url) if hasattr(result.url, '__str__') else result.url
                            print(f"    - Debug: URL string is now type: {type(url_str)}")
                            
                            new_ref = ArticleReference(
                                title=f"Content from {result.domain}",
                                url=url_str,
                                source=result.domain
                            )
                            enriched_article.references.append(new_ref)
                            print(f"    - Added reference: {new_ref.url} ({type(new_ref.url)})")
                    except Exception as e:
                        print(f"    - Error adding reference: {e}")
                
                # Add the generated article to our list
                enriched_articles.append(enriched_article)
                print(f"    - Successfully generated enriched article: {enriched_article.enriched_content}")
            except Exception as e:
                print(f"    - Error generating enriched article: {e}")
        
        # Store the enriched articles in the state
        state.enriched_articles = enriched_articles
        
        print(f"\nArticleGeneratorAgent: Generated {len(enriched_articles)} enriched articles.")
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
    
    # Create a mock article plan
    class MockNewsArticlePlan(BaseModel):
        article_id: str
        headline: str
        summary: str
        keywords: List[str] = []
        categories: List[str] = []
        web_search_queries: List[str] = []
    
    # Create a mock article
    class MockCanonicalArticle(BaseModel):
        title: str
        link: str
        content: str
        published_at: str
        language: str
        source_domain: str
    
    # Create test data
    test_article = MockCanonicalArticle(
        title="Finland's AI Strategy",
        link="http://test.fi/suomi-ai",
        content="Finland aims to be a leader in AI. The government has announced plans to invest in AI research and education.",
        published_at="2023-01-15",
        language="en",
        source_domain="test.fi"
    )
    
    test_plan = MockNewsArticlePlan(
        article_id="http://test.fi/suomi-ai",
        headline="Finland Expands Its AI Leadership with New Investments",
        summary="Finland is strengthening its position in AI through increased funding and education initiatives.",
        keywords=["Finland", "AI", "investment", "education", "technology"],
        categories=["Technology", "Politics", "Education"],
        web_search_queries=["Finland AI strategy latest developments", "AI education programs Finland"]
    )
    
    # Mock web search result
    test_web_result = StructuredSourceArticle(
        url="https://example.com/finland-ai",
        domain="example.com",
        markdown="Finland has announced a new 100 million euro investment in AI research centers. The initiative will focus on developing ethical AI applications in healthcare and education sectors.",
        content_blocks=[]
    )
    
    # Set up mock state
    class MockAgentState:
        def __init__(self):
            self.articles = [test_article]
            self.plan = [test_plan]
            self.web_search_results = [test_web_result]
            self.enriched_articles = []
            self.canonical_ids = {
                "http://test.fi/suomi-ai": "finland-ai-2023"
            }
    
    # Create and run the agent
    generator_agent = ArticleGeneratorAgent(llm)
    initial_state = MockAgentState()
    
    print("\n--- Invoking the agent's run method... ---")
    result_state = generator_agent.run(initial_state)
    print("--- Agent run completed. ---")
    
    print("\n--- Results ---")
    print(f"Enriched articles in state: {len(getattr(result_state, 'enriched_articles', []))}")
    
    # Display the first enriched article if any were generated
    enriched_articles = getattr(result_state, 'enriched_articles', [])
    if enriched_articles:
        article = enriched_articles[0]
        print("\nFirst Enriched Article:")
        print(f"Title: {article.enriched_title}")
        print(f"Content (first 200 chars): {article.enriched_content[:200]}...")
        print(f"Sources: {', '.join(article.sources)}")
