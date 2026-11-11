"""Movies and TV part of the Watch suite (tools movies_*)."""
import json
import sys
from .player import WatchMovies

IDENTIFIER = {'type': 'string', 'description': 'Exact movie-N or tv-N ID selected from movies_search.'}
SESSION = {'type': 'string', 'description': 'Playback session returned by movies_play/movies_resume.'}
SOURCE = {'type': 'string', 'enum': ['auto', 'cinejoy', 'vixsrc', 'lookmovie']}
TOOLS = {
    'movies_search': ('Search movie and TV titles through the installed Luffy bridge using your Hermes-managed TMDB API v3 key. Show title/year/kind and select the exact ID; never silently choose a remake or a different series.', {
        'query': {'type': 'string', 'minLength': 1, 'maxLength': 160}, 'page': {'type': 'integer', 'minimum': 1, 'maximum': 500},
        'kind': {'type': 'string', 'enum': ['all', 'movie', 'tv']}}, ['query']),
    'movies_details': ('Show a selected title and season/episode metadata using your Hermes-managed TMDB API v3 key when refresh is needed. Metadata does not prove stream availability. Cached for 24 hours unless refresh is requested.', {
        'identifier': IDENTIFIER, 'season': {'type': 'integer', 'minimum': 0}, 'refresh': {'type': 'boolean'}}, ['identifier']),
    'movies_play': ('Play the selected movie or TV episode in local mpv on the Hermes host. Only use when the user requests playback; this opens a window and plays sound. Movies use season0/episode0. TV requires explicit season and episode. Preserves HLS master playlists and source headers. Linux development build.', {
        'identifier': IDENTIFIER, 'season': {'type': 'integer', 'minimum': 0}, 'episode': {'type': 'integer', 'minimum': 0},
        'source': SOURCE, 'resume': {'type': 'boolean'}}, ['identifier']),
    'movies_status': ('Read actual plugin-owned player status and observed progress.', {'session_id': SESSION}, ['session_id']),
    'movies_control': ('Pause, unpause, seek or stop only this plugin\'s own player session.', {
        'session_id': SESSION, 'action': {'type': 'string', 'enum': ['pause', 'unpause', 'seek', 'stop']},
        'seconds': {'type': 'number', 'minimum': 0, 'maximum': 28800}}, ['session_id', 'action']),
    'movies_history': ('Show this profile\'s local movie/TV viewing history, with source and saved positions.', {}, []),
    'movies_resume': ('Continue a requested movie/TV session from observed progress using fresh links. An optional source change preserves the position. Advances TV after natural completion; completed movies require an explicit replay.', {
        'identifier': IDENTIFIER, 'source': SOURCE}, []),
}


def invoke(name, args, settings=None):
    if sys.platform != 'linux':
        return json.dumps({'error': 'Watch Movies requires Linux sealed executable support in this development build', 'retry_automatically': False})
    from plugins.plugin_storage import plugin_data_dir
    try:
        data_dir = plugin_data_dir('watch') / 'movies'
        app = WatchMovies(data_dir, settings=settings)
        return json.dumps(getattr(app, name.removeprefix('movies_'))(**args))
    except (ValueError, TypeError, RuntimeError, OSError) as exc:
        return json.dumps({'error': str(exc), 'retry_automatically': False})


def register(ctx):
    if hasattr(ctx, 'register_skill'):
        from pathlib import Path
        ctx.register_skill('watch-movies', Path(__file__).parent / 'skills/watch-movies/SKILL.md', description='Use watch-movies with its bundled playback knowledge and current tool contracts')
    def settings():
        keys = ('bridge_path', 'bridge_sha256')
        return {key: value for key in keys if (value := ctx.get_config(key)) is not None}
    for name, (description, properties, required) in TOOLS.items():
        ctx.register_tool(name=name, toolset='watch_movies', schema={'name': name, 'description': description,
            'parameters': {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}},
            handler=lambda args, _name=name, **kwargs: invoke(_name, args, settings()))
