# News Room Production System

A sophisticated AI-powered news processing pipeline that automatically fetches articles from RSS feeds, enriches them with additional context through web searches, and produces publication-ready news articles with editorial oversight.

## Architecture

The system implements a multi-stage pipeline architecture using LangGraph with the following agents:

### Main Pipeline Agents

1. **FeedReaderAgent**: Fetches news articles from configured RSS feeds and performs initial filtering
2. **ArticleContentExtractorAgent**: Extracts and parses full article content from URLs, detects language, classifies article types, and identifies contact information
3. **NewsStorerAgent**: Stores original articles in PostgreSQL database with deduplication using content hashing and semantic embeddings
4. **NewsPlannerAgent**: Uses LLM to analyze articles and create enhancement plans including keywords, categories, and targeted web search queries
5. **WebSearchAgent**: Performs intelligent web searches using Selenium (DuckDuckGo, Bing, Google) to gather additional context and perspectives
6. **ArticleGeneratorAgent**: Combines original content with web search results to generate comprehensive, enriched articles using LLM
7. **ImageGeneratorAgent**: Generate images for article
8. **ArticleStorerAgent**: Stores enriched articles in database with HTML content blocks ready for publication

### Editorial Review Subgraph

After the main pipeline, each enriched article is processed individually through an editorial review subgraph:

1. **EditorInChiefAgent**: Reviews articles for legal compliance (Finnish law), journalistic ethics (JSN guidelines), editorial quality, and determines publication decisions
2. **ArticleReviserAgent**: Handles article revisions when needed
3. **FixValidationAgent**: Validates fixes and improvements
4. **ArticlePublisherAgent**: Publishes approved articles'
5. **ArticleRejectAgent**: Reject the article
6. **InterviewPlanningAgent**: Start the interview process

The editorial subgraph makes decisions to:

- **Publish**: Article meets all standards and is published immediately
- **Interview**: Article needs additional expert interviews or stakeholder input
- **Revise**: Article needs content improvements or corrections
- **Reject**: Article fails editorial standards

## Database Structure

The system uses PostgreSQL with pgvector extension for storing both original and enriched news articles:

## Setup and Configuration

### Prerequisites

- Python 3.9+
- PostgreSQL database with pgvector extension
- OpenAI API key for GPT-4o-mini
- Docker and Docker Compose (for database setup)

### Installation Steps

1. Clone the repository and navigate to the project directory

2. Create a virtual environment and activate it:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   source .venv/bin/activate  # Linux/Mac
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env`, whats example from .env.example file

5. Set up the PostgreSQL database with Docker:

   ```bash
   docker-compose up -d
   ```

6. Configure RSS feeds in `newsfeeds.yaml`:

   ```yaml
   feeds:
     - name: "Example News"
       url: "https://example.com/rss"
       category: "general"
       active: true
   ```

7. Initialize the database (if needed):

   ```bash
   python -c "from services.database_service import init_database; init_database()"
   ```

8. Run the system:

   ```bash
   python main.py
   ```

The system will continuously monitor RSS feeds and process new articles through the entire pipeline.

## Requirements

- Python 3.9+
- PostgreSQL database with pgvector extension
- OpenAI API key (for GPT-4 API access)
- Selenium WebDriver dependencies for web searching

## Development

To add a new agent to the pipeline:

1. Create a new agent class that extends BaseAgent
2. Update the `AgentState` schema if needed
3. Add the agent to `main.py`
4. Update the state graph to include the new agent in the workflow
