# File: main.py
from dotenv import load_dotenv
from agents.article_content_extractor_agent import ArticleContentExtractorAgent
from agents.editor_in_chief_agent import EditorInChiefAgent
from agents.feed_reader_agent import FeedReaderAgent
from agents.news_planner_agent import NewsPlannerAgent
from agents.news_storer_agent import NewsStorerAgent
from agents.web_search_agent import WebSearchAgent
from agents.article_generator_agent import ArticleGeneratorAgent
from agents.article_storer_agent import ArticleStorerAgent
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
    """Check if the state contains articles to process."""
    articles = state.articles  # Käytä suoraan, ei getattr
    if articles:
        return "continue"  # Yleinen "jatka" arvo
    return "end"


if __name__ == "__main__":
    # All agents are initialized here
    # This agent reads new news articles from RSS feeds and extracts their content

    # 1. Agent (feed_reader) -> GET RSS feed, check if RSS have changed since last check
    # 2. Agent (article_extractor) -> Extract content from articles
    # 2.1 Determine if article is news or press release
    # 2.2 Update AgentState with updated "CanonicalArticle" articles
    # 3. Agent (NEWS_STORER) -> Store articles to database
    # 3.1 Deduplicate articles using hash and embedding
    # 3.2 Over rides existings articles if semantically similar article is older than a time threshold
    # 3.3 If no new articles, go to END
    # 4. Agent (NEWS_PLANNER) -> Plan articles using LLM
    # 4.1 Stores the plans in AgentState.plan, match id to original article "article_id"
    # 5. Agent (WEB_SEARCH) -> Search web for more information about the articles
    # 5.1 Stores original id and related search results in AgentState.article_search_map
    # 6. Agent (ARTICLE_GENERATOR) -> Generate articles using LLM using original article content and web search results
    # 7. Agent (ARTICLE_STORER) -> Store generated articles to database... next if need to be validated by editor in chief
    # 8. Agent (EDITOR IN CHIEF) -> Validate articles, if ok, set article status to "published" and generate embeddings for the article
    # 8.1 ALso choose if interviews are needed, if so, create a new plan for the interview
    # 8.2 If article is not ok, set status to "rejected" and generate a reconsideration plan
    # 8.3 If article is ok, set status to "published" and generate embeddings for the article

    feed_reader = FeedReaderAgent(feed_urls=[f.url for f in feeds], max_news=1)
    article_extractor = ArticleContentExtractorAgent()
    news_storer = NewsStorerAgent(db_dsn=db_dsn)
    news_planner = NewsPlannerAgent(
        llm=llm,
    )
    web_search = WebSearchAgent(max_results_per_query=1)
    article_generator = ArticleGeneratorAgent(llm=llm)
    article_storer = ArticleStorerAgent(db_dsn=db_dsn)
    editor_in_chief = EditorInChiefAgent(llm=llm, db_dsn=db_dsn)

    # Build the state graph for the agents
    graph_builder = StateGraph(AgentState)
    # NODES
    graph_builder.add_node("feed_reader", feed_reader.run)
    graph_builder.add_node("content_extractor", article_extractor.run)
    graph_builder.add_node("news_storer", news_storer.run)
    graph_builder.add_node("news_planner", news_planner.run)
    graph_builder.add_node("web_search", web_search.run)
    graph_builder.add_node("article_generator", article_generator.run)
    graph_builder.add_node("article_storer", article_storer.run)
    graph_builder.add_node("editor_in_chief", editor_in_chief.run)

    # EDGES
    graph_builder.add_edge(START, "feed_reader")
    # if no articles, go to END
    graph_builder.add_conditional_edges(
        source="feed_reader",
        path=has_articles,
        path_map={"continue": "content_extractor", "end": END},
    )
    graph_builder.add_edge("content_extractor", "news_storer")
    # OBS! If there is many same hash articles or embeddings, we (no new articles) go to END
    graph_builder.add_conditional_edges(
        source="news_storer",
        path=has_articles,
        path_map={"continue": "news_planner", "end": END},
    )
    graph_builder.add_edge("news_planner", "web_search")
    graph_builder.add_edge("web_search", "article_generator")
    graph_builder.add_edge("article_generator", "article_storer")
    graph_builder.add_edge("article_storer", "editor_in_chief")
    graph_builder.add_edge("editor_in_chief", END)
    graph = graph_builder.compile()

    # Run the agent graph in a loop to continuously fetch and process news articles
    while True:
        state = AgentState()
        result = graph.invoke(state)
        print("Graph done!")
        time.sleep(60)
