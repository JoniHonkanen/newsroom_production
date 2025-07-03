from typing import List, Optional  # Korjattu import - ei ast.List!
from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from langdetect import detect, LangDetectException  # type: ignore

from schemas.feed_schema import CanonicalArticle
from services.article_parser import to_structured_article


class ArticleContentExtractorAgent(BaseAgent):
    """Agent that fetches articles."""

    def __init__(self):
        super().__init__(llm=None, prompt=None, name="ArticleContentExtractorAgent")
        # we want to detect if this is article or press release
        self.PRESS_RELEASE_URL_KEYWORDS = [
            "/tiedotteet",
            "/tiedote/",
            "/press-releases",
            "/media/",
            "/newsroom/",
        ]
        self.PRESS_RELEASE_TITLE_KEYWORDS = [
            "tiedote:",
            "lehdistötiedote",
            "press release:",
            "mediatiedote",
        ]
        self.PRESS_RELEASE_CONTENT_KEYWORDS = {
            "contact_info": ["lisätietoja:", "for more information:", "yhteystiedot:"],
            "distributors": [
                "koodiviidakko",
                "cision",
                "stt info",
                "epressi",
                "meltwater",
            ],
        }

    def _classify_article_type(self, url: str, title: str, content: str) -> str:
        """
        Classifies article as 'news' or 'press_release' based on URL, title, and content heuristics.
        Maybe we can use different kind of agent to do something based on this classification.
        """
        lower_url = url.lower()
        lower_title = title.lower()
        # We only check the last 300 characters, because the end of the article often contains contact information or distribution details.
        content_ending = content.lower()[-300:]

        # check if the URL contains known press release keywords
        for keyword in self.PRESS_RELEASE_URL_KEYWORDS:
            if keyword in lower_url:
                return "press_release"

        # check if the title contains known press release keywords
        for keyword in self.PRESS_RELEASE_TITLE_KEYWORDS:
            if lower_title.startswith(keyword):
                return "press_release"

        # check if the content ending contains known press release keywords
        for keyword in self.PRESS_RELEASE_CONTENT_KEYWORDS["contact_info"]:
            if keyword in content_ending:
                return "press_release"

        # if none of the earlier checks matched, classify as news
        return "news"

    def _detect_language(self, text: Optional[str]) -> Optional[str]:
        """Try to detect the language of the given text."""
        if not text:
            return None
        try:
            return detect(text)
        except LangDetectException:
            return None

    def run(self, state: AgentState) -> AgentState:
        # Käytä suoraan state.articles - nyt tyyppi on oikea!
        articles = state.articles
        if not articles:
            print("ArticleContentExtractorAgent: No new articles to process.")
            return state

        print(
            f"ArticleContentExtractorAgent: Fetching content for {len(articles)} articles..."
        )
        handled_articles: List[CanonicalArticle] = []

        for art in articles:
            url = art.link
            if not url:
                print("No URL found for article, skipping.")
                continue
            # This function fetches the article content and returns a structured representation
            # this includes parsing html elements and converting them to markdown
            structured = to_structured_article(url)
            if structured is None:
                print(f"Failed to fetch article content: {url}")
                continue

            # Check the language of the article using its title
            language = self._detect_language(art.title)

            article_type = self._classify_article_type(
                url, art.title, structured.markdown
            )

            # Yhdistä uutisen alkuperäiset kentät ja uusi rakenne (voit säilyttää summaryn yms.)
            single_article: CanonicalArticle = art.model_copy(
                update={
                    "structured_article": structured,
                    "content": structured.markdown,
                    "published_at": structured.published or art.published_at, # fallback!
                    "source_domain": structured.domain,
                    "language": language,
                    "article_type": article_type,
                }
            )

            handled_articles.append(single_article)

        state.articles = handled_articles
        print("ArticleContentExtractorAgent: Done.")
        return state
