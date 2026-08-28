import hashlib
import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import parent_auth


class PinAuthenticationTests(unittest.TestCase):
    def test_pbkdf2_and_legacy_pin_hashes_remain_supported(self):
        pin_hash = parent_auth.hash_pin("1234", salt="00" * 16)
        legacy_hash = hashlib.sha256(b"1234").hexdigest()[:16]

        self.assertTrue(parent_auth.is_supported_pin_hash(pin_hash))
        self.assertTrue(parent_auth.verify_pin(pin_hash, "1234"))
        self.assertFalse(parent_auth.verify_pin(pin_hash, "9999"))
        self.assertTrue(parent_auth.is_legacy_pin_hash(legacy_hash))
        self.assertTrue(parent_auth.verify_pin(legacy_hash, "1234"))
        self.assertFalse(parent_auth.verify_pin(legacy_hash, "9999"))

    def test_pin_format_and_hash_format_validation_stay_bounded(self):
        for pin in ("123", "1234567", "12ab", 1234):
            with self.subTest(pin=pin):
                with self.assertRaisesRegex(ValueError, "4 to 6 digits"):
                    parent_auth.hash_pin(pin)

        for pin_hash in (
            None,
            "pbkdf2_sha256$49999$" + "00" * 16 + "$" + "00" * 32,
            "pbkdf2_sha256$200000$short$" + "00" * 32,
            "not-a-supported-hash",
        ):
            with self.subTest(pin_hash=pin_hash):
                self.assertFalse(parent_auth.is_supported_pin_hash(pin_hash))


class ParentSessionTests(unittest.TestCase):
    def setUp(self):
        parent_auth.clear_admin_sessions()
        parent_auth.clear_pin_failures()

    def tearDown(self):
        parent_auth.clear_admin_sessions()
        parent_auth.clear_pin_failures()

    def test_session_cookie_keeps_security_attributes_and_sliding_ttl(self):
        start = 100.0
        token = parent_auth.create_admin_session(now=start)
        cookie = parent_auth.admin_session_cookie(token)

        self.assertEqual(
            cookie,
            f"cozy_admin={token}; Path=/; HttpOnly; SameSite=Strict; "
            f"Max-Age={parent_auth.ADMIN_SESSION_TTL_SECONDS}",
        )
        first_refresh = start + parent_auth.ADMIN_SESSION_TTL_SECONDS - 1
        self.assertTrue(parent_auth.valid_admin_session(cookie, now=first_refresh))
        second_refresh = start + parent_auth.ADMIN_SESSION_TTL_SECONDS + 1
        self.assertTrue(
            parent_auth.valid_admin_session(
                cookie,
                now=second_refresh,
            )
        )
        self.assertFalse(
            parent_auth.valid_admin_session(
                cookie,
                now=second_refresh + parent_auth.ADMIN_SESSION_TTL_SECONDS,
            )
        )

    def test_unknown_expired_and_cleared_sessions_are_rejected(self):
        self.assertFalse(parent_auth.valid_admin_session(""))
        self.assertFalse(parent_auth.valid_admin_session("unrelated=value"))
        self.assertFalse(
            parent_auth.valid_admin_session("cozy_admin=unknown", now=100.0)
        )

        token = parent_auth.create_admin_session(now=100.0)
        cookie = f"cozy_admin={token}"
        self.assertFalse(
            parent_auth.valid_admin_session(
                cookie,
                now=100.0 + parent_auth.ADMIN_SESSION_TTL_SECONDS,
            )
        )

        token = parent_auth.create_admin_session(now=200.0)
        parent_auth.clear_admin_sessions()
        self.assertFalse(
            parent_auth.valid_admin_session(f"cozy_admin={token}", now=200.0)
        )

    def test_expired_cookie_matches_the_existing_browser_contract(self):
        self.assertEqual(
            parent_auth.expired_admin_session_cookie(),
            "cozy_admin=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0",
        )

    def test_pin_failures_are_shared_and_expire_after_the_window(self):
        start = 100.0
        for offset in range(parent_auth.PIN_FAILURE_LIMIT):
            parent_auth.record_pin_failure(now=start + offset)

        self.assertTrue(
            parent_auth.pin_attempt_blocked(
                now=start + parent_auth.PIN_FAILURE_LIMIT,
            )
        )
        self.assertFalse(
            parent_auth.pin_attempt_blocked(
                now=start
                + parent_auth.PIN_FAILURE_WINDOW_SECONDS
                + parent_auth.PIN_FAILURE_LIMIT,
            )
        )
