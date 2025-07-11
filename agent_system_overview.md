# Newsroom Production - Agent System Documentation

## Overview

Newsroom production system käyttää agenttipohjaista arkkitehtuuria uutisten käsittelyyn RSS-syötteistä valmiiksi rikastettuihin ja tarkastettuihin artikkeleihin.

## Agent Pipeline Flow

```text
RSS Feeds → ArticleContentExtractorAgent → NewsPlannerAgent → WebSearchAgent → ArticleGeneratorAgent → EditorInChiefAgent → NewsStorerAgent
```

## Agents and Their Responsibilities

### 1. ArticleContentExtractorAgent

**Purpose**: Fetches and parses article content from RSS feed URLs

**Input**:

- `state.articles: List[CanonicalArticle]` (basic RSS data)

**Output**:

- Updates `state.articles` with full content, language detection, and article type classification

**Schemas Used**:

- `CanonicalArticle` (from `feed_schema.py`) - Input and output
- `ParsedArticle` (from `parsed_article.py`) - Temporary parsing result
- `AgentState` (from `agent_state.py`) - State management

**Key Operations**:

- Calls `to_structured_article(url)` to parse HTML content to markdown
- Detects article language using title
- Classifies article type (news, press release, etc.)
- Updates articles with content, language, and metadata

---

### 2. NewsPlannerAgent

**Purpose**: Creates enrichment plans for articles using LLM analysis

**Input**:

- `state.articles: List[CanonicalArticle]` (articles with content)

**Output**:

- `state.plan: List[NewsArticlePlan]` (enrichment plans)

**Schemas Used**:

- `NewsArticlePlan` (from `article_plan_schema.py`) - Output planning structure
- `CanonicalArticle` (from `feed_schema.py`) - Input articles
- `AgentState` (from `agent_state.py`) - State management

**Key Operations**:

- Analyzes article content with LLM
- Generates keywords, categories, and search queries
- Creates new headlines and summaries
- Uses structured LLM output with `NewsArticlePlan` schema

---

### 3. WebSearchAgent

**Purpose**: Performs web searches to gather additional context for articles

**Input**:

- `state.plan: List[NewsArticlePlan]` (contains web_search_queries)

**Output**:

- `state.article_search_map: Dict[str, List[ParsedArticle]]` (search results by article_id)

**Schemas Used**:

- `NewsArticlePlan` (from `article_plan_schema.py`) - Input plans
- `ParsedArticle` (from `parsed_article.py`) - Search result structure
- `AgentState` (from `agent_state.py`) - State management

**Key Operations**:

- Uses Selenium for web searching (DuckDuckGo, Bing, Google)
- Parses search result pages to extract content
- Maps results to article IDs for later enrichment
- Handles search failures with fallback mechanisms

---

### 4. ArticleGeneratorAgent

**Purpose**: Generates enriched articles combining original content with web search results

**Input**:

- `state.articles: List[CanonicalArticle]` (original articles)
- `state.plan: List[NewsArticlePlan]` (enrichment plans)
- `state.article_search_map: Dict[str, List[ParsedArticle]]` (web search results)

**Output**:

- `state.enriched_articles: List[EnrichedArticle]` (generated enriched articles)

**Schemas Used**:

- `EnrichedArticle` (from `enriched_article.py`) - Output structure
- `LLMArticleOutput` (from `enriched_article.py`) - LLM response structure
- `CanonicalArticle` (from `feed_schema.py`) - Original articles
- `NewsArticlePlan` (from `article_plan_schema.py`) - Plans
- `ParsedArticle` (from `parsed_article.py`) - Search results
- `AgentState` (from `agent_state.py`) - State management

**Key Operations**:

- Combines original article with web search context
- Uses LLM to generate enriched content in markdown
- Extracts keywords, locations, and references
- Creates comprehensive enriched articles

---

### 5. EditorInChiefAgent

**Purpose**: Reviews articles for legal, ethical, and editorial compliance

**Input**:

- `state.enriched_articles: List[EnrichedArticle]` (generated articles)

**Output**:

- `state.reviewed_articles: List[ReviewedNewsItem]` (editorial decisions)
- Updates `featured` and `interview_needed` flags on enriched articles

**Schemas Used**:

- `ReviewedNewsItem` (from `editor_in_chief_schema.py`) - Review results
- `EditorialReasoning` (from `editor_in_chief_schema.py`) - Reasoning structure
- `InterviewDecision` (from `editor_in_chief_schema.py`) - Interview decisions
- `HeadlineNewsAssessment` (from `editor_in_chief_schema.py`) - Featured article assessment
- `ReasoningStep` (from `editor_in_chief_schema.py`) - Step-by-step reasoning
- `ReviewIssue` (from `editor_in_chief_schema.py`) - Issue tracking
- `EnrichedArticle` (from `enriched_article.py`) - Input articles
- `AgentState` (from `agent_state.py`) - State management

**Key Operations**:

- Legal compliance checking (Finnish law, defamation, privacy)
- Journalistic ethics review (JSN guidelines)
- Editorial quality assessment
- Featured article evaluation for front page
- Interview requirement decisions
- Structured reasoning with transparent decision-making

---

### 6. NewsStorerAgent

**Purpose**: Saves approved articles to database and handles publication workflow

**Input**:

- `state.reviewed_articles: List[ReviewedNewsItem]` (approved articles)
- `state.enriched_articles: List[EnrichedArticle]` (articles to store)

**Output**:

- Database persistence
- Updated `news_article_id` on stored articles

**Schemas Used**:

- `ReviewedNewsItem` (from `editor_in_chief_schema.py`) - Review decisions
- `EnrichedArticle` (from `enriched_article.py`) - Articles to store
- `AgentState` (from `agent_state.py`) - State management

**Key Operations**:

- Filters articles based on editorial approval
- Saves to database with proper metadata
- Updates articles with database IDs
- Handles publication status and timestamps

---

## Schema Dependencies

### Core Schemas

- **`AgentState`** - Central state management across all agents
- **`CanonicalArticle`** - RSS feed article structure
- **`EnrichedArticle`** - Final article output structure

### Planning Schemas

- **`NewsArticlePlan`** - Article enrichment planning
- **`ParsedArticle`** - Temporary parsing and search results

### Editorial Schemas

- **`ReviewedNewsItem`** - Editorial review results
- **`EditorialReasoning`** - Review reasoning structure
- **`InterviewDecision`** - Interview requirement decisions
- **`HeadlineNewsAssessment`** - Featured article evaluation

### Supporting Schemas

- **`ArticleReference`** - Article citations
- **`LocationTag`** - Geographic tagging
- **`LLMArticleOutput`** - LLM response structure

## Data Flow Summary

1. **RSS Ingestion**: `CanonicalArticle` objects created from feeds
2. **Content Extraction**: Articles enriched with full content and metadata
3. **Planning**: `NewsArticlePlan` objects created for each article
4. **Web Search**: `ParsedArticle` results mapped to plans
5. **Generation**: `EnrichedArticle` objects created combining all data
6. **Editorial Review**: `ReviewedNewsItem` decisions made
7. **Storage**: Approved articles saved to database

Each agent operates on shared `AgentState` allowing for transparent data flow and state management across the entire pipeline.
