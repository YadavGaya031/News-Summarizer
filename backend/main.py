from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from langchain_groq import ChatGroq
from dotenv import load_dotenv
import os
import requests
from gtts import gTTS
from models import NewsRequest
import base64
import re


app = FastAPI()
load_dotenv()

#Scraping functions
def scrape_google_news(topic: list[str]):
    query = " OR ".join(topic)
    url = f"https://newsapi.org/v2/everything?q={query}&language=en&apiKey={os.getenv('NEWS_API_KEY')}"
    resp = requests.get(url)
    data = resp.json()
    if data.get("articles"):
        return " ".join([article["title"] + ". " + article.get("description", "") for article in data["articles"][:5]])
    return ""


def scrape_x_posts(topic: list[str]):
    # Using X API v2
    query = " OR ".join(topic)
    url = f"https://api.twitter.com/2/tweets/search/recent?query={query}&max_results=15"
    headers = {"Authorization": f"Bearer {os.getenv('X_BEARER_TOKEN')}"}
    resp = requests.get(url, headers=headers)
    data = resp.json()
    if data.get("data"):
        return " ".join([tweet["text"] for tweet in data["data"]])
    return ""


# ---------- Summarization Function ----------
def summary_function(news_data: str, x_data: str):
    # Call Groq DeepSeek LLM
    groq_api_key = os.getenv("GROQ_API_KEY")

    payload = {
        "model" : "deepseek-r1-distill-llama-70b",
        "messages": [
            {"role": "system",
             "content": (
                "You are a precise summarization assistant. "
                "Only use the information given in the news and tweets. "
                "Do not add unrelated facts, opinions, or assumptions. "
                "Summarize in 10-15 bullet points, each under 50 words."
                )
            },
            {"role": "user", "content": f"NEWS:\n{news_data}\n\nTWEETS:\n{x_data}\n\nNow summarize."}
        ],
        "temperature": 0
    }
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {groq_api_key}", "Content-Type": "application/json"},
        json=payload
    )

    # Debug logging for failures
    try:
        result = response.json()
    except Exception:
        raise HTTPException(status_code=500, detail=f"Invalid JSON from Groq: {response.text}")

    # Check if API returned an error
    if "error" in result:
        raise HTTPException(status_code=500, detail=f"Groq API Error: {result['error']}")

    if "choices" not in result or not result["choices"]:
        raise HTTPException(status_code=500, detail=f"No choices in Groq response: {result}")
    raw_text = str(result["choices"][0]["message"]["content"].strip())
    cleaned_text = re.sub(r"<think>.*?</think>","",raw_text,flags=re.DOTALL).strip()
    return cleaned_text


# ---------- Text to Audio ----------
def convert_text_to_audio(text: str):
    audio_file_path = "summary_audio.mp3"
    tts = gTTS(text=text, lang="en")
    tts.save(audio_file_path)
    #return base64 directly so frontend can use st.audio
    with open(audio_file_path, "rb") as f:
        audio_base64 = base64.b64encode(f.read()).decode("utf-8")
    return audio_base64



@app.post("/generate-audio")
async def generate_audio(request: NewsRequest):
    try:
        #Scrapping
        news_data = scrape_google_news(request.topics) if request.source_type in ["news", "both"] else ""
        X_data = scrape_x_posts(request.topics) if request.source_type in ["X", "both"] else ""

        print("Scrapped News:", news_data)
        print('Scrapped Tweets:', X_data)

        #Summarization
        news_summary = summary_function(news_data, X_data)
        if not news_summary.strip():
            raise HTTPException(status_code=400, detail="summary generation failed.")
        print("Summary:", news_summary)
        #convert to audio
        audio_base64 = convert_text_to_audio(news_summary)

        #send both text and audio to frontend
        return JSONResponse({
            "summary": news_summary,
            "audio" : audio_base64
        })
    except Exception as e:
        print("Error IN /generate-audio:",e)
        raise HTTPException(status_code=500, detail=str(e))
