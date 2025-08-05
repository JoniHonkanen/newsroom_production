from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle
from schemas.interview_schema import (
    InterviewPlan,
    EmailInterviewPlan,
    PhoneInterviewPlan,
)
from pydantic import BaseModel, Field
from typing import Optional

#TODO:: NEEDS TESTING!!!

# Simplified Article Enrichment Prompt
ARTICLE_ENRICHMENT_PROMPT = """
You are an experienced journalist responsible for enriching articles with interview content.

You have been given:
1. An original article that needed additional perspectives
2. Raw interview content from an expert source
3. Information about the expert who provided the content

Your task is to create an enriched version of the article that integrates the interview content to provide better balance, expert perspectives, and journalistic depth.

## ORIGINAL ARTICLE:

**Title:** {article_title}

**Content:**
{article_content}

## INTERVIEW CONTENT:

**Expert:** {respondent_name}
**Title:** {respondent_title}
**Organization:** {respondent_organization}

**Content:**
{interview_content}

## INTERVIEW CONTEXT:

**Interview Focus:** {interview_focus}
**Target Expertise Areas:** {target_expertise_areas}

## ENRICHMENT GUIDELINES:

### INTEGRATION STRATEGY:
1. **Preserve original structure** - Enhance existing content, don't completely rewrite
2. **Extract key insights** - Identify the most valuable quotes and insights from the interview content
3. **Strategic placement** - Add expert perspectives that support, challenge, or expand key points
4. **Maintain journalistic tone** - Keep the original article's style and language ({language})
5. **Expert attribution** - Properly credit the source with title and organization

### CONTENT ENHANCEMENT:
- Parse the interview content to find relevant quotes and insights
- Integrate expert perspectives that weren't in the original article
- Add context and explanations that strengthen the story
- Address gaps identified in the original editorial review
- Ensure all additions provide genuine journalistic value

### QUALITY FOCUS:
- Enrichment over expansion - focus on quality insights, not just length
- Use expert credentials appropriately to add credibility
- Ensure smooth integration - new content should flow naturally
- Every addition should serve the reader and strengthen the story

## ENRICHED ARTICLE:

Create an enriched version of the article that strategically integrates the interview content while maintaining the original article's core message and journalistic integrity.
"""


class EnrichedArticleResult(BaseModel):
    """Result of article enrichment process."""

    enriched_title: str = Field(description="Enriched article title")
    enriched_content: str = Field(description="Complete enriched article content")
    enrichment_summary: str = Field(description="Summary of what was enriched")
    respondent_name: str = Field(description="Name of expert source integrated")


class ArticleEnricherAgent(BaseAgent):
    """Agent that enriches articles with raw interview content."""

    def __init__(self, llm, db_dsn: str):
        super().__init__(
            llm=llm, prompt=ARTICLE_ENRICHMENT_PROMPT, name="ArticleEnricherAgent"
        )
        self.db_dsn = db_dsn

    def run(self, state: AgentState) -> AgentState:
        """Enriches article with raw interview content."""
        print("✨ ARTICLE ENRICHER AGENT: Enriching article with interview content...")

        if not hasattr(state, "current_article") or not state.current_article:
            print("❌ ArticleEnricherAgent: No current_article to enrich!")
            return state

        article: EnrichedArticle = state.current_article

        # Get raw interview content from state
        raw_content = getattr(state, "raw_interview_content", None)
        if not raw_content:
            print("❌ ArticleEnricherAgent: No raw_interview_content found in state!")
            return state

        # Get respondent info
        respondent_name = getattr(state, "respondent_name", "Unknown Expert")
        respondent_title = getattr(state, "respondent_title", None)
        respondent_organization = getattr(state, "respondent_organization", None)

        print(f"📚 Processing interview content from: {respondent_name}")
        print(f"📝 Content length: {len(raw_content)} characters")

        # Get interview plan for context
        interview_plan = getattr(state, "interview_plan", None)

        try:
            # Create enriched article
            enriched_result = self._enrich_article(
                article,
                raw_content,
                respondent_name,
                respondent_title,
                respondent_organization,
                interview_plan,
            )

            # Update the article with enriched content
            article.enriched_content = enriched_result.enriched_content
            article.enriched_title = enriched_result.enriched_title

            # Store enrichment result in state
            state.enrichment_result = enriched_result
            state.current_article = article

            print("✅ Article enrichment completed successfully!")
            print(f"   📰 Title: {enriched_result.enriched_title[:60]}...")
            print(f"   👤 Expert integrated: {enriched_result.respondent_name}")
            print(
                f"   📄 Content length: {len(enriched_result.enriched_content)} chars"
            )

            return state

        except Exception as e:
            print(f"❌ Error enriching article: {e}")
            import traceback

            traceback.print_exc()
            return state

    def _enrich_article(
        self,
        article: EnrichedArticle,
        interview_content: str,
        respondent_name: str,
        respondent_title: Optional[str],
        respondent_organization: Optional[str],
        interview_plan: Optional[InterviewPlan] = None,
    ) -> EnrichedArticleResult:
        """Use LLM to enrich article with raw interview content."""

        # Get context from interview plan
        interview_focus = "Additional expert perspectives"
        target_expertise_areas = []

        if interview_plan:
            if interview_plan.email_plan:
                interview_focus = interview_plan.email_plan.interview_focus
                target_expertise_areas = (
                    interview_plan.email_plan.target_expertise_areas
                )
            elif interview_plan.phone_plan:
                interview_focus = interview_plan.phone_plan.interview_focus
                target_expertise_areas = (
                    interview_plan.phone_plan.target_expertise_areas
                )

        # Create structured output model
        class ArticleEnrichmentResponse(BaseModel):
            enriched_title: str = Field(description="Enriched article title")
            enriched_content: str = Field(
                description="Complete enriched article content"
            )
            enrichment_summary: str = Field(description="Summary of enhancements made")

        # Prepare the enrichment prompt
        prompt = self.prompt.format(
            article_title=article.enriched_title,
            article_content=article.enriched_content,
            interview_content=interview_content,
            respondent_name=respondent_name,
            respondent_title=respondent_title or "N/A",
            respondent_organization=respondent_organization or "N/A",
            interview_focus=interview_focus,
            target_expertise_areas=", ".join(target_expertise_areas),
            language=getattr(article, "language", "fi"),
        )

        # Use structured output
        structured_llm = self.llm.with_structured_output(ArticleEnrichmentResponse)
        response = structured_llm.invoke(prompt)

        return EnrichedArticleResult(
            enriched_title=response.enriched_title,
            enriched_content=response.enriched_content,
            enrichment_summary=response.enrichment_summary,
            respondent_name=respondent_name,
        )


# TEST RUNNER
if __name__ == "__main__":
    import os
    from langchain.chat_models import init_chat_model
    from schemas.agent_state import AgentState
    from dotenv import load_dotenv
    import json

    load_dotenv()

    print("🧪 TESTING ArticleEnricherAgent (SIMPLIFIED)...")

    try:
        llm = init_chat_model("gpt-4o-mini", model_provider="openai")
        print("✅ LLM initialized successfully.")
    except Exception as e:
        print(f"❌ Failed to initialize LLM: {e}")
        exit()

    db_dsn = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/newsdb")

    # Initialize agent
    agent = ArticleEnricherAgent(llm, db_dsn)

    # Create mock article
    mock_article = EnrichedArticle(
        article_id="test-article-12345",
        news_article_id=12345,
        enriched_title="Kauppakeskuksen Sähköakkuhanke Herättää Kysymyksiä Turvallisuudesta",
        enriched_content="""
# Kauppakeskuksen Sähköakkuhanke Herättää Kysymyksiä Turvallisuudesta

Rovaniemeläinen kauppakeskus Rinteenkulma on hankkinut kiinalaisia Huawei-akkuja puolen miljoonan euron arvosta. 
Hanke liittyy sähköverkon varajärjestelmiin, mutta herättää kysymyksiä turvallisuudesta.

Kauppakeskuksen johtaja Pekka Rinne kertoo, että akut tulevat osaksi sähköverkon tasapainotusta.
Fingridin edustaja Mikko Kuivaniemi kommentoi, että tällaisia hankkeita on useita käynnissä.

Kriitikot nostavat esiin huolia kiinalaisten komponenttien turvallisuusriskeistä infrastruktuurissa.
        """,
        published_at="2025-07-28T10:00:00Z",
        source_domain="test-news.fi",
        keywords=["sähköakut", "Huawei", "turvallisuus", "infrastruktuuri"],
        categories=["teknologia", "energia"],
        language="fi",
        sources=["https://example.com/source1"],
        summary="Kauppakeskus hankki kiinalaisia akkuja, herättää turvallisuuskysymyksiä",
        contacts=[],
    )

    # Test with email content
    email_content = """
Hei,

Kiitos kysymyksistänne. Vastaan mielelläni:

Turvallisuusriskeistä: Kiinalaisten akkujärjestelmien käyttö infrastruktuurissa vaatii huolellista riskinarviointia. Teknologia on laadukasta, mutta geopoliittiset näkökohdat on otettava huomioon kriittisessä infrastruktuurissa.

Sähköverkon toiminnasta: Akkujärjestelmät tarjoavat nopeaa säätövoimaa ja parantavat verkon vakautta. Huawein teknologia on teknisesti korkealaatuista ja soveltuu kaupallisiin sovelluksiin.

Ystävällisin terveisin,
Dr. Marja Kyberturva
    """

    # Test with phone content
    phone_transcript = [
        {
            "speaker": "assistant",
            "text": "Mikä on näkemyksenne turvallisuusriskeistä kiinalaisessa teknologiassa?",
        },
        {
            "speaker": "user",
            "text": "Kiinalaisten akkujärjestelmien käyttö vaatii huolellista arviointia.",
        },
        {
            "speaker": "user",
            "text": "Geopoliittiset riskit on otettava huomioon infrastruktuurissa.",
        },
        {"speaker": "assistant", "text": "Entä energiamarkkinoiden näkökulmasta?"},
        {
            "speaker": "user",
            "text": "Akkuteknologia tarjoaa nopeaa säätövoimaa verkon vakauteen.",
        },
    ]
    phone_content = json.dumps(phone_transcript)

    print("\n📋 TEST INPUT:")
    print(f"   Original article: {len(mock_article.enriched_content)} characters")
    print(f"   Email content: {len(email_content)} characters")
    print(f"   Phone content: {len(phone_content)} characters")

    # Test 1: Email content
    print("\n🧪 TESTING WITH EMAIL CONTENT:")
    mock_state = AgentState()
    mock_state.current_article = mock_article
    mock_state.raw_interview_content = email_content
    mock_state.respondent_name = "Dr. Marja Kyberturva"
    mock_state.respondent_title = "Kyberturvallisuusasiantuntija"
    mock_state.respondent_organization = "Huoltovarmuuskeskus"

    result_state = agent.run(mock_state)

    if hasattr(result_state, "enrichment_result") and result_state.enrichment_result:
        result = result_state.enrichment_result
        print(f"   ✅ Email enrichment successful!")
        print(f"   📰 Enhanced title: {result.enriched_title[:80]}...")
        print(f"   👤 Expert: {result.respondent_name}")
        print(f"   📝 Summary: {result.enrichment_summary[:100]}...")
    else:
        print("   ❌ Email enrichment failed!")

    # Test 2: Phone content
    print("\n🧪 TESTING WITH PHONE CONTENT:")
    mock_state2 = AgentState()
    mock_state2.current_article = mock_article
    mock_state2.raw_interview_content = phone_content
    mock_state2.respondent_name = "Ing. Paavo Energiamies"
    mock_state2.respondent_title = "Verkkoasiantuntija"
    mock_state2.respondent_organization = "Energiateollisuus ry"

    result_state2 = agent.run(mock_state2)

    if hasattr(result_state2, "enrichment_result") and result_state2.enrichment_result:
        result2 = result_state2.enrichment_result
        print(f"   ✅ Phone enrichment successful!")
        print(f"   📰 Enhanced title: {result2.enriched_title[:80]}...")
        print(f"   👤 Expert: {result2.respondent_name}")
        print(f"   📝 Summary: {result2.enrichment_summary[:100]}...")
    else:
        print("   ❌ Phone enrichment failed!")

    print("\n🎯 Test completed - ArticleEnricherAgent (SIMPLIFIED) ready!")
    print("\n💡 KEY FEATURES:")
    print("   ✅ Handles raw interview content (email body, phone JSON, anything)")
    print("   ✅ No complex parsing - LLM handles everything")
    print("   ✅ Simple state interface - just raw content + respondent info")
    print("   ✅ Quality focus - enrichment over expansion")
    print("   ✅ Maintains original article structure and style")
