import os, asyncio, logging
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import psycopg
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle

load_dotenv()

# Import phone interview integration
from agents.editor_in_chief_agent import EditorInChiefAgent
from integrations.phone_interview_integration import enrich_article_with_phone_call

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("callback-api")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI(title="Newsroom Callback API", version="0.1.0")

# TODO:: REMEMBER UPDATE THESE WHEN WE GO FOR PRODUCTION
# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://192.168.1.102:3000",  # Example IP address, replace with your frontend's address
        "http://localhost:3001",  # Add more origins as needed
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_db_connection():
    """Get database connection"""
    return await psycopg.AsyncConnection.connect(DATABASE_URL)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Debug 422 virheitä."""
    log.error(f"💥 Validation error: {exc.errors()}")
    log.error(f"💥 Request body: {await request.body()}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "body": (await request.body()).decode() if await request.body() else None,
        },
    )


# USED FOR TWILIO
class CallEndedPayload(BaseModel):
    article_id: int
    interview: List[Dict[str, Any]]


# USED FOR DASHBOARD TO MANAGE PROMPTS
# PERSONALITY
class EthicalPersona(BaseModel):
    name: str
    content: str


# FRAGMENTS for prompt construction
class PromptFragment(BaseModel):
    name: str
    content: str


# WHOLE PROMPT, INCLUDING PERSONA AND FRAGMENTS
class PromptComposition(BaseModel):
    name: str
    ethical_persona_id: int
    fragment_ids: List[int] = []
    
# FOR TESTING editor_in_chief agent
# Yksinkertainen malli vain tekstiä varten
class SimpleArticleTest(BaseModel):
    content: str
    title: str = "Testiotsikko"  # Valinnainen, defaultti jos ei anneta

class TestArticleResponse(BaseModel):
    status: str
    editorial_decision: str
    featured: bool
    interview_needed: bool
    issues_count: int
    reasoning: str
    message: str
    review: Optional[Dict[str, Any]] = None
    report: Optional[str] = None
    prompt_used: Optional[str] = None
    model: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/callbacks/call-ended", status_code=202)
async def call_ended(
    payload: CallEndedPayload, x_webhook_secret: str = Header(default="")
):
    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="invalid secret")

    print("TÄÄTÄÄTÄÄ")
    print("Received call-ended payload:", payload)

    async def run():
        try:
            log.info(
                "Phone interview enrichment started for article_id=%s",
                payload.article_id,
            )

            # Muunna haastattelulista stringiksi
            interview_text = ""
            for turn in payload.interview:
                speaker = turn.get("speaker", "unknown")
                text = turn.get("text", "")
                interview_text += f"{speaker}: {text}\n"

            if not interview_text.strip():
                log.warning(
                    "No interview content available for article_id=%s",
                    payload.article_id,
                )
                return

            # Käynnistä rikastaminen
            result = enrich_article_with_phone_call(
                article_id=str(
                    payload.article_id
                ),  # Muunna stringiksi phone_interview_integration varten
                call_content=interview_text,
            )

            if result["status"] == "success":
                log.info(
                    "Phone interview enrichment completed successfully for article_id=%s. "
                    "Respondent: %s, Content length: %d",
                    payload.article_id,
                    result.get("respondent_integrated", "Unknown"),
                    result.get("content_length", 0),
                )
            else:
                log.error(
                    "Phone interview enrichment failed for article_id=%s: %s",
                    payload.article_id,
                    result.get("message", "Unknown error"),
                )

        except Exception:
            log.exception(
                "Phone interview enrichment failed for article_id=%s",
                payload.article_id,
            )

    asyncio.create_task(run())
    return {"accepted": True}


# HERE IS ROUTES FOR DASHBOARD WHERE IT IS POSSIBLE TO CONSTRUCT EDITOR IN CHIEF PROMPTS
# WE CAN MAKE NEW ONES, DELETE, UPDATE ETC...


# ETHICAL PERSONAS ROUTES
# GET ALL PERSONAS
@app.get("/api/ethical-personas")
async def get_ethical_personas():
    """Hae kaikki eettiset persoonat"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, name, content, is_system 
                FROM prompt_ethical_personas 
                ORDER BY is_system DESC, name ASC;
            """
            )
            rows = await cur.fetchall()

            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "content": row[2],
                    "is_system": row[3],
                }
                for row in rows
            ]


# CREATE NEW PERSONA
@app.post("/api/ethical-personas")
async def create_ethical_persona(persona: EthicalPersona):
    """Luo uusi eettinen persoona"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.execute(
                    """
                    INSERT INTO prompt_ethical_personas (name, content, is_system)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """,
                    (persona.name, persona.content, False),
                )

                persona_id = (await cur.fetchone())[0]
                await conn.commit()

                return {
                    "message": f"Ethical persona '{persona.name}' created",
                    "id": persona_id,
                }
            except psycopg.IntegrityError:
                raise HTTPException(
                    status_code=400, detail="Persona name already exists"
                )


# DELETE PERSONA
@app.delete("/api/ethical-personas/{persona_id}")
async def delete_ethical_persona(persona_id: int):
    """Poista eettinen persoona (vain käyttäjän luomat)"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            # Check if persona exists and is not system
            await cur.execute(
                """
                SELECT is_system FROM prompt_ethical_personas WHERE id = %s
            """,
                (persona_id,),
            )

            result = await cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Persona not found")

            if result[0]:  # is_system = True
                raise HTTPException(
                    status_code=403, detail="Cannot delete system persona"
                )

            # Check if used in ANY composition (not just active ones)
            await cur.execute(
                """
                SELECT name FROM prompt_compositions 
                WHERE ethical_persona_id = %s
            """,
                (persona_id,),
            )

            compositions = await cur.fetchall()
            if compositions:
                composition_names = [row[0] for row in compositions]
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot delete persona: used in compositions: {', '.join(composition_names)}",
                )

            # Delete persona
            await cur.execute(
                """
                DELETE FROM prompt_ethical_personas WHERE id = %s
            """,
                (persona_id,),
            )

            await conn.commit()
            return {"message": "Persona deleted"}


# PROMPT FRAGMENTS ROUTES
# GET ALL FRAGMENTS FOR CREATING PROMPTS
@app.get("/api/prompt-fragments")
async def get_prompt_fragments():
    """Hae kaikki prompt-fragmentit"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, name, content, is_system, created_at 
                FROM prompt_fragments 
                ORDER BY is_system DESC, name ASC
            """
            )
            rows = await cur.fetchall()

            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "content": row[2],
                    "is_system": row[3],
                    "created_at": row[4].isoformat() if row[4] else None,
                }
                for row in rows
            ]


# CREATE NEW FRAGMENT
@app.post("/api/prompt-fragments")
async def create_prompt_fragment(fragment: PromptFragment):
    """Luo uusi prompt-fragmentti"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.execute(
                    """
                    INSERT INTO prompt_fragments (name, content, is_system)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """,
                    (fragment.name, fragment.content, False),
                )

                fragment_id = (await cur.fetchone())[0]
                await conn.commit()

                return {
                    "message": f"Fragment '{fragment.name}' created",
                    "id": fragment_id,
                }
            except psycopg.IntegrityError:
                raise HTTPException(
                    status_code=400, detail="Fragment name already exists"
                )


# DELETE FRAGMENT
@app.delete("/api/prompt-fragments/{fragment_id}")
async def delete_prompt_fragment(fragment_id: int):
    """Poista prompt-fragmentti (vain käyttäjän luomat)"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            # Check if fragment exists and is not system
            await cur.execute(
                """
                SELECT is_system FROM prompt_fragments WHERE id = %s
            """,
                (fragment_id,),
            )

            result = await cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Fragment not found")

            if result[0]:  # is_system = True
                raise HTTPException(
                    status_code=403, detail="Cannot delete system fragment"
                )

            # Check if used in ANY composition
            await cur.execute(
                """
                SELECT name FROM prompt_compositions 
                WHERE %s = ANY(fragment_ids)
            """,
                (fragment_id,),
            )

            compositions = await cur.fetchall()
            if compositions:
                composition_names = [row[0] for row in compositions]
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot delete fragment: used in compositions: {', '.join(composition_names)}",
                )

            # Delete fragment
            await cur.execute(
                """
                DELETE FROM prompt_fragments WHERE id = %s
            """,
                (fragment_id,),
            )

            await conn.commit()
            return {"message": "Fragment deleted"}


# PROMPT COMPOSITIONS ROUTES
@app.get("/api/prompt-compositions")
async def get_prompt_compositions():
    """Hae kaikki prompt-kokoonpanot"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, name, ethical_persona_id, fragment_ids, is_active, created_at
                FROM prompt_compositions 
                ORDER BY is_active DESC, created_at DESC
            """
            )
            rows = await cur.fetchall()

            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "ethical_persona_id": row[2],
                    "fragment_ids": row[3] or [],
                    "is_active": row[4],
                    "created_at": row[5].isoformat() if row[5] else None,
                }
                for row in rows
            ]


@app.post("/api/prompt-compositions")
async def create_prompt_composition(composition: PromptComposition):
    """Luo uusi prompt-kokoonpano"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            # Validate persona exists
            await cur.execute(
                """
                SELECT COUNT(*) FROM prompt_ethical_personas WHERE id = %s
            """,
                (composition.ethical_persona_id,),
            )

            if (await cur.fetchone())[0] == 0:
                raise HTTPException(status_code=400, detail="Ethical persona not found")

            # Validate fragments exist (if any)
            if composition.fragment_ids:
                await cur.execute(
                    """
                    SELECT COUNT(*) FROM prompt_fragments WHERE id = ANY(%s)
                """,
                    (composition.fragment_ids,),
                )

                if (await cur.fetchone())[0] != len(composition.fragment_ids):
                    raise HTTPException(
                        status_code=400, detail="One or more fragments not found"
                    )

            try:
                await cur.execute(
                    """
                    INSERT INTO prompt_compositions (name, ethical_persona_id, fragment_ids, is_active)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """,
                    (
                        composition.name,
                        composition.ethical_persona_id,
                        composition.fragment_ids,
                        False,
                    ),
                )

                composition_id = (await cur.fetchone())[0]
                await conn.commit()

                return {
                    "message": f"Composition '{composition.name}' created",
                    "id": composition_id,
                }
            except psycopg.IntegrityError:
                raise HTTPException(
                    status_code=400, detail="Composition name already exists"
                )


@app.put("/api/prompt-compositions/{composition_id}/activate")
async def activate_composition(composition_id: int):
    """Aktivoi tietty kokoonpano (deaktivoi muut)"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            # Check composition exists
            await cur.execute(
                """
                SELECT name FROM prompt_compositions WHERE id = %s
            """,
                (composition_id,),
            )

            result = await cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Composition not found")

            composition_name = result[0]

            # Deactivate all compositions
            await cur.execute(
                """
                UPDATE prompt_compositions SET is_active = false, updated_at = NOW()
                WHERE is_active = true
            """
            )

            # Activate this composition
            await cur.execute(
                """
                UPDATE prompt_compositions 
                SET is_active = true, updated_at = NOW()
                WHERE id = %s
            """,
                (composition_id,),
            )

            await conn.commit()
            return {"message": f"Composition '{composition_name}' activated"}


@app.get("/api/current-prompt")
async def get_current_active_prompt():
    """Hae aktiivinen prompt uutisten arviointiin"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            # Get active composition with persona
            await cur.execute(
                """
                SELECT 
                    pc.id, pc.name, pc.fragment_ids,
                    pep.name as persona_name, pep.content as persona_content
                FROM prompt_compositions pc
                JOIN prompt_ethical_personas pep ON pc.ethical_persona_id = pep.id
                WHERE pc.is_active = true
                LIMIT 1
            """
            )

            comp_result = await cur.fetchone()
            if not comp_result:
                raise HTTPException(
                    status_code=404, detail="No active composition found"
                )

            comp_id, comp_name, fragment_ids, persona_name, persona_content = (
                comp_result
            )

            # Get fragments if any
            ordered_fragments = []
            if fragment_ids:
                await cur.execute(
                    """
                    SELECT id, content FROM prompt_fragments WHERE id = ANY(%s)
                """,
                    (fragment_ids,),
                )

                fragment_rows = await cur.fetchall()
                fragment_dict = {row[0]: row[1] for row in fragment_rows}

                # Order fragments according to fragment_ids order
                ordered_fragments = [
                    fragment_dict[fid] for fid in fragment_ids if fid in fragment_dict
                ]

            # Build final prompt: persona first, then fragments
            prompt_parts = [persona_content] + ordered_fragments
            final_prompt = "\n\n".join(prompt_parts)

            return {
                "content": final_prompt,
                "composition_name": comp_name,
                "ethical_persona": persona_name,
                "fragment_count": len(ordered_fragments),
            }


@app.delete("/api/prompt-compositions/{composition_id}")
async def delete_composition(composition_id: int):
    """Poista prompt-kokoonpano"""
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            # Check if composition exists and is not active
            await cur.execute(
                """
                SELECT is_active FROM prompt_compositions WHERE id = %s
            """,
                (composition_id,),
            )

            result = await cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Composition not found")

            if result[0]:  # is_active = True
                raise HTTPException(
                    status_code=400, detail="Cannot delete active composition"
                )

            # Delete composition
            await cur.execute(
                """
                DELETE FROM prompt_compositions WHERE id = %s
            """,
                (composition_id,),
            )

            await conn.commit()
            return {"message": "Composition deleted"}


# FOR TESTING editor_in_chief agent
@app.post("/api/test-article-simple", response_model=TestArticleResponse)
async def test_article_simple(request: SimpleArticleTest):
    """Testaa artikkelia pelkällä tekstillä – palauttaa maksimaalisen strukturoitun datan"""
    try:
        model_name = "gpt-4o-mini"
        llm = init_chat_model(model_name, model_provider="openai")

        test_article = EnrichedArticle(
            article_id="test-simple",
            canonical_news_id=999,
            news_article_id=999,
            enriched_title=request.title,
            enriched_content=request.content,
            published_at="2024-01-01T10:00:00Z",
            source_domain="test.fi",
            keywords=[],
            categories=["Yleinen"],
            language="fi",
            sources=["https://test.fi/original"],
            references=[],
            locations=[],
            summary=(request.content[:200] + "..." if len(request.content) > 200 else request.content),
            enrichment_status="success",
            original_article_type="news",
            contacts=[],
        )

        initial_state = AgentState(
            current_article=test_article,
            enriched_articles=[test_article],
            reviewed_articles=[],
            review_result=None,
        )

        class MockEditorialReviewService:
            def __init__(self, db_dsn): ...
            def save_review(self, news_article_id, review_result): return True

        original_init = EditorInChiefAgent.__init__

        def mock_init(self, llm, db_dsn: str):
            from agents.base_agent import BaseAgent
            from schemas.editor_in_chief_schema import ReviewedNewsItem
            BaseAgent.__init__(self, llm=llm, prompt=None, name="EditorInChiefAgent")
            self.structured_llm = self.llm.with_structured_output(ReviewedNewsItem)
            self.db_dsn = db_dsn
            # Hae aktiivinen prompt normaalisti kannasta
            self.active_prompt = self._get_active_persona_prompt()
            # Korvaa vain tallennuspalvelu
            self.editorial_service = MockEditorialReviewService(db_dsn)

        EditorInChiefAgent.__init__ = mock_init

        try:
            editor_agent = EditorInChiefAgent(llm, DATABASE_URL)
            result_state = editor_agent.run(initial_state)

            review = getattr(result_state, "review_result", None)
            if review:
                try:
                    review_dict = review.model_dump()  # Pydantic v2
                except Exception:
                    review_dict = review.dict() if hasattr(review, "dict") else {}

                featured = bool(getattr(getattr(review, "headline_news_assessment", None), "featured", False))
                interview_needed = bool(getattr(getattr(review, "interview_decision", None), "interview_needed", False))
                issues_count = len(getattr(review, "issues", []) or [])
                er = getattr(review, "editorial_reasoning", None)
                reasoning = getattr(er, "explanation", None) or getattr(er, "explanation_text", None) or "Ei perusteluja"
                decision = getattr(review, "editorial_decision", "unknown")

                return TestArticleResponse(
                    status="success",
                    editorial_decision=decision,
                    featured=featured,
                    interview_needed=interview_needed,
                    issues_count=issues_count,
                    reasoning=reasoning,
                    message="Arviointi valmis",
                    review=review_dict,                       # koko strukturoitu data frontille
                    prompt_used=getattr(editor_agent, "active_prompt", None),
                    model=model_name,
                )

            return TestArticleResponse(
                status="error",
                editorial_decision="unknown",
                featured=False,
                interview_needed=False,
                issues_count=0,
                reasoning="Ei tulosta",
                message="Arviointi epäonnistui",
                review=None,
                prompt_used=None,
                model=model_name,
            )

        finally:
            EditorInChiefAgent.__init__ = original_init

    except Exception as e:
        log.error(f"Virhe artikkeliarviossa: {str(e)}")
        return TestArticleResponse(
            status="error",
            editorial_decision="error",
            featured=False,
            interview_needed=False,
            issues_count=0,
            reasoning=f"Virhe: {str(e)}",
            message="Tekninen virhe",
            review=None,
            prompt_used=None,
            model=model_name if "model_name" in locals() else None,
        )



# Käynnistä server suoraan
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")

    log.info(f"Starting callback server on {host}:{port}")
    uvicorn.run("server:app", host=host, port=port, reload=True, log_level="info")
