import os, asyncio, logging
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any
from dotenv import load_dotenv
load_dotenv()

# Import phone interview integration
from integrations.phone_interview_integration import enrich_article_with_phone_call

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("callback-api")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me")

app = FastAPI(title="Newsroom Callback API", version="0.1.0")


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


class CallEndedPayload(BaseModel):
    article_id: int 
    interview: List[Dict[str, Any]]


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


# TODO: Jos haluat myöhemmin lisätä transcript URL:n latauksen
# Ei tarvita enää, koska haastatteludata tulee suoraan JSON:ina


# Käynnistä server suoraan
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")

    log.info(f"Starting callback server on {host}:{port}")
    uvicorn.run("server:app", host=host, port=port, reload=True, log_level="info")
