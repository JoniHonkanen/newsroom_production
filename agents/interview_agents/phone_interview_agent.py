import os
import requests
import logging
from typing import Optional, Any
import psycopg
from schemas.agent_state import AgentState
from schemas.interview_schema import InterviewPlan, PhoneInterviewPlan
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# PHONE CALLING NEED TO BE DONE VIA SERVER,
# THATS WHY WE USE OUR OWN PHONE SERVER URL
# AFTER PHONE CALL IS DONE, WE STORE THE INTERVIEW TO DB
# AND THEN WE WILL ENRICH THE ARTICLE ONCE AGAIN
#TODO:: THIS STILL NEED TO BE TESTED AND DONE... NOT USED SERVER FOR INTEGRATION YET
class PhoneInterviewExecutionAgent:
    """Agent that executes phone interviews via Twilio/OpenAI integration."""

    def __init__(self, db_dsn: str):
        self.db_dsn = db_dsn
        self.phone_server_url = os.getenv("PHONE_SERVER_URL")

    def run(self, state: AgentState) -> AgentState:
        """Main execution method for phone interviews."""
        try:
            plan: InterviewPlan = state.interview_plan
            phone_plan: PhoneInterviewPlan = plan.phone_plan

            # Initiate the call with all interview data
            success, call_sid, message = self._trigger_phone_call(phone_plan)

            if success:
                try:
                    # Store phone interview to database
                    phone_db_id = self._store_phone_interview_to_db(
                        phone_plan, call_sid
                    )
                    logger.info(
                        f"✅ Phone interview stored to database with ID: {phone_db_id}"
                    )
                except Exception as e:
                    logger.error(f"Failed to store phone interview to database: {e}")

            return state

        except Exception as e:
            logger.error(f"Unexpected error in PhoneInterviewExecutionAgent: {e}")
            return state

    def _trigger_phone_call(
        self, phone_plan: PhoneInterviewPlan
    ) -> tuple[bool, Optional[str], str]:
        """Trigger the phone call with all interview data via single API call."""
        try:
            # Send everything in one request
            payload = {
                "phone_number": phone_plan.to_number,
                "system_prompt": phone_plan.prompt,
                "language": phone_plan.language,
                "interview_context": phone_plan.background_context,
            }

            response = requests.post(
                f"{self.phone_server_url}/start-interview", json=payload, timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                call_sid = data.get("call_sid", "unknown")
                logger.info(
                    f"✅ Phone interview initiated successfully, SID: {call_sid}"
                )
                return True, call_sid, "Phone interview initiated successfully"
            else:
                error_msg = f"Phone server returned status {response.status_code}"
                logger.error(error_msg)
                return False, None, error_msg

        except requests.RequestException as e:
            error_msg = f"Failed to connect to phone server: {e}"
            logger.error(error_msg)
            return False, None, error_msg

    def _store_phone_interview_to_db(
        self, phone_plan: PhoneInterviewPlan, call_sid: str
    ) -> int:
        """Store the phone interview to database."""
        try:
            with psycopg.connect(self.db_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO phone_interview
                        (canonical_news_id, interview_decision_id, to_number, from_number, 
                         prompt, status, language, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        RETURNING id
                        """,
                        (
                            phone_plan.canonical_news_id,
                            getattr(phone_plan, "interview_decision_id", None),
                            phone_plan.to_number,
                            phone_plan.from_number,
                            phone_plan.prompt,
                            "initiated",
                            phone_plan.language,
                        ),
                    )
                    phone_id = cur.fetchone()[0]

                    cur.execute(
                        """
                        INSERT INTO phone_interview_attempt 
                        (phone_interview_id, started_at, status)
                        VALUES (%s, NOW(), %s)
                        """,
                        (phone_id, f"twilio_sid:{call_sid}"),
                    )

                    conn.commit()
                    logger.info(f"Stored phone interview with ID {phone_id}")
                    return phone_id

        except psycopg.Error as e:
            logger.error(f"Database error storing phone interview: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error storing phone interview to database: {e}")
            raise


if __name__ == "__main__":
    from schemas.interview_schema import InterviewPlan, InterviewQuestion
    from schemas.parsed_article import NewsContact

    #TODO:: DO TESTS!

    questions = [
        InterviewQuestion(
            topic="energiamarkkinat",
            question="Miten Kiinalaisen teknologian käyttö sähköakkuhankkeissa voi vaikuttaa kilpailutilanteeseen energiamarkkinoilla?",
            position=1,
            priority="high",
            follow_up_potential=True,
        ),
        InterviewQuestion(
            topic="kyberturvallisuus",
            question="Mitä kyberturvallisuuden haasteita näet kiinalaisissa akkujärjestelmissä?",
            position=2,
            priority="high",
            follow_up_potential=True,
        ),
    ]

    phone_plan = PhoneInterviewPlan(
        canonical_news_id=12345,
        interview_decision_id=None,
        to_number=os.getenv("TEST_PHONE_NUMBER", "+358123456789"),
        from_number=None,
        prompt="""PHONE INTERVIEW SCRIPT (Finnish):

1. OPENING:
"Hei! Soitan lehdestä. Kirjoitamme artikkelia sähköakkuhankkeesta."
→ WAIT_FOR_ACKNOWLEDGMENT

2. PERMISSION REQUEST:
"Onko teillä hetki aikaa 2 kysymykseen? Kestää noin 6 minuuttia."
→ WAIT_FOR_CONSENT

3. QUESTIONS:
1. [HIGH] Miten Kiinalaisen teknologian käyttö sähköakkuhankkeissa voi vaikuttaa kilpailutilanteeseen energiamarkkinoilla?
→ WAIT_FOR_COMPLETE_ANSWER

2. [HIGH] Mitä kyberturvallisuuden haasteita näet kiinalaisissa akkujärjestelmissä?
→ WAIT_FOR_COMPLETE_ANSWER

4. CLOSING:
"Kiitos haastattelusta!"

REMEMBER: Always wait for complete answers before proceeding!""",
        language="fi",
        questions=questions,
        background_context="Puhelinhaastattelu sähköakkuhankkeesta",
        target_expertise_areas=["energy markets", "cybersecurity"],
        interview_focus="Security implications investigation",
        deadline_priority="normal",
    )

    interview_plan = InterviewPlan(
        canonical_news_id=12345,
        article_id=12345,
        interview_method="phone",
        email_plan=None,
        phone_plan=phone_plan,
        available_contacts=[],
    )

    # Test the agent
    db_dsn = os.getenv("DATABASE_URL")
    state = type("State", (), {"interview_plan": interview_plan})()

    agent = PhoneInterviewExecutionAgent(db_dsn=db_dsn)
    print("🧪 Testing PhoneInterviewExecutionAgent...")
    print(f"📞 Calling: {phone_plan.to_number}")
    print(f"🎙️ Language: {phone_plan.language}")
    print(f"❓ Questions: {len(phone_plan.questions)}")

    result_state = agent.run(state)

    print(f"\n✅ Results:")
    print(f"  Call initiated: {getattr(result_state, 'phone_call_initiated', None)}")
    print(f"  Call SID: {getattr(result_state, 'phone_call_sid', None)}")
    print(f"  Database ID: {getattr(result_state, 'phone_db_id', None)}")
    if hasattr(result_state, "error_message") and result_state.error_message:
        print(f"  ❌ Error: {result_state.error_message}")
    else:
        print("  🎉 No errors detected!")
