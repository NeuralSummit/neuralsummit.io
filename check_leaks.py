#!/usr/bin/env python3
"""Fail if the built site holds anything that shouldn't be public: email addresses, local file paths, localhost
links. Run on every build, here and in GitHub Actions. Patterns that are themselves private (names, addresses) can be
added one per line in a file named by $LEAK_PATTERNS_FILE, or ~/.config/neuralsummit/private-patterns.txt; in
Actions they come from the LEAK_PATTERNS secret, so they never appear in this repo.

    python3 check_leaks.py [folder]      # default: public/
"""
import os
import re
import sys
from pathlib import Path

TEXT = {".html", ".css", ".js", ".json", ".md", ".txt", ".svg", ".xml"}
ALLOWED_EMAIL = re.compile(r"@users\.noreply\.github\.com$|^noreply@anthropic\.com$")
GENERIC = {
    "an email address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
    "a local path": re.compile(r"/home/[a-z_][a-z0-9_-]*/|/Users/[A-Za-z]|[A-Za-z]:\\\\Users\\\\|/mnt/[a-z]/"),
    "a localhost link": re.compile(r"https?://(?:localhost|127\.0\.0\.1)"),
}


def private_patterns():
    f = Path(os.environ.get("LEAK_PATTERNS_FILE") or Path.home() / ".config/neuralsummit/private-patterns.txt")
    if not f.exists():
        return {}
    lines = [x.strip() for x in f.read_text().splitlines() if x.strip() and not x.startswith("#")]
    return {f"private pattern {i + 1}": re.compile(x, re.I) for i, x in enumerate(lines)}


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "public")
    checks = {**GENERIC, **private_patterns()}
    hits = []
    for f in sorted(root.rglob("*")):
        if f.suffix not in TEXT or not f.is_file():
            continue
        text = f.read_text(errors="replace")
        for what, rx in checks.items():
            for m in rx.finditer(text):
                if what == "an email address" and ALLOWED_EMAIL.search(m.group(0)):
                    continue
                # say which file and what kind of thing, never the match itself (it may be the private part)
                hits.append(f"{f.relative_to(root)}: {what}")
                break
    if hits:
        print("Not publishing: the build has things that shouldn't be public:", *sorted(set(hits)), sep="\n  ")
        sys.exit(1)
    print(f"Leak check: {root.name}/ is clean ({len(checks)} checks)")


if __name__ == "__main__":
    main()
