---
status: SOURCE-REVIEWED
curated: 2026-11-09
---
# watch-movies setup and task guide

This is a source-reviewed operating guide, not a claim of a new live test.
Resolve exact parameter shapes from [tool contracts](tools.md) and
[registration schemas](contracts.json) before calling a tool.

## Setup decisions

Confirm Linux sealed-memfd support, Python 3.11+, mpv and a trusted bridge matching the configured hash/protocol. Bridge source build is explicit and may fetch dependencies; no binary downloads happen merely to inspect this wiki. Select movie/year or exact TV series/season/episode.

## Worked task flow

Use movies_search and movies_details for identity. On explicit play, movies_play selects Auto or the user’s named provider and returns a session; inspect movies_status before claiming playback. movies_control targets only that session. movies_resume resolves a fresh stream and uses latest observed position even if the source changes.

## Failure diagnosis

Preserve HLS master playlists and required headers so separate audio renditions are not dropped. Auto has its existing bounded provider fallback; explicit provider choices/cancellation do not authorize that fallback. Bridge integrity or provider-credential failures need diagnosis, not bypassing verification or borrowing personal Luffy config. Playback quality is adaptive, not an enforced cap.

## Acceptance and evidence limits

Accept observed video and audio for the exact selected title/episode, accurate status/progress and honest provider failures. A bridge resolution success is not playback success. Keep the earlier runtime/model-agnostic exception and do not run a provider or player merely for wiki checks.

## Source trail

Derived from the packaged [README](../../README.md), [manifest](../../plugin.yaml),
registered tool schemas and the tests listed in provenance.json. Existing
verification records describe their own dated scope; no new live capability
was inferred from this documentation review.
