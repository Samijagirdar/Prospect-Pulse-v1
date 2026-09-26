import os
import logging
import httpx

logger = logging.getLogger(__name__)

class DisburseClient:
    """
    API client for disburse.dev - APAC and Global B2B lead discovery & contact data engine.
    Docs: https://disburse.dev/docs
    """
    BASE_URL = "https://api.disburse.dev/v1"

    def __init__(self, api_key=None):
        if not api_key:
            try:
                from django.conf import settings
                api_key = getattr(settings, "DISBURSE_API_KEY", None)
            except Exception:
                pass
        raw_key = api_key or os.getenv("DISBURSE_API_KEY") or ""
        self.api_key = raw_key.strip().strip('"\'')

    @property
    def is_configured(self):
        return bool(self.api_key and len(self.api_key) > 5)

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def search_people(self, query=None, filters=None, limit=5, count=None):
        """
        Query Disburse for people / decision makers.
        Accepts natural language 'query' or structured 'filters'.
        """
        if not self.is_configured:
            logger.warning("[Disburse] DISBURSE_API_KEY is not configured in environment.")
            return []

        payload = {}
        if query:
            payload["query"] = query
        elif filters:
            payload["filters"] = filters

        if count:
            payload["count"] = count
        else:
            payload["limit"] = limit

        url = f"{self.BASE_URL}/search/people"

        try:
            with httpx.Client(timeout=25.0) as client:
                resp = client.post(url, headers=self._get_headers(), json=payload)
                
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    logger.info(f"[Disburse] Successfully returned {len(results)} people (Total matched: {data.get('total', 0)}).")
                    return results
                elif resp.status_code == 401:
                    logger.error("[Disburse] Authentication error: Invalid DISBURSE_API_KEY.")
                    return []
                elif resp.status_code == 402:
                    logger.error("[Disburse] Insufficient credits: Please top up your Disburse account.")
                    return []
                else:
                    logger.error(f"[Disburse] API error {resp.status_code}: {resp.text[:300]}")
                    return []
        except Exception as e:
            logger.error(f"[Disburse] Network error connecting to disburse.dev: {e}")
            return []

    def search_companies(self, query=None, filters=None, limit=5):
        """
        Query Disburse for companies matching industry, geography, or text.
        """
        if not self.is_configured:
            logger.warning("[Disburse] DISBURSE_API_KEY is not configured in environment.")
            return []

        payload = {}
        if query:
            payload["query"] = query
        elif filters:
            payload["filters"] = filters

        payload["limit"] = limit
        url = f"{self.BASE_URL}/search/companies"

        try:
            with httpx.Client(timeout=25.0) as client:
                resp = client.post(url, headers=self._get_headers(), json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("results", [])
                else:
                    logger.error(f"[Disburse] Companies API error {resp.status_code}: {resp.text[:300]}")
                    return []
        except Exception as e:
            logger.error(f"[Disburse] Network error connecting to disburse.dev: {e}")
            return []

    def search_leads_for_company(self, company_name, personas=None, country=None, limit=3):
        """
        Specialized helper to find decision-makers at a specific target company.
        Constructs natural language or structured search.
        """
        if not company_name or not company_name.strip():
            return []

        comp_clean = company_name.strip()
        personas_list = personas or ["CEO", "C-suite", "VP", "Director", "Head of Engineering", "Head of Operations"]
        
        # Formulate query: e.g. "CISO, VP Engineering, IT Director at Acme Corp"
        if isinstance(personas_list, list) and len(personas_list) > 0:
            titles_str = ", ".join(personas_list[:4])
            query = f"{titles_str} at {comp_clean}"
        else:
            query = f"Decision makers and executives at {comp_clean}"

        if country:
            query += f" in {country}"

        logger.info(f"[Disburse] Searching leads for company '{comp_clean}' with query: '{query}'")
        return self.search_people(query=query, limit=limit)
