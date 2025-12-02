import streamlit as st
import requests
import base64

BACKEND_URL = "https://news-summarizer-2-xlbc.onrender.com"

def main():
    st.title("News Scrapper")

    # Initialize session state for topics if not already set
    if 'topics' not in st.session_state:
        st.session_state.topics = []

    #setup sidebar
    with st.sidebar:
        st.header("Settings")
        source_type = st.selectbox(
            "Data Sources",
            options=["both","news","X"],
            format_func=lambda x: f"{x.capitalize()}" if x == "news" else f"{x.capitalize()}"
        )

    #topic management
    st.markdown("##### Topic Management")
    col1, col2 = st.columns([4,1])
    with col1:
        new_topic = st.text_input(
            "Enter a topic to scrap",
            placeholder="e.g. AI, Climate Change, etc."
        )
    with col2:
        add_disabled = len(st.session_state.topics) >= 1 or not new_topic.strip()
        if st.button("Add Topic", disabled=add_disabled):
            st.session_state.topics.append(new_topic.strip())
            st.rerun()

    #Add or remove Topics
    if st.session_state.topics:
        st.subheader("Selected Topic")
        for i, topic in enumerate(st.session_state.topics[:3]):
            cols = st.columns([4,1])
            cols[0].write(f"{i+1}. {topic}")
            if cols[1].button("Remove", key=f"remove_{i}"):
                del st.session_state.topics[i]
                st.rerun()

    #analysis controls
    st.markdown("-------------------------")
    st.subheader("Audio Generation")

    if st.button("Generate News", disabled=len(st.session_state.topics) == 0):
        if not st.session_state.topics:
            st.error("Please add at least one topic to generate audio.")
        else:
            with st.spinner("Scraping data and Generating Audio"):
                try:
                    response = requests.post(
                        f"{BACKEND_URL}/generate-audio",
                        json={
                            "topics": st.session_state.topics,
                            "source_type": source_type
                        }
                    )
                    if response.status_code == 200:
                        data = response.json()

                        
                        # Show text summary
                        if "summary" in data:
                            st.subheader("Generated Summary")
                            st.write(data["summary"])

                        # Play audio from base64
                        if "audio" in data:
                            audio_bytes = base64.b64decode(data["audio"])
                            st.audio(audio_bytes, format="audio/mpeg")
                            st.download_button(
                                "Download Audio Summary",
                                data=audio_bytes,
                                file_name="summary.mp3",
                                type="primary"
                            )
                    else:
                        handle_api_error(response)

                except requests.exceptions.ConnectionError:
                    st.error("Failed to connect to the backend server. Please ensure the backend is running.")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {str(e)}")

def handle_api_error(response):
    """Handle API errors by displaying an error message."""
    try:
        error_detail = response.json().get("detail", "Unknown error")
        st.error(f"API Error: ({response.status_code}): {error_detail}")
    except ValueError:
        st.error(f"Unexpected error: {response.text}")



if __name__ == "__main__":
    main()
