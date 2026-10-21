#!/usr/bin/env python3
"""Bring each discussion's site inputs from ~/debates (where the debate and video skills write them) into
discussions/, the folder this repo builds from. Only what the site shows is copied: the transcript, the sides and
fact-checks (context.json), our summaries of the checks (site.json), the cards' audio, and from the video's script just
the four things the site uses, not the script of a video that may not be out yet.

    python3 sync.py
"""
import json
import shutil
from pathlib import Path

SRC = Path.home() / "debates"
DST = Path(__file__).parent / "discussions"
SCRIPT_FIELDS = ("title", "round_titles", "voices", "video_url")


def copy(a, b):
    """Copy a to b if it's new or changed; True if it did."""
    if b.exists() and b.read_bytes() == a.read_bytes():
        return False
    b.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(a, b)
    return True


def main():
    changed = []
    for d in sorted(SRC.iterdir()):
        v = d / "video"
        if not ((v / "transcript.md").exists() and (v / "script.json").exists() and (v / "context.json").exists()):
            continue  # not a finished discussion (or not a discussion at all, like site/)
        out = DST / d.name
        for name in ("transcript.md", "context.json"):
            if copy(v / name, out / "video" / name):
                changed.append(f"{d.name}/video/{name}")
        script = json.loads((v / "script.json").read_text())
        trimmed = json.dumps({k: script[k] for k in SCRIPT_FIELDS if k in script}, indent=1, ensure_ascii=False) + "\n"
        f = out / "video/script.json"
        if not f.exists() or f.read_text() != trimmed:
            f.write_text(trimmed)
            changed.append(f"{d.name}/video/script.json")
        if (d / "site.json").exists() and copy(d / "site.json", out / "site.json"):
            changed.append(f"{d.name}/site.json")
        # audio voiced before the site had its own repo; new voicing (build_site.py --voice) happens in discussions/
        for m in sorted((d / "site-voice").glob("*.m4a")) if (d / "site-voice").exists() else []:
            if not (out / "site-voice" / m.name).exists():
                copy(m, out / "site-voice" / m.name)
                changed.append(f"{d.name}/site-voice/{m.name}")
        dur = d / "site-voice/durations.json"
        if dur.exists() and not (out / "site-voice/durations.json").exists():
            copy(dur, out / "site-voice/durations.json")
    print(f"Synced from {SRC}: " + (f"{len(changed)} file(s) new or changed" if changed else "nothing new"))
    return changed


if __name__ == "__main__":
    main()
