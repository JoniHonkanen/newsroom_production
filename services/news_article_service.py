# File: services/news_article_service.py

import sys
import os
import json
import re
import markdown
from datetime import datetime
from typing import List, Dict, Any, Optional
import psycopg # type: ignore
import numpy as np

# Add project root to path for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schemas.enriched_article import EnrichedArticle, ArticleReference, LocationTag
from schemas.news_article_db import NewsArticleDB, ContentBlock


class NewsArticleService:
    """Service for managing news articles in the database."""
    
    def __init__(self, db_dsn: str):
        """Initialize with database connection string."""
        self.db_dsn = db_dsn
        self._setup_tables()
        
    def _setup_tables(self):
        """
        Make sure the database is ready. Tables should be created by the enable_pgvector.sql script
        when the container starts, but we'll add indexes if they don't exist.
        """
        with psycopg.connect(self.db_dsn) as conn:
            with conn.cursor() as cur:
                # Create helpful indexes if they don't exist
                cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_news_article_canonical_id ON news_article(canonical_news_id);
                CREATE INDEX IF NOT EXISTS idx_news_article_language ON news_article(language);
                CREATE INDEX IF NOT EXISTS idx_news_article_status ON news_article(status);
                """)
                conn.commit()
    
    def _convert_markdown_to_html_blocks(self, markdown_text: str) -> List[Dict[str, Any]]:
        """
        Convert markdown text to a list of HTML content blocks.
        Each block will be a dictionary with type, content and potentially other attributes.
        """
        # Convert the full markdown to HTML
        html = markdown.markdown(markdown_text, extensions=['tables', 'fenced_code'])
        
        # Split the HTML into logical blocks (paragraphs, headers, etc.)
        # This is a simplified approach - for production, consider using BeautifulSoup
        # or a more robust HTML parsing library
        
        # We'll create a simple regex-based splitter
        block_patterns = [
            # Headers
            (r'<h([1-6])>(.*?)</h\1>', 'header'),
            # Images
            (r'<img\s+([^>]+)>', 'image'),
            # Paragraphs
            (r'<p>(.*?)</p>', 'text'),
            # Lists
            (r'<(ul|ol)>(.*?)</\1>', 'list'),
            # Code blocks
            (r'<pre><code>(.*?)</code></pre>', 'code'),
            # Blockquotes
            (r'<blockquote>(.*?)</blockquote>', 'quote'),
        ]
        
        # Extract blocks
        blocks = []
        remaining_html = html
        block_count = 0
        
        while remaining_html:
            block_count += 1
            matched = False
            
            for pattern, block_type in block_patterns:
                match = re.search(pattern, remaining_html, re.DOTALL)
                if match:
                    matched = True
                    
                    if block_type == 'header':
                        level = match.group(1)
                        content = match.group(2)
                        blocks.append({
                            'order': block_count,
                            'type': f'h{level}',
                            'content': content,
                            'html': match.group(0)
                        })
                    elif block_type == 'image':
                        # Extract src and alt if available
                        img_attrs = match.group(1)
                        src_match = re.search(r'src="([^"]+)"', img_attrs)
                        alt_match = re.search(r'alt="([^"]+)"', img_attrs)
                        
                        src = src_match.group(1) if src_match else ""
                        alt = alt_match.group(1) if alt_match else ""
                        
                        blocks.append({
                            'order': block_count,
                            'type': 'image',
                            'content': src,
                            'alt': alt,
                            'html': match.group(0)
                        })
                    else:
                        blocks.append({
                            'order': block_count,
                            'type': block_type,
                            'content': match.group(1) if block_type != 'image' else match.group(0),
                            'html': match.group(0)
                        })
                    
                    # Remove the matched content from remaining_html
                    start, end = match.span()
                    remaining_html = remaining_html[:start] + remaining_html[end:]
                    break
            
            # If no patterns matched, treat the remaining content as a single block
            if not matched:
                if remaining_html.strip():
                    blocks.append({
                        'order': block_count,
                        'type': 'text',
                        'content': remaining_html,
                        'html': remaining_html
                    })
                remaining_html = ""
        
        return blocks
    
    def _convert_location_tags(self, location_tags: Optional[List[LocationTag]]) -> Optional[Dict[str, Any]]:
        """Convert LocationTag objects to JSON structure for database storage."""
        if not location_tags:
            return None
        
        return [tag.dict(exclude_none=True) for tag in location_tags]
    
    def _convert_article_references(self, references: Optional[List[ArticleReference]]) -> Optional[List[Dict[str, str]]]:
        """Convert ArticleReference objects to JSON structure for database storage."""
        if not references:
            return None
        
        return [ref.dict() for ref in references]
    
    def _ensure_canonical_news_exists(self, canonical_news_id: str) -> int:
        """
        Ensure that the canonical_news record exists.
        If it's a string, convert it to integer to match the database schema.
        """
        try:
            return int(canonical_news_id)
        except ValueError:
            # If conversion fails, log a warning and return a default ID
            print(f"Warning: canonical_news_id '{canonical_news_id}' is not an integer.")
            # In a real application, you'd want to handle this more gracefully
            return 1  # Return a default ID or create a new canonical_news entry
    
    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate a vector embedding for the article text.
        This is a placeholder - in a real implementation, you would use a model like OpenAI's Ada or a local embedding model.
        """
        # This is just a placeholder - replace with actual embedding generation
        # For example, using OpenAI's API:
        # from openai import OpenAI
        # client = OpenAI()
        # response = client.embeddings.create(input=text, model="text-embedding-ada-002")
        # return response.data[0].embedding
        
        # Return None for now
        return None
        
    def save_enriched_article(self, article: EnrichedArticle) -> int:
        """
        Save an enriched article to the database.
        Returns the ID of the created database record.
        """
        # Extract the lead paragraph (first sentence or paragraph)
        content_parts = article.enriched_content.split('\n\n', 1)
        lead = content_parts[0].strip()
        
        # Convert markdown to HTML blocks
        body_blocks = self._convert_markdown_to_html_blocks(article.enriched_content)
        
        # Convert location tags and references to JSON
        location_tags_json = self._convert_location_tags(article.locations)
        sources_json = self._convert_article_references(article.references)
        
        # Generate text embedding if needed
        embedding = self._generate_embedding(article.enriched_content)
          # Create database record
        db_article = NewsArticleDB(
            canonical_news_id=int(article.article_id),  # Make sure it's an integer as required by the SQL schema
            language=article.language,
            version=1,  # Initial version
            lead=lead,
            summary=article.enriched_content[:200] + '...',  # Simple summary
            status='draft',  # Default status
            location_tags=location_tags_json,
            sources=sources_json,
            interviews=None,  # Not implemented yet
            review_status='standard',  # Default status for editorial review
            author='AI Assistant',  # Default author
            embedding=embedding,
            body_blocks=body_blocks,
            published_at=datetime.fromisoformat(article.generated_at),
            updated_at=datetime.now(),
        )
        
        # Save to database
        with psycopg.connect(self.db_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                INSERT INTO news_article 
                (canonical_news_id, language, version, lead, summary, status, 
                 location_tags, sources, interviews, review_status, author, 
                 embedding, body_blocks, published_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """, (
                    db_article.canonical_news_id,                    db_article.language,
                    db_article.version,
                    db_article.lead,
                    db_article.summary,
                    db_article.status,
                    Json(db_article.location_tags) if db_article.location_tags else None,
                    Json(db_article.sources) if db_article.sources else None,
                    Json(db_article.interviews) if db_article.interviews else None,
                    db_article.review_status,
                    db_article.author,
                    db_article.embedding,  # This will be None for now
                    Json(db_article.body_blocks),
                    db_article.published_at,
                    db_article.updated_at
                ))
                
                article_id = cur.fetchone()[0]
                
                # Save categories
                for category in article.categories:
                    # First, ensure the category exists
                    cur.execute(
                        "INSERT INTO category (slug) VALUES (%s) ON CONFLICT (slug) DO NOTHING",
                        (category.lower(),)
                    )
                    # Get the category ID
                    cur.execute("SELECT id FROM category WHERE slug = %s", (category.lower(),))
                    category_id = cur.fetchone()[0]
                    # Link article to category
                    cur.execute(
                        "INSERT INTO news_article_category (category_id, article_id) VALUES (%s, %s)",
                        (category_id, article_id)
                    )
                
                # Save keywords
                for keyword in article.keywords:
                    # First, ensure the keyword exists
                    cur.execute(
                        "INSERT INTO keyword (slug) VALUES (%s) ON CONFLICT (slug) DO NOTHING",
                        (keyword.lower(),)
                    )
                    # Get the keyword ID
                    cur.execute("SELECT id FROM keyword WHERE slug = %s", (keyword.lower(),))
                    keyword_id = cur.fetchone()[0]
                    # Link article to keyword
                    cur.execute(
                        "INSERT INTO news_article_keyword (keyword_id, article_id) VALUES (%s, %s)",
                        (keyword_id, article_id)
                    )
                
                conn.commit()
                
                return article_id
