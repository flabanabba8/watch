---
status: SOURCE-DERIVED
curated: 2026-11-09
---
# Actual tool contracts

Derived by importing maintained source and recording registration schemas; no tool
handler was executed. This is interface evidence, not live capability testing.

## anime_search

Search anime titles through the pinned ani-cli provider. Show the actual matching titles and let the user select ambiguous seasons before playback.

Inputs: `query` (required).

## anime_episodes

List currently available episode numbers for a previously selected anime title.

Inputs: `identifier` (required).

## anime_play

Open one episode in local mpv on the Hermes host. Only use when the user asks to play; this opens a window and plays audio. Resolves a fresh stream and resumes five seconds before saved progress by default. Linux only in this version.

Inputs: `identifier` (required), `episode` (required), `audio` (optional), `quality` (optional), `resume` (optional).

## anime_status

Report actual mpv playback state and saved position; a launched process is not yet confirmed playback.

Inputs: `session_id` (required).

## anime_control

Pause, unpause, seek or stop ONLY a player session launched by this plugin.

Inputs: `session_id` (required), `action` (required), `seconds` (optional).

## anime_history

List this Hermes profile's observed anime playback progress. Does not read ani-cli or another player's history.

Inputs: none.

## anime_resume

Continue watching on the Hermes host in local mpv, resolving fresh media links. Advances to the next episode only after a recorded natural completion; otherwise resumes five seconds before the saved position. Only use when the user asks to continue playback.

Inputs: `identifier` (optional), `quality` (optional).
