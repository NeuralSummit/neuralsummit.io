#!/usr/bin/env python3
"""Build the static transcripts site from discussions/ (each discussion's inputs, brought in from ~/debates by sync.py), shown as ~/discussions (debates are one kind; consensus runs
are the other): a CLI-style directory tree of them, and one page per
transcript. Reads each debate's video/ folder (script.json for the title, context.json for the sides and the
fact-checks, transcript.md for the text) and writes plain HTML to public/. No dependencies: the transcripts come
from debate.py in a known, small subset of Markdown, so it's converted here."""
import base64
import hashlib
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).parent
DEBATES = HERE / "discussions"  # one folder per discussion: video/{transcript.md,context.json,script.json}, site.json, site-voice/
HOME = "~/discussions"  # what the site calls that folder
CHANNEL = ("Neural", "Summit")  # the channel's name: first word in Opus orange, second in Argon blue
KIND = {"opposing": "Debate", "consensus": "Consensus"}  # context.json's mode, as the site names it
KINDS = [("consensus", "Consensus"), ("debate", "Debate")]  # a folder for each, in tree's (alphabetical) order
OUT = HERE / "public"
ASSETS = HERE / "assets"
# the channel's video skill, for its speech prep and ffmpeg; only on the channel's machine. Without it (GitHub's runner)
# the build uses what the last local build saved: each card's audio key (site-voice/keys.json) and length (durations.json)
VIDEO_SKILL = Path(os.environ.get("VIDEO_SKILL") or Path.home() / ".claude/skills/debate-video")
FFMPEG = VIDEO_SKILL / "remotion/node_modules/@remotion/compositor-linux-x64-gnu"

C = {"claude": "#f0883e", "gemini": "#4ea1ff", "evidence": "#f2c14e", "muted": "#8d96a3", "moderator": "#b48ead"}
WHO = {"🟠": "claude", "🔵": "gemini", "🔎": "evidence", "📋": "summary", "🟣": "moderator"}
VERDICT = {"TRUE": "true", "MOSTLY TRUE": "true", "PARTLY TRUE": "partly", "MISLEADING": "partly", "FALSE": "false"}
DOTS = {"🟠": "claude", "🔵": "gemini", "🟣": "moderator", "📋": "summary"}  # emoji fonts vary; dots match the page
LABEL = re.compile(r"^(Persona|Voice): ")  # profile lines debate.py writes one per line
META = re.compile(r"^(CHECK|STATUS|VERDICT): ")  # the sides' machine-read lines: shown, but as metadata
ENTRY = re.compile(r"^## (?P<kind>.+?) · (?P<emoji>\S+) (?P<who>.+?) · (?P<time>\d\d:\d\d)$")


# ── the logo: the channel's yin-yang (LogoArt.tsx's crt-e), small enough for a header and a favicon ──────────

def logo_svg(size, uid, scan=True):
    """The two halves' arcs and dots, tilted as in the video, with the CRT colour split. At header size the
    phosphor grille turns to mush, so it keeps only the scanlines; the favicon drops those too. Each half is its own
    group (data-half), placed by a transform, so site.js can replay the video's sting on it: the halves spiral in
    and lock."""
    r, cx = 400, 500
    sp = math.radians(20)
    sx, sy = cx + r * math.sin(sp), cx - r * math.cos(sp)
    arcs = {
        "claude": [f"M{sx:.1f},{sy:.1f} A{r},{r} 0 0 0 {1000 - sx:.1f},{1000 - sy:.1f}", "M500,500 A200,200 0 0 0 500,100"],
        "gemini": [f"M{sx:.1f},{sy:.1f} A{r},{r} 0 0 1 {1000 - sx:.1f},{1000 - sy:.1f}", "M500,900 A200,200 0 0 1 500,500"],
    }
    dots = {"claude": ("gemini", 300), "gemini": ("claude", 700)}  # each head holds a dot of the other side

    def half(who, ink=None):
        dot, y = dots[who]
        return (f'<g data-half="{who}" transform="rotate(-35 500 500)">'
                + "".join(f'<path d="{d}" stroke="{ink or C[who]}" stroke-width="56" fill="none"/>' for d in arcs[who])
                + f'<circle cx="500" cy="{y}" r="54" stroke="{ink or C[dot]}" stroke-width="30" fill="none"/>'
                f'<circle cx="500" cy="{y}" r="20" fill="{ink or C[dot]}"/></g>')

    chroma = (f'<filter id="{uid}-c" x="-50%" y="-50%" width="200%" height="200%">'
              '<feColorMatrix in="SourceGraphic" values="1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0" result="r"/>'
              '<feOffset in="r" dx="14" result="r2" data-shift="1"/>'
              '<feColorMatrix in="SourceGraphic" values="0 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 1 0" result="gb"/>'
              '<feOffset in="gb" dx="-14" result="gb2" data-shift="-1"/><feBlend in="r2" in2="gb2" mode="screen"/></filter>')
    lines = (f'<pattern id="{uid}-s" width="1000" height="44" patternUnits="userSpaceOnUse">'
             f'<rect y="27" width="1000" height="17" fill="#000"/></pattern>'
             f'<mask id="{uid}-m" maskUnits="userSpaceOnUse" x="-1000" y="-1000" width="3000" height="3000">'
             f'{half("claude", "#fff")}{half("gemini", "#fff")}</mask>')
    over = (f'<rect x="-1000" y="-1000" width="3000" height="3000" fill="url(#{uid}-s)" mask="url(#{uid}-m)" opacity="0.55"/>'
            if scan else "")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 1000 1000" '
            f'aria-hidden="true" class="logo" style="overflow: visible">'
            f'<defs>{chroma}{lines if scan else ""}</defs>'
            f'<g class="lock"><g filter="url(#{uid}-c)">{half("claude")}{half("gemini")}</g>{over}</g></svg>')



# ── the links: YouTube and the site's repo, as the logo's colours split by the name cursor's S ──────────────────
# The marks are simple-icons' (CC0); each is filled Opus orange and Argon blue either side of the cursor's yin-yang S
# (style.css .cursor.duo), with the logo's colour split and the name's scanlines, both drawn in the mark's own units.
LINKS = [
    ("yt", "https://www.youtube.com/@NeuralSummit", "Neural Summit on YouTube",
     "M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 "
     "6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505"
     "a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"),
    ("gh", "https://github.com/NeuralSummit/neuralsummit.io", "This site's source on GitHub",
     "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338"
     ".724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 "
     "1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 "
     "1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 "
     "2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92"
     ".42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627"
     "-5.373-12-12-12"),
]
S_SPLIT = "M0,0 L12,0 C20,3 20,9 12,12 C4,15 4,21 12,24 L0,24 Z"  # the cursor's S, from its 60x72 box into the mark's 24


def link_svg(path, size, uid):
    px = 24 / size  # one screen pixel in the mark's units: the scanlines are 2 lit, 1 dimmed, as the name's
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true" style="overflow: visible"><defs>'
            f'<filter id="{uid}-c" x="-30%" y="-30%" width="160%" height="160%">'
            '<feColorMatrix in="SourceGraphic" values="1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0" result="r"/>'
            '<feOffset in="r" dx="0.34" result="r2" data-shift="1"/>'
            '<feColorMatrix in="SourceGraphic" values="0 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 1 0" result="gb"/>'
            '<feOffset in="gb" dx="-0.34" result="gb2" data-shift="-1"/><feBlend in="r2" in2="gb2" mode="screen"/></filter>'
            f'<pattern id="{uid}-p" width="24" height="{3 * px:.4f}" patternUnits="userSpaceOnUse"><rect width="24" '
            f'height="{2 * px:.4f}" fill="#fff"/><rect y="{2 * px:.4f}" width="24" height="{px:.4f}" fill="#737373"/></pattern>'
            f'<mask id="{uid}-s" maskUnits="userSpaceOnUse" x="-4" y="-4" width="32" height="32">'
            f'<rect x="-4" y="-4" width="32" height="32" fill="url(#{uid}-p)"/></mask>'
            f'<mask id="{uid}-m" maskUnits="userSpaceOnUse" x="-1" y="-1" width="26" height="26"><path d="{path}" fill="#fff"/></mask>'
            f'</defs><g mask="url(#{uid}-s)"><g filter="url(#{uid}-c)"><g mask="url(#{uid}-m)">'
            f'<rect width="24" height="24" fill="{C["gemini"]}"/><path d="{S_SPLIT}" fill="{C["claude"]}"/></g></g></g></svg>')


def links_html(where, size):
    return "".join(f'<a class="ln {k}" href="{url}" target="_blank" rel="noopener" aria-label="{label}" title="{label}">'
                   f'{link_svg(path, size, f"{where}-{k}")}</a>' for k, url, label, path in LINKS)

# ── Markdown (the subset debate.py writes) ─────────────────────────────────────────────────────────────────────

def inline(text, refs):
    t = html.escape(text, quote=False)
    t = re.sub(r"&lt;(https?://[^\s&]+)&gt;", r'<a href="\1">\1</a>', t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub("|".join(DOTS), lambda m: f'<span class="dot {DOTS[m[0]]}"></span>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t)
    t = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", t)
    # a fact-check reference links to its card in the fact-checks tab (site.js shows it as a preview instead): "🔎 #11",
    # "the 🔎 note on #5", "🔎 #3, #4 and #6". The 🔎 is what marks a reference, so rankings ("AFI #13") stay plain
    def ref(num, words="", first=True):
        cls = "ref" if first else "ref more"  # the 🔎 is drawn before the first only
        text = f"{words}#{num}"
        return (f'<a class="{cls}" href="#fc-{num}" data-check>{text}</a>' if num in refs
                else f'<span class="{cls}">{text}</span>')

    def refs_in(m):
        words, rest = m[1].strip(), m[3]
        out = ref(m[2], f"{words} " if words else "")
        for sep, num in re.findall(r"(,\s*|\s+and\s+)#(\d+)", rest):
            out += sep + ref(num, first=False)
        return out
    t = re.sub(r"🔎((?:\s+[a-z]+){0,3})\s*#(\d+)((?:(?:,\s*|\s+and\s+)#\d+)*)", refs_in, t)
    return t


def blocks(lines, refs):
    out, para, items, quote = [], [], [], []

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para), refs)}</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i, refs)}</li>" for i in items) + "</ul>")
            items.clear()
        if quote:
            q = " ".join(quote)
            # a source quote that's raw page data ('"score":"91",…') shows as code, not prose
            out.append(f"<blockquote><code>{html.escape(q)}</code></blockquote>" if re.match(r'^"\w+":', q)
                       else f"<blockquote>{inline(q, refs)}</blockquote>")
            quote.clear()

    for ln in lines:
        s = ln.rstrip()
        if not s.strip():
            flush()
        elif s.startswith("## ") or s.startswith("# "):
            flush()
            head = s.lstrip("#").strip()
            # a section label ("Rebut") looks like a heading; a long one is content (a side's position)
            out.append(f"<h3>{inline(head, refs)}</h3>" if len(head) < 40 else f'<h4>{inline(head, refs)}</h4>')
        elif META.match(s.strip()):
            flush()
            out.append(f'<div class="meta">{inline(s.strip(), refs)}</div>')
        elif LABEL.match(s.strip()):
            flush()
            k, v = s.strip().split(": ", 1)
            out.append(f'<p class="label"><span>{k}</span> {inline(v, refs)}</p>')
        elif re.match(r"^[-*] ", s):
            if para or quote:
                flush()
            items.append(s[2:])
        elif s.startswith("> ") or s == ">":
            if para or items:
                flush()
            quote.append(s[2:])
        elif s.startswith("<details") or s.startswith("</details") or s.startswith("<summary"):
            flush()
            out.append(s)  # debate.py's own collapsible topic block
        elif items and s.startswith("  "):
            items[-1] += " " + s.strip()
        else:
            para.append(s.strip())
    flush()
    return "\n".join(out)


def folded(lines, refs, kind="", who=""):
    """An entry's text, folded so the page reads quickly: a side's response is folded whole behind a button (the
    summaries carry the rounds); closings, out-of-character statements and summaries show in full; a proposal of the
    sides keeps both positions; anything else long shows its first two blocks. The folded text stays findable:
    hidden="until-found" opens on find-in-page."""
    more = lambda h: f'<div class="more" hidden="until-found">{h}</div>' if h.strip() else ""
    def fold(label, secs=""):
        return (f'<button type="button" class="fold" aria-expanded="false"><span class="to-open">▸ {label}</span>'
                f'<span class="to-shut">▾ minimise</span>{secs}</button>')
    # the closings and out-of-character statements are the payoff, and short: always in full
    if kind.startswith(("Closing", "Out of character")) or who == "summary":
        return blocks(lines, refs)
    # a proposal or draft of the sides: both positions and personas stay, each side's voice and description fold
    if any(re.match(r"^#{1,3} Side [A-Z]:", x.strip()) for x in lines):
        keep = lambda x: re.match(r"^#{1,3} Side [A-Z]:", x.strip()) or x.strip().startswith("Persona: ")
        out, run, shown = [], [], None
        for x in lines + [None]:
            k = None if x is None else (True if keep(x) else (shown if not x.strip() else False))
            if run and (x is None or k != shown):
                h = blocks(run, refs)
                out.append(h if shown else more(h))
                run = []
            if x is not None:
                run.append(x)
                shown = k
        return "".join(out) + fold("persona details")
    # a side's response folds away whole: the round's summary, shown in full, already gives each side's TL;DR
    if who in ("claude", "gemini"):
        return fold("full response") + more(blocks(lines, refs))
    parts = blocks(lines, refs).split("\n")
    if len(parts) > 3 and len(plain(" ".join(lines))) > 700 and not any(x.startswith(("<details", "</details")) for x in parts):
        return "\n".join(parts[:2]) + fold("the rest") + more("\n".join(parts[2:]))
    return "\n".join(parts)


# ── listening: each card voiced ahead of time with the videos' Kokoro voices ─────────────────────────────────────
# A card's words go through the video's own speech prep (debate.py's speakable(): no URLs or machine lines, names
# respelt, abbreviations said in full, years said properly; build.py's sentence splitter) and debate-video's voice.py,
# in the voice of whoever is talking: the narrator names whose card it is where that isn't a side's own turn, and each
# side reads its own points in a summary (heard()). The audio is cached per debate in site-voice/<key>.m4a, the key
# hashing the voices and the words, so only new or changed cards are voiced: `build_site.py --voice` voices what's
# missing (slow: about 3 minutes per 1,000 words, on the CPU, free); a plain build uses what's there, and a card with no
# audio has no speaker button.
SPEECH = {}  # debate dir -> {key: (voice, sentences)}, every card's, gathered while the pages are built
KEYS = {}  # debate dir -> {hash of a card's voice and raw words: its audio key}, saved as site-voice/keys.json
_vb = None
_saved = {}


def saved_keys(d):
    if d.name not in _saved:
        f = d / "site-voice/keys.json"
        _saved[d.name] = json.loads(f.read_text()) if f.exists() else {}
    return _saved[d.name]


def video_build():
    global _vb
    if _vb is None:
        sys.path.insert(0, str(VIDEO_SKILL))
        import build as vb  # debate-video's build.py (it brings the debate skill's debate.py, as vb.dbt)
        _vb = vb
    return _vb


# How the site's cards are paced (the videos keep their own). Kokoro leaves about 60 ms at a comma and ignores brackets,
# so "its own innovations (Massive, Gollum)" came out as "innovations massive Gollum"; and the same short gap after
# every sentence, bullet and paragraph read like a machine gun. Voicing a sentence in pieces with silence between made
# it worse: each piece was said as a sentence of its own ("Return... of the Jedi", "where the scow is stowed"). So each
# sentence is said in one go, with brackets and dashes as an inline dash, and the quiet Kokoro leaves after a comma or
# a dash is lengthened in place (voice.py's breathe(), with the timed model below), an aside said a little quieter
# (hush()); then real silence (seconds) after each sentence, and a longer one after a line (a paragraph or a bullet).
PACE = {"sentence": 0.45, "line": 0.8, "aside": 0.4, "comma": 0.25, "hush": 0.7}  # hush: an aside's volume
SPEED = {"bf_emma": 0.96, "am_michael": 0.96, "bm_george": 0.96}  # a touch slower than Kokoro's 1.0, which hurried
ASIDE = "‖"  # a dash or bracket, kept through speakable() (which makes dashes commas), said as a dash
DASHES = re.compile(r"\s*—\s*|\s+–\s+")  # not "1977–1983" or "2–1"
QUOTES = re.compile(r'["“”]')  # read out, they're a stop either side of the word ("obviously" better)


def pauses():
    """The silence voice.py tops each mark up to, inside a sentence."""
    return {",": PACE["comma"], "—": PACE["aside"], ";": PACE["aside"], ":": PACE["aside"]}


def spoken(x):
    """A sentence as Kokoro gets it, and its asides. Brackets, and dashes in pairs, are said as dashes, and what's
    between them is an aside: [n, m] means from the sentence's nth dash to its mth (None: to the end), which voice.py
    says a little quieter, as a person drops their voice for a bracket. A lone dash is a break, not an aside. No quote
    marks (read out, they're a stop either side of the word: "obviously" better), and no doubled-up punctuation where
    a bracket closed before a comma or a full stop."""
    dashes = x.count(ASIDE)
    paired = dashes - dashes % 2
    n = iter(range(dashes))
    x = re.sub(ASIDE, lambda _: (" ⟨ ", " ⟩ ")[k % 2] if (k := next(n)) < paired else " ‖ ", x)
    x = QUOTES.sub("", x.replace("(", " ⟨ ").replace(")", " ⟩ "))
    x = re.sub(r"\s*,?\s*([⟨⟩‖])\s*,?\s*", r" \1 ", x)  # "question), both" -> "question — both"
    x = re.sub(r"\s*[⟨⟩‖]\s*([.!?;:]|$)", r"\1", x)  # "(Massive, Gollum)." ends with the full stop, not a dash
    x = re.sub(r"([.!?;:])\s*[⟨⟩‖]", r"\1", x)  # "(An aside.) Then" -> "An aside. Then"
    x = re.sub(r"^\s*[⟨⟩‖]", "", x)
    x = re.sub(r"([.!?])[.!?]+$", r"\1", x)  # 'not "obviously."' -> "not obviously."
    asides, opened = [], None
    for k, m in enumerate(re.findall(r"[⟨⟩‖]", x)):
        if m == "⟨" and opened is None:
            opened = k
        elif m == "⟩" and opened is not None:
            asides.append([opened, k])
            opened = None
    if opened is not None:
        asides.append([opened, None])
    return re.sub(r"\s+", " ", re.sub(r"[⟨⟩‖]", "—", x)).strip(), asides


def timed_model():
    """Kokoro's model with the length of every sound it makes as a second output (it's computed inside but not given
    out), so voice.py knows where each comma falls. The audio is the same, sample for sample. Made once, from the
    model the video skill downloads, next to it."""
    vb = video_build()
    src = vb.dbt.TTS_CACHE / vb.dbt.TTS_FILES["model"]
    dst = src.with_name(src.stem + ".timed.onnx")
    if not dst.exists():
        print("making the timed Kokoro model (once)", flush=True)
        make = ("import onnx, sys; m = onnx.load(sys.argv[1]); "
                "m.graph.output.append(onnx.helper.make_tensor_value_info('duration', onnx.TensorProto.INT64, ['n'])); "
                "m.graph.node.append(onnx.helper.make_node('Identity', ['/encoder/Gather_output_0'], ['duration'])); "
                "onnx.save(m, sys.argv[2])")
        if subprocess.run([str(vb.dbt.TTS_PYTHON), "-I", "-c", make, str(src), str(dst)]).returncode:
            sys.exit(f"couldn't make the timed model (it needs onnx: {vb.dbt.TTS_PYTHON.parent}/pip install onnx)")
    return dst


def speech(d, parts):
    """Queue a card's words for voicing, as (voice, text) parts said in turn; returns its key."""
    raw = hashlib.sha1(json.dumps(list(parts[0]) if len(parts) == 1 else [list(x) for x in parts]).encode()).hexdigest()[:16]
    if not VIDEO_SKILL.exists():
        key = saved_keys(d).get(raw, raw)  # a card no local build has keyed has no audio, so no speaker button
        SPEECH.setdefault(d.name, {})[key] = None  # still listed, so its audio is copied into the build
        return key
    vb = video_build()
    sents = []
    for voice, text in parts:
        for line in vb.dbt.speakable(DASHES.sub(f" {ASIDE} ", text)).splitlines():
            line = line.strip()
            if not line:
                continue
            if not re.search(r"[.!?:;]$", line):
                line += "."  # a bullet or a label line ends where it ends, not run into the next
            quoted = line.startswith(QUOTED)
            line = line.removeprefix(QUOTED)
            n = len(sents)
            for x in vb.sentences(line):
                if re.search(r"\w", x):
                    said, asides = spoken(x)
                    asides = [[None, None]] if quoted else asides  # all of it, quieter
                    sents.append({"text": x.replace(ASIDE, "—"), "spoken": said, "voice": voice,
                                  "speed": SPEED.get(voice, 1.0), "pauses": pauses(),
                                  **({"asides": asides, "hush": PACE["hush"]} if asides else {}),
                                  "after": PACE["sentence"]})
            if len(sents) > n and not quoted:  # a quote runs on into its reply
                sents[-1]["after"] = PACE["line"]  # the end of a paragraph or a bullet: a longer breath
    key = hashlib.sha1(json.dumps([[x["voice"], x["speed"], x["spoken"], x["pauses"], x.get("asides"), x.get("hush"),
                                    x["after"]] for x in sents]).encode()).hexdigest()[:16]
    SPEECH.setdefault(d.name, {})[key] = (parts[0][0], sents)
    KEYS.setdefault(d.name, {})[raw] = key
    return key


SPEAKER = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path class="spk" d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/>'
           '<path class="wave" d="M15.5 9a4.2 4.2 0 0 1 0 6M18 6.5a7.8 7.8 0 0 1 0 11"/>'
           '<path class="bars" d="M9 7v10M15 7v10"/></svg>')


def say(d, key):
    """The speaker button, if the card's audio exists."""
    if not (d / "site-voice" / f"{key}.m4a").exists():
        return ""
    return f'<button type="button" class="say" data-audio="audio/{key}.m4a" aria-label="Listen" aria-pressed="false">{SPEAKER}</button>'


def seconds(d, key):
    """How long a card's audio runs (0 without it); cached in site-voice/durations.json."""
    f = d / "site-voice" / f"{key}.m4a"
    if not f.exists():
        return 0.0
    cache = d / "site-voice/durations.json"
    known = json.loads(cache.read_text()) if cache.exists() else {}
    if key not in known:
        if not (FFMPEG / "ffprobe").exists():
            return 0.0
        out = subprocess.run([str(FFMPEG / "ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                             capture_output=True, text=True, env={"LD_LIBRARY_PATH": str(FFMPEG)}).stdout
        known[key] = round(float(out), 2)
        cache.write_text(json.dumps(known, indent=0))
    return known[key]


def voice_missing(d):
    """Voice and encode the cards of debate `d` that have no audio yet."""
    vb = video_build()
    cache = d / "site-voice"
    todo = {k: v for k, v in SPEECH.get(d.name, {}).items() if not (cache / f"{k}.m4a").exists()}
    if not todo:
        return
    words = sum(len(" ".join(x["text"] for x in sents).split()) for _, sents in todo.values())
    print(f"{d.name}: voicing {len(todo)} cards, {words} words (about {math.ceil(words * 3 / 1000)} min)", flush=True)
    (cache / "audio").mkdir(parents=True, exist_ok=True)
    jobs = [{"who": voice, "voice": voice, "file": f"audio/{k}.wav", "sentences": sents} for k, (voice, sents) in todo.items()]
    (cache / "audio/jobs.json").write_text(json.dumps(jobs))
    r = subprocess.run([str(vb.dbt.TTS_PYTHON), "-I", str(vb.VOICE_WORKER), "--model", str(timed_model()), "--voices",
                        str(vb.dbt.TTS_CACHE / vb.dbt.TTS_FILES["voices"]), "--dir", str(cache)])
    if r.returncode:
        sys.exit("voicing failed")
    env = {"LD_LIBRARY_PATH": str(FFMPEG)}
    for k in todo:
        wav = cache / f"audio/{k}.wav"
        # AAC at 32 kb/s, mono: clear for speech, plays in every browser, about 14 MB an hour
        subprocess.run([str(FFMPEG / "ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav), "-c:a", "libfdk_aac",
                        "-b:a", "32k", "-ac", "1", "-movflags", "+faststart", "-f", "mp4", str(cache / f"{k}.m4a")], env=env, check=True)
        wav.unlink()
        (cache / f"audio/{k}.wav.json").unlink(missing_ok=True)



# ── a listen: the cards' audio joined into one file ─────────────────────────────────────────────────────────────
# A phone with its screen locked lets audio that's already playing carry on, but pauses any that starts while it's
# locked, so playing each card's own file in turn stopped at the first card change. Each way of listening through a
# page (a quick or a full listen, or the fact-checks) is one file instead: the cards' audio end to end with a short beat
# between, each card marked with where it starts and ends, and the player moves through it by time. Built wherever
# there's an ffmpeg (the video skill's here, apt's in GitHub Actions), cached in site-voice/ by what it holds; not
# committed, being made from what is.
GAP = 0.4  # seconds of quiet between cards
RATE = 24000  # the voices' sample rate
LISTENS = {}  # debate dir -> the listen files its pages use


def ffmpeg():
    """(ffmpeg, its environment, an AAC encoder), or None."""
    if (FFMPEG / "ffmpeg").exists():
        return str(FFMPEG / "ffmpeg"), {"LD_LIBRARY_PATH": str(FFMPEG)}, "libfdk_aac"
    if shutil.which("ffmpeg"):
        return "ffmpeg", None, "aac"
    return None


def listen_file(d, keys):
    """The cards' audio (by key, in order) as one file: (its name, [[start, end]] per key), or None without ffmpeg."""
    if not keys:
        return None
    name = "listen-" + hashlib.sha1(json.dumps([keys, GAP, RATE]).encode()).hexdigest()[:16]
    m4a, spans_f = d / "site-voice" / f"{name}.m4a", d / "site-voice" / f"{name}.json"
    LISTENS.setdefault(d.name, set()).add(m4a.name)
    if m4a.exists() and spans_f.exists():
        return m4a.name, json.loads(spans_f.read_text())
    ff = ffmpeg()
    if not ff:
        if os.environ.get("REQUIRE_LISTENS"):  # the pipeline: no quietly going back to a file per card
            sys.exit("No ffmpeg to join the cards' audio into listens")
        LISTENS[d.name].discard(m4a.name)
        return None
    exe, env, enc = ff
    pcm, spans, gap = bytearray(), [], bytes(int(GAP * RATE) * 2)
    for k in keys:
        # decoded to plain samples and joined here, so every card's place is exact to the sample
        # (via a WAV file: the video skill's ffmpeg can't write raw samples)
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "card.wav"
            subprocess.run([exe, "-v", "error", "-i", str(d / "site-voice" / f"{k}.m4a"), "-ac", "1", "-ar", str(RATE),
                            "-c:a", "pcm_s16le", "-f", "wav", str(wav)], env=env, check=True)
            with wave.open(str(wav)) as w:
                raw = w.readframes(w.getnframes())
        start = len(pcm) / 2 / RATE
        pcm += raw
        spans.append([round(start, 3), round(len(pcm) / 2 / RATE, 3)])
        pcm += gap
    subprocess.run([exe, "-v", "error", "-y", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "-", "-c:a", enc,
                    "-b:a", "32k", "-movflags", "+faststart", "-f", "mp4", str(m4a)], input=bytes(pcm), env=env, check=True)
    spans_f.write_text(json.dumps(spans))
    print(f"{d.name}: joined {len(keys)} cards into {m4a.name} ({spans[-1][1] / 60:.0f} min)", flush=True)
    return m4a.name, spans

# ── a transcript page ──────────────────────────────────────────────────────────────────────────────────────────

# what the sections before the rounds are, for a reader who hasn't seen how a debate runs
PHASE_TOPICS = {"Sides": "Agreeing the two positions and personas, then a coin toss to assign them"}


def phase(kind):
    """The table-of-contents group an entry belongs to."""
    k = re.sub(r" summary$", "", kind)
    if k.startswith("Sides") or k == "Coin flip":
        return "Sides"
    if k == "Evidence":
        return None  # fact-checks sit with the round they follow
    return {"Opening": "Openings", "Openings": "Openings", "Closing": "Closings"}.get(k, k)


def plain(x):
    """Text to compare claims by: words only, lower case."""
    return re.sub(r"\W+", " ", x).strip().lower()


def split_closings(entries):
    """Each side's closing card holds its closing statement and, under "## Out of character", what it really thinks.
    Give the out-of-character part a card of its own, after both closings, and drop the "Out of character summary",
    which repeats those two parts word for word (kept if it says anything they don't)."""
    out, aside = [], []
    for e in entries:
        heads = [i for i, x in enumerate(e["lines"]) if x.strip() == "## Out of character"]
        if e["kind"] == "Closing" and heads:
            k = heads[0]
            closing = [x for x in e["lines"][:k] if x.strip() != "## Closing"]  # the card already says "Closing"
            out.append({**e, "lines": closing})
            # out of character, so not "as" the persona
            aside.append({**e, "kind": "Out of character", "who": e["who"].split(" as ")[0], "lines": e["lines"][k + 1:]})
        elif e["kind"] == "Out of character summary" and aside:
            said = {plain(x) for a in aside for x in a["lines"] if plain(x)}
            summary = {plain(x) for x in e["lines"] if plain(x) and not re.match(r"^\*\*\S+ .+\*\*$", x.strip())}
            out += aside
            if not summary <= said:
                out.append(e)
            aside = []
        else:
            if aside and e["kind"] != "Closing":
                out += aside
                aside = []
            out.append(e)
    return out + aside


def listen(heard_for):
    """The tabs' listen button: a quick or a full listen through the transcript, with how long each runs."""
    if not heard_for["full"]:
        return ""
    mins = lambda t: f"{max(1, round(t / 60))} min"
    return ('<div class="listen"><button type="button" class="go" aria-expanded="false">▶ listen</button>'
            '<div class="menu" hidden>'
            f'<button type="button" data-mode="quick"><b>quick</b> · {mins(heard_for["quick"])}'
            '<span>from the coin toss: summaries, the fact-checks that caught something, closings and out-of-character statements</span></button>'
            f'<button type="button" data-mode="full"><b>full</b> · {mins(heard_for["full"])}'
            '<span>every word</span></button></div></div>')


QUOTED = "⁅"  # starts a line that quotes the other side, said like an aside: a little quieter, then a pause
TURN_HEADING = re.compile(r"^#{1,6}\s*(Rebut|Opening|Closing)\s*$")  # the narrator has just said where we are
QUOTE_LEAD = re.compile(r'^(\s*[-*•]\s+)\*\*["“](.+?)["”]\*\*[:.]?\s*')  # - **"the other side's words"**: reply
REVIEWED = {"AGREE": "agreed", "AMEND": "amendments asked for"}


def heard(e, who, voice_of, announce=""):
    """What a transcript card says aloud, as (voice, text) parts said in turn: its text (not a persona's voice line),
    after a few words from the narrator saying what it is, so the voice you hear is always the one talking. A side's
    turn: the narrator says the round as it starts (`announce`), then the side, without its own "Rebut" heading, and
    with the words it quotes from the other side said like an aside. A side's sides card is named as theirs ("Argon's
    sides review, version 1: agreed"). A summary: the narrator names each side, just "Opus", "Argon" (their personas
    were heard where they were set, in the sides cards; at every summary they'd grate), and the side reads its own
    points."""
    # not the voice ids ("Voice: bf_emma", "voiced by `am_michael`"): they read out as nonsense
    lines = [re.sub(r",?\s*voiced by `?\w+`?", "", x) for x in e["lines"] if not x.strip().startswith("Voice: ")]
    narrator = voice_of("narrator")
    if who in ("claude", "gemini"):
        if not e["kind"].startswith("Sides"):
            first = next((i for i, x in enumerate(lines) if x.strip()), None)
            if first is not None and TURN_HEADING.match(lines[first].strip()):
                lines = lines[first + 1:]
            lines = [QUOTE_LEAD.sub(lambda m: f"{m[1]}{QUOTED}{m[2]}{'' if m[2][-1] in '.!?' else '.'}\n{m[1]}", x) for x in lines]
            return ([(narrator, announce)] if announce else []) + [(voice_of(who), "\n".join(lines))]
        kind = re.sub(r"\s+v(\d+)$", r", version \1", e["kind"]).lower()  # "Sides draft v1": "sides draft, version 1"
        verdict = next((m[1].upper() for m in (re.match(r"^VERDICT:\s*(\w+)", x.strip()) for x in lines) if m), "")
        verdict = f": {REVIEWED.get(verdict, verdict.lower())}" if verdict else ""
        return [(narrator, f"{e['who'].partition(' as ')[0]}'s {kind}{verdict}."), (voice_of(who), "\n".join(lines))]
    parts = [(narrator, [f"{e['kind']}."])]
    for x in lines:
        side = re.match(r"^\*\*(🟠|🔵)\s*(.+?)\*\*", x.strip()) if who == "summary" else None
        if side:
            parts += [(narrator, [f"{side[2].partition(' as ')[0]}."]), (voice_of(DOTS[side[1]]), [])]
        else:
            parts[-1][1].append(x)
    merged = []
    for voice, said in parts:
        if not "\n".join(said).strip():
            continue
        if merged and merged[-1][0] == voice:
            merged[-1][1].extend(said)
        else:
            merged.append((voice, list(said)))
    return [(voice, "\n".join(said)) for voice, said in merged]


def transcript_page(d, meta):
    text = (d / "video/transcript.md").read_text()
    lines = text.splitlines()
    evidence = meta["context"]["evidence"]
    # the transcript's fact-check entries are in the same order as context.json's evidence
    checks = iter(evidence)
    refs = {str(e["id"]) for e in evidence}
    intro, entries, cur = [], [], None
    for ln in lines[1:]:
        m = ENTRY.match(ln)
        if m:
            cur = {**m.groupdict(), "lines": []}
            entries.append(cur)
        elif cur:
            cur["lines"].append(ln)
        else:
            intro.append(ln)
    entries = split_closings(entries)

    body, cards, seen, ids, n = [], [], set(), set(), 0
    script = json.loads((d / "video/script.json").read_text())
    narrator = (script.get("voices") or {}).get("narrator") or meta["context"].get("narrator_voice") or "bm_george"
    voice_of = lambda w: meta["context"]["people"][w]["voice"] if w in ("claude", "gemini") else narrator
    heard_for = {"quick": 0.0, "full": 0.0}  # seconds of listening through the transcript, each way
    where = "Sides"  # the section a fact-check follows
    p = meta["context"]["people"]
    asked = []  # (side, claim) from the sides' CHECK lines, in order: who made each claim the checker checked
    toc = [f'<li class="title"><a href="#top"># {html.escape(meta["title"])}</a></li>']
    heard_cards, check_cards = [], []  # (key, skipped by a quick listen), in page order; the fact-checks tab's keys
    said_round = ""  # the round the narrator last announced, before its first turn
    mark = lambda tab, k: f"\x00{tab}{k}\x00"  # where a card's times go, once its listen file is made
    for e in entries:
        # a pointer to a local file ("Result: `result.md`") means nothing on the site
        if all(re.match(r"^\w+: `[^`]+`$", x.strip()) for x in e["lines"] if x.strip()):
            continue
        n += 1
        who = WHO.get(e["emoji"], "summary")
        if who in ("claude", "gemini"):
            asked += [(who, plain(m[1])) for m in (re.match(r"^CHECK: (.+)", x.strip()) for x in e["lines"]) if m]
        anchor = f"e{n}"
        group = phase(e["kind"])
        if group and group not in seen:
            seen.add(group)
            where = group
            section = re.sub(r"\W+", "-", group.lower()).strip("-")
            # a round's topic, written with the video script (script.json's round_titles)
            rnd = re.fullmatch(r"Round (\d+)", group)
            topic = meta["round_titles"].get(rnd[1]) if rnd else PHASE_TOPICS.get(group)
            toc.append(f'<li><a href="#{section}">{html.escape(group)}'
                       + (f'<span class="topic">{html.escape(topic)}</span>' if topic else "") + "</a></li>")
            # and the same heading above the section's first card
            body.append(f'<h2 class="section" id="{section}"><span class="num">## {html.escape(group)}</span>'
                        + (f'<span class="topic">{html.escape(topic)}</span>' if topic else "") + "</h2>")
        badge, verdict = "", "unclear"
        if who == "evidence":
            ev = next(checks, None)
            if ev:
                v = (ev.get("verdict") or "").upper()
                ev_verdict = v.lower() or "checked"
                verdict = VERDICT.get(v, "unclear")
                badge = f'<span class="verdict {verdict}">{html.escape(v.title() or "Checked")}</span>'
                e["who"] = f"Fact-check #{ev['id']}"
                anchor = str(ev["id"])
                if anchor in ids:  # a check that was run twice: references go to the first
                    anchor += "-2"
                    e["who"] += " · run again"
        ids.add(anchor)
        name, _, persona = e["who"].partition(" as ")
        text = blocks(e["lines"], refs) if who == "evidence" else folded(e["lines"], refs, e["kind"], who)
        by = []
        if who == "evidence":
            # the checker was blind to who made the claim; the site isn't: name the side that asked for it, when its
            # CHECK line matches the claim exactly (the "without knowing which side" line stays as it was)
            claim = next((m[1] for m in (re.match(r"^\*\*Claim checked:\*\* (.+)", x) for x in e["lines"]) if m), "")
            by = [w for w, c in asked if c == plain(claim)]
            if claim and len(set(by)) == 1:
                text = text.replace("<strong>Claim checked:</strong>",
                                    f'<strong><span class="by {by[0]}">{html.escape(p[by[0]]["model"])}</span>\u2019s claim checked:</strong>', 1)
        if who == "evidence":
            # in the transcript, a one-line marker where the check landed; the card itself is in the fact-checks tab
            side = by[0] if len(set(by)) == 1 else ""
            note = meta["notes"].get(anchor, {})
            # a lookup a side asked for (no claim to judge) says so
            what = "request" if note.get("request") else "claim"
            whose = f'<span class="by {side}">{html.escape(p[side]["model"])}</span>’s {what}: ' if side else ""
            # heard: the check, the claim, and our plain-English summary (or the checker's finding, without one); the
            # marker plays it too, so listening through the transcript hears each check where it landed
            finding = next((m[1] for m in (re.match(r"^\*\*Finding:\*\* (.+)", x) for x in e["lines"]) if m), "")
            spoken = (f"{e['who'].replace('#', 'number ')}: {ev_verdict}.\n"
                      + (f"{p[side]['model']}'s {what}: " if side else "The claim: ") + (note.get("request") or claim) + "\n"
                      + (f"In short: {note['summary']}" if note.get("summary") else f"Finding: {finding}"))
            key = speech(d, [(narrator, spoken)])
            heard_for["full"] += seconds(d, key)
            # a quick listen hears only the checks that caught something: one that came back true just confirms what
            # was said
            caught = verdict != "true"
            if caught:
                heard_for["quick"] += seconds(d, key)
            audio = f' data-say="audio/{key}.m4a"' if seconds(d, key) else ""
            if audio:
                heard_cards.append((key, not caught))
            body.append(f'<a class="check-line" id="m-{anchor}" href="#fc-{anchor}" data-check{audio}{"" if caught else " data-skim"}'
                        f'{mark("t", len(heard_cards) - 1) if audio else ""}>'
                        f'<span class="num">#{html.escape(anchor.replace("-2", ""))}</span>{badge}'
                        f'<span class="claim">{whose}{html.escape(note.get("request") or note.get("claim", claim))}</span></a>')
            gist = (f'<p class="gist"><span class="lbl">In short</span>{html.escape(note["summary"])}</p>'
                    if note.get("summary") else "")
            if say(d, key):
                check_cards.append(key)
            cards.append(
                f'<article class="entry evidence" id="fc-{anchor}" data-by="{side}" data-verdict="{verdict}"'
                f'{mark("c", len(check_cards) - 1) if say(d, key) else ""}><header>'
                f'<span class="kind">After {html.escape(where)}</span><span class="who">{html.escape(e["who"])}</span>{badge}'
                f'<time>{e["time"]}</time></header>{gist}<div class="text">{text}</div>'
                f'<a class="back" href="#m-{anchor}">↩ in the transcript</a>{say(d, key)}</article>')
            continue
        turn = who in ("claude", "gemini") and not e["kind"].startswith("Sides")
        announce = ""
        if turn and e["kind"] != said_round:
            announce = {"Opening": "Openings.", "Closing": "Closings."}.get(e["kind"], f"{e['kind']}.")
            said_round = e["kind"]
        key = speech(d, heard(e, who, voice_of, announce))
        heard_for["full"] += seconds(d, key)
        # a quick listen leaves the sides' responses to their round's summary, and starts at the coin toss: the sides
        # being drafted and reviewed before it is background
        skim = "full response" in text or e["kind"].startswith("Sides")
        if not skim:
            heard_for["quick"] += seconds(d, key)
        if say(d, key):
            heard_cards.append((key, skim))
        body.append(
            f'<article class="entry {who}" id="{anchor}"{" data-skim" if skim else ""}'
            f'{mark("t", len(heard_cards) - 1) if say(d, key) else ""}><header>'
            f'<span class="kind">{html.escape(e["kind"])}</span>'
            f'<span class="who">{html.escape(name)}'
            + (f' <span class="persona">as {html.escape(persona)}</span>' if persona else "")
            + f"</span>{badge}<time>{e['time']}</time></header>"
            f'<div class="text">{text}</div>{say(d, key)}</article>')

    # the listens: a full one through the transcript, a quick one without what it skips, and one through the checks
    full = listen_file(d, [k for k, _ in heard_cards])
    quick = listen_file(d, [k for k, skim in heard_cards if not skim])
    checks_l = listen_file(d, check_cards)
    quick_at = {}  # a transcript card's place in the quick listen
    for i, (_, skim) in enumerate(heard_cards):
        if not skim:
            quick_at[i] = len(quick_at)
    span = lambda f, j: f"{f[1][j][0]},{f[1][j][1]}"
    def times(m):
        tab, i = m[1][0], int(m[1][1:])
        if tab == "c":
            return f' data-full="{span(checks_l, i)}" data-quick="{span(checks_l, i)}"' if checks_l else ""
        out = f' data-full="{span(full, i)}"' if full else ""
        return out + (f' data-quick="{span(quick, quick_at[i])}"' if quick and i in quick_at else "")
    fill = lambda html_: re.sub(r"\x00([tc]\d+)\x00", times, html_)
    body, cards = [fill(x) for x in body], [fill(x) for x in cards]
    files = lambda a, b: (f' data-file-full="audio/{a[0]}"' if a else "") + (f' data-file-quick="audio/{b[0]}"' if b else "")

    def chip(attr, value, label, count):
        n = f' <span class="n">{count}</span>'
        return f'<button type="button" data-{attr}="{value}" aria-pressed="{str(value == "all").lower()}">{label}{n}</button>'
    count = lambda attr, v: sum(f'data-{attr}="{v}"' in c for c in cards)
    filters = (
        # each label kept with its chips, so a narrow screen wraps between the groups, not inside one
        '<div class="filters"><span class="grp"><span class="lbl">claim by</span>' + chip("by", "all", "all", len(cards))
        + "".join(chip("by", w, f'<span class="by {w}">{html.escape(p[w]["model"])}</span>', count("by", w)) for w in ("claude", "gemini"))
        + '</span><span class="grp"><span class="lbl">verdict</span>' + chip("verdict", "all", "all", len(cards))
        + "".join(chip("verdict", v, label, count("verdict", v)) for v, label in
                  (("true", "true"), ("partly", "partly true"), ("false", "false"), ("unclear", "unclear")) if count("verdict", v))
        + '</span></div>')
    sides = "".join(
        f'<div class="side {w}"><span class="dot"></span><b>{html.escape(p[w]["model"])}</b> '
        f'<span class="lab">{html.escape(p[w]["lab"])}</span><br><span class="persona">{html.escape(p[w]["persona"] or "")}</span></div>'
        for w in ("claude", "gemini"))
    return page(
        f"{meta['title']} · transcript",
        crumbs([HOME, meta["dir"], d.name])
        + f'<div class="layout"><aside class="toc"><div class="label" role="button" tabindex="0" aria-expanded="false">contents</div><ol>{"".join(toc)}</ol></aside>'
        f'<main><section class="hero" id="top"><div class="kicker">{meta["kind"]} · {meta["date"]} · {meta["rounds"]} rounds · <a href="#checks">{len(evidence)} fact-checks</a></div>'
        f'<h1>{html.escape(meta["title"])}</h1><div class="sides">{sides}</div>'
        f'<p class="note">The full discussion, unedited: every round, every summary and every fact-check, in order. '
        f'Every quote in the video comes from here, word for word.</p>'
        f'<div class="intro">{blocks(intro, refs)}</div></section>'
        '<nav class="tabs" role="tablist"><a href="#transcript" role="tab" data-tab="transcript">transcript</a>'
        f'<a href="#checks" role="tab" data-tab="checks"><span class="long">🔎 fact-</span>checks <span class="n">{len(cards)}</span></a>'
        + listen(heard_for) + '<button type="button" class="all" aria-pressed="false">expand<span class="long"> all</span></button></nav>'
        f'<section class="panel" id="transcript" data-panel="transcript"{files(full, quick)}>{"".join(body)}</section>'
        f'<section class="panel" id="checks" data-panel="checks"{files(checks_l, checks_l)}><h2 class="section"><span class="num">## Fact-checks</span>'
        '<span class="topic">Every claim the checker tested</span></h2>'
        '<p class="note checks-note">In the order they were run. Each starts with our plain-English summary; the checker’s '
        'own report follows, unedited. Hover or tap a 🔎 link anywhere in the transcript for a preview.</p>'
        f'{filters}{"".join(cards)}<p class="none" hidden>No checks match.</p></section></main></div>',
        depth=2)


def crumbs(dirs):
    """The path: ~/discussions links home; a kind (debate/) is plain, having no page of its own; the last part is
    where you are."""
    out = []
    for k, label in enumerate(dirs):
        if k == len(dirs) - 1:
            out.append(f'<span class="dir here">{label}</span>')
        elif k == 0:
            out.append(f'<a class="dir" href="{"../" * (len(dirs) - 1)}index.html">{label}</a>')
        else:
            out.append(f'<span class="dir">{label}</span>')
    return '<nav class="crumbs">' + '<span class="sep">/</span>'.join(out) + "</nav>"


def terminal(path, command, rows):
    """A terminal window at `path` that has run `command`, printed `rows`, and is waiting at the prompt."""
    prompt = f'<div class="row prompt"><span class="ps">{path}</span> <span class="dl">$</span> '
    # the window's buttons, with macOS's close, minimise and full-screen marks that show on hovering them
    lights = ('<span class="lights" aria-hidden="true">'
              '<i class="l"><svg viewBox="0 0 10 10"><path d="M3 3l4 4M7 3l-4 4"/></svg></i>'
              '<i class="l"><svg viewBox="0 0 10 10"><path d="M2.5 5h5"/></svg></i>'
              '<i class="l"><svg viewBox="0 0 10 10"><path class="fill" d="M3 3h2.7L3 5.7zM7 7H4.3L7 4.3z"/></svg></i></span>')
    return (f'<div class="term"><div class="bar">{lights}<em>{path}</em></div>'
            f'<div class="screen">{prompt}{command}</div>{"".join(rows)}{prompt}<span class="cursor"></span></div>'
            "</div></div>")


# ── the directory tree ─────────────────────────────────────────────────────────────────────────────────────────

def tree_rows(nodes, prefix=()):
    """`tree`'s lines for nested (label_html, comment, children) nodes. The box-drawing branches are kept as
    (invisible) text, so a copy of the tree still has them, and drawn as lines in style.css, which join up across
    the terminal's tall rows and a comment wrapped onto a second line, where the characters leave gaps."""
    cell = {"pipe": "│   ", "gap": "    ", "tee": "├── ", "elbow": "└── "}
    rows = []
    for i, (label, note, children) in enumerate(nodes):
        last = i == len(nodes) - 1
        branches = "".join(f'<i class="t {k}">{cell[k]}</i>' for k in (*prefix, "elbow" if last else "tee"))
        rows.append(f'<div class="row"><span class="g">{branches}</span><span class="item">{label}'
                    + (f'<span class="cmt">{note}</span>' if note else "") + "</span></div>")
        rows += tree_rows(children, (*prefix, "gap" if last else "pipe"))
    return rows


def index_page(by_kind):
    """`tree -d`: folders only. Each discussion's folder is its transcript; the kinds are just folders."""
    nodes, dirs = [], 0
    for kind, _ in KINDS:
        found = by_kind[kind]
        dirs += 1 + len(found)
        kids = []
        for d, meta in found:
            note = f"# {html.escape(meta['title'])} · {meta['rounds']} rounds · {meta['checks']} fact-checks"
            if meta.get("video_url"):
                note += f' · <a class="file" href="{meta["video_url"]}">video ↗</a>'
            # index.html, not just the folder: opened from disk, a folder link shows a file listing
            kids.append((f'<a class="dir" href="{kind}/{d.name}/index.html">{d.name}/</a>', note, []))
        nodes.append((f'<span class="dir">{kind}/</span>', "", kids))
    rows = ([f'<div class="row"><span class="dir">{HOME[2:]}/</span></div>'] + tree_rows(nodes)
            + [f'<div class="row blank"> </div><div class="row cmt">{dirs} director{"y" if dirs == 1 else "ies"}</div>'])
    return page(
        "Discussion transcripts",
        '<main class="home"><section class="hero"><div class="kicker">AI vs AI · fact-checked</div>'
        '<h1>Discussion transcripts</h1><p class="note">Every discussion from the channel, in full and unedited. '
        'Two AI models from two different companies take on a question over several rounds, from opposite sides '
        'in a debate, or towards an answer they both accept in a consensus, with a third checking their facts '
        'blind. The videos quote these word for word.</p></section>'
        + terminal(HOME, "tree -d", rows) + "</main>",
        depth=0)



# ── docs/publishing: how the site is built, tested privately and published, in the site's own look ─────────────

def out_rows(*lines):
    """A command's output lines in a terminal; `# …` lines are comments."""
    return [f'<div class="row{" cmt" if x.startswith("#") else ""}">{x}</div>' for x in lines]


def docs_page():
    term = lambda path, cmd, *out: terminal(path, cmd, out_rows(*out))
    step = lambda text: f'<div class="step"><span class="pipe" aria-hidden="true">│<br>▼</span><p>{text}</p></div>'
    stage = lambda n, name, what, cls="": (f'<li class="stage {cls}"><span class="n">{n}</span><b>{name}</b>'
                                           f'<span class="what">{what}</span></li>')
    tree = tree_rows([
        ('<span class="dir">.github/workflows/</span>', "# site.yml: the pipeline", []),
        ('<span class="fname">build_site.py</span>', "# writes the whole site into public/", []),
        ('<span class="dir">discussions/</span>', "# each discussion's transcript, fact-checks and audio", []),
        ('<span class="dir">assets/</span>', "# style.css, site.js, the logo's zap", []),
        ('<span class="fname">check_leaks.py</span>', "# fails the build if anything private is in it", []),
        ('<span class="fname">sync.py</span>', "# brings new discussions in from ~/debates", []),
        ('<span class="fname">publish.py</span>', "# sync, build, check, commit, push", []),
        ('<span class="fname">serve.py</span>', "# the site on this machine, as Pages serves it", []),
        ('<span class="fname">wrangler.jsonc</span>', "# the private test site's settings", []),
    ])
    body = f"""
<main class="home doc">
<section class="hero"><div class="kicker">How this site is made</div><h1>Build, test, publish</h1>
<p class="note">Every page here is a static file, written by a script from the discussions' own folders: the
transcripts, the fact-checks and the audio, voiced ahead of time. A change goes to a private test copy first, gets
checked on a real phone, and only goes live once it's approved. The source is all
<a href="https://github.com/NeuralSummit/neuralsummit.io">on GitHub</a>.</p></section>

<h2><span class="hash">##</span> The pipeline</h2>
<p>Every push to the repo runs it, in GitHub Actions:</p>
<ol class="pipeline">
{stage(1, "build", "the site from the repo, then a leak check: no email addresses, local paths or anything private")}
{stage(2, "test", "uploaded to <code>test.neuralsummit.io</code>, which only the channel's human can open")}
{stage(3, "approve", "checked on a phone, then approved on GitHub or in its app", "gate")}
{stage(4, "live", "the same build, on GitHub Pages at <code>neuralsummit.io</code>")}
</ol>
<p>Starting it, on the channel's machine:</p>
{term("~/debates/site", 'python3 publish.py "what changed" "why, in a line or two"', "Synced from ~/debates: 3 file(s) new or changed",
      "Built 1 discussion(s) into public/", "Leak check: public/ is clean",
      "Pushed. Building now; check https://test.neuralsummit.io in a minute or two, then approve")}
{step("Each discussion's inputs come in from the folders the debate and video tools write. New cards are voiced "
      "here first (<code>--voice</code>): the voices run on this machine's CPU, so the pipeline only ever uses audio "
      "that's already made. <code>python3 serve.py</code> shows a build on this machine before anything's pushed.")}

<h2><span class="hash">##</span> Where things are</h2>
{terminal("~/debates", "tree site", ['<div class="row"><span class="dir">site/</span></div>'] + tree)}

<h2><span class="hash">##</span> The test site</h2>
<ul>
<li><b>What:</b> a Cloudflare Worker that only serves the build's files (Cloudflare has folded its Pages product into
Workers; this is its current form), uploaded by the pipeline's test step with <code>wrangler</code>, Cloudflare's
tool, pinned to one version that had been out a while.</li>
<li><b>Who gets in:</b> Cloudflare Access sits in front of <code>test.neuralsummit.io</code> and lets one email
address through, with a one-time code sent to it. The gate was set up before the first upload, so the copy was never
public, not even for a moment.</li>
<li><b>No back doors:</b> the Worker's own Cloudflare addresses (<code>workers.dev</code> and preview links) are
switched off, so Access is the only way in.</li>
<li><b>Always fresh:</b> it's served with <code>Cache-Control: no-store</code>, so a reload shows the latest
upload at once, and <code>noindex</code>, so search engines leave it alone.</li>
</ul>

<h2><span class="hash">##</span> Going live</h2>
<ul>
<li><b>The gate:</b> the live step deploys to the repo's <code>github-pages</code> environment, which needs a
reviewer's approval. Until it's pressed, the run waits; a newer push replaces a run that's still waiting.</li>
<li><b>Hosting:</b> GitHub Pages, deployed straight from the pipeline, so the repo holds the source, not built pages.</li>
<li><b>Secrets:</b> the Cloudflare token lives in the <code>test</code> environment's secrets, and the private part
of the leak check in a repo secret, so neither is ever in the code.</li>
<li><b>Pinned:</b> every action the pipeline uses is pinned to an exact commit, not a tag that could move.</li>
<li><b>Commits:</b> made by the channel's human, with Claude as co-author, using GitHub's no-reply address so no
real email is ever published.</li>
<li><b>Protection:</b> a rule on <code>main</code> refuses force-pushes and deleting the branch, admins included.
Only the human has write access; anyone can open an issue.</li>
<li><b>Caching:</b> Pages lets browsers keep CSS and scripts for up to 10 minutes, so a phone can show the old ones
just after going live. The test site doesn't cache.</li>
</ul>

<h2><span class="hash">##</span> Listening</h2>
<p>Each card is voiced ahead of time with the videos' Kokoro voices, and the build records which audio belongs to
which card (<code>keys.json</code>), so it doesn't need the voices to build. A phone with its screen locked lets audio
that's already playing carry on, but pauses any that starts while it's locked, so a listen isn't a card's file after
another: the build joins each way of listening (quick, full, the fact-checks) into one file, with a short beat between
cards and every card marked with where it starts. The player moves through that file by time, so going from card to
card never starts anything new.</p>
</main>"""
    return page("How this site is made", crumbs([HOME, "docs", "publishing"]) + body, depth=2)


def redirect_home(depth):
    """For a folder with no page of its own (debate/): someone who trims the URL lands on the tree."""
    home = "../" * depth + "index.html"
    return (f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={home}">'
            f'<link rel="canonical" href="{home}"><title>Redirecting</title><a href="{home}">{HOME}</a>\n')


def page(title, content, depth):
    up = "../" * depth
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · {" ".join(CHANNEL)}</title>
<link rel="icon" href="{up}logo.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=JetBrains+Mono:ital,wght@0,400;0,600;0,700;0,800;1,400;1,600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{up}style.css">
<noscript><style>.more {{ display: block !important; content-visibility: visible !important; }} .fold, .tabs .all, .say {{ display: none !important; }}</style></noscript>
</head>
<body>
<div class="bg" aria-hidden="true"><div class="glow"></div><svg class="shapes"></svg></div>
<header class="top"><a class="brand" href="{up}index.html" aria-label="{" ".join(CHANNEL)}: home">{logo_svg(56, "hdr")}<span class="lockup"><span class="wordmark" aria-hidden="true"><span class="w1" data-text="{CHANNEL[0]}">{CHANNEL[0]}</span><span class="w2" data-text="{CHANNEL[1]}">{CHANNEL[1]}</span><span class="cursor duo"></span></span><span class="ps">{HOME}</span></span></a></header>
<nav class="links" aria-label="Elsewhere">{links_html("hdr", 26)}</nav>
<div id="page">{content}</div>
<footer class="credit"><nav class="links-foot" aria-label="Elsewhere">{links_html("ft", 22)}</nav>Directed by the human behind this channel · Built with Claude Opus</footer>
<script src="{up}zap.js"></script>
<script src="{up}site.js"></script>
</body>
</html>
"""


def meta_of(d):
    v = d / "video"
    script, ctx = json.loads((v / "script.json").read_text()), json.loads((v / "context.json").read_text())
    text = (v / "transcript.md").read_text()
    date = re.search(r"\d{4}-\d\d-\d\d", d.name)
    return {"title": script["title"], "context": ctx, "rounds": ctx["rounds"], "checks": len(ctx["evidence"]),
            "words": len(text.split()), "date": date[0] if date else "", "video_url": script.get("video_url"),
            "round_titles": script.get("round_titles") or {}, "kind": KIND.get(ctx["mode"], "Discussion"),
            "dir": "debate" if ctx["mode"] == "opposing" else "consensus",
            # our plain-English summaries of the fact-checks (see site.json's _about)
            "notes": json.loads((d / "site.json").read_text()).get("checks", {}) if (d / "site.json").exists() else {}}


def main():
    if "--voice" in sys.argv[1:]:
        build()  # gathers every card's words
        for d in DEBATES.iterdir():
            if d.name in SPEECH:
                voice_missing(d)
        SPEECH.clear()
    build()


def build():
    found = [(d, meta_of(d)) for d in sorted(DEBATES.iterdir(), reverse=True)
             if (d / "video/transcript.md").exists() and (d / "video/script.json").exists()]
    by_kind = {kind: [(d, m) for d, m in found if m["dir"] == kind] for kind, _ in KINDS}
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for f in ASSETS.iterdir():
        if f.suffix != ".wav" and ".bak" not in f.name:
            shutil.copy(f, OUT / f.name)
    # the logo's zap, as a script: site.js decodes it itself, which works even when the site is opened from disk
    (OUT / "zap.js").write_text(f"window.ZAP = '{base64.b64encode((ASSETS / 'zap.wav').read_bytes()).decode()}';\n")
    (OUT / "logo.svg").write_text(logo_svg(64, "fav", scan=False))
    (OUT / "index.html").write_text(index_page(by_kind))
    (OUT / "docs" / "publishing").mkdir(parents=True)
    (OUT / "docs" / "index.html").write_text(redirect_home(1))
    (OUT / "docs" / "publishing" / "index.html").write_text(docs_page())
    for kind, _ in KINDS:
        (OUT / kind).mkdir()
        (OUT / kind / "index.html").write_text(redirect_home(1))
        for d, meta in by_kind[kind]:
            (OUT / kind / d.name).mkdir()
            (OUT / kind / d.name / "index.html").write_text(transcript_page(d, meta))  # the folder is the transcript
            # its cards' audio, beside it
            have = [k for k in SPEECH.get(d.name, {}) if (d / "site-voice" / f"{k}.m4a").exists()]
            if have:
                (OUT / kind / d.name / "audio").mkdir()
                for k in have:
                    shutil.copy(d / "site-voice" / f"{k}.m4a", OUT / kind / d.name / "audio" / f"{k}.m4a")
                for f in LISTENS.get(d.name, ()):
                    shutil.copy(d / "site-voice" / f, OUT / kind / d.name / "audio" / f)
            # listen files no page uses any more (made from older words)
            for f in (d / "site-voice").glob("listen-*") if (d / "site-voice").exists() else []:
                if f.with_suffix(".m4a").name not in LISTENS.get(d.name, ()):
                    f.unlink()
    for d, _ in found:  # a local build saves each card's audio key, for builds without the skill
        keys = dict(sorted(KEYS.get(d.name, {}).items()))
        f = d / "site-voice/keys.json"
        if keys and f.parent.exists() and (not f.exists() or json.loads(f.read_text()) != keys):
            f.write_text(json.dumps(keys, indent=0) + "\n")
    print(f"Built {len(found)} discussion(s) into {OUT}")


if __name__ == "__main__":
    main()
