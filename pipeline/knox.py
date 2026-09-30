"""Read Knox City Council's meeting webcast site.

Everything here is parsing: the archive list, a meeting page's agenda index
(each agenda link carries its start time in seconds), and the caption file.
"""
import datetime as dt
import html
import re
import urllib.request
from urllib.parse import urljoin

BASE = "https://webcast.knox.vic.gov.au"
USER_AGENT = "atwell-reports/1.0 (councillor report archive)"

ROW = re.compile(
    r'<a href="([^"]*archive/video(\d\d)-(\d\d)(\d\d)\.php)"[^>]*>.*?</a>\s*</td>'
    r"\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>",
    re.S,
)
ITEM = re.compile(r'onclick="[^"]*currentTime\s*=\s*([\d.]+)[^"]*"[^>]*>(.*?)</a>', re.S)
SOURCE = re.compile(r'<source[^>]+src="([^"]+\.mp4)"', re.I)
TRACK = re.compile(r'<track[^>]+src="([^"]+\.vtt)"', re.I)
CUE = re.compile(r"([\d:.]+)\s+-->\s+([\d:.]+)[^\n]*\n(.*)", re.S)
THANKS = re.compile(r"thank(s| you),?\s+(deputy mayor,?\s+)?(cr|coun[cs]e?l+or)", re.I)


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def archive_url(page):
    return f"{BASE}/archive.php" if page <= 1 else f"{BASE}/archive{page}.php"


def parse_archive(page_html):
    """Meetings listed on one archive page, newest first."""
    meetings = []
    for url, yy, mm, dd, _date_text, kind in ROW.findall(page_html):
        meetings.append({
            "id": f"{yy}-{mm}{dd}",
            "date": dt.date(2000 + int(yy), int(mm), int(dd)).isoformat(),
            "url": urljoin(BASE + "/", url).replace("http://", "https://"),
            "type": " ".join(kind.split()),
        })
    return meetings


def parse_meeting(page_html, page_url):
    """Agenda index, video address and caption address for one meeting."""
    items = [
        {"title": " ".join(html.unescape(re.sub(r"<[^>]+>", "", t)).split()), "start": float(s)}
        for s, t in ITEM.findall(page_html)
    ]
    source = SOURCE.search(page_html)
    track = TRACK.search(page_html)
    return {
        "items": items,
        "video_url": source.group(1) if source else None,
        "vtt_url": urljoin(page_url, track.group(1)) if track else None,
    }


def find_report(items, surname):
    """The agenda item for this councillor, and where the next item begins.

    Agenda times are not always in order (public question time can be listed
    before an item that was heard earlier), so the end is the earliest item
    that starts after ours rather than simply the next one in the list.
    """
    name = re.compile(rf"\b{re.escape(surname)}\b", re.I)
    for item in items:
        if name.search(item["title"]):
            later = [i["start"] for i in items if i["start"] > item["start"]]
            return {"title": item["title"], "start": item["start"], "end": min(later) if later else None}
    return None


def _seconds(stamp):
    parts = [float(p) for p in stamp.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def parse_vtt(text):
    cues = []
    for block in re.split(r"\r?\n\r?\n", text):
        m = CUE.search(block)
        if m:
            cues.append({"start": _seconds(m.group(1)), "end": _seconds(m.group(2)),
                         "text": " ".join(m.group(3).split())})
    return cues


def refine(cues, start, end, aliases):
    """Tighten the agenda index times using the captions.

    The index marks roughly where the Mayor calls the councillor. The clip
    should start once the Mayor has said the name and stop when the Mayor
    thanks them. Where the captions don't show either, keep the index time.
    Returns (clip_start, clip_end, timing) with timing one of auto/index/mixed.
    """
    name = re.compile("|".join(re.escape(a) for a in aliases), re.I)
    clip_start, clip_end, found = start, end, 0
    calls = [c for c in cues if start - 20 <= c["start"] <= start + 20 and name.search(c["text"])]
    if calls:
        clip_start, found = calls[-1]["end"], found + 1
    if end is not None:
        thanks = [c for c in cues
                  if end - 25 <= c["start"] <= end + 8 and c["start"] > clip_start + 20
                  and THANKS.search(c["text"])]
        if thanks:
            clip_end, found = thanks[-1]["start"], found + 1
    return round(clip_start, 1), (round(clip_end, 1) if clip_end is not None else None), \
        {2: "auto", 1: "mixed", 0: "index"}[found]


def segment_text(cues, clip_start, clip_end):
    return " ".join(c["text"] for c in cues
                    if c["end"] > clip_start + 0.3 and c["start"] < clip_end - 0.3)
