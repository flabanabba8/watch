---
status: SOURCE-DERIVED
curated: 2026-11-09
---
# Actual tool contracts

Derived by importing maintained source and recording registration schemas; no tool
handler was executed. This is interface evidence, not live capability testing.

## movies_search

Search movie and TV titles through the installed Luffy bridge using your Hermes-managed TMDB API v3 key. Show title/year/kind and select the exact ID; never silently choose a remake or a different series.

Inputs: `query` (required), `page` (optional), `kind` (optional).

## movies_details

Show a selected title and season/episode metadata using your Hermes-managed TMDB API v3 key when refresh is needed. Metadata does not prove stream availability. Cached for 24 hours unless refresh is requested.

Inputs: `identifier` (required), `season` (optional), `refresh` (optional).

## movies_play

Play the selected movie or TV episode in local mpv on the Hermes host. Only use when the user requests playback; this opens a window and plays sound. Movies use season0/episode0. TV requires explicit season and episode. Preserves HLS master playlists and source headers. Linux development build.

Inputs: `identifier` (required), `season` (optional), `episode` (optional), `source` (optional), `resume` (optional).

## movies_status

Read actual plugin-owned player status and observed progress.

Inputs: `session_id` (required).

## movies_control

Pause, unpause, seek or stop only this plugin's own player session.

Inputs: `session_id` (required), `action` (required), `seconds` (optional).

## movies_history

Show this profile's local movie/TV viewing history, with source and saved positions.

Inputs: none.

## movies_resume

Continue a requested movie/TV session from observed progress using fresh links. An optional source change preserves the position. Advances TV after natural completion; completed movies require an explicit replay.

Inputs: `identifier` (optional), `source` (optional).
