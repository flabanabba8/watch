---
status: SOURCE-REVIEWED
curated: 2026-11-09
---
# watch-anime setup and task guide

This is a source-reviewed operating guide, not a claim of a new live test.
Resolve exact parameter shapes from [tool contracts](tools.md) and
[registration schemas](contracts.json) before calling a tool.

## Setup decisions

Confirm Linux, Python 3.11+, POSIX shell utilities and mpv, and which exact title/season/audio variant the user wants. Playback opens on the Hermes host, not in a remote chat client. The pinned ani-cli provider path and the earlier runtime-audit exception remain unchanged.

## Worked task flow

Use anime_search, choose a returned stable identifier and inspect anime_episodes. Only on a playback request call anime_play with a listed episode and selected audio/quality. Poll anime_status until media actually loads; control only the returned owned session. anime_resume resolves a fresh stream and uses recorded progress.

## Failure diagnosis

A launched process is starting, not playing. Stream URLs expire and must not be reused as saved playback state. Natural EOF plus near-end progress establishes completion; stop/seek alone does not. A fallback quality must be reported. If the supervisor is interrupted, inspect actual player state before restarting or advancing an episode.

## Acceptance and evidence limits

Accept the intended season/episode/audio with observed playback and retained progress. Resume should preserve unfinished position and advance only after observed natural completion. Provider failure is not permission to bypass access controls, auto-update code or open an unrelated player/session.

## Source trail

Derived from the packaged [README](../../README.md), [manifest](../../plugin.yaml),
registered tool schemas and the tests listed in provenance.json. Existing
verification records describe their own dated scope; no new live capability
was inferred from this documentation review.
