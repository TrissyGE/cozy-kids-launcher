import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from package_install import PackageInstaller
from packagekit_backend import InstallError, error_category

PLAN = {'installed': False, 'packageIds': ['paint;1;amd64;repo'],
        'changeIds': ['paint;1;amd64;+manual:repo'], 'packages': ['paint'], 'downloadBytes': 1024}
CATALOG = [{'id': 'paint', 'package': 'paint'}]


class Backend:
    def __init__(self):
        self.plan = copy.deepcopy(PLAN)
        self.calls = 0
        self.has_installed = False
        self.failure = None
        self.block = None

    def prepare(self, package):
        if self.block:
            self.block.wait(5)
        if self.failure:
            raise self.failure
        return copy.deepcopy(self.plan)

    def install(self, plan, progress):
        self.calls += 1
        progress('waiting-for-auth', 101)
        progress('download', 40)
        self.has_installed = True

    def installed(self, package):
        return self.has_installed

    def close(self):
        pass


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.backend = Backend()
        self.path = Path(self.temp.name) / 'state' / 'package-install.json'
        self.manager = PackageInstaller(self.path, lambda: self.backend)

    def prepare(self):
        self.manager.prepare('paint', CATALOG)
        self.manager.worker.join(5)
        self.assertFalse(self.manager.worker.is_alive())
        return self.manager.snapshot()

    def test_prepare_never_installs_and_requires_exact_single_use_consent(self):
        ready = self.prepare()
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(self.backend.calls, 0)
        self.assertEqual(ready['downloadBytes'], 1024)
        for job, token in [('forged', ready['confirmationToken']), (ready['jobId'], 'forged'), ([], {})]:
            with self.assertRaises(InstallError):
                self.manager.start(job, token)
        self.manager.start(ready['jobId'], ready['confirmationToken'])
        self.manager.worker.join(5)
        self.assertEqual(self.backend.calls, 1)
        self.assertEqual(self.manager.snapshot()['status'], 'complete')
        with self.assertRaises(InstallError):
            self.manager.start(ready['jobId'], ready['confirmationToken'])
        self.assertNotIn('confirmationToken', self.manager.snapshot())

    def test_changed_or_expired_plan_never_installs(self):
        ready = self.prepare()
        self.backend.plan['changeIds'] = ['different dependency']
        self.manager.start(ready['jobId'], ready['confirmationToken'])
        self.manager.worker.join(5)
        self.assertEqual(self.manager.snapshot()['error'], 'plan_changed')
        self.assertEqual(self.backend.calls, 0)
        ready = self.prepare()
        self.manager.clock = lambda: self.manager.expires + 1
        with self.assertRaises(InstallError):
            self.manager.start(ready['jobId'], ready['confirmationToken'])
        self.assertEqual(self.backend.calls, 0)

    def test_busy_jobs_and_invalid_app_values_are_rejected(self):
        for value in (None, {}, [], True, 'unknown', 'paint;id'):
            with self.assertRaises(ValueError):
                self.manager.prepare(value, CATALOG)
        self.backend.block = threading.Event()
        self.manager.prepare('paint', CATALOG)
        try:
            with self.assertRaises(InstallError) as raised:
                self.manager.prepare('paint', CATALOG)
            self.assertEqual(raised.exception.code, 'busy')
        finally:
            self.backend.block.set()
            self.manager.worker.join(5)

    def test_restart_never_replays_and_journal_excludes_plans_and_consent(self):
        ready = self.prepare()
        journal = json.loads(self.path.read_text())
        self.assertEqual(set(journal), {'jobId', 'appId', 'status'})
        self.assertNotIn(ready['confirmationToken'], self.path.read_text())
        recovered = PackageInstaller(self.path, lambda: self.backend)
        self.assertEqual(recovered.snapshot()['status'], 'interrupted')
        self.assertIsNone(recovered.worker)
        with self.assertRaises(InstallError):
            recovered.start(ready['jobId'], ready['confirmationToken'])
        self.assertEqual(self.backend.calls, 0)
        if sys.platform != 'win32':
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_installed_and_error_states_do_not_claim_a_new_installation(self):
        self.backend.plan = {'installed': True}
        self.assertEqual(self.prepare()['status'], 'complete')
        self.assertEqual(self.backend.calls, 0)
        for code in ('authorization', 'network', 'busy', 'unavailable'):
            self.backend.failure = InstallError(code)
            self.assertEqual(self.prepare()['error'], code)
        self.backend.failure = RuntimeError('private paths or backend details')
        self.assertEqual(self.prepare()['error'], 'failed')
        self.assertNotIn('private', json.dumps(self.manager.snapshot()))

    def test_backend_success_is_verified_and_unknown_percent_is_not_101(self):
        ready = self.prepare()
        self.backend.installed = lambda package: False
        self.manager.start(ready['jobId'], ready['confirmationToken'])
        self.manager.worker.join(5)
        self.assertEqual(self.manager.snapshot()['status'], 'error')
        self.manager._progress('waiting-for-auth', 101)
        self.assertIsNone(self.manager.snapshot()['percent'])
        self.assertEqual(self.manager.snapshot()['phase'], 'authorization')

    def test_error_categories_are_safe_and_actionable(self):
        for source, expected in [('no-network', 'network'), ('not-authorized', 'authorization'),
                                 ('cannot-get-lock', 'busy'), ('package-not-found', 'not_found')]:
            self.assertEqual(error_category(source), expected)

    def test_storage_failure_never_starts_or_reuses_consent(self):
        with patch.object(self.manager, '_persist', side_effect=OSError('private path')):
            with self.assertRaises(InstallError) as raised:
                self.manager.prepare('paint', CATALOG)
            self.assertEqual(raised.exception.code, 'storage')
            self.assertIsNone(self.manager.worker)
        for expired in (False, True):
            ready = self.prepare()
            if expired:
                self.manager.clock = lambda: self.manager.expires + 1
            with patch.object(self.manager, '_persist', side_effect=OSError('private path')):
                with self.assertRaises(InstallError) as raised:
                    self.manager.start(ready['jobId'], ready['confirmationToken'])
                self.assertEqual(raised.exception.code, 'storage')
            self.assertIsNone(self.manager.token)
            self.assertEqual(self.manager.snapshot()['error'], 'storage')
            self.assertEqual(self.backend.calls, 0)
