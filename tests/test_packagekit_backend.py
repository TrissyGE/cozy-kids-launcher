from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from packagekit_backend import InstallError, PackageKitBackend
from package_provider import NATIVE_PACKAGEKIT_PROFILES


def package(name='paint', info=2, origin='repo', version='1', arch='amd64'):
    return NS(get_id=lambda: f'{name};{version};{arch};{origin}', get_name=lambda: name, get_info=lambda: info)


class BackendTests(unittest.TestCase):
    def test_initialization_matches_the_distribution_to_its_actual_daemon_backend(self):
        for system, provider, daemon in (("ubuntu", "apt", "apt"), ("fedora", "dnf", "dnf5"),
                                         ("arch", "pacman", "alpm"), ("opensuse-tumbleweed", "zypper", "zypp")):
            for actual in (daemon, "foreign-backend"):
                with self.subTest(system=system, actual=actual):
                    control = mock.Mock(props=NS(backend_name=actual))
                    context = mock.Mock()
                    client = mock.Mock()
                    modules = {"gi": NS(require_version=lambda *_: None),
                               "gi.repository": NS(Gio=NS(), GLib=NS(MainContext=NS(new=lambda: context)),
                                                   PackageKitGlib=NS(Control=lambda: control, Client=lambda: client))}
                    with mock.patch.dict(sys.modules, modules), \
                            mock.patch("packagekit_backend.read_os_release", return_value={"ID": system}), \
                            mock.patch("packagekit_backend.detect_native_provider", return_value=provider):
                        if actual != daemon:
                            with self.assertRaisesRegex(InstallError, "unsupported"):
                                PackageKitBackend()
                            context.pop_thread_default.assert_called_once()
                        else:
                            backend = PackageKitBackend()
                            self.assertEqual(backend.provider, provider)
                            client.set_interactive.assert_called_once_with(False)
                            backend.close()

    def backend(self, changes=None, candidates=None):
        backend = PackageKitBackend.__new__(PackageKitBackend)
        backend.provider = "apt"
        backend.profile = NATIVE_PACKAGEKIT_PROFILES["apt"]
        backend.pk = NS(FilterEnum=NS(ARCH=18, NEWEST=16), InfoEnum=NS(
                            INSTALLED=1, AVAILABLE=2, INSTALLING=3, UPDATING=4, REMOVING=5, BLOCKED=6),
                        TransactionFlagEnum=NS(SIMULATE=2, ONLY_TRUSTED=1),
                        RoleEnum=NS(RESOLVE=1, GET_DETAILS=2, INSTALL_PACKAGES=3, UPDATE_PACKAGES=4, REMOVE_PACKAGES=5, GET_UPDATES=6))
        backend.control = mock.Mock()
        backend.control.props.roles = 127
        backend.control.props.backend_name = "apt"
        backend.control.get_transaction_list.return_value = []
        backend.client = mock.Mock()
        backend._call = mock.Mock(side_effect=[
            NS(get_package_array=lambda: candidates if candidates is not None else [package()]),
            NS(get_package_array=lambda: changes if changes is not None else [package(info=3)]),
            NS(get_details_array=lambda: [NS(props=NS(download_size=100), get_size=lambda: 1000)])
        ])
        return backend

    def test_prepare_is_only_simulation_with_trust_and_reports_download(self):
        backend = self.backend()
        plan = backend.prepare('paint')
        self.assertEqual(plan['downloadBytes'], 100)
        self.assertEqual(plan['packages'], ['paint'])
        call = backend._call.call_args_list[1]
        self.assertEqual(call.args[0], backend.client.install_packages)
        self.assertEqual(call.args[1], (1 << 2) | (1 << 1))
        backend.client.set_interactive.assert_not_called()

    def test_native_operation_policy_and_daemon_capabilities_fail_before_resolving(self):
        backend = self.backend()
        backend.control.props.roles = 0
        with self.assertRaisesRegex(InstallError, "unsupported"):
            backend.prepare("paint")
        backend._call.assert_not_called()
        backend.provider = "pacman"
        backend.profile = NATIVE_PACKAGEKIT_PROFILES["pacman"]
        with self.assertRaisesRegex(InstallError, "system_update_required"):
            backend.prepare("paint", "update")
        with self.assertRaisesRegex(InstallError, "system_update_required"):
            backend.perform("update", {}, mock.Mock())
        backend.client.set_interactive.assert_not_called()

    def test_unknown_download_sizes_do_not_reuse_installed_size(self):
        for size in (0, None, -1, True, "100"):
            with self.subTest(size=size):
                backend = self.backend()
                backend._call.side_effect = [
                    NS(get_package_array=lambda: [package()]),
                    NS(get_package_array=lambda: [package(info=3)]),
                    NS(get_details_array=lambda: [NS(props=NS(download_size=size), get_size=lambda: 999999)]),
                ]
                self.assertIsNone(backend.prepare("paint")["downloadBytes"])

    def test_arch_install_refuses_pending_system_updates_before_review_and_execution(self):
        backend = self.backend()
        backend.provider = "pacman"
        backend.profile = NATIVE_PACKAGEKIT_PROFILES["pacman"]
        backend._call.side_effect = None
        backend._call.return_value = NS(get_package_array=lambda: [package("system-library", version="2")])
        with self.assertRaisesRegex(InstallError, "system_update_required"):
            backend.prepare("paint")
        self.assertEqual(backend._call.call_args.args[0], backend.client.get_updates)
        with self.assertRaisesRegex(InstallError, "system_update_required"):
            backend.perform("install", {"packageIds": ["paint;1;amd64;repo"]}, mock.Mock())
        backend.client.set_interactive.assert_not_called()

    def test_rpm_maintenance_is_delegated_before_any_backend_transaction(self):
        for provider in ("dnf", "zypper"):
            backend = self.backend()
            backend.provider = provider
            backend.profile = NATIVE_PACKAGEKIT_PROFILES[provider]
            for operation in ("update", "remove"):
                with self.assertRaisesRegex(InstallError, "system_maintenance_required"):
                    backend.prepare("paint", operation)
                with self.assertRaisesRegex(InstallError, "system_maintenance_required"):
                    backend.perform(operation, {}, mock.Mock())
            backend._call.assert_not_called()
            backend.client.set_interactive.assert_not_called()

    def test_install_verification_requires_the_reviewed_version_and_architecture(self):
        backend = self.backend()
        plan = {"packageIds": ["paint;2;x86_64;repository"]}
        for version, arch in (("1", "x86_64"), ("2", "i686")):
            backend._resolve = mock.Mock(return_value=[package(info=1, version=version, arch=arch)])
            self.assertFalse(backend.verify("paint", "install", plan))
        backend._resolve = mock.Mock(return_value=[package(info=1, version="2", arch="x86_64", origin="installed")])
        self.assertTrue(backend.verify("paint", "install", plan))

    def test_removals_updates_ambiguity_and_missing_packages_fail_closed(self):
        for changes in ([], [package(info=4)], [package(info=5)], [package(info=3)] * 201):
            with self.subTest(changes=len(changes)), self.assertRaises(InstallError):
                self.backend(changes=changes).prepare('paint')
        for candidates in ([], [package('other')], [package(origin='one'), package(origin='two')]):
            with self.assertRaises(InstallError):
                self.backend(candidates=candidates).prepare('paint')

    def test_existing_install_and_another_transaction_do_not_start_any_action(self):
        backend = self.backend(candidates=[package(info=1)])
        self.assertTrue(backend.prepare('paint')['installed'])
        self.assertEqual(backend._call.call_count, 1)
        backend = self.backend()
        backend.control.get_transaction_list.return_value = ['/active']
        with self.assertRaises(InstallError) as raised:
            backend.prepare('paint')
        self.assertEqual(raised.exception.code, 'busy')
        backend._call.assert_not_called()

    def test_execution_uses_system_interaction_and_only_trusted_package_ids(self):
        backend = self.backend()
        backend._call = mock.Mock()
        backend.perform('install', {'packageIds': ['paint;1;amd64;repo']}, mock.Mock())
        backend.client.set_interactive.assert_called_once_with(True)
        args = backend._call.call_args.args
        self.assertEqual(args[0], backend.client.install_packages)
        self.assertEqual(args[1:], (1 << 1, ['paint;1;amd64;repo']))

    def test_removal_simulates_only_the_target_and_disables_dependency_removal(self):
        for changes in ([package(info=5)], [package(info=5), package("dependent", info=5)]):
            backend = self.backend(candidates=[package(info=1)], changes=changes)
            if len(changes) > 1:
                with self.assertRaisesRegex(InstallError, "changes_required"):
                    backend.prepare("paint", "remove")
                continue
            plan = backend.prepare("paint", "remove")
            self.assertIsNone(plan["downloadBytes"])
            self.assertEqual(plan["currentVersion"], "1")
            self.assertEqual(backend._call.call_args.args,
                             (backend.client.remove_packages, 1 << 2, ["paint;1;amd64;repo"], False, False))
            backend._call = mock.Mock()
            backend.perform("remove", plan, mock.Mock())
            self.assertEqual(backend._call.call_args.args,
                             (backend.client.remove_packages, 0, ["paint;1;amd64;repo"], False, False))
            backend._resolve = mock.Mock(return_value=[package(info=2)])
            self.assertTrue(backend.verify("paint", "remove", plan))
            backend._resolve.return_value = [package(info=1)]
            self.assertFalse(backend.verify("paint", "remove", plan))

    def test_update_checks_native_candidates_and_verifies_the_exact_version(self):
        backend = self.backend()
        backend._resolve = mock.Mock(return_value=[package(info=1)])
        backend._call.side_effect = [
            NS(get_package_array=lambda: [package(version="2"), package(version="3", arch="i386"),
                                          package("unrelated", version="9"), package(info=6, version="4")]),
            NS(get_package_array=lambda: [package(info=4, version="2")]),
            NS(get_details_array=lambda: [NS(props=NS(download_size=100), get_size=lambda: 1000)]),
        ]
        plan = backend.prepare("paint", "update")
        self.assertEqual(plan["currentVersion"], "1")
        self.assertEqual(plan["targetVersion"], "2")
        self.assertFalse(backend.verify("paint", "update", plan))
        backend._resolve.return_value = [package(info=1, version="2", origin="installed")]
        self.assertTrue(backend.verify("paint", "update", plan))
        backend._call = mock.Mock()
        backend.perform("update", plan, mock.Mock())
        self.assertEqual(backend._call.call_args.args,
                         (backend.client.update_packages, 1 << 1, ["paint;2;amd64;repo"]))
