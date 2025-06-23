from typing import Any
from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
import psycopg


class NewsStorerAgent(BaseAgent):
    def __init__(self, db_dsn: str):
        super().__init__(llm=None, prompt=None, name="NewsStorerAgent")
        self.db_dsn = db_dsn

    def run(self, state: AgentState) -> AgentState:
        articles = getattr(state, "articles", [])
        if not articles:
            print("NewsStorerAgent: No new articles to store.")
            return state

        print(f"NewsStorerAgent: Storing {len(articles)} articles...")

        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    for art in articles:
                        # 1. Insert into canonical_news, return id
                        cur.execute(
                            """
                            INSERT INTO canonical_news (title, content, published_at)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING
                            RETURNING id
                            """,
                            (
                                art["title"],
                                art[
                                    "summary"
                                ],  # 'summary'->'content' (korjaa tarvittaessa)
                                art["published"],
                            ),
                        )
                        row = cur.fetchone()
                        # Jos ei palauta id:tä (rivi oli jo olemassa), haetaan id erikseen
                        if row and row[0]:
                            canonical_news_id = row[0]
                        else:
                            cur.execute(
                                "SELECT id FROM canonical_news WHERE title = %s AND published_at = %s",
                                (art["title"], art["published"]),
                            )
                            res = cur.fetchone()
                            if res:
                                canonical_news_id = res[0]
                            else:
                                print(
                                    "WARNING: Uutista ei löytynyt kannasta vaikka INSERT tehtiin."
                                )
                                continue

                        # 2. Insert into news_sources
                        cur.execute(
                            """
                            INSERT INTO news_sources
                                (canonical_news_id, source_url, original_guid, published_at)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (
                                canonical_news_id,
                                art["link"],
                                art["unique_id"],
                                art["published"],
                            ),
                        )
                conn.commit()
            print("NewsStorerAgent: Storing done.")
        except Exception as e:
            print(f"NewsStorerAgent: ERROR while storing articles: {e}")

        return state
