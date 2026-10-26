"""Pure learning logic and quiz utilities (kept independent from Streamlit)."""
from __future__ import annotations

import random
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

from vocabora.data import DEFAULT_WORDS, get_category_names


def init_session_state(state: MutableMapping[str, Any] | None = None) -> None:
    """Set app state defaults without importing Streamlit inside the logic module."""
    if state is None:
        try:
            import streamlit as st  # local import keeps tests usable without Streamlit installed
            state = st.session_state
        except ImportError:
            return
    defaults = {
        "theme": "light", "current_page": "หน้าภาพรวม", "current_category": "ทั้งหมด",
        "flashcard_index": 0, "flashcard_flipped": False, "quiz": [], "quiz_index": 0,
        "quiz_answers": {}, "quiz_session_id": None, "quiz_complete": False,
        "practice_word_id": None, "practice_feedback": None,
    }
    for key, value in defaults.items():
        if key not in state:
            state[key] = value


def get_categories(words: list[dict[str, Any]] | None = None) -> list[str]:
    return get_category_names(words or DEFAULT_WORDS)


def get_filtered_vocab(category: str = "ทั้งหมด", words: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    source = words if words is not None else DEFAULT_WORDS
    if category in ("ทั้งหมด", "All", ""):
        return list(source)
    return [word for word in source if word.get("category") == category]


def create_quiz(words: Sequence[Mapping[str, Any]], count: int, *, distractor_pool: Sequence[Mapping[str, Any]] | None = None, seed: int | None = None) -> list[dict[str, Any]]:
    """Create questions with four unique translations where the vocabulary allows it."""
    rng = random.Random(seed)
    pool = list(distractor_pool if distractor_pool is not None else words)
    unique_words: list[Mapping[str, Any]] = []
    seen_words: set[str] = set()
    for item in words:
        key = str(item.get("word", "")).casefold()
        if key and key not in seen_words and str(item.get("translation", item.get("meaning", ""))).strip():
            unique_words.append(item)
            seen_words.add(key)
    rng.shuffle(unique_words)
    requested = max(0, int(count))
    selected = unique_words[:requested]
    option_pool: dict[str, Mapping[str, Any]] = {}
    for item in pool:
        translation = str(item.get("translation", item.get("meaning", ""))).strip()
        if translation:
            option_pool.setdefault(translation, item)
    questions: list[dict[str, Any]] = []
    for item in selected:
        answer = str(item.get("translation", item.get("meaning", ""))).strip()
        other_answers = [value for value in option_pool if value != answer]
        rng.shuffle(other_answers)
        options = [answer, *other_answers[:3]]
        if len(options) < 4:
            # Don't repeat answer options. If fewer than four distinct meanings exist, skip this question.
            continue
        rng.shuffle(options)
        questions.append({
            "word_id": item.get("id"), "word": str(item.get("word", "")),
            "translation": answer, "answer": answer, "options": options,
            "category": str(item.get("category", "ชีวิตประจำวัน")),
            "cefr": str(item.get("cefr", "A1")),
            "example": str(item.get("example", "")),
            "example_translation": str(item.get("example_translation", "")),
        })
    return questions


def get_result_level(percentage: float) -> str:
    if percentage >= 80:
        return "ดีมาก"
    if percentage >= 60:
        return "ดี"
    if percentage >= 40:
        return "พอใช้"
    return "ควรฝึกเพิ่มเติม"


def score_summary(answers: Sequence[Mapping[str, Any]]) -> dict[str, int | float]:
    total = len(answers)
    correct = sum(1 for item in answers if bool(item.get("is_correct")))
    incorrect = total - correct
    running = max_streak = 0
    for item in answers:
        if bool(item.get("is_correct")):
            running += 1
            max_streak = max(max_streak, running)
        else:
            running = 0
    return {
        "total": total, "correct": correct, "incorrect": incorrect,
        "max_streak": max_streak, "percentage": (correct / total * 100) if total else 0.0,
    }
