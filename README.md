# Prospect Pulse v2.0

Prospect Pulse is an AI-driven B2B intelligence and lead discovery platform built on Django. It automates web scraping, semantic deduplication, LLM-based relevance classification, and lead extraction for target accounts and Ideal Customer Profiles (ICPs).

---

## What's New in v2.0

- **Multi-Source Scraping**: Integrated Google News RSS, Bing News, and direct publisher scrapers with robust anti-bot headers and rate-limiting.
- **Semantic Deduplication**: Near-duplicate article clustering using 64-bit SimHash and configurable Hamming distance thresholds.
- **LLM-Driven Relevance & Lead Extraction**: Powered by Google Gemini (`gemini-2.5-flash`) for relevance scoring, sentiment analysis, key account extraction, and contact discovery.
- **Enrichment & Fallback Integration**: External lead enrichment client (Disburse API integration) with automated retries and schema validation.
- **Data Export Capabilities**: One-click export of discovered leads and target accounts into Excel (`.xlsx`) and CSV formats.
- **Security & Production Hardening**: Strict CSRF protection, secure cookie flags, environment-driven secrets, sanitized structured logging, and verified `check --deploy` compliance.
- **Asynchronous Architecture**: Celery worker and Celery beat scheduling backed by Redis.

---

## Tech Stack

- **Backend**: Python 3.11+ / Django 5.x
- **Task Queue**: Celery 5.x + Redis
- **AI / LLM**: Google Gemini (`google-genai` / `google-generativeai`)
- **Scraping & Parsing**: BeautifulSoup4, lxml, Feedparser, Requests
- **Frontend**: Django Templates, Bootstrap 5, Custom CSS/JS

---

## Quickstart

### 1. Environment Setup
```bash
python -m venv venv
# Linux / macOS
source venv/bin/activate
# Windows
.\venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy the example environment file and set your keys:
```bash
cp .env.example .env
```
Ensure you provide your `SECRET_KEY` and `GOOGLE_API_KEY`.

### 3. Database & Migrations
```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Run Services
```bash
# Terminal 1: Redis Broker
redis-server

# Terminal 2: Celery Worker
celery -A prospect_pulse worker -l info

# Terminal 3: Django Web App
python manage.py runserver
```

---

## License
Proprietary / All Rights Reserved.
