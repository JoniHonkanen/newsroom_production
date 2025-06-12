from base_agent import BaseAgent
from schemas.agent_state import AgentState
from typing import List

from schemas.news_draft import NewsDraftPlan
from services.rrs_utils import extract_article_text, render_article_as_markdown


class PlanningAgent(BaseAgent):
    def run(self, state: AgentState) -> AgentState:
        drafts: List[NewsDraftPlan] = []
        structured_llm = self.llm.with_structured_output(NewsDraftPlan)

        for item in state.articles:
            link = item["link"]
            # Hae ja käsittele artikkelin teksti
            full_text, published_str = extract_article_text(link)
            full_text_markdown = render_article_as_markdown(full_text)

            planning_prompt = self.prompt.format(
                article_text=full_text_markdown,
                published_date=published_str or "Unknown",
            )

            plan: NewsDraftPlan = structured_llm.invoke(planning_prompt)
            plan.markdown = full_text_markdown
            plan.url = link
            drafts.append(plan)

        state.plan = drafts
        return state
