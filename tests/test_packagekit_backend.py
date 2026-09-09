from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from packagekit_backend import InstallError, PackageKitBackend


def package(name='paint', info=2, origin='repo'):
    return NS(get_id=lambda: name+';1;amd64;'+origin, get_name=lambda: name, get_info=lambda: info)


class BackendTests(unittest.TestCase):
    def backend(self, changes=None, candidates=None):
        backend = PackageKitBackend.__new__(PackageKitBackend)
        backend.pk = NS(FilterEnum=NS(ARCH=18, NEWEST=16), InfoEnum=NS(INSTALLED=1, AVAILABLE=2, INSTALLING=3),
                        TransactionFlagEnum=NS(SIMULATE=2, ONLY_TRUSTED=1))
        backend.control = mock.Mock()
        backend.control.get_transaction_list.return_value = []
        backend.client = mock.Mock()
        backend._call = mock.Mock(side_effect=[
            NS(get_package_array=lambda: candidates if candidates is not None else [package()]),
            NS(get_package_array=lambda: changes if changes is not None else [package(info=3)]),
            NS(get_details_array=lambda: [NS(get_size=lambda: 100)])
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
        backend.install({'packageIds': ['paint;1;amd64;repo']}, mock.Mock())
        backend.client.set_interactive.assert_called_once_with(True)
        args = backend._call.call_args.args
        self.assertEqual(args[0], backend.client.install_packages)
        self.assertEqual(args[1:], (1 << 1, ['paint;1;amd64;repo']))
