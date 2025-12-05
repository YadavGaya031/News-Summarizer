import streamlit as st
import requests
import base64

BACKEND_URL = "https://news-summarizer-b6rs.onrender.com"
def main():
    st.set_page_config(page_title="News Scraper", page_icon="📰", layout="centered")
    st.title("📰 News Scraper & Audio Summarizer")

    # ---------- Session State: store topics across reruns ----------
    if "topics" not in st.session_state:
        st.session_state.topics = []

    # ---------- Sidebar: source type selection ----------
    with st.sidebar:
        st.header("Settings")
        source_type = st.selectbox(
            "Data Sources",
            options=["both", "news", "X"],
            format_func=lambda x: x.capitalize(),
            help="Choose whether to use News, X (Twitter), or both for summarization."
        )
        st.markdown("---")
        st.caption(
            "Tip: Repeating the same topic again and again will be cached on backend "
            "to avoid rate-limit issues."
        )

    # ---------- Topic Management UI ----------
    st.markdown("### Topic Management")

    col1, col2 = st.columns([4, 1])
    with col1:
        new_topic = st.text_input(
            "Enter a topic to scrape",
            placeholder="e.g. Ruturaj Gaikwad, AI, Climate Change..."
        )
    with col2:
        # Allow up to 3 topics; disable button accordingly
        add_disabled = len(st.session_state.topics) >= 3 or not new_topic.strip()

        if st.button("Add Topic", disabled=add_disabled):
            topic_clean = new_topic.strip()
            # Avoid duplicate topics
            if topic_clean and topic_clean not in st.session_state.topics:
                st.session_state.topics.append(topic_clean)
            # Clear text input in a simple way
            st.session_state["last_added_topic"] = topic_clean

    # Show selected topics with remove buttons
    if st.session_state.topics:
        st.subheader("Selected Topics")
        for i, topic in enumerate(st.session_state.topics):
            cols = st.columns([4, 1])
            cols[0].write(f"{i + 1}. {topic}")
            # Each remove button has a unique key
            if cols[1].button("Remove", key=f"remove_{i}"):
                del st.session_state.topics[i]
                st.rerun()

    else:
        st.info("No topics added yet. Add at least one topic to generate a summary.")

    st.markdown("---")
    st.subheader("🎧 Audio Generation")

    # ---------- Generate Button ----------
    generate_disabled = len(st.session_state.topics) == 0

    if st.button("Generate News", disabled=generate_disabled):
        if not st.session_state.topics:
            st.error("Please add at least one topic to generate audio.")
        else:
            with st.spinner("Scraping data and generating summary + audio..."):
                try:
                    # Only ONE backend call per click happens here
                    response = requests.post(
                        f"{BACKEND_URL}/generate-audio",
                        json={
                            "topics": st.session_state.topics,
                            "source_type": source_type
                        },
                        timeout=180,  # 3 minutes max timeout to be safe
                    )

                    # Handle success
                    if response.status_code == 200:
                        data = response.json()

                        # --- Show text summary ---
                        summary = data.get("summary")
                        if summary:
                            st.subheader("📝 Generated Summary")
                            st.write(summary)

                        # --- Play audio from base64 ---
                        audio_b64 = data.get("audio")
                        if audio_b64:
                            audio_bytes = base64.b64decode(audio_b64)
                            st.subheader("🎧 Audio Summary")
                            st.audio(audio_bytes, format="audio/mpeg")
                            st.download_button(
                                "Download Audio Summary",
                                data=audio_bytes,
                                file_name="summary.mp3",
                                type="primary"
                            )

                    else:
                        # Handle errors returned by backend (including 429)
                        handle_api_error(response)

                except requests.exceptions.ConnectionError:
                    st.error(
                        "Failed to connect to the backend server.\n\n"
                        "Please ensure the backend is running and the BACKEND_URL is correct."
                    )
                except requests.exceptions.Timeout:
                    st.error(
                        "The request to the backend timed out. "
                        "The summarization might be taking too long. Try again with fewer topics."
                    )
                except Exception as e:
                    st.error(f"An unexpected error occurred: {str(e)}")


def handle_api_error(response: requests.Response):
    """
    Handle non-200 API responses by showing a clear error.
    This also surfaces 429 rate-limit errors from backend / upstream APIs.
    """
    try:
        detail = response.json().get("detail", "Unknown error")
    except ValueError:
        detail = response.text or "Unknown error (non-JSON response)"

    if response.status_code == 429:
        st.error(f"Rate limit reached (429): {detail}\n\n"
                 "Please wait a few seconds and try again.")
    elif response.status_code == 400:
        st.error(f"Bad Request (400): {detail}")
    elif response.status_code == 500:
        st.error(f"Server Error (500): {detail}")
    else:
        st.error(f"API Error ({response.status_code}): {detail}")


if __name__ == "__main__":
    main()
