from agents.base_agent import BaseAgent
from schemas.agent_state import AgentState
from schemas.enriched_article import EnrichedArticle
from schemas.editor_in_chief_schema import InterviewDecision
from schemas.parsed_article import NewsContact
from schemas.interview_schema import (
    InterviewPlan,
    InterviewQuestion,
    EmailInterviewPlan,
    PhoneInterviewPlan,
)
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

# Updated Interview Planning Prompt
INTERVIEW_PLANNING_PROMPT = """
You are an experienced journalist responsible for planning interviews to strengthen articles.

You have been given:
1. An article that needs additional perspectives
2. Editorial feedback about what kind of interviews are needed
3. Selected contact for the interview

Your task is to create a comprehensive interview plan that will address the editorial concerns and strengthen the article's journalistic balance.

## ARTICLE TO STRENGTHEN:

**Title:** {article_title}

**Content:**
{article_content}

## EDITORIAL REQUIREMENTS:

**Interview Method:** {interview_method}
**Target Expertise Areas:** {target_expertise}
**Interview Focus:** {interview_focus}
**Justification:** {justification}

## SELECTED CONTACT:

{selected_contact}

## PLANNING GUIDELINES:

### METHOD SELECTION:
- **Phone**: For urgent news, emotional topics, or complex explanations
- **Email**: For expert opinions, fact-checking, or when detailed responses needed

### QUESTION STRATEGY:
1. **Open-ended questions** that encourage detailed responses
2. **Specific questions** that address editorial concerns
3. **Follow-up potential** questions that can lead to deeper insights
4. **Balance questions** that ensure multiple perspectives

### EXPERTISE PRIORITIZATION:
- **High priority**: Critical gaps in current article
- **Medium priority**: Additional context and perspective
- **Low priority**: Nice-to-have background information

## INTERVIEW PLAN:

Create a detailed interview plan (2-5 questions) that addresses the editorial feedback and strengthens the article's journalistic integrity.

Focus on:
- Questions that fill specific gaps identified in the editorial review
- Appropriate interview method for the situation
- Clear priority levels for different questions
- Utilize available contacts when appropriate
"""


class InterviewPlanningAgent(BaseAgent):
    """Agent that creates detailed interview plans for articles requiring additional sources."""

    def __init__(self, llm, db_dsn: str):
        super().__init__(
            llm=llm, prompt=INTERVIEW_PLANNING_PROMPT, name="InterviewPlanningAgent"
        )
        self.db_dsn = db_dsn
        self.question_llm = llm

    def run(self, state: AgentState) -> AgentState:
        """Creates interview plan based on editorial feedback."""
        print("📞 INTERVIEW PLANNING AGENT: Creating interview plan...")

        if not hasattr(state, "current_article") or not state.current_article:
            print(
                "❌ InterviewPlanningAgent: No current_article to plan interviews for!"
            )
            return state

        article: EnrichedArticle = state.current_article
        if not isinstance(article, EnrichedArticle):
            print(
                f"❌ InterviewPlanningAgent: Expected EnrichedArticle, got {type(article)}"
            )
            return state

        if not hasattr(state, "review_result") or not state.review_result:
            print(
                "❌ InterviewPlanningAgent: No review_result with interview decision!"
            )
            return state

        interview_decision = state.review_result.interview_decision
        if not interview_decision or not interview_decision.interview_needed:
            print(
                "❌ InterviewPlanningAgent: No interview needed according to editorial decision!"
            )
            return state

        print(f"📰 Planning interviews for: {article.enriched_title[:50]}...")
        print(f"🎯 Method: {interview_decision.interview_method}")
        print(f"🔍 Focus: {interview_decision.interview_focus}")
        print(
            f"👥 Target areas: {', '.join(interview_decision.target_expertise_areas)}"
        )

        # Get available contacts and select the best one early
        available_contacts = getattr(article, "contacts", []) or []
        print(f"📋 Available contacts: {len(available_contacts)}")

        # Select contact based on interview method
        if interview_decision.interview_method == "email":
            selected_contact = self._select_and_format_email_contact(available_contacts)
        else:
            selected_contact = self._select_and_format_phone_contact(available_contacts)

        print(
            f"👤 Selected contact: {selected_contact['name'] if selected_contact else 'None'}"
        )

        try:
            # Create method-specific interview plan
            if interview_decision.interview_method == "email":
                interview_plan = self._create_email_plan(
                    article, interview_decision, available_contacts, selected_contact
                )
            else:  # phone
                interview_plan = self._create_phone_plan(
                    article, interview_decision, available_contacts, selected_contact
                )

            # Add to state
            state.interview_plan = interview_plan

            print("✅ Interview plan created successfully!")
            print(f"   📅 Method: {interview_plan.interview_method}")

            if interview_plan.email_plan:
                print(f"   📧 Email to: {interview_plan.email_plan.recipient}")
                print(f"   ❓ Questions: {len(interview_plan.email_plan.questions)}")
                print(
                    f"   📝 Email ready: {len(interview_plan.email_plan.formatted_email_body)} characters"
                )
            elif interview_plan.phone_plan:
                print(f"   📞 Phone to: {interview_plan.phone_plan.to_number}")
                print(f"   ❓ Questions: {len(interview_plan.phone_plan.questions)}")

            print("TÄÄ!!!!!:")
            print(interview_plan)
            return state

        except Exception as e:
            print(f"❌ Error creating interview plan: {e}")
            import traceback

            traceback.print_exc()

            state.interview_plan = None
            print("⚠️ Created fallback interview plan")

            return state

    def _create_email_plan(
        self,
        article: EnrichedArticle,
        interview_decision: InterviewDecision,
        available_contacts: List[NewsContact],
        selected_contact: dict,
    ) -> InterviewPlan:
        """Create email-specific interview plan with formatted email body."""

        # Use the pre-selected contact
        email_contact = selected_contact.get("email") if selected_contact else None
        if not email_contact:
            email_contact = "ei-sahkopostia@example.com"

        # Get article language
        article_language = getattr(article, "language", "fi")

        # Generate questions (2-5 questions) in article language using LLM
        questions = self._generate_questions_from_areas(
            interview_decision.target_expertise_areas[:3],
            interview_decision.interview_focus,
            article.enriched_title,
            language=article_language,
        )

        # Create subject in article language
        if article_language == "fi":
            subject = f"Kysymyksiä artikkelista: {article.enriched_title[:50]}..."
        else:
            subject = f"Questions about article: {article.enriched_title[:50]}..."

        # Format complete email body
        formatted_email_body = self._format_email_body(
            article, interview_decision, questions, article_language
        )

        email_plan = EmailInterviewPlan(
            canonical_news_id=article.news_article_id or 0,
            recipient=email_contact,
            subject=subject,
            questions=questions,
            background_context=interview_decision.interview_focus,
            target_expertise_areas=interview_decision.target_expertise_areas,
            interview_focus=interview_decision.interview_focus,
            deadline_priority=self._determine_priority(
                interview_decision.justification
            ),
            formatted_email_body=formatted_email_body,  # NEW: Complete formatted email
        )

        return InterviewPlan(
            canonical_news_id=article.news_article_id or 0,
            article_id=article.news_article_id or 0,
            interview_method="email",
            email_plan=email_plan,
            available_contacts=available_contacts,
        )

    def _format_email_body(
        self,
        article: EnrichedArticle,
        interview_decision: InterviewDecision,
        questions: List[InterviewQuestion],
        language: str = "fi",
    ) -> str:
        """Format complete email body with intro, questions, outro, and signature."""

        # Intro/greeting
        if language == "fi":
            intro = f"""Hei,

Teen journalistista juttua aiheesta "{article.enriched_title}". {interview_decision.interview_focus}

Haluaisin kysyä muutaman tarkentavan kysymyksen aiheeseen liittyen:"""
        else:
            intro = f"""Hello,

I am working on a journalistic article about "{article.enriched_title}". {interview_decision.interview_focus}

I would like to ask a few clarifying questions related to this topic:"""

        # Format questions by topic
        questions_section = "\n"
        current_topic = None

        for question in questions:
            if question.topic != current_topic:
                if language == "fi":
                    questions_section += f"\n**{question.topic.title()}:**\n"
                else:
                    questions_section += f"\n**{question.topic.title()}:**\n"
                current_topic = question.topic

            questions_section += f"- {question.question}\n"

        # Outro
        if language == "fi":
            outro = """
Kiitos ajastanne! Vastaukset käsitellään osana tekoälyavusteista tutkimusta, jossa tekoäly toimii journalistina.
https://www.tuni.fi/fi/tutkimus/tekoalyn-johtama-uutistoimitus"""
        else:
            outro = """
Thank you for your time! The responses will be processed as part of AI-assisted research where AI acts as a journalist.
https://www.tuni.fi/fi/tutkimus/tekoalyn-johtama-uutistoimitus"""

        # Signature
        if language == "fi":
            signature = """
Ystävällisin terveisin,

Teppo Tekoälyjournalisti
– tutkimushanke Tampereen yliopisto"""
        else:
            signature = """
Best regards,

Teppo AI Journalist
– research project, University of Tampere"""

        # Combine all parts
        email_body = intro + questions_section + outro + signature

        return email_body

    def _create_phone_plan(
        self,
        article: EnrichedArticle,
        interview_decision: InterviewDecision,
        available_contacts: List[NewsContact],
        selected_contact: dict,
    ) -> InterviewPlan:
        """Create phone-specific interview plan."""

        # Use the pre-selected contact
        phone_contact = selected_contact.get("phone") if selected_contact else None
        if not phone_contact:
            phone_contact = "+358000000000"

        # Get article language
        article_language = getattr(article, "language", "fi")

        # Generate questions (2-5 questions) in article language using LLM
        questions = self._generate_questions_from_areas(
            interview_decision.target_expertise_areas[:3],
            interview_decision.interview_focus,
            article.enriched_title,
            language=article_language,
        )

        # Create phone script with WAIT instructions in article language
        phone_script = self._create_phone_script(
            questions,
            article.enriched_title,
            interview_decision.interview_focus,
            article_language,
        )

        # Background context in article language
        if article_language == "fi":
            context_prefix = "Puhelinhaastattelu aiheesta:"
        else:
            context_prefix = "Phone interview about:"

        phone_plan = PhoneInterviewPlan(
            canonical_news_id=article.news_article_id or 0,
            to_number=phone_contact,
            prompt=phone_script,
            questions=questions,
            language=article_language,
            background_context=f"{context_prefix} {article.enriched_title}. {interview_decision.interview_focus}",
            target_expertise_areas=interview_decision.target_expertise_areas,
            interview_focus=interview_decision.interview_focus,
            deadline_priority=self._determine_priority(
                interview_decision.justification
            ),
        )

        return InterviewPlan(
            canonical_news_id=article.news_article_id or 0,
            article_id=article.news_article_id or 0,
            interview_method="phone",
            phone_plan=phone_plan,
            available_contacts=available_contacts,
        )

    def _select_and_format_email_contact(self, contacts: List[NewsContact]) -> dict:
        """Select best email contact and format for LLM prompt."""
        selected = None

        # First, try to find primary contact with email
        for contact in contacts:
            if contact.email and contact.is_primary_contact:
                selected = contact
                break

        # Fallback to first available email
        if not selected:
            for contact in contacts:
                if contact.email:
                    selected = contact
                    break

        if selected:
            return {
                "name": selected.name,
                "title": selected.title,
                "organization": selected.organization,
                "email": selected.email,
                "contact_type": selected.contact_type,
                "context": selected.extraction_context,
            }
        return None

    def _select_and_format_phone_contact(self, contacts: List[NewsContact]) -> dict:
        """Select best phone contact and format for LLM prompt."""
        selected = None

        # First, try to find primary contact with phone
        for contact in contacts:
            if contact.phone and contact.is_primary_contact:
                selected = contact
                break

        # Fallback to first available phone
        if not selected:
            for contact in contacts:
                if contact.phone:
                    selected = contact
                    break

        if selected:
            return {
                "name": selected.name,
                "title": selected.title,
                "organization": selected.organization,
                "phone": selected.phone,
                "contact_type": selected.contact_type,
                "context": selected.extraction_context,
            }
        return None

    def _create_phone_script(
        self,
        questions: List[InterviewQuestion],
        title: str,
        focus: str,
        language: str = "fi",
    ) -> str:
        """Create phone interview script with WAIT instructions."""

        if language == "fi":
            script = f"""
PHONE INTERVIEW SCRIPT (Finnish):

1. OPENING:
"Hei! Soitan [Lehden nimi] -lehdestä. Kirjoitamme artikkelia aiheesta '{title[:30]}...'"
→ WAIT_FOR_ACKNOWLEDGMENT

2. PERMISSION REQUEST:
"Onko teillä hetki aikaa {len(questions)} kysymykseen? Kestää noin {len(questions) * 3} minuuttia."
→ WAIT_FOR_CONSENT

3. QUESTIONS (one at a time):
"""
        else:  # English
            script = f"""
PHONE INTERVIEW SCRIPT (English):

1. OPENING:
"Hello! I'm calling from [News outlet]. We're writing an article about '{title[:30]}...'"
→ WAIT_FOR_ACKNOWLEDGMENT

2. PERMISSION REQUEST:
"Do you have a moment for {len(questions)} questions? It will take about {len(questions) * 3} minutes."
→ WAIT_FOR_CONSENT

3. QUESTIONS (one at a time):
"""

        for i, q in enumerate(questions, 1):
            script += f"""
{i}. [{q.priority.upper()}] {q.question}
→ WAIT_FOR_COMPLETE_ANSWER
"""
            if q.follow_up_potential:
                script += "→ ASK_FOLLOW_UP_IF_NEEDED\n"

        if language == "fi":
            script += """
4. CLOSING:
"Kiitos haastattelusta! Lähetän artikkelin tarkistettavaksi ennen julkaisua."

REMEMBER: Always wait for the person to finish speaking before asking the next question!
"""
        else:
            script += """
4. CLOSING:
"Thank you for the interview! I'll send the article for review before publication."

REMEMBER: Always wait for the person to finish speaking before asking the next question!
"""
        return script

    def _determine_priority(
        self, justification: str
    ) -> Literal["urgent", "normal", "flexible"]:
        """Determine interview priority from justification."""
        if any(
            word in justification.lower()
            for word in ["urgent", "kiireellinen", "immediately"]
        ):
            return "urgent"
        elif any(
            word in justification.lower()
            for word in ["flexible", "joustava", "when possible"]
        ):
            return "flexible"
        return "normal"

    def _generate_questions_from_areas(
        self, expertise_areas: List[str], focus: str, title: str, language: str = "fi"
    ) -> List[InterviewQuestion]:
        """Generate 2-5 interview questions based on expertise areas and focus using LLM."""

        # Determine language name for prompt
        language_name = "Finnish" if language == "fi" else "English"

        # Create Pydantic model for structured output
        class InterviewQuestionsResponse(BaseModel):
            """Response model for generated interview questions"""

            questions: List[InterviewQuestion] = Field(
                description="List of 2-5 interview questions", min_items=2, max_items=5
            )

        # Prepare the prompt for LLM
        prompt = f"""You are an experienced journalist creating interview questions for an article.

## CONTEXT:
**Article Title:** {title}
**Interview Focus:** {focus}
**Target Expertise Areas:** {', '.join(expertise_areas)}
**Language:** {language_name}

## TASK:
Generate {min(len(expertise_areas) + 1, 5)} interview questions that:
1. Are in {language_name} language
2. Focus on the specified expertise areas
3. Are open-ended and encourage detailed responses
4. Address the interview focus
5. Have clear priority levels (first 2 questions should be high priority)
6. Include follow-up potential

## GUIDELINES:
- Create one question for each expertise area (max 3)
- Add one general/broader perspective question
- Questions should be specific to the expertise areas
- Use professional journalistic language
- Ensure questions encourage substantive responses"""

        try:
            # Use structured output with Pydantic model
            structured_llm = self.question_llm.with_structured_output(
                InterviewQuestionsResponse
            )
            response = structured_llm.invoke(prompt)

            # Extract questions and ensure they have correct positions
            questions = response.questions
            for i, question in enumerate(questions):
                question.position = i + 1

            # Ensure we have at least 2 questions
            if len(questions) < 2:
                raise ValueError("Not enough questions generated")

            return questions[:5]  # Return max 5 questions

        except Exception as e:
            print(f"⚠️ Error generating questions with LLM: {e}")
            print("   Falling back to template-based questions...")

            # Fallback to template-based questions
            questions = []

            # Generate questions for each area (max 3 areas)
            for i, area in enumerate(expertise_areas[:3]):
                if language == "fi":
                    question_text = f"Mikä on näkemyksenne asiasta '{focus.lower()}' erityisesti {area.lower()}-näkökulmasta?"
                    general_question = "Onko jotain tärkeää näkökulmaa, joka ei ole vielä tullut julkisuudessa esille?"
                else:  # English
                    question_text = f"What is your perspective on '{focus.lower()}' specifically from a {area.lower()} viewpoint?"
                    general_question = "Is there any important perspective that hasn't been covered in the public discussion yet?"

                questions.append(
                    InterviewQuestion(
                        topic=area,
                        question=question_text,
                        position=i + 1,
                        priority="high" if i < 2 else "medium",
                        follow_up_potential=True,
                    )
                )

            # Add one general question if we have space (max 5 total)
            if len(questions) < 5:
                questions.append(
                    InterviewQuestion(
                        topic="general",
                        question=general_question,
                        position=len(questions) + 1,
                        priority="medium",
                        follow_up_potential=True,
                    )
                )

            return questions


# TEST!
if __name__ == "__main__":
    import os
    import sys
    from langchain.chat_models import init_chat_model
    from schemas.agent_state import AgentState

    print("🧪 TESTING InterviewPlanningAgent with sample data...")
    # RUN WITH THIS:
    # python -m agents.subtask_agents.interview_planning_agent

    # Check if we should use real LLM or mock
    use_mock_llm = False
    interview_method = "phone"  # email # or phone

    print(f"📋 Interview method: {interview_method.upper()}")

    if use_mock_llm:
        print("🤖 Using MOCK LLM for testing (no API calls)")
        # Create a mock LLM that returns predefined questions
        from unittest.mock import MagicMock

        class MockLLMResponse:
            def __init__(self):
                self.questions = [
                    InterviewQuestion(
                        topic="energy markets",
                        question="Miten arvioitte Kiinan teknologian vaikutuksia Suomen energiamarkkinoihin?",
                        position=1,
                        priority="high",
                        follow_up_potential=True,
                    ),
                    InterviewQuestion(
                        topic="cybersecurity",
                        question="Millaisia kyberturvallisuusriskejä näette kiinalaisissa akkujärjestelmissä?",
                        position=2,
                        priority="high",
                        follow_up_potential=True,
                    ),
                    InterviewQuestion(
                        topic="consumer rights",
                        question="Miten kuluttajien oikeudet turvataan näissä hankkeissa?",
                        position=3,
                        priority="medium",
                        follow_up_potential=True,
                    ),
                ]

        mock_llm = MagicMock()
        mock_structured_llm = MagicMock()
        mock_structured_llm.invoke.return_value = MockLLMResponse()
        mock_llm.with_structured_output.return_value = mock_structured_llm
        llm = mock_llm
    else:
        print("🤖 Using REAL LLM (requires API key)")
        # Initialize real LLM
        llm = init_chat_model("gpt-4o-mini", model_provider="openai")

    db_dsn = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/newsdb")

    # Initialize agent
    agent = InterviewPlanningAgent(llm, db_dsn)

    # Create mock EnrichedArticle
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
        sources=["https://example.com/source1", "https://example.com/source2"],
        summary="Kauppakeskus hankki kiinalaisia akkuja, herättää turvallisuuskysymyksiä",
        contacts=[
            NewsContact(
                name="Pekka Rinne",
                title="Johtaja",
                organization="Kauppakeskus testi",
                email="pekka.rinne@testi.fi",
                phone="+358123456789",
                contact_type="source",
                extraction_context="Mentioned as shopping center manager",
                is_primary_contact=True,
            ),
            NewsContact(
                name="Mikko Kuivaniemi",
                title="Päällikkö",
                organization="Testi_kompania Oy",
                email="mikko.kuivaniemi@testi.fi",
                contact_type="expert",
                extraction_context="Quoted about grid balancing projects",
                is_primary_contact=False,
            ),
        ],
    )

    # Create mock InterviewDecision with selected method
    mock_interview_decision = InterviewDecision(
        interview_needed=True,
        interview_method=interview_method,  # Use selected method
        target_expertise_areas=["energy markets", "cybersecurity", "consumer rights"],
        interview_focus="Investigation of security implications of Chinese technology in critical infrastructure",
        justification="Article lacks balanced perspective on security risks and regulatory oversight of foreign technology in energy infrastructure",
        article_type_influence=f"Given the {'urgency and need for immediate response' if interview_method == 'phone' else 'technical complexity and security concerns'}, {interview_method} interviews {'allow for real-time clarification and emotional nuance' if interview_method == 'phone' else 'allow for detailed expert responses and fact-checking'}",
    )

    # Create mock ReviewedNewsItem
    from schemas.editor_in_chief_schema import (
        ReviewedNewsItem,
        EditorialReasoning,
        ReasoningStep,
        HeadlineNewsAssessment,
    )

    mock_review_result = ReviewedNewsItem(
        status="OK",
        issues=[],
        approval_comment="Article requires additional expert perspectives before publication",
        editorial_reasoning=EditorialReasoning(
            reviewer="editor-in-chief",
            initial_decision="ACCEPT",
            checked_criteria=["Balance", "Security", "Public Interest", "Accuracy"],
            failed_criteria=[],
            reasoning_steps=[
                ReasoningStep(
                    step_id=1,
                    action="Assess need for additional perspectives",
                    observation="Article needs expert views on security implications",
                    result="INFO",
                )
            ],
            explanation="Article accepted but requires expert interviews for balanced coverage",
        ),
        headline_news_assessment=HeadlineNewsAssessment(
            featured=True,
            reasoning="Important infrastructure security topic with broad public interest",
        ),
        interview_decision=mock_interview_decision,
        editorial_decision="interview",
    )

    # Create mock state
    mock_state = AgentState()
    mock_state.current_article = mock_article
    mock_state.review_result = mock_review_result

    print("\n📋 TEST INPUT:")
    print(f"   Article: {mock_article.enriched_title}")
    print(f"   Language: {mock_article.language}")
    print(f"   Method: {mock_interview_decision.interview_method}")
    print(
        f"   Target areas: {', '.join(mock_interview_decision.target_expertise_areas)}"
    )
    print(f"   Available contacts: {len(mock_article.contacts)}")

    print("\n🤖 RUNNING AGENT...")

    # Run the agent
    result_state = agent.run(mock_state)

    print("\n📊 TEST RESULTS:")
    if hasattr(result_state, "interview_plan") and result_state.interview_plan:
        plan = result_state.interview_plan
        print(f"   ✅ Interview plan created successfully!")
        print(f"   📅 Method: {plan.interview_method}")

        if plan.email_plan:
            print(f"   📧 Email to: {plan.email_plan.recipient}")
            print(f"   📝 Subject: {plan.email_plan.subject}")
            print(f"   ❓ Questions: {len(plan.email_plan.questions)}")
            print(f"   🚨 Priority: {plan.email_plan.deadline_priority}")
            print(
                f"   📝 Email ready: {len(plan.email_plan.formatted_email_body)} characters"
            )

            print(f"\n📝 EMAIL QUESTIONS:")
            for i, q in enumerate(plan.email_plan.questions, 1):
                print(f"   {i}. [{q.priority.upper()}] {q.question}")
                print(f"      Topic: {q.topic}")

            print(f"\n📧 COMPLETE EMAIL PREVIEW:")
            print("=" * 60)
            print(f"To: {plan.email_plan.recipient}")
            print(f"Subject: {plan.email_plan.subject}")
            print("-" * 60)
            print(plan.email_plan.formatted_email_body)
            print("=" * 60)

        elif plan.phone_plan:
            print(f"   📞 Phone to: {plan.phone_plan.to_number}")
            print(f"   🎙️ Language: {plan.phone_plan.language}")
            print(f"   ❓ Questions: {len(plan.phone_plan.questions)}")
            print(f"   🚨 Priority: {plan.phone_plan.deadline_priority}")

            print(f"\n📝 PHONE QUESTIONS:")
            for i, q in enumerate(plan.phone_plan.questions, 1):
                print(f"   {i}. [{q.priority.upper()}] {q.question}")
                print(f"      Topic: {q.topic}")

            print(f"\n📞 PHONE SCRIPT PREVIEW:")
            script_lines = plan.phone_plan.prompt.split("\n")[:10]
            for line in script_lines:
                if line.strip():
                    print(f"   {line}")
            print("   ...")

        print(f"\n👥 AVAILABLE CONTACTS:")
        for i, contact in enumerate(plan.available_contacts, 1):
            print(f"   {i}. {contact.name} ({contact.title}) - {contact.contact_type}")
            if contact.email:
                print(f"      📧 Email: {contact.email}")
            if contact.phone:
                print(f"      📞 Phone: {contact.phone}")
    else:
        print("   ❌ No interview plan created!")

    print("\n🎯 Test completed - InterviewPlanningAgent ready for production use!")
