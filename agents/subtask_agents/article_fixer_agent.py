# File: agents/article_reviser_agent.py

from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle
from schemas.editor_in_chief_schema import ReviewedNewsItem
from services.news_article_service import NewsArticleService


REVISION_PROMPT = """
You are an experienced journalist who revises articles based on editor-in-chief feedback.

You have been given:
1. Original article
2. Issues and correction suggestions found by the editor-in-chief
3. Additional editorial context (interviews needed, reconsiderations, warnings)

Your task is to revise the article so that it passes the editor-in-chief review on the next round.

## ORIGINAL ARTICLE:

**Title:** {original_title}

**Content:**
{original_content}

## EDITOR-IN-CHIEF FEEDBACK:

**Status:** {review_status}

**Issues found:**
{issues_list}

**General feedback:**
{general_feedback}

**Additional editorial context:**
{review_context}

### REVISION STRATEGY:

1. **Analyze severity:** Prioritize CRITICAL issues first
2. **For serious accusations:** 
   - Add phrases like "according to [source]", "alleged by [group]"
   - Include responses from accused parties if available
   - Use conditional language: "if true", "allegations suggest"
3. **Balance perspective:** Add opposing viewpoints, expert opinions, official statements
4. **Verify claims:** Only keep verifiable facts with credible sources
5. **Preserve core story:** Keep the newsworthy elements while fixing issues
6. **Maintain format:** Use same markdown structure as original

### SPECIAL HANDLING:
- If interview requirements are specified, note what additional sources are needed
- If reconsideration shows fundamental flaws, consider major restructuring
- If editorial warnings exist, address sensitive topic handling carefully

## REVISED ARTICLE:

Produce a revised version that addresses all critical issues while maintaining journalistic integrity.

**Title:** [Revised title - more neutral if needed]

**Content:**
[Revised content in markdown format - with balanced perspective and proper attribution]

**Summary of revisions:**
- [List the main changes made, especially for critical issues]
- [Note any fundamental restructuring]
- [Indicate if additional sources/interviews are still needed]
"""


class ArticleReviserAgent(BaseAgent):
    """Agent that revises articles based on editor-in-chief feedback."""

    def __init__(self, llm, db_dsn: str):
        super().__init__(llm=llm, prompt=REVISION_PROMPT, name="ArticleReviserAgent")
        self.article_service = NewsArticleService(db_dsn=db_dsn)

    def _format_issues_list(self, issues) -> str:
        """Format issues list for the prompt."""
        if not issues:
            return "No specific issues found."

        formatted_issues = []
        for i, issue in enumerate(issues, 1):
            # Add severity indicator based on issue type
            severity = "CRITICAL" if issue.type in ["Legal", "Ethics"] else "MODERATE"

            formatted_issues.append(
                f"""
{i}. {severity} **{issue.type.upper()}** - {issue.location}
   Issue: {issue.description}
   Suggestion: {issue.suggestion}
"""
            )
        return "\n".join(formatted_issues)

    def _format_review_context(self, review) -> str:
        """Format additional review context like reconsideration and interview needs."""
        context_parts = []

        # Add interview decision if needed
        if (
            hasattr(review, "interview_decision")
            and review.interview_decision.interview_needed
        ):
            interview = review.interview_decision
            context_parts.append(
                f"""
**INTERVIEW REQUIREMENTS:**
- Method: {interview.interview_method or 'Not specified'}
- Target expertise: {', '.join(interview.target_expertise_areas) if interview.target_expertise_areas else 'Not specified'}
- Focus: {interview.interview_focus or 'Not specified'}
- Justification: {interview.justification}
"""
            )

        # Add reconsideration details if present
        if hasattr(review, "reconsideration") and review.reconsideration:
            recon = review.reconsideration
            context_parts.append(
                f"""
**RECONSIDERATION ANALYSIS:**
- Final decision: {recon.final_decision}
- Critical issues: {', '.join(recon.failed_criteria)}
- Editor's final assessment: {recon.explanation}
"""
            )

        # Add editorial warning if present
        if hasattr(review, "editorial_warning") and review.editorial_warning:
            warning = review.editorial_warning
            context_parts.append(
                f"""
**EDITORIAL WARNING ISSUED:**
- Category: {warning.category}
- Details: {warning.details}
- Sensitive topics: {', '.join(warning.topics) if warning.topics else 'None specified'}
"""
            )

        return (
            "\n".join(context_parts)
            if context_parts
            else "No additional editorial context."
        )

    def _extract_corrected_content(self, llm_response: str) -> tuple[str, str]:
        """Extract title and content from LLM response."""
        lines = llm_response.strip().split("\n")

        title = ""
        content_lines = []
        in_content = False

        for line in lines:
            # Look for title
            if line.startswith("**Title:**"):
                title = line.replace("**Title:**", "").strip()
            # Look for content start
            elif line.startswith("**Content:**"):
                in_content = True
                continue
            # Stop at summary
            elif line.startswith("**Summary of revisions:**"):
                break
            # Collect content lines
            elif in_content:
                content_lines.append(line)

        content = "\n".join(content_lines).strip()

        # Fallback if extraction fails
        if not title or not content:
            print(
                "⚠️ Failed to extract title/content properly, using original structure"
            )
            # Try simpler extraction
            if "**Title:**" in llm_response:
                parts = llm_response.split("**Title:**", 1)[1]
                if "**Content:**" in parts:
                    title_part, content_part = parts.split("**Content:**", 1)
                    title = title_part.strip()
                    if "**Summary of revisions:**" in content_part:
                        content = content_part.split("**Summary of revisions:**")[
                            0
                        ].strip()
                    else:
                        content = content_part.strip()

        return title, content

    def run(self, state: AgentState) -> AgentState:
        """Revise the current article based on editor feedback."""

        if not hasattr(state, "current_article") or not state.current_article:
            print("❌ ArticleReviserAgent: No current_article to revise!")
            return state

        if not hasattr(state, "review_result") or not state.review_result:
            print("❌ ArticleReviserAgent: No review_result found!")
            return state

        article: EnrichedArticle = state.current_article
        review = state.review_result

        print(
            f"🔧 Revising article: {getattr(article, 'enriched_title', 'Unknown')[:50]}..."
        )
        print(f"📋 Found {len(review.issues)} issues to fix")
        print("TÄÄ ON SE MIKÄ KIINNOSTAA!!!!!")
        print(review)

        try:
            # Format the issues for the prompt
            issues_list = self._format_issues_list(review.issues)

            # Get general feedback from reasoning
            general_feedback = getattr(
                review.editorial_reasoning, "explanation", "See detailed issues above."
            )

            # Format additional review context (interviews, reconsideration, warnings)
            review_context = self._format_review_context(review)

            # Prepare prompt
            prompt_content = self.prompt.format(
                original_title=getattr(article, "enriched_title", ""),
                original_content=getattr(article, "enriched_content", ""),
                review_status=review.status,
                issues_list=issues_list,
                general_feedback=general_feedback,
                review_context=review_context,
            )

            # Get revision from LLM
            print("🤖 Generating revised version...")
            llm_response = self.llm.invoke(prompt_content).content

            # Extract revised title and content
            corrected_title, corrected_content = self._extract_corrected_content(
                llm_response
            )

            if not corrected_title or not corrected_content:
                print("❌ Failed to extract revised content from LLM response")
                print("📝 LLM Response preview:", llm_response[:200] + "...")
                return state

            # Update the article with revised content
            article.enriched_title = corrected_title
            article.enriched_content = corrected_content

            # Update correction tracking fields
            article.required_corrections = True
            article.revision_count += 1

            print(f"✅ Article revised successfully!")
            print(f"📝 New title: {corrected_title[:50]}...")
            print(article.enriched_content)

            # Update in database if article has been stored
            if article.news_article_id:

                success = self.article_service.update_enriched_article(article)
                if success:
                    print(
                        f"✅ Updated article in database (ID: {article.news_article_id})"
                    )
                else:
                    print(f"⚠️ Failed to update article in database")
            else:
                print("⚠️ Article not yet in database, skipping DB update")

                # Show excerpt of changes
                if len(corrected_content) > 100:
                    print(f"📋 Content preview: {corrected_content[:100]}...")

        except Exception as e:
            print(f"❌ Error during revision: {e}")
            import traceback

            traceback.print_exc()

        return state


# Test runner
if __name__ == "__main__":
    from dotenv import load_dotenv
    from langchain.chat_models import init_chat_model
    from schemas.enriched_article import EnrichedArticle
    from schemas.editor_in_chief_schema import (
        ReviewedNewsItem,
        ReviewIssue,
        EditorialReasoning,
        HeadlineNewsAssessment,
        InterviewDecision,
    )

    load_dotenv()

    # Initialize LLM
    llm = init_chat_model("gpt-4o-mini", model_provider="openai")

    # Mock article with issues
    test_article = EnrichedArticle(
        article_id="test-revision",
        canonical_news_id=1,
        news_article_id=1,
        enriched_title="Kiistanalainen päätös hallituksessa",
        enriched_content="""
# Hallitus tekee kiistanalaisen päätöksen

Hallitus päätti tänään nostaa veroja merkittävästi. Päätös on saanut laajaa kritiikkiä.

Pääministeri ei kommentoinut asiaa.
        """,
        published_at="2025-01-15T10:00:00Z",
        source_domain="test.fi",
        keywords=["hallitus", "verot"],
        categories=["Politiikka"],
        language="fi",
        sources=["https://example.com"],
        references=[],
        locations=[],
        summary="Hallitus nostaa veroja",
        enrichment_status="success",
    )

    # Mock review with issues
    test_review = ReviewedNewsItem(
        status="ISSUES_FOUND",
        editorial_decision="revise",
        issues=[
            ReviewIssue(
                type="Accuracy",
                location="Otsikko",
                description="Sana 'kiistanalainen' on liian subjektiivinen uutisessa",
                suggestion="Käytä neutraalimpaa kieltä",
            ),
            ReviewIssue(
                type="Style",
                location="Sisältö",
                description="Artikkeli on liian lyhyt ja epätarkka",
                suggestion="Lisää kontekstia ja yksityiskohtia päätöksestä",
            ),
        ],
        editorial_reasoning=EditorialReasoning(
            reviewer="TestEditor",
            initial_decision="REJECT",
            checked_criteria=["Accuracy", "Style"],
            failed_criteria=["Accuracy", "Style"],
            reasoning_steps=[],
            explanation="Artikkeli kaipaa neutraalimpaa kieltä ja lisää sisältöä",
        ),
        headline_news_assessment=HeadlineNewsAssessment(
            featured=False, reasoning="Ei sovellu etusivulle nykyisessä muodossa"
        ),
        interview_decision=InterviewDecision(
            interview_needed=False, justification="Ei tarvita haastatteluja"
        ),
    )

    # Mock state
    class MockState:
        def __init__(self):
            self.current_article = test_article
            self.review_result = test_review

    # Test the agent
    try:
        agent = ArticleReviserAgent(llm)
        result = agent.run(MockState())

        print("\n" + "=" * 50)
        print("KORJATTU ARTIKKELI:")
        print("=" * 50)
        print(f"Otsikko: {result.current_article.enriched_title}")
        print(f"Sisältö:\n{result.current_article.enriched_content}")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
