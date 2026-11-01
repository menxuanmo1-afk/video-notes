"""
Video Notes — Turn a video's story into your own system.
Built for GET1008 Persuasive Speech, NUS.
"""

import streamlit as st
import sqlite3
import json
import os
import re
from datetime import datetime
from openai import OpenAI

# ─── Config ───────────────────────────────────────────────────────────
DEEPSEEK_API_KEY = st.secrets.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_archive.db")

# ─── Init ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Video Notes", page_icon="📝", layout="wide")

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def get_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:v=|/v/)([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'embed/([a-zA-Z0-9_-]{11})',
        r'short/([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def fetch_transcript_yt_dlp(video_id: str) -> str:
    """Fetch transcript using yt-dlp (more resilient than youtube-transcript-api)."""
    import yt_dlp
    
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'writesubtitles': False,
        'writeautomaticsub': True,
        'subtitleslangs': ['en', 'en-US'],
    }
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    
    # Try to get subtitles
    subtitles = info.get('subtitles', {}) or {}
    automatic_captions = info.get('automatic_captions', {}) or {}
    
    # Prefer manual subtitles, fall back to auto-generated
    all_subs = {**automatic_captions, **subtitles}
    
    # Find English subtitles
    en_keys = [k for k in all_subs if k.startswith('en')]
    if not en_keys:
        raise ValueError(f"No English subtitles available for this video. Video ID: {video_id}")
    
    # Pick the first English variant
    chosen_key = en_keys[0]
    sub_entries = all_subs[chosen_key]
    
    # Get the best quality format
    if isinstance(sub_entries, list) and len(sub_entries) > 0:
        best_sub = max(sub_entries, key=lambda x: x.get('ext') == 'vtt' and 1 or 0)
    else:
        raise ValueError(f"Malformed subtitle data for {video_id}")
    
    sub_url = best_sub.get('url')
    if not sub_url:
        raise ValueError(f"Subtitle URL not found for {video_id}")
    
    # Download and parse VTT/SRT
    import urllib.request
    
    with urllib.request.urlopen(sub_url) as response:
        raw = response.read().decode('utf-8')
    
    # Strip timestamps, keep only text
    lines = []
    for line in raw.split('\n'):
        line = line.strip()
        # Skip VTT/SRT metadata (timestamps, indexes, blank lines)
        if not line or '-->' in line or re.match(r'^\d+$', line) or line.startswith('WEBVTT'):
            continue
        lines.append(line)
    
    return ' '.join(lines)


def fetch_transcript_api(video_id: str) -> str:
    """Fallback: try youtube-transcript-api."""
    from youtube_transcript_api import YouTubeTranscriptApi
    
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = transcript_list.find_manually_created_transcript(['en'])
    except Exception:
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_generated_transcript(['en'])
        except Exception:
            raise ValueError("No transcript found via API fallback either.")
    
    return ' '.join([snippet.text for snippet in transcript.fetch()])


def fetch_transcript(video_id: str) -> str:
    """Try yt-dlp first (more resilient), fall back to API."""
    try:
        return fetch_transcript_yt_dlp(video_id)
    except Exception as e1:
        try:
            return fetch_transcript_api(video_id)
        except Exception as e2:
            raise RuntimeError(f"Could not fetch transcript: {e1}; fallback also failed: {e2}")


def llm_call(system: str, user: str) -> str:
    """Call DeepSeek API."""
    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
        max_tokens=1500,
    )
    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 1)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rstrip("`").strip()
    return raw


def extract_story_skeleton(transcript: str) -> str:
    """AI extracts the narrative line the video actually tells."""
    return llm_call(
        "You are an expert at identifying the narrative structure in educational videos. "
        "Extract the STORY SKELETON — the actual narrative line the video tells, not the full knowledge system. "
        "Keep it concise (150-250 words). Focus on: what happened, in what order, and what the video wants you to feel or remember. "
        "Do NOT include conditions, exceptions, caveats, or deeper connections. Just the story.",
        f"Here is the transcript of an educational video:\n\n{transcript[:5000]}"
    )


def extract_system_map(transcript: str) -> str:
    """AI reveals the knowledge system — conditions, connections, trade-offs the video had to cut."""
    return llm_call(
        "You are an expert educator. Given a video transcript, reveal the KNOWLEDGE SYSTEM that the video could not fully cover due to algorithmic constraints. "
        "Include: (1) the key conditions and caveats the video glossed over, (2) connections between concepts that were implied but not explained, "
        "(3) common misunderstandings the video's simplified narrative might create, (4) what a real learner needs to add to turn this story into a system. "
        "Structure clearly. Be specific. ~300-500 words.",
        f"Here is the transcript of an educational video:\n\n{transcript[:5000]}"
    )


def generate_quiz(transcript: str) -> str:
    """Generate 3 detail-check questions."""
    return llm_call(
        "You are creating a short quiz to test whether someone understood the DETAILS of an educational video. "
        "Generate exactly 3 multiple-choice questions. Each question has 4 options (A-D), one correct answer, and a 1-sentence explanation. "
        "Focus on specific facts, details, and distinctions mentioned in the transcript — NOT the big picture. "
        "Format as JSON: [{\"question\": \"...\", \"options\": {\"A\": \"...\", \"B\": \"...\", \"C\": \"...\", \"D\": \"...\"}, \"answer\": \"A\", \"explanation\": \"...\"}]",
        f"Here is the transcript:\n\n{transcript[:5000]}"
    )


# ─── Database ─────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS archives (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL,
        video_id TEXT,
        title TEXT DEFAULT '',
        transcript TEXT DEFAULT '',
        story_skeleton TEXT DEFAULT '',
        system_map TEXT DEFAULT '',
        note_1 TEXT DEFAULT '',
        note_2 TEXT DEFAULT '',
        note_3 TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()


def save_archive(url, video_id, transcript, story, system_map, n1, n2, n3, title=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM archives WHERE video_id = ?", (video_id,))
    row = c.fetchone()
    if row:
        c.execute("""UPDATE archives SET url=?, title=?, transcript=?, story_skeleton=?, system_map=?,
                      note_1=?, note_2=?, note_3=?, updated_at=CURRENT_TIMESTAMP WHERE video_id=?""",
                  (url, title, transcript, story, system_map, n1, n2, n3, video_id))
    else:
        c.execute("""INSERT INTO archives (url, video_id, title, transcript, story_skeleton, system_map,
                      note_1, note_2, note_3) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (url, video_id, title, transcript, story, system_map, n1, n2, n3))
    conn.commit()
    conn.close()


def load_archives():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, url, video_id, title, note_1, note_2, note_3, created_at FROM archives ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows


# ─── App State ────────────────────────────────────────────────────────
init_db()

if "video_id" not in st.session_state:
    st.session_state.video_id = None
if "transcript" not in st.session_state:
    st.session_state.transcript = ""
if "story_skeleton" not in st.session_state:
    st.session_state.story_skeleton = ""
if "system_map" not in st.session_state:
    st.session_state.system_map = ""
if "quiz" not in st.session_state:
    st.session_state.quiz = ""
if "processing" not in st.session_state:
    st.session_state.processing = False

# ─── Custom CSS ───────────────────────────────────────────────────────
st.markdown("""
<style>
    .upload-zone {
        border: 2px dashed #555;
        border-radius: 12px;
        padding: 40px;
        text-align: center;
        background: rgba(255,255,255,0.03);
        cursor: pointer;
        transition: all 0.2s;
    }
    .upload-zone:hover {
        border-color: #888;
        background: rgba(255,255,255,0.06);
    }
    .section-title {
        font-size: 1.4rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        margin-top: 0.5rem;
    }
    .section-subtitle {
        color: #999;
        font-size: 0.9rem;
        margin-bottom: 0.5rem;
    }
    .note-box {
        background: rgba(255,255,255,0.04);
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 8px;
    }
    .gap-highlight {
        background: rgba(255, 180, 50, 0.15);
        border-left: 3px solid #ffb432;
        padding: 8px 12px;
        border-radius: 4px;
        margin: 8px 0;
    }
    .ai-response {
        background: rgba(100, 180, 255, 0.08);
        border-left: 3px solid #64b4ff;
        padding: 10px 14px;
        border-radius: 4px;
        margin: 8px 0;
    }
    textarea.st-emotion-cache { font-size: 1rem !important; }
    /* Tighten spacing between video and content */
    .element-container { margin-bottom: 0 !important; }
    div[data-testid="stVerticalBlock"] > div { padding-bottom: 0; }
</style>
""", unsafe_allow_html=True)

# ─── Sidebar: Archive Library ─────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📚 Archive Library")
    archives = load_archives()
    if archives:
        for idx, row in enumerate(archives):
            arch_id, url, vid, title, n1, n2, n3, created = row
            label = title if title else f"Video {vid[:8]}..."
            if st.button(f"{label[:30]}  \n*{created[:10]}*", key=f"arch_{idx}"):
                st.session_state.archived_row = row
                st.session_state.show_archive = True
    else:
        st.caption("No archived notes yet. Save your first one below!")

# ─── Main Area ────────────────────────────────────────────────────────

st.markdown("### 📺 Video")

if not st.session_state.video_id:
    # Step 1: Input URL
    with st.form("import_form", clear_on_submit=False):
        url_input = st.text_input(
            "Paste a YouTube URL",
            placeholder="https://www.youtube.com/watch?v=...",
        )
        submitted = st.form_submit_button("➕ Import", type="primary", use_container_width=True)
        if submitted and url_input:
            vid = get_video_id(url_input)
            if vid:
                st.session_state.video_id = vid
                st.session_state.processing = True
                st.rerun()
            else:
                st.error("Could not find a YouTube video ID in that URL.")
        elif submitted and not url_input:
            st.warning("Please paste a YouTube URL first.")
else:
    # Video is loaded — show player
    vid = st.session_state.video_id
    st.components.v1.html(
        f'<div style="position:relative;width:100%;padding-top:56.25%;max-width:960px;">'
        f'<iframe style="position:absolute;top:0;left:0;width:100%;height:100%;border:none;" '
        f'src="https://www.youtube.com/embed/{vid}?autoplay=0" '
        f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" '
        f'allowfullscreen></iframe></div>',
        height=0,
    )

    # Auto-fetch transcript
    if not st.session_state.transcript and not st.session_state.processing:
        st.session_state.processing = True
        st.rerun()

    if st.session_state.processing:
        try:
            transcript = fetch_transcript(vid)
            st.session_state.transcript = transcript
            st.session_state.processing = False
            st.rerun()
        except Exception as e:
            st.session_state.processing = False
            st.error(f"Could not auto-extract transcript: {e}")
            # Show manual fallback
            st.markdown("---")
            st.markdown("**Fallback: paste transcript manually**")
            st.caption("On YouTube: click the video ··· menu → Show transcript → copy all text → paste below")
            manual_input = st.text_area(
                "Paste transcript here",
                height=150,
                placeholder="Paste the transcript text here...",
                key="manual_fallback",
            )
            if st.button("✅ Use this transcript", type="primary"):
                if manual_input.strip():
                    st.session_state.transcript = manual_input.strip()
                    st.success(f"✅ Loaded — {len(manual_input.split())} words. Scroll down for AI features.")
                    st.rerun()
                else:
                    st.warning("Please paste some text first.")

    # ─ AI Features ──
    if st.session_state.transcript:
        transcript = st.session_state.transcript

        # Part 1: Notes
        st.markdown('<div class="section-title">✍️ Make It Yours</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-subtitle">Close the tab. Explain the idea out loud, from memory, as if teaching someone who has never seen the video — the Feynman Technique. Then write down what you got, and what it connects to in your own knowledge and experience.</div>', unsafe_allow_html=True)

        if "notes" not in st.session_state:
            st.session_state.notes = ""

        user_notes = st.text_area(
            "",
            key="notes",
            height=200,
            placeholder="What's the core idea in your own words?\nWhat does it connect to in what you already know?\nHow would you explain this to someone who hasn't watched?",
        )

        # Part 2: AI Supplement
        col_a, col_b = st.columns([1, 1])
        with col_a:
            if st.button("Reveal the System Map", type="primary", use_container_width=True):
                if not st.session_state.story_skeleton:
                    with st.spinner("Extracting story skeleton..."):
                        st.session_state.story_skeleton = extract_story_skeleton(transcript)
                if not st.session_state.system_map:
                    with st.spinner("Building the system map..."):
                        st.session_state.system_map = extract_system_map(transcript)

        with col_b:
            if st.button("Detail Quiz", use_container_width=True):
                if not st.session_state.quiz:
                    with st.spinner("Generating questions..."):
                        st.session_state.quiz = generate_quiz(transcript)

        # Show results
        if st.session_state.story_skeleton:
            st.markdown('<div class="section-title">🗺️ The System Map</div>', unsafe_allow_html=True)

            with st.expander("Story Skeleton — what the video actually gave you"):
                st.markdown(st.session_state.story_skeleton)

            with st.expander("System Map — what was left out"):
                st.markdown(st.session_state.system_map)

            if user_notes:
                with st.spinner("Finding the gaps between your notes and the system..."):
                    gap_analysis = llm_call(
                        "Compare the user's notes with the full system map. Identify 2-3 specific gaps — connections, conditions, or distinctions the user missed. "
                        "Be specific and constructive. No scores, no grades. Just: 'here's what's missing.' ~100 words.",
                        f"User's notes:\n{user_notes}\n\nSystem map:\n{st.session_state.system_map[:2000]}"
                    )
                st.markdown('<div class="section-title">🔍 Your Gaps</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="gap-highlight">{gap_analysis}</div>', unsafe_allow_html=True)

        if st.session_state.quiz:
            st.markdown('<div class="section-title">📋 Detail Check</div>', unsafe_allow_html=True)
            try:
                quiz_data = json.loads(st.session_state.quiz)
                if isinstance(quiz_data, list):
                    for i, q in enumerate(quiz_data, 1):
                        st.markdown(f"**Q{i}. {q['question']}**")
                        chosen = st.radio(
                            "",
                            [f"A) {q['options']['A']}", f"B) {q['options']['B']}",
                             f"C) {q['options']['C']}", f"D) {q['options']['D']}"],
                            key=f"quiz_q{i}",
                            index=None,
                            label_visibility="collapsed",
                        )
                        if chosen:
                            chosen_letter = chosen[0]
                            correct = chosen_letter == q['answer']
                            color = "#4caf50" if correct else "#f44336"
                            icon = "✅" if correct else "❌"
                            correct_letter = q['answer']
                            st.markdown(
                                f'<div style="background:{color}15;border-left:3px solid {color};'
                                f'padding:8px 12px;border-radius:4px;margin:8px 0 16px 0;">'
                                f'{icon} <b>{correct_letter}</b> — {q["explanation"]}</div>',
                                unsafe_allow_html=True,
                            )
                else:
                    st.markdown(st.session_state.quiz)
            except (json.JSONDecodeError, KeyError, TypeError):
                st.markdown(st.session_state.quiz)

        # Part 3: Ask AI
        st.markdown('<div class="section-title">💬 Ask AI</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-subtitle">Any question about this video. No judgment.</div>', unsafe_allow_html=True)

        ask_input = st.text_input("What don't you get yet?", key="ask_input")
        if st.button("Ask", use_container_width=True):
            if ask_input:
                with st.spinner("Thinking..."):
                    answer = llm_call(
                        f"You are helping a student understand a video. The transcript is:\n\n{transcript[:3000]}",
                        ask_input
                    )
                st.markdown(f'<div class="ai-response">{answer}</div>', unsafe_allow_html=True)

        # Archive
        st.markdown("---")
        if st.button("💾 Archive this video + notes", type="primary", use_container_width=True):
            save_archive(
                url=f"https://youtube.com/watch?v={vid}",
                video_id=vid,
                transcript=transcript[:10000],
                story=st.session_state.story_skeleton,
                system_map=st.session_state.system_map,
                n1=user_notes[:500] if user_notes else "",
                n2="",
                n3="",
            )
            st.success("Archived! Find it in the sidebar.")
