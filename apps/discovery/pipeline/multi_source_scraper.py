import asyncio
import email.utils
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import unquote, urlencode

import httpx

class MultiSourceScraper:
    """
    Parallel multi-source discovery engine.
    Ingests signals from 100% free, public sources:
    1. Google News RSS (Mainstream & Enterprise PR)
    2. Tech Funding News RSS (Startup & Mid-market Venture Capital Deals)
    3. EU-Startups RSS (Early & Growth Stage B2B Tech Startups)
    4. TechCrunch RSS (Venture & Enterprise Technology News)
    5. VentureBeat RSS (Enterprise AI, Data, and Digital Transformation)
    6. PR Newswire Tech RSS (Direct Corporate Releases, Executive Appointments)
    7. Hacker News Official API (Active tech migrations, Show HN, startup launches)
    """

    DEFAULT_USER_AGENT = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    )

    def __init__(self):
        self.gnews_base_url = "https://news.google.com/rss"
        self.headers = {
            'User-Agent': self.DEFAULT_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

    def clean_text(self, text):
        """Clean unicode, HTML entities, and normalized whitespace."""
        if not text:
            return ""
        try:
            def decode_match(match):
                return chr(int(match.group(1), 16))
            text = re.sub(r'\\u([0-9a-fA-F]{4})', decode_match, text)
        except Exception:
            pass
        text = html.unescape(text)
        return ' '.join(text.split()).strip()

    def clean_html(self, text):
        """Strip HTML tags and unquote."""
        if not text:
            return ""
        clean = re.sub(r'<[^<]+?>', '', text)
        clean = unquote(clean)
        return ' '.join(clean.split()).strip()

    def is_within_last_N_days(self, date_string, days):
        """Verify publication date falls within timeframe."""
        if not date_string:
            return True
        try:
            parsed_tuple = email.utils.parsedate_tz(date_string)
            if parsed_tuple:
                pub_date = datetime.fromtimestamp(email.utils.mktime_tz(parsed_tuple))
                n_days_ago = datetime.now() - timedelta(days=days)
                return pub_date >= n_days_ago
        except Exception:
            pass
        return True

    async def fetch_rss_feed(self, client, url, source_label, query_filter="", timeframe_days=60, existing_urls=None):
        """Generic asynchronous RSS feed parser with Trafilatura/lxml."""
        articles = []
        try:
            from apps.pulses.services.ai.url_service import is_safe_public_url
            if not is_safe_public_url(url):
                print(f"[Security] Blocked potential SSRF attempt for RSS feed: {url}")
                return []
        except Exception:
            pass

        try:
            resp = await client.get(url, timeout=12.0)
            if resp.status_code != 200 or not resp.text:
                return []

            content = resp.text.replace('\x00', '')
            if not content.startswith('<?xml'):
                content = '<?xml version="1.0" encoding="UTF-8"?>' + content

            root = ET.fromstring(content)
            now_iso = datetime.now().isoformat()

            for item in root.findall('.//item'):
                title_elem = item.find('title')
                title = self.clean_text(title_elem.text if title_elem is not None else "")

                link_elem = item.find('link')
                article_url = link_elem.text.strip() if link_elem is not None and link_elem.text else ""

                pub_date_elem = item.find('pubDate')
                pub_date = pub_date_elem.text if pub_date_elem is not None else ""

                desc_elem = item.find('description')
                desc = self.clean_html(desc_elem.text if desc_elem is not None else "")

                if not title or not article_url:
                    continue

                # Early-exit: Skip if article URL has already been ingested in past runs
                if existing_urls and article_url in existing_urls:
                    continue

                if pub_date and not self.is_within_last_N_days(pub_date, timeframe_days):
                    continue

                # If a query filter is specified, check relevant terms
                if query_filter:
                    if isinstance(query_filter, (list, tuple, set)):
                        terms = [t.lower() for kw in query_filter for t in str(kw).split() if len(t) > 2]
                        matched_kw = ", ".join(list(query_filter)[:2])
                    else:
                        terms = [t.lower() for t in str(query_filter).split() if len(t) > 2]
                        matched_kw = str(query_filter)

                    searchable = f"{title} {desc}".lower()
                    if terms and not any(t in searchable for t in terms):
                        continue
                else:
                    matched_kw = "general"

                articles.append({
                    'query': matched_kw,
                    'title': title,
                    'source': source_label,
                    'url': article_url,
                    'publication_date': pub_date,
                    'description': desc,
                    'scraped_at': now_iso
                })
        except Exception as e:
            err_type = type(e).__name__
            err_msg = f": {e}" if str(e) else ""
            print(f"[{source_label}] Feed fetch error ({err_type}{err_msg})")

        return articles

    async def fetch_google_news(self, client, query, timeframe_days, existing_urls=None):
        """Scrape Google News RSS for keyword."""
        search_params = {
            'q': f"{query} when:{timeframe_days}d",
            'hl': 'en-US',
            'gl': 'US',
            'ceid': 'US:en'
        }
        url = f"{self.gnews_base_url}/search?{urlencode(search_params)}"
        return await self.fetch_rss_feed(client, url, "Google News", query, timeframe_days, existing_urls=existing_urls)

    async def fetch_hacker_news(self, client, query, timeframe_days, existing_urls=None):
        """
        Fetch top tech/startup stories and Show HN launches via official free Firebase API.
        """
        articles = []
        try:
            top_ids_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
            resp = await client.get(top_ids_url, timeout=10.0)
            if resp.status_code != 200:
                return []

            story_ids = resp.json()[:30]  # Take top 30 current stories
            now_iso = datetime.now().isoformat()

            if isinstance(query, (list, tuple, set)):
                query_terms = [t.lower() for kw in query for t in str(kw).split() if len(t) > 2]
                primary_kw = ", ".join(list(query)[:2])
            else:
                query_terms = [t.lower() for t in str(query).split() if len(t) > 2]
                primary_kw = str(query)

            async def fetch_item(item_id):
                try:
                    item_resp = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json", timeout=6.0)
                    if item_resp.status_code == 200:
                        data = item_resp.json()
                        title = data.get('title', '')
                        url = data.get('url', f"https://news.ycombinator.com/item?id={item_id}")

                        # Skip if already exists in DB
                        if existing_urls and url in existing_urls:
                            return None

                        searchable = title.lower()

                        if query_terms and not any(t in searchable for t in query_terms):
                            return None

                        return {
                            'query': primary_kw,
                            'title': self.clean_text(title),
                            'source': 'Hacker News Tech',
                            'url': url,
                            'publication_date': datetime.fromtimestamp(data.get('time', 0)).strftime('%a, %d %b %Y %H:%M:%S GMT') if data.get('time') else "",
                            'description': f"Show HN / Community discussion: {title}",
                            'scraped_at': now_iso
                        }
                except Exception:
                    return None

            results = await asyncio.gather(*[fetch_item(sid) for sid in story_ids])
            for r in results:
                if r:
                    articles.append(r)
        except Exception as e:
            err_type = type(e).__name__
            err_msg = f": {e}" if str(e) else ""
            print(f"[Hacker News API] Error ({err_type}{err_msg})")

        return articles

    async def scrape_all_sources_parallel(self, keywords, timeframe_days, existing_urls=None):
        """
        Execute concurrent, parallel extraction across:
        1. Google News RSS (per keyword)
        2. Tech Funding News (venture deals)
        3. EU-Startups (startup expansions)
        4. GlobeNewswire Technology
        5. PR Newswire (B2B press releases)
        6. Hacker News Top Launches
        """
        all_articles = []
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
        async def _check_redirect_safety(response):
            if response.is_redirect and 'location' in response.headers:
                from urllib.parse import urljoin
                from apps.pulses.services.ai.url_service import is_safe_public_url
                target = urljoin(str(response.url), response.headers['location'])
                if not is_safe_public_url(target):
                    raise httpx.RequestError(f"Blocked SSRF redirect to unsafe target: {target}")

        async with httpx.AsyncClient(
            headers=self.headers,
            follow_redirects=True,
            timeout=timeout,
            limits=limits,
            event_hooks={'response': [_check_redirect_safety]}
        ) as client:
            tasks = []

            # 1. Google News queries (keyword specific)
            for kw in keywords:
                tasks.append(self.fetch_google_news(client, kw, timeframe_days, existing_urls=existing_urls))

            # 2. Industry & Venture Feeds (fetched ONCE and matched against all keywords in-memory)
            tasks.append(self.fetch_rss_feed(
                client,
                "https://techfundingnews.com/feed/",
                "Tech Funding News",
                keywords,
                timeframe_days,
                existing_urls=existing_urls
            ))
            tasks.append(self.fetch_rss_feed(
                client,
                "https://www.eu-startups.com/feed/",
                "EU-Startups",
                keywords,
                timeframe_days,
                existing_urls=existing_urls
            ))
            tasks.append(self.fetch_rss_feed(
                client,
                "https://feeds.feedburner.com/TechCrunch/",
                "TechCrunch",
                keywords,
                timeframe_days,
                existing_urls=existing_urls
            ))
            tasks.append(self.fetch_rss_feed(
                client,
                "https://venturebeat.com/feed/",
                "VentureBeat",
                keywords,
                timeframe_days,
                existing_urls=existing_urls
            ))
            tasks.append(self.fetch_rss_feed(
                client,
                "https://www.prnewswire.com/rss/financial-services-latest-news/financial-services-latest-news-list.rss",
                "PR Newswire Finance & Enterprise",
                keywords,
                timeframe_days,
                existing_urls=existing_urls
            ))
            tasks.append(self.fetch_hacker_news(client, keywords, timeframe_days, existing_urls=existing_urls))

            # Execute all parallel source tasks simultaneously
            print(f"Launching {len(tasks)} parallel source fetch tasks via HTTPX + Trafilatura...")
            results = await asyncio.gather(*tasks, return_exceptions=True)

            seen_urls = set(existing_urls or [])
            exception_count = 0
            for res in results:
                if isinstance(res, Exception):
                    exception_count += 1
                elif isinstance(res, list):
                    for item in res:
                        u = item.get('url')
                        if u and u not in seen_urls:
                            seen_urls.add(u)
                            all_articles.append(item)

            # If every single source task failed with an exception, this is a network outage
            if len(tasks) > 0 and exception_count == len(tasks):
                first_err = next((str(r) for r in results if isinstance(r, Exception) and str(r)), "Connection refused or timed out")
                raise ConnectionError(f"Network outage: All {len(tasks)} signal source requests failed. Check internet connection. (Detail: {first_err})")

        print(f"Multi-source ingestion finished: {len(all_articles)} raw signals extracted across all platforms.")
        return all_articles
