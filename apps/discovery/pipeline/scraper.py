import asyncio
import email.utils
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, unquote
from datetime import datetime, timedelta
import random
import re

import httpx
try:
    import trafilatura
except ImportError:
    trafilatura = None

try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    curl_requests = None
    CURL_CFFI_AVAILABLE = False


class GoogleNewsScraper:
    def __init__(self):
        self.base_url = "https://news.google.com/rss"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

    @staticmethod
    async def _check_redirect_safety(response):
        if response.is_redirect and 'location' in response.headers:
            from urllib.parse import urljoin
            from apps.pulses.services.ai.url_service import is_safe_public_url
            target = urljoin(str(response.url), response.headers['location'])
            if not is_safe_public_url(target):
                raise httpx.RequestError(f"Blocked SSRF redirect to unsafe target: {target}")

    async def random_delay(self, min_seconds=0.5, max_seconds=1.5):
        """Polite random delay between external requests"""
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
        """
        Scrape news from Google RSS feed using fast HTTPX as primary,
        falling back to curl_cffi Chrome TLS impersonation if blocked.
        """
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

            content = None

            # --- TIER 1: FAST HTTPX FETCH ---
            try:
                rss_headers = {
                    'User-Agent': self.headers['User-Agent'],
                    'Accept': 'application/rss+xml, text/xml, */*'
                }
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=12.0,
                    headers=rss_headers,
                    event_hooks={'response': [self._check_redirect_safety]}
                ) as client:
                    resp = await client.get(search_url)
                    if resp.status_code == 200 and resp.text:
                        content = resp.text
                        print(f"Fast HTTPX fetch succeeded for page {page + 1} ({len(content)} bytes)")
            except Exception as httpx_err:
                print(f"Fast HTTPX fetch failed or blocked: {httpx_err}")

            # --- TIER 2: STEALTH CURL_CFFI CHROME IMPERSONATION ---
            if not content and CURL_CFFI_AVAILABLE:
                try:
                    loop = asyncio.get_running_loop()
                    def _curl_get():
                        return curl_requests.get(search_url, impersonate="chrome", timeout=15)
                    
                    resp = await loop.run_in_executor(None, _curl_get)
                    if resp.status_code == 200 and resp.text:
                        content = resp.text
                        print(f"curl_cffi stealth fetch succeeded for page {page + 1}")
                except Exception as c_err:
                    print(f"curl_cffi stealth fetch failed for '{query}': {c_err}")

            if content:
                articles = await self.parse_rss_xml(content, query, page + 1, timeframe_days)
                all_articles.extend(articles)
                print(f"Found {len(articles)} articles on page {page + 1}")
                
                if not articles and page > 0:
                    break

        return all_articles

    async def extract_article_content(self, url):
        """
        Extract full main text of an article using a 100% free, 3-tier cascade:
        Tier 1 (Main): Trafilatura + HTTPX (Fastest, 100ms, removes boilerplate/nav/footer)
        Tier 2 (Stealth): curl_cffi + Trafilatura (Chrome TLS spoofing, bypasses Cloudflare/403)
        Tier 3 (Cloud JS): Jina Reader API (Free cloud proxy rendering dynamic JavaScript to markdown)
        """
        if not url:
            return ""

        # SSRF Defense: Block requests to localhost, loopback, private networks, and cloud metadata
        try:
            from apps.pulses.services.ai.url_service import is_safe_public_url
            if not is_safe_public_url(url):
                print(f"[Security] Blocked potential SSRF attempt to non-public/private target: {url}")
                return ""
        except Exception as ssrf_err:
            print(f"[Security] URL validation error for {url}: {ssrf_err}")

        # 1. TIER 1: TRAFILATURA + HTTPX (PRIMARY MAIN ENGINE)
        if trafilatura:
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=10.0,
                    headers=self.headers,
                    event_hooks={'response': [self._check_redirect_safety]}
                ) as client:
                    res = await client.get(url)
                    if res.status_code == 200 and res.text:
                        extracted_text = trafilatura.extract(res.text, include_links=False, include_comments=False)
                        if extracted_text and len(extracted_text.strip()) > 100:
                            return extracted_text.strip()
            except Exception as e:
                print(f"[Tier 1 Trafilatura] Direct fetch failed for {url}: {e}")

        # 2. TIER 2: CURL_CFFI (STEALTH CHROME TLS SPOOFING) + TRAFILATURA
        if CURL_CFFI_AVAILABLE and trafilatura:
            try:
                loop = asyncio.get_running_loop()
                def _curl_fetch():
                    return curl_requests.get(url, impersonate="chrome", timeout=12, headers=self.headers)
                
                resp = await loop.run_in_executor(None, _curl_fetch)
                if resp.status_code == 200 and resp.text:
                    extracted_text = trafilatura.extract(resp.text, include_links=False, include_comments=False)
                    if extracted_text and len(extracted_text.strip()) > 100:
                        return extracted_text.strip()
            except Exception as curl_err:
                print(f"[Tier 2 curl_cffi] Stealth fetch failed for {url}: {curl_err}")

        # 3. TIER 3: JINA READER API (100% FREE CLOUD JAVASCRIPT & MARKDOWN PROXY)
        try:
            jina_url = f"https://r.jina.ai/{url}"
            async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
                res = await client.get(jina_url)
                if res.status_code == 200 and res.text:
                    cleaned_markdown = self.clean_text(res.text)
                    if len(cleaned_markdown) > 100:
                        return cleaned_markdown
        except Exception as jina_err:
            print(f"[Tier 3 Jina Reader] Free cloud fallback failed for {url}: {jina_err}")

        return ""

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

        try:
            for i, query in enumerate(queries):
                print(f"\nProcessing query {i+1}/{len(queries)}: {query}")
                articles = await self.scrape_news_rss(query, timeframe_days, search_config)
                all_articles.extend(articles)
                print(f"Found {len(articles)} articles for '{query}'")

                if i < len(queries) - 1:
                    await asyncio.sleep(0.5)
        finally:
            await self.close()

        return all_articles

    async def close(self):
        """Cleanup resources if needed (backward compatibility)"""
        pass
