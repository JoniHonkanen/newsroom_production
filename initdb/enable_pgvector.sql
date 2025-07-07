-- This SQL script enables the pgvector extension in PostgreSQL.
-- this runs when docker-compose up is executed
CREATE EXTENSION IF NOT EXISTS vector;

-- Kieli (languages)
CREATE TABLE languages (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name_fi TEXT NOT NULL,
    name_en TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

-- category & keyword -pohjataulut ja käännökset
CREATE TABLE category (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE
);

CREATE TABLE category_translation (
    id SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES category(id),
    language TEXT NOT NULL,
    label TEXT NOT NULL
);

CREATE TABLE keyword (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE
);

CREATE TABLE keyword_translation (
    id SERIAL PRIMARY KEY,
    keyword_id INTEGER NOT NULL REFERENCES keyword(id),
    language TEXT NOT NULL,
    label TEXT NOT NULL
);

-- MAIN NEWS TABLE
CREATE TABLE canonical_news (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT,
    source_name TEXT,
    source_url TEXT,
    content_hash TEXT UNIQUE,
    content_embedding VECTOR(384),
    published_at TIMESTAMP WITH TIME ZONE, -- When the article was published
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), -- When the article was created in the system
    language TEXT,
    article_type TEXT
);

-- REFERENCES to canonical_news table
CREATE TABLE news_sources (
    id SERIAL PRIMARY KEY,
    canonical_news_id INTEGER NOT NULL REFERENCES canonical_news(id) ON DELETE CASCADE,
    source_name TEXT,
    source_url TEXT NOT NULL,
    original_guid TEXT,
    published_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    CONSTRAINT uq_source_url UNIQUE (source_url),
    article_type TEXT
);

-- Article, used for website to show the news articles
CREATE TABLE news_article (
    id SERIAL PRIMARY KEY,
    canonical_news_id INTEGER NOT NULL REFERENCES canonical_news(id) ON DELETE CASCADE,
    language TEXT NOT NULL,
    version INTEGER,
    lead TEXT,
    summary TEXT,
    status TEXT,
    location_tags JSONB,
    sources JSONB,
    interviews JSONB,
    review_status TEXT,
    author TEXT,
    embedding VECTOR(1536),
    body_blocks JSONB,
    enrichment_status VARCHAR(24) DEFAULT 'pending',
    markdown_content TEXT,  -- Alkuperäinen markdown-sisältö kokonaisuutena
    published_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    original_article_type TEXT DEFAULT NULL,
);

-- Kategoria- ja avainsanaliitostaulut
CREATE TABLE news_article_category (
    category_id INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
    article_id INTEGER NOT NULL REFERENCES news_article(id) ON DELETE CASCADE,
    PRIMARY KEY (category_id, article_id)
);

CREATE TABLE news_article_keyword (
    keyword_id INTEGER NOT NULL REFERENCES keyword(id) ON DELETE CASCADE,
    article_id INTEGER NOT NULL REFERENCES news_article(id) ON DELETE CASCADE,
    PRIMARY KEY (keyword_id, article_id)
);

-- EMAIL INTERVIEWS
CREATE TABLE email_interview (
    id SERIAL PRIMARY KEY,
    canonical_news_id INTEGER NOT NULL REFERENCES canonical_news(id) ON DELETE CASCADE,
    message_id TEXT,
    recipient TEXT,
    subject TEXT,
    sent_at TIMESTAMP,
    status TEXT
);

CREATE TABLE email_replies (
    id SERIAL PRIMARY KEY,
    uid TEXT,
    email_id INTEGER NOT NULL REFERENCES email_interview(id) ON DELETE CASCADE,
    from_address TEXT,
    in_reply_to TEXT,
    body TEXT,
    received_at TIMESTAMP
);

CREATE TABLE email_questions (
    id SERIAL PRIMARY KEY,
    email_id INTEGER NOT NULL REFERENCES email_interview(id) ON DELETE CASCADE,
    topic TEXT,
    question TEXT,
    position INTEGER
);

-- PHONE INTERVIEWS
CREATE TABLE phone_interview (
    id SERIAL PRIMARY KEY,
    canonical_news_id INTEGER NOT NULL REFERENCES canonical_news(id) ON DELETE CASCADE,
    to_number TEXT,
    from_number TEXT,
    prompt TEXT,
    transcript_json JSONB,
    status TEXT,
    created_at TIMESTAMP DEFAULT now(),
    language TEXT
);

CREATE TABLE phone_interview_attempt (
    id SERIAL PRIMARY KEY,
    phone_interview_id INTEGER NOT NULL REFERENCES phone_interview(id) ON DELETE CASCADE,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    status TEXT
);

-- FEED CATEGORIES 
CREATE TYPE feed_category AS ENUM (
    'press_release',
    'news',
    'blog',
    'event',
    'decision',
    'other'
);

-- RRS FEEDS! IF we have many feeds, maybe use this rather than file...
CREATE TABLE news_feeds (
    id SERIAL PRIMARY KEY,
    name TEXT,
    extra_info TEXT,
    feed_type TEXT NOT NULL,
    category feed_category NOT NULL,
    origin TEXT,
    url TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    added_at TIMESTAMP DEFAULT now(),
    modified_at TIMESTAMP DEFAULT now()
);



-- example block
-- body_block_example:
--   order INTEGER,
--   type TEXT,
--   content TEXT

-- image_example:
--   type TEXT,
--   url TEXT,
--   caption TEXT,
--   alt TEXT,
--   source TEXT,
--   photographer TEXT