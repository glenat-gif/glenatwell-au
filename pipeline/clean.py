"""Tidy council's auto-generated captions into a readable first draft.

This only does the mechanical part: known mis-hearings, filler words,
stammers and capital letters. A person still needs to read the result,
because the captions get local names wrong in new ways every month.
"""
import json
import pathlib
import re

RULES_FILE = pathlib.Path(__file__).with_name("corrections.json")


def load_rules(path=RULES_FILE):
    rules = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))["rules"]
    return [(re.compile(p, re.I), r.replace("$", "\\")) for p, r in rules]


def clean(text, rules=None):
    rules = load_rules() if rules is None else rules
    s = " " + " ".join(text.split()) + " "
    for pattern, replacement in rules:
        s = pattern.sub(replacement, s)
    s = re.sub(r"(^|[\s,])(um+|uh+|er)\b,?", r"\1", s, flags=re.I)      # fillers
    s = re.sub(r"\s+,", ",", s)
    s = re.sub(r",(\s*,)+", ",", s)
    s = re.sub(r"\.\s*,", ".", s)
    s = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", s, flags=re.I)              # "the the", "and and and"
    s = re.sub(r"\s{2,}", " ", s).strip().lstrip(",. ")
    s = re.sub(r"([.?!]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)
    return s[:1].upper() + s[1:]


def paragraphs(text, sentences_per_paragraph=4):
    """Break a cleaned transcript into short paragraphs so it can be read."""
    parts = re.split(r"(?<=[.?!])\s+", text)
    if len(parts) < 3:                       # older captions have no punctuation at all
        words = text.split()
        return [" ".join(words[i:i + 90]) for i in range(0, len(words), 90)]
    return [" ".join(parts[i:i + sentences_per_paragraph])
            for i in range(0, len(parts), sentences_per_paragraph)]
