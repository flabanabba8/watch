"""Anime part of the Watch suite (tools anime_*)."""
import json
import sys
from .player import WatchAnime

IDENTIFIER = {'type': 'string', 'description': 'Exact title/season ID returned by anime_search.'}
QUALITY = {'type': 'string', 'enum': ['best', 'worst', '360', '480', '720', '1080']}
SESSION = {'type': 'string', 'description': 'Playback session ID returned by anime_play or anime_resume.'}
TOOLS = {
    'anime_search': ('Search anime titles through the pinned ani-cli provider. Show the actual matching titles and let the user select ambiguous seasons before playback.', {
        'query': {'type': 'string', 'minLength': 1, 'maxLength': 160}}, ['query']),
    'anime_episodes': ('List currently available episode numbers for a previously selected anime title.', {
        'identifier': IDENTIFIER}, ['identifier']),
    'anime_play': ('Open one episode in local mpv on the Hermes host. Only use when the user asks to play; this opens a window and plays audio. Resolves a fresh stream and resumes five seconds before saved progress by default. Linux only in this version.', {
        'identifier': IDENTIFIER, 'episode': {'type': 'string', 'description': 'Episode number as returned by anime_episodes.'},
        'audio': {'type': 'string', 'enum': ['sub', 'dub']}, 'quality': QUALITY,
        'resume': {'type': 'boolean'}}, ['identifier', 'episode']),
    'anime_status': ('Report actual mpv playback state and saved position; a launched process is not yet confirmed playback.', {
        'session_id': SESSION}, ['session_id']),
    'anime_control': ('Pause, unpause, seek or stop ONLY a player session launched by this plugin.', {
        'session_id': SESSION, 'action': {'type': 'string', 'enum': ['pause', 'unpause', 'seek', 'stop']},
        'seconds': {'type': 'number', 'minimum': 0, 'maximum': 28800}}, ['session_id', 'action']),
    'anime_history': ('List this Hermes profile\'s observed anime playback progress. Does not read ani-cli or another player\'s history.', {}, []),
    'anime_resume': ('Continue watching on the Hermes host in local mpv, resolving fresh media links. Advances to the next episode only after a recorded natural completion; otherwise resumes five seconds before the saved position. Only use when the user asks to continue playback.', {
        'identifier': IDENTIFIER, 'quality': QUALITY}, []),
}


def invoke(name, args):
    if sys.platform != 'linux':
        return json.dumps({'error': 'Watch Anime requires Linux in this development build', 'retry_automatically': False})
    from plugins.plugin_storage import plugin_data_dir
    try:
        data_dir = plugin_data_dir('watch') / 'anime'
        app = WatchAnime(data_dir)
        return json.dumps(getattr(app, name.removeprefix('anime_'))(**args))
    except (ValueError, TypeError, RuntimeError, OSError) as exc:
        return json.dumps({'error': str(exc), 'retry_automatically': False})


def register(ctx):
    if hasattr(ctx, 'register_skill'):
        from pathlib import Path
        ctx.register_skill('watch-anime', Path(__file__).parent / 'skills/watch-anime/SKILL.md', description='Use watch-anime with its bundled playback knowledge and current tool contracts')
    for name, (description, properties, required) in TOOLS.items():
        ctx.register_tool(name=name, toolset='watch_anime', schema={
            'name': name, 'description': description, 'parameters': {
                'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}},
            handler=lambda args, _name=name, **kwargs: invoke(_name, args))
