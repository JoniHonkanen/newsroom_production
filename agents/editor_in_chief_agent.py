# File: agents/editor_in_chief_agent.py

import sys
import os

# Add the project root to the Python path FIRST
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

# Now import the modules
from schemas.editor_in_chief_schema import (
    EditorialReasoning,
    ReasoningStep,
    ReviewIssue,
    ReviewedNewsItem,
)
from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle


EDITOR_IN_CHIEF_PROMPT = """
{persona}

Your task is to review the news article and verify that it complies with:
- Finnish journalistic law (Freedom of Expression Act, Criminal Code)
- JSN's Journalistin ohjeet (ethical code)
- Our editorial and stylistic standards

As Editor-in-Chief, your responsibility includes not only identifying issues but also exercising editorial judgment. Do not reject an article unless it contains substantial legal, factual, or ethical violations. Minor or technical issues should lead to correction suggestions, not rejection.

You must explain your reasoning clearly and explicitly. Each decision, observation, and conclusion must be logged step-by-step, with justification. This includes both the initial decision and any reconsideration. Do not omit or summarize critical steps. The rationale must be transparent, traceable, and match the final editorial outcome.

Proceed step by step through the following five categories. For each step:
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

### Step 6: Final Checklist Review
Go through the following items and confirm if each one is satisfied. If any are not, explain why and how it can be fixed.
- [ ] All key facts are verified (minor unsourced details may be flagged but not block publication)  
- [ ] Legally compliant (no defamation, hate speech, or clear violations)  
- [ ] No major ethical violations  
- [ ] Balanced and fair representation of relevant perspectives  
- [ ] Correction policy present or not critical for this article type  
- [ ] Tone is professional and neutral

### Important: Justify All Reasoning Transparently
You must log all observations and decisions. For each step, explain what was checked, what was found, and how it contributed to the final decision. Your final explanation must clearly show why the article was accepted or rejected. This review will be recorded for auditing purposes.

**Remember:** Not all controversy is avoidable or undesirable. Responsible journalism may challenge readers. Do not suppress legitimate reporting simply because it may offend or provoke—only reject content that clearly breaches law, ethics, or accuracy.

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
"""

EDITOR_PERSONA = """
You are the Editor-in-Chief of a Finnish digital news platform. You have 15 years of experience in journalism, including 8 years as a senior editor at major Finnish newspapers. You are well-versed in:

- Finnish media law (Freedom of Expression Act, Criminal Code)
- JSN's ethical guidelines (Journalistin ohjeet)
- Modern digital journalism standards
- Editorial responsibility and accountability

Your editorial philosophy emphasizes:
- Accuracy and verification above speed
- Balanced reporting that serves the public interest
- Ethical treatment of all individuals and groups
- Legal compliance without sacrificing journalistic integrity
- Clear, accessible writing that respects readers' intelligence

You make decisions based on professional judgment, not personal opinion. You understand that journalism sometimes requires publishing uncomfortable truths, but you never compromise on accuracy, fairness, or legal compliance.
"""


class EditorInChiefAgent(BaseAgent):
    """An agent that reviews enriched articles for legal, ethical, and editorial compliance."""

    def __init__(self, llm):
        super().__init__(llm=llm, prompt=None, name="EditorInChiefAgent")
        self.structured_llm = self.llm.with_structured_output(ReviewedNewsItem)

    def _format_article_for_review(self, article: EnrichedArticle) -> str:
        """Format an enriched article for editorial review."""
        return f"""
        # {article.enriched_title}
        
        {article.enriched_content}
        
        ---
        **Summary:** {article.summary}
        **Keywords:** {', '.join(article.keywords)}
        **Categories:** {', '.join(article.categories)}
        **Sources:** {len(article.sources)} sources referenced
        """

    def review_article(self, article: EnrichedArticle) -> ReviewedNewsItem:
        """Review a single enriched article."""
        print(f"🔍 Reviewing: {article.enriched_title[:60]}...")

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

            print(f"\n{'='*80}")
            print(f"📋 PÄÄTOIMITAJAN ARVIOINTI")
            print(f"{'='*80}")
            print(f"📰 Artikkeli: {article.enriched_title}")
            print(f"⚖️  Lopputulos: {review_result.status}")

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
            return ReviewedNewsItem(
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
            )

    def run(self, state: AgentState) -> AgentState:
        """Run the editor-in-chief review process on all enriched articles."""
        print("📰 PÄÄTOIMITAJA ALOITTAA ARVIOINNIN...\n")

        enriched_articles = state.enriched_articles or []

        if not enriched_articles:
            print("❌ Ei artikkeleita arvioitavaksi.")
            return state

        print(f"📊 Arvioidaan {len(enriched_articles)} artikkelia...\n")

        reviewed_articles = []

        for article in enriched_articles:
            try:
                review_result = self.review_article(article)
                reviewed_articles.append({"article": article, "review": review_result})

            except Exception as e:
                print(f"❌ Virhe artikkelin {article.article_id} arvioinnissa: {e}")
                # Add article with error review
                error_review = ReviewedNewsItem(
                    status="ISSUES_FOUND",
                    issues=[
                        ReviewIssue(
                            type="Other",
                            location="Review Process",
                            description=f"Review process failed: {str(e)}",
                            suggestion="Manual review required",
                        )
                    ],
                    editorial_reasoning=EditorialReasoning(
                        reviewer="EditorInChiefAgent",
                        initial_decision="REJECT",
                        checked_criteria=["Review Process"],
                        failed_criteria=["Review Process"],
                        reasoning_steps=[],
                        explanation=f"Review process failed due to technical error: {str(e)}",
                    ),
                )
                reviewed_articles.append({"article": article, "review": error_review})

        # Store results in state
        state.reviewed_articles = reviewed_articles

        # Print summary
        ok_count = sum(1 for item in reviewed_articles if item["review"].status == "OK")
        issues_count = sum(
            1 for item in reviewed_articles if item["review"].status == "ISSUES_FOUND"
        )
        reconsideration_count = sum(
            1
            for item in reviewed_articles
            if item["review"].status == "RECONSIDERATION"
        )

        print(f"\n{'='*80}")
        print(f"📊 PÄÄTOIMITAJAN LOPPUYHTEENVETO")
        print(f"{'='*80}")
        print(f"✅ Hyväksytty: {ok_count}")
        print(f"⚠️  Ongelmia löytyi: {issues_count}")
        print(f"🤔 Vaatii harkintaa: {reconsideration_count}")
        print(f"📈 Yhteensä arvioitu: {len(reviewed_articles)}")

        return state


# ======================================================================
# Standalone Test Runner
# ======================================================================
if __name__ == "__main__":
    from dotenv import load_dotenv
    from langchain.chat_models import init_chat_model
    from schemas.enriched_article import EnrichedArticle, ArticleReference, LocationTag

    print("--- Running EditorInChiefAgent in isolation for testing ---")
    load_dotenv()

    # Initialize the LLM
    try:
        llm = init_chat_model("gpt-4o-mini", model_provider="openai")
    except Exception as e:
        print(f"Error initializing LLM: {e}")
        print("Make sure you have OPENAI_API_KEY set in your .env file")
        print("Install required packages: pip install langchain langchain-openai")
        sys.exit(1)

    # Create test enriched article with proper Pydantic models
    test_article = EnrichedArticle(
        article_id="test-article-1",
        canonical_news_id=123,
        enriched_title="Testiuutinen: Suomen tekoälystategia etenee",
        enriched_content="""
# Suomen tekoälystategia etenee

Suomen hallitus on julkistanut uuden tekoälystrateg ian, joka tähtää maan aseman vahvistamiseen teknologiakentässä.

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

    # Test the agent
    try:
        editor_agent = EditorInChiefAgent(llm)
        result_state = editor_agent.run(MockAgentState())

        print(
            f"\n🎉 Testi valmis! Testattiin {len(result_state.reviewed_articles)} artikkelia."
        )

    except Exception as e:
        print(f"\n❌ Virhe testissä: {e}")
        import traceback

        traceback.print_exc()
