"""Watch: stream anime, movies and TV on demand and resume where you stopped.

One Hermes plugin that registers two parts, unchanged in behaviour:
  anime  - anime_* tools (ani-cli provider, local mpv)
  movies - movies_* tools (TMDB search, Luffy bridge, local mpv)
Each part keeps its own tool names, skill and stored data (under the suite's
plugin-data folder, in separate "anime" and "movies" subfolders).
"""
from . import anime, movies


def register(ctx):
    anime.register(ctx)
    movies.register(ctx)
