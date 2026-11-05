import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from package_install import PackageInstaller
from packagekit_backend import InstallError, PackageKitBackend, error_category
from package_provider import mapped_package

PLAN = {'installed': False, 'packageIds': ['paint;1;amd64;repo'],
        'changeIds': ['paint;1;amd64;+manual:repo'], 'packages': ['paint'], 'downloadBytes': 1024}
CATALOG = [{'id': 'paint', 'package': 'paint'}]


class Backend:
    provider = "apt"

    def catalog_package(self, recommendation):
        package = mapped_package(recommendation, self.provider)
        if package is None:
            raise InstallError("unsupported")
        return package

    def __init__(self):
        self.plan = copy.deepcopy(PLAN)
        self.calls = 0
        self.has_installed = False
        self.failure = None
        self.block = None

    def prepare(self, package, operation="install"):
        self.requested_package = package
        if self.block:
            self.block.wait(5)
        if self.failure:
            raise self.failure
        return copy.deepcopy(self.plan)

    def perform(self, operation, plan, progress, transaction=None):
        self.calls += 1
        self.operation = operation
        progress('waiting-for-auth', 101)
        progress('download', 40)
        self.has_installed = True

    def verify(self, package, operation, plan):
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

    def prepare(self, operation="install"):
        self.manager.prepare('paint', CATALOG, operation)
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

    def flatpak_manager(self):
        backend = Backend()
        backend.provider = 'flatpak'
        backend.catalog_package = lambda rec: {'id': 'org.tuxpaint.Tuxpaint'}
        backend.plan = {'installed': False, 'packages': ['app/org.tuxpaint.Tuxpaint/x86_64/stable'],
                        'downloadBytes': 123, 'operations': [{'commit': 'a'*64}],
                        'flatpak': {'permissions': ['Context.shared=ipc'], 'scope': 'user'}}
        manager = PackageInstaller(self.path, lambda: self.backend, flatpak_factory=lambda: backend)
        return manager, backend

    def test_flatpak_source_keeps_native_backend_out_and_requires_new_consent(self):
        manager, backend = self.flatpak_manager()
        manager.prepare('tuxpaint', [{'id':'tuxpaint','package':'tuxpaint'}], source='flatpak')
        manager.worker.join(5)
        ready = manager.snapshot()
        self.assertEqual(ready['source'], 'flatpak')
        self.assertEqual(ready['provider'], 'flatpak')
        self.assertEqual(ready['flatpak']['scope'], 'user')
        self.assertEqual(backend.calls, 0)
        self.assertEqual(self.backend.calls, 0)
        manager.start(ready['jobId'], ready['confirmationToken'])
        manager.worker.join(5)
        self.assertEqual(manager.snapshot()['status'], 'complete')
        self.assertEqual(backend.calls, 1)

    def test_flatpak_plan_change_does_not_execute_the_new_permissions(self):
        manager, backend = self.flatpak_manager()
        manager.prepare('tuxpaint', [{'id':'tuxpaint','package':'tuxpaint'}], source='flatpak')
        manager.worker.join(5)
        ready = manager.snapshot()
        backend.plan['flatpak']['permissions'].append('Context.shared=network')
        manager.start(ready['jobId'], ready['confirmationToken'])
        manager.worker.join(5)
        self.assertEqual(manager.snapshot()['error'], 'plan_changed')
        self.assertEqual(backend.calls, 0)

    def test_flatpak_restart_keeps_only_identity_and_never_replays_or_reattaches(self):
        self.path.parent.mkdir()
        self.path.write_text(json.dumps({'status':'installing','operation':'install',
            'source':'flatpak','provider':'flatpak','appId':'tuxpaint','jobId':'a'*32,'confirmationToken':'old'}))
        backend = Mock()
        manager = PackageInstaller(self.path, backend, flatpak_factory=backend)
        state = manager.snapshot()
        self.assertEqual((state['status'],state['source'],state['appId']), ('interrupted','flatpak','tuxpaint'))
        backend.assert_not_called()
        self.assertNotIn('confirmationToken', state)
        with self.assertRaises(InstallError): manager.start('a'*32, 'old')

    def test_invalid_or_unmapped_sources_do_not_start_any_backend(self):
        for source in ([], {}, 'shell', '--user'):
            with self.assertRaises(ValueError): self.manager.prepare('paint', CATALOG, source=source)
        with self.assertRaises(ValueError): self.manager.prepare('paint', CATALOG, source='flatpak')
        self.assertIsNone(self.manager.worker)

    def test_native_mapping_and_consent_stay_bound_to_the_detected_provider(self):
        catalog = [{"id": "paint", "package": "debian-paint", "packages": {"dnf": "fedora-paint", "pacman": "arch-paint"}}]
        self.backend.provider = "dnf"
        self.manager.prepare("paint", catalog)
        self.manager.worker.join(5)
        ready = self.manager.snapshot()
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["provider"], "dnf")
        self.assertEqual(self.backend.requested_package, "fedora-paint")
        self.assertEqual(json.loads(self.path.read_text())["provider"], "dnf")
        self.backend.provider = "pacman"
        self.manager.start(ready["jobId"], ready["confirmationToken"])
        self.manager.worker.join(5)
        self.assertEqual(self.manager.snapshot()["error"], "plan_changed")
        self.assertEqual(self.backend.calls, 0)

    def test_unmapped_native_package_never_falls_back_to_the_apt_name(self):
        self.backend.provider = "dnf"
        self.assertEqual(self.prepare()["error"], "unsupported")
        self.assertEqual(self.backend.calls, 0)
        self.assertFalse(hasattr(self.backend, "requested_package"))

    def test_restart_cannot_adopt_a_transaction_from_another_native_provider(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"jobId": "a" * 32, "appId": "paint", "operation": "install", "status": "installing",
                                         "transactionId": "/42_abc", "target": ["paint", "1", "amd64"], "provider": "dnf"}))
        self.backend.recover = Mock()
        restarted = PackageInstaller(self.path, lambda: self.backend)
        restarted.worker.join(5)
        self.assertEqual(restarted.snapshot()["status"], "interrupted")
        self.backend.recover.assert_not_called()

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
        self.assertEqual(set(journal), {'jobId', 'appId', 'operation', 'status', 'provider'})
        self.assertNotIn(ready['confirmationToken'], self.path.read_text())
        recovered = PackageInstaller(self.path, lambda: self.backend)
        self.assertEqual(recovered.snapshot()['status'], 'interrupted')
        self.assertEqual(recovered.snapshot()['operation'], 'install')
        self.assertIsNone(recovered.worker)
        with self.assertRaises(InstallError):
            recovered.start(ready['jobId'], ready['confirmationToken'])
        self.assertEqual(self.backend.calls, 0)
        if sys.platform != 'win32':
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_restart_monitors_only_the_recorded_transaction_and_keeps_job_busy(self):
        ready = self.prepare()
        started = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        def perform(operation, plan, progress, transaction):
            transaction("/42_abcdef")
            started.set()
            release.wait(5)

        with patch.object(self.backend, "perform", side_effect=perform):
            self.manager.start(ready["jobId"], ready["confirmationToken"])
            try:
                self.assertTrue(started.wait(5))
                record = json.loads(self.path.read_text())
                self.assertEqual(record["transactionId"], "/42_abcdef")
                self.assertEqual(record["target"], ["paint", "1", "amd64"])
                self.assertNotIn("transactionId", self.manager.snapshot())
                self.assertNotIn(ready["confirmationToken"], self.path.read_text())
            finally:
                release.set()
                self.manager.worker.join(5)

        # Restore the snapshot taken while the original process owned the transaction.
        self.path.write_text(json.dumps(record))
        observing = threading.Event()
        finish = threading.Event()
        self.addCleanup(finish.set)
        backend = Backend()

        def recover(transaction, operation, target, progress):
            self.assertEqual((transaction, operation, target), ("/42_abcdef", "install", ["paint", "1", "amd64"]))
            progress("download", 42)
            observing.set()
            return finish.wait(5)

        backend.recover = recover
        restarted = PackageInstaller(self.path, lambda: backend)
        try:
            self.assertTrue(observing.wait(5))
            snapshot = restarted.snapshot()
            self.assertEqual(snapshot["jobId"], ready["jobId"])
            self.assertEqual(snapshot["percent"], 42)
            self.assertTrue(snapshot["recovered"])
            self.assertNotIn("target", snapshot)
            with self.assertRaisesRegex(InstallError, "busy"):
                restarted.prepare("paint", CATALOG)
            with self.assertRaises(InstallError):
                restarted.start(ready["jobId"], ready["confirmationToken"])
        finally:
            finish.set()
            restarted.worker.join(5)
        self.assertEqual(restarted.snapshot()["status"], "complete")
        self.assertEqual(backend.calls, 0)
        self.assertNotIn("transactionId", json.loads(self.path.read_text()))

    def test_invalid_journal_or_missing_transaction_is_interrupted(self):
        self.path.parent.mkdir(parents=True)
        record = {"jobId": "a" * 32, "appId": "paint", "operation": "remove",
                  "status": "installing", "target": ["paint", "1", "amd64"]}
        backend = Backend()
        def unavailable(*args):
            raise InstallError("interrupted")
        backend.recover = unavailable
        for transaction in ("../../foreign", "/52_abcdef"):
            self.path.write_text(json.dumps(dict(record, transactionId=transaction)))
            restarted = PackageInstaller(self.path, lambda: backend)
            if restarted.worker:
                restarted.worker.join(5)
            self.assertEqual(restarted.snapshot()["status"], "interrupted")
            self.assertEqual(backend.calls, 0)

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
        self.backend.verify = lambda package, operation, plan: False
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

    def test_maintenance_consent_is_bound_to_operation_and_version(self):
        for operation in ("update", "remove"):
            with self.subTest(operation=operation):
                self.backend.plan = {**PLAN, "currentVersion": "1"}
                ready = self.prepare(operation)
                self.assertEqual(ready["operation"], operation)
                self.assertEqual(ready["currentVersion"], "1")
                with self.assertRaises(InstallError):
                    self.manager.start(ready["jobId"], ready["confirmationToken"], expected_operation="install")
                self.backend.plan["currentVersion"] = "2"
                self.manager.start(ready["jobId"], ready["confirmationToken"])
                self.manager.worker.join(5)
                self.assertEqual(self.manager.snapshot()["error"], "plan_changed")
                ready = self.prepare(operation)
                self.manager.start(ready["jobId"], ready["confirmationToken"])
                self.manager.worker.join(5)
                self.assertEqual(self.backend.operation, operation)
                self.assertEqual(self.manager.snapshot()["status"], "complete")
        for operation in ("purge", None, [], {"command": "remove"}):
            with self.assertRaises(ValueError):
                self.manager.prepare("paint", CATALOG, operation)



class RecoveryIdentityTests(unittest.TestCase):
    def test_foreign_role_uid_and_simulation_are_rejected(self):
        backend = PackageKitBackend.__new__(PackageKitBackend)
        backend.pk = Mock()
        backend.pk.RoleEnum.UPDATE_PACKAGES = 9
        backend.pk.TransactionFlagEnum.SIMULATE = 2
        backend.gio = Mock()
        backend.client = Mock()
        backend._transaction_properties = Mock()
        for uid, role, flags in ((2000, 9, 0), (1000, 3, 0), (1000, 9, 4)):
            with self.subTest(uid=uid, role=role, flags=flags):
                backend._transaction_properties.return_value = {
                    "Uid": uid, "Role": role, "TransactionFlags": flags,
                }
                with patch("packagekit_backend.os.getuid", return_value=1000, create=True):
                    with self.assertRaisesRegex(InstallError, "interrupted"):
                        backend.recover("/50_abc", "update", ["paint", "1", "amd64"], Mock())
        backend.client.get_old_transactions.assert_not_called()
