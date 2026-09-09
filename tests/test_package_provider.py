from pathlib import Path
import shlex
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import package_provider


class PackageProviderTests(unittest.TestCase):
    def test_native_detection_uses_id_before_id_like_and_checks_the_tool(self):
        cases = (
            ({"ID": "ubuntu", "ID_LIKE": "debian"}, "apt"),
            ({"ID": "zorin", "ID_LIKE": "ubuntu debian"}, "apt"),
            ({"ID": "custom", "ID_LIKE": "arch"}, "pacman"),
            ({"ID": "fedora", "ID_LIKE": "debian"}, "dnf"),
            ({"ID": "opensuse-tumbleweed", "ID_LIKE": "suse"}, "zypper"),
            ({"ID": "unknown"}, None),
        )
        for release, expected in cases:
            with self.subTest(release=release):
                self.assertEqual(package_provider.detect_native_provider(
                    release, which=lambda name: "/usr/bin/" + name, immutable=False
                ), expected)
        self.assertIsNone(package_provider.detect_native_provider(
            {"ID": "fedora", "ID_LIKE": "debian"},
            which=lambda name: "/usr/bin/apt" if name == "apt" else None,
            immutable=False,
        ))

    def test_immutable_hosts_do_not_offer_native_transactions(self):
        for variant in ("silverblue", "kinoite", "microos"):
            self.assertIsNone(package_provider.detect_native_provider(
                {"ID": "fedora", "VARIANT_ID": variant}, which=lambda name: name,
                immutable=False,
            ))
        self.assertIsNone(package_provider.detect_native_provider(
            {"ID": "fedora"}, which=lambda name: name, immutable=True
        ))

    def test_os_release_is_parsed_as_data_and_supports_missing_etc_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "os-release"
            path.write_text('ID=custom\nID_LIKE="ubuntu debian"\nPRETTY_NAME="Ignored"\n', encoding="utf-8")
            self.assertEqual(package_provider.read_os_release([path.with_name("absent"), path]), {
                "ID": "custom", "ID_LIKE": "ubuntu debian"
            })
            path.write_text('ID="$(touch should-not-exist)"\n', encoding="utf-8")
            self.assertEqual(package_provider.read_os_release([path])["ID"], "$(touch should-not-exist)")
            self.assertIsNone(package_provider.detect_native_provider(
                package_provider.read_os_release([path]), which=lambda name: name,
                immutable=False,
            ))
            path.write_text('ID="unterminated\n', encoding="utf-8")
            self.assertEqual(package_provider.read_os_release([path]), {})
            path.write_bytes(b'ID=\xff')
            self.assertEqual(package_provider.read_os_release([path]), {})

    def test_plans_preserve_confirmation_and_use_explicit_native_mapping(self):
        recs = [{"package": "debian-name", "packages": {
            "apt": "debian-name", "dnf": "rpm-name", "zypper": "suse-name", "pacman": "arch-name"
        }}]
        expected = {
            "apt": ["sudo", "apt", "install", "--no-remove", "debian-name"],
            "dnf": ["sudo", "dnf", "install", "rpm-name"],
            "zypper": ["sudo", "zypper", "install", "suse-name"],
            "pacman": ["sudo", "pacman", "-S", "arch-name"],
        }
        for provider, argv in expected.items():
            with self.subTest(provider=provider):
                plan = package_provider.prepare_install("debian-name", recs, provider=provider)
                self.assertEqual(plan["status"], "manual")
                self.assertEqual(plan["argv"], argv)
                self.assertEqual(shlex.split(plan["command"]), argv)

    def test_legacy_names_are_not_assumed_to_work_on_other_distributions(self):
        recs = [{"package": "tuxpaint"}]
        self.assertEqual(package_provider.prepare_install("tuxpaint", recs, provider="apt")["status"], "manual")
        for provider in ("dnf", "pacman", "zypper", "unknown"):
            plan = package_provider.prepare_install("tuxpaint", recs, provider=provider)
            self.assertEqual(plan["status"], "unsupported")
            self.assertNotIn("command", plan)

    def test_untrusted_package_values_never_become_command_arguments(self):
        for package in (None, [], {}, True, 1, "", "-y", "foo-", "foo+", "foo bar", "foo;id", "$(id)", "https://example/a.rpm", "../file", "*", "a" * 129):
            with self.subTest(package=package), self.assertRaises(ValueError):
                package_provider.prepare_install(package, [{"package": package}], provider="apt")
        with self.assertRaises(ValueError):
            package_provider.prepare_install("unknown", [{"package": "tuxpaint"}], provider="apt")
        with self.assertRaises(ValueError):
            package_provider.prepare_install("tuxpaint", [{"package": "tuxpaint", "packages": {"dnf": "foo;id"}}], provider="dnf")

    def test_real_catalog_mapping_supports_kturtle_on_fedora_and_arch(self):
        import json
        catalog = json.loads((Path(__file__).resolve().parents[1] / "src" / "recommendations.json").read_text(encoding="utf-8"))
        for provider in ("dnf", "pacman"):
            self.assertEqual(package_provider.prepare_install("kturtle", catalog, provider=provider)["argv"][-1], "kturtle")
        # Tux Paint is in the AUR, not in Arch's supported binary repositories.
        self.assertEqual(package_provider.prepare_install("tuxpaint", catalog, provider="pacman")["status"], "unsupported")
