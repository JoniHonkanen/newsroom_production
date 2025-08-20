import os
import logging
from typing import Optional, Dict, Any
from langchain.chat_models import init_chat_model
import psycopg  # type: ignore

from agents.interview_agents.article_enricher_agent import ArticleEnricherAgent
from schemas.agent_state import AgentState, InterviewAgentState
from schemas.enriched_article import EnrichedArticle
from schemas.interview_schema import DataAfterInterviewFromDatabase

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
        print("Starting article enrichment for article_id:", article_id)

        try:
            # 1. Load article from database
            article: DataAfterInterviewFromDatabase = self._load_article_from_db(
                article_id
            )
            if not article:
                return {
                    "status": "error",
                    "message": f"Article {article_id} not found",
                    "article_id": article_id,
                }

            print("ALKUPERÄINEN ARTIKKELI:", article)
            print("HAASTATTELUN JUTUT:", interview_content)

            # 2. Create simple agent state
            state = InterviewAgentState()
            state.current_article = article
            state.interview_content = interview_content

            # 3. Run enrichment agent
            print("🤖 Running ArticleEnricherAgent...")
            result_state = self.enricher_agent.run(state)
            print("ONKO ARTIKKELI RIKASTETTU ONNISTUNEESTI????: ", result_state)

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

    def _load_article_from_db(self, article_id: int) -> DataAfterInterviewFromDatabase:
        """Load article from database."""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, lead, markdown_content, language
                        FROM news_article
                        WHERE id = %s
                    """,
                        (article_id,),
                    )

                    row = cur.fetchone()
                    if not row:
                        return None

                    id, lead, content, language = row

                    return DataAfterInterviewFromDatabase(
                        article_id=id,
                        enriched_title=lead,
                        enriched_content=content,
                        language=language,
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
                            lead = %s,
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


# YKSINKERTAINEN FUNKTIO ULKOISEN SERVERIN KÄYTTÖÖN
def enrich_article_with_interview(
    article_id: int,
    interview_content: str,
    respondent_name: str,
    respondent_title: str = None,
    respondent_organization: str = None,
) -> Dict[str, Any]:
    """
    Yksinkertainen funktio artikkelien rikastamiseen haastatteluilla.

    Args:
        article_id: Artiklin ID
        interview_content: Haastatteludata (sähköposti, puhelu json, mitä tahansa)
        respondent_name: Haastateltavan nimi
        respondent_title: Titteli (valinnainen)
        respondent_organization: Organisaatio (valinnainen)
    """
    print("ENRICHING ARTICLE WITH INTERVIEW!!!!!! :;DDD")
    db_dsn = os.getenv("DATABASE_URL")
    integration = ArticleEnrichmentIntegration(db_dsn)

    return integration.enrich_article_with_interview(
        article_id,
        interview_content,
        respondent_name,
        respondent_title,
        respondent_organization,
    )


# SÄHKÖPOSTIVASTAUSTEN KÄSITTELY MESSAGE_ID:N PERUSTEELLA
def enrich_article_with_email_reply(message_id: str, email_body: str) -> Dict[str, Any]:
    """
    Rikasta artikkeli sähköpostivastauksen perusteella message_id:tä käyttäen.
    """
    print("ENRICHING ARTICLE AGAIN !!!!!")
    # Hae artikkelitiedot message_id:n perusteella
    article_info = _get_article_info_by_message_id(message_id)
    print("ARTICLE INFO")
    print(article_info)

    if not article_info:
        return {
            "status": "error",
            "message": f"Artikkelia tai vastaanottajaa ei löydy message_id:lle: {message_id}",
            "message_id": message_id,
        }

    # Käytä yleistä rikastamisfunktiota
    result = enrich_article_with_interview(
        article_id=article_info["article_id"],
        interview_content=email_body,
        respondent_name=article_info["respondent_name"],
    )
    print("_get_article_info_by_message_id: ", result)

    # Lisää message_id tulokseen seurantaa varten
    result["message_id"] = message_id
    return result


def _get_article_info_by_message_id(message_id: str) -> Optional[Dict[str, Any]]:
    """Hae artikel_id ja vastaanottajan tiedot message_id:n perusteella."""
    db_dsn = os.getenv("DATABASE_URL")

    try:
        with psycopg.connect(db_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT news_article_id, recipient
                    FROM email_interview 
                    WHERE message_id = %s
                    """,
                    (message_id,),
                )

                row = cur.fetchone()
                if not row:
                    return None

                article_id, recipient = row
                print("ARTICLE ID:", article_id)
                print("RECIPIENT:", recipient)

                # Käytä sähköpostin alkuosaa nimenä
                respondent_name = recipient.split("@")[0]

                return {
                    "article_id": article_id,
                    "respondent_name": respondent_name,
                }

    except Exception as e:
        logger.error(f"Virhe haettaessa artikkelitietoja message_id:llä: {e}")
        return None


# TESTAUS
if __name__ == "__main__":
    from dotenv import load_dotenv
    import json

    load_dotenv()

    print("🧪 TESTING ArticleEnrichmentIntegration...")

    test_message_id = "<test-message-id@gmail.com>"
    test_email_body = """
    Hei,
    
    Kiinalaiset akkujärjestelmät ovat teknisesti laadukkaita, mutta geopoliittisia 
    riskejä on syytä arvioida huolellisesti. Sähköverkon kannalta ne tarjoavat 
    nopeaa säätövoimaa ja parantavat verkon vakautta.
    
    Terveisin,
    Asiantuntija
    """

    try:
        # Testaa sähköpostivastauksen rikastaminen
        result = enrich_article_with_email_reply(test_message_id, test_email_body)
        print(f"Tulos: {result['status']}")

        if result["status"] == "success":
            print(f"Rikastettu artikkeli: {result['enriched_title'][:50]}...")
        else:
            print(f"Virhe: {result['message']}")

    except Exception as e:
        print(f"Testi epäonnistui: {e}")

    print("✅ Valmis ulkoisten servereiden käyttöön!")
