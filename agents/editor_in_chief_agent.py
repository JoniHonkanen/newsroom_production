# File: agents/editor_in_chief_agent.py

import sys
import os

# Add the project root to the Python path FIRST
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

# Now import the modules
from schemas.editor_in_chief_schema import (
    EditorialReasoning,
    InterviewDecision,
    ReasoningStep,
    ReviewIssue,
    ReviewedNewsItem,
    HeadlineNewsAssessment,
)
from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle
from services.editor_review_service import EditorialReviewService


EDITOR_IN_CHIEF_PROMPT = """
{persona}

Your task is to review the news article and verify that it complies with:
- Finnish journalistic law (Freedom of Expression Act, Criminal Code)
- JSN's Journalistin ohjeet (ethical code)
- Our editorial and stylistic standards
- Assessment of headline news worthiness

As Editor-in-Chief, your responsibility includes not only identifying issues but also exercising editorial judgment. Do not reject an article unless it contains substantial legal, factual, or ethical violations. Minor or technical issues should lead to correction suggestions, not rejection.

You must explain your reasoning clearly and explicitly. Each decision, observation, and conclusion must be logged step-by-step, with justification. This includes both the initial decision and any reconsideration. Do not omit or summarize critical steps. The rationale must be transparent, traceable, and match the final editorial outcome.

Proceed step by step through the following categories. For each step:
– Briefly state what was checked  
– Evaluate whether the article meets the criteria and why  
– List any issues and propose corrections if necessary

### Step 1: Legal Compliance
– No defamation, hate speech, or privacy violations  
– Correct attribution of quotes and sources  
– Follows Finnish Freedom of Expression Act and Criminal Code

### Step 2: Journalistic Accuracy & Balance
– Verifiable and sourced facts  
– Relevant perspectives fairly represented  
– No hidden conflicts of interest

### Step 3: Ethical Standards (JSN)
– Respect for privacy and human dignity  
– No misleading framing, headlines or omissions  
– Individuals treated fairly, with chance to respond if criticized

### Step 4: Style & Structure
– Clear and coherent structure: headline, subheadings, paragraphs  
– Professional, neutral tone  
– Proper use of quotes, context, statistics

### Step 5: Corrections & Accountability
– Identify significant legal, factual or ethical errors  
– Suggest clear corrections if needed  
– Correction policy is encouraged, but its absence is not grounds for rejection unless other serious accountability issues are present

### Step 6: Featured Article Assessment (ETUSIVULLE)
This is CRITICAL for editorial decision-making. Assess whether this article should be featured on the front page:

**Key Questions:**
- Does this affect many Finns or have broad public interest?
- Is this timely, breaking news or highly current?
- Would readers expect to see this as a top story?
- Is this more important than typical daily news?

**Guidelines:**
- Only 2-3 stories per day should be featured
- Featured articles should serve broad public interest
- Consider: politics, economy, major events, breaking news
- Avoid: routine announcements, very local news, niche topics

You must provide clear reasoning for your featured assessment.

### Step 7: Interview Decision (HAASTATTELUPÄÄTÖS)
Decide whether this article requires additional interviews to provide balanced, comprehensive coverage:

**When interviews are typically needed:**
- Press releases: Independent expert perspective to verify claims
- Breaking news: Expert analysis or context from authorities
- Controversial topics: Multiple viewpoints for balance
- Technical subjects: Expert explanations for general audience
- Policy announcements: Affected parties' reactions

**When interviews are usually NOT needed:**
- Routine announcements with clear facts
- Event reports with sufficient eyewitness accounts
- Articles already containing expert quotes and analysis
- Time-sensitive breaking news where speed is critical

**Interview method considerations:**
- **Phone**: For urgent breaking news, immediate expert reactions
- **Email**: For detailed analysis, technical explanations, non-urgent topics

**Expertise areas to consider:**
- Subject matter experts (technology, economy, law, medicine, etc.)
- Affected stakeholders (citizens, organizations, industry representatives)
- Opposition voices or alternative perspectives
- Academic researchers or independent analysts

You must justify your interview decision based on journalistic value and public interest.

### Step 8: Final Checklist Review
Go through the following items and confirm if each one is satisfied. If any are not, explain why and how it can be fixed.
- [ ] All key facts are verified (minor unsourced details may be flagged but not block publication)  
- [ ] Legally compliant (no defamation, hate speech, or clear violations)  
- [ ] No major ethical violations  
- [ ] Balanced and fair representation of relevant perspectives  
- [ ] Correction policy present or not critical for this article type  
- [ ] Tone is professional and neutral
- [ ] Featured article assessment completed with proper justification
- [ ] Interview decision made with proper justification

### Important: Justify All Reasoning Transparently
You must log all observations and decisions. For each step, explain what was checked, what was found, and how it contributed to the final decision. Your final explanation must clearly show why the article was accepted or rejected, AND why it received its specific featured article assessment. This review will be recorded for auditing purposes.

**Remember:** Not all controversy is avoidable or undesirable. Responsible journalism may challenge readers. Do not suppress legitimate reporting simply because it may offend or provoke—only reject content that clearly breaches law, ethics, or accuracy. However, featured articles should serve the broader public interest and have wide appeal.

### This is the Article to be Reviewed
**Title:** {article_title}

**Content:**
{generated_article_markdown}

**Additional Context:**
- Language: {language}
- Source Domain: {source_domain}
- Keywords: {keywords}
- Categories: {categories}
- Published: {published_at}
- Time of Review: Consider what other major news might be competing for headlines today
"""

EDITOR_PERSONA = """
You are the Editor-in-Chief of a Finnish digital news platform. You have 15 years of experience in journalism, including 8 years as a senior editor at major Finnish newspapers. You are well-versed in:

- Finnish media law (Freedom of Expression Act, Criminal Code)
- JSN's ethical guidelines (Journalistin ohjeet)
- Modern digital journalism standards
- Editorial responsibility and accountability
- News value assessment and headline selection

Your editorial philosophy emphasizes:
- Accuracy and verification above speed
- Balanced reporting that serves the public interest
- Ethical treatment of all individuals and groups
- Legal compliance without sacrificing journalistic integrity
- Clear, accessible writing that respects readers' intelligence
- Strategic headline selection that maximizes public service and readership

You understand that headline news selection is crucial for:
- Attracting and retaining readers
- Serving the public interest
- Maintaining editorial credibility
- Competing effectively in the digital news landscape

You make decisions based on professional judgment, not personal opinion. You understand that journalism sometimes requires publishing uncomfortable truths, but you never compromise on accuracy, fairness, or legal compliance. You also understand that not every good story is headline material - headlines must serve the broader public interest and have wide appeal.

Your headline selection criteria prioritize:
1. Public interest and impact
2. Timeliness and relevance
3. Broad audience appeal
4. Editorial balance across different topics
5. Competitive positioning against other news sources

FOR TESTING PURPOSE, REJECT ALL ARTICLES THAT DO NOT MEET THE CRITERIA ABOVE.
THIS IS IMPORTANT: STATUS NEED TO BE "REVISE" OR "REJECT" FOR TESTING PURPOSES.
"""


class EditorInChiefAgent(BaseAgent):
    """An agent that reviews enriched articles for legal, ethical, and editorial compliance, including headline news assessment."""

    def __init__(self, llm, db_dsn: str):
        super().__init__(llm=llm, prompt=None, name="EditorInChiefAgent")
        self.structured_llm = self.llm.with_structured_output(ReviewedNewsItem)
        self.editorial_service = EditorialReviewService(db_dsn)

    def _format_article_for_review(self, article: EnrichedArticle) -> str:
        """Format an enriched article for editorial review."""
        return f"""
        # {article.enriched_title}
        
        {article.enriched_content}
        
        ---
        **Summary:** {article.summary}
        **Sources:** {len(article.sources)} sources referenced
        """

    def review_article(self, article: EnrichedArticle) -> ReviewedNewsItem:
        """Review a single enriched article and save to database."""
        print(f"🔍 Reviewing: {article.enriched_title[:60]}...")

        # Check if article has been stored to database
        if not article.news_article_id:
            print(f"❌ Article {article.article_id} has no news_article_id!")
            print("   This article was not properly stored to database.")
            print("   Cannot save editorial review without news_article_id.")

            # Create error review but don't try to save it
            return ReviewedNewsItem(
                status="ISSUES_FOUND",
                issues=[
                    ReviewIssue(
                        type="Other",
                        location="Review Process",
                        description="Article not stored in database - missing news_article_id",
                        suggestion="Ensure ArticleStorerAgent runs before EditorInChiefAgent",
                    )
                ],
                editorial_reasoning=EditorialReasoning(
                    reviewer="EditorInChiefAgent",
                    initial_decision="REJECT",
                    checked_criteria=["Database Storage"],
                    failed_criteria=["Database Storage"],
                    reasoning_steps=[
                        ReasoningStep(
                            step_id=1,
                            action="Check Database Storage",
                            observation="Article has no news_article_id",
                            result="FAIL",
                        )
                    ],
                    explanation="Cannot review article that is not stored in database",
                ),
                headline_news_assessment=HeadlineNewsAssessment(
                    featured=False,
                    reasoning="Technical error prevented proper featured assessment",
                ),
                interview_decision=InterviewDecision(
                    interview_needed=False,
                    justification="Technical error prevented proper interview assessment",
                ),
            )

        print(f"📋 Using news_article.id: {article.news_article_id}")

        # Format the article content for review
        formatted_content = self._format_article_for_review(article)

        # Prepare the prompt
        prompt_content = EDITOR_IN_CHIEF_PROMPT.format(
            persona=EDITOR_PERSONA,
            article_title=article.enriched_title,
            generated_article_markdown=formatted_content,
            language=article.language,
            source_domain=article.source_domain,
            keywords=", ".join(article.keywords),
            categories=", ".join(article.categories),
            published_at=article.published_at,
        )

        try:
            # Get structured review from LLM
            review_result = self.structured_llm.invoke(prompt_content)

            # Save to database using news_article_id
            success = self.editorial_service.save_review(
                article.news_article_id, review_result
            )

            if success:
                print(
                    f"💾 Saved editorial review to database for news_article.id {article.news_article_id}"
                )
            else:
                print(
                    f"⚠️  Failed to save editorial review for news_article.id {article.news_article_id}"
                )

            # Display results
            print(f"\n{'='*80}")
            print(f"📋 PÄÄTOIMITAJAN ARVIOINTI")
            print(f"{'='*80}")
            print(f"📰 Artikkeli: {article.enriched_title}")
            print(f"🔢 News Article ID: {article.news_article_id}")
            print(f"⚖️  Lopputulos: {review_result.status}")

            # Show headline news assessment
            if review_result.headline_news_assessment:
                headline_assessment = review_result.headline_news_assessment
                print(f"\n🏆 FEATURED-ARVIOINTI:")

                featured_status = (
                    "✅ FEATURED" if headline_assessment.featured else "❌ EI FEATURED"
                )
                print(f"   🎯 Status: {featured_status}")
                print(f"   📝 Perustelu: {headline_assessment.reasoning}")

            if review_result.interview_decision:
                interview_decision = review_result.interview_decision
                print(f"\n🎤 HAASTATTELUPÄÄTÖS:")

                interview_status = (
                    "✅ TARVITAAN HAASTATTELU"
                    if interview_decision.interview_needed
                    else "❌ EI HAASTATTELUA"
                )
                print(f"   🎯 Status: {interview_status}")
                print(f"   📝 Perustelu: {interview_decision.justification}")

                if interview_decision.interview_needed:
                    if interview_decision.interview_method:
                        method_emoji = (
                            "📧"
                            if interview_decision.interview_method == "email"
                            else "📞"
                        )
                        print(
                            f"   {method_emoji} Menetelmä: {interview_decision.interview_method}"
                        )

                    if interview_decision.target_expertise_areas:
                        print(
                            f"   🎯 Asiantuntemus: {', '.join(interview_decision.target_expertise_areas)}"
                        )

                    if interview_decision.interview_focus:
                        print(f"   🔍 Fokus: {interview_decision.interview_focus}")

                    if interview_decision.article_type_influence:
                        print(
                            f"   📄 Artikkelityypin vaikutus: {interview_decision.article_type_influence}"
                        )

            # Show editorial reasoning process
            if review_result.editorial_reasoning:
                reasoning = review_result.editorial_reasoning

                print(f"\n🧠 PÄÄTTELYPROSESSI:")
                print(f"   👤 Arvioija: {reasoning.reviewer}")
                print(f"   🎯 Alkupäätös: {reasoning.initial_decision}")

                print(f"\n📋 ARVIOIDUT KRITEERIT:")
                for criterion in reasoning.checked_criteria:
                    status = "❌" if criterion in reasoning.failed_criteria else "✅"
                    print(f"   {status} {criterion}")

                if reasoning.reasoning_steps:
                    print(f"\n🔍 VAIHEITTAINEN ARVIOINTI:")
                    for step in reasoning.reasoning_steps:
                        emoji = {"PASS": "✅", "FAIL": "❌", "INFO": "ℹ️"}.get(
                            step.result, "🔹"
                        )
                        print(f"\n   {step.step_id}. {emoji} {step.action}")
                        print(f"      💭 Havainto: {step.observation}")
                        print(f"      📊 Tulos: {step.result}")

                print(f"\n📝 PÄÄTÖKSEN PERUSTELU:")
                print(f"   {reasoning.explanation}")

                # Show reconsideration if it happened
                if reasoning.reconsideration:
                    recon = reasoning.reconsideration
                    print(f"\n🤔 UUDELLEENARVIOINTI:")
                    print(f"   🎯 Lopullinen päätös: {recon.final_decision}")
                    print(
                        f"   📋 Uudelleen arvioitut kriteerit: {', '.join(recon.failed_criteria)}"
                    )
                    if recon.reasoning_steps:
                        print(f"   🔍 Lisävaiheet:")
                        for step in recon.reasoning_steps:
                            emoji = {"PASS": "✅", "FAIL": "❌", "INFO": "ℹ️"}.get(
                                step.result, "🔹"
                            )
                            print(f"      • {emoji} {step.action}: {step.observation}")
                    print(f"   💬 Selitys: {recon.explanation}")

            # Show issues found
            if review_result.issues:
                print(f"\n⚠️  LÖYDETYT ONGELMAT ({len(review_result.issues)}):")
                for i, issue in enumerate(review_result.issues, 1):
                    print(f"\n   {i}. {issue.type.upper()} - {issue.location}")
                    print(f"      🔍 Ongelma: {issue.description}")
                    print(f"      💡 Ehdotus: {issue.suggestion}")

            # Show approval comment if given
            if review_result.approval_comment:
                print(f"\n✅ HYVÄKSYNTÄKOMMENTTI:")
                print(f"   {review_result.approval_comment}")

            # Show editorial warning if issued
            if review_result.editorial_warning:
                warning = review_result.editorial_warning
                print(f"\n⚠️  TOIMITUKSELLINEN VAROITUS:")
                print(f"   📂 Kategoria: {warning.category}")
                print(f"   📝 Lukijoille: {warning.details}")
                if warning.topics:
                    print(f"   🏷️  Aiheet: {', '.join(warning.topics)}")

            # Show final reconsideration if separate from reasoning
            if (
                review_result.reconsideration
                and not review_result.editorial_reasoning.reconsideration
            ):
                recon = review_result.reconsideration
                print(f"\n🎯 LOPULLINEN UUDELLEENARVIOINTI:")
                print(f"   📊 Päätös: {recon.final_decision}")
                print(f"   💬 Perustelu: {recon.explanation}")

            print(f"\n{'='*80}")

            return review_result

        except Exception as e:
            print(f"❌ Virhe arvioinnissa: {e}")
            # Return a default "issues found" review in case of error
            error_review = ReviewedNewsItem(
                status="ISSUES_FOUND",
                issues=[
                    ReviewIssue(
                        type="Other",
                        location="Review Process",
                        description=f"Technical error during review: {str(e)}",
                        suggestion="Manual review required",
                    )
                ],
                editorial_reasoning=EditorialReasoning(
                    reviewer="EditorInChiefAgent",
                    initial_decision="REJECT",
                    checked_criteria=["Technical Review"],
                    failed_criteria=["Technical Review"],
                    reasoning_steps=[
                        ReasoningStep(
                            step_id=1,
                            action="Technical Review",
                            observation=f"Error occurred: {str(e)}",
                            result="FAIL",
                        )
                    ],
                    explanation=f"Technical error prevented proper review: {str(e)}",
                ),
                headline_news_assessment=HeadlineNewsAssessment(
                    featured=False,
                    reasoning="Technical error prevented proper featured assessment",
                ),
            )

            # Try to save error review if we have news_article_id
            if article.news_article_id:
                try:
                    self.editorial_service.save_review(
                        article.news_article_id, error_review
                    )
                    print(
                        f"💾 Saved error review to database for news_article.id {article.news_article_id}"
                    )
                except Exception as save_error:
                    print(f"⚠️  Could not save error review to database: {save_error}")

            return error_review

    def run(self, state: AgentState) -> AgentState:
        """Run editor-in-chief review for single article in subgraph."""

        if not hasattr(state, "current_article") or not state.current_article:
            print("❌ Ei current_article -kenttää!")
            return state

        print(
            f"📰 ARVIOINTI: {getattr(state.current_article, 'enriched_title', 'Unknown')[:50]}..."
        )

        try:
            # TEE REVIEW
            review_result = self.review_article(state.current_article)
            print(f"📋 Arviointi valmis: {review_result.status}")

            # ASETA EDITORIAL DECISION
            if review_result.status == "OK":
                if review_result.interview_decision.interview_needed:
                    review_result.editorial_decision = "interview"
                    print(f"🎤 Päätös: HAASTATTELU tarvitaan")
                else:
                    review_result.editorial_decision = "publish"
                    print(f"✅ Päätös: JULKAISU")
            elif review_result.status == "ISSUES_FOUND":
                # Useimmat ongelmat voidaan korjata → revise
                review_result.editorial_decision = "revise"
                print(
                    f"🔧 Päätös: KORJAUS (löytyi {len(review_result.issues)} ongelmaa)"
                )
            else:  # RECONSIDERATION
                review_result.editorial_decision = "revise"
                print(f"🤔 Päätös: HARKINTA → KORJAUS")

            # TALLENNA TULOS
            state.review_result = review_result

            print(f"📋 Editorial decision: {review_result.editorial_decision}")

        except Exception as e:
            print(f"❌ Virhe arvioinnissa: {e}")

            # Luo error review - VAIN TÄSSÄ käytetään "reject"
            from schemas.editor_in_chief_schema import (
                ReviewedNewsItem,
                ReviewIssue,
                EditorialReasoning,
                HeadlineNewsAssessment,
                InterviewDecision,
                ReasoningStep,
            )

            error_review = ReviewedNewsItem(
                status="ISSUES_FOUND",
                editorial_decision="reject",  # VAIN virhetilanteessa reject
                issues=[
                    ReviewIssue(
                        type="Other",
                        location="Review Process",
                        description=f"Technical error: {str(e)}",
                        suggestion="Manual review required",
                    )
                ],
                editorial_reasoning=EditorialReasoning(
                    reviewer="EditorInChiefAgent",
                    initial_decision="REJECT",
                    checked_criteria=["Technical Review"],
                    failed_criteria=["Technical Review"],
                    reasoning_steps=[
                        ReasoningStep(
                            step_id=1,
                            action="Technical Review",
                            observation=f"Error: {str(e)}",
                            result="FAIL",
                        )
                    ],
                    explanation="Technical error during review",
                ),
                headline_news_assessment=HeadlineNewsAssessment(
                    featured=False, reasoning="Technical error prevented assessment"
                ),
                interview_decision=InterviewDecision(
                    interview_needed=False,
                    justification="Technical error prevented assessment",
                ),
            )
            state.review_result = error_review
            print(f"📋 Editorial decision: reject (technical error)")

        return state


# ======================================================================
# Standalone Test Runner with Database Integration
# ======================================================================
if __name__ == "__main__":
    from dotenv import load_dotenv
    from langchain.chat_models import init_chat_model
    from schemas.enriched_article import EnrichedArticle, ArticleReference, LocationTag
    import os

    print("--- Running EditorInChiefAgent with Database Integration ---")
    load_dotenv()

    # Get database connection
    db_dsn = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/newsdb")

    # Initialize the LLM
    try:
        llm = init_chat_model("gpt-4o-mini", model_provider="openai")
    except Exception as e:
        print(f"Error initializing LLM: {e}")
        print("Make sure you have OPENAI_API_KEY set in your .env file")
        print("Install required packages: pip install langchain langchain-openai")
        sys.exit(1)

    # Create test enriched article with news_article_id (simulating ArticleStorerAgent result)
    test_article = EnrichedArticle(
        article_id="test-article-1",
        canonical_news_id=123,
        news_article_id=1,  # Simulated database ID
        enriched_title="Testiuutinen: Suomen tekoälystategia etenee",
        enriched_content="""
# Suomen tekoälystategia etenee

Suomen hallitus on julkistanut uuden tekoälystrategian, joka tähtää maan aseman vahvistamiseen teknologiakentässä.

## Keskeiset tavoitteet

Strategian mukaan Suomi panostaa 100 miljoonaa euroa tekoälyn tutkimukseen ja kehitykseen seuraavan kolmen vuoden aikana.

"Tämä on tärkeä askel Suomen digitaalisen tulevaisuuden rakentamisessa", kommentoi teknologiaministeri.

## Vaikutukset

Uusi strategia vaikuttaa erityisesti:
- Yliopistojen tutkimustoimintaan
- Startup-yritysten tukijärjestelmiin
- Julkisen sektorin digitalisaatioon

Strategia otetaan käyttöön asteittain vuoden 2025 aikana.
        """,
        published_at="2024-01-15T10:00:00Z",
        source_domain="test.fi",
        keywords=["tekoäly", "strategia", "Suomi", "teknologia"],
        categories=["Teknologia", "Politiikka"],
        language="fi",
        sources=["https://example.com/source1", "https://example.com/source2"],
        references=[
            ArticleReference(
                title="Alkuperäinen uutinen", url="https://test.fi/original"
            ),
            ArticleReference(title="Lisätietoja", url="https://example.com/more"),
        ],
        locations=[
            LocationTag(
                continent="Europe", country="Finland", region="Uusimaa", city="Helsinki"
            ),
            LocationTag(continent="Europe", country="Finland", region=None, city=None),
        ],
        summary="Suomen hallitus julkisti uuden tekoälystrategian, joka sisältää 100 miljoonan euron panostuksen.",
        enrichment_status="success",
    )

    # Mock state
    class MockAgentState:
        def __init__(self):
            self.enriched_articles = [test_article]
            self.reviewed_articles = []

    # Test the agent with database
    try:
        editor_agent = EditorInChiefAgent(llm, db_dsn)
        result_state = editor_agent.run(MockAgentState())

        print(
            f"\n🎉 Testi valmis! Testattiin {len(result_state.reviewed_articles)} artikkelia."
        )
        print("💾 Arviot tallennettiin tietokantaan!")

    except Exception as e:
        print(f"\n❌ Virhe testissä: {e}")
        import traceback

        traceback.print_exc()
