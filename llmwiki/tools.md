---
status: SOURCE-DERIVED
curated: 2026-11-11
---
# Watch: tool reference

Exactly the 14 tools this plugin registers, in two groups. Each group's detailed
contract (side effects, acceptance limits) lives in its part's own file.
Derived from the registration code; no handler was executed. This is interface
evidence, not live capability testing.

## Anime part

Detailed contracts: [anime/llmwiki/tools.md](anime/llmwiki/tools.md).

- `anime_search`: Search anime titles through the pinned ani-cli provider. Show the actual matching titles and let the user select ambiguous seasons before playback. Inputs: `query` (required).
- `anime_episodes`: List currently available episode numbers for a previously selected anime title. Inputs: `identifier` (required).
- `anime_play`: Open one episode in local mpv on the Hermes host. Only use when the user asks to play; this opens a window and plays audio. Resolves a fresh stream and resumes five seconds before saved progress by default. Linux only in this version. Inputs: `identifier` (required), `episode` (required), `audio` (optional), `quality` (optional), `resume` (optional).
- `anime_status`: Report actual mpv playback state and saved position; a launched process is not yet confirmed playback. Inputs: `session_id` (required).
- `anime_control`: Pause, unpause, seek or stop ONLY a player session launched by this plugin. Inputs: `session_id` (required), `action` (required), `seconds` (optional).
- `anime_history`: List this Hermes profile's observed anime playback progress. Does not read ani-cli or another player's history. Inputs: none.
- `anime_resume`: Continue watching on the Hermes host in local mpv, resolving fresh media links. Advances to the next episode only after a recorded natural completion; otherwise resumes five seconds before the saved position. Only use when the user asks to continue playback. Inputs: `identifier` (optional), `quality` (optional).

## Movies and TV part

Detailed contracts: [movies/llmwiki/tools.md](movies/llmwiki/tools.md).

- `movies_search`: Search movie and TV titles through the installed Luffy bridge using your Hermes-managed TMDB API v3 key. Show title/year/kind and select the exact ID; never silently choose a remake or a different series. Inputs: `query` (required), `page` (optional), `kind` (optional).
- `movies_details`: Show a selected title and season/episode metadata using your Hermes-managed TMDB API v3 key when refresh is needed. Metadata does not prove stream availability. Cached for 24 hours unless refresh is requested. Inputs: `identifier` (required), `season` (optional), `refresh` (optional).
- `movies_play`: Play the selected movie or TV episode in local mpv on the Hermes host. Only use when the user requests playback; this opens a window and plays sound. Movies use season0/episode0. TV requires explicit season and episode. Preserves HLS master playlists and source headers. Linux development build. Inputs: `identifier` (required), `season` (optional), `episode` (optional), `source` (optional), `resume` (optional).
- `movies_status`: Read actual plugin-owned player status and observed progress. Inputs: `session_id` (required).
- `movies_control`: Pause, unpause, seek or stop only this plugin's own player session. Inputs: `session_id` (required), `action` (required), `seconds` (optional).
- `movies_history`: Show this profile's local movie/TV viewing history, with source and saved positions. Inputs: none.
- `movies_resume`: Continue a requested movie/TV session from observed progress using fresh links. An optional source change preserves the position. Advances TV after natural completion; completed movies require an explicit replay. Inputs: `identifier` (optional), `source` (optional).
