from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.models import NewsRequest
from dotenv import load_dotenv
import os
import requests
from gtts import gTTS
import base64
import re
import time
import hashlib
import json

# ---------- Load env variables ----------
# Expects:
# NEWS_API_KEY
# X_BEARER_TOKEN
# GROQ_API_KEY
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

app = FastAPI(title="News Summarizer Backend")

# ---------- CORS (allow frontend Render URL) ----------
# In production, restrict origins to your exact Streamlit URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for debugging; later change to ["https://your-frontend.onrender.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# # ---------- Request Model ----------
# class NewsRequest(BaseModel):
#     topics: List[str]
#     source_type: Literal["news", "X", "both"]


# ---------- Simple In-Memory Cache ----------
# This helps avoid repeated API + LLM calls for same topics/source_type.
CACHE: dict[str, dict] = {}
CACHE_TTL_SECONDS = 10 * 60  # 10 minutes


def make_cache_key(topics: List[str], source_type: str) -> str:
    """
    Create a stable cache key from topics + source_type.
    Topics are lowercased + sorted to avoid duplicates.
    """
    normalized_topics = [t.strip().lower() for t in topics if t.strip()]
    normalized_topics.sort()
    payload = {
        "topics": normalized_topics,
        "source_type": source_type,
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_from_cache(key: str):
    """Return cached value if present & not expired."""
    entry = CACHE.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > CACHE_TTL_SECONDS:
        # expired
        del CACHE[key]
        return None
    return entry["data"]


def set_cache(key: str, data: dict):
    """Store data in cache with current timestamp."""
    CACHE[key] = {"data": data, "ts": time.time()}


# ---------- External Scraping Functions ----------

def scrape_google_news(topics: List[str]) -> str:
    """
    Use NewsAPI to fetch news articles for the given topics.
    Returns concatenated title + description for top 5 articles.
    """
    if not NEWS_API_KEY:
        raise HTTPException(status_code=500, detail="NEWS_API_KEY is not configured on the server.")

    query = " OR ".join(topics)
    url = (
        f"https://newsapi.org/v2/everything"
        f"?q={query}&language=en&pageSize=5&apiKey={NEWS_API_KEY}"
    )

    resp = requests.get(url, timeout=20)

    if resp.status_code == 429:
        # Upstream NewsAPI rate limit
        raise HTTPException(
            status_code=429,
            detail="News API rate limit reached. Please wait and try again."
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"News API error: {resp.text}"
        )

    data = resp.json()
    articles = data.get("articles", [])
    if not articles:
        return ""

    combined = []
    for article in articles[:5]:
        title = article.get("title", "")
        desc = article.get("description", "")
        combined.append(f"{title}. {desc}")
    return " ".join(combined).strip()


def scrape_x_posts(topics: List[str]) -> str:
    """
    Use X (Twitter) API v2 to fetch recent tweets for given topics.
    Returns combined tweet texts.
    """
    if not X_BEARER_TOKEN:
        # It's okay to proceed without X; just return empty and rely on news.
        return ""

    query = " OR ".join(topics)
    url = (
        "https://api.twitter.com/2/tweets/search/recent"
        f"?query={query}&max_results=15"
    )
    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}

    resp = requests.get(url, headers=headers, timeout=20)

    if resp.status_code == 429:
        # Upstream X API rate limit
        raise HTTPException(
            status_code=429,
            detail="X API rate limit reached. Please wait and try again."
        )

    if resp.status_code != 200:
        # Don't hard-fail if X fails; just ignore tweets.
        print(f"⚠ X API error ({resp.status_code}): {resp.text}")
        return ""

    data = resp.json()
    tweets = data.get("data", [])
    if not tweets:
        return ""

    texts = [tweet.get("text", "") for tweet in tweets]
    return " ".join(texts).strip()


# ---------- LLM Summarization ----------

def summary_function(news_data: str, x_data: str) -> str:
    """
    Calls Groq ChatCompletion-style API to summarize combined news + tweets.
    Cleans out <think> blocks if present.
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY is not configured on the server.")

    # Guard: if we have no data, don't waste LLM calls
    if not news_data and not x_data:
        raise HTTPException(
            status_code=400,
            detail="No news or tweets available to summarize for the given topics."
        )

    payload = {
        "model": "groq/compound",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a precise summarization assistant. "
                    "Only use the information given in the news and tweets. "
                    "Do not add unrelated facts, opinions, or assumptions. "
                    "Summarize in 10-15 bullet points, each under 50 words."
                )
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
        # Groq rate limit
        raise HTTPException(
            status_code=429,
            detail="Groq LLM rate limit reached. Please wait a few seconds and try again."
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Groq API error: {resp.text}"
        )

    try:
        result = resp.json()
    except Exception:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid JSON from Groq: {resp.text}"
        )

    if "error" in result:
        raise HTTPException(
            status_code=500,
            detail=f"Groq API error: {result['error']}"
        )

    choices = result.get("choices")
    if not choices:
        raise HTTPException(
            status_code=500,
            detail=f"No choices in Groq response: {result}"
        )

    raw_text = str(choices[0]["message"]["content"]).strip()

    # Remove <think>...</think> blocks if present
    cleaned_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
    return cleaned_text


# ---------- Text to Audio ----------

def convert_text_to_audio(text: str) -> str:
    """
    Converts text to mp3 using gTTS and returns base64-encoded audio string.
    """
    audio_file_path = "summary_audio.mp3"
    tts = gTTS(text=text, lang="en")
    tts.save(audio_file_path)

    with open(audio_file_path, "rb") as f:
        audio_base64 = base64.b64encode(f.read()).decode("utf-8")

    return audio_base64


# ---------- Main Endpoint ----------

@app.post("/generate-audio")
async def generate_audio(request: NewsRequest):
    """
    Main pipeline:
    1. Check cache for existing result for (topics, source_type)
    2. Scrape news / tweets
    3. Summarize using Groq
    4. Convert to audio (gTTS)
    5. Return summary + audio (base64)
    """
    try:
        # Filter out empty topics
        topics = [t.strip() for t in request.topics if t.strip()]
        if not topics:
            raise HTTPException(status_code=400, detail="At least one non-empty topic is required.")

        # ----- Check cache -----
        cache_key = make_cache_key(topics, request.source_type)
        cached = get_from_cache(cache_key)
        if cached:
            print("✔ Returning cached result.")
            return JSONResponse(cached)

        # ----- Scraping -----
        news_data = ""
        x_data = ""

        if request.source_type in ("news", "both"):
            news_data = scrape_google_news(topics)

        if request.source_type in ("X", "both"):
            x_data = scrape_x_posts(topics)

        # If still no data from either source
        if not news_data and not x_data:
            raise HTTPException(
                status_code=400,
                detail="No data could be fetched from News or X for the given topics."
            )

        print("✅ Scraped News Length:", len(news_data))
        print("✅ Scraped Tweets Length:", len(x_data))

        # ----- Summarization -----
        summary = summary_function(news_data, x_data)
        if not summary.strip():
            raise HTTPException(status_code=500, detail="Summary generation failed.")

        print("✅ Generated Summary Length:", len(summary))

        # ----- Convert to Audio -----
        audio_base64 = convert_text_to_audio(summary)

        result = {
            "summary": summary,
            "audio": audio_base64,
        }

        # ----- Store in Cache -----
        set_cache(cache_key, result)

        return JSONResponse(result)

    except HTTPException as e:
        # Re-raise structured API errors
        print("HTTPException in /generate-audio:", e.detail)
        raise e

    except Exception as e:
        # Catch-all for unexpected errors
        print("Unexpected Error in /generate-audio:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
