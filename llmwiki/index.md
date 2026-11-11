---
status: SOURCE-DERIVED
curated: 2026-11-11
---
# Watch LLM wiki

Read this index on first use, then only the part you need. This wiki ships inside
the plugin and needs no outside checkout. It gives the active host model domain
knowledge; it is not a separate LLM service.

Watch is one plugin with two parts that share one idea: find it, stream it,
resume it. Pick the part by what the user asks for.

| User asks for | Part | Tools | Start with |
|---|---|---|---|
| An anime series or episode | anime | `anime_*` | [anime wiki](../anime/llmwiki/index.md), skill `watch-anime` |
| A film or a non-anime TV series | movies | `movies_*` | [movies wiki](../movies/llmwiki/index.md), skill `watch-movies` |

## Knowledge map

- [Tool reference for the whole suite](tools.md): exactly the 14 registered tools.
- Anime: [setup and task guide](../anime/llmwiki/task-guide.md), [registration schemas](../anime/llmwiki/contracts.json), [tool contracts](../anime/llmwiki/tools.md).
- Movies and TV: [setup and task guide](../movies/llmwiki/task-guide.md), [registration schemas](../movies/llmwiki/contracts.json), [tool contracts](../movies/llmwiki/tools.md).
- [Suite README](../README.md): install, needs, limits and credits.
- [Manifest](../plugin.yaml): supported host, settings and tools.
- [Verification record](../VERIFICATION.md): what was tested for the suite.

## Rules that hold for both parts

- Playback opens a window and plays sound on the computer running Hermes. Only
  start it when the user asks. Linux with mpv only.
- A launched player is "starting", not "playing". Check the status tool before
  saying it plays.
- Stream URLs are fresh on every launch and are never reused or shown.
- The streaming sites are third-party services whose content licensing the user
  must judge. Do not bypass blocks, keep retrying, or save media.
- Each part keeps its own watch history and settings. They do not share state.
- The movies part needs a bridge the user built and a TMDB key of their own
  (or a bridge built with Luffy's own key). Check the settings before searching.

The per-part `provenance.json` files record the stand-alone packages as they were
when those wikis were curated; paths in them name the old stand-alone layout.
