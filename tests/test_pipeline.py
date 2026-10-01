"""Checks for the pipeline. Run with:  python -m unittest discover tests -v

The fixtures are excerpts of council's real pages, so these tests fail loudly
if the parsing drifts from the markup the webcast site actually serves.
"""
import functools
import json
import http.server
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline import clean, content, knox, run  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
ALIASES = ["atwell", "at well", "outwell", "howwell"]


class Parsing(unittest.TestCase):
    def setUp(self):
        url = "https://webcast.knox.vic.gov.au/archive/video26-0928.php"
        self.info = knox.parse_meeting((FIX / "video26-0928.html").read_text(), url)
        self.cues = knox.parse_vtt((FIX / "knox-260928.vtt").read_text())

    def test_archive_list(self):
        meetings = knox.parse_archive((FIX / "archive.html").read_text())
        self.assertEqual([m["date"] for m in meetings], ["2026-09-28", "2026-09-14", "2025-12-08"])
        self.assertEqual(meetings[0]["id"], "26-0928")
        self.assertEqual(meetings[0]["type"], "Council Meeting")

    def test_meeting_page(self):
        self.assertEqual(self.info["video_url"], "https://cdn.interstream-media.com/council/knox/knox-260928.mp4")
        self.assertEqual(self.info["vtt_url"], "https://webcast.knox.vic.gov.au/archive/subtitles/knox-260928.vtt")
        self.assertEqual(len(self.info["items"]), 21)
        self.assertEqual(self.info["items"][0], {"title": "1 Apologies And Requests For Leaves Of Absence", "start": 195.0})

    def test_find_report(self):
        found = knox.find_report(self.info["items"], "Atwell")
        self.assertEqual(found, {"title": "5.5 Cr Glen Atwell", "start": 1708.0, "end": 1946.0})
        self.assertIsNone(knox.find_report(self.info["items"], "Nobody"))

    def test_end_is_next_in_time_not_next_in_list(self):
        # Public question time (3291s) is listed before officer reports (2825s).
        items = self.info["items"]
        self.assertEqual(knox.find_report(items, "Planning Applications")["end"], 2825.0)

    def test_refine_uses_captions(self):
        start, end, timing = knox.refine(self.cues, 1708.0, 1946.0, ALIASES)
        self.assertEqual((start, end, timing), (1710.5, 1945.1, "auto"))

    def test_refine_falls_back_to_index(self):
        self.assertEqual(knox.refine([], 1708.0, 1946.0, ALIASES), (1708.0, 1946.0, "index"))

    def test_segment_text(self):
        text = knox.segment_text(self.cues, 1710.5, 1945.1)
        self.assertTrue(text.startswith("thank you Mayor. a few things"))
        self.assertTrue(text.endswith("tonight. Thank you, Mayor."))


class Cleaning(unittest.TestCase):
    def test_clean(self):
        raw = "thank you Mayor. first the um the telecommunications tower in in Roville, councelor Duncan"
        self.assertEqual(clean.clean(raw),
                         "Thank you Mayor. First the telecommunications tower in Rowville, Councillor Duncan")

    def test_paragraphs(self):
        self.assertEqual(len(clean.paragraphs("One. Two. Three. Four. Five.", 2)), 3)


class ReportFiles(unittest.TestCase):
    def test_round_trip(self):
        report = {"date": "2030-01-28", "status": "draft", "youtube": "", "headline": "A: b", "role": "Councillor",
                  "meeting_url": "https://example.org/m", "video_url": "https://example.org/v.mp4",
                  "clip_start": 10.5, "clip_end": 99.0, "timing": "auto", "topics": ["One", "Two"],
                  "check": ["Look: here"], "summary": "Short.", "transcript": "Para one.\n\nPara two."}
        with tempfile.TemporaryDirectory() as tmp:
            back = content.read_report(content.write_report(report, pathlib.Path(tmp) / "r.md"))
        for key, value in report.items():
            self.assertEqual(back[key], value, key)

    def test_every_report_file_is_sound(self):
        reports = content.all_reports()
        self.assertTrue(reports)
        for r in reports:
            self.assertRegex(r["date"], r"^\d{4}-\d\d-\d\d$")
            self.assertIn(r["status"], ("draft", "published"))
            self.assertLess(r["clip_start"], r["clip_end"])
            self.assertTrue(r["headline"] and r["summary"] and r["transcript"], r["date"])
            self.assertTrue(r["video_url"].endswith(f"knox-{r['date'][2:].replace('-', '')}.mp4"), r["date"])
            self.assertFalse(re.search(chr(0x2014), pathlib.Path(r["path"]).read_text()), r["date"])

    def test_youtube_titles_lead_with_the_topic_and_fit(self):
        for r in content.all_reports():
            title = run.youtube_text(r).splitlines()[0]
            self.assertLessEqual(len(title), 100, title)
            self.assertTrue(title.startswith(r["video_title"] or r["headline"][:20]), title)
        sample = dict(content.all_reports()[0], video_title="Stud Road phone tower and The Dizzy Rooster", date="2026-09-28")
        self.assertEqual(run.youtube_text(sample).splitlines()[0],
                         "Stud Road phone tower and The Dizzy Rooster | Cr Glen Atwell, Rowville and Scoresby, 28 Sep 2026")


class CheckCommand(unittest.TestCase):
    def test_check_drafts_new_report_and_records_the_rest(self):
        pages = {"archive.php": (FIX / "archive.html").read_text(),
                 "video26-0928.php": (FIX / "video26-0928.html").read_text(),
                 "knox-260928.vtt": (FIX / "knox-260928.vtt").read_text()}
        no_report = '<a onclick="document.getElementById(\'video\').currentTime = 5 ">1 Apologies</a>'

        def fake_fetch(url, timeout=60):
            return pages.get(url.rsplit("/", 1)[-1], no_report)

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(knox, "fetch", fake_fetch), \
                mock.patch.object(content, "REPORTS", pathlib.Path(tmp) / "reports"), \
                mock.patch.object(run, "STATE_FILE", pathlib.Path(tmp) / "meetings.json"):
            run.main(["check", "--no-clip"])
            draft = content.read_report(pathlib.Path(tmp) / "reports" / "2026-09-28.md")
            state = json.loads((pathlib.Path(tmp) / "meetings.json").read_text())
        self.assertEqual((draft["status"], draft["clip_start"], draft["clip_end"], draft["timing"]),
                         ("draft", 1710.5, 1945.1, "auto"))
        self.assertEqual(draft["role"], "Councillor")
        self.assertIn("Rowville", draft["transcript"])
        self.assertEqual(state["26-0914"]["status"], "no-report")
        self.assertNotIn("26-0928", state)


class _RangeHandler(http.server.SimpleHTTPRequestHandler):
    """A minimal file server that honours Range requests, like council's video host."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = pathlib.Path(self.translate_path(self.path))
        size = path.stat().st_size
        m = re.match(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        first = int(m.group(1)) if m else 0
        last = int(m.group(2)) if m and m.group(2) else size - 1
        self.send_response(206 if m else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(last - first + 1))
        if m:
            self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
        self.end_headers()
        with open(path, "rb") as fh:
            fh.seek(first)
            try:
                self.wfile.write(fh.read(last - first + 1))
            except (BrokenPipeError, ConnectionResetError):
                pass


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not installed")
class Clipping(unittest.TestCase):
    def test_cut_clip_over_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25",
                 "-f", "lavfi", "-i", "sine=frequency=440", "-t", "90", "-c:v", "libx264", "-preset", "ultrafast",
                 "-c:a", "aac", "-movflags", "+faststart", str(tmp / "meeting.mp4")], check=True)
            server = http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0), functools.partial(_RangeHandler, directory=str(tmp)))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                url = f"http://127.0.0.1:{server.server_address[1]}/meeting.mp4"
                out = run.cut_clip(url, 40.5, 71.0, tmp / "clips" / "clip.mp4")
            finally:
                server.shutdown()
                server.server_close()
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                capture_output=True, text=True, check=True)
            self.assertAlmostEqual(float(probe.stdout), 30.5, delta=0.2)


if __name__ == "__main__":
    unittest.main()
