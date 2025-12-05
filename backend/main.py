from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.models import NewsRequest  # data model
from dotenv import load_dotenv

import os
import requests
from gtts import gTTS
import base64
import re
import time
import hashlib
import json

# ----------------------------------
# Load environment variables
# Required:
# NEWS_API_KEY
# X_BEARER_TOKEN
# GROQ_API_KEY
# ----------------------------------
load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not NEWS_API_KEY:
    print("⚠ WARNING: NEWS_API_KEY not set.")
if not X_BEARER_TOKEN:
    print("⚠ WARNING: X_BEARER_TOKEN not set.")
if not GROQ_API_KEY:
    print("⚠ WARNING: GROQ_API_KEY not set.")

# ----------------------------------
# FastAPI Instance
# ----------------------------------
app = FastAPI(title="News Summarizer Backend")

# ----------------------------------
# CORS
# IMPORTANT: replace this with YOUR FRONTEND URL
# Example: "https://news-summarizer-2-xlbc.onrender.com"
# ----------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For now, allow all during testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------
# Simple Cache
# Key: sha256(sorted_topics, source)
# Value: { "summary": "...", "audio": "...base64" }
# TTL: 10 mins
# ----------------------------------
CACHE: dict[str, dict] = {}
CACHE_TTL_SECONDS = 10 * 60


def make_cache_key(topics: list[str], source_type: str) -> str:
    normalized_topics = [t.strip().lower() for t in topics if t.strip()]
    normalized_topics.sort()
    payload = {
        "topics": normalized_topics,
        "source_type": source_type,
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_from_cache(key: str):
    entry = CACHE.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > CACHE_TTL_SECONDS:
        del CACHE[key]
        return None
    return entry["data"]


def set_cache(key: str, data: dict):
    CACHE[key] = {"data": data, "ts": time.time()}


# ----------------------------------
# EXTERNAL SCRAPING FUNCTIONS
# ----------------------------------

def scrape_google_news(topics: list[str]) -> str:
    """Scrape top 5 news articles for topics using NewsAPI."""
    if not NEWS_API_KEY:
        return ""

    query = " OR ".join(topics)
    url = (
        f"https://newsapi.org/v2/everything"
        f"?q={query}&language=en&pageSize=5&apiKey={NEWS_API_KEY}"
    )

    resp = requests.get(url, timeout=20)

    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="News API rate limit reached. Try later."
        )

    if resp.status_code != 200:
        print(f"⚠ NewsAPI error: {resp.text}")
        return ""

    articles = resp.json().get("articles", [])
    if not articles:
        return ""

    final = []
    for article in articles[:5]:
        title = article.get("title", "")
        desc = article.get("description", "")
        final.append(f"{title}. {desc}")

    return " ".join(final).strip()


def scrape_x_posts(topics: list[str]) -> str:
    """Scrape recent X posts matching topics."""
    if not X_BEARER_TOKEN:
        return ""  # optional

    query = " OR ".join(topics)
    url = (
        "https://api.twitter.com/2/tweets/search/recent"
        f"?query={query}&max_results=15"
    )

    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}

    resp = requests.get(url, headers=headers, timeout=20)

    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="X API rate limit reached. Try again later."
        )

    if resp.status_code != 200:
        print(f"⚠ Warning: X API error {resp.status_code}: {resp.text}")
        return ""

    tweets = resp.json().get("data", [])
    if not tweets:
        return ""

    return " ".join([t.get("text", "") for t in tweets]).strip()


# ----------------------------------
# GROQ SUMMARIZATION
# ----------------------------------

def summary_function(news_data: str, x_data: str) -> str:
    """Calls Groq LLM to summarize scraped text."""
    if not GROQ_API_KEY:
        raise HTTPException(500, "GROQ_API_KEY missing.")

    if not news_data and not x_data:
        raise HTTPException(400, "No news or tweets available.")

    payload = {
        "model": "groq/compound",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a precise summarization assistant. Use ONLY given info. "
                    "No opinions, assumptions, or invented facts. "
                    "Summarize into 10-15 bullet points, each under 50 words."
                ),
            },
            {
                "role": "user",
                "content": f"NEWS:\n{news_data}\n\nTWEETS:\n{x_data}\n\nNow summarize."
            },
        ],
        "temperature": 0,
    }

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )

    if resp.status_code == 429:
        raise HTTPException(429, "Groq rate limit reached. Try again.")

    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"Groq API Error: {resp.text}")

    result = resp.json()

    if "error" in result:
        raise HTTPException(500, f"Groq Error: {result['error']}")

    choices = result.get("choices")
    if not choices:
        raise HTTPException(500, f"No choices in response: {result}")

    text = choices[0]["message"]["content"].strip()

    # remove <think>...</think>
    clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return clean


# ----------------------------------
# TEXT → AUDIO (MP3 via gTTS)
# ----------------------------------

def convert_text_to_audio(text: str) -> str:
    audio_file = "summary.mp3"
    tts = gTTS(text=text, lang="en")
    tts.save(audio_file)

    with open(audio_file, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ----------------------------------
# MAIN ENDPOINT
# ----------------------------------

@app.post("/generate-audio")
async def generate_audio(request: NewsRequest):
    try:
        topics = [t.strip() for t in request.topics if t.strip()]
        if not topics:
            raise HTTPException(400, "At least one topic is required.")

        cache_key = make_cache_key(topics, request.source_type)
        cached = get_from_cache(cache_key)
        if cached:
            print("✔ Returning cached result")
            return JSONResponse(cached)

        # --- Scrape data
        news = ""
        tweets = ""

        if request.source_type in ("news", "both"):
            news = scrape_google_news(topics)

        if request.source_type in ("X", "both"):
            tweets = scrape_x_posts(topics)

        if not news and not tweets:
            raise HTTPException(400, "No data found for topics.")

        print(f"News length: {len(news)}, Tweets length: {len(tweets)}")

        # --- Summarize
        summary = summary_function(news, tweets)
        if not summary:
            raise HTTPException(500, "Failed to produce summary.")

        print("Summary Generated ✔")

        # --- Audio Encode
        audio_base64 = convert_text_to_audio(summary)

        result = {
            "summary": summary,
            "audio": audio_base64,
        }

        set_cache(cache_key, result)
        return JSONResponse(result)

    except HTTPException as e:
        print("API Error:", e.detail)
        raise e

    except Exception as e:
        print("Unexpected Error:", str(e))
        raise HTTPException(500, str(e))


# ----------------------------------
# HEALTH CHECK
# ----------------------------------
@app.get("/")
def health():
    return {"status": "OK", "message": "Backend is running!"}
