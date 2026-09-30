"""Build the website from the report files.

  python build.py            public site: published reports only, written to dist/
  python build.py --drafts   preview: includes drafts, with their review notes

A report is public when its file says `status: published` and has a YouTube ID.
"""
import argparse
import datetime as dt
import html
import json
import pathlib
import shutil
import sys

from pipeline import content

ROOT = pathlib.Path(__file__).resolve().parent
SITE = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
FONTS = ("https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500..800"
         "&family=Hanken+Grotesk:wght@400;500;600"
         "&family=Newsreader:ital,opsz,wght@0,6..72,400;1,6..72,400&display=swap")
# Accent name: (fill colour, colour of text and icons placed on that fill).
ACCENTS = {"orange": ("#ea8d30", "#171b36"), "wattle": ("#f5b800", "#1b1500"), "violet": ("#8f72ff", "#0f0830")}
PHOTO = ROOT / "static" / "glen.jpg"          # optional portrait for the About section
e = html.escape


def long_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d:%B %Y}"


def seconds_of(report):
    return round(report["clip_end"] - report["clip_start"])


def duration(report):
    s = seconds_of(report)
    return f"{s // 60} min {s % 60:02d} s"


def timecode(seconds):
    seconds = int(seconds)
    h, m, s = seconds // 3600, seconds % 3600 // 60, seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def hours_minutes(seconds):
    h, m = int(seconds) // 3600, round(int(seconds) % 3600 / 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def paragraphs(text):
    return "\n".join(f"<p>{e(p.strip())}</p>" for p in text.split("\n\n") if p.strip())


def page(title, description, body, root, preview, path="", fragment=False):
    """One full HTML page. `root` is the relative path back to the site's top folder."""
    accent = ACCENTS.get(SITE.get("accent"), ACCENTS["orange"])
    canonical = (f'<link rel="canonical" href="{e(SITE["base_url"].rstrip("/"))}/{path}">'
                 if SITE.get("base_url") and not preview else "")
    share = (f'<meta property="og:image" content="{e(SITE["base_url"].rstrip("/"))}/{e(SITE["share_image"])}">'
             '\n<meta name="twitter:card" content="summary">'
             if SITE.get("base_url") and SITE.get("share_image") else "")
    icon = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
            "%3Crect width='32' height='32' rx='7' fill='%23202648'/%3E"
            f"%3Ccircle cx='16' cy='16' r='7' fill='%23{accent[0][1:]}'/%3E%3C/svg%3E")
    head = f"""<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:type" content="website">
{share}
{canonical}
<link rel="icon" href="{icon}">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>
{CSS}
[hidden] {{ display: none !important; }}
:root {{ --accent: {accent[0]}; --on-accent: {accent[1]}; }}
</style>"""
    notice = ('<div class="notice"><div class="wrap">Preview. This build includes drafts that are not public yet.'
              "</div></div>") if preview else ""
    contact = f'<p>Contact: {e(SITE["contact_email"])}</p>' if SITE.get("contact_email") else ""
    swatches = ""
    if preview:
        buttons = "".join(f'<button type="button" data-accent="{name}" style="background:{fill}" '
                          f'aria-label="{name.title()} accent" aria-pressed="false"></button>'
                          for name, (fill, _) in ACCENTS.items())
        swatches = f"""<div class="swatches" id="swatches">Accent {buttons}</div>
<script>
(function () {{
  var accents = {json.dumps(ACCENTS)}, start = {json.dumps(SITE.get("accent", "orange"))};
  var buttons = [].slice.call(document.querySelectorAll('#swatches button'));
  function set(name) {{
    var a = accents[name]; if (!a) return;
    document.documentElement.style.setProperty('--accent', a[0]);
    document.documentElement.style.setProperty('--on-accent', a[1]);
    buttons.forEach(function (b) {{ b.setAttribute('aria-pressed', String(b.dataset.accent === name)); }});
    try {{ localStorage.setItem('accent', name); }} catch (err) {{}}
  }}
  var saved = null; try {{ saved = localStorage.getItem('accent'); }} catch (err) {{}}
  set(accents[saved] ? saved : start);
  buttons.forEach(function (b) {{ b.addEventListener('click', function () {{ set(b.dataset.accent); }}); }});
}})();
</script>"""
    inner = f"""{notice}
{body}
<footer><div class="wrap">
<a class="wordmark" href="{root}index.html">{e(SITE["site_title"])}</a>
<p>This is {e(SITE["councillor"])}'s own website. It is not a {e(SITE["council"])} website, and the views expressed are his own.</p>
<p>Video and captions come from {e(SITE["council"])}'s public meeting webcast. Transcripts are edited from the auto-generated captions and may contain errors. The video is the record.</p>
{contact}
</div></footer>
{swatches}"""
    if fragment:                      # for a preview host that supplies its own <html> wrapper
        return head + "\n" + inner + "\n"
    return f"""<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{head}
</head>
<body>
{inner}
</body>
</html>
"""


def nav(root):
    media = f'<li><a href="{root}index.html#media">Media</a></li>' if SITE.get("media") else ""
    return f"""<nav class="nav">
<a class="wordmark" href="{root}index.html">{e(SITE["site_title"])}</a>
<ul><li><a href="{root}index.html#reports">Reports</a></li>{media}<li><a href="{root}index.html#about">About</a></li></ul>
</nav>"""


def poster(report, preview):
    """The 16:9 tile for a report: the YouTube still when there is one, otherwise the date."""
    d = dt.date.fromisoformat(report["date"])
    image, cls = "", "poster"
    if report["image"]:
        focus = f' style="object-position:{e(report["image_focus"])}"' if report["image_focus"] else ""
        image = f'<img src="photos/{e(report["image"])}" alt="" loading="lazy"{focus}>'
        cls = "poster has-image"
    elif report["youtube"]:
        base = f"https://i.ytimg.com/vi/{e(report['youtube'])}"
        image = (f'<img src="{base}/maxresdefault.jpg" alt="" loading="lazy" '
                 f"onload=\"if(this.naturalWidth&lt;200)this.src='{base}/hqdefault.jpg'\" "
                 f"onerror=\"this.onerror=null;this.src='{base}/hqdefault.jpg'\">")
        cls = "poster has-image"
    flags = '<span class="draft-flag">Draft</span>' if preview and report["status"] != "published" else ""
    if report["kind"] != "report":
        flags += f'<span class="kind-flag">{e(report["kind"].title())}</span>'
    flag = f'<span class="flags">{flags}</span>' if flags else ""
    strip = ""
    if report["meeting_length"]:      # where the clip sits within the whole meeting
        left = report["clip_start"] / report["meeting_length"] * 100
        width = seconds_of(report) / report["meeting_length"] * 100
        strip = f'<span class="poster-strip"><i style="left:{left:.2f}%;width:{width:.2f}%"></i></span>'
    return (f'<span class="{cls}">{image}{flag}<span class="poster-len mono">{timecode(seconds_of(report))}</span>'
            f'<span class="poster-date"><b>{d.day}</b><span>{d:%b %Y}</span></span><span class="play"></span>'
            f'{strip}</span>')


def card(report, preview):
    text = " ".join([report["headline"], " ".join(report["topics"]), report["summary"]]).lower()
    return f"""<a class="card" href="reports/{report['slug']}.html" data-key="{report['slug']}" data-text="{e(text)}">
{poster(report, preview)}
<span><h4>{e(report['headline'])}</h4><p>{e(' · '.join(report['topics'][:3]))}</p></span>
</a>"""


def term_timeline(reports):
    start, end = dt.date.fromisoformat(SITE["term_start"]), dt.date.fromisoformat(SITE["term_end"])
    span = (end - start).days

    def at(day):
        return max(0.0, min(100.0, (day - start).days / span * 100))

    ticks = "".join(
        f'<a href="reports/{r["slug"]}.html" style="left:{at(dt.date.fromisoformat(r["date"])):.2f}%" '
        f'title="{long_date(r["date"])}: {e(r["headline"])}" aria-label="Report of {long_date(r["date"])}"></a>'
        for r in reversed(reports))
    now = at(dt.date.today())
    return f"""<div class="term mono" aria-label="Reports across the council term">
<div class="term-track">{ticks}<span class="term-now" style="left:{now:.2f}%"><span>Now</span></span></div>
<div class="term-ends"><span>{start:%b %Y} · term begins</span><span>Election · {end:%b %Y}</span></div>
</div>"""


SEARCH_JS = """<script>
(function () {
  var input = document.getElementById('q'), out = document.getElementById('q-count');
  var cards = [].slice.call(document.querySelectorAll('.card')), spoken = {}, asked = false;
  function load() {
    if (asked) return; asked = true;
    fetch('search.json').then(function (r) { return r.ok ? r.json() : []; })
      .then(function (rows) { rows.forEach(function (r) { spoken[r.d] = r.t; }); run(); })
      .catch(function () {});
  }
  function run() {
    var terms = input.value.toLowerCase().split(/\\s+/).filter(Boolean), shown = 0;
    cards.forEach(function (c) {
      var hay = c.dataset.text + ' ' + (spoken[c.dataset.key] || '');
      var ok = terms.every(function (t) { return hay.indexOf(t) > -1; });
      c.hidden = !ok; if (ok) shown++;
    });
    [].forEach.call(document.querySelectorAll('.year'), function (y) {
      y.hidden = !y.querySelector('.card:not([hidden])');
    });
    document.getElementById('q-empty').hidden = shown > 0;
    out.textContent = terms.length ? shown + ' of ' + cards.length + ' reports mention \\u201c' + input.value.trim() + '\\u201d' : '';
  }
  input.addEventListener('focus', load);
  input.addEventListener('input', function () { load(); run(); });
})();
</script>"""


def feature_block(item, preview):
    """The pinned piece at the top of the home page."""
    opening = paragraphs("\n\n".join(item["summary"].split("\n\n")[:2]))
    label = " · ".join(x for x in [item["label"], long_date(item["date"])] if x)
    outcome = f'<span class="outcome">{e(item["outcome"])}</span>' if item["outcome"] else ""
    return f"""<section class="feature">
<a href="reports/{item['slug']}.html" aria-label="Watch: {e(item['headline'])}">{poster(item, preview)}</a>
<div>
<p class="eyebrow">Featured · {e(label)}</p>
<h2><a href="reports/{item['slug']}.html">{e(item['headline'])}</a></h2>
{opening}
<p class="feature-actions"><a class="button" href="reports/{item['slug']}.html">Watch the speech · {timecode(seconds_of(item))}</a>{outcome}</p>
</div>
</section>"""


def index_page(items, preview, fragment=False):
    reports = [r for r in items if r["kind"] == "report"] or items
    featured = next((r for r in items if r["featured"]), None)
    latest = reports[0]
    first = dt.date.fromisoformat(items[-1]["date"])
    minutes = round(sum(seconds_of(r) for r in items) / 60)
    years = sorted({r["date"][:4] for r in items}, reverse=True)
    groups = "\n".join(
        f'<section class="year"><h3>{year}</h3>\n<div class="grid">\n'
        + "\n".join(card(r, preview) for r in items if r["date"].startswith(year))
        + "\n</div></section>" for year in years)
    if PHOTO.exists():
        side = '<figure class="portrait"><img src="glen.jpg" alt="Glen Atwell" width="800" height="1201"></figure>'
    else:
        side = f"""<a class="latest" href="reports/{latest['slug']}.html">
{poster(latest, preview)}
<span class="latest-text"><span class="eyebrow">Latest report · {long_date(latest['date'])}</span>
<h2>{e(latest['headline'])}</h2></span>
</a>"""
    media = ""
    if SITE.get("media"):
        rows = "".join(
            f'<li><span class="mono">{e(m["outlet"])} · {long_date(m["date"])}</span>'
            f'<a href="{e(m["url"])}">{e(m["title"])}</a></li>' for m in SITE["media"])
        media = f'<section class="media" id="media"><h2>In the media</h2><ul>{rows}</ul></section>'
    about = SITE["about"] if isinstance(SITE["about"], list) else [SITE["about"]]
    feature = feature_block(featured, preview) if featured else ""
    figures = "".join(
        f'<figure><img src="photos/{e(ph["file"])}" alt="{e(ph["alt"])}" loading="lazy"'
        + (f' style="object-position:{e(ph["focus"])}"' if ph.get("focus") else "") + ">"
        + (f'<figcaption>{e(ph["caption"])}</figcaption>' if ph.get("caption") else "") + "</figure>"
        for ph in SITE.get("about_photos", []) if (ROOT / "static" / "photos" / ph["file"]).exists())
    cut = SITE.get("about_photos_after", len(about))
    about_html = ("".join(f"<p>{e(par)}</p>" for par in about[:cut])
                  + (f'<div class="about-photos">{figures}</div>' if figures else "")
                  + "".join(f"<p>{e(par)}</p>" for par in about[cut:]))
    body = f"""<div class="band"><div class="wrap">
{nav("")}
<div class="hero{' has-portrait' if PHOTO.exists() else ''}">
<div class="hero-text">
<p class="eyebrow">{e(SITE["ward"])} · {e(SITE["council"])}</p>
<h1>{e(SITE["hero_lead"])} <em>{e(SITE["suburbs"])}.</em></h1>
<p class="lede">{e(SITE["intro"])}</p>
<p class="stats mono"><span><b>{len(reports)}</b> monthly reports</span><span><b>{minutes}</b> minutes of video</span><span>since <b>{first:%B %Y}</b></span></p>
</div>
{side}
</div>
{term_timeline(reports)}
</div></div>
<main class="wrap">
{feature}
<section class="reports" id="reports">
<div class="section-head">
<h2>Reports and motions</h2>
<div class="search"><input id="q" type="search" placeholder="Search what was said, for example Stud Road" aria-label="Search the reports" autocomplete="off"><output id="q-count" class="mono" for="q"></output></div>
</div>
{groups}
<p class="empty" id="q-empty" hidden>No report mentions that yet.</p>
</section>
{media}
<section class="about" id="about">
<div><h2>About</h2></div>
<div class="about-text">{about_html}</div>
</section>
</main>
{SEARCH_JS}"""
    title = f'{SITE["site_title"]} {SITE["tagline"]}'
    desc = (f'{SITE["councillor"]}, {SITE["ward"]}, {SITE["council"]}: video, summaries and transcripts '
            f'of his monthly reports to Council.')
    return page(title, desc, body, "", preview, fragment=fragment)


def report_page(report, newer, older, preview):
    if report["youtube"]:
        video = (f'<iframe class="video" src="https://www.youtube-nocookie.com/embed/{e(report["youtube"])}" '
                 f'title="{e(report["headline"])}" loading="lazy" allowfullscreen '
                 'allow="accelerometer; encrypted-media; gyroscope; picture-in-picture"></iframe>')
    else:
        video = ('<div class="video video-pending"><span class="play"></span><b>Video not added yet</b>'
                 f'<span class="mono">{timecode(report["clip_start"])} to {timecode(report["clip_end"])} '
                 "of the meeting recording</span></div>")
    review = ""
    if preview and (report["check"] or report["status"] != "published"):
        items = "".join(f"<li>{e(c)}</li>" for c in report["check"]) or "<li>Nothing flagged.</li>"
        review = f'<section class="review"><h2>To check before publishing</h2><ul>{items}</ul></section>'
    strip = ""
    if report["meeting_length"]:
        total = report["meeting_length"]
        left = report["clip_start"] / total * 100
        width = (report["clip_end"] - report["clip_start"]) / total * 100
        strip = f"""<section class="strip">
<div class="strip-track"><i style="left:{left:.2f}%;width:{width:.2f}%"></i></div>
<div class="strip-ends mono"><span>0:00</span><span>{timecode(total)}</span></div>
<p>This report runs from {timecode(report['clip_start'])} to {timecode(report['clip_end'])} of a {hours_minutes(total)} meeting. <a href="{e(report['meeting_url'])}">Watch the full meeting on the council webcast</a>.</p>
</section>"""
    chips = "".join(f"<li>{e(t)}</li>" for t in report["topics"])
    role = {"Deputy Mayor": "Reported as Deputy Mayor", "Mayor": "Reported as Mayor"}.get(
        report["role"], "Reported as ward councillor")
    photo = ""
    if report["image"]:
        caption = f"<figcaption>{e(report['image_caption'])}</figcaption>" if report["image_caption"] else ""
        photo = (f'<figure class="photo"><img src="../photos/{e(report["image"])}" '
                 f'alt="{e(report["image_caption"] or "Photo from the month of this report")}" loading="lazy">{caption}</figure>')
    if report["gallery"]:
        extras = "".join(f'<img src="../photos/{e(g)}" alt="Photo from the month of this report" loading="lazy">'
                         for g in report["gallery"])
        photo += f'<div class="gallery">{extras}</div>'
    result = f"<div><dt>Result</dt><dd>{e(report['outcome'])}</dd></div>" if report["outcome"] else ""
    links = []
    if older:
        links.append(f'<a href="{older["slug"]}.html"><span class="mono">Earlier · {long_date(older["date"])}</span>'
                     f'<b>{e(older["headline"])}</b></a>')
    if newer:
        links.append(f'<a href="{newer["slug"]}.html"><span class="mono">Later · {long_date(newer["date"])}</span>'
                     f'<b>{e(newer["headline"])}</b></a>')
    body = f"""<div class="band"><div class="wrap">
{nav("../")}
<div class="report-head">
<a class="back" href="../index.html#reports">All reports</a>
<p class="eyebrow">{e(report['label'] or 'Council meeting')} · {long_date(report['date'])}</p>
<h1>{e(report['headline'])}</h1>
<p class="mono">{duration(report)} · {e(report['item'] or 'Item 5, Reports by Councillors')} · {e(report['outcome'] or role)}</p>
</div>
</div></div>
<div class="stage"><div class="wrap">{video}</div></div>
<main class="wrap report-body">
{review}
{strip}
<div class="columns">
<div class="text">
<section class="summary"><p class="eyebrow">{e(report['summary_label'] or 'Summary')}</p>
<div class="prose">{paragraphs(report['summary'])}</div>
</section>
{photo}
<section class="transcript"><p class="eyebrow">Transcript</p>
<p class="note">Edited from the meeting's auto-generated captions.</p>
<div class="prose">{paragraphs(report['transcript'])}</div>
</section>
</div>
<aside class="facts">
<div><p class="eyebrow">In this report</p><ul class="chips">{chips}</ul></div>
<dl>
<div><dt>Meeting</dt><dd>{long_date(report['date'])}</dd></div>
<div><dt>Length</dt><dd>{duration(report)}</dd></div>
{result}
<div><dt>Full meeting</dt><dd><a href="{e(report['meeting_url'])}">Council webcast</a>, from {timecode(report['clip_start'])}</dd></div>
</dl>
</aside>
</div>
<nav class="pager">{''.join(links)}</nav>
</main>"""
    title = f'{report["headline"]} | {SITE["site_title"]}'
    return page(title, report["summary"], body, "../", preview, path=f"reports/{report['slug']}.html")


def feed(reports):
    base = SITE["base_url"].rstrip("/")
    items = "".join(f"""<item><title>{e(r['headline'])}</title>
<link>{base}/reports/{r['slug']}.html</link><guid>{base}/reports/{r['slug']}.html</guid>
<pubDate>{dt.date.fromisoformat(r['date']):%a, %d %b %Y} 09:00:00 GMT</pubDate>
<description>{e(r['summary'])}</description></item>
""" for r in reports[:20])
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>{e(SITE['site_title'])} {e(SITE['tagline'])}</title>
<link>{base}/</link><description>{e(SITE['intro'])}</description>
{items}</channel></rss>
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--drafts", action="store_true", help="include drafts and their review notes")
    parser.add_argument("--out", default="dist")
    args = parser.parse_args(argv)

    reports = content.all_reports()
    problems = [f"{r['slug']}: marked published but has no YouTube ID"
                for r in reports if r["status"] == "published" and not r["youtube"]]
    problems += [f"{r['date']}: no headline" for r in reports if r["status"] == "published" and not r["headline"]]
    if problems:
        sys.exit("Cannot build:\n  " + "\n  ".join(problems))
    if not args.drafts:
        reports = [r for r in reports if r["status"] == "published"]

    out = ROOT / args.out
    shutil.rmtree(out, ignore_errors=True)
    (out / "reports").mkdir(parents=True)
    if PHOTO.exists():
        shutil.copy(PHOTO, out / "glen.jpg")
    if (ROOT / "static" / "photos").is_dir():
        shutil.copytree(ROOT / "static" / "photos", out / "photos")
    if not reports:
        body = (f'<div class="band"><div class="wrap">{nav("")}<div class="hero">'
                f'<p class="eyebrow">{e(SITE["ward"])} · {e(SITE["council"])}</p>'
                f'<h1>{e(SITE["hero_lead"])} <em>{e(SITE["suburbs"])}.</em></h1>'
                '<p class="lede">The first reports are being prepared.</p>'
                '</div></div></div>')
        (out / "index.html").write_text(page(SITE["site_title"], SITE["intro"], body, "", False), encoding="utf-8")
        print("Built an empty site: no published reports yet.")
        return
    (out / "index.html").write_text(index_page(reports, args.drafts), encoding="utf-8")
    if args.drafts:
        (out / "preview.html").write_text(index_page(reports, True, fragment=True), encoding="utf-8")
    (out / "search.json").write_text(
        json.dumps([{"d": r["slug"], "t": " ".join(r["transcript"].lower().split())} for r in reports]),
        encoding="utf-8")
    for i, report in enumerate(reports):
        newer = reports[i - 1] if i > 0 else None
        older = reports[i + 1] if i + 1 < len(reports) else None
        (out / "reports" / f"{report['slug']}.html").write_text(
            report_page(report, newer, older, args.drafts), encoding="utf-8")
    if SITE.get("base_url") and not args.drafts:
        (out / "feed.xml").write_text(feed(reports), encoding="utf-8")
    print(f"Built {len(reports)} report pages in {out.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
