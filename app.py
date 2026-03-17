import base64
import json
import os
import re
import uuid
from io import BytesIO

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from PIL import Image, ImageDraw

from agent import get_agent

load_dotenv()

APP_TITLE = "Dream Story Time"
SESSION_FILE = ".story_session.json"


# ── Persistence ───────────────────────────────────────────────────────────────

def _read_json(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _write_json(path: str, data: dict) -> None:
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def save_session() -> None:
    _write_json(SESSION_FILE, {
        "child_name": st.session_state.get("child_name", ""),
        "age": int(st.session_state.get("age", 6)),
        "thread_id": st.session_state.get("thread_id", ""),
        "phase": st.session_state.get("phase", "greeting"),
        "story_so_far": st.session_state.get("story_so_far", ""),
        "current_question": st.session_state.get("current_question", ""),
        "current_narration": st.session_state.get("current_narration", ""),
        "current_image_prompt": st.session_state.get("current_image_prompt", ""),
        "current_image_b64": st.session_state.get("current_image_b64", ""),
        "last_fetched_prompt": st.session_state.get("last_fetched_prompt", ""),
        "greeting_done": st.session_state.get("greeting_done", False),
        "is_ending": st.session_state.get("is_ending", False),
        "moral": st.session_state.get("moral", ""),
        "goodnight": st.session_state.get("goodnight", ""),
    })


def save_profile_to_local_storage(child_name: str, age: int) -> None:
    payload_name = json.dumps(child_name)
    payload_age = json.dumps(str(age))
    components.html(
        f"""<!doctype html><html><body><script>
        (function() {{
          const pw = window.parent;
          pw.localStorage.setItem('bst_child_name', {payload_name});
          pw.localStorage.setItem('bst_child_age', {payload_age});
        }})();
        </script></body></html>""",
        height=0,
    )


def bootstrap_profile_from_local_storage() -> None:
    if st.query_params.get("profile_loaded", ""):
        return
    components.html(
        """<!doctype html><html><body><script>
        (function() {
          const pw = window.parent;
                    const pd = pw.document;
                    function navigateTo(url) {
                        const s = pd.createElement('script');
                        s.textContent = 'window.location.href=' + JSON.stringify(url) + ';';
                        pd.head.appendChild(s);
                        s.remove();
                    }
          const url = new URL(pw.location.href);
          if (url.searchParams.get('profile_loaded')) return;
          const n = pw.localStorage.getItem('bst_child_name') || '';
          const a = pw.localStorage.getItem('bst_child_age') || '';
          if (n) url.searchParams.set('profile_name', n);
          if (a) url.searchParams.set('profile_age', a);
          url.searchParams.set('profile_loaded', 'one');
                    navigateTo(url.toString());
        })();
        </script></body></html>""",
        height=0,
    )
    st.stop()


def close_profile_expander() -> None:
        components.html(
                """<!doctype html><html><body><script>
                (function() {
                    const pw = window.parent;
                    const pd = pw.document;
                    const expanders = pd.querySelectorAll('details[data-testid="stExpander"]');
                    expanders.forEach((el) => {
                        const summary = el.querySelector('summary');
                        const text = (summary && summary.textContent || '').trim();
                        if (text === 'Profile') {
                            el.removeAttribute('open');
                        }
                    });
                })();
                </script></body></html>""",
                height=0,
        )


def ensure_session_defaults(
    voice_input: str = "",
    profile_name: str = "",
    profile_age: str = "",
) -> None:
    """
    Called once per Python session (not per rerun).
    Distinguishes between a fresh browser open vs a URL-param voice-navigation reload.
    `voice_input` must be passed in since the query param is consumed before this call.
    """
    if "session_loaded" in st.session_state:
        return

    sess = _read_json(SESSION_FILE)
    is_voice_nav = bool(voice_input)

    clean_name = (profile_name or "").strip() or (sess.get("child_name", "") or "").strip()

    if profile_age:
        try:
            clean_age = int(profile_age)
        except Exception:
            clean_age = int(sess.get("age", 6) or 6)
    else:
        clean_age = int(sess.get("age", 6) or 6)
    clean_age = max(3, min(12, clean_age))

    st.session_state["child_name"] = clean_name
    st.session_state["age"] = clean_age
    st.session_state["thread_id"] = sess.get("thread_id") or str(uuid.uuid4())
    st.session_state["profile_set"] = bool(clean_name)

    if is_voice_nav:
        # Mid-story page reload — restore conversation state from disk
        st.session_state["phase"] = sess.get("phase", "greeting")
        st.session_state["story_so_far"] = sess.get("story_so_far", "")
        st.session_state["current_question"] = sess.get("current_question", "")
        st.session_state["current_narration"] = sess.get("current_narration", "")
        st.session_state["current_image_prompt"] = sess.get("current_image_prompt", "")
        st.session_state["current_image_b64"] = sess.get("current_image_b64", "")
        st.session_state["last_fetched_prompt"] = sess.get("last_fetched_prompt", "")
        st.session_state["greeting_done"] = sess.get("greeting_done", False)
        st.session_state["is_ending"] = sess.get("is_ending", False)
        st.session_state["moral"] = sess.get("moral", "")
        st.session_state["goodnight"] = sess.get("goodnight", "")
        st.session_state["has_shown_voice"] = True  # no delay after voice nav
    else:
        # Fresh open — start a clean story session (profile is preserved)
        st.session_state["phase"] = "greeting"
        st.session_state["story_so_far"] = ""
        st.session_state["current_question"] = ""
        st.session_state["current_narration"] = ""
        st.session_state["current_image_prompt"] = ""
        st.session_state["current_image_b64"] = ""
        st.session_state["last_fetched_prompt"] = ""
        st.session_state["greeting_done"] = False
        st.session_state["is_ending"] = False
        st.session_state["moral"] = ""
        st.session_state["goodnight"] = ""
        st.session_state["has_shown_voice"] = False

    st.session_state["session_loaded"] = True


# ── CSS ────────────────────────────────────────────────────────────────────────

def inject_css() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fredoka+One&family=Nunito:wght@400;700;900&display=swap');

html, body, [class*="css"] { font-family: 'Nunito', sans-serif; }

.stApp {
    background: radial-gradient(ellipse at 20% 0%, #1a1060 0%, #0d0820 40%, #030212 100%);
    min-height: 100vh;
}
.main .block-container {
    padding-top: 1.5rem;
    padding-bottom: 7rem;  /* leave room for fixed bottom FAB */
    max-width: 780px;
}
#MainMenu, footer, header { visibility: hidden; }

.welcome-card {
    background: linear-gradient(135deg, #1e1060 0%, #2d1b8e 50%, #1a0f5c 100%);
    border: 2px solid #7c5cbf;
    border-radius: 28px;
    padding: 2.5rem 2rem;
    box-shadow: 0 0 60px rgba(150,100,255,0.3);
    text-align: center;
}
.welcome-title {
    font-family: 'Fredoka One', cursive;
    font-size: 3rem;
    color: #f9e4ff;
    text-shadow: 0 0 30px rgba(220,150,255,0.8);
    margin-bottom: 0.3rem;
}
.welcome-subtitle { font-size: 1.1rem; color: #c8a8f0; margin-bottom: 2rem; }

.stTextInput input, .stNumberInput input {
    background: rgba(255,255,255,0.07) !important;
    border: 2px solid #7c5cbf !important;
    border-radius: 16px !important;
    color: #f0e6ff !important;
    font-size: 1.1rem !important;
    padding: 0.7rem 1rem !important;
    font-family: 'Nunito', sans-serif !important;
}
.stTextInput input:focus, .stNumberInput input:focus {
    border-color: #c084fc !important;
    box-shadow: 0 0 15px rgba(192,132,252,0.4) !important;
}
label, .stTextInput label, .stNumberInput label {
    color: #d8b4fe !important; font-size: 1rem !important; font-weight: 700 !important;
}

.stButton > button {
    background: linear-gradient(135deg, #7c3aed, #a855f7) !important;
    color: white !important;
    border: none !important;
    border-radius: 50px !important;
    font-family: 'Fredoka One', cursive !important;
    font-size: 1.2rem !important;
    padding: 0.7rem 2rem !important;
    box-shadow: 0 6px 20px rgba(139,92,246,0.5) !important;
    transition: transform 0.15s, box-shadow 0.15s !important;
    cursor: pointer !important;
}
.stButton > button:hover {
    transform: translateY(-2px) scale(1.03) !important;
    box-shadow: 0 10px 30px rgba(139,92,246,0.7) !important;
}

/* Scene image */
[data-testid="stImage"] {
    border-radius: 20px;
    overflow: hidden;
    border: 3px solid #7c5cbf;
    box-shadow: 0 0 40px rgba(150,100,255,0.4);
    margin: 0.8rem 0;
    display: block;
}
[data-testid="stImage"] img {
    width: 100% !important;
    display: block !important;
    border-radius: 17px;
    animation: sceneFadeIn .6s ease;
}
@keyframes sceneFadeIn {
    0%   { opacity: 0; transform: perspective(1000px) rotateY(-90deg) scale(0.85); }
    55%  { opacity: 1; transform: perspective(1000px) rotateY(8deg)   scale(1.01); }
    80%  { transform: perspective(1000px) rotateY(-3deg) scale(1); }
    100% { opacity: 1; transform: perspective(1000px) rotateY(0deg)   scale(1); }
}
.question-bubble {
    background: linear-gradient(135deg, #0f4c75 0%, #1a6fa8 100%);
    border: 1.5px solid #38bdf8;
    border-radius: 20px 20px 20px 0;
    padding: 0.8rem 1.2rem;
    margin: 0.4rem 0 0.6rem 0;
    color: #e0f7ff;
    font-size: 1rem;
    line-height: 1.5;
}
.goodnight-card {
    background: linear-gradient(135deg, #1a0a2e 0%, #280a52 100%);
    border: 2px solid #a855f7;
    border-radius: 24px;
    padding: 2rem;
    text-align: center;
    box-shadow: 0 0 50px rgba(168,85,247,0.4);
    margin: 1rem 0;
}
.goodnight-card .moral { font-size: 1.1rem; color: #e9d5ff; font-style: italic; margin-bottom: 1rem; }
.goodnight-card .message {
    font-family: 'Fredoka One', cursive;
    font-size: 1.6rem;
    color: #f9e4ff;
    text-shadow: 0 0 20px rgba(220,150,255,0.7);
}

.stars {
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    pointer-events: none; z-index: 0;
    background-image:
      radial-gradient(1px 1px at 10% 15%, #fff 0%, transparent 100%),
      radial-gradient(1px 1px at 30% 5%, #fff 0%, transparent 100%),
      radial-gradient(1.5px 1.5px at 55% 25%, #fff 0%, transparent 100%),
      radial-gradient(1px 1px at 75% 10%, #fff 0%, transparent 100%),
      radial-gradient(1px 1px at 20% 50%, #fff 0%, transparent 100%),
      radial-gradient(1px 1px at 45% 60%, #fff 0%, transparent 100%),
      radial-gradient(1px 1px at 65% 45%, #fff 0%, transparent 100%),
      radial-gradient(1.5px 1.5px at 5% 80%, #fff 0%, transparent 100%),
      radial-gradient(1px 1px at 80% 90%, #fff 0%, transparent 100%);
}
hr { border-color: rgba(124,92,191,0.3); }
.stSpinner > div { color: #c084fc !important; }
</style>
<div class="stars"></div>
        """,
        unsafe_allow_html=True,
    )


# ── Image creation ─────────────────────────────────────────────────────────────

@st.cache_data
def create_story_image(image_prompt: str) -> bytes:
    import random

    W, H = 900, 480
    rng = random.Random(abs(hash(image_prompt)))

    # ── Pick palette based on prompt keywords ──────────────────────────
    p = image_prompt.lower()
    if any(w in p for w in ("ocean", "sea", "beach", "wave", "island")):
        sky0, sky1 = (5, 15, 60), (10, 40, 100)
        ground0, ground1 = (5, 60, 80), (5, 30, 50)
        accent = (80, 200, 255)
    elif any(w in p for w in ("castle", "kingdom", "tower", "magic", "wizard")):
        sky0, sky1 = (20, 5, 60), (50, 10, 100)
        ground0, ground1 = (25, 10, 45), (15, 5, 30)
        accent = (200, 120, 255)
    elif any(w in p for w in ("forest", "tree", "jungle", "wood", "enchanted")):
        sky0, sky1 = (5, 20, 50), (10, 50, 60)
        ground0, ground1 = (10, 40, 20), (5, 25, 10)
        accent = (100, 240, 140)
    elif any(w in p for w in ("desert", "sand", "dune", "pyramid", "oasis")):
        sky0, sky1 = (40, 20, 60), (100, 50, 20)
        ground0, ground1 = (120, 80, 30), (80, 50, 15)
        accent = (255, 200, 100)
    else:  # default: moonlit night
        sky0, sky1 = (8, 10, 55), (25, 15, 75)
        ground0, ground1 = (15, 10, 40), (8, 6, 28)
        accent = (180, 140, 255)

    img  = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    def lerp(a, b, t):
        return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))

    # Sky gradient
    horizon = int(H * 0.58)
    for y in range(horizon):
        draw.line([(0, y), (W, y)], fill=lerp(sky0, sky1, y / horizon))

    # Ground gradient
    for y in range(horizon, H):
        t = (y - horizon) / (H - horizon)
        draw.line([(0, y), (W, y)], fill=lerp(ground0, ground1, t))

    # ── Stars ───────────────────────────────────────────────────────────────────
    for _ in range(80):
        sx = rng.randint(0, W)
        sy = rng.randint(0, horizon - 20)
        rs = rng.choice([1, 1, 1, 2, 2, 3])
        br = rng.randint(160, 255)
        draw.ellipse([(sx - rs, sy - rs), (sx + rs, sy + rs)], fill=(br, br, min(br + 30, 255)))

    # ── Moon ───────────────────────────────────────────────────────────────────────
    mx, my, mr = W - 100, 55, 34
    # Glow
    for g in range(20, 0, -1):
        gc = lerp(sky0, (255, 240, 150), g / 20)
        draw.ellipse([(mx - mr - g, my - mr - g), (mx + mr + g, my + mr + g)], fill=gc)
    # Moon disk
    draw.ellipse([(mx - mr, my - mr), (mx + mr, my + mr)], fill=(255, 245, 180))
    # Crescent shadow
    draw.ellipse([(mx - mr + 16, my - mr - 8), (mx + mr + 14, my + mr - 8)], fill=lerp(sky0, sky1, 0.3))

    # ── Distant mountains ─────────────────────────────────────────────────────────
    def mountain_row(peaks, base_y, fill_top, fill_bot):
        pts = [(0, H)]
        for px, py in peaks:
            pts.append((px, py))
        pts.append((W, H))
        # Fill with gradient by drawing horizontal lines
        for i in range(len(peaks) - 1):
            x0, y0 = peaks[i]
            x1, y1 = peaks[i + 1]
            # Simple triangle fill
            for x in range(x0, x1 + 1):
                t_x = (x - x0) / max(x1 - x0, 1)
                edge_y = int(y0 * (1 - t_x) + y1 * t_x)
                for y in range(edge_y, H):
                    t_y = (y - edge_y) / max(H - edge_y, 1)
                    draw.point((x, y), fill=lerp(fill_top, fill_bot, t_y))

    mtn_color_top = lerp(sky1, ground0, 0.5)
    mtn_color_bot = ground0
    # Back mountains (wider, taller)
    peaks_back = [(0, horizon - 60), (120, horizon - 130), (250, horizon - 90),
                  (400, horizon - 160), (540, horizon - 110), (680, horizon - 145),
                  (820, horizon - 80), (W, horizon - 50)]
    mountain_row(peaks_back, horizon, mtn_color_top, mtn_color_bot)

    # Front hills (shorter, darker)
    hill_color = lerp(ground0, ground1, 0.4)
    peaks_front = [(0, horizon + 10), (80, horizon - 30), (200, horizon - 50),
                   (350, horizon - 35), (500, horizon - 55), (650, horizon - 30),
                   (800, horizon - 45), (W, horizon + 5)]
    mountain_row(peaks_front, horizon, hill_color, ground1)

    # ── Tree silhouettes ────────────────────────────────────────────────────────────
    tree_dark = lerp(ground1, (0, 0, 0), 0.3)
    tree_mid  = lerp(ground0, (0, 0, 0), 0.2)
    tree_positions = [(int(x), rng.randint(50, 90)) for x in range(0, W + 40, rng.randint(28, 48))]
    for tx, th in tree_positions:
        base_y = H - rng.randint(0, 30)
        # Trunk
        tw2 = max(3, th // 8)
        draw.rectangle([(tx - tw2, base_y - th // 3), (tx + tw2, base_y)], fill=tree_dark)
        # Three tiered triangles
        for tier, (scale, offset) in enumerate([(1.0, 0), (0.7, th // 4), (0.45, th // 2)]):
            half = int(th * 0.38 * scale)
            tip_y = base_y - th + int(th * 0.15 * tier) - offset
            draw.polygon([
                (tx - half, base_y - th // 3 + offset),
                (tx + half, base_y - th // 3 + offset),
                (tx, tip_y)
            ], fill=lerp(tree_dark, tree_mid, tier * 0.3))

    # ── Glowing window / element ───────────────────────────────────────────────────────
    # Small cozy lit window in a random tree gap
    wx = rng.randint(W // 4, 3 * W // 4)
    wy = H - rng.randint(90, 150)
    for glow in range(16, 0, -1):
        gc2 = lerp(ground1, (255, 220, 100), glow / 16)
        draw.ellipse([(wx - glow * 2, wy - glow), (wx + glow * 2, wy + glow)], fill=gc2)
    draw.rectangle([(wx - 8, wy - 6), (wx + 8, wy + 6)], fill=(255, 230, 120))
    draw.line([(wx, wy - 6), (wx, wy + 6)], fill=(180, 130, 60), width=1)
    draw.line([(wx - 8, wy), (wx + 8, wy)], fill=(180, 130, 60), width=1)

    # ── Subtle vignette ──────────────────────────────────────────────────────────────────
    for v in range(1, 8):
        alpha_approx = int(30 * v / 8)
        c = (alpha_approx // 4, alpha_approx // 4, alpha_approx // 4)
        draw.rectangle([(v * 3, v * 2), (W - v * 3, H - v * 2)], outline=c, width=2)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── AI image generation ───────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=86400)
def fetch_story_image(image_prompt: str) -> bytes:
    """
    Generate a real AI image for the story scene.

    - If HF_TOKEN is set in .env: uses HuggingFace FLUX.1-schnell (free tier,
      ~100 requests/day, no credit card required).
    - Otherwise: renders a beautiful hand-crafted PIL landscape scene.

    Results are cached for 24 h so the same scene never refetches.
    Add HF_TOKEN=hf_... to your .env for real AI illustrations.
    """
    hf_token = os.environ.get("HF_TOKEN", "")
    if hf_token:
        try:
            from huggingface_hub import InferenceClient
            client = InferenceClient(token=hf_token)
            style = (
                "children's book illustration, magical whimsical digital painting, "
                "soft warm lighting, vivid colors, dreamlike, bedtime story art, "
                "no text, no watermark, no letters"
            )
            full_prompt = f"{image_prompt}. {style}"[:400]
            pil_img = client.text_to_image(
                full_prompt,
                model="black-forest-labs/FLUX.1-schnell",
                width=800,
                height=448,
            )
            buf = BytesIO()
            pil_img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            pass  # fall through to PIL

    # Fallback: local PIL atmospheric scene
    return create_story_image(image_prompt)


# ── TTS text cleanup ───────────────────────────────────────────────────────────

def clean_for_tts(text: str) -> str:
    """Remove characters that voice synthesisers read aloud awkwardly."""
    # Strip common emoji Unicode blocks
    text = re.sub(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
        r"\U0001F1E0-\U0001F1FF\U00002700-\U000027BF\U0001F900-\U0001F9FF"
        r"\u2600-\u26FF\u2700-\u27BF]",
        "",
        text,
    )
    text = re.sub(r"[*#@~`<>{}|\\^]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── Voice system (TTS + STT injected into the top-level page) ─────────────────

def voice_inject(
    text_to_speak: str,
    is_idle: bool = False,
    auto_start: bool = False,
    is_continuous: bool = False,
    force_reset: bool = False,
) -> None:
    clean = (
        clean_for_tts(text_to_speak)
        .replace("\\", "\\\\")
        .replace("`", "'")
        .replace('"', "'")
        .replace("\n", " ")
    )
    auto_js    = "true" if auto_start else "false"
    is_idle_js = "true" if is_idle else "false"
    is_cont_js = "true" if is_continuous else "false"
    force_reset_js = "true" if force_reset else "false"

    bridge_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
<script>
(function(){{
  const TEXT        = `{clean}`;
  const AUTO        = {auto_js};
  const IS_IDLE     = {is_idle_js};
  const IS_CONT     = {is_cont_js};   // continuous mode: auto-listen after TTS
    const FORCE_RESET = {force_reset_js};
  const pw = window.parent;
  const pd = pw.document;

  // ── Parent-context navigation (script-injection trick) ───────────────
  function navigateTo(url) {{
    const s = pd.createElement('script');
    s.textContent = 'window.location.href=' + JSON.stringify(url) + ';';
    pd.head.appendChild(s); s.remove();
  }}

  function sendVoice(text) {{
    setFab('sending', '✓');
    setLbl(text === '__CONTINUE__' ? 'Next...' : 'Got it!');
    pw.speechSynthesis && pw.speechSynthesis.cancel();
        const name = pw.localStorage.getItem('bst_child_name') || '';
        const age = pw.localStorage.getItem('bst_child_age') || '';
        const p = new URLSearchParams();
        p.set('voice_input', text);
        if (name) p.set('profile_name', name);
        if (age) p.set('profile_age', age);
        p.set('profile_loaded', 'one');
        navigateTo(pw.location.href.split('?')[0] + '?' + p.toString());
  }}

  function setFab(cls, html) {{
    const f = pd.getElementById('__sfab'); if (f) {{ f.className = cls; f.innerHTML = html; }}
  }}
  function setLbl(t) {{
    const l = pd.getElementById('__sfab-lbl'); if (l) l.textContent = t;
  }}

    if (FORCE_RESET) {{
        try {{ pw.speechSynthesis && pw.speechSynthesis.cancel(); }} catch(_) {{}}
        if (pw.__storyRec) {{ try {{ pw.__storyRec.abort(); }} catch(_) {{}} pw.__storyRec = null; }}
        const oldFab = pd.getElementById('__sfab');
        const oldLbl = pd.getElementById('__sfab-lbl');
        const oldCss = pd.getElementById('__sfab-css');
        if (oldFab) oldFab.remove();
        if (oldLbl) oldLbl.remove();
        if (oldCss) oldCss.remove();
        pw.__storyGo = null;
        pw.__storyInstalled = false;
    }}

  // ── Install FAB + styles once ─────────────────────────────────────────
  if (!pw.__storyInstalled) {{
    pw.__storyInstalled = true;

    const css = pd.createElement('style');
    css.id = '__sfab-css';
    css.textContent = `
      #__sfab {{
        position:fixed; bottom:28px; left:50%; transform:translateX(-50%);
        z-index:99999; min-width:90px; height:70px; padding:0 24px;
        border-radius:35px; border:3px solid rgba(255,255,255,.18);
        cursor:pointer; outline:none;
        display:flex; align-items:center; justify-content:center; gap:8px;
        font-family:'Fredoka One',cursive; font-weight:700;
        font-size:1.3rem; color:#fff; letter-spacing:.05em;
        transition:background .3s, box-shadow .3s, transform .12s;
      }}
      #__sfab:active {{ transform:translateX(-50%) scale(.93) !important; }}
      #__sfab.idle {{
        background:linear-gradient(135deg,#15803d,#22c55e);
        box-shadow:0 6px 28px rgba(34,197,94,.7);
        animation:__fpulse 1.8s ease-in-out infinite;
      }}
      #__sfab.playing {{
        background:linear-gradient(135deg,#7c3aed,#a855f7);
        box-shadow:0 6px 28px rgba(139,92,246,.7);
        animation:__fsoft 2.2s ease-in-out infinite;
      }}
      #__sfab.listening {{
        background:linear-gradient(135deg,#b91c1c,#ef4444);
        box-shadow:0 6px 28px rgba(239,68,68,.8);
        animation:__ffast .7s ease-in-out infinite;
      }}
      #__sfab.sending {{
        background:linear-gradient(135deg,#374151,#6b7280);
        box-shadow:0 3px 12px rgba(107,114,128,.4);
        animation:none;
      }}
      #__sfab-lbl {{
        position:fixed; bottom:110px; left:50%; transform:translateX(-50%);
        z-index:99999; background:rgba(12,6,28,.92); color:#d8b4fe;
        font-family:'Nunito',sans-serif; font-size:.8rem; font-weight:700;
        padding:4px 16px; border-radius:20px; white-space:nowrap;
        pointer-events:none; letter-spacing:.04em;
      }}
      @keyframes __fpulse {{
        0%,100% {{ transform:translateX(-50%) scale(1);    box-shadow:0 6px 28px rgba(34,197,94,.5); }}
        50%      {{ transform:translateX(-50%) scale(1.07); box-shadow:0 12px 48px rgba(34,197,94,1); }}
      }}
      @keyframes __fsoft {{
        0%,100% {{ transform:translateX(-50%) scale(1);    box-shadow:0 6px 28px rgba(139,92,246,.4); }}
        50%      {{ transform:translateX(-50%) scale(1.03); box-shadow:0 10px 40px rgba(139,92,246,.9); }}
      }}
      @keyframes __ffast {{
        0%,100% {{ transform:translateX(-50%) scale(1);    box-shadow:0 6px 28px rgba(239,68,68,.5); }}
        50%      {{ transform:translateX(-50%) scale(1.05); box-shadow:0 10px 40px rgba(239,68,68,1); }}
      }}
    `;
    pd.head.appendChild(css);

    const fab = pd.createElement('button');
    fab.id = '__sfab'; fab.className = 'idle';
    fab.innerHTML = 'START';
    fab.setAttribute('aria-label', 'Start or stop the story');
    pd.body.appendChild(fab);

    const lbl = pd.createElement('div');
    lbl.id = '__sfab-lbl'; lbl.textContent = 'Tap to begin!';
    pd.body.appendChild(lbl);

    const synth = pw.speechSynthesis;
    const SR    = pw.SpeechRecognition || pw.webkitSpeechRecognition;

    function pickVoice() {{
      const vs = synth.getVoices();
      return vs.find(x => x.name === 'Samantha')
          || vs.find(x => x.name.includes('Google') && x.lang === 'en-US')
          || vs.find(x => x.lang === 'en-US' && x.localService)
          || vs.find(x => x.lang.startsWith('en') && x.localService)
          || vs.find(x => x.lang.startsWith('en'));
    }}

    function speak(text, cb) {{
      synth.cancel();
      if (!text || !text.trim()) {{ cb && cb(); return; }}
      const u = new pw.SpeechSynthesisUtterance(text);
      u.rate = 0.82; u.pitch = 1.25; u.volume = 1.0;
      u.onstart = () => {{ setFab('playing', 'STOP'); setLbl('Tap to interrupt'); }};
      u.onend   = () => {{ setTimeout(() => cb && cb(), 400); }};
      u.onerror = () => {{ cb && cb(); }};
      function doSpeak() {{ const v = pickVoice(); if (v) u.voice = v; synth.speak(u); }}
      if (synth.getVoices().length > 0) doSpeak();
      else {{ synth.onvoiceschanged = () => {{ synth.onvoiceschanged = null; doSpeak(); }}; setTimeout(doSpeak, 500); }}
    }}

    // Listen then send result (or __CONTINUE__ on timeout)
    // timeoutMs = 0 means listen until kid speaks (no auto-continue)
    function listenThen(timeoutMs) {{
      if (!SR) {{ sendVoice('__CONTINUE__'); return; }}
      let done = false;
      let timer = null;
      const rec = new SR();
      pw.__storyRec = rec;
      rec.lang = 'en-US'; rec.continuous = false; rec.interimResults = false;
      setFab('listening', '&#127908;'); setLbl(timeoutMs ? 'Say something...' : 'Your turn!');

      function finish(txt) {{
        if (done) return; done = true;
        clearTimeout(timer);
        pw.__storyRec = null;
        try {{ rec.abort(); }} catch(_) {{}}
        const result = (txt || '').trim();
        if (result) sendVoice(result);
        else if (timeoutMs) sendVoice('__CONTINUE__');
                else {{ setFab('idle', 'START'); setLbl('Tap to answer'); }}  // wait until kid speaks
      }}
      rec.onresult = (e) => finish(e.results[0][0].transcript);
            rec.onerror  = (e) => {{
                const err = (e && e.error) || '';
                if (err === 'no-speech') return;  // timeout handles this
                if (err === 'not-allowed' || err === 'service-not-allowed' || err === 'audio-capture') {{
                    done = true;
                    clearTimeout(timer);
                    pw.__storyRec = null;
                    setFab('idle', 'START');
                    setLbl('Please allow microphone');
                    return;
                }}
                finish('');
            }};
      rec.onend    = () => {{ if (!done) finish(''); }};
      try {{
        rec.start();
        if (timeoutMs) timer = setTimeout(() => finish(''), timeoutMs);
            }} catch(err) {{
                done = true;
                clearTimeout(timer);
                pw.__storyRec = null;
                setFab('idle', 'START');
                setLbl('Tap to try again');
            }}
    }}

    pw.__storyGo = function() {{
            speak(pw.__storyText || '', () => listenThen(pw.__storyCont ? 5000 : 0));
    }};

    // ── FAB click logic ───────────────────────────────────────────────────
    fab.addEventListener('click', () => {{
      const cls = pd.getElementById('__sfab').className;
      // Small delay so initial dialogue isn't clipped by the browser
      if (cls === 'idle')   {{ setTimeout(() => pw.__storyGo && pw.__storyGo(), 800); return; }}
      if (cls === 'playing') {{
        // Tap STOP → immediately switch to START and say goodbye
        synth.cancel();
        if (pw.__storyRec) {{ try {{ pw.__storyRec.abort(); }} catch(_) {{}} pw.__storyRec = null; }}
        setFab('idle', 'START');
        setLbl('See you next time! 🌙');
        const byeU = new pw.SpeechSynthesisUtterance('Sweet dreams! Tap start whenever you want another adventure!');
        byeU.rate = 0.82; byeU.pitch = 1.25; byeU.volume = 1.0;
        function doGoodbye() {{
          const v = pickVoice(); if (v) byeU.voice = v;
                    byeU.onend = byeU.onerror = () => sendVoice('__STOP__');
          synth.speak(byeU);
        }}
        if (synth.getVoices().length > 0) doGoodbye();
        else {{ synth.onvoiceschanged = () => {{ synth.onvoiceschanged = null; doGoodbye(); }}; setTimeout(doGoodbye, 500); }}
        return;
      }}
      if (cls === 'listening') {{
        if (pw.__storyRec) {{ try {{ pw.__storyRec.abort(); }} catch(_) {{}} pw.__storyRec = null; }}
        sendVoice('__CONTINUE__');
        return;
      }}
    }});

  }} // end install-once

  // ── Per-render: update text, continuous flag, and FAB state ──────────
  pw.__storyText = TEXT;
  pw.__storyCont = IS_CONT;

  const fab = pd.getElementById('__sfab');
  const lbl = pd.getElementById('__sfab-lbl');
  // Only reset FAB visual if not mid-interaction
    if (fab && !['playing','listening'].includes(fab.className)) {{
    if (IS_IDLE) {{
      fab.className = 'idle'; fab.innerHTML = 'START';
      if (lbl) lbl.textContent = 'Tap to begin!';
    }} else {{
      fab.className = 'playing'; fab.innerHTML = 'STOP';
      if (lbl) lbl.textContent = 'Tap to interrupt';
    }}
  }}

  // Slightly longer delay on auto-play so the browser audio context is fully ready
  if (AUTO) setTimeout(() => pw.__storyGo && pw.__storyGo(), 800);

}})();
</script></body></html>"""

    components.html(bridge_html, height=0)


# ── State helpers ──────────────────────────────────────────────────────────────

def _apply_state(state: dict) -> None:
    """Write agent turn output into session state."""
    new_phase    = state.get("phase", st.session_state.get("phase", "greeting"))
    narration    = state.get("narration", "")
    image_prompt = state.get("image_prompt", "a magical scene under the stars")
    question     = state.get("question_for_kid", "")
    moral        = state.get("moral", "")
    goodnight    = state.get("goodnight_message", "")
    is_ending    = new_phase == "ending"

    if new_phase == "storytelling":
        st.session_state["story_so_far"] = state.get(
            "story_so_far", st.session_state.get("story_so_far", "")
        )

    st.session_state["phase"]               = new_phase
    st.session_state["current_question"]    = question
    st.session_state["current_narration"]   = narration
    st.session_state["current_image_prompt"] = image_prompt
    st.session_state["greeting_done"]       = True
    st.session_state["is_ending"]           = is_ending
    st.session_state["moral"]               = moral
    st.session_state["goodnight"]           = goodnight


def _clear_story_state() -> None:
    """Reset story for a new adventure (keep profile)."""
    st.session_state.update({
        "phase": "greeting",
        "story_so_far": "",
        "current_question": "",
        "current_narration": "",
        "current_image_prompt": "",
        "current_image_b64": "",
        "last_fetched_prompt": "",
        "greeting_done": False,
        "is_ending": False,
        "moral": "",
        "goodnight": "",
        "has_shown_voice": False,
    })
    _write_json(SESSION_FILE, {})


def run_agent_turn(agent, thread_id, phase, child_name, age, kid_input, story_so_far):
    return agent.run_turn(
        thread_id=thread_id,
        child_name=child_name,
        age=age,
        phase=phase,
        kid_input=kid_input,
        story_so_far=story_so_far,
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="static/icon-192.png", layout="centered")
    inject_css()
    bootstrap_profile_from_local_storage()

    # Read (and immediately clear) any incoming voice input from URL
    # IMPORTANT: must happen BEFORE ensure_session_defaults so the is_voice_nav
    # check inside that function sees the param on its first run.
    voice_input: str = st.query_params.get("voice_input", "")
    profile_name: str = st.query_params.get("profile_name", "")
    profile_age: str = st.query_params.get("profile_age", "")
    if voice_input:
        try:
            del st.query_params["voice_input"]
        except Exception:
            pass

    ensure_session_defaults(voice_input, profile_name, profile_age)

    if not os.environ.get("GROQ_API_KEY"):
        st.error("GROQ_API_KEY is not set. Please set it in your environment.")
        return

    agent = get_agent()

    # ── SCREEN 1: Profile entry (only on very first launch) ──────────────────
    if not st.session_state["profile_set"]:
        st.markdown(
            """
            <div class="welcome-card">
              <div class="welcome-title">&#127769; Dream Story Time</div>
              <div class="welcome-subtitle">A magical bedtime adventure just for you!</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("What's your name?", placeholder="e.g. Mia")
        with col2:
            age_val = st.number_input(
                "How old are you?", min_value=3, max_value=12,
                value=int(st.session_state.get("age", 6)), step=1,
            )
        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("Let's Begin! ✨", type="primary", use_container_width=True):
            if name.strip():
                tid = str(uuid.uuid4())
                st.session_state.update({
                    "child_name": name.strip(),
                    "age": int(age_val),
                    "thread_id": tid,
                    "profile_set": True,
                    "phase": "greeting",
                    "story_so_far": "",
                    "current_question": "",
                    "current_narration": "",
                    "current_image_prompt": "",
                    "greeting_done": False,
                    "is_ending": False,
                    "moral": "",
                    "goodnight": "",
                    "has_shown_voice": False,
                })
                save_profile_to_local_storage(name.strip(), int(age_val))
                save_session()
                st.rerun()
        return

    child_name: str = st.session_state["child_name"]
    age: int = int(st.session_state["age"])
    thread_id: str = st.session_state["thread_id"]

    # ── HEADER ───────────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="text-align:center;font-family:\'Fredoka One\',cursive;'
        f'font-size:2rem;color:#f5e6ff;text-shadow:0 0 20px rgba(200,150,255,.7);'
        f'margin-bottom:.2rem;">&#127769; Dream Story Time</div>'
        f'<div style="text-align:center;color:#c8a8f0;font-size:.95rem;margin-bottom:1.2rem;">'
        f'Hello, <b>{child_name}</b>! Your magical adventure awaits...</div>',
        unsafe_allow_html=True,
    )

    if st.session_state.pop("close_profile_expander", False):
        close_profile_expander()

    with st.expander("Profile", expanded=st.session_state.get("profile_panel_open", False)):
        edit_name = st.text_input("Name", value=child_name, key="profile_edit_name")
        edit_age = st.number_input(
            "Age",
            min_value=3,
            max_value=12,
            value=int(age),
            step=1,
            key="profile_edit_age",
        )
        if st.button("Save Profile", key="save_profile_edits"):
            if edit_name.strip():
                st.session_state["child_name"] = edit_name.strip()
                st.session_state["age"] = int(edit_age)
                st.session_state["thread_id"] = str(uuid.uuid4())
                st.session_state["phase"] = "greeting"
                st.session_state["story_so_far"] = ""
                st.session_state["current_question"] = ""
                st.session_state["current_narration"] = ""
                st.session_state["current_image_prompt"] = ""
                st.session_state["greeting_done"] = False
                st.session_state["is_ending"] = False
                st.session_state["moral"] = ""
                st.session_state["goodnight"] = ""
                st.session_state["has_shown_voice"] = False
                st.session_state["speak_trigger"] = False
                st.session_state["voice_reset"] = True
                st.session_state["profile_panel_open"] = False
                st.session_state["close_profile_expander"] = True
                save_profile_to_local_storage(edit_name.strip(), int(edit_age))
                save_session()
                st.rerun()

    # ── AUTO-GREETING (first turn of this session) ────────────────────────────
    if not st.session_state["greeting_done"]:
        with st.spinner("Waking up the story magic..."):
            state = run_agent_turn(agent, thread_id, "greeting", child_name, age, "", "")
        _apply_state(state)
        # No speak_trigger here - user must tap START to begin the first greeting
        save_session()
        st.rerun()

    # ── PROCESS INCOMING VOICE INPUT ─────────────────────────────────────────
    # Allow voice input even during ending (so kid can say "yes" for another story)
    if voice_input == "__STOP__":
        # STOP — reset and restart normal greeting flow on next START
        _clear_story_state()
        save_session()
        st.rerun()
    elif voice_input == "__CONTINUE__":
        # Auto-continue only when a story is already in progress.
        # During questions (including "what kind of story"), wait for kid input.
        phase_now = st.session_state.get("phase", "greeting")
        story_now = st.session_state.get("story_so_far", "").strip()
        if phase_now == "storytelling" and story_now:
            with st.spinner("Getting the next part ready..."):
                state = run_agent_turn(
                    agent, thread_id,
                    phase=phase_now,
                    child_name=child_name,
                    age=age,
                    kid_input="",
                    story_so_far=st.session_state.get("story_so_far", ""),
                )
            _apply_state(state)
            st.session_state["has_shown_voice"] = True
            st.session_state["speak_trigger"] = True   # one-shot: auto-play this new narration
            save_session()
        st.rerun()
    elif voice_input:
        with st.spinner("Thinking of the next part of your story..."):
            state = run_agent_turn(
                agent, thread_id,
                phase=st.session_state["phase"],
                child_name=child_name,
                age=age,
                kid_input=voice_input,
                story_so_far=st.session_state.get("story_so_far", ""),
            )
        _apply_state(state)
        st.session_state["has_shown_voice"] = True
        st.session_state["speak_trigger"] = True   # one-shot: auto-play this new narration
        save_session()
        st.rerun()

    # ── RENDER SCENE ──────────────────────────────────────────────────────────
    # Show old cached image INSTANTLY, then fetch new image only when prompt changes.
    img_placeholder = st.empty()
    cached_b64 = st.session_state.get("current_image_b64", "")
    if cached_b64:
        img_placeholder.image(base64.b64decode(cached_b64), width="stretch")

    new_prompt  = st.session_state.get("current_image_prompt", "")
    last_prompt = st.session_state.get("last_fetched_prompt", "")
    if new_prompt and new_prompt != last_prompt:
        with st.spinner("Painting your scene..."):
            img_bytes = fetch_story_image(new_prompt)
        new_b64 = base64.b64encode(img_bytes).decode()
        st.session_state["current_image_b64"]   = new_b64
        st.session_state["last_fetched_prompt"] = new_prompt
        save_session()
        img_placeholder.image(img_bytes, width="stretch")

    # ── VOICE INJECT (fixed bottom FAB + TTS/STT) ────────────────────────
    # is_idle=True  → show green START (before first interaction)
    # is_idle=False → show purple STOP pulsing (story in progress)
    #
    # speak_trigger is a ONE-SHOT flag: set only when new narration arrives
    # consumed (popped) here so subsequent renders don't re-trigger the same narration (double fire TTS).
    auto    = st.session_state.pop("speak_trigger", False)
    force_reset = st.session_state.pop("voice_reset", False)
    is_idle = not st.session_state.get("has_shown_voice", False)
    phase   = st.session_state.get("phase", "greeting")
    is_cont = phase == "storytelling" and bool(st.session_state.get("story_so_far", "").strip())
    voice_inject(
        text_to_speak=st.session_state.get("current_narration", ""),
        is_idle=is_idle,
        auto_start=auto,
        is_continuous=is_cont,
        force_reset=force_reset,
    )


if __name__ == "__main__":
    main()
