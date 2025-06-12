from dotenv import load_dotenv
from agents.feed_reader_agent import FeedReaderAgent
from schemas.feed_categories import NewsFeedConfig
from schemas.agent_state import AgentState
from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model
import yaml
import time

from schemas.news_draft import NewsDraftPlan

# Lataa ympäristömuuttujat (esim. API-avaimet)
load_dotenv()

llm = init_chat_model("gpt-4o-mini", model_provider="openai")

NEWS_PLANNING_PROMPT = "Plan article: {article_text} / {published_date}"

# Lue feedien tiedot YAML-tiedostosta
with open("newsfeeds.yaml") as f:
    config = yaml.safe_load(f)
feeds = [NewsFeedConfig(**feed) for feed in config["feeds"]]

if __name__ == "__main__":
    # Alusta agentti käyttäen konfiguraatiotiedostosta luettuja url:eja
    feed_reader = FeedReaderAgent(feed_urls=[f.url for f in feeds], max_news=5)
    
    # Rakenna agenttigraafi
    graph_builder = StateGraph(AgentState)
    graph_builder.add_node("feed_reader", feed_reader.run)
    graph_builder.add_edge(START, "feed_reader")
    graph_builder.add_edge("feed_reader", END)
    graph = graph_builder.compile()

    # Suorita graafi silmukassa (looppi minuutin välein)
    while True:
        state = AgentState()
        result = graph.invoke(state)
        #if hasattr(result, "articles"):
        #    print(f"Haettiin {len(result.articles)} uutista.")
        time.sleep(60)
