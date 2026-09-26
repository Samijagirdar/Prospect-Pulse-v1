import os
import json
import re
import numpy as np

# Safe import of Google GenAI SDK
try:
    from google import genai as google_genai
    from google.genai import types as genai_types
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    google_genai = None
    genai_types = None
    GOOGLE_GENAI_AVAILABLE = False

# Safe import of SentenceTransformer
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SentenceTransformer = None
    SENTENCE_TRANSFORMERS_AVAILABLE = False

# Force transformers to run in local/offline mode
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"

# Initialize SentenceTransformer for cheap local pre-filtering
try:
    if SentenceTransformer:
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    else:
        embedding_model = None
except Exception as e:
    print(f"Warning: Failed to load local SentenceTransformer: {e}")
    embedding_model = None


def pre_filter_check(text, target_focus):
    """
    Cheap pre-filter check:
    Compute cosine similarity between article text and target focus.
    Returns: (passes_pre_filter: bool, similarity_score: float)
    """
    if not embedding_model or not target_focus or not text:
        return True, 0.5  # Bypassed if model or inputs missing

    try:
        focus_emb = embedding_model.encode(target_focus, show_progress_bar=False)
        text_emb = embedding_model.encode(text, show_progress_bar=False)
        dot = np.dot(focus_emb, text_emb)
        norm_focus = np.linalg.norm(focus_emb)
        norm_text = np.linalg.norm(text_emb)
        similarity = dot / (norm_focus * norm_text) if norm_focus and norm_text else 0.0

        # Threshold set to very loose (0.15) to catch obvious spam/junk
        return (similarity >= 0.15), float(similarity)
    except Exception as e:
        print(f"Pre-filter exception: {e}")
        return True, 0.5


# Create the client ONCE at module load, not per-call
_client = None

def _get_client():
    global _client
    if _client is not None:
        return _client
    if not GOOGLE_GENAI_AVAILABLE:
        raise ImportError("google-genai package is not installed.")
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Google API key is not configured. Add GOOGLE_API_KEY to your environment.")
    _client = google_genai.Client(api_key=api_key)
    return _client


def extract_json_by_matching_braces(text):
    first_brace = text.find('{')
    if first_brace == -1:
        return text
        
    brace_count = 0
    in_string = False
    escape = False
    
    for i in range(first_brace, len(text)):
        char = text[i]
        
        if escape:
            escape = False
            continue
            
        if char == '\\':
            escape = True
            continue
            
        if char == '"':
            in_string = not in_string
            continue
            
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return text[first_brace:i+1]
                    
    return text[first_brace:]

def repair_truncated_json(text):
    """
    Robustly repairs truncated or malformed JSON strings from LLMs.
    Closes open quotes, strips trailing commas/incomplete keys, and closes open braces/brackets.
    """
    if not text:
        return "{}"
        
    cleaned = text.strip()
    
    # Find first '{'
    first_brace = cleaned.find('{')
    if first_brace == -1:
        return "{}"
    
    candidate = cleaned[first_brace:]
    
    # State tracking
    stack = []
    in_string = False
    escape = False
    i = 0
    limit = len(candidate)
    
    while i < limit:
        char = candidate[i]
        
        if escape:
            escape = False
            i += 1
            continue
            
        if char == '\\':
            escape = True
            i += 1
            continue
            
        if char == '"':
            in_string = not in_string
            i += 1
            continue
            
        if not in_string:
            if char == '{':
                stack.append('{')
            elif char == '[':
                stack.append('[')
            elif char == '}':
                if stack and stack[-1] == '{':
                    stack.pop()
            elif char == ']':
                if stack and stack[-1] == '[':
                    stack.pop()
        i += 1

    # If we ended inside a string, close the quote
    repaired = candidate
    if in_string:
        repaired += '"'
        in_string = False
        
    # Strip any trailing whitespace
    repaired = repaired.strip()
    
    # Loop to strip trailing invalid elements (commas, keys with colons but no values, etc.)
    while True:
        original = repaired
        repaired = re.sub(r',\s*$', '', repaired)
        repaired = re.sub(r'"[^"]*"\s*:\s*$', '', repaired)
        repaired = re.sub(r',\s*$', '', repaired)
        repaired = re.sub(r',\s*"[^"]*"\s*$', '', repaired)
        if repaired == original:
            break
            
    # Rebuild stack to close open brackets/braces accurately
    final_stack = []
    in_str = False
    esc = False
    for c in repaired:
        if esc:
            esc = False
            continue
        if c == '\\':
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if not in_str:
            if c == '{':
                final_stack.append('{')
            elif c == '[':
                final_stack.append('[')
            elif c == '}':
                if final_stack and final_stack[-1] == '{':
                    final_stack.pop()
            elif c == ']':
                if final_stack and final_stack[-1] == '[':
                    final_stack.pop()
                    
    # Close any open structures in reverse order
    for sym in reversed(final_stack):
        if sym == '{':
            repaired += '}'
        elif sym == '[':
            repaired += ']'
            
    return repaired

def clean_and_parse_json(text):
    """
    Robustly parses JSON from LLM text responses, handling markdown code blocks,
    trailing text/commentary, trailing commas, and unescaped strings.
    """
    if not text:
        raise ValueError("Empty response text from LLM")

    cleaned = text.strip()

    # Strip markdown code blocks
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    # 1. Try standard brace matching extraction
    json_candidate = extract_json_by_matching_braces(cleaned)
    try:
        return json.loads(json_candidate)
    except json.JSONDecodeError:
        pass

    # 2. Try trailing comma cleanup
    json_candidate_fixed = re.sub(r',\s*([\}\]])', r'\1', json_candidate)
    try:
        return json.loads(json_candidate_fixed)
    except json.JSONDecodeError:
        pass

    # 3. Try full structural repair (truncation/missing brackets)
    try:
        repaired = repair_truncated_json(cleaned)
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # RegEx field extraction fallback
    category_match = re.search(r'"category"\s*:\s*"([^"]+)"', json_candidate, re.IGNORECASE)
    buying_signal_match = re.search(r'"buying_signal"\s*:\s*("([^"]+)"|null)', json_candidate, re.IGNORECASE)
    score_match = re.search(r'"relevance_score"\s*:\s*(\d+)', json_candidate, re.IGNORECASE)
    reason_match = re.search(r'"reason"\s*:\s*"([^"]+)"', json_candidate, re.IGNORECASE)

    if category_match:
        cat_val = category_match.group(1).strip()
        sig_val = None
        if buying_signal_match:
            raw_sig = buying_signal_match.group(1).strip()
            if raw_sig != "null" and raw_sig != 'null':
                sig_val = raw_sig.strip('"')
        score_val = int(score_match.group(1)) if score_match else 50
        reason_val = reason_match.group(1) if reason_match else "Extracted from LLM response."

        return {
            "category": cat_val,
            "buying_signal": sig_val,
            "relevance_score": score_val,
            "reason": reason_val
        }

    raise ValueError(f"Unable to parse valid JSON from LLM response: {text[:200]}")


def classify_article(title, description, query_focus, query_keyword, source, pulse):
    """
    Main entry point for classifying an article using Gemini LLM.
    Guarantees every article is evaluated by LLM and captures input/output/total token metadata.
    Returns a dict containing classification, scoring, signal, reasoning, and token counts.
    """
    full_text = f"{title or ''} {description or ''}"

    # Log pre-filter similarity for audit, but do not bypass LLM classification
    _, similarity = pre_filter_check(full_text, query_focus)

    # Fetch pulse-scoped buying signal definitions
    buying_signals = pulse.buying_signals_rel.all()
    if buying_signals.exists():
        actionable_signals = [f"- {sig.signal_name} (Category: {sig.category})" for sig in buying_signals]
    else:
        actionable_signals = [
            "- Technology Adoption or Migration: Deploying new software, cloud infrastructure, or security frameworks.",
            "- Leadership Changes: C-suite hires, key executive appointments, or team expansions.",
            "- Business Milestones: Raising funding, expansion into new markets, or launching new offerings."
        ]

    # Always ensure competitive intelligence is recognized as actionable
    actionable_signals.append("- Competitive Intelligence & Market Moves: Direct competitor product launches, strategic partnerships, funding rounds, acquisitions, or commercial expansions by specific named competitor vendors in this space.")
    actionable_text = "\n".join(actionable_signals)

    # Generic noise definitions
    noise_text = """
- Market Research Reports & Industry Overviews: Broad multi-year market projections, CAGR forecasts, syndicated industry research reports, and generic survey roundups without a specific company commercial deployment or product launch.
- Stock Market & Financial Rating Reports: Stock price fluctuations, equity analyst price target changes (e.g. JPMorgan/Morgan Stanley ratings), or earnings call previews without commercial product milestones.
- Socio-Political & Public Sector Policies: Geopolitical news, government treaties, and broad public sector policy discussions without specific enterprise software purchasing.
- Thought Leadership / General Blog Post: Tutorials, opinion pieces, generic threat advisories without concrete commercial company intent or competitive developments.
- Career & Tutorial Guides: Job listings, generic how-to articles, educational coursework.
"""

    target_geography = (getattr(pulse, 'target_geography', None) or "").strip()
    geo_line = f"- Target Geography: {target_geography} (Prioritize signals relevant to this region)" if target_geography else "- Target Geography: Global (no regional restriction)"

    competitors_list = ", ".join(pulse.competitors_list) if hasattr(pulse, 'competitors_list') and pulse.competitors_list else ""
    comp_line = f"- Monitored Competitors in this Space: {competitors_list}" if competitors_list else ""

    prompt = f"""
You are an expert sales and market intelligence relevance classification engine. Your task is to judge whether a scraped news article represents actionable commercial intent, target account expansion, or competitive market movements versus irrelevant noise or non-commercial content.

**ARTICLE DETAILS**:
- Title: {title}
- Description: {description}
- Search query keyword context: {query_keyword}
- Intended focus area: {query_focus}
- Publisher/Source: {source}
{geo_line}
{comp_line}

**CLASSIFICATION CATEGORIES**:
Below are the valid categories. You MUST match the article against these categories:

### Actionable Intelligence & Commercial Intent Signals:
{actionable_text}

### Filtered Noise Categories:
{noise_text}

**INSTRUCTIONS**:
1. Classify the article into either "actionable" or "noise" based on the definitions above.
2. If it is "actionable", match it to the single most relevant signal name from the list. If it is "noise", set "buying_signal" to null.
3. Assign a "relevance_score" (integer between 0 and 100) indicating confidence and relevance quality.
4. Provide a clear, one-sentence "reason" for your choice. Avoid double quotes or newline characters inside the reason sentence.
5. Return ONLY a valid, single JSON object with NO markdown formatting, NO backticks, and NO trailing text outside the JSON object.
Structure:
{{
  "category": "actionable" | "noise",
  "buying_signal": "Name of matched signal" | null,
  "relevance_score": 0-100,
  "reason": "explanation text"
}}
"""

    try:
        client = _get_client()
        primary_model = os.getenv("GEMINI_RELEVANCE_MODEL", "gemini-3.8-flash")
        fallback_model = os.getenv("GEMINI_BACKUP_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.7-flash"))

        
        try:
            response = client.models.generate_content(
                model=primary_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=2048
                )
            )
        except Exception as model_err:
            print(f"Relevance Judge: Primary model {primary_model} failed ({model_err}). Retrying with {fallback_model}...")
            response = client.models.generate_content(
                model=fallback_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=2048
                )
            )

        res_json = clean_and_parse_json(response.text)

        category = res_json.get("category", "noise")
        buying_signal = res_json.get("buying_signal")
        score = int(res_json.get("relevance_score", 0))
        reason = res_json.get("reason", "Classified by LLM.")

        is_relevant = 1 if category == "actionable" else 0

        # Extract token usage metadata
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            prompt_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
            completion_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0
            total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) or (prompt_tokens + completion_tokens)

        print(f"[Gemini API] Call: Relevance Judge | Prompt: {prompt_tokens} | Completion: {completion_tokens} | Total: {total_tokens} tokens", flush=True)

        return {
            "is_relevant": is_relevant,
            "relevance_score": score,
            "buying_signal": buying_signal,
            "relevance_tier": category,
            "reason": reason,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens
        }
    except Exception as e:
        print(f"Gemini API invocation error: {e}")
        raise e
