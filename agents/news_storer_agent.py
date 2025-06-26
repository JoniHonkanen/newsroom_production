from typing import Any
from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
import psycopg  # type: ignore
import hashlib
from sentence_transformers import SentenceTransformer  # type: ignore
import datetime

try:
    from dateutil import parser as date_parser
except ImportError:
    date_parser = None


class NewsStorerAgent(BaseAgent):
    """Agent that stores news articles into PostgreSQL with hash- and embedding-based dedupe (pre-check),
    allowing re-insertion if semantically similar article is older than a time threshold.
    """

    def __init__(self, db_dsn: str, threshold: float = 0.1, time_window_days: int = 2):
        super().__init__(llm=None, prompt=None, name="NewsStorerAgent")
        self.db_dsn = db_dsn
        self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        self.threshold = threshold
        self.time_window = datetime.timedelta(days=time_window_days)

    def _normalize(self, text: str) -> str:
        """Normalize text by stripping whitespace and removing extra spaces."""
        return " ".join(text.split())

    def _calc_hash(self, text: str) -> str:
        """Calculate SHA-256 hash of the normalized text."""
        h = hashlib.sha256()
        h.update(text.encode("utf-8"))
        return h.hexdigest()

    def _encode(self, text: str) -> list[float]:
        """Encode text into a vector using the SentenceTransformer model."""
        return (
            self.model.encode(text, normalize_embeddings=True)
            .astype("float32")
            .tolist()
        )

    def _parse_published(self, published: Any) -> datetime.datetime:
        """Ensure published_at is a naive datetime object (UTC)."""
        if isinstance(published, datetime.datetime):
            dt = published
        elif isinstance(published, str):
            try:
                if date_parser:
                    dt = date_parser.parse(published)
                else:
                    dt = datetime.datetime.fromisoformat(
                        published.replace("Z", "+00:00")
                    )
            except Exception:
                raise ValueError(f"Unable to parse published timestamp: {published}")
        else:
            raise TypeError(f"Unsupported type for published: {type(published)}")
        # Convert to naive UTC
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt

    def run(self, state: AgentState) -> AgentState:
        articles = getattr(state, "articles", [])
        if not articles:
            print("NewsStorerAgent: No new articles.")
            return state

        with psycopg.connect(self.db_dsn) as conn:
            with conn.transaction():
                for art in articles:
                    raw = getattr(art, "content", "") or ""
                    print(f"Processing raw article: {raw}")
                    norm = self._normalize(raw)
                    print(f"Normalized content: {norm[:100]}...")  # Print first 100 chars for brevity
                    h = self._calc_hash(norm) #hashing
                    published_dt = self._parse_published(
                        getattr(art, "published", None)
                    )

                    # 1. Hash-duplication
                    row = conn.execute(
                        "SELECT id FROM canonical_news WHERE content_hash = %s",
                        (h,),
                    ).fetchone()
                    if row:
                        print(
                            f"Skipping by hash duplicate: canonical_id={row[0]}, url={art.link}"
                        )
                        continue

                    # 2. Embedding pre-check
                    emb = self._encode(norm)
                    sim = conn.execute(
                        """
                        SELECT id, published_at, content_embedding <=> %s::vector AS dist
                        FROM canonical_news
                        ORDER BY dist
                        LIMIT 1
                        """,
                        (emb,),
                    ).fetchone()

                    if sim:
                        similar_id, sim_published, dist = sim
                        if (
                            isinstance(sim_published, str)
                            or sim_published.tzinfo is not None
                        ):
                            sim_published = self._parse_published(sim_published)
                        if (
                            dist < self.threshold
                            and (published_dt - sim_published) <= self.time_window
                        ):
                            print(
                                f"Found semantic duplicate: canonical_id={similar_id}, dist={dist:.4f}, url={art.link}"
                            )
                            result = conn.execute(
                                """
                                INSERT INTO news_sources
                                    (canonical_news_id, source_url, original_guid, published_at)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT DO NOTHING
                                """,
                                (
                                    similar_id,
                                    art.link,
                                    getattr(art, "unique_id", None),
                                    published_dt,
                                ),
                            )
                            if result.rowcount:
                                print(
                                    f"  → Linked new source for canonical_id={similar_id}"
                                )
                            else:
                                print(
                                    f"  → Source already linked for canonical_id={similar_id}"
                                )
                            continue

                    # 3. Uusi canonical_news
                    row = conn.execute(
                        """
                        INSERT INTO canonical_news
                            (title,
                             content,
                             published_at,
                             created_at,
                             content_hash,
                             content_embedding,
                             source_name,
                             source_url,
                             language)
                        VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            art.title,
                            norm,
                            published_dt,
                            datetime.datetime.now(datetime.timezone.utc),
                            h,
                            emb,
                            art.source_domain,
                            art.link,
                            art.language,
                        ),
                    ).fetchone()
                    canonical_id = row[0]
                    print(
                        f"Inserted new canonical_news id={canonical_id}, url={art.link}"
                    )

        print("NewsStorerAgent: Storing done.")
        return state
