"""Load vocabulary data from a JSON file, keeping content separate from UI logic."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
VOCABULARY_FILE = DATA_DIR / "vocabulary.json"

CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
POS_LABELS = {
    "noun": "คำนาม", "verb": "คำกริยา", "adjective": "คำคุณศัพท์",
    "adverb": "คำวิเศษณ์", "pronoun": "คำสรรพนาม", "preposition": "คำบุพบท",
    "conjunction": "คำเชื่อม", "interjection": "คำอุทาน", "phrase": "วลี",
    "phrasal verb": "คำกริยาวลี", "idiom": "สำนวน", "determiner": "คำกำหนดนาม",
}


def normalize_word(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept the current JSON shape and common CSV/import field aliases."""
    word = str(raw.get("word", raw.get("english", raw.get("e-entry", "")))).strip()
    translation = str(raw.get("translation", raw.get("meaning", raw.get("thai", raw.get("t-entry", raw.get("t-def", "")))))).strip()
    if not word or not translation:
        raise ValueError("แต่ละรายการต้องมีคำศัพท์ภาษาอังกฤษและคำแปลภาษาไทย")
    pos = str(raw.get("pos", raw.get("part_of_speech", raw.get("e-cat", "")))).strip().lower()
    cefr = str(raw.get("cefr", "A1")).strip().upper()
    if cefr not in CEFR_LEVELS:
        cefr = "A1"
    category = str(raw.get("category", "ชีวิตประจำวัน")).strip() or "ชีวิตประจำวัน"
    synonyms = raw.get("synonyms", raw.get("synonym", raw.get("e-syn", [])))
    if isinstance(synonyms, str):
        synonyms = [s.strip() for s in synonyms.replace(";", ",").split(",") if s.strip()]
    elif not isinstance(synonyms, list):
        synonyms = []
    return {
        "word": word,
        "translation": translation,
        "pos": pos,
        "cefr": cefr,
        "category": category,
        "pronunciation": str(raw.get("pronunciation", raw.get("ipa", ""))).strip(),
        "example": str(raw.get("example", raw.get("example_en", ""))).strip(),
        "example_translation": str(raw.get("example_translation", raw.get("example_th", ""))).strip(),
        "synonyms": [str(s).strip() for s in synonyms if str(s).strip()],
    }


def load_vocabulary(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load a UTF-8 JSON/CSV vocabulary file and deduplicate by English word."""
    file_path = Path(path) if path else VOCABULARY_FILE
    if not file_path.exists():
        return []
    if file_path.suffix.lower() == ".csv":
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    else:
        with file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        rows = payload.get("words", payload) if isinstance(payload, dict) else payload
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not isinstance(rows, list):
        raise ValueError("รูปแบบไฟล์คำศัพท์ต้องเป็นรายการคำศัพท์ หรือมีคีย์ words")
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            word = normalize_word(row)
        except ValueError:
            continue
        key = word["word"].casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(word)
    return result


DEFAULT_WORDS = load_vocabulary()
# Backwards-compatible alias used by the original app.
VOCABULARY = DEFAULT_WORDS


def get_category_names(words: list[dict[str, Any]] | None = None) -> list[str]:
    items = words if words is not None else DEFAULT_WORDS
    return sorted({str(item.get("category", "ชีวิตประจำวัน")) for item in items}, key=str.casefold)
