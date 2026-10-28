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
import re
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


def motion_html(text):
    """The wording of a motion: plain paragraphs, then numbered points, with lettered sub-points indented under them."""
    out, depth = [], 0
    def close(to):
        nonlocal depth
        while depth > to:
            out.append("</li></ol>"); depth -= 1
    for block in text.split("\n"):
        line = block.rstrip()
        if not line.strip():
            continue
        top = re.match(r"(\d+)\.\s+(.*)", line)
        sub = re.match(r"\s+([a-z])\)\s+(.*)", line)
        if top:
            close(1)
            out.append("</li>" if depth == 1 else "<ol>"); depth = 1
            out.append(f"<li>{e(top.group(2))}")
        elif sub and depth:
            if depth == 1:
                out.append('<ol type="a">'); depth = 2
            else:
                out.append("</li>")
            out.append(f"<li>{e(sub.group(2))}")
        else:
            close(0)
            out.append(f"<p>{e(line.strip())}</p>")
    close(0)
    return "\n".join(out)


def person_ld():
    """The councillor, for search engines."""
    base = SITE.get("base_url", "").rstrip("/")
    d = {"@type": "Person", "name": SITE["councillor"].replace("Cr ", ""), "jobTitle": f"Councillor, {SITE['ward']}",
         "worksFor": {"@type": "GovernmentOrganization", "name": SITE["council"]}, "url": base + "/"}
    links = [SITE.get(k) for k in ("facebook", "youtube_channel") if SITE.get(k)]
    if links:
        d["sameAs"] = links
    return d


def page(title, description, body, root, preview, path="", fragment=False, ld=None):
    """One full HTML page. `root` is the relative path back to the site's top folder. `ld` is structured data for search engines."""
    accent = ACCENTS.get(SITE.get("accent"), ACCENTS["orange"])
    canonical = (f'<link rel="canonical" href="{e(SITE["base_url"].rstrip("/"))}/{path}">'
                 if SITE.get("base_url") and not preview else "")
    share = (f'<meta property="og:image" content="{e(SITE["base_url"].rstrip("/"))}/{e(SITE["share_image"])}">'
             '\n<meta name="twitter:card" content="summary">'
             if SITE.get("base_url") and SITE.get("share_image") else "")
    if (ROOT / "static" / "icons" / "favicon-64.png").exists():
        icons = (f'<link rel="icon" type="image/png" sizes="32x32" href="{root}icons/favicon-32.png">\n'
                 f'<link rel="icon" type="image/png" sizes="64x64" href="{root}icons/favicon-64.png">\n'
                 f'<link rel="icon" type="image/png" sizes="192x192" href="{root}icons/favicon-192.png">\n'
                 f'<link rel="apple-touch-icon" href="{root}icons/apple-touch-icon.png">')
    else:
        icon = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
                "%3Crect width='32' height='32' rx='7' fill='%23202648'/%3E"
                f"%3Ccircle cx='16' cy='16' r='7' fill='%23{accent[0][1:]}'/%3E%3C/svg%3E")
        icons = f'<link rel="icon" href="{icon}">'
    ld_html = ""
    if ld and not preview:
        ld_html = '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"
    head = f"""<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:type" content="website">
{share}
{canonical}
{icons}
{ld_html}
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
    inner = f"""{notice}
{body}
<footer><div class="wrap">
<a class="wordmark" href="{root}index.html">{e(SITE["site_title"])}</a>
<p>This is {e(SITE["councillor"])}'s own website. It is not a {e(SITE["council"])} website, and the views expressed are his own.</p>
<p>Video and captions come from {e(SITE["council"])}'s public meeting webcast. Transcripts are edited from the auto-generated captions and may contain errors. The video is the record.</p>
{contact}
</div></footer>"""
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
    issues = f'<li><a href="{root}index.html#issues">Issues</a></li>' if (ROOT / "issues.json").exists() else ""
    if (ROOT / "places.json").exists() and (ROOT / "static" / "ward.json").exists():
        issues += f'<li><a href="{root}ward.html">Ward map</a></li>'
    if SITE.get("facebook"):
        media += f'<li><a href="{root}index.html#facebook">Facebook</a></li>'
    mark = ""
    if SITE.get("mark_photo") and (ROOT / "static" / "photos" / SITE["mark_photo"]).exists():
        mark = f'<img src="{root}photos/{e(SITE["mark_photo"])}" alt="" width="96" height="96">'
    line = f'<small>{e(SITE["mark_line"])}</small>' if SITE.get("mark_line") else ""
    return f"""<nav class="nav">
<a class="wordmark{' has-mark' if mark else ''}" href="{root}index.html">{mark}<span>{e(SITE["site_title"])}{line}</span></a>
<ul><li><a href="{root}index.html#reports">Reports</a></li>{issues}{media}<li><a href="{root}index.html#about">About</a></li></ul>
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


def feature_block(item, preview, paras=2):
    """A pinned piece at the top of the home page."""
    opening = paragraphs("\n\n".join(item["summary"].split("\n\n")[:paras]))
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


SLIDES_JS = """<script>
(function () {
  var box = document.getElementById('slides'); if (!box) return;
  var imgs = [].slice.call(box.querySelectorAll('.frame img'));
  var dots = [].slice.call(box.querySelectorAll('.dots button'));
  var note = box.querySelector('.slide-note');
  var at = 0, timer = null, held = false;
  var still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function show(n) {
    at = (n + imgs.length) % imgs.length;
    imgs.forEach(function (img, i) { img.classList.toggle('on', i === at); });
    dots.forEach(function (d, i) { d.setAttribute('aria-current', String(i === at)); });
    note.textContent = imgs[at].dataset.caption || '';
  }
  function play() {
    clearInterval(timer);
    if (!still && !held && !document.hidden) timer = setInterval(function () { show(at + 1); }, 6000);
  }
  dots.forEach(function (d, i) { d.addEventListener('click', function () { show(i); play(); }); });
  var frame = box.querySelector('.frame'), x0 = null;
  frame.addEventListener('click', function () { show(at + 1); play(); });
  frame.addEventListener('touchstart', function (ev) { x0 = ev.touches[0].clientX; }, { passive: true });
  frame.addEventListener('touchend', function (ev) {
    if (x0 === null) return;
    var dx = ev.changedTouches[0].clientX - x0; x0 = null;
    if (Math.abs(dx) > 40) { ev.preventDefault(); show(at + (dx < 0 ? 1 : -1)); play(); }
  });
  ['mouseenter', 'focusin'].forEach(function (n) { box.addEventListener(n, function () { held = true; play(); }); });
  ['mouseleave', 'focusout'].forEach(function (n) { box.addEventListener(n, function () { held = false; play(); }); });
  document.addEventListener('visibilitychange', play);
  play();
})();
</script>"""


FACEBOOK_JS = """<script>
(function () {
  var box = document.getElementById('fb-box'); if (!box) return;
  function load() {
    var w = Math.max(180, Math.min(500, Math.floor(box.clientWidth))), h = 640;
    var f = document.createElement('iframe');
    f.src = 'https://www.facebook.com/plugins/page.php?href=' + encodeURIComponent(box.dataset.page) +
      '&tabs=timeline&width=' + w + '&height=' + h +
      '&small_header=true&adapt_container_width=true&hide_cover=false&show_facepile=false';
    f.width = w; f.height = h; f.title = box.dataset.title;
    f.setAttribute('scrolling', 'no'); f.setAttribute('frameborder', '0');
    f.setAttribute('allow', 'encrypted-media; picture-in-picture; web-share');
    box.appendChild(f);
  }
  if (!('IntersectionObserver' in window)) { load(); return; }
  var seen = new IntersectionObserver(function (entries) {
    if (entries.some(function (en) { return en.isIntersecting; })) { seen.disconnect(); load(); }
  }, { rootMargin: '400px' });
  seen.observe(box);
})();
</script>"""


def hero_slides(slides):
    """The photo frame at the top of the home page: one photo, or a few that change every six seconds."""
    imgs = "".join(
        ('<img class="on"' if i == 0 else "<img")
        + f' src="photos/{e(ph["file"])}" alt="{e(ph.get("alt") or "Glen Atwell")}" '
        f'width="960" height="1200" data-caption="{e(ph.get("caption", ""))}"'
        + (f' style="object-position:{e(ph["focus"])}"' if ph.get("focus") else "")
        + ("" if i == 0 else ' loading="lazy"') + ">"
        for i, ph in enumerate(slides))
    dots = ""
    if len(slides) > 1:
        dots = '<span class="dots">' + "".join(
            f'<button type="button" aria-label="Photo {i + 1} of {len(slides)}" aria-current="{str(i == 0).lower()}"></button>'
            for i in range(len(slides))) + "</span>"
    return (f'<figure class="portrait slides" id="slides"><div class="frame">{imgs}</div>'
            f'<figcaption><span class="slide-note">{e(slides[0].get("caption", ""))}</span>{dots}</figcaption></figure>')


def load_issues(items):
    """Sort what was said into issues, using the rules in issues.json.

    A report joins an issue when a paragraph of its transcript matches one of the issue's `match` patterns
    (and none of its `skip` patterns). A motion joins the issues named on its `issues` line, and is pinned first.
    """
    path = ROOT / "issues.json"
    if not path.exists():
        return []
    out = []
    for rule in json.loads(path.read_text(encoding="utf-8")):
        want = re.compile("|".join(rule["match"]), re.I)
        skip = re.compile("|".join(rule["skip"]), re.I) if rule.get("skip") else None
        pinned, entries = [], []
        for r in items:
            if rule["slug"] in r["issues"]:
                pinned.append(r)
            elif r["kind"] == "report":
                paras = [para.strip() for para in r["transcript"].split("\n\n")
                         if want.search(para) and not (skip and skip.search(para))]
                if paras:
                    entries.append((r, paras))
        if pinned or entries:
            out.append({"slug": rule["slug"], "title": rule["title"], "intro": rule.get("intro", ""),
                        "pinned": pinned, "entries": entries, "count": len(pinned) + len(entries)})
    return out


def short_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d:%b %Y}"


def times(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def issue_page(issue, issues, preview):
    def flag(r):
        return '<span class="draft-flag">Draft</span> ' if preview and r["status"] != "published" else ""
    blocks, index = [], []
    for r in issue["pinned"]:
        outcome = f' · {e(r["outcome"])}' if r["outcome"] else ""
        index.append(f'<li><a href="#{r["slug"]}"><span class="mono">{short_date(r["date"])}</span>{e(r["label"] or "Speech")}: {e(r["headline"])}</a></li>')
        blocks.append(f"""<article class="issue-entry pinned" id="{r["slug"]}">
<p class="mono">{flag(r)}{e(r["label"] or "Speech")} · {long_date(r["date"])}{outcome}</p>
<h2><a href="../reports/{r["slug"]}.html">{e(r["headline"])}</a></h2>
<div class="prose">{paragraphs(r["summary"].split(chr(10) + chr(10))[0])}</div>
<p><a class="button" href="../reports/{r["slug"]}.html">Watch the speech · {timecode(seconds_of(r))}</a></p>
</article>""")
    for r, paras in issue["entries"]:
        index.append(f'<li><a href="#{r["slug"]}"><span class="mono">{short_date(r["date"])}</span>{e(r["headline"])}</a></li>')
        blocks.append(f"""<article class="issue-entry" id="{r["slug"]}">
<p class="mono">{flag(r)}{long_date(r["date"])}</p>
<div class="prose">{paragraphs((chr(10) + chr(10)).join(paras))}</div>
<p class="issue-more"><a href="../reports/{r["slug"]}.html">Watch this report · {timecode(seconds_of(r))}</a> <a class="to-top" href="#top">Back to top</a></p>
</article>""")
    contents = f'<nav class="issue-index" aria-label="On this page"><p class="eyebrow">On this page</p><ol>{"".join(index)}</ol></nav>'
    dates = [r["date"] for r in issue["pinned"]] + [r["date"] for r, _ in issue["entries"]]
    parts = []
    if issue["entries"]:
        parts.append(times(len(issue["entries"]), "report"))
    if issue["pinned"]:
        parts.append(times(len(issue["pinned"]), "motion"))
    others = "".join(f'<li><a href="{i["slug"]}.html">{e(i["title"])}</a></li>' for i in issues if i is not issue)
    body = f"""<div class="band"><div class="wrap">
{nav("../")}
<div class="report-head">
<a class="back" href="../index.html#issues">All issues</a>
<p class="eyebrow">Issue</p>
<h1>{e(issue["title"])}</h1>
<p class="mono">Raised in {" and ".join(parts)} · most recently {long_date(max(dates))}</p>
</div>
</div></div>
<main class="wrap issue-body" id="top">
<p class="issue-intro">{e(issue["intro"])} What follows is what I’ve said in the Council chamber.</p>
<div class="issue-columns">
<div class="issue-list">
{chr(10).join(blocks)}
</div>
{contents}
</div>
<section class="issue-others"><p class="eyebrow">Other issues</p><ul class="chips">{others}</ul></section>
</main>"""
    title = f'{issue["title"]} in {SITE["suburbs"]} | {SITE["councillor"]}'
    desc = f'{SITE["councillor"]} on {issue["title"].lower()}: what he has said in the Council chamber, with video.'
    return page(title, desc, body, "../", preview, path=f"issues/{issue['slug']}.html")


WARD_JS = """<script src="leaflet/leaflet.js"></script>
<script>
(function () {
  var data = JSON.parse(document.getElementById('ward-data').textContent);
  var map = L.map('map', { scrollWheelZoom: false, tap: false });
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, className: 'muted-tiles',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(map);
  var ward = L.geoJSON(data.ward, { style: { color: '#202648', weight: 2.5, dashArray: '6 5', fillColor: '#202648', fillOpacity: 0.04 } }).addTo(map);
  map.fitBounds(ward.getBounds(), { padding: [12, 12] });
  var layer = L.layerGroup().addTo(map), active = 'all';
  function render() {
    layer.clearLayers();
    data.places.forEach(function (p) {
      if (active !== 'all' && p.issues.indexOf(active) < 0) return;
      var n = p.mentions.length, spoke = n > 0;
      var m = L.circleMarker([p.lat, p.lng], { radius: spoke ? 7 + Math.min(n, 8) * 1.2 : 6,
        color: '#fff', weight: 2, fillColor: spoke ? '#ea8d30' : '#8a8fa8', fillOpacity: 0.95 });
      var html = '<b>' + p.name + '</b>' + (p.blurb ? '<p>' + p.blurb + '</p>' : '');
      if (spoke) {
        var last = p.mentions[0];
        html += '<p class="pop-quote">' + last.text + '</p>' +
          '<p class="pop-meta">' + last.date + ' · <a href="reports/' + last.slug + '.html">Watch this report</a>' +
          (n > 1 ? ' · <a href="#' + p.id + '">' + n + ' mentions</a>' : '') + '</p>';
      } else { html += '<p class="pop-meta">Not raised in a report yet.</p>'; }
      m.bindPopup(html, { maxWidth: 300 }); layer.addLayer(m);
    });
  }
  [].slice.call(document.querySelectorAll('#map-filters button')).forEach(function (b) {
    b.addEventListener('click', function () {
      active = b.dataset.issue;
      [].slice.call(document.querySelectorAll('#map-filters button')).forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      render();
    });
  });
  [].slice.call(document.querySelectorAll('.place-list a.locate')).forEach(function (a) {
    a.addEventListener('click', function (ev) {
      ev.preventDefault(); var p = data.places.filter(function (q) { return q.id === a.dataset.id; })[0];
      map.setView([p.lat, p.lng], 15); document.getElementById('map').scrollIntoView({ behavior: 'smooth', block: 'center' });
      layer.eachLayer(function (m) { if (m.getLatLng().lat === p.lat && m.getLatLng().lng === p.lng) m.openPopup(); });
    });
  });
  render();
})();
</script>"""


def ward_page(items, issues, preview):
    """A map of the ward with a pin for each place raised in the chamber."""
    places = json.loads((ROOT / "places.json").read_text(encoding="utf-8"))
    ward = json.loads((ROOT / "static" / "ward.json").read_text(encoding="utf-8"))
    titles = {i["slug"]: i["title"] for i in issues}
    for p in places:
        want = re.compile("|".join(p["match"]), re.I)
        p["mentions"] = []
        for r in items:
            for para in r["transcript"].split("\n\n"):
                if want.search(para):
                    text = para.strip()
                    if len(text) > 320:
                        cut = text[:300]; text = cut[:cut.rfind(" ")] + "…"
                    p["mentions"].append({"slug": r["slug"], "date": long_date(r["date"]), "headline": r["headline"], "text": text})
                    break
    spoken = [p for p in places if p["mentions"]]
    used = [slug for slug in titles if any(slug in p["issues"] for p in spoken)]
    filters = '<button type="button" data-issue="all" aria-pressed="true">Everything</button>' + "".join(
        f'<button type="button" data-issue="{slug}" aria-pressed="false">{e(titles[slug])}</button>' for slug in used)
    rows = []
    for p in sorted(places, key=lambda p: (-len(p["mentions"]), p["name"])):
        n = len(p["mentions"])
        meta = (times(n, "mention") + " · last " + p["mentions"][0]["date"]) if n else "Not raised in a report yet"
        tags = "".join(f'<a href="issues/{slug}.html">{e(titles[slug])}</a>' for slug in p["issues"] if slug in titles)
        links = "".join(f'<li><a href="reports/{m["slug"]}.html"><span class="mono">{m["date"]}</span>{e(m["headline"])}</a></li>' for m in p["mentions"])
        note = ' <span class="mono">outside the ward</span>' if p.get("outside") else (' <span class="mono">approximate</span>' if p.get("approx") else "")
        rows.append(f"""<article class="place{' spoken' if n else ''}" id="{p['id']}">
<h3><a class="locate" href="#map" data-id="{p['id']}">{e(p['name'])}</a>{note}</h3>
<p class="mono">{meta}</p>
<p>{e(p.get('blurb', ''))}</p>
{f'<p class="place-tags">{tags}</p>' if tags else ''}
{f'<ul class="place-links">{links}</ul>' if links else ''}
</article>""")
    data = json.dumps({"ward": ward, "places": [{k: p[k] for k in ("id", "name", "lat", "lng", "issues", "mentions", "blurb")} for p in places]})
    safe = data.replace("</", "<\\/")
    about = SITE.get("ward_about", [])
    about_html = "".join(f"<p>{e(par)}</p>" for par in about)
    history = SITE.get("ward_history", [])
    history_html = ""
    if history:
        history_html = (f'<section class="ward-history prose"><h2>{e(SITE.get("ward_history_title", "Where the name comes from"))}</h2>'
                        + "".join(f"<p>{e(par)}</p>" for par in history))
        if SITE.get("ward_credit"):
            history_html += f'<p class="credit">{e(SITE["ward_credit"])}</p>'
        history_html += "</section>"
    body = f"""<div class="band"><div class="wrap">
{nav("")}
<div class="report-head">
<p class="eyebrow">Ward map · {e(SITE["council"])}</p>
<h1>{e(SITE.get("ward_title", "The ward"))}</h1>
<p class="mono">{e(SITE["suburbs"])} · {len(spoken)} places raised in the chamber</p>
</div>
</div></div>
<main class="wrap ward-body">
<div class="ward-intro prose">{about_html}</div>
<section class="ward-map">
<div class="filters" id="map-filters">{filters}</div>
<div id="map" aria-label="Map of {e(SITE["ward"])}"></div>
</section>
<section class="place-list">
<h2>Place by place</h2>
<div class="places">
{chr(10).join(rows)}
</div>
</section>
{history_html}
</main>
<script type="application/json" id="ward-data">{safe}</script>
{WARD_JS}"""
    title = f'{SITE.get("ward_title", "The ward")} map, {SITE["suburbs"]} | {SITE["councillor"]}'
    desc = f'A map of {SITE["ward"]} ({SITE["suburbs"]}) with every place {SITE["councillor"]} has raised in the Knox City Council chamber.'
    html = page(title, desc, body, "", preview, path="ward.html")
    return html.replace("<style>", '<link rel="stylesheet" href="leaflet/leaflet.css">\n<style>', 1)


def index_page(items, preview, fragment=False, issues=()):
    reports = [r for r in items if r["kind"] == "report"] or items
    featured = [r for r in items if r["featured"]][:2]      # one is shown wide, two sit side by side
    latest = reports[0]
    first = dt.date.fromisoformat(items[-1]["date"])
    minutes = round(sum(seconds_of(r) for r in items) / 60)
    years = sorted({r["date"][:4] for r in items}, reverse=True)
    groups = "\n".join(
        f'<section class="year"><h3>{year}</h3>\n<div class="grid">\n'
        + "\n".join(card(r, preview) for r in items if r["date"].startswith(year))
        + "\n</div></section>" for year in years)
    slides = [ph for ph in SITE.get("hero_photos", []) if (ROOT / "static" / "photos" / ph["file"]).exists()]
    has_portrait = bool(slides) or PHOTO.exists()
    face = ""
    latest_card = f"""<a class="latest" href="reports/{latest['slug']}.html">
{poster(latest, preview)}
<span class="latest-text"><span class="eyebrow">Latest report · {long_date(latest['date'])}</span>
<h2>{e(latest['headline'])}</h2></span>
</a>"""
    if SITE.get("hero_style") == "latest":       # the newest report takes the right-hand side; one photo sits with the headline
        side, has_portrait = latest_card, False
        face = bool(SITE.get("mark_photo"))       # the portrait lives in the site mark, so the headline needs no eyebrow
        slides = []
    elif slides:
        side = hero_slides(slides)
    elif PHOTO.exists():
        side = '<figure class="portrait"><img src="glen.jpg" alt="Glen Atwell" width="800" height="1201"></figure>'
    else:
        side = latest_card
    media = ""
    if SITE.get("media"):
        rows = "".join(
            f'<li><span class="mono">{e(m["outlet"])} · {long_date(m["date"])}</span>'
            f'<a href="{e(m["url"])}">{e(m["title"])}</a></li>' for m in SITE["media"])
        yt = (f'<a class="button" href="{e(SITE["youtube_channel"])}" rel="noopener">Watch on YouTube</a>'
              if SITE.get("youtube_channel") else "")
        media = f'<section class="media" id="media"><div class="social-head"><h2>In the media</h2>{yt}</div><ul>{rows}</ul></section>'
    social = ""
    if SITE.get("facebook"):                 # Facebook's own box of recent posts, loaded only when scrolled to
        fb = e(SITE["facebook"])
        note = f'\n<p class="social-note">{e(SITE["facebook_note"])}</p>' if SITE.get("facebook_note") else ""
        social = f"""<section class="social" id="facebook">
<div class="social-head"><h2>On Facebook</h2><a class="button" href="{fb}" rel="noopener">Follow on Facebook</a></div>
<div class="fb-box" id="fb-box" data-page="{fb}" data-title="{e(SITE["councillor"])} on Facebook"><a href="{fb}" rel="noopener">See the latest posts on Facebook</a></div>{note}
</section>"""
    # News coverage and Facebook sit side by side on a wide screen when both are present.
    duo = f'<div class="duo">\n{media}\n{social}\n</div>' if media and social else media + social
    about = SITE["about"] if isinstance(SITE["about"], list) else [SITE["about"]]
    if len(featured) == 2:
        feature = '<div class="features">\n' + "\n".join(feature_block(r, preview, paras=1) for r in featured) + "\n</div>"
    else:
        feature = feature_block(featured[0], preview) if featured else ""
    issue_row = ""
    if issues:
        links = "".join(f'<li><a href="issues/{i["slug"]}.html"><b>{e(i["title"])}</b>'
                        f'<span class="mono">{times(i["count"], "time")}</span></a></li>' for i in issues)
        issue_row = (f'<section class="issues" id="issues"><div class="section-head"><h2>Issues</h2></div>'
                     f'<ul class="issue-grid">{links}</ul></section>')
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
<div class="hero{' has-portrait' if has_portrait else ''}">
<div class="hero-text">
{'' if face else f'<p class="eyebrow">{e(SITE["ward"])} · {e(SITE["council"])}</p>'}
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
{issue_row}
<section class="reports" id="reports">
<div class="section-head">
<h2>Reports and motions</h2>
<div class="search"><input id="q" type="search" placeholder="Search what was said, for example Stud Road" aria-label="Search the reports" autocomplete="off"><output id="q-count" class="mono" for="q"></output></div>
</div>
{groups}
<p class="empty" id="q-empty" hidden>No report mentions that yet.</p>
</section>
{duo}
<section class="about" id="about">
<div><h2>About</h2></div>
<div class="about-text">{about_html}</div>
</section>
</main>
{SEARCH_JS}
{SLIDES_JS if len(slides) > 1 else ""}
{FACEBOOK_JS if social else ""}"""
    title = SITE.get("page_title") or f'{SITE["site_title"]} {SITE["tagline"]}'
    desc = (f'{SITE["councillor"]}, {SITE["ward"]} ({SITE["suburbs"]}), {SITE["council"]}: video, summaries and transcripts '
            f'of his monthly reports to Council.')
    ld = {"@context": "https://schema.org", "@graph": [person_ld(), {"@type": "WebSite", "name": title, "url": SITE.get("base_url", "").rstrip("/") + "/"}]}
    return page(title, desc, body, "", preview, fragment=fragment, ld=ld)


def report_page(report, newer, older, preview, issues=()):
    mine = [i for i in issues if report in i["pinned"] or any(r is report for r, _ in i["entries"])]
    issue_links = ""
    if mine:
        issue_links = ('<div><p class="eyebrow">Issues</p><ul class="chips">'
                       + "".join(f'<li><a href="../issues/{i["slug"]}.html">{e(i["title"])}</a></li>' for i in mine) + "</ul></div>")
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
    motion = (f'<section class="motion"><p class="eyebrow">The motion</p>\n<div class="prose">{motion_html(report["motion"])}</div>\n</section>'
              if report.get("motion") else "")
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
{motion}
<section class="transcript"><p class="eyebrow">Transcript</p>
<p class="note">Edited from the meeting's auto-generated captions.</p>
<div class="prose">{paragraphs(report['transcript'])}</div>
</section>
</div>
<aside class="facts">
<div><p class="eyebrow">In this report</p><ul class="chips">{chips}</ul></div>
{issue_links}
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
    title = f'{report["headline"]} | {SITE["councillor"]}, {SITE["suburbs"]}'
    base = SITE.get("base_url", "").rstrip("/")
    ld = {"@context": "https://schema.org", "@type": "Article", "headline": report["headline"], "description": report["summary"],
          "datePublished": report["date"], "author": person_ld(), "url": f"{base}/reports/{report['slug']}.html",
          "about": {"@type": "Place", "name": f"{SITE['ward']}, {SITE['council']}"}}
    if report.get("image"):
        ld["image"] = f"{base}/photos/{report['image']}"
    if report.get("youtube"):
        ld["video"] = {"@type": "VideoObject", "name": report.get("video_title") or report["headline"], "description": report["summary"],
                       "uploadDate": report["date"], "thumbnailUrl": f"https://i.ytimg.com/vi/{report['youtube']}/hqdefault.jpg",
                       "embedUrl": f"https://www.youtube.com/embed/{report['youtube']}"}
    return page(title, report["summary"], body, "../", preview, path=f"reports/{report['slug']}.html", ld=ld)


def sitemap(reports, issues, has_ward):
    """Every public page, with the date it last changed, for search engines."""
    base = SITE["base_url"].rstrip("/")
    latest = max((r["date"] for r in reports), default=dt.date.today().isoformat())
    urls = [(f"{base}/", latest)]
    if has_ward:
        urls.append((f"{base}/ward.html", latest))
    for issue in issues:
        dates = [r["date"] for r in issue["pinned"]] + [r["date"] for r, _ in issue["entries"]] or [latest]
        urls.append((f"{base}/issues/{issue['slug']}.html", max(dates)))
    urls += [(f"{base}/reports/{r['slug']}.html", r["date"]) for r in reports]
    body = "".join(f"<url><loc>{e(u)}</loc><lastmod>{d}</lastmod></url>\n" for u, d in urls)
    return f'<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}</urlset>\n'


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
    if (ROOT / "static" / "icons").is_dir():
        shutil.copytree(ROOT / "static" / "icons", out / "icons")
    if (ROOT / "static" / "leaflet").is_dir():
        shutil.copytree(ROOT / "static" / "leaflet", out / "leaflet")
    if (ROOT / "static" / "ward.json").exists():
        shutil.copy(ROOT / "static" / "ward.json", out / "ward.json")
    if not reports:
        body = (f'<div class="band"><div class="wrap">{nav("")}<div class="hero">'
                f'<p class="eyebrow">{e(SITE["ward"])} · {e(SITE["council"])}</p>'
                f'<h1>{e(SITE["hero_lead"])} <em>{e(SITE["suburbs"])}.</em></h1>'
                '<p class="lede">The first reports are being prepared.</p>'
                '</div></div></div>')
        (out / "index.html").write_text(page(SITE["site_title"], SITE["intro"], body, "", False), encoding="utf-8")
        print("Built an empty site: no published reports yet.")
        return
    issues = load_issues(reports)
    (out / "index.html").write_text(index_page(reports, args.drafts, issues=issues), encoding="utf-8")
    if args.drafts:
        (out / "preview.html").write_text(index_page(reports, True, fragment=True, issues=issues), encoding="utf-8")
    if (ROOT / "places.json").exists() and (ROOT / "static" / "ward.json").exists():
        (out / "ward.html").write_text(ward_page(reports, issues, args.drafts), encoding="utf-8")
    if issues:
        (out / "issues").mkdir()
        for issue in issues:
            (out / "issues" / f"{issue['slug']}.html").write_text(issue_page(issue, issues, args.drafts), encoding="utf-8")
    (out / "search.json").write_text(
        json.dumps([{"d": r["slug"], "t": " ".join(r["transcript"].lower().split())} for r in reports]),
        encoding="utf-8")
    for i, report in enumerate(reports):
        newer = reports[i - 1] if i > 0 else None
        older = reports[i + 1] if i + 1 < len(reports) else None
        (out / "reports" / f"{report['slug']}.html").write_text(
            report_page(report, newer, older, args.drafts, issues), encoding="utf-8")
    if SITE.get("base_url") and not args.drafts:
        (out / "feed.xml").write_text(feed(reports), encoding="utf-8")
        (out / "sitemap.xml").write_text(sitemap(reports, issues, (out / "ward.html").exists()), encoding="utf-8")
        (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE['base_url'].rstrip('/')}/sitemap.xml\n", encoding="utf-8")
    print(f"Built {len(reports)} report pages in {out.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
