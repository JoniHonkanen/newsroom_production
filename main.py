# File: main.py
from dotenv import load_dotenv
from agents.article_content_extractor_agent import ArticleContentExtractorAgent
from agents.editor_in_chief_agent import EditorInChiefAgent
from agents.feed_reader_agent import FeedReaderAgent
from agents.news_planner_agent import NewsPlannerAgent
from agents.news_storer_agent import NewsStorerAgent
from agents.subtask_agents.publisher_agent import ArticlePublisherAgent
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


# IF THERE IS STILL AFTER WORKS AFTER EDITORIAL BATCH (need to re check the articles etc...)
# TODO::: WE might need to change this at some point!
def has_pending_work(state: AgentState):
    """Check if there are interviews to conduct or revisions to make."""
    pending_interviews = getattr(state, "pending_interviews", [])
    pending_revisions = getattr(state, "pending_revisions", [])

    if pending_interviews or pending_revisions:
        return "handle_follow_ups"
    return "end"


# EEditor in Chief decision -> "publish", "interview", "revise", "reject"
def get_editorial_decision(state: AgentState):
    """Route based on editor-in-chief review result."""
    if hasattr(state, "review_result") and state.review_result:
        return state.review_result.editorial_decision
    return "reject"


def create_editorial_subgraph():
    """Create subgraph for individual article editorial decisions."""
    subgraph = StateGraph(AgentState)

    # Initialize agents using existing ones
    editor_in_chief = EditorInChiefAgent(llm=llm, db_dsn=db_dsn)
    news_planner = NewsPlannerAgent(llm=llm)  # For interview/revision planning
    article_publisher = ArticlePublisherAgent(db_dsn=db_dsn)  # For publishing

    # Add nodes
    subgraph.add_node("editor_in_chief", editor_in_chief.run)
    subgraph.add_node("interview_planning", news_planner.run)
    subgraph.add_node("revision_planning", news_planner.run)
    subgraph.add_node("publish_article", article_publisher.run)

    # Start with editor-in-chief decision
    subgraph.add_edge(START, "editor_in_chief")

    # Conditional edges based on editorial decision
    # DO WE NEED TO PUBLISH, INTERVIEW, REVISE OR REJECT?
    subgraph.add_conditional_edges(
        source="editor_in_chief",
        path=get_editorial_decision,
        path_map={
            "publish": "publish_article",
            "interview": "interview_planning",
            "revise": "revision_planning",
            "reject": END,
        },
    )

    # All paths lead to END
    subgraph.add_edge("publish_article", END)
    subgraph.add_edge("interview_planning", END)
    subgraph.add_edge("revision_planning", END)

    # AFTER THIS WE RETURN TO THE MAIN GRAPH
    # AND FROM THERE WE CHECK IF THERE ARE ANY PENDING INTERVIEWS OR REVISIONS...

    return subgraph.compile()


# We can use this function to process a batch of articles through editorial review
def process_editorial_batch(state: AgentState):
    """Process all enriched articles through editorial review using subgraph."""
    if not hasattr(state, "enriched_articles") or not state.enriched_articles:
        print("No enriched articles to review")
        return state

    published_articles = []
    pending_interviews = []
    pending_revisions = []
    rejected_articles = []

    editorial_subgraph = create_editorial_subgraph()

    print(f"Editorial review for {len(state.enriched_articles)} articles...")

    for i, article in enumerate(state.enriched_articles):
        try:
            print(
                f"Reviewing article {i+1}/{len(state.enriched_articles)}: {getattr(article, 'enriched_title', 'Untitled')[:50]}..."
            )

            # Create state for single article review
            article_state = AgentState(current_article=article)

            # Process through editorial subgraph
            editorial_subgraph.invoke(article_state)

            # KORJATTU: Lue päätös suoraan article_state:sta (jossa review_result on)
            if hasattr(article_state, "review_result") and article_state.review_result:
                decision = article_state.review_result.editorial_decision
                print(f"🔍 Editorial decision: {decision}")

                if decision == "publish":
                    published_articles.append(article)
                    print(
                        f"✅ Article published: {getattr(article, 'enriched_title', 'Unknown')[:30]}..."
                    )
                elif decision == "interview":
                    pending_interviews.append(article)
                    print(
                        f"🎤 Article needs interview: {getattr(article, 'enriched_title', 'Unknown')[:30]}..."
                    )
                elif decision == "revise":
                    pending_revisions.append(article)
                    print(
                        f"🔧 Article needs revision: {getattr(article, 'enriched_title', 'Unknown')[:30]}..."
                    )
                else:  # reject
                    rejected_articles.append(article)
                    print(
                        f"❌ Article rejected: {getattr(article, 'enriched_title', 'Unknown')[:30]}..."
                    )

        except Exception as e:
            print(f"Error in editorial review {i+1}: {e}")
            rejected_articles.append(article)
            continue


def handle_follow_up_work(state: AgentState):
    """Handle interviews and revisions from editorial decisions."""

    print("Handling follow-up work...")
    # TODO:: DO THIS LATER...
    if hasattr(state, "pending_interviews") and state.pending_interviews:
        print(f"TODO: Process {len(state.pending_interviews)} interview articles")
        # For now, just move them back to enriched_articles for re-review
        if not hasattr(state, "enriched_articles"):
            state.enriched_articles = []
        state.enriched_articles.extend(state.pending_interviews)
        state.pending_interviews = []

    if hasattr(state, "pending_revisions") and state.pending_revisions:
        print(f"TODO: Process {len(state.pending_revisions)} revision articles")
        # For now, just move them back to enriched_articles for re-review
        if not hasattr(state, "enriched_articles"):
            state.enriched_articles = []
        state.enriched_articles.extend(state.pending_revisions)
        state.pending_revisions = []

    return state


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

    # FROM THIS WE START EDITORIAL REVIEW -> ONE ARTICLE AT A TIME - SO WE'LL USE A SUBGRAPH
    graph_builder.add_node("editorial_batch", process_editorial_batch)
    graph_builder.add_node("handle_follow_ups", handle_follow_up_work)

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
    graph_builder.add_edge("article_storer", "editorial_batch")

    # Check for pending work after editorial batch
    graph_builder.add_conditional_edges(
        source="editorial_batch",
        path=has_pending_work,
        path_map={"handle_follow_ups": "handle_follow_ups", "end": END},
    )
    graph_builder.add_edge("handle_follow_ups", "editorial_batch")
    graph = graph_builder.compile()

    # Run the agent graph in a loop to continuously fetch and process news articles
    while True:
        state = AgentState()
        result = graph.invoke(state)
        print("Graph done!")
        time.sleep(60)
