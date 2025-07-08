"""
Editorial Review Service - Simple version following NewsArticleService pattern
"""

import psycopg
from psycopg.types.json import Jsonb
from typing import List, Optional, Dict, Any
from datetime import datetime
from schemas.editor_in_chief_schema import ReviewedNewsItem, ReasoningStep


class EditorialReviewService:
    """Service for managing editorial review data - simple and clean like NewsArticleService"""

    def __init__(self, db_dsn: str):
        """Initialize with database connection string"""
        self.db_dsn = db_dsn
        print(f"🔗 Initializing EditorialReviewService with DSN: {db_dsn[:50]}...")
        self._setup_tables()
        print("✅ EditorialReviewService initialized successfully")

    def _setup_tables(self):
        """Ensure database tables and indexes exist"""
        with psycopg.connect(self.db_dsn) as conn:
            with conn.cursor() as cur:
                # Create helpful indexes if they don't exist
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_editorial_reviews_article_id ON editorial_reviews(article_id);
                    CREATE INDEX IF NOT EXISTS idx_editorial_reviews_status ON editorial_reviews(status);
                    CREATE INDEX IF NOT EXISTS idx_editorial_reviews_reviewer ON editorial_reviews(reviewer);
                    CREATE INDEX IF NOT EXISTS idx_editorial_reviews_created_at ON editorial_reviews(created_at);
                    CREATE INDEX IF NOT EXISTS idx_editorial_issues_article_id ON editorial_issues(article_id);
                    CREATE INDEX IF NOT EXISTS idx_editorial_reasoning_steps_article_id ON editorial_reasoning_steps(article_id);
                """
                )
                conn.commit()

    def save_review(self, article_id: str, review: ReviewedNewsItem) -> bool:
        """
        Save editorial review decision to database

        Args:
            article_id: Unique identifier for the generated news article
            review: ReviewedNewsItem object containing the full review decision

        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    # Determine final decision
                    final_decision = None
                    if review.reconsideration:
                        final_decision = review.reconsideration.final_decision
                    elif review.editorial_reasoning.initial_decision:
                        final_decision = review.editorial_reasoning.initial_decision

                    # Insert/Update main review record (same upsert logic as before)
                    cur.execute(
                        """
                        INSERT INTO editorial_reviews 
                        (article_id, review_data, status, reviewer, initial_decision, 
                         final_decision, has_warning, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (article_id) 
                        DO UPDATE SET 
                            review_data = EXCLUDED.review_data,
                            status = EXCLUDED.status,
                            final_decision = EXCLUDED.final_decision,
                            has_warning = EXCLUDED.has_warning,
                            updated_at = EXCLUDED.updated_at
                    """,
                        (
                            article_id,
                            Jsonb(review.model_dump()),
                            review.status,
                            review.editorial_reasoning.reviewer,
                            review.editorial_reasoning.initial_decision,
                            final_decision,
                            review.editorial_warning is not None,
                            datetime.now(),
                            datetime.now(),
                        ),
                    )

                    # Clear and re-insert related data
                    cur.execute(
                        "DELETE FROM editorial_issues WHERE article_id = %s",
                        (article_id,),
                    )
                    cur.execute(
                        "DELETE FROM editorial_reasoning_steps WHERE article_id = %s",
                        (article_id,),
                    )

                    # Insert issues
                    for issue in review.issues:
                        cur.execute(
                            """
                            INSERT INTO editorial_issues 
                            (article_id, issue_type, location, description, suggestion)
                            VALUES (%s, %s, %s, %s, %s)
                        """,
                            (
                                article_id,
                                issue.type,
                                issue.location,
                                issue.description,
                                issue.suggestion,
                            ),
                        )

                    # Insert reasoning steps
                    self._insert_reasoning_steps(
                        cur,
                        article_id,
                        review.editorial_reasoning.reasoning_steps,
                        False,
                    )

                    # Insert reconsideration steps if present
                    if review.reconsideration:
                        self._insert_reasoning_steps(
                            cur,
                            article_id,
                            review.reconsideration.reasoning_steps,
                            True,
                        )

                    conn.commit()
                    print(f"✅ Successfully saved review for article {article_id}")
                    print(f"   - Main review: ✅")
                    print(f"   - Issues: {len(review.issues)} saved")
                    print(
                        f"   - Reasoning steps: {len(review.editorial_reasoning.reasoning_steps)} saved"
                    )
                    if review.reconsideration:
                        print(
                            f"   - Reconsideration steps: {len(review.reconsideration.reasoning_steps)} saved"
                        )
                    return True

        except Exception as e:
            print(f"Error saving editorial review for article {article_id}: {e}")
            return False

    def _insert_reasoning_steps(
        self, cur, article_id: str, steps: List[ReasoningStep], is_reconsideration: bool
    ):
        """Helper method to insert reasoning steps"""
        for step in steps:
            cur.execute(
                """
                INSERT INTO editorial_reasoning_steps 
                (article_id, step_id, action, observation, result, is_reconsideration)
                VALUES (%s, %s, %s, %s, %s, %s)
            """,
                (
                    article_id,
                    step.step_id,
                    step.action,
                    step.observation,
                    step.result,
                    is_reconsideration,
                ),
            )

    # ***********THESE ARE NOT USED, BUT MAY BE HELPFUL LATER**************
    def get_review(self, article_id: str) -> Optional[ReviewedNewsItem]:
        """Get editorial review by article ID"""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT review_data 
                        FROM editorial_reviews 
                        WHERE article_id = %s
                    """,
                        (article_id,),
                    )

                    result = cur.fetchone()
                    if result:
                        return ReviewedNewsItem(**result[0])
                    return None

        except Exception as e:
            print(f"Error retrieving editorial review for article {article_id}: {e}")
            return None

    def get_articles_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get articles by review status"""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT article_id, review_data, created_at, updated_at
                        FROM editorial_reviews 
                        WHERE status = %s
                        ORDER BY created_at DESC
                    """,
                        (status,),
                    )

                    return [
                        {
                            "article_id": row[0],
                            "review_data": row[1],
                            "created_at": row[2],
                            "updated_at": row[3],
                        }
                        for row in cur.fetchall()
                    ]

        except Exception as e:
            print(f"Error retrieving articles by status {status}: {e}")
            return []

    def get_reviewer_stats(self, reviewer: str) -> Dict[str, Any]:
        """Get statistics for a specific reviewer"""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 
                            COUNT(*) as total_reviews,
                            COUNT(CASE WHEN status = 'OK' THEN 1 END) as ok_reviews,
                            COUNT(CASE WHEN status = 'ISSUES_FOUND' THEN 1 END) as issues_found,
                            COUNT(CASE WHEN status = 'RECONSIDERATION' THEN 1 END) as reconsiderations,
                            COUNT(CASE WHEN has_warning = true THEN 1 END) as with_warnings
                        FROM editorial_reviews 
                        WHERE reviewer = %s
                    """,
                        (reviewer,),
                    )

                    result = cur.fetchone()
                    if result:
                        return {
                            "reviewer": reviewer,
                            "total_reviews": result[0],
                            "ok_reviews": result[1],
                            "issues_found": result[2],
                            "reconsiderations": result[3],
                            "with_warnings": result[4],
                        }
                    return {}

        except Exception as e:
            print(f"Error retrieving stats for reviewer {reviewer}: {e}")
            return {}

    def get_articles_with_warnings(self) -> List[Dict[str, Any]]:
        """Get all articles that have editorial warnings"""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT article_id, review_data, created_at
                        FROM editorial_reviews 
                        WHERE has_warning = true
                        ORDER BY created_at DESC
                    """
                    )

                    return [
                        {
                            "article_id": row[0],
                            "review_data": row[1],
                            "created_at": row[2],
                        }
                        for row in cur.fetchall()
                    ]

        except Exception as e:
            print(f"Error retrieving articles with warnings: {e}")
            return []

    def get_articles_needing_attention(self) -> List[Dict[str, Any]]:
        """Get articles that need editorial attention (not OK status)"""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT article_id, status, reviewer, created_at, updated_at
                        FROM editorial_reviews 
                        WHERE status != 'OK'
                        ORDER BY updated_at DESC
                    """
                    )

                    return [
                        {
                            "article_id": row[0],
                            "status": row[1],
                            "reviewer": row[2],
                            "created_at": row[3],
                            "updated_at": row[4],
                        }
                        for row in cur.fetchall()
                    ]

        except Exception as e:
            print(f"Error retrieving articles needing attention: {e}")
            return []


# Example usage - simple and clean like NewsArticleService
if __name__ == "__main__":
    import os

    # Initialize service - no singleton complexity
    db_dsn = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/newsdb")
    service = EditorialReviewService(db_dsn)

    # Example usage:
    # success = service.save_review("news_article_123", review)
    # review = service.get_review("news_article_123")
    # stats = service.get_editorial_summary()
    # articles_needing_attention = service.get_articles_needing_attention()

    print("EditorialReviewService (simple version) ready for use")
