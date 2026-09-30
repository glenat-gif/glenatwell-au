"""Optional: ask Claude to draft the headline, summary and topics for a new report.

Only runs when an ANTHROPIC_API_KEY is available (for example as a GitHub
Actions secret). Without one, the draft is created with the summary left
blank for a person to write. Whatever comes back is a draft for review.
"""
import json
import os
import re
import urllib.request

MODEL = os.environ.get("SUMMARY_MODEL", "claude-sonnet-5-5")

PROMPT = """Below is a transcript of a councillor's report to a Knox City Council meeting, \
taken from auto-generated captions (expect mis-heard names).

Reply with JSON only, in this shape:
{{"headline": "...", "summary": "...", "topics": ["...", "..."], "check": ["...", "..."]}}

- headline: under 90 characters, naming the two or three main subjects. No full stop.
- summary: 50 to 90 words, first person, plain Australian English, in the speaker's own
  register. Say only what the transcript says. No praise words the speaker did not use.
- topics: 3 to 8 short labels (2 to 5 words each).
- check: names of people, places or organisations that look mis-heard in the captions,
  each as "what the captions say: what it probably is".
- Never use em dashes.

Transcript:
{transcript}"""


def summarise(transcript):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": PROMPT.format(transcript=transcript)}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            text = json.loads(resp.read())["content"][0]["text"]
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        return {"headline": str(data.get("headline", "")).strip(),
                "summary": str(data.get("summary", "")).strip(),
                "topics": [str(t).strip() for t in data.get("topics", [])],
                "check": [str(c).strip() for c in data.get("check", [])]}
    except Exception as exc:                      # a failed summary must not stop the draft
        print(f"  summary step skipped: {exc}")
        return None
