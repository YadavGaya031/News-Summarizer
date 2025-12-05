import os
import json
import time
import base64
import hashlib
import traceback
import requests
import re
from gtts import gTTS
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.models import NewsRequest

# ----------------------------------
# Logging Setup
# ----------------------------------
import logging
logging.basicConfig(
    level=logging.INFO,
    format="\n[%(asctime)s] [%(levelname)s]\n%(message)s\n"
)

log = logging.getLogger("NewsSummarizer")

# ----------------------------------
# ENVIRONMENT
# ----------------------------------
load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def warn_missing(var: str):
    if not globals()[var]:
        log.warning(f"⚠ ENV NOT FOUND: {var}")

warn_missing("NEWS_API_KEY")
warn_missing("X_BEARER_TOKEN")
warn_missing("GROQ_API_KEY")

# ----------------------------------
# FASTAPI APP
# ----------------------------------
app = FastAPI(title="News Summarizer Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Modify for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------
# GLOBAL ERROR HANDLER
# logs every unhandled exception
# ----------------------------------
@app.middleware("http")
async def catch_all(request: Request, call_next):
    try:
        return await call_next(request)

    except Exception as e:
        log.error("🔥 UNCAUGHT BACKEND EXCEPTION")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

# ----------------------------------
# CACHE
# ----------------------------------
CACHE: dict[str, dict] = {}
CACHE_TTL_SECONDS = 10 * 60

def make_cache_key(topics: list[str], source_type: str) -> str:
    normalized = sorted([t.strip().lower() for t in topics if t.strip()])
    raw = json.dumps({"topics": normalized, "source": source_type}, sort_keys=True)
    key = hashlib.sha256(raw.encode()).hexdigest()
    log.info(f"[CACHE-KEY] {key} for payload {raw}")
    return key

def get_from_cache(key: str):
    entry = CACHE.get(key)
    if not entry:
        log.info("[CACHE] MISS")
        return None

    age = time.time() - entry["ts"]
    if age > CACHE_TTL_SECONDS:
        log.info(f"[CACHE] EXPIRED after {age:.2f}s")
        del CACHE[key]
        return None

    log.info("[CACHE] HIT")
    return entry["data"]

def set_cache(key: str, data: dict):
    CACHE[key] = {"data": data, "ts": time.time()}
    log.info("[CACHE] STORED")

# ----------------------------------
# HTTP Helper with logging
# ----------------------------------
def safe_request(method, url, **kwargs):
    # Apply default timeout only if caller hasn't given one
    if "timeout" not in kwargs:
        kwargs["timeout"] = 20

    log.info(
        f"\n----- External API Call -----\n"
        f"URL: {url}\n"
        f"Method: {method}\n"
        f"Params: {kwargs}\n"
        "-----------------------------"
    )

    try:
        resp = requests.request(method, url, **kwargs)
        log.info(f"STATUS: {resp.status_code}")
        log.info(f"RAW RESPONSE:\n{resp.text}\n")
        return resp

    except Exception:
        log.error("HTTP REQUEST FAILED!")
        traceback.print_exc()
        raise

# ----------------------------------
# SCRAPE: NEWS
# ----------------------------------
def scrape_google_news(topics: list[str]) -> str:
    try:
        if not NEWS_API_KEY:
            log.warning("NEWS_API_KEY missing, skipping Google News")
            return ""

        query = " OR ".join(topics)
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={query}&language=en&pageSize=5&apiKey={NEWS_API_KEY}"
        )

        resp = safe_request("GET", url)

        if resp.status_code == 429:
            raise HTTPException(429, "Google News rate limit hit!")

        if resp.status_code != 200:
            log.error(f"Unexpected NewsAPI response:\n{resp.text}")
            return ""

        articles = resp.json().get("articles", [])
        news_text = " ".join(
            f"{a.get('title','')}. {a.get('description','')}" for a in articles[:5]
        ).strip()

        log.info(f"[NEWS-RESULT] Extracted length: {len(news_text)} chars")
        return news_text

    except Exception:
        log.error("ERROR SCRAPING NEWS")
        traceback.print_exc()
        return ""

# ----------------------------------
# SCRAPE: X
# ----------------------------------
def scrape_x_posts(topics: list[str]) -> str:
    try:
        if not X_BEARER_TOKEN:
            log.warning("X_BEARER_TOKEN not found, skipping X scraping")
            return ""

        query = " OR ".join(topics)
        url = (
            f"https://api.twitter.com/2/tweets/search/recent"
            f"?query={query}&max_results=15"
        )

        headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}

        resp = safe_request("GET", url, headers=headers)

        if resp.status_code == 429:
            raise HTTPException(429, "X Rate limit reached")

        if resp.status_code != 200:
            log.warning(f"X API Non-200:\n{resp.text}")
            return ""

        tweets = resp.json().get("data", [])
        text = " ".join([t.get("text", "") for t in tweets])
        log.info(f"[X-RESULT] Extracted len: {len(text)}")
        return text

    except Exception:
        log.error("ERROR SCRAPING X POSTS")
        traceback.print_exc()
        return ""

# ----------------------------------
# GROQ SUMMARIZATION
# ----------------------------------
def summary_function(news: str, tweets: str) -> str:
    log.info("LLM Summarization Started")
    log.info(f"NEWS LEN: {len(news)} | TWEETS LEN: {len(tweets)}")

    if not GROQ_API_KEY:
        raise HTTPException(500, "GROQ_API_KEY missing.")

    if not news and not tweets:
        raise HTTPException(400, "No scraped data.")

    payload = {
        "model": "groq/compound",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Strict summary. Only given info. "
                    "10-15 bullets, each under 50 words. No hallucinations."
                ),
            },
            {
                "role": "user",
                "content": f"NEWS:\n{news}\n\nTWEETS:\n{tweets}",
            },
        ],
        "temperature": 0,
    }

    log.info(f"Payload to Groq:\n{json.dumps(payload, indent=2)}")

    try:
        resp = safe_request(
            "POST",
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, resp.text)

        data = resp.json()
        text = data["choices"][0]["message"]["content"]

        clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        log.info("LLM Summary Generated Successfully")
        return clean

    except Exception:
        log.error("ERROR IN LLM SUMMARIZATION")
        traceback.print_exc()
        raise

# ----------------------------------
# AUDIO
# ----------------------------------
def convert_text_to_audio(text: str) -> str:
    log.info("Audio Generation Started")
    try:
        tts = gTTS(text=text, lang="en")
        tts.save("summary.mp3")

        with open("summary.mp3", "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()

        log.info("Audio Encoding Successful")
        return audio_b64

    except Exception:
        log.error("AUDIO CONVERSION FAILED")
        traceback.print_exc()
        raise

# ----------------------------------
# ENDPOINT
# ----------------------------------
@app.post("/generate-audio")
async def generate_audio(req: NewsRequest):
    log.info(f"\n=== /generate-audio HIT ===\n{req}")

    try:
        topics = [t.strip() for t in req.topics if t.strip()]
        if not topics:
            raise HTTPException(400, "No topics provided")

        key = make_cache_key(topics, req.source_type)
        cached = get_from_cache(key)
        if cached:
            log.info("Returning Cached Result")
            return JSONResponse(cached)

        # SCRAPING
        news = scrape_google_news(topics) if req.source_type in ("news", "both") else ""
        tweets = scrape_x_posts(topics) if req.source_type in ("X", "both") else ""

        if not news and not tweets:
            raise HTTPException(400, "No data found from sources")

        # SUMMARIZE
        summary = summary_function(news, tweets)

        # AUDIO
        audio = convert_text_to_audio(summary)

        result = {"summary": summary, "audio": audio}

        set_cache(key, result)
        return JSONResponse(result)

    except HTTPException as e:
        log.error(f"HTTPException: {e.detail}")
        traceback.print_exc()
        raise

    except Exception as e:
        log.error("UNEXPECTED ERROR IN /generate-audio")
        traceback.print_exc()
        raise HTTPException(500, str(e))

# ----------------------------------
# Root
# ----------------------------------
@app.get("/")
def health_check():
    log.info("Health check")
    return {"status": "OK"}
