"""PIN authentication, throttling, and parent-session state."""

import hashlib
import hmac
import re
import secrets
import threading
import time
from http.cookies import SimpleCookie


ADMIN_SESSION_TTL_SECONDS = 30 * 60
PIN_FAILURE_WINDOW_SECONDS = 60
PIN_FAILURE_LIMIT = 5
PIN_KDF_ITERATIONS = 200_000
ADMIN_COOKIE_NAME = "cozy_admin"

_admin_sessions = {}
_admin_sessions_lock = threading.Lock()
_pin_failures = []
_pin_failures_lock = threading.Lock()


def is_legacy_pin_hash(pin_hash):
    return isinstance(pin_hash, str) and bool(
        re.fullmatch(r"[0-9a-f]{16}", pin_hash)
    )


def is_supported_pin_hash(pin_hash):
    if not isinstance(pin_hash, str):
        return False
    if is_legacy_pin_hash(pin_hash):
        return True
    parts = pin_hash.split("$")
    return (
        len(parts) == 4
        and parts[0] == "pbkdf2_sha256"
        and parts[1].isdigit()
        and 50_000 <= int(parts[1]) <= 1_000_000
        and bool(re.fullmatch(r"[0-9a-f]{32}", parts[2]))
        and bool(re.fullmatch(r"[0-9a-f]{64}", parts[3]))
    )


def hash_pin(pin, salt=None):
    if not isinstance(pin, str) or not re.fullmatch(r"\d{4,6}", pin):
        raise ValueError("PIN must contain 4 to 6 digits")
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        bytes.fromhex(salt),
        PIN_KDF_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PIN_KDF_ITERATIONS}${salt}${digest}"


def verify_pin(pin_hash, pin):
    if not pin_hash or not pin:
        return False
    if is_legacy_pin_hash(pin_hash):
        computed = hashlib.sha256(pin.encode("utf-8")).hexdigest()[:16]
        return hmac.compare_digest(computed, pin_hash)
    if not is_supported_pin_hash(pin_hash):
        return False
    _, iterations, salt, expected = pin_hash.split("$")
    computed = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        bytes.fromhex(salt),
        int(iterations),
    ).hex()
    return hmac.compare_digest(computed, expected)


def create_admin_session(now=None):
    now = time.time() if now is None else now
    token = secrets.token_urlsafe(32)
    with _admin_sessions_lock:
        expired = [key for key, expiry in _admin_sessions.items() if expiry <= now]
        for key in expired:
            _admin_sessions.pop(key, None)
        _admin_sessions[token] = now + ADMIN_SESSION_TTL_SECONDS
    return token


def clear_admin_sessions():
    with _admin_sessions_lock:
        _admin_sessions.clear()


def valid_admin_session(cookie_header, now=None):
    if not cookie_header:
        return False
    try:
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get(ADMIN_COOKIE_NAME)
        token = morsel.value if morsel else ""
    except Exception:
        return False
    if not token:
        return False
    now = time.time() if now is None else now
    with _admin_sessions_lock:
        expiry = _admin_sessions.get(token, 0)
        if expiry <= now:
            _admin_sessions.pop(token, None)
            return False
        _admin_sessions[token] = now + ADMIN_SESSION_TTL_SECONDS
    return True


def admin_session_cookie(token):
    return (
        f"{ADMIN_COOKIE_NAME}={token}; Path=/; HttpOnly; "
        f"SameSite=Strict; Max-Age={ADMIN_SESSION_TTL_SECONDS}"
    )


def expired_admin_session_cookie():
    return (
        f"{ADMIN_COOKIE_NAME}=; Path=/; HttpOnly; "
        "SameSite=Strict; Max-Age=0"
    )


def pin_attempt_blocked(now=None):
    now = time.time() if now is None else now
    cutoff = now - PIN_FAILURE_WINDOW_SECONDS
    with _pin_failures_lock:
        _pin_failures[:] = [stamp for stamp in _pin_failures if stamp > cutoff]
        return len(_pin_failures) >= PIN_FAILURE_LIMIT


def record_pin_failure(now=None):
    now = time.time() if now is None else now
    with _pin_failures_lock:
        _pin_failures.append(now)


def clear_pin_failures():
    with _pin_failures_lock:
        _pin_failures.clear()
