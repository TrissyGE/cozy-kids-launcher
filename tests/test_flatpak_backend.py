import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from flatpak_backend import FlatpakBackend
from flatpak_catalog import FLATHUB_URL, launch_command, recipe
from packagekit_backend import InstallError


class Metadata:
    def __init__(self, access=None):
        self.groups = access or {}
    def get_groups(self):
        return list(self.groups), len(self.groups)
    def get_keys(self, group):
        return list(self.groups[group]), len(self.groups[group])
    def get_value(self, group, key):
        return self.groups[group][key]
    def has_group(self, group):
        return group in self.groups
    def to_data(self):
        text = json.dumps(self.groups)
        return text, len(text)


class Operation:
    def __init__(self, ref='app/org.tuxpaint.Tuxpaint/x86_64/stable', access=None):
        self.ref, self.remote, self.commit, self.kind = ref, 'flathub', 'a'*64, 'install'
        self.metadata = Metadata(access)
    def get_ref(self): return self.ref
    def get_remote(self): return self.remote
    def get_commit(self): return self.commit
    def get_operation_type(self):
        class Kind(str):
            @property
            def value_nick(self): return str(self)
        return Kind(self.kind)
    def get_metadata(self): return self.metadata
    def get_download_size(self): return 123


class Aborted(Exception): pass


class Transaction:
    def __init__(self, operations):
        self.operations, self.handlers, self.installed = operations, {}, False
    def connect(self, signal, callback): self.handlers[signal] = callback
    def set_no_interaction(self, value): pass
    def set_disable_auto_pin(self, value): pass
    def add_install(self, *args): self.install_args = args
    def get_operations(self): return self.operations
    def run(self, _cancel):
        if not self.handlers['ready'](self): raise Aborted()
        self.installed = True


class FlatpakBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.backend = object.__new__(FlatpakBackend)
        self.backend.arch = 'x86_64'
        self.backend.context = None
        self.backend.installation = mock.Mock()
        self.backend.installation.get_path.return_value.get_path.return_value = self.temp.name
        self.backend.fp = types.SimpleNamespace(TransactionOperationType=types.SimpleNamespace(INSTALL='install', UPDATE='update'))
        self.value = recipe('tuxpaint')
        self.app = Operation(access={'Context': {'shared': 'ipc;', 'sockets':'x11;pulseaudio;'}})
        self.runtime = Operation('runtime/org.freedesktop.Platform/x86_64/25.08')
        self.tx = Transaction([self.runtime, self.app])

    def error(self, code, action):
        with self.assertRaises(InstallError) as error: action()
        self.assertEqual(error.exception.code, code)

    def test_plan_captures_exact_app_and_runtime_commits_and_permissions(self):
        plan = self.backend._resolved_plan(self.tx, self.value, 'flathub')
        self.assertEqual(plan['downloadBytes'], 246)
        self.assertEqual(len(plan['operations']), 2)
        self.assertEqual(plan['operations'][0]['commit'], 'a'*64)
        self.assertIn('Context.sockets=pulseaudio', plan['flatpak']['permissions'])
        self.assertEqual(plan['flatpak']['url'], FLATHUB_URL)

    def test_unreviewed_access_and_dependency_permissions_are_rejected(self):
        for target in (self.app, self.runtime):
            original = target.metadata
            target.metadata = Metadata({'Context': {'shared': 'network;'}})
            self.error('flatpak_permissions', lambda: self.backend._resolved_plan(self.tx, self.value, 'flathub'))
            target.metadata = original

    def test_other_apps_remotes_uninstalls_and_invalid_commits_are_rejected(self):
        for field, value in [('ref','app/org.example.Other/x86_64/stable'), ('remote','another'),
                             ('kind','uninstall'), ('commit','untrusted')]:
            original = getattr(self.app, field)
            setattr(self.app, field, value)
            self.error('changes_required', lambda: self.backend._resolved_plan(self.tx, self.value, 'flathub'))
            setattr(self.app, field, original)

    def test_extra_data_and_unknown_metadata_are_not_silently_installed(self):
        self.app.metadata = Metadata({'Extra Data': {'download':'https://example.com'}})
        self.error('unsupported', lambda: self.backend._resolved_plan(self.tx, self.value, 'flathub'))

    def test_runtime_update_binds_both_old_and_new_commits(self):
        self.runtime.kind = 'update'
        self.backend.fp.RefKind = types.SimpleNamespace(APP=0, RUNTIME=1)
        installed = self.backend.installation.get_installed_ref.return_value
        installed.get_commit.return_value = 'c'*64
        before = self.backend._resolved_plan(self.tx, self.value, 'flathub')
        self.assertEqual(before['flatpak']['runtimeUpdates'], [self.runtime.ref])
        installed.get_commit.return_value = 'd'*64
        self.assertNotEqual(before, self.backend._resolved_plan(self.tx, self.value, 'flathub'))

    def test_trust_requires_one_enabled_gpg_verified_official_remote(self):
        remote = mock.Mock()
        remote.get_name.return_value = 'flathub'
        remote.get_url.return_value = FLATHUB_URL
        remote.get_gpg_verify.return_value = True
        remote.get_disabled.return_value = False
        self.backend.installation.list_remotes.return_value = [remote]
        self.assertEqual(self.backend.trusted_remote(), 'flathub')
        for method, value in [('get_url','https://example.com/repo/'), ('get_gpg_verify',False), ('get_disabled',True)]:
            previous = getattr(remote, method).return_value
            getattr(remote, method).return_value = value
            self.error('flatpak_setup', self.backend.trusted_remote)
            getattr(remote, method).return_value = previous
        self.backend.installation.list_remotes.return_value = [remote, remote]
        self.error('flatpak_setup', self.backend.trusted_remote)

    def test_overrides_are_refused_without_rewriting_them(self):
        root = Path(self.temp.name) / 'overrides'
        root.mkdir()
        self.backend.check_overrides(self.value)
        for name in ('global', self.value['id']):
            path = root / name
            path.write_text('[Context]\nshared=network;\n')
            self.error('flatpak_overrides', lambda: self.backend.check_overrides(self.value))
            self.assertIn('network', path.read_text())
            path.unlink()

    def test_preview_aborts_before_changes_and_execution_rechecks_the_entire_plan(self):
        self.backend.trusted_remote = mock.Mock(return_value='flathub')
        self.backend.fp.Transaction = types.SimpleNamespace(new_for_installation=lambda *_: self.tx)
        self.backend.glib = types.SimpleNamespace(Error=Aborted)
        self.backend.gio = types.SimpleNamespace(Cancellable=mock.Mock)
        plan = self.backend._transaction(self.value)
        self.assertFalse(self.tx.installed)
        self.assertFalse(self.tx.handlers['add-new-remote']())
        self.assertFalse(self.tx.handlers['end-of-lifed-with-rebase']())
        self.backend._transaction(self.value, expected=plan)
        self.assertTrue(self.tx.installed)
        self.tx.installed = False
        self.runtime.commit = 'b'*64
        self.error('plan_changed', lambda: self.backend._transaction(self.value, expected=plan))
        self.assertFalse(self.tx.installed)

    def test_launch_recipe_preserves_explicit_scope_architecture_branch_and_fullscreen(self):
        argv = launch_command(self.value, 'x86_64')
        self.assertEqual(argv, ['flatpak','run','--user','--arch=x86_64','--branch=stable',
                                'org.tuxpaint.Tuxpaint','--fullscreen=yes'])
        with self.assertRaises(ValueError): launch_command(self.value, '--system')


if __name__ == '__main__': unittest.main()
