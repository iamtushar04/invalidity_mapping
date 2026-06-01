# app/embedding/text_utils.py
"""Utility functions for text handling used by the Qdrant embedding service.
"""
import re
from typing import Any, Iterable, Set

def normalize_text(text: Any) -> str:
    """Normalize raw text into a single cleaned string.
    Handles strings, lists of strings, and removes leading claim numbers.
    """
    if not text:
        return ""
    if isinstance(text, list):
        text = " ".join(text)
    text = re.sub(r"^\s*\d+\.\s*", "", text)
    text = " ".join(text.split()).strip()
    return text

def should_skip_embedding(text: str) -> bool:
    """Return True for short figure captions that we don't want to embed.
    Heuristic: starts with "fig." and less than 25 words.
    """
    if not text:
        return False
    lower = text.lower()
    return lower.startswith("fig.") and len(text.split()) < 25


def normalize_patent_number(patent_number: str) -> str:
    """Canonical form for matching and storage (no hyphens, uppercased)."""
    if not patent_number:
        return ""
    return patent_number.replace("-", "").replace(" ", "").strip().upper()


def patent_number_variants(*numbers: str) -> Set[str]:
    """All forms used for Qdrant filter matching."""
    variants: Set[str] = set()
    for num in numbers:
        if not num:
            continue
        variants.add(num.strip())
        variants.add(normalize_patent_number(num))
    variants.discard("")
    return variants


def patent_numbers_match(stored: str, *candidates: str) -> bool:
    """True if stored patent_number matches any candidate (hyphen-insensitive)."""
    if not stored:
        return False
    stored_forms = patent_number_variants(stored)
    for candidate in candidates:
        if stored_forms & patent_number_variants(candidate):
            return True
    return False
