# File: agents/selenium_web_search_agent.py

import sys
import os
import time
from typing import List, Optional, Tuple
import re
from urllib.parse import quote_plus
import random

# Add project root to path for standalone testing
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.article_plan_schema import NewsArticlePlan
from schemas.parsed_article import ParsedArticle

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager

from services.article_parser import to_structured_article


class SeleniumSearchClient:
    """
    A robust search client using Selenium with multiple search engine fallbacks.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        # List of search engines to try in order
        self.search_engines = [
            {
                "name": "DuckDuckGo",
                "url": "https://duckduckgo.com",
                "search_url": "https://duckduckgo.com/?q={}",
                "search_box": (By.NAME, "q"),
                "results": (By.CSS_SELECTOR, "[data-testid='result']"),
                "title": (By.CSS_SELECTOR, "h2 a"),
                "link": (By.CSS_SELECTOR, "h2 a"),
                "snippet": (By.CSS_SELECTOR, "[data-result='snippet']"),
            },
            {
                "name": "Bing",
                "url": "https://www.bing.com",
                "search_url": "https://www.bing.com/search?q={}",
                "search_box": (By.NAME, "q"),
                "results": (By.CSS_SELECTOR, "li.b_algo"),
                "title": (By.CSS_SELECTOR, "h2 a"),
                "link": (By.CSS_SELECTOR, "h2 a"),
                "snippet": (By.CSS_SELECTOR, ".b_caption p"),
            },
            {
                "name": "Google",
                "url": "https://www.google.com",
                "search_url": "https://www.google.com/search?q={}",
                "search_box": (By.NAME, "q"),
                "results": (By.CSS_SELECTOR, "div.g"),
                "title": (By.CSS_SELECTOR, "h3"),
                "link": (By.CSS_SELECTOR, "a"),
                "snippet": (By.CSS_SELECTOR, "div.VwiC3b, span.aCOpRe, div.IsZvec"),
            },
        ]

    def __enter__(self):
        """Context manager entry - initializes the driver"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920,1080")

        # Rotate user agents to avoid detection
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        chrome_options.add_argument(f"user-agent={random.choice(user_agents)}")

        # Performance optimizations
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.stylesheet": 2,
            "profile.default_content_setting_values.media_stream": 2,
            "profile.default_content_setting_values.plugins": 2,
            "profile.default_content_setting_values.popups": 2,
            "profile.default_content_setting_values.geolocation": 2,
            "profile.default_content_setting_values.notifications": 2,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_page_load_timeout(15)  # Shorter timeout
            self.driver.implicitly_wait(3)  # Add implicit wait

            # Execute JavaScript to hide webdriver detection
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            print("    - Selenium Chrome driver initialized successfully")
        except Exception as e:
            print(f"    - Failed to initialize Chrome driver: {e}")
            raise

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes the driver"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass

    def text(self, query: str, max_results: int = 10) -> Tuple[List[dict], str]:
        """
        Performs a web search with fallback to multiple search engines.

        Returns:
            Tuple of (results_list, status_string)
        """
        if not self.driver:
            return [], "error"

        results = []

        # Try each search engine until one works
        for engine in self.search_engines:
            try:
                print(f"    - Trying {engine['name']} search for: '{query}'")
                results = self._search_with_engine(engine, query, max_results)
                if results:
                    print(
                        f"    - {engine['name']} search SUCCESS: found {len(results)} results"
                    )
                    return results, "success"
            except TimeoutException:
                print(f"    - {engine['name']} timeout, trying next engine...")
                continue
            except Exception as e:
                print(
                    f"    - {engine['name']} error: {type(e).__name__}, trying next engine..."
                )
                continue

        # If all engines failed
        print(f"    - All search engines failed for query: '{query}'")
        return [], "search_failed"

    def _search_with_engine(
        self, engine: dict, query: str, max_results: int
    ) -> List[dict]:
        """Search using a specific search engine configuration."""
        results = []

        # Navigate directly to search URL (faster than filling form)
        search_url = engine["search_url"].format(quote_plus(query))
        self.driver.get(search_url)

        # Wait for results with shorter timeout
        wait = WebDriverWait(self.driver, 8)
        try:
            wait.until(EC.presence_of_element_located(engine["results"]))
        except TimeoutException:
            # Try alternative approach - check if page loaded at all
            if "captcha" in self.driver.page_source.lower():
                print(f"      - CAPTCHA detected on {engine['name']}")
                raise
            # Sometimes results load but selector changes
            time.sleep(2)

        # Find search results
        result_elements = self.driver.find_elements(*engine["results"])[:max_results]

        if not result_elements:
            print(f"      - No results found on {engine['name']}")
            return []

        for i, element in enumerate(result_elements):
            try:
                # Extract URL
                link_element = element.find_element(*engine["link"])
                url = link_element.get_attribute("href")

                # Skip internal links
                if not url or engine["url"] in url:
                    continue

                # Extract title
                try:
                    title_element = element.find_element(*engine["title"])
                    title = title_element.text
                except:
                    title = "No title"

                # Extract snippet (not critical if fails)
                snippet = ""
                try:
                    snippet_element = element.find_element(*engine["snippet"])
                    snippet = snippet_element.text
                except:
                    snippet = f"Search result for: {query}"

                if url and title:
                    results.append({"title": title, "href": url, "body": snippet})

            except Exception as e:
                # Skip problematic results
                continue

        return results


class WebSearchAgent(BaseAgent):
    """
    A robust web search agent using Selenium with fallback search engines.
    """

    def __init__(self, max_results_per_query: int = 2, headless: bool = True):
        super().__init__(llm=None, prompt=None, name="SeleniumWebSearchAgent")
        self.max_results = max_results_per_query
        self.headless = headless

    def _safe_search(
        self, selenium_client: SeleniumSearchClient, query: str
    ) -> Tuple[List[dict], str]:
        """
        Performs a search query with error handling.
        Returns (results, status)
        """
        try:
            print(f"    - Executing search query: '{query}'")
            results, status = selenium_client.text(query, max_results=self.max_results)
            return results, status
        except Exception as e:
            print(f"    - CRITICAL: Search failed for query '{query}': {e}")
            return [], "error"

    def _fetch_search_result_content(self, url: str) -> Optional[ParsedArticle]:
        """
        Fetches and parses content from a single URL using the robust Trafilatura parser.
        """
        try:
            print(f"      - Fetching and parsing: {url}")
            parsed_article = to_structured_article(url)
            if parsed_article and parsed_article.markdown:
                return parsed_article
            return None
        except Exception as e:
            print(f"        - Failed to fetch or parse {url}: {e}")
            return None

    def run(self, state: AgentState) -> AgentState:
        """Runs the web search agent on the provided state."""
        # Käytä suoraan state.plan - nyt tyyppi on oikea!
        plan_dicts = state.plan or []
        plans = [NewsArticlePlan(**plan_dict) for plan_dict in plan_dicts]
        if not plans:
            print("SeleniumWebSearchAgent: No article plans to search for.")
            return state

        print(
            f"SeleniumWebSearch: Performing web search for {len(plans)} article plans..."
        )

        # Vain linkitys-mäppäys - ei erillistä "all" listaa
        article_search_map: dict[str, List[ParsedArticle]] = {}

        try:
            with SeleniumSearchClient(headless=self.headless) as selenium_client:
                for plan in plans:
                    article_id = plan.article_id
                    search_queries = plan.web_search_queries

                    if not search_queries:
                        print(
                            f"  - No search queries for article: {article_id}. Skipping."
                        )
                        continue

                    print(f"  - Searching for: {article_id}")
                    print(f"    - Queries: {search_queries}")

                    # Alusta lista tälle article_id:lle
                    article_search_map[article_id] = []

                    # Use only the first query
                    if search_queries:
                        query = search_queries[0]
                        print(f"    - Using first query: '{query}'")

                        search_results, status = self._safe_search(
                            selenium_client, query
                        )

                        for result in search_results:
                            url = result.get("href")
                            if not url:
                                continue

                            try:
                                parsed_article = self._fetch_search_result_content(url)
                                if parsed_article:
                                    article_search_map[article_id].append(
                                        parsed_article
                                    )
                            except Exception as e:
                                print(f"        - Failed to process URL {url}: {e}")

                        # Respectful delay between searches
                        time.sleep(random.uniform(2.0, 4.0))

        except Exception as e:
            print(f"SeleniumWebSearchAgent: Critical error during search: {e}")

        # Tallenna vain linkitys-mäppäys
        state.article_search_map = article_search_map

        total_results = sum(len(results) for results in article_search_map.values())
        print(
            f"\nFound {total_results} search results for {len(article_search_map)} articles"
        )
        print("SeleniumWebSearchAgent: Done.")
        return state


# ======================================================================
# Standalone Test Runner
# ======================================================================
if __name__ == "__main__":
    from dotenv import load_dotenv
    import datetime
    from pydantic import BaseModel
    from schemas.article_plan_schema import NewsArticlePlan

    print("--- Running SeleniumWebSearchAgent in isolation for testing ---")
    load_dotenv()

    # Test with multiple queries to see fallback behavior
    test_plans = [
        NewsArticlePlan(
            article_id="test-suomi-ai",
            headline="Finland's AI Strategy",
            summary="Finland aims to be a leader in AI.",
            keywords=["Finland", "AI", "strategy", "technology"],
            categories=["Technology", "Politics"],
            web_search_queries=[
                "Finland national AI strategy 2024 latest updates",
                "Finnish artificial intelligence research centers",
            ],
        )
    ]

    class MockAgentState:
        def __init__(self, plan):
            self.articles = []
            self.article_search_map = {}
            self.plan = plan

    search_agent = WebSearchAgent(headless=True)
    initial_state = MockAgentState(plan=test_plans)

    print("\n--- Invoking the agent's run method... ---")
    result_state = search_agent.run(initial_state)
    print("--- Agent run completed. ---")

    print("\n--- Results ---")
    total_results = sum(
        len(results) for results in result_state.article_search_map.values()
    )
    print(f"Article search map: {len(result_state.article_search_map)} articles")
    print(f"Total search results: {total_results}")

    # Print detailed results
    for article_id, results in result_state.article_search_map.items():
        print(f"\n- Article ID: {article_id}")
        print(f"  Found {len(results)} search results:")
        for result in results:
            print(f"    - {result.domain}: {result.markdown[:100]}...")
