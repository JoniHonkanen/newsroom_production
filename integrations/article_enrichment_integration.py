import os
import logging
from typing import Optional, Dict, Any
from langchain.chat_models import init_chat_model
import psycopg  # type: ignore


from agents.interview_agents.article_enricher_agent import ArticleEnricherAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle

#TODO:: NEEDS TESTING!!!
# THIS COMPONENT IS WHAT EXTERNAL SERVER CALLS TO ENRICH ARTICLES AFTER INTERVIEWS

logger = logging.getLogger(__name__)


class ArticleEnrichmentIntegration:
    """Integration layer for enriching articles with interview content from external server."""

    def __init__(self, db_dsn: str, llm_model: str = "gpt-4o-mini"):
        self.db_dsn = db_dsn
        self.llm = init_chat_model(llm_model, model_provider="openai")
        self.enricher_agent = ArticleEnricherAgent(self.llm, db_dsn)

    def enrich_article_with_interview(
        self,
        article_id: int,
        interview_content: str,
        respondent_name: str,
        respondent_title: str = None,
        respondent_organization: str = None,
    ) -> Dict[str, Any]:
        logger.info(f"🚀 Starting article enrichment for article_id: {article_id}")
        logger.info(f"👤 Respondent: {respondent_name}")

        try:
            # 1. Load article from database
            article = self._load_article_from_db(article_id)
            if not article:
                return {
                    "status": "error",
                    "message": f"Article {article_id} not found",
                    "article_id": article_id,
                }

            logger.info(f"📰 Loaded article: {article.enriched_title[:50]}...")

            # 2. Create simple agent state
            state = AgentState()
            state.current_article = article
            state.raw_interview_content = interview_content
            state.respondent_name = respondent_name
            state.respondent_title = respondent_title
            state.respondent_organization = respondent_organization

            # 3. Run enrichment agent
            logger.info("🤖 Running ArticleEnricherAgent...")
            result_state = self.enricher_agent.run(state)

            # 4. Save enriched article back to database
            if (
                hasattr(result_state, "enrichment_result")
                and result_state.enrichment_result
            ):
                enrichment_result = result_state.enrichment_result
                enriched_article = result_state.current_article

                # Save to database
                self._save_enriched_article_to_db(enriched_article, enrichment_result)

                logger.info("✅ Article enrichment completed successfully!")

                return {
                    "status": "success",
                    "message": "Article enriched successfully",
                    "article_id": article_id,
                    "enrichment_summary": enrichment_result.enrichment_summary,
                    "respondent_integrated": f"{respondent_name} ({respondent_organization or 'Independent'})",
                    "enriched_title": enrichment_result.enriched_title,
                    "content_length": len(enrichment_result.enriched_content),
                }
            else:
                logger.error("❌ Enrichment agent failed to produce results")
                return {
                    "status": "error",
                    "message": "Enrichment agent failed to produce results",
                    "article_id": article_id,
                }

        except Exception as e:
            logger.error(f"❌ Error during article enrichment: {e}")
            import traceback

            traceback.print_exc()

            return {
                "status": "error",
                "message": f"Enrichment failed: {str(e)}",
                "article_id": article_id,
            }

    def _load_article_from_db(self, article_id: int) -> Optional[EnrichedArticle]:
        """Load article from database."""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 
                            id, 
                            enriched_title, 
                            enriched_content,
                            published_at,
                            source_domain,
                            language,
                            summary,
                            keywords,
                            categories
                        FROM canonical_news 
                        WHERE id = %s
                    """,
                        (article_id,),
                    )

                    row = cur.fetchone()
                    if not row:
                        return None

                    (
                        id,
                        title,
                        content,
                        published_at,
                        source_domain,
                        language,
                        summary,
                        keywords,
                        categories,
                    ) = row

                    return EnrichedArticle(
                        article_id=f"article-{id}",
                        news_article_id=id,
                        enriched_title=title,
                        enriched_content=content,
                        published_at=published_at.isoformat() if published_at else None,
                        source_domain=source_domain,
                        language=language or "fi",
                        summary=summary or "",
                        keywords=keywords or [],
                        categories=categories or [],
                        sources=[],
                        contacts=[],
                    )

        except psycopg.Error as e:
            logger.error(f"Database error loading article: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading article: {e}")
            return None

    def _save_enriched_article_to_db(
        self, article: EnrichedArticle, enrichment_result
    ) -> bool:
        """Save enriched article back to database."""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    # Update the article with enriched content
                    cur.execute(
                        """
                        UPDATE canonical_news 
                        SET 
                            enriched_title = %s,
                            enriched_content = %s,
                            enrichment_status = 'enriched',
                            enriched_at = NOW()
                        WHERE id = %s
                    """,
                        (
                            article.enriched_title,
                            article.enriched_content,
                            article.news_article_id,
                        ),
                    )

                    # Log enrichment metadata
                    cur.execute(
                        """
                        INSERT INTO article_enrichment_log 
                        (canonical_news_id, enrichment_type, respondent_name, 
                         enrichment_summary, processed_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        ON CONFLICT DO NOTHING
                    """,
                        (
                            article.news_article_id,
                            "interview_integration",
                            (
                                enrichment_result.respondent_name
                                if hasattr(enrichment_result, "respondent_name")
                                else "Unknown"
                            ),
                            enrichment_result.enrichment_summary,
                        ),
                    )

                    conn.commit()
                    logger.info("✅ Enriched article saved to database")
                    return True

        except psycopg.Error as e:
            logger.error(f"Database error saving enriched article: {e}")
            return False
        except Exception as e:
            logger.error(f"Error saving enriched article: {e}")
            return False


# Simple convenience function for external server use
def enrich_article_with_interview(
    article_id: int,
    interview_content: str,
    respondent_name: str,
    respondent_title: str = None,
    respondent_organization: str = None,
) -> Dict[str, Any]:
    """
    Ultra-simple function for enriching article with any interview content.

    Args:
        article_id: ID of article to enrich
        interview_content: Raw content - email body, phone transcript JSON string, anything
        respondent_name: Name of the person interviewed
        respondent_title: Title/position (optional)
        respondent_organization: Organization (optional)

    Example usage:
        # Email response
        email_body = _extract_body(email_message)
        result = enrich_article_with_interview(
            article_id=12345,
            interview_content=email_body,
            respondent_name="Dr. Marja Asiantuntija"
        )

        # Phone transcript
        phone_json = json.dumps(phone_transcript_list)
        result = enrich_article_with_interview(
            article_id=12345,
            interview_content=phone_json,
            respondent_name="Ing. Paavo Energiamies"
        )
    """

    # Initialize integration and run enrichment
    db_dsn = os.getenv("DATABASE_URL")
    integration = ArticleEnrichmentIntegration(db_dsn)

    return integration.enrich_article_with_interview(
        article_id,
        interview_content,
        respondent_name,
        respondent_title,
        respondent_organization,
    )


# If email reply processing is needed, we can use this function
def enrich_article_with_email_reply(message_id: str, email_body: str) -> Dict[str, Any]:

    # Get all needed info from database using message_id
    article_info = _get_article_info_by_message_id(message_id)
    print(f"Article info for message_id {message_id}: {article_info}")
    if not article_info:
        return {
            "status": "error",
            "message": f"Could not find article or recipient info for message_id: {message_id}",
            "message_id": message_id,
        }

    # Use the standard enrichment function
    result = enrich_article_with_interview(
        article_id=article_info["article_id"],
        interview_content=email_body,
        respondent_name=article_info["respondent_name"],  # From email recipient
        respondent_title=article_info.get("respondent_title"),
        respondent_organization=article_info.get("respondent_organization"),
    )

    # Add message_id to result for tracking
    result["message_id"] = message_id
    return result


def _get_article_info_by_message_id(message_id: str) -> Optional[Dict[str, Any]]:
    """Get article_id and recipient info by looking up the message_id."""

    db_dsn = os.getenv("DATABASE_URL")

    try:
        with psycopg.connect(db_dsn) as conn:
            with conn.cursor() as cur:
                # Get article_id and recipient from email_interview table
                cur.execute(
                    """
                    SELECT 
                        canonical_news_id,
                        recipient
                    FROM email_interview 
                    WHERE message_id = %s
                """,
                    (message_id,),
                )

                row = cur.fetchone()
                if not row:
                    return None

                article_id, recipient_email = row

                # Parse recipient name from email (simple extraction)
                # Format is usually: "Name" <email@domain.com> or just email@domain.com
                respondent_name = recipient_email
                if "<" in recipient_email and ">" in recipient_email:
                    # Extract name from "Name" <email@domain.com> format
                    name_part = recipient_email.split("<")[0].strip()
                    if name_part.startswith('"') and name_part.endswith('"'):
                        name_part = name_part[1:-1]  # Remove quotes
                    if name_part:
                        respondent_name = name_part
                    else:
                        # Fall back to email local part
                        email_part = recipient_email.split("<")[1].split(">")[0]
                        respondent_name = email_part.split("@")[0]
                else:
                    # Just email, use local part as name
                    respondent_name = recipient_email.split("@")[0]

                return {
                    "article_id": article_id,
                    "respondent_name": respondent_name,
                    "respondent_title": None,  # Could be enhanced later
                    "respondent_organization": None,  # Could be enhanced later
                }

    except psycopg.Error as e:
        logger.error(f"Database error getting article info by message_id: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting article info by message_id: {e}")
        return None


def _find_article_by_message_id(message_id: str) -> Optional[int]:
    """Find article_id by looking up the message_id in email_interview table."""

    article_info = _get_article_info_by_message_id(message_id)
    return article_info["article_id"] if article_info else None


# TEST FUNCTION
if __name__ == "__main__":
    from dotenv import load_dotenv
    import json

    load_dotenv()

    print("🧪 TESTING ArticleEnrichmentIntegration (SIMPLIFIED)...")

    # Test email body (raw text)
    mock_email_body = """
Hei,

Kiitos kysymyksistänne. Vastaan mielelläni:

Turvallisuusriskeistä: Kiinalaisten akkujärjestelmien käyttö infrastruktuurissa vaatii huolellista riskinarviointia. Teknologia on laadukasta, mutta geopoliittiset näkökohdat on otettava huomioon.

Sähköverkon toiminnasta: Akkujärjestelmät tarjoavat nopeaa säätövoimaa ja parantavat verkon vakautta. Huawein teknologia on teknisesti korkealaatuista.

Ystävällisin terveisin,
Dr. Marja Kyberturva
    """

    # Test phone transcript (JSON string)
    mock_phone_transcript = [
        {"speaker": "assistant", "text": "Mikä on näkemyksenne turvallisuusriskeistä?"},
        {
            "speaker": "user",
            "text": "Kiinalaisten akkujärjestelmien käyttö vaatii huolellista arviointia.",
        },
        {"speaker": "assistant", "text": "Entä energiamarkkinoiden näkökulmasta?"},
        {"speaker": "user", "text": "Akkuteknologia tarjoaa nopeaa säätövoimaa."},
    ]
    phone_json = json.dumps(mock_phone_transcript)

    test_article_id = 12345  # Replace with real article ID

    try:
        # Test with known message_id (if you have one in your DB)
        test_message_id = "<34c0a8ed-f201-46cd-894c-ea2b2dbf433a@gmail.com>"
        test_email_body = """
Hei,
Kiinalaiset akkujärjestelmät ovat teknisesti laadukkaita, mutta niiden käyttöön liittyy geopoliittisia riskejä. Ne parantavat sähköverkon vakautta tarjoamalla nopeaa säätövoimaa.
Terveisin,
Jomppe Jormanen
        """

        # Test email reply enrichment using message_id
        print(f"\n🧪 TESTING EMAIL REPLY ENRICHMENT:")
        print(f"   Message ID: {test_message_id}")

        email_reply_result = enrich_article_with_email_reply(
            message_id=test_message_id, email_body=test_email_body
        )

        print(f"   Status: {email_reply_result['status']}")
        if email_reply_result["status"] == "success":
            print(f"   📰 Title: {email_reply_result['enriched_title'][:60]}...")
            print(f"   👤 Respondent: {email_reply_result['respondent_integrated']}")
            print(f"   📧 Message ID: {email_reply_result['message_id']}")
        else:
            print(f"   ❌ Error: {email_reply_result['message']}")

        # Test direct article enrichment (fallback method)
        print(f"\n🧪 TESTING DIRECT ARTICLE ENRICHMENT:")
        direct_result = enrich_article_with_interview(
            article_id=test_article_id,
            interview_content=test_email_body,
            respondent_name="Test User",
        )

        print(f"   Status: {direct_result['status']}")
        if direct_result["status"] == "success":
            print(f"   📰 Title: {direct_result['enriched_title'][:60]}...")
            print(f"   👤 Respondent: {direct_result['respondent_integrated']}")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()

    print("\n🎯 Integration ready for external server calls!")
    print("\n💡 USAGE FROM EXTERNAL SERVER:")
    print(
        "   from integrations.article_enrichment_integration import enrich_article_with_interview"
    )
    print("")
    print("   # Email response:")
    print("   email_body = _extract_body(email_message)")
    print(
        "   result = enrich_article_with_interview(article_id, email_body, respondent_name)"
    )
    print("")
    print("   # Phone transcript:")
    print("   phone_json = json.dumps(phone_transcript)")
    print(
        "   result = enrich_article_with_interview(article_id, phone_json, respondent_name)"
    )
