from __future__ import annotations

import csv
import html
import io
import json
import random
from collections import Counter
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from vocabora.data import CEFR_LEVELS, POS_LABELS, normalize_word
from vocabora.database import (
    add_word,
    create_quiz_session,
    export_words_csv,
    finish_quiz_session,
    get_all_words,
    get_categories,
    get_category_performance,
    get_cefr_performance,
    get_due_words,
    get_mistakes,
    get_quiz_history,
    get_saved_words,
    get_setting,
    get_stats,
    get_word,
    import_words,
    initialize_database,
    record_answer,
    record_review,
    remove_mistake,
    reset_learning_history,
    save_word,
    set_setting,
    toggle_saved_word,
)
from vocabora.logic import create_quiz, get_result_level, score_summary

st.set_page_config(page_title="VOCABORA | เรียนคำศัพท์ภาษาอังกฤษ", page_icon="📘", layout="wide", initial_sidebar_state="expanded")
initialize_database()

PAGES = {
    "หน้าภาพรวม": "🏠",
    "เริ่มเรียน": "🚀",
    "เรียนต่อจากครั้งล่าสุด": "⏯️",
    "คำศัพท์ทั้งหมด": "📚",
    "คำศัพท์ตามระดับ": "🎚️",
    "หมวดหมู่คำศัพท์": "🗂️",
    "คำศัพท์ที่บันทึกไว้": "🔖",
    "คำศัพท์ที่ยังจำไม่ได้": "🧩",
    "บัตรคำศัพท์": "🃏",
    "แบบทดสอบ 4 ตัวเลือก": "✍️",
    "ฝึกพิมพ์คำศัพท์": "⌨️",
    "ฝึกสะกดคำ": "🔤",
    "ฝึกแปลประโยค": "💬",
    "ทบทวนวันนี้": "🗓️",
    "ความก้าวหน้าในการเรียน": "📈",
    "สถิติการเรียน": "📊",
    "ประวัติแบบทดสอบ": "🕘",
    "คำศัพท์ที่เรียนรู้แล้ว": "✅",
    "ตั้งค่า": "⚙️",
    "เกี่ยวกับ VOCABORA": "ℹ️",
}
NAV_GROUPS = {
    "หน้าหลัก": ["หน้าภาพรวม", "เริ่มเรียน", "เรียนต่อจากครั้งล่าสุด"],
    # ซ่อนรายการที่ผู้ใช้ขอออกจาก Sidebar แต่คงหน้าและฟังก์ชันไว้
    # เพื่อให้ปุ่มภายในแอปยังเปิดไปยังฟังก์ชันเหล่านี้ได้ตามปกติ
    "คลังคำศัพท์": ["คำศัพท์ทั้งหมด", "คำศัพท์ที่บันทึกไว้", "คำศัพท์ที่ยังจำไม่ได้"],
    "วิธีฝึก": ["แบบทดสอบ 4 ตัวเลือก", "ฝึกพิมพ์คำศัพท์", "ฝึกสะกดคำ", "ฝึกแปลประโยค", "ทบทวนวันนี้"],
    "ติดตามผล": ["ความก้าวหน้าในการเรียน"],
    "ระบบ": ["ตั้งค่า", "เกี่ยวกับ VOCABORA"],
}

if "current_page" not in st.session_state:
    st.session_state.current_page = "หน้าภาพรวม"
if "current_category" not in st.session_state:
    st.session_state.current_category = get_setting("last_category", "ทั้งหมด")
if "flashcard_index" not in st.session_state:
    st.session_state.flashcard_index = 0
if "flashcard_signature" not in st.session_state:
    st.session_state.flashcard_signature = ""
if "theme" not in st.session_state:
    saved_theme = get_setting("theme", "light")
    st.session_state.theme = saved_theme if saved_theme in ("light", "dark") else "light"
if "quiz" not in st.session_state:
    st.session_state.quiz = []
if "quiz_answers" not in st.session_state:
    st.session_state.quiz_answers = {}
if "quiz_index" not in st.session_state:
    st.session_state.quiz_index = 0
if "quiz_session_id" not in st.session_state:
    st.session_state.quiz_session_id = None
if "quiz_complete" not in st.session_state:
    st.session_state.quiz_complete = False
if "practice_item" not in st.session_state:
    st.session_state.practice_item = None
if "practice_feedback" not in st.session_state:
    st.session_state.practice_feedback = None


def _set_page(page: str) -> None:
    st.session_state.current_page = page
    st.rerun()


def _safe(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _cefr_color(level: str) -> str:
    return {"A1": "#15803d", "A2": "#0f766e", "B1": "#2563eb", "B2": "#6d28d9", "C1": "#a16207", "C2": "#b45309"}.get(level, "#64748b")


def _pos_label(pos: str) -> str:
    return POS_LABELS.get(str(pos).lower(), str(pos or "ยังไม่ระบุ"))


def _format_when(value: str | None) -> str:
    if not value:
        return "ยังไม่มีประวัติ"
    return str(value).replace("T", " ")[:16]


def _get_words() -> list[dict[str, Any]]:
    return get_all_words()


def _navigate_to_card(word: dict[str, Any]) -> None:
    st.session_state.current_category = word.get("category", "ทั้งหมด")
    st.session_state.flashcard_category = st.session_state.current_category
    st.session_state.flashcard_index = 0
    st.session_state.flashcard_start_word = str(word.get("word", ""))
    set_setting("last_category", st.session_state.current_category)
    set_setting("last_word", str(word.get("word", "")))
    _set_page("บัตรคำศัพท์")


# Color tokens switch for the entire app, including navigation, forms and data tables.
if st.session_state.theme == "dark":
    theme = {
        "bg": "#0f172a", "sidebar": "#111c32", "surface": "#17243b", "surface2": "#1d2d49",
        "text": "#edf2ff", "muted": "#a9b7cf", "border": "#2c3d5b", "accent": "#a99aff",
        "accent_bg": "#302b55", "success": "#34d399", "danger": "#fb7185", "shadow": "rgba(0,0,0,.18)",
    }
else:
    theme = {
        "bg": "#f6f7fb", "sidebar": "#ffffff", "surface": "#ffffff", "surface2": "#f1efff",
        "text": "#1c2540", "muted": "#69758e", "border": "#e1e6f0", "accent": "#6856dc",
        "accent_bg": "#f0edff", "success": "#16835d", "danger": "#d9465c", "shadow": "rgba(32,43,77,.06)",
    }
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Anuphan:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700;800&display=swap');
:root {{
  --vo-bg:{theme['bg']}; --vo-sidebar:{theme['sidebar']}; --vo-surface:{theme['surface']}; --vo-surface-2:{theme['surface2']};
  --vo-text:{theme['text']}; --vo-muted:{theme['muted']}; --vo-border:{theme['border']}; --vo-accent:{theme['accent']};
  --vo-accent-bg:{theme['accent_bg']}; --vo-success:{theme['success']}; --vo-danger:{theme['danger']}; --vo-shadow:{theme['shadow']};
  --vo-glass:color-mix(in srgb, var(--vo-surface) 70%, transparent);
  --vo-glass-strong:color-mix(in srgb, var(--vo-surface) 84%, transparent);
  --vo-glass-border:color-mix(in srgb, var(--vo-border) 68%, white 32%);
  --vo-radius-xl:26px; --vo-radius-lg:20px; --vo-radius-md:15px;
}}
* {{ -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; }}
html, body, [class*="css"], button, input, textarea, label, select {{font-family:'Anuphan','Inter',Tahoma,sans-serif !important;}}
html {{text-rendering:optimizeLegibility; font-feature-settings:'kern' 1;}}
body {{background:var(--vo-bg);}}
.stApp {{background:radial-gradient(ellipse at 12% 4%, color-mix(in srgb, var(--vo-accent) 16%, transparent), transparent 37%),
  radial-gradient(ellipse at 88% 12%, rgba(85,176,255,.13), transparent 34%),
  radial-gradient(ellipse at 70% 92%, rgba(131,111,255,.10), transparent 38%), var(--vo-bg) !important; color:var(--vo-text);}}
[data-testid="stAppViewContainer"], [data-testid="stHeader"], [data-testid="stMain"] {{background:transparent !important;}}
[data-testid="stHeader"] {{border-bottom:1px solid color-mix(in srgb, var(--vo-border) 36%, transparent);}}
.block-container {{max-width:1500px; padding-top:1.8rem; padding-bottom:3.2rem;}}
[data-testid="stSidebar"] {{background:color-mix(in srgb, var(--vo-sidebar) 76%, transparent) !important; border-right:1px solid color-mix(in srgb, var(--vo-border) 68%, transparent); backdrop-filter:blur(28px) saturate(170%); -webkit-backdrop-filter:blur(28px) saturate(170%);}}
[data-testid="stSidebar"] > div:first-child {{padding-top:1.1rem; background:transparent;}}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] li {{color:var(--vo-muted);}}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {{letter-spacing:-.025em;}}
h1,h2,h3,h4,h5,h6 {{color:var(--vo-text); font-weight:750; letter-spacing:-.027em; line-height:1.35;}}
h1 {{font-size:clamp(1.8rem, 3vw, 2.55rem);}}
h2 {{font-size:clamp(1.35rem, 2vw, 1.8rem);}}
p, li, .stMarkdown {{color:var(--vo-text); line-height:1.72;}}
.stCaption, [data-testid="stWidgetLabel"], [data-testid="stCaptionContainer"] {{color:var(--vo-muted) !important;}}
[data-testid="stMetric"] {{background:var(--vo-glass); border:1px solid var(--vo-glass-border); padding:18px 20px; border-radius:var(--vo-radius-lg); box-shadow:0 10px 28px var(--vo-shadow), inset 0 1px 0 rgba(255,255,255,.30); backdrop-filter:blur(22px) saturate(160%); -webkit-backdrop-filter:blur(22px) saturate(160%); transition:transform .2s ease, box-shadow .2s ease;}}
[data-testid="stMetric"]:hover {{transform:translateY(-2px); box-shadow:0 15px 32px var(--vo-shadow), inset 0 1px 0 rgba(255,255,255,.34);}}
[data-testid="stMetricLabel"] p {{color:var(--vo-muted) !important; font-size:.9rem; font-weight:550;}}
[data-testid="stMetricValue"] {{color:var(--vo-text) !important; font-weight:800; letter-spacing:-.035em;}}
[data-testid="stVerticalBlockBorderWrapper"] {{background:var(--vo-glass); border:1px solid var(--vo-glass-border) !important; border-radius:var(--vo-radius-lg); box-shadow:0 8px 24px var(--vo-shadow), inset 0 1px 0 rgba(255,255,255,.22); backdrop-filter:blur(20px) saturate(155%); -webkit-backdrop-filter:blur(20px) saturate(155%);}}
.stTextInput input, .stTextArea textarea, .stNumberInput input {{background:var(--vo-glass-strong) !important; color:var(--vo-text) !important; border:1px solid var(--vo-border) !important; border-radius:var(--vo-radius-md) !important; box-shadow:inset 0 1px 1px rgba(255,255,255,.15); transition:border-color .18s ease, box-shadow .18s ease;}}
.stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {{border-color:var(--vo-accent) !important; box-shadow:0 0 0 3px color-mix(in srgb, var(--vo-accent) 18%, transparent) !important;}}
.stSelectbox [data-baseweb="select"] > div, .stMultiSelect [data-baseweb="select"] > div {{background:var(--vo-glass-strong); color:var(--vo-text); border-color:var(--vo-border); border-radius:var(--vo-radius-md);}}
[data-baseweb="popover"] > div, [data-baseweb="menu"] {{background:var(--vo-glass-strong); backdrop-filter:blur(24px); border:1px solid var(--vo-border); border-radius:14px; box-shadow:0 14px 40px var(--vo-shadow);}}
.stRadio [data-testid="stMarkdownContainer"] p, .stCheckbox [data-testid="stMarkdownContainer"] p {{color:var(--vo-text);}}
.stButton > button, .stDownloadButton > button {{border-radius:14px; font-weight:650; min-height:2.7rem; padding:.48rem 1rem; border:1px solid var(--vo-border); background:var(--vo-glass-strong); color:var(--vo-text); box-shadow:0 3px 12px var(--vo-shadow), inset 0 1px 0 rgba(255,255,255,.34); transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease, filter .18s ease;}}
.stButton > button:hover, .stDownloadButton > button:hover {{transform:translateY(-1px); box-shadow:0 8px 20px var(--vo-shadow), inset 0 1px 0 rgba(255,255,255,.4); border-color:color-mix(in srgb, var(--vo-accent) 60%, var(--vo-border)); filter:saturate(1.08);}}
.stButton > button:active, .stDownloadButton > button:active {{transform:scale(.985);}}
[data-testid="stBaseButton-primary"] {{background:linear-gradient(135deg, color-mix(in srgb, var(--vo-accent) 92%, white 8%), var(--vo-accent)) !important; border-color:color-mix(in srgb, var(--vo-accent) 72%, white 28%) !important; color:#fff !important; box-shadow:0 7px 19px color-mix(in srgb, var(--vo-accent) 22%, transparent), inset 0 1px 0 rgba(255,255,255,.28) !important;}}
[data-testid="stBaseButton-secondary"] {{background:var(--vo-glass-strong) !important; border-color:var(--vo-border) !important; color:var(--vo-text) !important;}}
[data-testid="stSidebar"] .stButton > button {{width:100%; text-align:left; border-radius:13px; box-shadow:none; background:transparent; border-color:transparent; min-height:2.5rem;}}
[data-testid="stSidebar"] .stButton > button:hover {{background:var(--vo-glass); border-color:var(--vo-border); transform:translateX(2px);}}
.stTabs [data-baseweb="tab-list"] {{gap:6px; padding:5px; border-radius:16px; background:var(--vo-glass); border:1px solid var(--vo-glass-border); backdrop-filter:blur(16px);}}
.stTabs [data-baseweb="tab"] {{border-radius:12px; padding:9px 15px; transition:background .18s ease;}}
.stTabs [aria-selected="true"] {{background:var(--vo-accent-bg); border-radius:12px;}}
.stTabs [data-baseweb="tab-highlight"] {{background:var(--vo-accent); height:3px; border-radius:999px;}}
.stProgress > div > div {{background:color-mix(in srgb, var(--vo-accent) 13%, var(--vo-surface)); border-radius:999px;}}
.stProgress > div > div > div {{background:linear-gradient(90deg,var(--vo-accent),#7fc5ff); border-radius:999px;}}
[data-testid="stAlert"] {{background:var(--vo-glass); border:1px solid var(--vo-glass-border); border-radius:16px; backdrop-filter:blur(18px);}}
[data-testid="stExpander"] {{border:1px solid var(--vo-glass-border); border-radius:16px; background:var(--vo-glass); overflow:hidden;}}
hr {{border-color:var(--vo-border) !important; opacity:.7;}}
.vo-brand {{font-weight:800; letter-spacing:.075em; font-size:1.5rem; color:var(--vo-text); text-shadow:0 1px 0 rgba(255,255,255,.12);}}
.vo-brand-dot {{color:var(--vo-accent);}}
.vo-subbrand {{font-size:.83rem; color:var(--vo-muted); margin-top:-4px; letter-spacing:.01em;}}
.vo-hero {{position:relative; isolation:isolate; overflow:hidden; background:linear-gradient(125deg,color-mix(in srgb, var(--vo-accent-bg) 76%, transparent),color-mix(in srgb, var(--vo-surface) 62%, transparent)); border:1px solid var(--vo-glass-border); border-radius:var(--vo-radius-xl); padding:30px 32px; margin-bottom:24px; box-shadow:0 18px 42px var(--vo-shadow), inset 0 1px 0 rgba(255,255,255,.42); backdrop-filter:blur(24px) saturate(170%); -webkit-backdrop-filter:blur(24px) saturate(170%);}}
.vo-hero::after {{content:""; position:absolute; z-index:-1; width:250px; height:250px; right:-65px; top:-125px; border-radius:50%; background:radial-gradient(circle at 35% 35%,rgba(255,255,255,.42),color-mix(in srgb, var(--vo-accent) 24%, transparent) 48%,transparent 72%); filter:blur(1px); pointer-events:none;}}
.vo-eyebrow {{font-size:.77rem; text-transform:uppercase; letter-spacing:.13em; color:var(--vo-accent); font-weight:800; margin-bottom:9px;}}
.vo-hero-title {{font-weight:800; font-size:clamp(1.65rem,2.7vw,2.5rem); letter-spacing:-.035em; line-height:1.28; margin:0 0 9px 0; color:var(--vo-text);}}
.vo-hero-sub {{font-size:1rem; line-height:1.85; color:var(--vo-muted); margin:0; max-width:880px;}}
.vo-panel {{background:var(--vo-glass); border:1px solid var(--vo-glass-border); border-radius:var(--vo-radius-lg); padding:20px 22px; box-shadow:0 8px 24px var(--vo-shadow), inset 0 1px 0 rgba(255,255,255,.24); backdrop-filter:blur(19px) saturate(150%); -webkit-backdrop-filter:blur(19px) saturate(150%); margin-bottom:13px;}}
.vo-panel-title {{font-weight:750; font-size:1.1rem; letter-spacing:-.018em; margin-bottom:6px; color:var(--vo-text);}}
.vo-muted {{color:var(--vo-muted); font-size:.91rem; line-height:1.7;}}
.vo-chip {{display:inline-block; padding:4px 11px; background:var(--vo-glass); border:1px solid var(--vo-border); border-radius:999px; font-size:.77rem; color:var(--vo-muted); margin:2px 4px 2px 0; box-shadow:inset 0 1px 0 rgba(255,255,255,.18);}}
.vo-word {{font-size:1.25rem; font-weight:800; letter-spacing:-.015em; color:var(--vo-text);}}
.vo-translation {{font-size:1.04rem; color:var(--vo-accent); font-weight:700;}}
.vo-stat-label {{font-size:.84rem; color:var(--vo-muted);}}
.vo-empty {{text-align:center; padding:38px 20px; border:1px dashed var(--vo-border); border-radius:var(--vo-radius-lg); color:var(--vo-muted); background:var(--vo-glass); backdrop-filter:blur(16px);}}
.vo-nav-label {{padding:14px 10px 6px; color:var(--vo-muted); font-size:.73rem; font-weight:800; letter-spacing:.09em;}}
.vo-source {{font-size:.83rem; color:var(--vo-muted); line-height:1.8;}}
[data-testid="stDataFrame"] {{border:1px solid var(--vo-glass-border); border-radius:16px; overflow:hidden; box-shadow:0 6px 18px var(--vo-shadow);}}
[data-testid="stFileUploader"] section {{background:var(--vo-glass); border:1px dashed var(--vo-border); border-radius:16px;}}
@media(prefers-reduced-motion:reduce) {{ *,*::before,*::after {{transition:none !important; animation:none !important; scroll-behavior:auto !important;}} }}
@media(max-width:700px) {{
  .block-container {{padding-left:1rem;padding-right:1rem;padding-top:1.25rem;}}
  .vo-hero {{padding:23px 20px; border-radius:22px;}}
  .vo-panel {{padding:17px 17px;}}
  [data-testid="stMetric"] {{padding:15px 15px; border-radius:17px;}}
  .stTabs [data-baseweb="tab"] {{padding:8px 11px;}}
}}
</style>
""", unsafe_allow_html=True)


def _hero(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="vo-hero"><div class="vo-eyebrow">{_safe(eyebrow)}</div>'
        f'<div class="vo-hero-title">{_safe(title)}</div><p class="vo-hero-sub">{_safe(subtitle)}</p></div>',
        unsafe_allow_html=True,
    )


def _panel(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="vo-panel-title">{_safe(title)}</div>' + (f'<div class="vo-muted">{_safe(subtitle)}</div>' if subtitle else ""), unsafe_allow_html=True)


def _empty(message: str) -> None:
    st.markdown(f'<div class="vo-empty">{_safe(message)}</div>', unsafe_allow_html=True)


def _word_status_label(item: dict[str, Any]) -> str:
    if item.get("status") == "mastered":
        return "จำได้แล้ว"
    if item.get("status") == "learning" or int(item.get("wrong_count", 0) or 0) > 0:
        return "ควรทบทวน"
    return "ยังไม่เริ่มเรียน"


def _mark_word_review(word_id: int, remembered: bool) -> None:
    result = record_review(word_id, remembered)
    word = get_word(word_id)
    if remembered:
        st.toast(f"บันทึกว่า ‘{word['word'] if word else 'คำศัพท์'}’ จำได้แล้ว", icon="✅")
    else:
        st.toast(f"เพิ่ม ‘{word['word'] if word else 'คำศัพท์'}’ ในรายการทบทวน", icon="🔁")


# Sidebar navigation: all visible entries have working routes.
with st.sidebar:
    st.markdown('<div class="vo-brand">VOCA<span class="vo-brand-dot">BORA</span></div><div class="vo-subbrand">แพลตฟอร์มเรียนรู้คำศัพท์ภาษาอังกฤษ</div>', unsafe_allow_html=True)
    st.markdown("---")
    for group, pages in NAV_GROUPS.items():
        st.markdown(f'<div class="vo-nav-label">{_safe(group)}</div>', unsafe_allow_html=True)
        for nav_page in pages:
            active = st.session_state.current_page == nav_page
            label = f"{PAGES[nav_page]}  {nav_page}"
            if st.button(label, key=f"nav_{nav_page}", use_container_width=True, type="primary" if active else "secondary"):
                if nav_page == "เรียนต่อจากครั้งล่าสุด":
                    st.session_state.current_category = get_setting("last_category", "ทั้งหมด")
                    st.session_state.flashcard_category = st.session_state.current_category
                    st.session_state.current_page = "บัตรคำศัพท์"
                    st.session_state.flashcard_index = 0
                else:
                    st.session_state.current_page = nav_page
                st.rerun()
    st.markdown("---")
    query_side = st.text_input("ค้นหาคำศัพท์", placeholder="อังกฤษหรือภาษาไทย…", key="sidebar_search")
    if st.button("🔎 ค้นหาในคลัง", key="sidebar_search_button", use_container_width=True):
        st.session_state.library_search = query_side
        st.session_state.current_page = "คำศัพท์ทั้งหมด"
        st.rerun()
    theme_label = "☀️ เปลี่ยนเป็นธีมสว่าง" if st.session_state.theme == "dark" else "🌙 เปลี่ยนเป็นธีมมืด"
    if st.button(theme_label, use_container_width=True, key="theme_toggle"):
        st.session_state.theme = "dark" if st.session_state.theme == "light" else "light"
        set_setting("theme", st.session_state.theme)
        st.rerun()

page = st.session_state.current_page
words = _get_words()
categories = get_categories()
st.session_state.current_category = st.session_state.get("current_category", "ทั้งหมด")

# ----------------------------------------------------------------------------
# หน้าภาพรวม
# ----------------------------------------------------------------------------
if page == "หน้าภาพรวม":
    stats = get_stats()
    due_words = get_due_words()
    mistakes = get_mistakes()
    recent = get_quiz_history(1)
    _hero("ยินดีต้อนรับสู่ VOCABORA", "คำศัพท์ใหม่ทีละคำ ความมั่นใจเพิ่มขึ้นทุกวัน", "พื้นที่ฝึกภาษาอังกฤษที่ออกแบบมาเพื่อผู้เรียนชาวไทย พร้อมคลังคำศัพท์ บัตรคำ แบบทดสอบ และระบบทบทวนที่บันทึกความก้าวหน้าให้คุณอัตโนมัติ")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("คำศัพท์ในคลัง", f"{len(words):,}", help="จำนวนคำศัพท์ทั้งหมดที่บันทึกอยู่ในคลัง")
    c2.metric("คำศัพท์ที่เคยฝึก", f"{int(stats['practiced_words']):,}")
    c3.metric("คำศัพท์ที่จำได้แล้ว", f"{int(stats['mastered_words']):,}")
    c4.metric("ควรทบทวนวันนี้", f"{len(set(w['id'] for w in due_words) | set(m['id'] for m in mistakes)):,}")

    left, right = st.columns([1.5, 1])
    with left:
        _panel("เริ่มต้นเรียนได้ทันที", "เลือกวิธีฝึกที่เหมาะกับเวลาของคุณ")
        a, b = st.columns(2)
        with a:
            if st.button("🃏  เริ่มจากบัตรคำศัพท์", use_container_width=True, type="primary", key="home_flashcards"):
                st.session_state.current_category = "ทั้งหมด"
                st.session_state.flashcard_category = "ทั้งหมด"
                st.session_state.flashcard_index = 0
                st.session_state.flashcard_flipped = False
                _set_page("บัตรคำศัพท์")
        with b:
            if st.button("✍️  ทำแบบทดสอบ", use_container_width=True, key="home_quiz"):
                st.session_state.quiz = []
                _set_page("แบบทดสอบ 4 ตัวเลือก")
        a, b = st.columns(2)
        with a:
            if st.button("🔁  ทบทวนคำที่ยังไม่แม่น", use_container_width=True, key="home_review"):
                _set_page("ทบทวนวันนี้")
        with b:
            if st.button("📚  สำรวจหมวดหมู่", use_container_width=True, key="home_categories"):
                _set_page("หมวดหมู่คำศัพท์")
        if recent:
            item = recent[0]
            st.markdown(f'<div class="vo-panel"><div class="vo-panel-title">เรียนต่อจากครั้งล่าสุด</div><div class="vo-muted">หมวดหมู่: {_safe(item["category"])} · {_safe(_format_when(item["started_at"]))}</div></div>', unsafe_allow_html=True)
            if st.button("เรียนต่อในหมวดหมู่นี้ →", key="resume_recent"):
                st.session_state.current_category = item["category"]
                st.session_state.flashcard_category = item["category"]
                _set_page("บัตรคำศัพท์")
        else:
            st.markdown('<div class="vo-panel"><div class="vo-panel-title">เคล็ดลับสำหรับผู้เริ่มต้น</div><div class="vo-muted">ลองฝึกวันละ 5–10 คำ แล้วกลับมาทบทวนคำเดิมในวันถัดไป</div></div>', unsafe_allow_html=True)
    with right:
        _panel("ภาพรวมการเรียน", "สรุปจากประวัติที่บันทึกไว้จริง")
        accuracy = float(stats["accuracy"])
        st.markdown(f'<div class="vo-panel"><div class="vo-stat-label">ความแม่นยำจากแบบทดสอบ</div><div style="font-size:2rem;font-weight:800;color:var(--vo-accent)">{accuracy:.1f}%</div><div class="vo-muted">ตอบถูก {int(stats["correct"]):,} จาก {int(stats["total_answered"]):,} ข้อ</div></div>', unsafe_allow_html=True)
        learned_rate = int(stats["mastered_words"]) / max(1, len(words))
        st.caption("ความก้าวหน้าของคำศัพท์ที่จำได้แล้ว")
        st.progress(min(1.0, learned_rate))
        st.caption(f"{int(stats['mastered_words']):,} / {len(words):,} คำ ({learned_rate*100:.1f}%)")
        st.markdown(f'<div class="vo-panel"><div class="vo-panel-title">รายการที่ควรกลับมาดู</div><div class="vo-muted">คำที่ยังจำไม่ได้: {len(mistakes)} คำ</div><div class="vo-muted">ถึงกำหนดทบทวน: {len(due_words)} คำ</div></div>', unsafe_allow_html=True)

    st.markdown("### สำรวจคลังคำศัพท์")
    if categories:
        colset = st.columns(4)
        counts = Counter(str(w["category"]) for w in words)
        for i, cat in enumerate(categories[:8]):
            with colset[i % 4]:
                st.markdown(f'<div class="vo-panel"><div class="vo-panel-title">{_safe(cat)}</div><div class="vo-muted">{counts[cat]} คำศัพท์</div></div>', unsafe_allow_html=True)
                if st.button("เปิดหมวดนี้", key=f"home_cat_{i}", use_container_width=True):
                    st.session_state.current_category = cat
                    st.session_state.flashcard_category = cat
                    st.session_state.flashcard_index = 0
                    st.session_state.flashcard_flipped = False
                    set_setting("last_category", cat)
                    _set_page("บัตรคำศัพท์")

# ----------------------------------------------------------------------------
# เริ่มเรียน / หมวดหมู่คำศัพท์
# ----------------------------------------------------------------------------
elif page in ("เริ่มเรียน", "หมวดหมู่คำศัพท์"):
    _hero("คลังคำศัพท์", "เลือกหมวดหมู่ที่อยากฝึก", "เริ่มจากเรื่องใกล้ตัว แล้วค่อยขยับไปสู่ภาษาอังกฤษเพื่อการเรียนและการทำงาน")
    counts = Counter(str(w["category"]) for w in words)
    filter_text = st.text_input("ค้นหาหมวดหมู่", placeholder="เช่น การทำงาน, การท่องเที่ยว…", key="category_search")
    filtered_categories = [cat for cat in categories if filter_text.strip().casefold() in cat.casefold()] if filter_text.strip() else categories
    if not filtered_categories:
        _empty("ไม่พบหมวดหมู่ที่ตรงกับคำค้นหา ลองใช้คำอื่นดูนะ")
    else:
        cols = st.columns(3)
        for i, cat in enumerate(filtered_categories):
            with cols[i % 3]:
                st.markdown(f'<div class="vo-panel"><div class="vo-panel-title">{_safe(cat)}</div><div class="vo-muted">{counts[cat]:,} คำศัพท์ · มีระดับตั้งแต่ A1 ถึง C2</div></div>', unsafe_allow_html=True)
                if st.button(f"เริ่มฝึกหมวดนี้  →", key=f"category_start_{i}_{cat}", use_container_width=True, type="primary" if i == 0 else "secondary"):
                    st.session_state.current_category = cat
                    st.session_state.flashcard_category = cat
                    st.session_state.flashcard_index = 0
                    set_setting("last_category", cat)
                    _set_page("บัตรคำศัพท์")

# ----------------------------------------------------------------------------
# คลังคำศัพท์, ระดับ, คำที่บันทึก และคำที่ต้องฝึกเพิ่ม
# ----------------------------------------------------------------------------
elif page in ("คำศัพท์ทั้งหมด", "คำศัพท์ตามระดับ", "คำศัพท์ที่บันทึกไว้", "คำศัพท์ที่เรียนรู้แล้ว"):
    title_map = {
        "คำศัพท์ทั้งหมด": ("คลังคำศัพท์ทั้งหมด", "ค้นหาคำแปลและกรองคำศัพท์ตามระดับ หมวดหมู่ หรือสถานะการเรียน"),
        "คำศัพท์ตามระดับ": ("คำศัพท์ตามระดับ CEFR", "เริ่มจากระดับที่เหมาะกับพื้นฐานของคุณ"),
        "คำศัพท์ที่บันทึกไว้": ("คำศัพท์ที่บันทึกไว้", "รวมคำที่คุณต้องการกลับมาดูอีกครั้ง"),
        "คำศัพท์ที่เรียนรู้แล้ว": ("คำศัพท์ที่จำได้แล้ว", "คำที่เลื่อนระดับการทบทวนไปยังกล่องที่สูงขึ้น"),
    }
    title, subtitle = title_map[page]
    _hero("คลังคำศัพท์", title, subtitle)
    search_default = st.session_state.pop("library_search", "")
    if search_default:
        st.session_state.library_search_input = search_default
    c1, c2, c3 = st.columns([1.6, 1, 1])
    with c1:
        query = st.text_input("ค้นหาคำภาษาอังกฤษหรือคำแปลไทย", placeholder="พิมพ์คำศัพท์หรือความหมาย…", key="library_search_input")
    with c2:
        category_options = ["ทุกหมวดหมู่", *categories]
        default_cat = st.session_state.current_category if st.session_state.current_category in categories else "ทุกหมวดหมู่"
        category_filter = st.selectbox("หมวดหมู่", category_options, index=category_options.index(default_cat), key="library_category_filter")
    with c3:
        levels = ["ทุกระดับ", *CEFR_LEVELS]
        level_default = st.session_state.get("library_level_filter", "ทุกระดับ") if page == "คำศัพท์ตามระดับ" else "ทุกระดับ"
        level_filter = st.selectbox("ระดับ CEFR", levels, index=levels.index(level_default) if level_default in levels else 0, key="library_cefr_filter")
    c4, c5, c6 = st.columns([1, 1, 1])
    with c4:
        pos_options = ["ทุกชนิด", *sorted({str(w.get("pos", "")) for w in words if w.get("pos")})]
        pos_filter = st.selectbox("ชนิดของคำ", pos_options, format_func=lambda p: "ทุกชนิด" if p == "ทุกชนิด" else _pos_label(p), key="library_pos_filter")
    with c5:
        status_options = ["ทุกสถานะ", "ยังไม่เริ่มเรียน", "ควรทบทวน", "จำได้แล้ว", "บันทึกไว้"]
        status_filter = st.selectbox("สถานะ", status_options, key="library_status_filter")
    with c6:
        sort_by = st.selectbox("เรียงตาม", ["ตัวอักษร A–Z", "ระดับง่ายไปยาก", "ระดับยากไปง่าย", "คำที่เรียนล่าสุด"], key="library_sort_filter")

    candidates = words
    if page == "คำศัพท์ที่บันทึกไว้":
        saved_ids = {int(w["id"]) for w in get_saved_words()}
        candidates = [w for w in candidates if int(w["id"]) in saved_ids]
    elif page == "คำศัพท์ที่ยังจำไม่ได้":
        mistake_ids = {int(m["id"]) for m in get_mistakes()}
        candidates = [w for w in candidates if int(w["id"]) in mistake_ids]
    elif page == "คำศัพท์ที่เรียนรู้แล้ว":
        candidates = [w for w in candidates if w.get("status") == "mastered"]
    if query.strip():
        needle = query.strip().casefold()
        candidates = [w for w in candidates if needle in str(w["word"]).casefold() or needle in str(w["translation"]).casefold()]
    if category_filter != "ทุกหมวดหมู่":
        candidates = [w for w in candidates if w.get("category") == category_filter]
    if page == "คำศัพท์ตามระดับ" and level_filter == "ทุกระดับ":
        # A sensible default when opening the CEFR shortcut: show starter levels.
        candidates = [w for w in candidates if w.get("cefr") in ("A1", "A2")]
    elif level_filter != "ทุกระดับ":
        candidates = [w for w in candidates if w.get("cefr") == level_filter]
    if pos_filter != "ทุกชนิด":
        candidates = [w for w in candidates if w.get("pos") == pos_filter]
    if status_filter == "ยังไม่เริ่มเรียน":
        candidates = [w for w in candidates if w.get("status", "new") == "new"]
    elif status_filter == "ควรทบทวน":
        ids = {int(m["id"]) for m in get_mistakes()}
        candidates = [w for w in candidates if w.get("status") == "learning" or int(w["id"]) in ids]
    elif status_filter == "จำได้แล้ว":
        candidates = [w for w in candidates if w.get("status") == "mastered"]
    elif status_filter == "บันทึกไว้":
        candidates = [w for w in candidates if w.get("is_saved")]
    if sort_by == "ระดับง่ายไปยาก":
        candidates.sort(key=lambda w: (CEFR_LEVELS.index(w.get("cefr", "A1")) if w.get("cefr") in CEFR_LEVELS else 0, str(w["word"]).casefold()))
    elif sort_by == "ระดับยากไปง่าย":
        candidates.sort(key=lambda w: (-(CEFR_LEVELS.index(w.get("cefr", "A1")) if w.get("cefr") in CEFR_LEVELS else 0), str(w["word"]).casefold()))
    elif sort_by == "คำที่เรียนล่าสุด":
        candidates.sort(key=lambda w: str(w.get("last_reviewed") or ""), reverse=True)
    else:
        candidates.sort(key=lambda w: str(w["word"]).casefold())

    st.markdown(f"**พบ {len(candidates):,} คำ**")
    if not candidates:
        _empty("ไม่พบคำศัพท์ที่ตรงกับเงื่อนไข ลองเปลี่ยนคำค้นหาหรือตัวกรอง")
    else:
        page_size = 20
        pages_total = max(1, (len(candidates) + page_size - 1) // page_size)
        if int(st.session_state.get("library_page_num", 1) or 1) > pages_total:
            st.session_state.library_page_num = 1
        curr = st.selectbox("หน้าผลลัพธ์", list(range(1, pages_total + 1)), format_func=lambda n: f"หน้า {n} / {pages_total}", key="library_page_num")
        shown = candidates[(curr - 1) * page_size:curr * page_size]
        for item in shown:
            with st.container(border=True):
                c1, c2 = st.columns([5, 1.7])
                with c1:
                    st.markdown(f'<div class="vo-word">{_safe(item["word"])}</div><div class="vo-translation">{_safe(item["translation"])}</div><div class="vo-muted">{_safe(_pos_label(item.get("pos", "")))} · ระดับ {_safe(item.get("cefr", "A1"))} · {_safe(item.get("category", ""))}</div>', unsafe_allow_html=True)
                    if item.get("example"):
                        st.markdown(f'<div style="margin-top:8px">“{_safe(item["example"])}”</div>', unsafe_allow_html=True)
                        if item.get("example_translation"):
                            st.caption(item["example_translation"])
                with c2:
                    s1, s2 = st.columns(2)
                    with s1:
                        if st.button("🔖" if item.get("is_saved") else "☆", key=f"library_save_{item['id']}", help="ยกเลิกการบันทึก" if item.get("is_saved") else "บันทึกคำศัพท์"):
                            save_word(int(item["id"]), not bool(item.get("is_saved")))
                            st.rerun()
                    with s2:
                        if st.button("🃏", key=f"library_card_{item['id']}", help="เปิดบัตรคำศัพท์"):
                            _navigate_to_card(item)
                    st.caption(_word_status_label(item))

# ----------------------------------------------------------------------------
# บัตรคำศัพท์แบบ 3D flip
# ----------------------------------------------------------------------------
elif page == "บัตรคำศัพท์":
    _hero("โหมดฝึก", "บัตรคำศัพท์แบบพลิกการ์ด", "ลองนึกความหมายด้วยตัวเองก่อนพลิกดูคำแปล แล้วบันทึกผลว่าจำได้หรือยังต้องทบทวน")
    c1, c2 = st.columns([1, 1])
    with c1:
        selected_category = st.selectbox("เลือกหมวดหมู่", ["ทั้งหมด", *categories], index=( ["ทั้งหมด", *categories].index(st.session_state.current_category) if st.session_state.current_category in ["ทั้งหมด", *categories] else 0 ), key="flashcard_category")
    with c2:
        selected_level = st.selectbox("เลือกระดับ CEFR", ["ทุกระดับ", *CEFR_LEVELS], key="flashcard_level")
    card_words = [w for w in words if selected_category == "ทั้งหมด" or w["category"] == selected_category]
    if selected_level != "ทุกระดับ":
        card_words = [w for w in card_words if w.get("cefr") == selected_level]
    base_ids = [int(w["id"]) for w in card_words]
    signature = f"{selected_category}|{selected_level}|" + ",".join(str(word_id) for word_id in base_ids)
    if st.session_state.flashcard_signature != signature:
        st.session_state.flashcard_signature = signature
        st.session_state.flashcard_order_ids = base_ids[:]
        st.session_state.flashcard_index = 0
    else:
        order_ids = st.session_state.get("flashcard_order_ids", base_ids[:])
        if len(order_ids) != len(base_ids) or set(order_ids) != set(base_ids):
            st.session_state.flashcard_order_ids = base_ids[:]
            st.session_state.flashcard_index = 0
    word_lookup = {int(w["id"]): w for w in card_words}
    order_ids = st.session_state.get("flashcard_order_ids", base_ids[:])
    card_words = [word_lookup[word_id] for word_id in order_ids if word_id in word_lookup]
    st.session_state.current_category = selected_category
    if not card_words:
        _empty("ยังไม่มีคำศัพท์ในตัวกรองนี้ ลองเปลี่ยนหมวดหมู่หรือระดับ CEFR")
    else:
        start_word = st.session_state.pop("flashcard_start_word", None)
        if start_word:
            requested_index = next((i for i, row in enumerate(card_words) if row["word"].casefold() == str(start_word).casefold()), None)
            if requested_index is not None:
                st.session_state.flashcard_index = requested_index
        index = int(st.session_state.flashcard_index) % len(card_words)
        item = card_words[index]
        set_setting("last_category", selected_category)
        set_setting("last_word", str(item["word"]))
        st.progress((index + 1) / len(card_words))
        st.caption(f"คำที่ {index + 1:,} จาก {len(card_words):,} คำ · {_word_status_label(item)}")
        bg_front = theme["surface"]
        bg_back = theme["surface2"]
        fg = theme["text"]
        muted = theme["muted"]
        accent = theme["accent"]
        border = theme["border"]
        word_html = _safe(item["word"])
        translation_html = _safe(item["translation"])
        pos_html = _safe(_pos_label(item.get("pos", "")))
        category_html = _safe(item.get("category", ""))
        cefr_html = _safe(item.get("cefr", "A1"))
        pronunciation_html = f'<div class="pron">{_safe(item.get("pronunciation"))}</div>' if item.get("pronunciation") else ""
        ex_html = f'<div class="example">“{_safe(item["example"])}”</div>' if item.get("example") else '<div class="example muted">ตัวอย่างประโยคยังไม่มีในรายการนี้</div>'
        exth_html = f'<div class="example-th">{_safe(item.get("example_translation"))}</div>' if item.get("example_translation") else ""
        syn_html = f'<div class="syn">คำใกล้เคียง: {_safe(", ".join(item.get("synonyms", [])))}</div>' if item.get("synonyms") else ""
        card_html = f"""
        <style>
          * {{box-sizing:border-box}} body {{margin:0;background:transparent;font-family:'Anuphan','Inter','Noto Sans Thai',Tahoma,sans-serif;color:{fg};-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}}
          .scene {{width:100%;height:335px;perspective:1200px;cursor:pointer;outline:none}}
          .inner {{position:relative;width:100%;height:100%;transform-style:preserve-3d;transition:transform .65s cubic-bezier(.2,.8,.2,1)}}
          .scene.flipped .inner {{transform:rotateY(180deg)}}
          .face {{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:25px;border-radius:26px;border:1px solid {border};backface-visibility:hidden;-webkit-backface-visibility:hidden;box-shadow:0 20px 42px rgba(10,20,40,.17),inset 0 1px 0 rgba(255,255,255,.62);overflow:hidden;}}
          .front {{background:linear-gradient(145deg,{bg_front},color-mix(in srgb, {bg_front} 84%, {accent} 16%))}}.back {{background:linear-gradient(145deg,{bg_back},color-mix(in srgb, {bg_back} 88%, {accent} 12%));transform:rotateY(180deg)}}
          .eyebrow {{font-size:12px;letter-spacing:.13em;text-transform:uppercase;color:{accent};font-weight:700;margin-bottom:14px}}
          .word {{font-size:clamp(30px,5vw,47px);font-weight:800;line-height:1.2;margin-bottom:10px;overflow-wrap:anywhere}}
          .translation {{font-size:clamp(25px,4vw,34px);font-weight:750;color:{accent};margin:3px 0 10px;overflow-wrap:anywhere}}
          .meta {{font-size:13px;color:{muted};margin-top:5px;line-height:1.8}}
          .hint {{font-size:13px;color:{muted};margin-top:28px}}
          .pron {{font-size:14px;color:{muted};margin-bottom:8px}}
          .example {{font-size:16px;margin-top:10px;line-height:1.6;max-width:100%;overflow-wrap:anywhere}}
          .example-th {{font-size:14px;color:{muted};margin-top:5px;line-height:1.6}}
          .syn {{font-size:12px;color:{muted};margin-top:12px}}
          .muted {{color:{muted}}}
          @media(max-width:600px) {{.scene{{height:365px}}.face{{padding:19px}}.example{{font-size:14px}}}}
        </style>
        <div class="scene" tabindex="0" role="button" aria-label="คลิกเพื่อพลิกดูคำแปล" onclick="this.classList.toggle('flipped')" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();this.classList.toggle('flipped')}}">
          <div class="inner">
            <div class="face front"><div class="eyebrow">VOCABORA · บัตรคำศัพท์</div><div class="word">{word_html}</div><div class="meta">{pos_html} · ระดับ {cefr_html}<br>{category_html}</div><div class="hint">↻ คลิกการ์ดเพื่อพลิกดูความหมาย</div></div>
            <div class="face back"><div class="eyebrow">ความหมายภาษาไทย</div><div class="word" style="font-size:25px">{word_html}</div><div class="translation">{translation_html}</div>{pronunciation_html}<div class="meta">{pos_html} · ระดับ {cefr_html}</div>{ex_html}{exth_html}{syn_html}<div class="hint">คลิกอีกครั้งเพื่อกลับไปดูคำศัพท์</div></div>
          </div>
        </div>
        """
        _, center, _ = st.columns([0.4, 2.2, 0.4])
        with center:
            components.html(card_html, height=360, scrolling=False)
        p, shuffle, n = st.columns([1, 1, 1])
        with p:
            if st.button("← ก่อนหน้า", use_container_width=True, key="flash_prev"):
                st.session_state.flashcard_index = (index - 1) % len(card_words)
                st.rerun()
        with shuffle:
            if st.button("🔀 สุ่มลำดับ", use_container_width=True, key="flash_shuffle"):
                shuffled_ids = [int(w["id"]) for w in card_words]
                random.shuffle(shuffled_ids)
                st.session_state.flashcard_order_ids = shuffled_ids
                st.session_state.flashcard_index = 0
                st.session_state.flashcard_start_word = None
                st.rerun()
        with n:
            if st.button("ถัดไป →", use_container_width=True, type="primary", key="flash_next"):
                st.session_state.flashcard_index = (index + 1) % len(card_words)
                st.rerun()
        st.markdown("")
        cknown, cunknown, csave = st.columns(3)
        with cknown:
            if st.button("✅ จำได้แล้ว", key="flash_known", use_container_width=True, type="primary"):
                _mark_word_review(int(item["id"]), True)
                st.session_state.flashcard_index = (index + 1) % len(card_words)
                st.rerun()
        with cunknown:
            if st.button("🔁 ยังจำไม่ได้", key="flash_unknown", use_container_width=True):
                _mark_word_review(int(item["id"]), False)
                st.session_state.flashcard_index = (index + 1) % len(card_words)
                st.rerun()
        with csave:
            if st.button("🔖 ยกเลิกบันทึก" if item.get("is_saved") else "☆ บันทึกคำนี้", key="flash_save", use_container_width=True):
                save_word(int(item["id"]), not bool(item.get("is_saved")))
                st.rerun()

# ----------------------------------------------------------------------------
# แบบทดสอบ 4 ตัวเลือก
# ----------------------------------------------------------------------------
elif page == "แบบทดสอบ 4 ตัวเลือก":
    _hero("โหมดฝึก", "แบบทดสอบคำศัพท์ 4 ตัวเลือก", "ตอบจากความจำของคุณ ระบบจะตรวจให้ทันที บันทึกคะแนน และเก็บคำที่ตอบผิดไว้ทบทวน")
    if not st.session_state.quiz or st.session_state.quiz_complete:
        if st.session_state.quiz_complete:
            answers_for_summary = list(st.session_state.quiz_answers.values())
            summary = score_summary(answers_for_summary)
            st.markdown(f'<div class="vo-panel"><div class="vo-eyebrow">ผลการทดสอบ</div><div style="font-size:2.4rem;font-weight:800;color:var(--vo-accent)">{summary["percentage"]:.1f}%</div><div class="vo-panel-title">{_safe(get_result_level(float(summary["percentage"])))}</div><div class="vo-muted">ตอบถูก {summary["correct"]} ข้อ · ตอบผิด {summary["incorrect"]} ข้อ · ทั้งหมด {summary["total"]} ข้อ</div></div>', unsafe_allow_html=True)
            st.progress(float(summary["percentage"]) / 100 if summary["total"] else 0)
            if summary["incorrect"]:
                with st.expander("ดูคำตอบที่ต้องทบทวน", expanded=True):
                    for answer in answers_for_summary:
                        if not answer["is_correct"]:
                            st.markdown(f"**{answer['word']}** — คำแปล: {answer['correct_answer']}  ")
                            st.caption(f"คำตอบของคุณ: {answer['selected_answer']}")
            left, right = st.columns(2)
            with left:
                if st.button("ทำแบบทดสอบชุดใหม่", use_container_width=True, type="primary"):
                    st.session_state.quiz = []
                    st.session_state.quiz_answers = {}
                    st.session_state.quiz_index = 0
                    st.session_state.quiz_session_id = None
                    st.session_state.quiz_complete = False
                    st.rerun()
            with right:
                if st.button("ไปทบทวนคำที่ตอบผิด", use_container_width=True):
                    _set_page("คำศัพท์ที่ยังจำไม่ได้")
        else:
            q1, q2, q3 = st.columns([1.4, 1, 1])
            with q1:
                quiz_category = st.selectbox("หมวดหมู่", ["ทั้งหมด", *categories], key="quiz_category_setup")
            with q2:
                quiz_level = st.selectbox("ระดับ CEFR", ["ทุกระดับ", *CEFR_LEVELS], key="quiz_level_setup")
            with q3:
                quiz_count = st.selectbox("จำนวนข้อ", [5, 10, 15, 20, 30], index=1, key="quiz_count_setup")
            candidate = [w for w in words if (quiz_category == "ทั้งหมด" or w["category"] == quiz_category) and (quiz_level == "ทุกระดับ" or w.get("cefr") == quiz_level)]
            st.caption(f"พบคำศัพท์ {len(candidate):,} คำในเงื่อนไขที่เลือก · ตัวเลือกคำตอบจะมาจากคลังคำศัพท์ทั้งหมด")
            if len({w['translation'] for w in words}) < 4:
                st.warning("คลังคำศัพท์ต้องมีอย่างน้อย 4 คำแปลที่แตกต่างกันจึงจะสร้างแบบทดสอบได้")
            elif not candidate:
                st.warning("ไม่มีคำศัพท์ในตัวกรองนี้ ลองเลือกหมวดหมู่หรือระดับอื่น")
            elif st.button("เริ่มทำแบบทดสอบ", type="primary", use_container_width=True):
                question_pool = create_quiz(candidate, min(int(quiz_count), len(candidate)), distractor_pool=words)
                if not question_pool:
                    st.error("ยังสร้างข้อสอบจากเงื่อนไขนี้ไม่ได้ กรุณาเลือกหมวดหมู่หรือระดับอื่น")
                else:
                    st.session_state.quiz = question_pool
                    st.session_state.quiz_answers = {}
                    st.session_state.quiz_index = 0
                    st.session_state.quiz_session_id = create_quiz_session(quiz_category, len(question_pool))
                    st.session_state.quiz_complete = False
                    st.rerun()
    else:
        quiz = st.session_state.quiz
        idx = int(st.session_state.quiz_index)
        if idx >= len(quiz):
            st.session_state.quiz_complete = True
            if st.session_state.quiz_session_id is not None:
                finish_quiz_session(int(st.session_state.quiz_session_id))
            st.rerun()
        question = quiz[idx]
        answer_map = st.session_state.quiz_answers
        st.progress((idx + 1) / len(quiz))
        st.caption(f"ข้อ {idx + 1} จาก {len(quiz)} ข้อ · ระดับ {question['cefr']} · {_safe(question['category'])}")
        st.markdown(f'<div class="vo-panel"><div class="vo-eyebrow">คำศัพท์ภาษาอังกฤษ</div><div style="font-size:2rem;font-weight:800;color:var(--vo-accent)">{_safe(question["word"])}</div><div class="vo-muted">คำนี้มีความหมายว่าอะไร?</div></div>', unsafe_allow_html=True)
        saved = answer_map.get(idx)
        if saved is None:
            selected = st.radio("เลือกคำแปลที่ถูกต้อง", question["options"], key=f"quiz_choice_{st.session_state.quiz_session_id}_{idx}", label_visibility="collapsed")
            if st.button("ส่งคำตอบ", type="primary", use_container_width=True, key=f"quiz_submit_{idx}"):
                is_correct = selected == question["answer"]
                streak = 0
                for prior_idx in range(idx - 1, -1, -1):
                    if answer_map.get(prior_idx, {}).get("is_correct"):
                        streak += 1
                    else:
                        break
                if record_answer(int(st.session_state.quiz_session_id), idx + 1, int(question["word_id"]), selected, question["answer"], is_correct, 0, streak + int(is_correct)):
                    st.session_state.quiz_answers[idx] = {"word": question["word"], "selected_answer": selected,
                                                           "correct_answer": question["answer"], "is_correct": is_correct,
                                                           "category": question["category"], "cefr": question["cefr"]}
                st.rerun()
        else:
            if saved["is_correct"]:
                st.success("ถูกต้อง! เก่งมาก")
            else:
                st.error(f"ยังไม่ถูก คำตอบที่คุณเลือกคือ: {saved['selected_answer']}")
                st.info(f"คำตอบที่ถูกต้อง: **{saved['correct_answer']}**")
            if question.get("example"):
                st.markdown(f"ตัวอย่าง: *{question['example']}*")
                if question.get("example_translation"):
                    st.caption(question["example_translation"])
            if idx + 1 < len(quiz):
                if st.button("ข้อถัดไป →", type="primary", use_container_width=True, key=f"quiz_next_{idx}"):
                    st.session_state.quiz_index += 1
                    st.rerun()
            else:
                if st.button("ดูผลการทดสอบ", type="primary", use_container_width=True, key="quiz_finish"):
                    st.session_state.quiz_index = len(quiz)
                    st.session_state.quiz_complete = True
                    finish_quiz_session(int(st.session_state.quiz_session_id))
                    st.rerun()

# ----------------------------------------------------------------------------
# ฝึกพิมพ์ / สะกด / แปลประโยค
# ----------------------------------------------------------------------------
elif page in ("ฝึกพิมพ์คำศัพท์", "ฝึกสะกดคำ"):
    is_spelling = page == "ฝึกสะกดคำ"
    _hero("แบบฝึกเฉพาะทักษะ", "ฝึกสะกดคำให้แม่นยำ" if is_spelling else "ฝึกพิมพ์คำศัพท์ภาษาอังกฤษ", "อ่านคำแปลภาษาไทย แล้วพิมพ์คำศัพท์ภาษาอังกฤษให้ตรงทุกตัวอักษร ระบบจะบันทึกผลเพื่อช่วยวางแผนทบทวน")
    category = st.selectbox("หมวดหมู่", ["ทั้งหมด", *categories], key=f"typing_category_{page}")
    candidate = [w for w in words if category == "ทั้งหมด" or w["category"] == category]
    if not candidate:
        _empty("ไม่มีคำศัพท์ในหมวดหมู่นี้")
    else:
        refresh_clicked = st.button("สุ่มคำใหม่", key=f"typing_refresh_{page}")
        if (st.session_state.practice_item is None
                or st.session_state.practice_item.get("page") != page
                or st.session_state.practice_item.get("category") != category
                or refresh_clicked):
            item = random.choice(candidate)
            st.session_state.practice_item = {"id": item["id"], "word": item["word"], "translation": item["translation"], "page": page, "category": category, "cefr": item.get("cefr", "A1")}
            st.session_state.practice_feedback = None
        item = st.session_state.practice_item
        st.markdown(f'<div class="vo-panel"><div class="vo-eyebrow">คำแปลภาษาไทย · ระดับ {_safe(item["cefr"])}</div><div style="font-size:1.7rem;font-weight:800;color:var(--vo-accent)">{_safe(item["translation"])}</div><div class="vo-muted">พิมพ์คำศัพท์ภาษาอังกฤษที่ตรงกับความหมายนี้</div></div>', unsafe_allow_html=True)
        if is_spelling:
            target = str(item["word"])
            hint = target[0] + " " + "_ " * max(0, len(target) - 1) if len(target) <= 16 else target[0] + " …"
            st.caption(f"คำใบ้: {hint}")
        answer = st.text_input("คำตอบภาษาอังกฤษ", key=f"typing_answer_{page}_{item['id']}", placeholder="พิมพ์คำศัพท์ที่นี่…")
        if st.button("ตรวจคำตอบ", type="primary", use_container_width=True, key=f"typing_check_{page}_{item['id']}"):
            is_correct = answer.strip().casefold() == str(item["word"]).casefold()
            st.session_state.practice_feedback = {"correct": is_correct, "entered": answer.strip(), "word": item["word"], "translation": item["translation"], "id": item["id"]}
            _mark_word_review(int(item["id"]), is_correct)
            st.rerun()
        feedback = st.session_state.practice_feedback
        if feedback and feedback.get("id") == item["id"]:
            if feedback["correct"]:
                st.success("ถูกต้อง! คุณสะกดคำนี้ได้แล้ว")
            else:
                st.error(f"ยังไม่ถูก คำที่ถูกต้องคือ **{feedback['word']}**")
                st.caption(f"คำตอบของคุณ: {feedback['entered'] or 'ไม่ได้กรอกคำตอบ'}")
        if st.button("ข้ามไปคำถัดไป", key=f"typing_next_{page}", use_container_width=True):
            st.session_state.practice_item = None
            st.session_state.practice_feedback = None
            st.rerun()

elif page == "ฝึกแปลประโยค":
    _hero("แบบฝึกเฉพาะทักษะ", "ฝึกทำความเข้าใจจากประโยคจริง", "อ่านประโยคภาษาอังกฤษ แล้วเลือกความหมายภาษาไทยที่ใกล้เคียงที่สุดจากตัวเลือกที่มี")
    examples = [w for w in words if w.get("example") and w.get("example_translation")]
    if not examples:
        _empty("ยังไม่มีตัวอย่างประโยคที่มีคำแปลครบในคลัง")
    else:
        if st.session_state.practice_item is None or st.session_state.practice_item.get("page") != page:
            item = random.choice(examples)
            options = [item["example_translation"]]
            alternatives = list({w["example_translation"] for w in examples if w["example_translation"] and w["example_translation"] != item["example_translation"]})
            random.shuffle(alternatives)
            options.extend(alternatives[:3])
            random.shuffle(options)
            st.session_state.practice_item = {"id": item["id"], "word": item["word"], "example": item["example"], "example_translation": item["example_translation"], "options": options, "page": page}
            st.session_state.practice_feedback = None
        item = st.session_state.practice_item
        st.markdown(f'<div class="vo-panel"><div class="vo-eyebrow">ประโยคภาษาอังกฤษ</div><div style="font-size:1.2rem;font-weight:650">“{_safe(item["example"])}”</div></div>', unsafe_allow_html=True)
        selected = st.radio("เลือกคำแปลประโยค", item["options"], key=f"sentence_choice_{item['id']}")
        if st.button("ตรวจคำแปล", type="primary", use_container_width=True, key="sentence_check"):
            correct = selected == item["example_translation"]
            st.session_state.practice_feedback = {"correct": correct, "id": item["id"], "answer": item["example_translation"]}
            _mark_word_review(int(item["id"]), correct)
            st.rerun()
        feedback = st.session_state.practice_feedback
        if feedback and feedback.get("id") == item["id"]:
            if feedback["correct"]:
                st.success("ถูกต้อง! เข้าใจประโยคได้ดีมาก")
            else:
                st.error("คำแปลยังไม่ตรงกับความหมายของประโยค")
                st.info(f"คำแปลที่ถูกต้อง: {feedback['answer']}")
        if st.button("ฝึกประโยคถัดไป", key="sentence_next", use_container_width=True):
            st.session_state.practice_item = None
            st.session_state.practice_feedback = None
            st.rerun()

# ----------------------------------------------------------------------------
# ทบทวนวันนี้ และคำศัพท์ที่ยังจำไม่ได้
# ----------------------------------------------------------------------------
elif page in ("ทบทวนวันนี้", "คำศัพท์ที่ยังจำไม่ได้"):
    _hero("ระบบทบทวน", "ทบทวนคำศัพท์ตามความจำ", "คำที่ตอบผิดจะกลับมาให้ฝึกบ่อยขึ้น ส่วนคำที่จำได้จะค่อย ๆ ขยายช่วงเวลาทบทวนตามหลักการแบบ Leitner")
    due = get_due_words()
    mistakes = get_mistakes()
    items_by_id = {int(w["id"]): w for w in due}
    for m in mistakes:
        items_by_id.setdefault(int(m["id"]), next((w for w in words if int(w["id"]) == int(m["id"])), m))
    items = list(items_by_id.values())
    if page == "คำศัพท์ที่ยังจำไม่ได้":
        mistake_ids = {int(m["id"]) for m in mistakes}
        items = [w for w in items if int(w["id"]) in mistake_ids]
    st.caption(f"คำศัพท์ที่ต้องทบทวน {len(items):,} คำ")
    if not items:
        _empty("ยอดเยี่ยม! ตอนนี้ไม่มีคำศัพท์ที่ถึงกำหนดทบทวน ลองเรียนคำใหม่เพื่อเพิ่มคลังคำศัพท์ได้เลย")
        if st.button("ไปเรียนคำศัพท์ใหม่", type="primary", use_container_width=True):
            _set_page("หมวดหมู่คำศัพท์")
    else:
        for item in items:
            with st.container(border=True):
                a, b = st.columns([4, 2])
                with a:
                    st.markdown(f'<div class="vo-word">{_safe(item["word"])}</div><div class="vo-translation">{_safe(item.get("translation", item.get("meaning", "")))}</div><div class="vo-muted">ระดับ {_safe(item.get("cefr", "A1"))} · {_safe(item.get("category", ""))}</div>', unsafe_allow_html=True)
                    if item.get("example"):
                        st.caption(item["example"])
                with b:
                    if st.button("เปิดบัตรคำศัพท์", key=f"review_card_{item['id']}", use_container_width=True):
                        _navigate_to_card(item)
                    r1, r2 = st.columns(2)
                    with r1:
                        if st.button("จำได้แล้ว", key=f"review_known_{item['id']}", use_container_width=True, type="primary"):
                            _mark_word_review(int(item["id"]), True)
                            st.rerun()
                    with r2:
                        if st.button("ยังจำไม่ได้", key=f"review_unknown_{item['id']}", use_container_width=True):
                            _mark_word_review(int(item["id"]), False)
                            st.rerun()

# ----------------------------------------------------------------------------
# ความก้าวหน้า, สถิติ, ประวัติแบบทดสอบ
# ----------------------------------------------------------------------------
elif page in ("ความก้าวหน้าในการเรียน", "สถิติการเรียน", "ประวัติแบบทดสอบ"):
    stats = get_stats()
    _hero("ติดตามผล", "ความก้าวหน้าของคุณ" if page != "ประวัติแบบทดสอบ" else "ประวัติแบบทดสอบ", "ดูผลจากกิจกรรมที่บันทึกไว้จริง ไม่มีการเติมคะแนนตัวอย่าง")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ข้อที่ตอบแล้ว", f"{int(stats['total_answered']):,}")
    c2.metric("ตอบถูก", f"{int(stats['correct']):,}")
    c3.metric("ตอบผิด", f"{int(stats['incorrect']):,}")
    c4.metric("ความแม่นยำ", f"{float(stats['accuracy']):.1f}%")
    if page == "ประวัติแบบทดสอบ":
        history = get_quiz_history(100)
        if not history:
            _empty("ยังไม่มีประวัติแบบทดสอบ เมื่อทำแบบทดสอบครั้งแรก ผลจะปรากฏในหน้านี้")
        else:
            rows = [{"วันที่": _format_when(h["started_at"]), "หมวดหมู่": h["category"], "ข้อที่ตอบ": f"{h['answered']}/{h['total_questions']}", "ตอบถูก": h["correct"], "ความแม่นยำ": f"{h['accuracy']:.1f}%", "สถานะ": "เสร็จแล้ว" if h["status"] == "completed" else "ยังทำไม่เสร็จ"} for h in history]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.markdown("### ความก้าวหน้าตามระดับ CEFR")
        level_counts = {level: {"total": 0, "mastered": 0, "learning": 0} for level in CEFR_LEVELS}
        for item in words:
            level = item.get("cefr", "A1") if item.get("cefr") in CEFR_LEVELS else "A1"
            level_counts[level]["total"] += 1
            if item.get("status") == "mastered":
                level_counts[level]["mastered"] += 1
            elif item.get("status") == "learning":
                level_counts[level]["learning"] += 1
        level_df = pd.DataFrame([{"ระดับ": level, "คำศัพท์ทั้งหมด": v["total"], "จำได้แล้ว": v["mastered"], "กำลังฝึก": v["learning"]} for level, v in level_counts.items()])
        st.dataframe(level_df, use_container_width=True, hide_index=True)
        st.markdown("### ผลการทำแบบทดสอบแยกตามหมวดหมู่")
        category_data = get_category_performance()
        if category_data:
            st.bar_chart(pd.DataFrame(category_data).set_index("category")["accuracy"], y_label="ความแม่นยำ (%)")
            st.dataframe(pd.DataFrame([{"หมวดหมู่": v["category"], "ตอบแล้ว": v["total"], "ตอบถูก": v["correct"], "ความแม่นยำ": f"{v['accuracy']:.1f}%"} for v in category_data]), use_container_width=True, hide_index=True)
        else:
            _empty("ยังไม่มีข้อมูลพอสำหรับแสดงผลตามหมวดหมู่ ลองทำแบบทดสอบก่อน แล้วกราฟจะอัปเดตจากผลจริง")
        cefr_data = get_cefr_performance()
        if cefr_data:
            st.markdown("### ผลตามระดับ CEFR")
            st.dataframe(pd.DataFrame([{"ระดับ": v["cefr"], "ตอบแล้ว": v["total"], "ตอบถูก": v["correct"], "ความแม่นยำ": f"{v['accuracy']:.1f}%"} for v in cefr_data]), use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------------
# ตั้งค่า: theme, data import/export, history reset
# ----------------------------------------------------------------------------
elif page == "ตั้งค่า":
    _hero("การตั้งค่า", "ปรับ VOCABORA ให้เหมาะกับคุณ", "เลือกธีม จัดการคลังคำศัพท์ และสำรองข้อมูลในเครื่องของคุณ")
    st.markdown("### รูปแบบการแสดงผล")
    current = st.session_state.theme
    theme_choice = st.radio("ธีมสี", ["สว่าง", "มืด"], index=0 if current == "light" else 1, horizontal=True, key="settings_theme_choice")
    if st.button("บันทึกธีม", type="primary", key="settings_save_theme"):
        st.session_state.theme = "light" if theme_choice == "สว่าง" else "dark"
        set_setting("theme", st.session_state.theme)
        st.rerun()
    st.markdown("---")
    st.markdown("### จัดการคลังคำศัพท์")
    st.caption("นำเข้าข้อมูลจากไฟล์ JSON หรือ CSV ได้ โดยรายการที่ซ้ำจะไม่สร้างเป็นคำใหม่ และข้อมูลเดิมจะไม่ถูกลบ")
    uploaded = st.file_uploader("เลือกไฟล์คำศัพท์ (.json หรือ .csv)", type=["json", "csv"], key="vocabulary_import_file")
    if uploaded is not None:
        try:
            content = uploaded.getvalue().decode("utf-8-sig")
            if uploaded.name.lower().endswith(".csv"):
                parsed_rows = list(csv.DictReader(io.StringIO(content)))
            else:
                payload = json.loads(content)
                parsed_rows = payload.get("words", payload) if isinstance(payload, dict) else payload
            if not isinstance(parsed_rows, list):
                st.error("รูปแบบ JSON ต้องเป็นรายการคำศัพท์ หรือมีคีย์ words ที่เป็นรายการ")
            else:
                st.caption(f"อ่านข้อมูลได้ {len(parsed_rows):,} รายการ ตรวจสอบช่องคำศัพท์ภาษาอังกฤษและคำแปลภาษาไทยก่อนนำเข้า")
                if st.button("นำเข้าคำศัพท์", type="primary", key="import_words_button"):
                    result = import_words([row for row in parsed_rows if isinstance(row, dict)])
                    st.success(f"นำเข้าใหม่ {result['added']:,} คำ · ข้ามรายการซ้ำ/ข้อมูลไม่ครบ {result['skipped']:,} รายการ")
                    st.rerun()
        except (UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
            st.error(f"อ่านไฟล์ไม่ได้: {exc}")
    st.download_button("⬇️ ส่งออกคลังคำศัพท์เป็น CSV", data=export_words_csv().encode("utf-8-sig"), file_name="vocabora_vocabulary.csv", mime="text/csv", use_container_width=True)
    st.markdown("---")
    st.markdown("### รีเซ็ตประวัติการเรียน")
    st.warning("การรีเซ็ตจะลบประวัติแบบทดสอบ คำที่ต้องทบทวน และกำหนดการทบทวน แต่จะไม่ลบคลังคำศัพท์ คำที่บันทึกไว้ หรือธีม")
    confirm_reset = st.checkbox("ฉันเข้าใจและต้องการรีเซ็ตประวัติการเรียน", key="confirm_reset_history")
    if st.button("รีเซ็ตประวัติ", disabled=not confirm_reset, key="reset_history_button"):
        reset_learning_history()
        st.session_state.quiz = []
        st.session_state.quiz_answers = {}
        st.session_state.quiz_session_id = None
        st.session_state.quiz_complete = False
        st.success("รีเซ็ตประวัติการเรียนแล้ว โดยเก็บคลังคำศัพท์เดิมไว้ครบถ้วน")
        st.rerun()

# ----------------------------------------------------------------------------
# เกี่ยวกับ
# ----------------------------------------------------------------------------
elif page == "เกี่ยวกับ VOCABORA":
    _hero("เกี่ยวกับโปรแกรม", "VOCABORA", "แพลตฟอร์มเรียนรู้คำศัพท์ภาษาอังกฤษสำหรับคนไทย")
    st.markdown("""
    **VOCABORA** ใช้ Python และ Streamlit เพื่อให้เรียนคำศัพท์ได้ทั้งจากการค้นหา บัตรคำศัพท์ แบบทดสอบ การฝึกพิมพ์ และการทบทวนตามช่วงเวลา

    **การเก็บข้อมูล:** ประวัติและการตั้งค่าบันทึกลง SQLite ภายในโฟลเดอร์โปรเจกต์ ไม่มีระบบบัญชีผู้ใช้หรือการส่งประวัติไปยังเซิร์ฟเวอร์ภายนอก

    **หมายเหตุเรื่องระดับ:** ระดับ CEFR ในชุดคำศัพท์เริ่มต้นเป็นการจัดระดับโดยประมาณเพื่อช่วยเลือกเนื้อหา ไม่ใช่ผลการรับรองอย่างเป็นทางการจากหน่วยงานผู้จัดสอบ
    """)
    st.markdown("### แหล่งข้อมูลและการเพิ่มคำศัพท์")
    st.markdown('<div class="vo-source">ชุดข้อมูลเริ่มต้นคัดเลือกสำหรับการเรียนรู้ และเก็บแยกใน <code>data/vocabulary.json</code> สามารถนำเข้าคำศัพท์ของคุณจาก JSON หรือ CSV ได้จากหน้า “ตั้งค่า”<br><br>แหล่งพจนานุกรมอ้างอิงที่สามารถนำมาจัดทำชุดคำศัพท์เพิ่มเติมได้: <a href="https://lexitron.nectec.or.th/" target="_blank">LEXiTRON — NECTEC</a> และ <a href="https://opend-portal.nectec.or.th/en/prepare/lexitron-2-0" target="_blank">NECTEC Data Catalog</a> โปรดตรวจสอบเงื่อนไขการอนุญาตใช้ข้อมูลก่อนนำชุดข้อมูลภายนอกมาแจกจ่ายต่อ</div>', unsafe_allow_html=True)
    st.markdown("### สรุปคลังคำศัพท์ปัจจุบัน")
    level_counter = Counter(str(w.get("cefr", "A1")) for w in words)
    a, b, c = st.columns(3)
    a.metric("คำศัพท์ทั้งหมด", f"{len(words):,} คำ")
    b.metric("หมวดหมู่", f"{len(categories):,} หมวด")
    c.metric("ระดับ CEFR", f"{len(level_counter)} ระดับ")
    st.dataframe(pd.DataFrame([{"ระดับ": level, "จำนวนคำ": level_counter.get(level, 0)} for level in CEFR_LEVELS]), use_container_width=True, hide_index=True)

else:
    _hero("VOCABORA", "หน้านี้ยังไม่พร้อมใช้งาน", "เลือกเมนูจากแถบด้านซ้ายเพื่อเริ่มเรียน")
    if st.button("กลับหน้าภาพรวม", type="primary"):
        _set_page("หน้าภาพรวม")
