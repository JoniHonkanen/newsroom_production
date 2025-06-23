from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState

from services.article_parser import to_structured_article


class ArticleContentExtractorAgent(BaseAgent):
    def __init__(self):
        super().__init__(llm=None, prompt=None, name="ArticleContentExtractorAgent")

    def run(self, state: AgentState) -> AgentState:
        articles = getattr(state, "articles", [])
        if not articles:
            print("ArticleContentExtractorAgent: No new articles to process.")
            return state

        print(
            f"ArticleContentExtractorAgent: Fetching content for {len(articles)} articles..."
        )
        enriched_articles = []
        for art in articles:
            url = art.get("link")
            if not url:
                print("No URL found for article, skipping.")
                continue
            #This function fetches the article content and returns a structured representation
            structured = to_structured_article(url)
            if structured is None:
                print(f"Failed to fetch article content: {url}")
                continue

            # Yhdistä uutisen alkuperäiset kentät ja uusi rakenne (voit säilyttää summaryn yms.)
            enriched = {
                **art,
                "structured_article": structured,
                "content": structured.markdown,  # esim. markdown tallennukseen
                "published_at": structured.published or art.get("published"),
                "source_domain": structured.domain,
            }
            enriched_articles.append(enriched)
        state.articles = enriched_articles
        print("ArticleContentExtractorAgent: Done.")
        return state
