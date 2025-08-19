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
import json

# Updated Interview Planning Prompt - POISTETTU priority-viittaukset
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
3. **Balance questions** that ensure multiple perspectives

## INTERVIEW PLAN:

Create a detailed interview plan (2-5 questions) that addresses the editorial feedback and strengthens the article's journalistic integrity.

Focus on:
- Questions that fill specific gaps identified in the editorial review
- Appropriate interview method for the situation
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
            # DO WE WANT EMAIL OR PHONE INTERVIEW !!!
            # IDEA IS, PHONE IF ITS URGENT THING!
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

            return state

        except Exception as e:
            print(f"❌ Error creating interview plan: {e}")
            import traceback

            traceback.print_exc()

            state.interview_plan = None
            print("⚠️ Failed to create interview plan")

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
            canonical_news_id=article.news_article_id,
            recipient=email_contact,
            subject=subject,
            questions=questions,
            background_context=interview_decision.interview_focus,
            target_expertise_areas=interview_decision.target_expertise_areas,
            interview_focus=interview_decision.interview_focus,
            formatted_email_body=formatted_email_body,
        )

        return InterviewPlan(
            canonical_news_id=article.news_article_id,
            article_id=article.news_article_id,
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
                questions_section += f"\n**{question.topic.title()}:**\n"
                current_topic = question.topic

            # Käytä position-numeroa
            questions_section += f"{question.position}. {question.question}\n"

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
        """Create phone-specific interview plan with JSON structure for Realtime API."""

        # Use the pre-selected contact
        phone_contact = selected_contact.get("phone") if selected_contact else None

        # Get article language
        article_language = getattr(article, "language", "fi")

        # Generate questions (2-5 questions) in article language using LLM
        questions = self._generate_questions_from_areas(
            interview_decision.target_expertise_areas[:3],
            interview_decision.interview_focus,
            article.enriched_title,
            language=article_language,
        )

        # Create JSON-structured phone script for Realtime API
        phone_script_json = self._create_phone_script_json(
            questions,
            article.enriched_title,
            article_language,
        )

        phone_plan = PhoneInterviewPlan(
            to_number=phone_contact,
            phone_script_json=phone_script_json,
        )

        print("AAAAAAAAAAAAAAAAAAAA")
        print(phone_contact)
        print(phone_script_json)
        print(article.canonical_news_id)
        print(article.news_article_id)

        interview_plan_for_phone = InterviewPlan(
            canonical_news_id=article.canonical_news_id,
            article_id=article.news_article_id,
            interview_method="phone",
            phone_plan=phone_plan,
            available_contacts=available_contacts,
        )

        print(interview_plan_for_phone)

        return interview_plan_for_phone

    def _create_phone_script_json(
        self,
        questions: List[InterviewQuestion],
        title: str,
        language: str = "fi",
    ) -> dict:
        """Create hybrid JSON-structured phone interview script for OpenAI Realtime API."""

        if language == "fi":
            description = (
                f"Olet suomenkielinen puhelinhaastattelija artikkeliin: {title}. "
                "Toimi ystävällisesti ja ammattimaisesti, esitä kysymykset yksi kerrallaan ja odota vastaus ennen seuraavaa."
            )
            structure = {
                "opening": "Hei! Olen Tampereen yliopiston tekoälyhaastattelija...",
                "permission": "Onko teillä hetki nopeaan haastatteluun?",
                "questions": [q.question for q in questions],
                "closing": "Kiitos haastattelusta ja hyvää päivänjatkoa!",
            }
            rules = [
                "Älä vastaa omiin kysymyksiisi.",
                "Puhu vain suomea koko haastattelun ajan.",
                "Kysy vain yksi kysymys kerrallaan.",
                "Jos vastaus on epäselvä, pyydä tarkennusta.",
                "Lopetuksen jälkeen pyydä sulkemaan puhelu",
            ]
            instructions = (
                f"Olet Tampereen yliopiston tekoäly, joka tekee puhelinhaastatteluja tutkimustarkoituksiin artikkeliin: {title}.\n"
                "Aloita tervehdyksellä ja kerro haastateltavalle, että kyseessä on tekoälyhaastattelu.\n"
                "Kysy lupa jatkaa, ja esitä sitten kysymykset yksi kerrallaan.\n"
                "Odota aina vastaus ennen seuraavaa kysymystä.\n"
                "Pysy suomen kielessä ja lopuksi kiitä haastattelusta."
            )
            voice = "nova"

        else:  # English
            description = (
                f"You are an English-speaking phone interviewer for the article: {title}. "
                "Be friendly and professional, ask questions one at a time and wait for answers before moving on."
            )
            structure = {
                "opening": "Hello! I'm calling from the newspaper. We're writing an article on this topic.",
                "permission": "Do you have a few minutes for a quick interview?",
                "questions": [q.question for q in questions],
                "closing": "Thank you for the interview and have a great day!",
            }
            rules = [
                "Do not answer your own questions.",
                "Speak only in English throughout the interview.",
                "Ask one question at a time.",
                "If the answer is unclear, ask for clarification.",
            ]
            instructions = (
                f"You are a professional journalist conducting a phone interview for the article: {title}.\n"
                "Start with a greeting and ask for permission, then ask the questions one by one.\n"
                "Always wait for the answer before moving on.\n"
                "Stay in English and end by thanking the interviewee."
            )
            voice = "alloy"

        config = {
            "role": "system",
            "content": {
                "description": description,
                "structure": structure,
                "rules": rules,
            },
            "instructions": instructions,
            "voice": voice,
            "temperature": 0.7,
            "language": language,
            "questions_data": [
                {"position": q.position, "topic": q.topic, "text": q.question}
                for q in questions
            ],
        }

        return config

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

        # Prepare the prompt for LLM - PÄIVITETTY ilman priority-viittauksia
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

## GUIDELINES:
- Create one question for each expertise area (max 3)
- Add one general/broader perspective question
- Questions should be specific to the expertise areas
- Use professional journalistic language
- Order questions logically (most important first)"""

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

            # Fallback to template-based questions - PÄIVITETTY ilman priority
            questions = []

            # Generate questions for each area (max 3 areas)
            for i, area in enumerate(expertise_areas[:3]):
                if language == "fi":
                    question_text = f"Mikä on näkemyksenne asiasta '{focus.lower()}' erityisesti {area.lower()}-näkökulmasta?"
                else:  # English
                    question_text = f"What is your perspective on '{focus.lower()}' specifically from a {area.lower()} viewpoint?"

                questions.append(
                    InterviewQuestion(
                        topic=area,
                        question=question_text,
                        position=i + 1,
                    )
                )

            # Add one general question if we have space (max 5 total)
            if len(questions) < 5:
                if language == "fi":
                    general_question = "Onko jotain tärkeää näkökulmaa, joka ei ole vielä tullut julkisuudessa esille?"
                else:
                    general_question = "Is there any important perspective that hasn't been covered in the public discussion yet?"

                questions.append(
                    InterviewQuestion(
                        topic="general",
                        question=general_question,
                        position=len(questions) + 1,
                    )
                )

            return questions


# TEST!
if __name__ == "__main__":
    import os
    import sys
    from langchain.chat_models import init_chat_model
    from schemas.agent_state import AgentState
    from dotenv import load_dotenv

    load_dotenv()  # Load environment variables from .env file

    print("🧪 TESTING InterviewPlanningAgent with sample data...")
    # RUN WITH THIS:
    # python -m agents.subtask_agents.interview_planning_agent

    interview_method = "phone"  # email # or phone

    print(f"📋 Interview method: {interview_method.upper()}")

    try:
        llm = init_chat_model("gpt-4o-mini", model_provider="openai")
        print("LLM initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize LLM: {e}")
        exit()

    db_dsn = os.getenv("DATABASE_URL")

    # Initialize agent
    agent = InterviewPlanningAgent(llm, db_dsn)

    # Create mock EnrichedArticle
    mock_article = EnrichedArticle(
        article_id="test-article-12345",
        canonical_news_id=66666,
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
        editorial_warning=None,
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
            print(
                f"   📝 Email ready: {len(plan.email_plan.formatted_email_body)} characters"
            )

            print(f"\n📝 EMAIL QUESTIONS:")
            for q in plan.email_plan.questions:
                print(f"   {q.position}. {q.question}")
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

            # Hae tiedot phone_script_json:sta
            script_json = plan.phone_plan.phone_script_json
            questions_data = script_json.get("questions_data", [])

            print(f"   🎙️ Language: {script_json.get('language', 'fi')}")
            print(f"   ❓ Questions: {len(questions_data)}")

            print(f"\n📝 PHONE QUESTIONS:")
            for q in questions_data:
                print(f"   {q['position']}. {q['text']}")
                print(f"      Topic: {q['topic']}")

            print(f"\n📜 FULL PHONE SCRIPT JSON:")
            print(json.dumps(script_json, ensure_ascii=False, indent=2))

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
