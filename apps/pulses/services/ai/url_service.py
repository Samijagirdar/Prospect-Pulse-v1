import ipaddress
import logging
import socket
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

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

logger = logging.getLogger(__name__)

def is_safe_public_url(url):
    """
    Validates that a URL uses http/https, uses standard web ports, and does not
    resolve to private, loopback, carrier-grade NAT, or cloud-metadata IP addresses (SSRF defense).
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
            
        # Reject non-standard ports to prevent internal port scanning
        if parsed.port and parsed.port not in (80, 443, 8080, 8443):
            return False

        lower_host = hostname.lower()
        if lower_host in ('localhost', '127.0.0.1', '::1', '0.0.0.0', 'metadata.google.internal'):
            return False

        # Resolve hostname to verify destination IP addresses
        addr_info = socket.getaddrinfo(hostname, None)
        cgnat_net = ipaddress.ip_network('100.64.0.0/10')

        for entry in addr_info:
            ip_str = entry[4][0]
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False

            if isinstance(ip, ipaddress.IPv4Address) and ip in cgnat_net:
                return False

        return True
    except Exception as e:
        logger.warning(f"URL safety check failed for '{url}': {e}")
        return False

def extract_text_from_url(url):
    """
    Extract clean, comprehensive text from a target company or article URL.
    1. Primary: Trafilatura (fast, boilerplate-free extractor)
    2. Modern SPA / Landing Page Fallback: Jina Reader (https://r.jina.ai/<url>)
       When Trafilatura returns sparse text (< 800 chars, common on React/Next.js landing pages),
       Jina Reader provides complete rendered markdown of products, features, and pricing.
    3. Stealth Fallback: curl_cffi with Chrome TLS fingerprint spoofing.
    4. Resilient Fallback: Standard requests (with allow_redirects=True) + BeautifulSoup.
    """
    if not is_safe_public_url(url):
        logger.warning(f"Blocked potential SSRF or invalid URL request: {url}")
        return ""

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    trafilatura_text = ""

    # 1. Primary: Trafilatura
    if trafilatura:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                extracted = trafilatura.extract(downloaded, include_links=False, include_comments=False)
                if extracted and len(extracted.strip()) > 800:
                    return extracted.strip()
                elif extracted:
                    trafilatura_text = extracted.strip()
        except Exception as e:
            logger.warning(f"Trafilatura fetch failed for {url}: {e}")

    # 2. Modern Landing Page Reader: Jina Reader (free LLM markdown extractor for JS/Next.js/React apps)
    try:
        jina_url = f"https://r.jina.ai/{url}"
        jina_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'text/plain, text/markdown, */*'
        }
        jina_resp = requests.get(jina_url, headers=jina_headers, timeout=12)
        if jina_resp.status_code == 200 and len(jina_resp.text.strip()) > 400:
            logger.info(f"Successfully extracted rich markdown via Jina Reader ({len(jina_resp.text)} chars) for {url}")
            return jina_resp.text.strip()
    except Exception as jina_err:
        logger.warning(f"Jina Reader fetch failed for {url}: {jina_err}")

    # 3. Stealth Fallback: curl_cffi (Chrome TLS spoofing) + Trafilatura
    if CURL_CFFI_AVAILABLE and trafilatura:
        try:
            resp = curl_requests.get(url, impersonate="chrome", timeout=12, headers=headers)
            if resp.status_code == 200 and resp.text:
                extracted = trafilatura.extract(resp.text, include_links=False, include_comments=False)
                if extracted and len(extracted.strip()) > 800:
                    return extracted.strip()
                elif extracted and len(extracted.strip()) > len(trafilatura_text):
                    trafilatura_text = extracted.strip()
        except Exception as c_err:
            logger.warning(f"curl_cffi fetch failed for {url}: {c_err}")

    # 4. Fallback: Standard requests (following redirects) + BeautifulSoup
    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for element in soup(["script", "style", "nav", "footer", "svg"]):
            element.decompose()
            
        text = soup.get_text(separator=' ')
        clean_text = ' '.join(text.split())
        
        # If BeautifulSoup yielded significantly more content than sparse trafilatura, prefer it
        if len(clean_text) > len(trafilatura_text):
            return clean_text
    except Exception as e:
        logger.error(f"Error fetching URL {url} via BeautifulSoup: {e}")

    return trafilatura_text

