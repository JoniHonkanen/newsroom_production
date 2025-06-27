from dotenv import load_dotenv
from agents.article_content_extractor_agent import ArticleContentExtractorAgent
from agents.feed_reader_agent import FeedReaderAgent
from agents.news_planner_agent import NewsPlannerAgent
from agents.news_storer_agent import NewsStorerAgent
from schemas.feed_schema import NewsFeedConfig
from schemas.agent_state import AgentState
from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model
import yaml
import time
import os

# Load environment variables from .env file
load_dotenv()
# This is what we use to connect to the PostgreSQL database
# During test phase, we use docker-compose to set up the database
db_dsn = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
print("DSN:", db_dsn)

llm = init_chat_model("gpt-4o-mini", model_provider="openai")

NEWS_PLANNING_PROMPT = "Plan article: {article_text} / {published_date}"

# read rss feeds from config file
with open("newsfeeds.yaml") as f:
    config = yaml.safe_load(f)
feeds = [NewsFeedConfig(**feed) for feed in config["feeds"]]


def has_articles(state):
    """Check if the state contains articles to process.
    If the articles list is not empty, return 'content_extractor' to continue processing.
    Otherwise, return END to terminate the graph.
    """
    articles = getattr(state, "articles", [])
    if articles:  # Jos lista ei ole tyhjä
        return "content_extractor"
    return "end"


if __name__ == "__main__":
    # All agents are initialized here
    # This agent reads new news articles from RSS feeds and extracts their content
    feed_reader = FeedReaderAgent(feed_urls=[f.url for f in feeds], max_news=2)
    article_extractor = ArticleContentExtractorAgent()
    news_storer = NewsStorerAgent(db_dsn=db_dsn)
    news_planner = NewsPlannerAgent(
        llm=llm,
    )

    # Build the state graph for the agents
    graph_builder = StateGraph(AgentState)
    # NODES
    graph_builder.add_node("feed_reader", feed_reader.run)
    graph_builder.add_node("content_extractor", article_extractor.run)
    graph_builder.add_node("news_storer", news_storer.run)
    graph_builder.add_node("news_planner", news_planner.run)

    # EDGES
    graph_builder.add_edge(START, "feed_reader")
    # if no articles, go to END
    graph_builder.add_conditional_edges(
        source="feed_reader",
        path=has_articles,
        path_map={"content_extractor": "content_extractor", "end": END},
    )
    graph_builder.add_edge("content_extractor", "news_storer")
    graph_builder.add_edge("news_storer", "news_planner")
    graph_builder.add_edge("news_planner", END)
    graph = graph_builder.compile()

    # Run the agent graph in a loop to continuously fetch and process news articles
    while True:
        state = AgentState()
        result = graph.invoke(state)
        print("Graph done!")
        time.sleep(60)
