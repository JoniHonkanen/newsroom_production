from dotenv import load_dotenv
from agents.feed_reader_agent import FeedReaderAgent
from schemas.feed_categories import NewsFeedConfig
from schemas.agent_state import AgentState
from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model
import yaml

from schemas.news_draft import NewsDraftPlan


load_dotenv()  # Lataa esim. OPENAI_API_KEY

llm = init_chat_model("gpt-4o-mini", model_provider="openai")

NEWS_PLANNING_PROMPT = "Plan article: {article_text} / {published_date}"

with open("newsfeeds.yaml") as f:
    config = yaml.safe_load(f)
feeds = [NewsFeedConfig(**feed) for feed in config["feeds"]]

if __name__ == "__main__":
    # 1. Alusta agentit
    feed_url = feeds[0].url
    feed_reader = FeedReaderAgent(feed_url=feed_url, max_news=5)
    # planning_agent = PlanningAgent(
    #     llm=llm, prompt=NEWS_PLANNING_PROMPT, structured_output_model=NewsDraftPlan
    # )

    # 2. Rakenna StateGraph
    graph_builder = StateGraph(AgentState)
    graph_builder.add_node("feed_reader", feed_reader.run)
    # graph_builder.add_node("planner", planning_agent.run)
    graph_builder.add_edge(START, "feed_reader")
    graph_builder.add_edge("feed_reader", END)
    #graph_builder.add_edge("planner", END)
    graph = graph_builder.compile()

    # 3. Suorita pipeline
    state = AgentState()
    result = graph.invoke(state)
    print("Pipeline completed. Result state:", result)