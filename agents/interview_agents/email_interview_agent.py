import os
import smtplib
import uuid
from email.message import EmailMessage
from typing import Optional, Tuple
import psycopg  # type: ignore
from schemas.interview_schema import InterviewPlan, EmailInterviewPlan


class EmailInterviewExecutionAgent:
    """Agent that sends interview questions by email and stores them in the database."""

    def __init__(self, db_dsn: str):
        self.db_dsn = db_dsn

    def run(self, state):
        plan: InterviewPlan = state.interview_plan
        email_plan: EmailInterviewPlan = plan.email_plan
        if not email_plan:
            print("❌ No email interview plan found!")
            return state

        plain_text, html_body = self.build_email_body(email_plan)
        to = email_plan.recipient
        subject = email_plan.subject

        success, message, msg_id = self.send_email(
            to=to,
            subject=subject,
            plain_text=plain_text,
            html_body=html_body,
        )
        print(success, message, msg_id)

        if success:
            self.store_email_to_db(email_plan, msg_id)
            print("✅ Email and questions stored to database.")

        state.email_sent = success
        state.email_message_id = msg_id
        return state

    @staticmethod
    def generate_message_id(domain: Optional[str] = None) -> str:
        if domain is None:
            email_addr = os.getenv("EMAIL_ADDRESS_GMAIL", "example@example.com")
            domain = email_addr.split("@")[-1]
        unique_id = uuid.uuid4()
        return f"<{unique_id}@{domain}>"

    @staticmethod
    def build_email_body(email_plan: EmailInterviewPlan) -> Tuple[str, str]:
        lines = [email_plan.background_context, ""]
        for q in email_plan.questions:
            lines.append(f"- {q.question}")
        lines.append("")
        lines.append("Ystävällisin terveisin,\nTekoälyjournalisti\nTampereen yliopisto")
        plain_text = "\n".join(lines)

        html_lines = [
            "<html><body>",
            f"<p>{email_plan.background_context}</p>",
            "<ol>",
        ]
        for q in email_plan.questions:
            html_lines.append(f"<li>{q.question}</li>")
        html_lines.append("</ol>")
        html_lines.append(
            "<p>Ystävällisin terveisin,<br>Tekoälyjournalisti<br>Tampereen yliopisto</p>"
        )
        html_lines.append("</body></html>")
        html_text = "\n".join(html_lines)
        return plain_text, html_text

    def send_email(
        self, to: str, subject: str, plain_text: str, html_body: str
    ) -> Tuple[bool, str, str]:
        email_host = os.environ["EMAIL_HOST_GMAIL"]
        email_port = int(os.environ["EMAIL_PORT"])
        email_address_sender = os.environ["EMAIL_ADDRESS_GMAIL"]
        email_password = os.environ["EMAIL_PASSWORD_GMAIL"]

        print(f"Yritetään lähettää sähköposti osoitteeseen: {to}")
        print(f"Aihe: {subject}")
        print(f"Plain text:\n{plain_text}")
        print(f"HTML body:\n{html_body}")

        msg = EmailMessage()
        msg["From"] = email_address_sender
        msg["To"] = to
        msg["Subject"] = subject
        msg_id = self.generate_message_id()
        msg["Message-ID"] = msg_id
        msg.set_content(plain_text)
        msg.add_alternative(html_body, subtype="html")

        try:
            with smtplib.SMTP(email_host, email_port) as smtp:
                smtp.starttls()
                smtp.login(email_address_sender, email_password)
                smtp.send_message(msg)
                print("Sähköposti lähetetty onnistuneesti.")
            return True, f"Email sent to {to}", msg_id
        except Exception as e:
            print(f"Sähköpostin lähetys epäonnistui: {e}")
            return False, f"Failed to send email: {e}", "None"

    def store_email_to_db(self, email_plan: EmailInterviewPlan, msg_id: str):
        with psycopg.connect(self.db_dsn) as conn:
            with conn.cursor() as cur:
                # Insert into email_interview
                cur.execute(
                    """
                    INSERT INTO email_interview
                    (canonical_news_id, interview_decision_id, message_id, recipient, subject, status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        email_plan.canonical_news_id,
                        getattr(email_plan, "interview_decision_id", None),
                        msg_id,
                        email_plan.recipient,
                        email_plan.subject,
                        "sent",
                    ),
                )
                email_id = cur.fetchone()[0]
                # Insert questions
                for i, q in enumerate(email_plan.questions, 1):
                    cur.execute(
                        """
                        INSERT INTO email_questions (email_id, topic, question, position)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (email_id, q.topic, q.question, i),
                    )
                conn.commit()
        return email_id


# TESTING!!!
# python -m agents.interview_agents.email_interview_agent
if __name__ == "__main__":
    import os
    from schemas.interview_schema import (
        InterviewPlan,
        EmailInterviewPlan,
        InterviewQuestion,
    )
    from agents.interview_agents.email_interview_agent import (
        EmailInterviewExecutionAgent,
    )

    # Käytä ympäristömuuttujaa tai kovakoodattua DSN:ää testissä
    db_dsn = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/newsdb")

    # Luo testikysymykset
    questions = [
        InterviewQuestion(
            topic="Testaus",
            question="Miksi sähköpostiagentin testaus on tärkeää?",
            position=1,
            priority="high",
            follow_up_potential=False,
        ),
        InterviewQuestion(
            topic="Käyttö",
            question="Miten agenttia käytetään newsroom-tuotannossa?",
            position=2,
            priority="medium",
            follow_up_potential=True,
        ),
    ]

    # Luo EmailInterviewPlan
    email_plan = EmailInterviewPlan(
        canonical_news_id=9999,
        interview_decision_id=123,
        recipient="YOUR EMAIL ADDRESS",
        subject="Testisähköposti newsroom-agentilta",
        background_context="Hei,\n\nTämä on testisähköposti newsroomin EmailInterviewExecutionAgentilta.",
        questions=questions,
        deadline_priority="normal",
        target_expertise_areas=["Testaus", "Käyttö"],
        interview_focus="Testataan sähköpostiagentin toimintaa.",
    )

    # Luo InterviewPlan, jossa vain email_plan täytetty
    interview_plan = InterviewPlan(
        interview_method="email",
        email_plan=email_plan,
        phone_plan=None,
        available_contacts=[],
        deadline_priority="normal",
        canonical_news_id=9999,
        article_id=123,
    )

    # Luo mock state-olio
    class MockState:
        pass

    state = MockState()
    state.interview_plan = interview_plan

    # Aja agentti
    agent = EmailInterviewExecutionAgent(db_dsn=db_dsn)
    print("🧪 Lähetetään testisähköposti agentilla...")

    result_state = agent.run(state)
    print("Lähetys onnistui:", getattr(result_state, "email_sent", None))
    print("Message-ID:", getattr(result_state, "email_message_id", None))
