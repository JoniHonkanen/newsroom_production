# File: agents/web_search_agent.py

import sys
import os
import time
from typing import List, Optional, Any

from schemas.news_draft import StructuredSourceArticle

# Add project root to path for standalone testing
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState

from duckduckgo_search import DDGS  # type: ignore
from duckduckgo_search.exceptions import (  # type: ignore
    DuckDuckGoSearchException,
)
from services.article_parser import to_structured_article


class WebSearchAgent(BaseAgent):
    """
    An agent that performs web searches and returns a structured list of found articles.
    """

    def __init__(self, max_results_per_query: int = 2):
        super().__init__(llm=None, prompt=None, name="WebSearchAgent")
        self.max_results = max_results_per_query

    def _safe_search(self, ddgs_client: DDGS, query: str) -> List[dict]:
        """
        Performs a search query with exponential backoff for rate limit errors.
        """
        retries = 3
        for attempt in range(retries):
            try:
                print(f"    - Executing query: '{query}'")
                results = ddgs_client.text(query, max_results=self.max_results)
                return list(results)
            except DuckDuckGoSearchException as e:
                if "Ratelimit" in str(e) and attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"    - Rate limit hit. Retrying in {wait} seconds...")
                    time.sleep(wait)
                else:
                    print(f"    - CRITICAL: Search failed for query '{query}': {e}")
                    return []
        return []

    def _fetch_search_result_content(
        self, url: str
    ) -> Optional[StructuredSourceArticle]:
        """
        Fetches and parses content from a single URL using the robust Trafilatura parser.
        """
        try:
            print(f"      - Fetching and parsing: {url}")
            structured_article = to_structured_article(url)
            if structured_article and structured_article.markdown:
                # This function now returns the full structured object
                return structured_article
            return None
        except Exception as e:
            print(f"        - Failed to fetch or parse {url}: {e}")
            return None

    def run(self, state: AgentState) -> AgentState:
        """Runs the web search agent on the provided state."""
        # Haetaan suunnitelmat state.plan-kentästä
        plans = getattr(state, "plan", [])
        if not plans:
            print("WebSearchAgent: No article plans to search for.")
            return state

        print(f"WebSearch-DDG: Performing web search for {len(plans)} article plans...")
        # Säilytetään alkuperäiset artikkelit muuttumattomina
        all_web_search_results = []  # Kerätään kaikki hakutulokset tänne

        # Käytämme tätä pitämään kirjaa, mikä hakutulos liittyy mihin artikkeliin
        article_search_map = {}  # key: article_id, value: List[StructuredSourceArticle]

        with DDGS() as ddgs:
            for plan in plans:
                article_id = plan.article_id
                search_queries = plan.web_search_queries
                if not search_queries:
                    print(f"  - No search queries for article: {article_id}. Skipping.")
                    continue

                print(f"  - Searching for: {article_id}")
                print(f"    - Queries: {search_queries}")

                # Alustetaan tämän artikkelin hakutuloslista, jos sitä ei vielä ole
                if article_id not in article_search_map:
                    article_search_map[article_id] = []

                # Käytetään vain ensimmäistä hakukyselyä
                if search_queries:
                    query = search_queries[0]  # Otetaan vain ensimmäinen kysely
                    print(f"    - Using only the first query: '{query}'")

                    search_results = self._safe_search(ddgs, query)

                    for result in search_results:
                        url = result.get("href")
                        if not url:
                            continue

                        try:
                            # Parser palauttaa koko strukturoidun objektin
                            structured_article = self._fetch_search_result_content(url)
                            if structured_article:
                                # Lisätään hakutulos sekä kokonaislistaan että artikkelikohtaiseen listaan
                                all_web_search_results.append(structured_article)
                                article_search_map[article_id].append(
                                    structured_article
                                )
                        except Exception as e:
                            print(f"        - Failed to process URL {url}: {e}")

                    time.sleep(1.0)  # Kohtelias viive hakujen välissä

        # Tallennetaan hakutulokset web_search_results kenttään
        state.web_search_results = all_web_search_results

        # Päivitetään suunnitelmat hakutuloksilla
        for i, plan in enumerate(state.plan):
            article_id = plan.article_id
            if article_id in article_search_map:
                # Emme voi muokata plan-objektia suoraan, joten luomme uuden listan
                # joka korvaa vanhan state.plan-kentässä
                if i == 0:  # Vain ensimmäisellä kierroksella
                    new_plans = []

                # Luodaan hakutuloslista tälle artikkelille
                search_results = article_search_map[article_id]

                # Tässä haluaisimme päivittää plan-objektia, mutta koska Pydantic
                # objekteissa ei ole helposti muokattavia web_search_results -kenttiä,
                # pidämme hakutulokset erillisessä article_search_map-rakenteessa.

                new_plans.append(plan)

        print(
            f"\nLöytyi yhteensä {len(all_web_search_results)} hakutulosta {len(article_search_map)} artikkelille"
        )
        print("WebSearchAgent: Done.")
        return state


# ======================================================================
# Standalone Test Runner
# ======================================================================
if __name__ == "__main__":
    from dotenv import load_dotenv
    import datetime
    from pydantic import BaseModel

    print("--- Running WebSearchAgent (Direct DDGS) in isolation for testing ---")
    load_dotenv()

    # Luodaan testidataa, joka vastaa NewsArticlePlan-objekteja
    class MockNewsArticlePlan(BaseModel):
        article_id: str
        headline: str = ""
        summary: str = ""
        keywords: List[str] = []
        categories: List[str] = []
        web_search_queries: List[str] = []

    # Luodaan testidataa
    test_plans = [
        MockNewsArticlePlan(
            article_id="http://test.fi/suomi-ai",
            headline="Finland's AI Strategy",
            summary="Finland aims to be a leader in AI.",
            keywords=["Finland", "AI", "strategy", "technology"],
            categories=["Technology", "Politics"],
            web_search_queries=[
                "Finland national AI strategy latest updates",
                "AI research centers in Finland",
            ],
        )
    ]
    print(f"Created {len(test_plans)} mock article plans with search queries.")

    class MockAgentState:
        def __init__(self, plan):
            self.articles = []  # Artikkelita ei tarvitse testiajossa
            self.web_search_results = []
            self.plan = plan

    search_agent = WebSearchAgent()
    initial_state = MockAgentState(plan=test_plans)

    print("\n--- Invoking the agent's run method... ---")
    result_state = search_agent.run(initial_state)
    print("--- Agent run completed. ---")

    print("\n--- Results ---")
    print(f"Web search results in state: {len(result_state.web_search_results)}")

    # Tulostetaan hakutulokset artikkeleittain
    article_search_map = {}
    for result in result_state.web_search_results:
        # Yksinkertaistuksen vuoksi käytetään domain-kenttää ryhmittelyyn
        domain = result.domain
        if domain not in article_search_map:
            article_search_map[domain] = []
        article_search_map[domain].append(result)

    for domain, results in article_search_map.items():
        print(f"\nDomain {domain} has {len(results)} search results:")
        for i, result in enumerate(results):
            lang = getattr(result, "language", "N/A")
            print(f"  {i+1}. {result.url} (Lang: {lang})")
