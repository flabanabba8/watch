import json
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from test_movies import ROOT
from movies_test.provider import Provider

class ProviderCredentialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/tmp')
        self.root=Path(self.tmp.name)
        self.bridge=self.root/'fixture-bridge'
        self.bridge.write_bytes(b'fixture executable')
        self.bridge.chmod(0o700)
        self.bridge_hash=hashlib.sha256(self.bridge.read_bytes()).hexdigest()
        self.provider=Provider(self.root,str(self.bridge),self.bridge_hash)
    def tearDown(self): self.tmp.cleanup()

    def test_metadata_key_only_through_private_stdin(self):
        key='fixture-'+'x'*24
        process=Mock(returncode=0)
        process.communicate.return_value=(b'{"items":[]}',None)
        with patch('agent.secret_scope.get_secret',return_value=key), patch('movies_test.provider.shutil.which',return_value=str(self.bridge)), patch('movies_test.provider.subprocess.Popen',return_value=process) as spawn:
            result=self.provider.call({'action':'search','query':'Example','page':1})
        sent=json.loads(process.communicate.call_args.args[0])
        self.assertEqual(sent['tmdb_key'],key)
        self.assertFalse(key in str(spawn.call_args))
        self.assertNotIn('TMDB_API_KEY',spawn.call_args.kwargs['env'])
        self.assertFalse(key in str(result))
        self.assertFalse(any(key.encode() in p.read_bytes() for p in self.root.iterdir() if p.is_file()))

    def test_metadata_key_does_not_cross_profile_scopes(self):
        from agent.secret_scope import set_multiplex_context, reset_multiplex_context, set_secret_scope, reset_secret_scope
        process=Mock(returncode=0)
        process.communicate.return_value=(b'{"items":[]}',None)
        mode=set_multiplex_context(True)
        try:
            with patch.dict(os.environ, {'TMDB_API_KEY':'other-profile-fixture-value'}), patch('movies_test.provider.shutil.which',return_value=str(self.bridge)), patch('movies_test.provider.subprocess.Popen',return_value=process):
                first=set_secret_scope({'TMDB_API_KEY':'fixture-'+'x'*24})
                try: self.provider.call({'action':'search','query':'Example','page':1})
                finally: reset_secret_scope(first)
                second=set_secret_scope({})
                try:
                    self.provider.call({'action':'search','query':'Example','page':1})
                    self.assertNotIn('tmdb_key',json.loads(process.communicate.call_args.args[0]))
                finally: reset_secret_scope(second)
        finally: reset_multiplex_context(mode)

    def test_keyless_bridge_error_names_the_missing_key(self):
        process=Mock(returncode=0)
        process.communicate.return_value=(b'{"error":"Configure a TMDB API v3 key in Hermes settings"}',None)
        with patch('agent.secret_scope.get_secret',return_value=''), patch('movies_test.provider.shutil.which',return_value=str(self.bridge)), patch('movies_test.provider.subprocess.Popen',return_value=process):
            with self.assertRaisesRegex(ValueError, 'no built-in TMDB key'):
                self.provider.call({'action':'search','query':'Example','page':1})
        self.assertNotIn('tmdb_key',json.loads(process.communicate.call_args.args[0]))

    def test_untrusted_bridge_cannot_receive_key(self):
        self.provider.bridge_sha256 = '0'*64
        with patch('agent.secret_scope.get_secret') as secret, patch('movies_test.provider.shutil.which',return_value=str(self.bridge)), patch('movies_test.provider.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'trusted SHA-256'):
                self.provider.call({'action':'search','query':'Example','page':1})
        secret.assert_not_called()
        spawn.assert_not_called()

    def test_bridge_copy_is_sealed_before_execution(self):
        from movies_test.provider import open_trusted_bridge
        fd = open_trusted_bridge(str(self.bridge), self.bridge_hash)
        try:
            with self.assertRaises(OSError): os.write(fd, b'change')
        finally:
            os.close(fd)

    def test_missing_key_still_searches_with_the_bridge_builtin_key(self):
        process=Mock(returncode=0)
        process.communicate.return_value=(b'{"items":[]}',None)
        with patch('agent.secret_scope.get_secret',return_value=''), patch('movies_test.provider.shutil.which',return_value=str(self.bridge)), patch('movies_test.provider.subprocess.Popen',return_value=process) as spawn:
            self.provider.call({'action':'search','query':'Example','page':1})
        spawn.assert_called_once()
        self.assertNotIn('tmdb_key',json.loads(process.communicate.call_args.args[0]))

    def test_malformed_optional_key_blocks_before_spawn(self):
        with patch('agent.secret_scope.get_secret',return_value='bad key!'), patch('movies_test.provider.shutil.which',return_value=str(self.bridge)), patch('movies_test.provider.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'not valid'):
                self.provider.call({'action':'search','query':'Example','page':1})
        spawn.assert_not_called()

    def test_stream_resolution_does_not_send_a_key(self):
        process=Mock(returncode=0)
        process.communicate.return_value=(b'{"streams":[]}',None)
        with patch('agent.secret_scope.get_secret') as secret, patch('movies_test.provider.shutil.which',return_value=str(self.bridge)), patch('movies_test.provider.subprocess.Popen',return_value=process):
            self.provider.call({'action':'streams','id':'movie-1'})
        secret.assert_not_called()
        self.assertNotIn('tmdb_key',json.loads(process.communicate.call_args.args[0]))

    def test_bad_credential_error_is_actionable_without_leak(self):
        key='fixture-'+'x'*24
        process=Mock(returncode=1)
        process.communicate.return_value=(b'{"error":"metadata returned HTTP 401"}',None)
        with patch('agent.secret_scope.get_secret',return_value=key), patch('movies_test.provider.shutil.which',return_value=str(self.bridge)), patch('movies_test.provider.subprocess.Popen',return_value=process):
            with self.assertRaisesRegex(RuntimeError,'authentication failed') as exc:
                self.provider.call({'action':'details','id':'movie-1'})
        self.assertFalse(key in str(exc.exception))

if __name__=='__main__': unittest.main()
