# Video Notes

Turn a video's story into your own system.

Built for GET1008 Persuasive Speech, NUS School of Computing.

## What it does

1. Paste a YouTube URL → extract transcript
2. Write your three-sentence retell (Feynman method)
3. AI reveals the "system map" — conditions, connections, trade-offs the video had to cut
4. Gap analysis: compare your notes vs the full system
5. Optional: detail quiz + ask AI

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub (public or private)
2. Go to https://share.streamlit.io and sign in with GitHub
3. Click "New app" → select this repo → Main file: `app.py`
4. In your app's **Settings > Secrets**, add:
   - `DEEPSEEK_API_KEY` = your DeepSeek API key
5. Click **Deploy**

## Local development

```bash
pip install -r requirements.txt
streamlit run app.py
```

Create `.streamlit/secrets.toml` with your API key for local testing.

## Tech stack

- Streamlit (frontend)
- youtube-transcript-api (subtitle extraction)
- DeepSeek API via openai library (LLM)
- SQLite (local archive)
