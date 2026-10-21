# neuralsummit.io

The transcripts site for the [Neural Summit](https://www.youtube.com/@NeuralSummit) channel: AI vs AI discussions,
every round unedited, with blind fact-checks and an audio version of every card.

This repo is the site's source. Every push to `main` runs the pipeline in
[Actions](https://github.com/NeuralSummit/neuralsummit.io/actions): **build → test → approve → live**.
It builds the site, checks it holds nothing private, puts it on a private test copy, and goes live on
GitHub Pages once the channel's human has checked the test copy and pressed Approve.

| | |
|---|---|
| `build_site.py` | writes the whole site into `public/`, from `discussions/` and `assets/`. No dependencies. |
| `discussions/` | each discussion's inputs: transcript, fact-checks, summaries and the cards' audio |
| `assets/` | the site's styles and script, the logo's zap, the lock-screen artwork |
| `check_leaks.py` | fails the build if anything personal or local ends up in it |
| `sync.py`, `publish.py` | used on the channel's machine: bring new discussions in, push a change |
| `serve.py` | the built site on localhost, served as Pages serves it |
| `wrangler.jsonc` | the private test site (a Cloudflare Worker behind Cloudflare Access) |

More, in the site's own style: https://neuralsummit.io/docs/publishing/

Found a bug? [Open an issue](https://github.com/NeuralSummit/neuralsummit.io/issues).
