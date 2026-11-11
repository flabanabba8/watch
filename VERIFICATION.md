# Watch verification

Checked 2026-11-11 for the combined plugin `watch` 0.1.0.

## Passed for the suite

- `python3 -m unittest discover -s tests` from the plugin folder, in a throwaway Hermes home: 36 tests pass: the carried-over Python tests of both parts (the anime and the movies playback, provider, credential and build-script tests) plus 3 new suite tests (registration, wiki tool list, separate data folders). The tests of the stand-alone parts were carried over with their paths adjusted; the Desktop and dashboard tests were not carried over because those surfaces are not part of this plugin.
- Registration test: `register()` exposes exactly the 14 tools declared in `plugin.yaml` (7 `anime_*`, 7 `movies_*`), no hooks, no commands, no middleware, and the two skills `watch-anime` and `watch-movies`. The wiki tool reference lists exactly those 14 tools.
- Data test: the two parts write to separate folders `plugin-data/watch/anime/` and `plugin-data/watch/movies/`.
- `hermes plugins validate --install-deps` on a clean export of the committed tree, in a disposable Hermes home: passed with no warnings and no failed checks, including the declared-tools match, security scan and no-core-override rules (Hermes v0.23.0).
- A static scan of the tree and the single commit's history for credentials, personal paths, device ids and e-mail addresses: no findings.

## Not run for the suite

- The Go tests of the movies bridge source in `movies/native/` were not run for this combined build (no Go toolchain here). They are carried over unchanged and passed in the stand-alone movies plugin's own verification.
- No live provider request, playback or Hermes session was run for the combined plugin. The live evidence is each part's own, from the stand-alone plugins:
  - Anime: live search, episode list and resolution on 2026-11-07, then a headless mpv run (no window, null audio) that reached a 7-second position at 720p.
  - Movies and TV: a freshly built bridge searched, fetched details and resolved a stream through VixSrc on 2026-11-07, and a headless mpv run reached a 7-second position; explicit LookMovie playback and an HLS fixture with a separate audio rendition also passed in the part's own checks. A user-supplied TMDB key on the new bridge was not live-tested.
- Not verified at all: Windows, long playback, a picture or sound review by a person, provider uptime, the licensing of the sites' content.
