# SQLite Schema & ER Diagram

This document contains the exact SQLite database schema currently used in the codebase (`news_scraper.db`), alongside a visual Entity-Relationship (ER) diagram representing the tables and foreign-key mappings.

---

## 1. Entity-Relationship (ER) Diagram

```mermaid
erDiagram
    queries {
        int id PK
        string keyword UNIQUE
        string category
        string target_focus
        int is_active
    }

    signal_definitions {
        int id PK
        string name UNIQUE
        string category
        string definition
        int is_active
    }

    articles {
        int id PK
        int query_id FK
        string title
        string source
        string url
        string publication_date
        string description
        string scraped_at
        blob embedding
        int is_duplicate
        int matched_original_id
        string duplicate_reason
        string delta_summary
        int is_relevant
        int relevance_score
        string buying_signal
        string relevance_tier
        string relevance_reason
        string executive_summary
        int is_summarized
        int prompt_tokens
        int completion_tokens
        int total_tokens
    }

    companies {
        int id PK
        string name UNIQUE
        int score
        string buying_signal
        string reason
        int source_article_id FK
        string extracted_at
    }

    leads {
        int id PK
        string name
        string designation
        string organization_name
        int score
        string buying_signal
        string reason
        string email
        string phone
        int source_article_id FK
        string extracted_at
    }

    competitors {
        int id PK
        string name UNIQUE
        string buying_signal
        string reason
        int source_article_id FK
        string extracted_at
    }

    corrections {
        int id PK
        int article_id FK
        string original_tier
        string corrected_tier
        string note
        string created_at
    }

    queries ||--o{ articles : "categorizes"
    articles ||--o{ corrections : "tracks"
    articles ||--o{ companies : "extracts"
    articles ||--o{ leads : "extracts"
    articles ||--o{ competitors : "extracts"
```

---

## 2. Table DDL Schemas

### `queries`
```sql
CREATE TABLE queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL,
    target_focus TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
);
```

### `signal_definitions`
```sql
CREATE TABLE signal_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('actionable', 'noise')),
    definition TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
);
```

### `articles`
```sql
CREATE TABLE articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    source TEXT,
    url TEXT NOT NULL,
    publication_date TEXT,
    description TEXT,
    scraped_at TEXT NOT NULL,
    embedding BLOB,
    is_duplicate INTEGER DEFAULT 0,
    matched_original_id INTEGER,
    duplicate_reason TEXT,
    delta_summary TEXT,
    is_relevant INTEGER DEFAULT 1,
    relevance_score INTEGER DEFAULT 0,
    buying_signal TEXT,
    relevance_tier TEXT DEFAULT 'actionable',
    relevance_reason TEXT,
    executive_summary TEXT,
    is_summarized INTEGER DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    FOREIGN KEY (query_id) REFERENCES queries (id) ON DELETE CASCADE
);
```

### `companies`
```sql
CREATE TABLE companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    score INTEGER,
    buying_signal TEXT,
    reason TEXT,
    source_article_id INTEGER,
    extracted_at TEXT,
    FOREIGN KEY (source_article_id) REFERENCES articles(id) ON DELETE SET NULL
);
```

### `leads`
```sql
CREATE TABLE leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    designation TEXT,
    organization_name TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    buying_signal TEXT,
    reason TEXT,
    email TEXT,
    phone TEXT,
    source_article_id INTEGER,
    extracted_at TEXT,
    FOREIGN KEY (source_article_id) REFERENCES articles(id) ON DELETE SET NULL
);
```

### `competitors`
```sql
CREATE TABLE competitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    buying_signal TEXT,
    reason TEXT,
    source_article_id INTEGER,
    extracted_at TEXT,
    FOREIGN KEY (source_article_id) REFERENCES articles(id) ON DELETE SET NULL
);
```

### `corrections`
```sql
CREATE TABLE corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    original_tier TEXT NOT NULL,
    corrected_tier TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (article_id) REFERENCES articles(id)
);
```
