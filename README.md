# News Room Production System

A sophisticated news processing pipeline that fetches articles from RSS feeds, plans enhancements, performs web searches, and generates enriched news articles using AI.

## Architecture

The system implements a pipeline architecture using LangGraph with the following agents:

1. **FeedReaderAgent**: Fetches news articles from configured RSS feeds
2. **ArticleContentExtractorAgent**: Extracts structured content from raw articles
3. **NewsStorerAgent**: Stores original articles in a PostgreSQL database
4. **NewsPlannerAgent**: Creates enhancement plans for articles using AI
5. **WebSearchAgent**: Performs web searches based on article plans to gather additional information
6. **ArticleGeneratorAgent**: Generates enriched articles by combining original content with web search results
7. **ArticleStorerAgent**: Stores the enriched articles in the database with HTML content blocks

## Data Flow

The system maintains proper data flow between agents through an `AgentState` object:

- `state.articles`: Contains the original articles fetched from RSS feeds (never overwritten)
- `state.plan`: Stores article enhancement plans created by NewsPlannerAgent
- `state.web_search_results`: Stores web search results from WebSearchAgent
- `state.enriched_articles`: Stores the generated enriched articles from ArticleGeneratorAgent

The `EnrichedArticle` schema includes:
- Core article data (title, content, metadata)
- Location tags (continent, country, region, city)
- Article references (links to cited sources)

Each agent processes data from its respective input fields and stores results in its designated output field, ensuring a clean data flow without overwriting.

## Database Structure

The system uses PostgreSQL for storing both original and enriched news articles:

### Original Articles Table
- `canonical_news`: Stores the original articles fetched from RSS feeds

### Enriched Articles Table
- `news_article`: Stores the AI-enriched articles with HTML content blocks
  - `id`: Unique identifier
  - `canonical_news_id`: Reference to the original article
  - `language`: ISO language code (e.g., 'fi', 'en', 'sv')
  - `lead`: Article introduction paragraph
  - `summary`: Brief summary of the article
  - `body_blocks`: JSON structure containing HTML content blocks
  - `location_tags`: Geographic locations mentioned in the article
  - `sources`: References to external sources
  - Other metadata fields (status, author, timestamps)

### Junction Tables
- `news_article_category`: Links articles to categories
- `news_article_keyword`: Links articles to keywords

The system automatically converts markdown content to HTML blocks when storing articles, making them ready for frontend display.

## Setup and Configuration

1. Create a `.env` file with PostgreSQL database credentials:
   ```
   DB_USER=your_username
   DB_PASSWORD=your_password
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=newsroom
   ```

2. Configure RSS feeds in `newsfeeds.yaml`

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up the database:
   ```
   docker-compose up -d
   ```

5. Test the database and HTML conversion:
   ```
   python test_database.py
   ```

6. Run the system:
   ```
   python main.py
   ```

## Requirements

- Python 3.9+
- PostgreSQL database with pgvector extension
- OpenAI API key (for GPT-4 API access)

## Development

To add a new agent to the pipeline:
1. Create a new agent class that extends BaseAgent
2. Update the `AgentState` schema if needed
3. Add the agent to `main.py`
4. Update the state graph to include the new agent in the workflow

## Future Enhancements

- Storing enriched articles in the database
- Web interface for viewing generated articles
- More sophisticated article enrichment strategies
- Support for additional languages