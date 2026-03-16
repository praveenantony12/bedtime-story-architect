# Bedtime Story Architect

A tiny LangGraph + Groq + Streamlit app that tells personalized bedtime stories for kids. It remembers your child's name using a LangGraph checkpointer and offers a **Sleepy Mode** that makes stories extra calm and soothing.

## Features

- **LangGraph agent**: `agent.py` defines a `BedtimeStoryAgent` that:
  - Uses Groq for text generation.
  - Maintains a `StoryState` with `child_name`, `age`, `story_prompt`, `sleepy_mode`, and `story_so_far`.
  - Uses a `MemorySaver` checkpointer so the same `thread_id` remembers the child's name and story across turns.
- **Streamlit UI**: `app.py` provides:
  - Inputs for child name, age, and story idea.
  - A **Sleepy Mode** toggle to make the story more relaxing.
  - Buttons to start a new story or continue the current one.
- **PWA manifest**: `static/manifest.json` to help browsers install the app as a pseudo-native experience (you may also want to add icons at `static/icon-192.png` and `static/icon-512.png`).

## Setup

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Set your Groq API key**

   ```bash
   export GROQ_API_KEY="your_api_key_here"
   ```

3. **Run the Streamlit app**

   ```bash
   streamlit run app.py
   ```

4. **(Optional) PWA tweaks**

   To get better PWA behavior, you may want to:

   - Serve `static/manifest.json` at `/manifest.json` or configure your deployment so that `/static/manifest.json` is discoverable via a `<link rel="manifest" href="/static/manifest.json">` tag.
   - Add app icons at:
     - `static/icon-192.png`
     - `static/icon-512.png`

## How memory works

- The LangGraph agent uses `MemorySaver` as a checkpointer.
- The Streamlit app creates a stable `thread_id` per browser session using `st.session_state`.
- That `thread_id` is passed into `agent.run_turn(...)`, so the graph can remember the child's name and the story text between turns.

