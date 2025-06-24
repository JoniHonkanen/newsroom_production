from typing import Any
from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
import psycopg  # type: ignore


class NewsStorerAgent(BaseAgent):
    """Agent that stores news articles into a PostgreSQL database."""

    def __init__(self, db_dsn: str):
        super().__init__(llm=None, prompt=None, name="NewsStorerAgent")
        self.db_dsn = "postgresql://newsroom:newsroom@localhost:15432/newsroom"

    def run(self, state: AgentState) -> AgentState:
        articles = getattr(state, "articles", [])
        if not articles:
            print("NewsStorerAgent: No new articles to store.")
            return state
        print(f"NewsStorerAgent initialized with DSN: {self.db_dsn}")
        print(f"NewsStorerAgent: Storing {len(articles)} articles...")

        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.transaction():
                    for art in articles:
                        print(f"Storing article: {art.title}")
                        print(art)
                        # 1. Insert into canonical_news, return id
                        row = conn.execute(
                            """
                            INSERT INTO canonical_news (title, content, published_at)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING
                            RETURNING id
                            """,
                            (
                                art.title,
                                getattr(art, "content", None),
                                art.published,
                            ),
                        ).fetchone()

                        # Jos ei palauta id:tä (rivi oli jo olemassa), haetaan id erikseen
                        if row and row[0]:
                            canonical_news_id = row[0]
                        else:
                            res = conn.execute(
                                "SELECT id FROM canonical_news WHERE title = %s AND published_at = %s",
                                (art.title, art.published),
                            ).fetchone()
                            if res:
                                canonical_news_id = res[0]
                            else:
                                print(
                                    "WARNING: Uutista ei löytynyt kannasta vaikka INSERT tehtiin."
                                )
                                continue

                        # 2. Insert into news_sources
                        conn.execute(
                            """
                            INSERT INTO news_sources
                                (canonical_news_id, source_url, original_guid, published_at)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (
                                canonical_news_id,
                                art.link,
                                getattr(art, "unique_id", None),
                                art.published,
                            ),
                        )
            print("NewsStorerAgent: Storing done.")
        except Exception as e:
            print(f"NewsStorerAgent: ERROR while storing articles: {e}")

        return state
