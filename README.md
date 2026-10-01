# Glen Atwell: Councillor Reports

A small website that publishes Cr Glen Atwell's monthly Councillor Report from Knox City Council meetings: the video clip, a short summary and the transcript.

## How it works

1. Council posts each meeting at `webcast.knox.vic.gov.au`. The meeting page has an agenda index, and each agenda item carries its start time in seconds.
2. `pipeline/` reads that page, finds the item with "Atwell" in it, and uses the captions to tighten the start (after the Mayor's call) and the end (before the Mayor's thanks).
3. It cuts that clip straight from council's video file with ffmpeg. Only the part needed is downloaded, not the whole 2 GB meeting.
4. It writes a draft report file in `content/reports/` with a cleaned-up transcript.
5. A person checks the draft, uploads the clip to YouTube, pastes the YouTube ID into the file and marks it published.
6. `build.py` turns the published report files into the website in `dist/`.

Nothing is public until a report file says `status: published` and has a YouTube ID.

## The report files

One file per report, named by meeting date, for example `content/reports/2026-09-28.md`. The top block holds the details; the summary and transcript follow.

| Line | Meaning |
| --- | --- |
| `status` | `draft` or `published` |
| `youtube` | The video's ID, the part after `watch?v=` in its YouTube address |
| `clip_start`, `clip_end` | Where the clip starts and ends in the meeting recording, in seconds |
| `timing` | How the times were found: `auto` (captions), `mixed` or `index` (agenda index), `manual` (set by hand) |
| `topics` | Shown beside the report, separated by ` \| ` |
| `check` | Things to verify before publishing, separated by ` \| `. Clear this line when done |

## Setting up on GitHub (once)

1. Create a repository and push this folder to it.
2. Settings, Pages: set Source to "GitHub Actions".
3. Settings, Actions, General: tick "Allow GitHub Actions to create and approve pull requests".
4. Optional: add a repository secret `ANTHROPIC_API_KEY` if you want new drafts to arrive with a suggested headline, summary and topics. Without it, those are left for you to write.
5. Connect the domain (see below).

## The domain: glenatwell.au

`site.json` already has `base_url` set to `https://glenatwell.au`.

1. In the repository: Settings, Pages, Custom domain, enter `glenatwell.au` and save.
2. At the registrar for glenatwell.au, add four A records for the bare domain pointing to GitHub Pages: `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`. Add a CNAME record for `www` pointing to `<your-github-username>.github.io`. Check these against GitHub's current Pages documentation before saving, in case the addresses have changed.
3. Back in Settings, Pages, tick "Enforce HTTPS" once it becomes available (it can take up to a day).
4. At the registrar for glenatwell.com, set up domain forwarding (a permanent, 301 redirect) to `https://glenatwell.au`.

## Look and wording

Everything about the look is in `static/style.css`. The words on the home page are in `site.json`:

| Setting | What it changes |
| --- | --- |
| `hero_lead`, `suburbs` | The headline: "Reporting back to" + "Rowville and Scoresby." |
| `intro` | The paragraph under the headline |
| `about` | The About section |
| `accent` | The highlight colour: `orange` (the 2024 campaign orange), `wattle` or `violet` |
| `term_start`, `term_end` | The two ends of the term timeline |
| `contact_email` | Shown in the footer when filled in |

The photos at the top of the home page are listed under `hero_photos` in `site.json`, and the files live in `static/photos`. Each one is an upright 4:5 photo (960 by 1200 works well) with an optional `caption`. With more than one, they change every six seconds, and a visitor can click the dots or the photo to move on. The first in the list is the one people see first. If `hero_photos` is empty, the site falls back to the single portrait `static/glen.jpg`.

Other photos live in `static/photos/`:

- **About section:** listed under `about_photos` in `site.json` (file, description for screen readers, optional caption). `about_photos_after` sets which paragraph they follow.
- **On a report:** add `image: filename.jpg` to the report file. The photo becomes that report's tile on the home page and appears on its page. `image_caption` adds a caption, and `image_focus` (for example `50% 20%`) sets which part of a tall photo shows in the wide tile.
- **Facebook:** `facebook` in `site.json` is the address of the Facebook Page whose recent posts appear in the "On Facebook" section, and `facebook_note` is the line of text beside it. Remove `facebook` to drop the section. It only works for a Page, not a personal profile.
- **Link previews:** `share_image` in `site.json` is the picture shown when the site is shared on social media.

The "In the media" list is the `media` section of `site.json`: outlet, date, title and link for each item.

## Motions and other speeches

A speech that is not a monthly report gets its own file in `content/reports/` with a longer name, for example `2025-08-25-nom-184.md`. It works the same way as a report, with a few extra lines at the top:

| Line | Meaning |
| --- | --- |
| `kind` | `motion` (shown as a tag on the tile) |
| `label` | For example `Notice of Motion 184` |
| `item` | The agenda item, for example `Item 10.2, Notices of Motion` |
| `outcome` | For example `Carried unanimously` |
| `featured` | `yes` pins it to the top of the home page. Only the first featured piece is shown |
| `summary_label` | Heading for the first section, for example `Statement` |

These are added by hand: the daily check only looks for monthly reports. Set `clip_start` and `clip_end` in seconds, then run **Cut clips** with the file's name (without `.md`).

## Each month

The **Check for a new report** workflow runs every morning. When a new report appears it opens a pull request containing the draft, and attaches the clip to the workflow run. The pull request lists the steps: watch the clip, upload it to YouTube, paste the ID, fix the text, set `status: published`, merge.

## The back catalogue

All 22 reports since November 2024 are already drafted in `content/reports/`. To get their clips, run the **Cut clips** workflow with `all` and download the result. Each clip comes with a `.txt` file holding a YouTube title and description.

Five early meetings (November 2024 to March 2025) and April 2025 have no usable agenda index on council's site, so their clip times were set by hand from the captions and are marked `timing: manual`.

## Running it on your own computer

Needs Python 3.11 or later and ffmpeg. No other packages.

```
python -m pipeline.run check              # look for new meetings, draft any new report
python -m pipeline.run clip 2026-09-28    # cut one clip into clips/
python -m pipeline.run clip all           # cut every clip that has no YouTube ID
python -m pipeline.run inspect 26-0928    # show a meeting's agenda index
python build.py --drafts                  # preview site, drafts included
python build.py                           # public site
python -m unittest discover tests         # run the checks
```

## When the captions get a name wrong

Add a rule to `pipeline/corrections.json`. Future drafts will apply it. If the captions mis-hear "Atwell" in a new way, add the variant to `caption_aliases` in `site.json` so the clip start is still found.

## A note on the recordings

Council's website states that meeting recordings are council copyright and are not to be altered or republished without permission. Publishing the clips is the site owner's decision.
