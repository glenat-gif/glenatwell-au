"""Report files: one plain-text file per report in content/reports/.

The format is deliberately simple so a report can be edited in any text
editor or in GitHub's web editor:

    ---
    date: 2026-09-28
    status: draft
    youtube:
    ...
    ---

    ## Summary
    ...

    ## Transcript
    ...
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS = ROOT / "content" / "reports"
FIELDS = ["date", "status", "youtube", "headline", "video_title", "kind", "label", "item", "outcome", "featured",
          "summary_label", "image", "image_focus", "image_caption", "gallery", "role", "meeting_url", "video_url",
          "clip_start", "clip_end", "meeting_length", "timing", "topics", "check"]
LISTS = {"topics", "check", "gallery"}
OPTIONAL = {"video_title", "kind", "label", "item", "outcome", "featured", "summary_label", "image", "image_focus", "image_caption", "gallery"}   # left out of the file when empty


def read_report(path):
    text = pathlib.Path(path).read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        raise ValueError(f"{path}: missing the '---' header block")
    report = {f: ([] if f in LISTS else "") for f in FIELDS}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        report[key] = [v.strip() for v in value.split("|") if v.strip()] if key in LISTS else value
    body = m.group(2)
    summary = re.search(r"## Summary\n(.*?)(?=\n## |\Z)", body, re.S)
    transcript = re.search(r"## Transcript\n(.*)\Z", body, re.S)
    motion = re.search(r"## Motion\n(.*?)(?=\n## |\Z)", body, re.S)     # optional: the wording of a notice of motion
    report["summary"] = summary.group(1).strip() if summary else ""
    report["motion"] = motion.group(1).strip() if motion else ""
    report["transcript"] = transcript.group(1).strip() if transcript else ""
    for key in ("clip_start", "clip_end", "meeting_length"):
        report[key] = float(report[key]) if report[key] else None
    report["path"] = str(path)
    report["slug"] = pathlib.Path(path).stem      # the page address: reports/<slug>.html
    report["kind"] = report["kind"] or "report"
    return report


def write_report(report, path=None):
    path = pathlib.Path(path or REPORTS / f"{report['date']}.md")
    lines = ["---"]
    for key in FIELDS:
        value = report.get(key, "")
        if key in LISTS:
            value = " | ".join(value or [])
        elif value is None:
            value = ""
        if key in OPTIONAL and not value:
            continue
        lines.append(f"{key}: {value}".rstrip())
    lines += ["---", "", "## Summary", "", report.get("summary", "").strip(), ""]
    if report.get("motion"):
        lines += ["## Motion", "", report["motion"].strip(), ""]
    lines += ["## Transcript", "", report.get("transcript", "").strip(), ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def all_reports():
    return sorted((read_report(p) for p in REPORTS.glob("*.md")),
                  key=lambda r: r["date"], reverse=True)
