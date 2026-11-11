import importlib.util
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('overridable_fixture',Path(__file__).parents[1]/'movies'/'native'/'make-key-overridable.py')
core=importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class OverridableTests(unittest.TestCase):
    def test_constant_becomes_variable_and_keeps_upstream_value(self):
        key='fixture-' + 'x'*24
        out=core.make_overridable('package core\nconst TMDB_API_KEY = "'+key+'"\n')
        self.assertIn('var TMDB_API_KEY = "'+key+'"',out)
        self.assertNotIn('const TMDB_API_KEY',out)

    def test_unexpected_upstream_declaration_fails_closed(self):
        for text in ('package core\n','package core\nconst TMDB_API_KEY = "a"\nconst TMDB_API_KEY = "b"\n'):
            with self.assertRaisesRegex(ValueError,'Unexpected'): core.make_overridable(text)

    def test_build_children_do_not_inherit_credentials(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp); binary = root/'bin'; binary.mkdir(); marker = root/'marker'
            fake_git = binary/'git'
            fake_git.write_text('#!/bin/sh\nif [ -n "${INWORLD_API_KEY:-}" ]; then printf leaked > '+shlex.quote(str(marker))+'; else printf absent > '+shlex.quote(str(marker))+'; fi\nexit 1\n')
            fake_git.chmod(0o700)
            script = Path(__file__).parents[1]/'movies'/'native'/'build-bridge.sh'
            env = {'PATH':str(binary)+os.pathsep+os.defpath, 'HOME':os.environ.get('HOME','/tmp'),
                   'TMPDIR':str(root), 'GO_BIN':'/bin/true', 'INWORLD_API_KEY':'fixture-only-value'}
            result = subprocess.run(['sh',str(script.resolve()),str(root/'output')],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(marker.read_text(),'absent')
            self.assertFalse(b'fixture-only-value' in result.stdout + result.stderr)

if __name__=='__main__': unittest.main()
