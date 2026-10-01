"""Command line for the report pipeline.

  python -m pipeline.run check              look for new meetings and draft any new report
  python -m pipeline.run clip 2026-09-28    cut the video clip for one report
  python -m pipeline.run clip all           cut clips for every report that has no YouTube ID yet
  python -m pipeline.run inspect 26-0928    show what the webcast page says for one meeting
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

from . import clean, content, knox, summarise

ROOT = content.ROOT
SITE = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
STATE_FILE = ROOT / "data" / "meetings.json"
TERM_START = "2024-11-11"      # sworn in; nothing earlier can contain a report
GIVE_UP_DAYS = 21              # how long to wait for council to add the agenda index


def long_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d:%B %Y}"


def short_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d:%b %Y}"


def role_from(title):
    t = title.lower()
    if "deputy mayor" in t:
        return "Deputy Mayor"
    return "Mayor" if t.lstrip("0123456789. ").startswith("mayor") else "Councillor"


def cut_clip(video_url, start, end, out):
    """Cut one clip straight from council's file. ffmpeg only reads the part it needs."""
    out = pathlib.Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{start:.2f}", "-to", f"{end:.2f}", "-i", video_url,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)],
        check=True)
    return out


def meeting_length(video_url):
    """Length of the whole meeting recording in seconds, or None if it can't be read."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", video_url], capture_output=True, text=True, timeout=120)
        return round(float(out.stdout.strip()))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def youtube_text(report):
    """Title and description to paste into YouTube when uploading the clip."""
    ward = f"{SITE['ward']} ({SITE['suburbs']})"
    # The topic leads, because YouTube cuts a title at about 55 characters in a list. 100 is its hard limit.
    tail = f" | {SITE['councillor']}, {SITE['suburbs']}, {short_date(report['date'])}"
    lead = report.get("video_title") or report["headline"]
    title = lead[:100 - len(tail)].rstrip(" ,") + tail
    lines = [title,
             "", report.get("summary", "").strip(), "",
             (f"{report['label']}. " if report.get("label") else "")
             + f"From the {SITE['council']} meeting of {long_date(report['date'])}.",
             f"{SITE['councillor']}, {ward}.",
             f"Full meeting: {report['meeting_url']}"]
    if SITE.get("base_url"):
        lines.append(f"Transcript: {SITE['base_url'].rstrip('/')}/reports/{report.get('slug', report['date'])}.html")
    return "\n".join(lines) + "\n"


def make_clip(report, clips_dir):
    slug = report.get("slug", report["date"])
    name = f"{slug}-councillor-report" if slug == report["date"] else slug
    out = pathlib.Path(clips_dir) / f"{name}.mp4"
    cut_clip(report["video_url"], report["clip_start"], report["clip_end"], out)
    out.with_suffix(".txt").write_text(youtube_text(report), encoding="utf-8")
    return out


def draft_report(meeting, info, found):
    cues = knox.parse_vtt(knox.fetch(info["vtt_url"])) if info["vtt_url"] else []
    end = found["end"] if found["end"] is not None else found["start"] + 300
    clip_start, clip_end, timing = knox.refine(cues, found["start"], end, SITE["caption_aliases"])
    text = clean.clean(knox.segment_text(cues, clip_start, clip_end)) if cues else ""
    report = {
        "date": meeting["date"], "status": "draft", "youtube": "", "headline": "", "video_title": "",
        "role": role_from(found["title"]), "meeting_url": meeting["url"],
        "video_url": info["video_url"], "clip_start": clip_start, "clip_end": clip_end,
        "meeting_length": meeting_length(info["video_url"]) if info["video_url"] else None,
        "timing": timing, "topics": [], "summary": "",
        "transcript": "\n\n".join(clean.paragraphs(text)),
        "check": ["Write the video_title for YouTube: the top one or two topics, 47 characters or fewer",
                  "Watch the clip: does it start and end cleanly?",
                  "Read the transcript against the video (captions mis-hear local names)"],
    }
    if timing != "auto":
        report["check"].insert(0, "Clip times came from the agenda index, not the captions: check both ends")
    if found["end"] is None:
        report["check"].insert(0, "No later agenda item to mark the end: clip_end is a guess")
    if not cues:
        report["check"].append("No captions were published for this meeting: add the transcript by hand")
    drafted = summarise.summarise(text) if text else None
    if drafted:
        report.update(headline=drafted["headline"], summary=drafted["summary"], topics=drafted["topics"])
        report["check"] += [f"Caption query, {c}" for c in drafted["check"]]
    else:
        report["check"].append("Write the headline, summary and topics")
    return report


def cmd_check(args):
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    today, new = dt.date.today(), []
    for page in range(1, args.pages + 1):
        for meeting in knox.parse_archive(knox.fetch(knox.archive_url(page))):
            if meeting["date"] < TERM_START:
                continue
            if (content.REPORTS / f"{meeting['date']}.md").exists():
                continue
            if state.get(meeting["id"], {}).get("status") in ("no-report", "no-index"):
                continue
            if meeting["date"] in args.skip:      # a draft is already waiting for review
                continue
            info = knox.parse_meeting(knox.fetch(meeting["url"]), meeting["url"])
            found = knox.find_report(info["items"], SITE["surname"])
            if not found:
                age = (today - dt.date.fromisoformat(meeting["date"])).days
                status = "no-report" if info["items"] else ("no-index" if age > GIVE_UP_DAYS else "pending")
                state[meeting["id"]] = {"date": meeting["date"], "status": status}
                print(f"{meeting['date']}: {status}")
                continue
            report = draft_report(meeting, info, found)
            path = content.write_report(report)
            print(f"{meeting['date']}: drafted {path.name} "
                  f"({report['clip_start']}s to {report['clip_end']}s, timing {report['timing']})")
            if not args.no_clip:
                print(f"  clip: {make_clip(report, args.clips)}")
            new.append(meeting["date"])
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write(f"new={' '.join(new)}\n")
    if not new:
        print("No new reports.")


def cmd_clip(args):
    reports = content.all_reports()
    if args.which != "all":
        reports = [r for r in reports if args.which in (r["date"], r["slug"])]
        if not reports:
            sys.exit(f"No report file for {args.which}")
    else:
        reports = [r for r in reports if not r["youtube"]]
    for report in reports:
        print(f"{report['slug']}: {make_clip(report, args.clips)}")


def cmd_inspect(args):
    url = f"{knox.BASE}/archive/video{args.meeting}.php"
    info = knox.parse_meeting(knox.fetch(url), url)
    for item in info["items"]:
        print(f"{item['start']:>8.0f}s  {item['title']}")
    print("video:", info["video_url"], "\ncaptions:", info["vtt_url"])
    print("report:", knox.find_report(info["items"], SITE["surname"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check")
    p.add_argument("--pages", type=int, default=1, help="archive pages to scan (20 meetings each)")
    p.add_argument("--clips", default="clips")
    p.add_argument("--no-clip", action="store_true")
    p.add_argument("--skip", nargs="*", default=[], help="meeting dates that already have a draft open")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("clip")
    p.add_argument("which", help='a report date such as 2026-09-28, or "all"')
    p.add_argument("--clips", default="clips")
    p.set_defaults(func=cmd_clip)
    p = sub.add_parser("inspect")
    p.add_argument("meeting", help="meeting id as it appears in the web address, e.g. 26-0928")
    p.set_defaults(func=cmd_inspect)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
