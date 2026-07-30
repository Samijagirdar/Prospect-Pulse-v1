import re

class RelevanceEngine:
    """
    Lightweight, minimal keyword-based fallback engine.
    Used only when the primary LLM-based API is unreachable.
    """
    def __init__(self, model=None):
        self.model = model
        self.domain_terms = ["data", "cloud", "ai", "analytics", "software", "infrastructure", "lakehouse", "warehouse"]
        self.buying_terms = ["migration", "launches", "acquires", "acquisition", "funding", "raises", "partners", "partnership", "modernize"]
        self.blacklist = ["career", "guide", "tutorial", "course", "school", "student", "opinion"]

    def calculate_relevance_score(self, title, description, query_focus, query_keyword, source):
        text = f"{title or ''} {description or ''}".lower()
        
        # Check simple word occurrences
        has_domain = any(t in text for t in self.domain_terms)
        has_buying = any(t in text for t in self.buying_terms)
        has_blacklist = any(t in text for t in self.blacklist)
        
        is_relevant = 1 if (has_domain and has_buying and not has_blacklist) else 0
        score = 65 if is_relevant else 15
        signal = "Industry Intelligence" if is_relevant else None
        tier = "actionable" if is_relevant else "noise"
        
        return is_relevant, score, signal, tier
