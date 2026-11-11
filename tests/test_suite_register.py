import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('watch_suite_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)


class Ctx:
    def __init__(self):
        self.tools, self.skills, self.hooks, self.commands, self.middleware, self.other = {}, {}, [], [], [], []

    def register_tool(self, name, **kw): self.tools[name] = kw
    def register_skill(self, name, path, **kw): self.skills[name] = path
    def register_hook(self, *a, **kw): self.hooks.append(a)
    def register_command(self, *a, **kw): self.commands.append(a)
    def register_middleware(self, *a, **kw): self.middleware.append(a)
    def get_config(self, key): return None


def declared_tools():
    out, on = [], False
    for line in (ROOT / 'plugin.yaml').read_text().splitlines():
        if line.startswith('provides_tools:'): on = True
        elif on and line.startswith('  - '): out.append(line[4:].strip())
        elif on: break
    return out


class SuiteRegistration(unittest.TestCase):
    def test_register_exposes_exactly_the_declared_tools_and_no_hooks(self):
        ctx = Ctx()
        package.register(ctx)
        declared = declared_tools()
        self.assertEqual(14, len(declared))
        self.assertEqual(sorted(declared), sorted(ctx.tools))
        self.assertEqual([], ctx.hooks + ctx.commands + ctx.middleware)
        self.assertEqual({'watch-anime', 'watch-movies'}, set(ctx.skills))
        for path in ctx.skills.values():
            self.assertTrue(Path(path).is_file(), path)
        self.assertEqual({'watch_anime', 'watch_movies'}, {t['toolset'] for t in ctx.tools.values()})

    def test_wiki_tool_reference_lists_exactly_the_registered_tools(self):
        import re
        ctx = Ctx(); package.register(ctx)
        text = (ROOT / 'llmwiki' / 'tools.md').read_text()
        listed = re.findall(r'^- `((?:anime|movies)_[a-z]+)`', text, re.M)
        self.assertEqual(sorted(ctx.tools), sorted(listed))

    def test_parts_store_data_separately_under_the_suite_folder(self):
        import tempfile, os, json
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {'HERMES_HOME': home}):
            for tool in ('anime_history', 'movies_history'):
                ctx = Ctx(); package.register(ctx)
                json.loads(ctx.tools[tool]['handler']({}))
            base = Path(home) / 'plugin-data' / 'watch'
            self.assertTrue((base / 'anime').is_dir())
            self.assertTrue((base / 'movies').is_dir())
            self.assertFalse((Path(home) / 'plugin-data' / 'watch-anime').exists())


if __name__ == '__main__':
    unittest.main()
