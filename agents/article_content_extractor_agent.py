from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState

from services.article_parser import to_structured_article


class ArticleContentExtractorAgent(BaseAgent):
    """Agent that fetches articles."""

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
        handled_articles = []
        for art in articles:
            url = art.get("link")
            if not url:
                print("No URL found for article, skipping.")
                continue
            # This function fetches the article content and returns a structured representation
            # this includes parsing html elements and converting them to markdown
            structured = to_structured_article(url)
            if structured is None:
                print(f"Failed to fetch article content: {url}")
                continue

            # Yhdistä uutisen alkuperäiset kentät ja uusi rakenne (voit säilyttää summaryn yms.)
            single_article = {
                **art,
                "structured_article": structured,
                "content": structured.markdown,  # esim. markdown tallennukseen
                "published_at": structured.published or art.get("published"),
                "source_domain": structured.domain,
            }
            handled_articles.append(single_article)
        state.articles = handled_articles
        print("ArticleContentExtractorAgent: Done.")
        return state
