# News Scraper & Audio Summary Application

A full-stack web application that scrapes news articles from Google News and X (Twitter), then generates audio summaries using AI. Built with FastAPI backend and Streamlit frontend.

## 🚀 Features

- **Multi-source News Scraping**: Fetches latest news from Google News and X (Twitter)
- **AI-Powered Summarization**: Uses Groq's DeepSeek LLM for intelligent summarization
- **Audio Generation**: Converts summaries to audio using Google Text-to-Speech
- **Real-time Processing**: Streamlit interface for live interaction
- **Flexible Source Selection**: Choose between news, X posts, or both
- **Downloadable Audio**: Export generated audio summaries as MP3 files

## 🏗️ Architecture

```
news-scrapper/
├── backend/
│   ├── backend.py          # FastAPI REST API
│   ├── models.py           # Pydantic models for request/response
│   └── requirements.txt    # Backend dependencies
├── frontend/
│   ├── frontend.py         # Streamlit web interface
│   └── requirements.txt    # Frontend dependencies
└── README.md
```

## 🛠️ Tech Stack

### Backend
- **FastAPI** - Modern web framework for REST API
- **Uvicorn** - ASGI server
- **Groq API** - DeepSeek LLM for AI summarization
- **News API** - Google News data source
- **X API** - Twitter/X data source
- **gTTS** - Google Text-to-Speech for audio generation
- **Python-dotenv** - Environment variable management

### Frontend
- **Streamlit** - Web application framework
- **Requests** - HTTP client for API calls
- **Base64** - Audio encoding/decoding

## 📋 Prerequisites

- Python 3.8+
- pip (Python package manager)
- Git
- API Keys:
  - Groq API Key
  - News API Key
  - X (Twitter) Bearer Token

## 🔧 Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd news-scrapper
```

### 2. Backend Setup
```bash
cd backend
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Frontend Setup
```bash
cd frontend
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 4. Environment Configuration
Create a `.env` file in the backend directory:

```env
GROQ_API_KEY=your_groq_api_key_here
NEWS_API_KEY=your_news_api_key_here
X_BEARER_TOKEN=your_twitter_bearer_token_here
```

## 🚀 Running the Application

### Start Backend Server
```bash
cd backend
uvicorn backend.backend:app --reload --host 0.0.0.0 --port 8000
```
The API will be available at `http://localhost:8000`

### Start Frontend
```bash
cd frontend
streamlit run frontend.py
```
The web interface will open automatically in your browser at `http://localhost:8501`

## 📡 API Endpoints

### Generate Audio Summary
- **POST** `/generate-audio` - Generate audio summary from news topics
  ```json
  {
    "topics": ["AI", "climate change"],
    "source_type": "both"
  }
  ```
  Response:
  ```json
  {
    "summary": "Bullet-point summary...",
    "audio": "base64-encoded-audio-data"
  }
  ```

## 🎯 Usage Examples

### Using the Web Interface
1. Open the Streamlit app at `http://localhost:8501`
2. Enter topics in the sidebar (e.g., "AI", "climate change")
3. Select data sources (News, X posts, or both)
4. Click "Generate Audio" to process
5. Listen to the audio summary or download as MP3

### Using the API Directly
```python
import requests

response = requests.post(
    "http://localhost:8000/generate-audio",
    json={
        "topics": ["AI", "climate change"],
        "source_type": "both"
    }
)

data = response.json()
print(data["summary"])  # Text summary
# data["audio"] contains base64-encoded MP3
```

## 🔍 Configuration

### Environment Variables
- `GROQ_API_KEY` - Groq API key for AI summarization
- `NEWS_API_KEY` - News API key for Google News
- `X_BEARER_TOKEN` - Twitter/X API bearer token

### Source Selection Options
- `"news"` - Google News only
- `"X"` - X (Twitter) posts only
- `"both"` - Both sources combined

## 🧪 Testing

### Backend Tests
```bash
cd backend
python -m pytest tests/ -v
```

### Manual Testing
1. Start the backend server
2. Test the API endpoint:
   ```bash
   curl -X POST http://localhost:8000/generate-audio \
     -H "Content-Type: application/json" \
     -d '{"topics": ["AI"], "source_type": "both"}'
   ```

## 🔄 Deployment


### Manual Deployment
1. Set production environment variables
2. Use a process manager (e.g., systemd, supervisor)
3. Configure reverse proxy (nginx)
4. Set up SSL certificates

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support, please open an issue on GitHub or contact the development team.

## 🗺️ Roadmap

- [ ] Add user authentication and saved preferences
- [ ] Implement real-time notifications for trending topics
- [ ] Add sentiment analysis for news articles
- [ ] Support for RSS feeds and custom sources
- [ ] Mobile app development
- [ ] Advanced filtering and search capabilities
- [ ] Batch processing for multiple topics
- [ ] Integration with other AI models (OpenAI, Anthropic)

## 🐛 Known Issues

- Rate limiting from X API may cause delays
- News API has daily request limits
- Audio generation may take 10-30 seconds for long summaries
- Some special characters in news titles may not render correctly in audio

## 📊 Performance

- **Scraping Speed**: ~50 articles/minute
- **AI Processing**: ~5-10 seconds per summary
- **Audio Generation**: ~2-5 seconds per summary
- **API Response Time**: <30 seconds total
- **Frontend Load Time**: <1 second

## 🔐 Security Notes

- Never commit API keys to version control
- Use environment variables for sensitive configuration
- Implement rate limiting in production
- Validate and sanitize all user inputs
- Use HTTPS in production environments
