import asyncio
import json
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, quote, unquote
from datetime import datetime, timedelta
import random
import re
import email.utils
from playwright.async_api import async_playwright

from apps.discovery.models import Article

class GoogleNewsScraper:
    def __init__(self):
        self.browser = None
        self.page = None
        self.base_url = "https://news.google.com/rss"

    async def setup_browser(self, proxy_config=None):
        """Setup browser with anti-detection measures"""
        playwright = await async_playwright().start()

        launch_options = {
            'headless': True,
            'args': [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
            ]
        }

        if proxy_config and proxy_config.get('enabled', False):
            country = proxy_config.get('country', 'US').lower()
            username = f"username-{country}-rotate"
            launch_options['proxy'] = {
                'server': proxy_config.get('server', 'http://p.webshare.io:80'),
                'username': proxy_config.get('username', username),
                'password': proxy_config.get('password', 'password')
            }

        self.browser = await playwright.chromium.launch(**launch_options)
        context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        self.page = await context.new_page()
        await self.page.set_extra_http_headers({
            'Accept': 'application/rss+xml, text/xml, */*',
            'Accept-Language': 'en-US,en;q=0.9',
        })

    async def random_delay(self, min_seconds=1, max_seconds=3):
        """Random delay between requests"""
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)

    def is_within_last_N_days(self, date_string, days):
        """Check if publication date is within the last N days"""
        if not date_string:
            return False
        try:
            parsed_tuple = email.utils.parsedate_tz(date_string)
            if parsed_tuple:
                pub_date = datetime.fromtimestamp(email.utils.mktime_tz(parsed_tuple))
                n_days_ago = datetime.now() - timedelta(days=days)
                return pub_date >= n_days_ago
        except Exception as e:
            print(f"Error parsing date {date_string}: {e}")
        return True

    async def scrape_news_rss(self, query, timeframe_days, search_config):
        """Scrape news from Google RSS feed with configurable parameters"""
        all_articles = []
       
        for page in range(search_config.get('pagination', 1)):
            search_params = {
                'q': f"{query} when:{timeframe_days}d",
                'hl': search_config.get('hl', 'en-US'),
                'gl': search_config.get('gl', 'US'),
                'ceid': f"{search_config.get('gl', 'US')}:{search_config.get('hl', 'en').split('-')[0]}"
            }
           
            if page > 0:
                search_params['start'] = page * 10

            search_url = f"{self.base_url}/search?{urlencode(search_params)}"
            print(f"Scraping page {page + 1}: {search_url}")

            try:
                await self.page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                await self.random_delay(1, 2)

                content = await self.page.content()
                articles = await self.parse_rss_xml(content, query, page + 1, timeframe_days)
                all_articles.extend(articles)
               
                print(f"Found {len(articles)} articles on page {page + 1}")
               
                if not articles and page > 0:
                    break
                   
            except Exception as e:
                print(f"Error scraping page {page + 1} for '{query}': {e}")
                break

        return all_articles

    async def parse_rss_xml(self, xml_content, query, page_num, timeframe_days):
        """Parse RSS XML content and extract articles"""
        articles = []
        try:
            xml_content = self.clean_xml_content(xml_content)
            root = ET.fromstring(xml_content)
           
            for item in root.findall('.//item'):
                article_data = await self.extract_article_from_xml(item, query, page_num, timeframe_days)
                if article_data:
                    articles.append(article_data)
                   
        except ET.ParseError as e:
            print(f"XML parsing error: {e}")
            articles = await self.fallback_parse(xml_content, query, page_num, timeframe_days)
        except Exception as e:
            print(f"Error parsing RSS XML: {e}")
           
        return articles

    def clean_xml_content(self, content):
        """Clean XML content before parsing"""
        content = content.replace('\x00', '')
        if not content.startswith('<?xml'):
            content = '<?xml version="1.0" encoding="UTF-8"?>' + content
        return content

    async def extract_article_from_xml(self, item_element, query, page_num, timeframe_days):
        """Extract article data from XML item element"""
        try:
            title_elem = item_element.find('title')
            title = title_elem.text if title_elem is not None else ""
           
            link_elem = item_element.find('link')
            url = link_elem.text if link_elem is not None else ""
           
            source_elem = item_element.find('source')
            source = source_elem.text if source_elem is not None else ""
           
            pub_date_elem = item_element.find('pubDate')
            pub_date = pub_date_elem.text if pub_date_elem is not None else ""
           
            desc_elem = item_element.find('description')
            raw_description = desc_elem.text if desc_elem is not None else ""
            clean_description = self.clean_html(raw_description)
           
            clean_title = self.clean_text(title)
            clean_source = self.clean_text(source)
            clean_date = self.clean_date(pub_date)

            # Filter for last N days
            if clean_date and not self.is_within_last_N_days(clean_date, timeframe_days):
                return None
           
            if not clean_title:
                return None
           
            return {
                'query': query,
                'page': page_num,
                'title': clean_title,
                'source': clean_source,
                'url': url,
                'publication_date': clean_date,
                'description': clean_description,
                'scraped_at': datetime.now().isoformat()
            }
           
        except Exception as e:
            print(f"Error extracting article from XML: {e}")
            return None

    def clean_html(self, text):
        """Remove HTML tags from text"""
        if not text:
            return ""
        clean = re.sub('<[^<]+?>', '', text)
        clean = unquote(clean)
        clean = ' '.join(clean.split())
        return clean.strip()

    def clean_date(self, date_string):
        """Clean and validate date string"""
        if not date_string:
            return ""
        date_string = ' '.join(date_string.split())
        try:
            current_year = datetime.now().year
            if str(current_year + 2) in date_string:
                return "Invalid date"
        except:
            pass
        return date_string

    def clean_text(self, text):
        """Clean and normalize text, decoding any literal Unicode escapes and HTML entities"""
        if not text:
            return ""
        
        import html
        import re

        # Decode literal unicode escape sequences like \u002d or \u002D
        try:
            def decode_match(match):
                return chr(int(match.group(1), 16))
            text = re.sub(r'\\u([0-9a-fA-F]{4})', decode_match, text)
        except Exception as e:
            print(f"Scraper: Unicode escape decode error: {e}")

        # Decode HTML entities (e.g. &amp;, &quot;, &#39;)
        text = html.unescape(text)

        return ' '.join(text.split()).strip()

    async def fallback_parse(self, content, query, page_num, timeframe_days):
        """Fallback parsing method if XML parsing fails"""
        articles = []
        try:
            lines = content.split('\n')
            current_article = {}
           
            for line in lines:
                line = line.strip()
                if '<item>' in line:
                    current_article = {}
                elif '</item>' in line and current_article:
                    if 'title' in current_article:
                        pub_date_val = current_article.get('pubDate', '')
                        if not pub_date_val or self.is_within_last_N_days(pub_date_val, timeframe_days):
                            articles.append({
                                'query': query,
                                'page': page_num,
                                'title': current_article.get('title', ''),
                                'source': current_article.get('source', ''),
                                'url': current_article.get('link', ''),
                                'publication_date': pub_date_val,
                                'description': self.clean_html(current_article.get('description', '')),
                                'scraped_at': datetime.now().isoformat()
                            })
                    current_article = {}
                elif '<title>' in line and '</title>' in line:
                    current_article['title'] = self.clean_text(
                        line.replace('<title>', '').replace('</title>', '')
                    )
                elif '<link>' in line and '</link>' in line:
                    current_article['link'] = self.clean_text(
                        line.replace('<link>', '').replace('</link>', '')
                    )
                elif '<source>' in line and '</source>' in line:
                    current_article['source'] = self.clean_text(
                        line.replace('<source>', '').replace('</source>', '')
                    )
                elif '<pubDate>' in line and '</pubDate>' in line:
                    current_article['pubDate'] = self.clean_text(
                        line.replace('<pubDate>', '').replace('</pubDate>', '')
                    )
                elif '<description>' in line and '</description>' in line:
                    current_article['description'] = line.replace('<description>', '').replace('</description>', '')
                   
        except Exception as e:
            print(f"Fallback parsing also failed: {e}")
           
        return articles

    async def scrape_queries(self, queries, timeframe_days, proxy_config=None, search_config=None):
        """Scrape news for multiple search queries"""
        all_articles = []
        if search_config is None:
            search_config = {
                'hl': 'en-US',
                'gl': 'US',
                'pagination': 1
            }

        await self.setup_browser(proxy_config)
        try:
            for i, query in enumerate(queries):
                print(f"\nProcessing query {i+1}/{len(queries)}: {query}")
                articles = await self.scrape_news_rss(query, timeframe_days, search_config)
                all_articles.extend(articles)
                print(f"Found {len(articles)} articles for '{query}'")

                if i < len(queries) - 1:
                    delay = random.uniform(2, 5)
                    await asyncio.sleep(delay)
        finally:
            await self.close()

        return all_articles

    async def close(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()
