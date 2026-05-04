from playwright.sync_api import sync_playwright
import json
import os
import re
import time
import urllib.parse
import urllib.request
from html import unescape

last_filled_url = None
tweet_text_cache = {}
DEBUG_SCORING = os.getenv("J7_DEBUG_SCORING", "0") == "1"

def _looks_like_tweet_url(text):
    t = (text or "").strip().lower()
    return ("x.com/" in t or "twitter.com/" in t) and "/status/" in t


def get_tweet_text_from_j7(page):
    """Extract text directly from J7 deploy page - NO extra tab"""
    text_parts = []
    try:
        # POST input often contains only the tweet URL, so treat it as metadata.
        post_input = page.locator('input[placeholder*="x.com"], input[placeholder*="twitter"], textarea').first
        post_value = post_input.input_value(timeout=500) or ""
        if post_value and not _looks_like_tweet_url(post_value):
            text_parts.append(post_value)
    except:
        pass

    # Always try preview text; this is usually the real tweet content.
    preview_selectors = [
        'article',
        'div[role="textbox"]',
        'pre',
        'code',
        '[data-testid*="tweet"]',
    ]
    for selector in preview_selectors:
        try:
            candidate = page.locator(selector).first.inner_text(timeout=500) or ""
            if candidate.strip():
                text_parts.append(candidate.strip())
        except:
            pass

    text = " ".join(text_parts).strip()
    if len(text) < 20:
        try:
            text = page.inner_text('body', timeout=800)[:900]
        except:
            pass

    return text.strip()


def fetch_tweet_text_from_url(tweet_url):
    """
    Resolve the actual tweet text from the x.com URL via Twitter oEmbed.
    This is usually far more accurate than scraping J7 UI text.
    """
    if not tweet_url:
        return ""
    if tweet_url in tweet_text_cache:
        return tweet_text_cache[tweet_url]
    if "/status/" not in tweet_url:
        return ""

    try:
        api = "https://publish.twitter.com/oembed?" + urllib.parse.urlencode(
            {"url": tweet_url, "omit_script": "1", "hide_thread": "1"}
        )
        req = urllib.request.Request(
            api,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        html = data.get("html", "")
        # Pull text from <p>...</p> block in returned embed HTML.
        m = re.search(r"<p[^>]*>(.*?)</p>", html, re.I | re.S)
        if not m:
            return ""
        text = m.group(1)
        text = re.sub(r"<br\\s*/?>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        text = unescape(text).strip()
        tweet_text_cache[tweet_url] = text
        return text
    except Exception:
        return ""

def _clean_words(text):
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9']*\b", text)
    stop = {
        "the", "and", "for", "over", "on", "in", "with", "this", "that", "you",
        "have", "not", "is", "are", "was", "were", "from", "your", "just",
        "about", "into", "when", "what", "where", "will", "would", "could",
        "should", "they", "them", "their", "there", "then", "than"
    }
    return [w for w in words if len(w) > 2 and w.lower() not in stop]


def _extract_handle_from_url(tweet_url):
    # e.g. https://x.com/elonmusk/status/... -> ELON
    m = re.search(r"x\.com/([A-Za-z0-9_]+)/status", tweet_url or "", re.I)
    if not m:
        return ""
    handle = re.sub(r"[^A-Za-z]", "", m.group(1))
    if not handle:
        return ""
    return handle[:13].upper()


def generate_name_and_symbol(tweet_text, tweet_url=""):
    """Tweet text/url -> salient phrase name + topic symbol (fast heuristic)."""
    if not tweet_text.strip():
        base = _extract_handle_from_url(tweet_url)
        return "Viral Token", base or "VIRAL"

    raw = re.sub(r"https?://\S+", "", tweet_text)
    raw = re.sub(r"@\w+", "", raw).strip()
    raw_lower = raw.lower()

    # Learned shortcuts from user feedback examples.
    if "stay consistent" in raw_lower:
        return "Stay Consistent", "CONSISTENT"
    if "hyper-realistic portrait" in raw_lower and "went viral" in raw_lower:
        return "Cooked", "COOKED"

    words_original = re.findall(r"\b[A-Za-z][A-Za-z0-9']*\b", raw)
    words_lower = [w.lower() for w in words_original]

    if not words_lower:
        base = _extract_handle_from_url(tweet_url)
        return "Viral Token", base or "VIRAL"

    # Keep this minimal so behavior stays broad and intuitive.
    connectors = {
        "the", "and", "for", "with", "this", "that", "you", "your", "from",
        "into", "what", "when", "where", "they", "them", "their", "there",
        "will", "would", "could", "should", "is", "are", "was", "were", "it"
    }

    # Build ranked name candidates (3-word chunks).
    name_candidates = []
    for i in range(len(words_lower)):
        chunk = words_lower[i:i + 3]
        if len(chunk) < 2:
            continue
        score = 0
        for w in chunk:
            score += 2 if w not in connectors else -2
            score += min(len(w), 9)
        phrase = " ".join(chunk).title().strip()
        if phrase:
            name_candidates.append((score, phrase))

    # Deduplicate name candidates while preserving best score.
    name_scores = {}
    for score, phrase in name_candidates:
        if phrase not in name_scores or score > name_scores[phrase]:
            name_scores[phrase] = score
    ranked_name_candidates = sorted(
        [(s, p) for p, s in name_scores.items()],
        key=lambda x: x[0],
        reverse=True,
    )
    best_phrase = ranked_name_candidates[0][1].split() if ranked_name_candidates else []

    if not best_phrase:
        content = [w for w in words_lower if w not in connectors]
        best_phrase = content[:3] if content else words_lower[:3]

    name = " ".join(best_phrase).title().strip()
    if not name:
        name = "Viral Token"

    # Symbol: prefer strongest proper noun/keyword from text.
    proper_candidates = [
        w for w in words_original if w[0].isupper() and len(w) >= 4
    ]
    keyword_candidates = [
        w for w in words_original if len(w) >= 5 and w.lower() not in connectors
    ]
    ordered = proper_candidates + keyword_candidates
    # Avoid picking generic platform/site words as symbols.
    banned_symbol_words = {
        "twitter", "thread", "status", "click", "reply", "retweet",
        "quote", "j7", "j7tracker", "deploy", "token",
        "settings", "disable", "suggestions", "create", "vamp", "translate",
    }
    # Build ranked symbol candidates.
    symbol_candidates = []
    for idx, candidate in enumerate(ordered):
        c = candidate.lower()
        if c in banned_symbol_words:
            continue
        score = 0
        if candidate in proper_candidates:
            score += 8
        if len(candidate) >= 6:
            score += 2
        score += max(0, 5 - idx)  # earlier candidates are preferred
        symbol_candidates.append((score, candidate))

    # Deduplicate symbols with max score.
    symbol_scores = {}
    for score, candidate in symbol_candidates:
        if candidate not in symbol_scores or score > symbol_scores[candidate]:
            symbol_scores[candidate] = score
    ranked_symbol_candidates = sorted(
        [(s, c) for c, s in symbol_scores.items()],
        key=lambda x: x[0],
        reverse=True,
    )

    symbol = ranked_symbol_candidates[0][1] if ranked_symbol_candidates else ""

    if len(symbol) < 3:
        symbol = _extract_handle_from_url(tweet_url)
    if len(symbol) < 3:
        symbol = "VIRL"

    symbol = re.sub(r"[^A-Za-z]", "", symbol).upper()[:13]
    if len(symbol) < 1:
        symbol = "VIRAL"

    if DEBUG_SCORING:
        print("\n[DEBUG] Top 5 name candidates:")
        for i, (score, cand) in enumerate(ranked_name_candidates[:5], 1):
            print(f"  {i}. {cand}  (score={score})")
        print("[DEBUG] Top 5 symbol candidates:")
        for i, (score, cand) in enumerate(ranked_symbol_candidates[:5], 1):
            cleaned = re.sub(r"[^A-Za-z]", "", cand).upper()[:13]
            print(f"  {i}. {cleaned or cand}  (raw={cand}, score={score})")

    return name, symbol

def smart_fill_deploy(page):
    global last_filled_url
    
    try:
        # Get URL to avoid refilling same page
        url = page.locator('input[placeholder*="x.com"]').first.input_value(timeout=600) or ""
        if url == last_filled_url:
            return
        
        tweet_text = fetch_tweet_text_from_url(url)
        if not tweet_text:
            tweet_text = get_tweet_text_from_j7(page)

        print(f"Tweet text: {tweet_text[:160]}...")
        
        name, symbol = generate_name_and_symbol(tweet_text, url)
        
        print(f"✅ Name: {name}")
        print(f"✅ Symbol: {symbol}")
        
        # Ultra-fast fill
        page.locator('input[placeholder*="Token name"]').first.fill(name)
        page.locator('input[placeholder*="Symbol"]').first.fill(symbol)
        
        # Cashback + Image
        try:
            page.locator('button:has-text("Cashback")').first.click(timeout=600)
        except:
            pass
        try:
            page.locator('img').first.click(timeout=600)
        except:
            pass
        
        last_filled_url = url
        print("✅ FILLED in <1s → Click Deploy!\n")
        
    except Exception as e:
        print(f"Error: {e}")

# ====================== MAIN ======================
with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
    )
    context = browser.new_context()
    page = context.new_page()
    
    page.goto("https://j7tracker.io/")
    print("✅ J7 is running. Log in and keep this script open.")
    print("Click DEPLOY → should now fill almost instantly.\n")
    
    while True:
        try:
            if page.locator('input[placeholder*="Token name"]').count() > 0:
                smart_fill_deploy(page)
                time.sleep(3)
        except:
            pass
        time.sleep(0.5)