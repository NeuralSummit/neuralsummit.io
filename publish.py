#!/usr/bin/env python3
"""Send a change down the pipeline: bring the discussions in from ~/debates (sync.py), build and leak-check here,
then commit and push. GitHub Actions takes it from there (.github/workflows/site.yml): it builds again, puts it on
the private test site, and waits for you to approve it before it goes live. Watch and approve at ACTIONS.

    python3 publish.py "what changed" "why, and anything worth knowing, in a line or two"
    python3 publish.py --voice "what changed" "why"   # first voice cards with no audio yet (slow, local only)

Commits are yours, as this repo's git settings say (user.name, and user.email set to your GitHub no-reply address so
no real email is published), with Claude as co-author.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

import build_site
import check_leaks
import sync

HERE = Path(__file__).parent
ACTIONS = "https://github.com/NeuralSummit/neuralsummit.io/actions"
CO_AUTHOR = "Claude Opus 5.5 <noreply@anthropic.com>"


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(HERE), *args], check=check, capture_output=True, text=True)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    msg = args[0] if args else "Update the site"
    # the commit's description, under its subject, wrapped at 72 as git expects (GitHub shows it as written, unwrapped)
    about = textwrap.fill(args[1], 72, break_long_words=False, break_on_hyphens=False) if len(args) > 1 else ""
    sync.main()
    build_site.main()  # --voice, if given, is read by build_site itself
    sys.argv = [sys.argv[0], str(build_site.OUT)]
    check_leaks.main()  # exits if anything shouldn't be public
    git("add", "-A")
    if not git("status", "--porcelain").stdout.strip():
        print("Nothing changed since the last publish.")
        return
    git("commit", "--quiet", "-m", msg, *(["-m", about] if about else []), "-m", f"Co-Authored-By: {CO_AUTHOR}")
    git("push", "--quiet", "origin", "main")
    print(f"Pushed. Building now; check https://test.neuralsummit.io in a minute or two, then approve at {ACTIONS}")


if __name__ == "__main__":
    main()
