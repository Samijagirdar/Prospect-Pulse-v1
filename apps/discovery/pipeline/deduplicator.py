import os
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
import re
import math
import difflib
import importlib
from datetime import datetime, timedelta
from django.utils import timezone

# Attempt imports for Layer 3 local embedding/similarity
try:
    sentence_transformers = importlib.import_module("sentence_transformers")
    SentenceTransformer = sentence_transformers.SentenceTransformer
    import numpy as np
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SentenceTransformer = None
    SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from .relevance_engine import RelevanceEngine
from . import llm_relevance_judge
from apps.discovery.models import Article

class Deduplicator:
    def __init__(self, time_window_days=14):
        self.time_window_days = time_window_days
        self.model = None
        self.tfidf_vectorizer = None
        self.stop_proper = {
            'this', 'that', 'with', 'from', 'then', 'there', 'their', 'they', 'what', 'when', 'where', 'which', 
            'other', 'first', 'today', 'years', 'month', 'great', 'about', 'some', 'news', 'projects', 'firm',
            'vice', 'president', 'business', 'future', 'industry', 'operations', 'platform', 'edge', 'cloud',
            'path', 'execution', 'greater', 'digital', 'industrial', 'autonomous', 'resilient', 'steel',
            'smart', 'connected', 'elevates', 'elevated', 'lead', 'join', 'forces', 'partner', 'come',
            'together', 'explore', 'signs', 'power', 'drive', 'powering', 'announces', 'selects', 'introduces',
            'tackles', 'shows', 'bets', 'running', 'today', 'tomorrow', 'yesterday', 'global', 'local', 'national',
            'world', 'market', 'report', 'trends', 'updates', 'update', 'latest', 'new', 'old', 'high', 'low',
            'chief', 'executive', 'officer', 'director', 'manager', 'head', 'lead', 'leader', 'leading',
            'firm', 'firms', 'strategic', 'agreement', 'advance', 'deployment', 'partner', 'partners',
            'partnership', 'partnerships', 'alliance', 'alliances', 'venture', 'ventures', 'joint',
            'collaboration', 'collaborations', 'reimagine', 'digitalpulse', 'smestreet', 'outlookbusiness',
            'gasworld', 'times', 'projects', 'acquire', 'acquires', 'acquiring', 'acquisitions', 'acquisition',
            'expand', 'expands', 'powered', 'revenue', 'intelligence', 'buying', 'buys', 'buyer', 'tools', 'tool',
            'bring', 'bringing', 'adds', 'adding', 'boost', 'boosts', 'accelerate', 'launches', 'launch',
            'reimagin', 'reimagines', 'hiring', 'hired', 'hire', 'hires', 'appoints', 'appointed', 'appoint',
            'naming', 'named', 'name', 'names', 'joins', 'force', 'reaches', 'reach', 'raising', 'raises',
            'raise', 'raised', 'funding', 'fund', 'funds', 'million', 'billion', 'startup', 'startups',
            'turn', 'customer', 'conversations', 'conversation', 'action', 'capabilities', 'capability',
            'service', 'services', 'solution', 'solutions', 'product', 'products', 'application', 'applications',
            'system', 'systems', 'integration', 'integrations', 'software', 'softwares', 'agent', 'agents',
            'into', 'onto', 'from', 'with', 'under', 'over', 'through', 'about', 'between', 'during', 'before',
            'after', 'above', 'below', 'down', 'upto', 'than', 'then', 'also', 'and', 'the', 'for', 'but',
            'yet', 'nor', 'out', 'off', 'sales', 'automation', 'round', 'rounds', 'pre', 'series', 'seed', 'crore',
            'lakh', 'lakhs', 'crores', 'funding', 'fundraise', 'fundraises', 'funded', 'invests', 'invest',
        }

        # Initialize local SentenceTransformer if available
        if SENTENCE_TRANSFORMERS_AVAILABLE and SentenceTransformer:
            try:
                self.model = SentenceTransformer('all-MiniLM-L6-v2')
            except Exception as e:
                print(f"Deduplicator: SentenceTransformer init warning: {e}")
                self.model = None

        if not self.model and SKLEARN_AVAILABLE:
            try:
                self.tfidf_vectorizer = TfidfVectorizer(
                    stop_words=list(ENGLISH_STOP_WORDS) if 'ENGLISH_STOP_WORDS' in globals() else 'english',
                    max_features=5000
                )
            except Exception as e:
                print(f"Deduplicator: TF-IDF vectorizer setup warning: {e}")
                self.tfidf_vectorizer = None

    def get_recent_articles(self, pulse, exclude_id=None):
        """Query unique articles published in the last time_window_days for this pulse"""
        cutoff_date = timezone.now() - timedelta(days=self.time_window_days)
        qs = Article.objects.filter(pulse=pulse, is_duplicate=False, scraped_at__gte=cutoff_date)
        if exclude_id:
            qs = qs.exclude(id=exclude_id)
        
        res = []
        for art in qs:
            res.append({
                'id': art.id,
                'title': art.title,
                'url': art.url,
                'description': art.description,
                'embedding': art.embedding,
                'publication_date': art.publication_date,
                'scraped_at': art.scraped_at.isoformat() if art.scraped_at else None,
                'is_relevant': art.is_relevant,
                'relevance_score': art.relevance_score,
                'buying_signal': art.buying_signal,
                'relevance_tier': art.relevance_tier,
                'relevance_reason': art.relevance_reason
            })
        return res

    def check_entity_time_overlap(self, art1, art2):
        """
        Check if two articles discuss the same proper entities within a short timeframe.
        Returns (is_dup, reason)
        """
        def parse_date(date_str):
            if not date_str:
                return datetime.now()
            for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%a, %d %b %Y %H:%M:%S GMT"):
                try:
                    return datetime.strptime(date_str.split('.')[0], fmt)
                except ValueError:
                    continue
            return datetime.now()
            
        d1 = parse_date(art1.get('publication_date') or art1.get('scraped_at'))
        d2 = parse_date(art2.get('publication_date') or art2.get('scraped_at'))
        
        # Temporal window check: 14 days
        if abs((d1 - d2).days) > 14:
            return False, None
            
        def get_proper_nouns(title, desc):
            text = f"{title} {desc}"
            words = set(re.findall(r'\b[A-Z][a-zA-Z0-9]{1,}\b', text))
            return {w.lower() for w in words if w.lower() not in self.stop_proper}
            
        p1 = get_proper_nouns(self.clean_rss_text(art1['title']), self.clean_rss_text(art1.get('description', '')))
        p2 = get_proper_nouns(self.clean_rss_text(art2['title']), self.clean_rss_text(art2.get('description', '')))
        
        if not p1 or not p2:
            return False, None
            
        intersection = p1 & p2
        if len(intersection) < 2:
            return False, None
            
        smaller_set_size = min(len(p1), len(p2))
        ratio = len(intersection) / smaller_set_size
        
        if ratio >= 0.50:
            return True, f"Layer 2.5: Entity Overlap ({int(ratio * 100)}%) inside 14-day window"
            
        return False, None

    def check_new_facts_local(self, original_desc, new_desc):
        """
        Offline check for new facts by comparing numbers, key metrics, and focal entities.
        """
        if not original_desc or not new_desc:
            return False, None
            
        def extract_metrics(text):
            numbers = set(re.findall(r'\b\d+(?:\.\d+)?[a-zA-Z%]*\b', text))
            currencies = set(re.findall(r'\$\d+(?:\.\d+)?[a-zA-Z%]*\b', text))
            return numbers | currencies
            
        orig_metrics = extract_metrics(original_desc)
        new_metrics = extract_metrics(new_desc)
        metrics_diff = new_metrics - orig_metrics
        
        def get_focal_entities(text):
            words = set(re.findall(r'\b[A-Z][a-zA-Z0-9]{1,}\b', text))
            return {w.lower(): w for w in words if w.lower() not in self.stop_proper}
            
        orig_entities = get_focal_entities(original_desc)
        new_entities = get_focal_entities(new_desc)
        entities_diff_keys = new_entities.keys() - orig_entities.keys()
        entities_diff = {new_entities[k] for k in entities_diff_keys}
        
        diff = metrics_diff | entities_diff
        
        if diff:
            delta_summary = f"New facts/entities detected: {', '.join(list(diff)[:5])}"
            return True, delta_summary
            
        return False, None

    def calculate_pure_python_cosine(self, text1, text2):
        """Pure python fallback to calculate cosine similarity between two texts based on term frequency"""
        def get_word_freq(text):
            words = re.findall(r'\w+', text.lower())
            freq = {}
            for w in words:
                if len(w) > 2:
                    freq[w] = freq.get(w, 0) + 1
            return freq

        f1 = get_word_freq(text1)
        f2 = get_word_freq(text2)

        intersection = set(f1.keys()) & set(f2.keys())
        if not intersection:
            return 0.0
            
        numerator = sum([f1[w] * f2[w] for w in intersection])

        sum1 = sum([f1[w]**2 for w in f1.keys()])
        sum2 = sum([f2[w]**2 for w in f2.keys()])
        denominator = math.sqrt(sum1) * math.sqrt(sum2)

        if not denominator:
            return 0.0
        return float(numerator) / denominator

    def clean_rss_text(self, text):
        """Strip common Google News RSS suffixes like ' - Source' or '  Source'"""
        if not text:
            return ""
        cleaned = text.replace('&nbsp;', ' ')
        cleaned = re.sub(r'(?:\s+[-|]\s+|\s{2,})[^-|]+$', '', cleaned)
        return cleaned.strip()

    def process_article(self, article_data, pulse):
        """
        Process an incoming article through the 3-layer deduplication engine FIRST.
        Only unique articles (is_duplicate == 0) trigger LLM API classification.
        For duplicate articles, relevance metadata is copied from the matched original.
        """
        title = article_data['title']
        url = article_data['url']
        desc = article_data.get('description', '')
        
        cleaned_title = self.clean_rss_text(title)
        cleaned_desc = self.clean_rss_text(desc)

        article_data['is_duplicate'] = False
        article_data['matched_original_id'] = None
        article_data['duplicate_reason'] = None
        article_data['delta_summary'] = None
        article_data['embedding'] = None

        query_focus = pulse._get_profile_field('target_account_focus', '')

        # Helper to copy relevance fields from original duplicate
        def copy_relevance_from_original(original_dict):
            article_data['is_relevant'] = original_dict.get('is_relevant', True)
            article_data['relevance_score'] = original_dict.get('relevance_score', 0)
            article_data['buying_signal'] = original_dict.get('buying_signal')
            article_data['relevance_tier'] = original_dict.get('relevance_tier', 'actionable')
            article_data['relevance_reason'] = original_dict.get('relevance_reason') or "Copied from duplicate original"
            article_data['prompt_tokens'] = 0
            article_data['completion_tokens'] = 0
            article_data['total_tokens'] = 0

        # Layer 1: URL match check
        existing_matches = Article.objects.filter(pulse=pulse, url=url)
        if article_data.get('id'):
            existing_matches = existing_matches.exclude(id=article_data['id'])
        
        match = existing_matches.first()
        if match:
            article_data['is_duplicate'] = True
            article_data['matched_original_id'] = match.id
            article_data['duplicate_reason'] = "Layer 1: URL Hash Match"
            copy_relevance_from_original({
                'is_relevant': match.is_relevant,
                'relevance_score': match.relevance_score,
                'buying_signal': match.buying_signal,
                'relevance_tier': match.relevance_tier,
                'relevance_reason': match.relevance_reason
            })
            return article_data
            
        recent_articles = self.get_recent_articles(pulse, exclude_id=article_data.get('id'))
        if not recent_articles:
            if self.model:
                try:
                    emb = self.model.encode(cleaned_desc)
                    article_data['embedding'] = emb.tobytes()
                except Exception:
                    pass
        else:
            # Layer 2: Title Similarity Check
            for existing in recent_articles:
                existing_cleaned_title = self.clean_rss_text(existing['title'])
                ratio = difflib.SequenceMatcher(None, cleaned_title.lower(), existing_cleaned_title.lower()).ratio()
                if ratio >= 0.85:
                    article_data['is_duplicate'] = True
                    article_data['matched_original_id'] = existing['id']
                    article_data['duplicate_reason'] = f"Layer 2: Title Similarity ({int(ratio * 100)}%)"
                    copy_relevance_from_original(existing)
                    return article_data

            # Layer 2.5: Entity Time-Window Overlap Check
            for existing in recent_articles:
                is_dup, reason = self.check_entity_time_overlap(article_data, existing)
                if is_dup:
                    article_data['is_duplicate'] = True
                    article_data['matched_original_id'] = existing['id']
                    article_data['duplicate_reason'] = reason
                    copy_relevance_from_original(existing)
                    return article_data

            # Layer 3: Semantic Cosine Similarity Check
            if not article_data['is_duplicate']:
                gate_recent_articles = recent_articles
                max_similarity = 0.0
                best_match = None

                if self.model:
                    try:
                        new_emb = self.model.encode(cleaned_desc)
                        article_data['embedding'] = new_emb.tobytes()
                        if gate_recent_articles:
                            for existing in gate_recent_articles:
                                if existing.get('embedding'):
                                    est_emb = np.frombuffer(existing['embedding'], dtype=np.float32)
                                    dot = np.dot(new_emb, est_emb)
                                    norm_new = np.linalg.norm(new_emb)
                                    norm_est = np.linalg.norm(est_emb)
                                    sim = dot / (norm_new * norm_est) if norm_new and norm_est else 0.0
                                    if sim > max_similarity:
                                        max_similarity = sim
                                        best_match = existing
                    except Exception as e:
                        print(f"Deduplicator: Error in sentence-transformer cosine check: {e}")
                        max_similarity = 0.0
                elif self.tfidf_vectorizer and gate_recent_articles:
                    try:
                        corpus = [self.clean_rss_text(existing['description']) for existing in gate_recent_articles] + [cleaned_desc]
                        tfidf_matrix = self.tfidf_vectorizer.fit_transform(corpus)
                        similarities = cosine_similarity(tfidf_matrix[-1], tfidf_matrix[:-1])[0]
                        for idx, sim in enumerate(similarities):
                            if sim > max_similarity:
                                max_similarity = sim
                                best_match = gate_recent_articles[idx]
                    except Exception as e:
                        print(f"Deduplicator: Error in TF-IDF cosine check: {e}")
                        max_similarity = 0.0
                elif gate_recent_articles:
                    for existing in gate_recent_articles:
                        existing_cleaned_desc = self.clean_rss_text(existing['description'])
                        sim = self.calculate_pure_python_cosine(cleaned_desc, existing_cleaned_desc)
                        if sim > max_similarity:
                            max_similarity = sim
                            best_match = existing

                if max_similarity >= 0.80:
                    article_data['is_duplicate'] = True
                    article_data['matched_original_id'] = best_match['id']
                    article_data['duplicate_reason'] = f"Layer 3: Semantic Match ({int(max_similarity * 100)}%)"
                    
                    has_delta, delta_summary = self.check_new_facts_local(best_match['description'], desc)
                    if has_delta:
                        article_data['is_duplicate'] = False
                        article_data['delta_summary'] = delta_summary
                    else:
                        copy_relevance_from_original(best_match)
                        return article_data

        # Run LLM classification for unique articles & updates
        try:
            res = llm_relevance_judge.classify_article(
                title=title,
                description=desc,
                query_focus=query_focus,
                query_keyword=article_data.get('query'),
                source=article_data.get('source', ''),
                pulse=pulse
            )
            article_data['is_relevant'] = bool(res.get('is_relevant', True))
            article_data['relevance_score'] = res.get('relevance_score', 0)
            article_data['buying_signal'] = res.get('buying_signal')
            article_data['relevance_tier'] = res.get('relevance_tier', 'actionable')
            article_data['relevance_reason'] = res.get('reason', '')
            article_data['prompt_tokens'] = res.get('prompt_tokens', 0)
            article_data['completion_tokens'] = res.get('completion_tokens', 0)
            article_data['total_tokens'] = res.get('total_tokens', 0)
        except Exception as e:
            print(f"LLM Classification failed: {e}. Falling back to regex engine.")
            fallback = RelevanceEngine()
            is_rel, score, signal, tier = fallback.calculate_relevance_score(
                title, desc, query_focus, article_data.get('query'), article_data.get('source', '')
            )
            article_data['is_relevant'] = bool(is_rel)
            article_data['relevance_score'] = score
            article_data['buying_signal'] = signal
            article_data['relevance_tier'] = tier
            article_data['relevance_reason'] = "Fallback regex match"
            article_data['prompt_tokens'] = 0
            article_data['completion_tokens'] = 0
            article_data['total_tokens'] = 0

        return article_data
