"""User-installation Flatpak transactions with exact, reviewed ready plans."""

import hashlib
import re
import stat
import threading

from flatpak_catalog import COMMIT, FLATHUB_URL, REF, recipe
from packagekit_backend import InstallError, error_category


def permissions(metadata):
    """Flatten declared sandbox access, including unknown future context keys."""
    result = []
    for group in metadata.get_groups()[0]:
        if group not in {"Context", "Session Bus Policy", "System Bus Policy"}:
            continue
        for key in metadata.get_keys(group)[0]:
            value = metadata.get_value(group, key)
            entries = value.split(";") if group == "Context" else [value]
            result.extend(f"{group}.{key}={entry}" for entry in entries if entry)
    if len(result) > 200 or any(len(value) > 500 or "\0" in value for value in result):
        raise InstallError("unsupported")
    return sorted(set(result))


class FlatpakBackend:
    provider = "flatpak"

    def __init__(self):
        self.context = None
        try:
            import gi
            gi.require_version("Flatpak", "1.0")
            from gi.repository import Flatpak, Gio, GLib
            self.fp, self.gio, self.glib = Flatpak, Gio, GLib
            self.context = GLib.MainContext.new()
            self.context.push_thread_default()
            self.installation = Flatpak.Installation.new_user(None)
            self.installation.set_no_interaction(True)
            self.arch = Flatpak.get_default_arch()
        except Exception:
            self.close()
            raise InstallError("flatpak_setup") from None

    def close(self):
        if self.context is not None:
            self.context.pop_thread_default()
            self.context = None

    def catalog_package(self, recommendation):
        value = recipe(recommendation.get("id"))
        if value is None:
            raise InstallError("unsupported")
        return value

    def trusted_remote(self):
        remotes = [remote for remote in self.installation.list_remotes(None)
                   if remote.get_url() == FLATHUB_URL and remote.get_gpg_verify() and not remote.get_disabled()]
        if len(remotes) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", remotes[0].get_name()):
            raise InstallError("flatpak_setup")
        return remotes[0].get_name()

    def check_overrides(self, value):
        # User apps load user global/app overrides, not system overrides (1.14.6
        # flatpak_dir_load_deployed). Keep existing overrides untouched and fail
        # closed rather than presenting manifest access as effective access.
        root = self.installation.get_path().get_path()
        from pathlib import Path
        for name in ("global", value["id"]):
            path = Path(root) / "overrides" / name
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            except OSError:
                raise InstallError("flatpak_overrides") from None
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                raise InstallError("flatpak_overrides")
            try:
                with path.open("rb") as stream:
                    if stream.read(65537).strip():
                        raise InstallError("flatpak_overrides")
            except OSError:
                raise InstallError("flatpak_overrides") from None

    def installed(self, value):
        self.check_overrides(value)
        try:
            installed = self.installation.get_installed_ref(self.fp.RefKind.APP, value["id"], self.arch, value["branch"], None)
        except self.glib.Error as error:
            if error.matches(self.fp.error_quark(), self.fp.Error.NOT_INSTALLED):
                return None
            raise InstallError("unavailable") from None
        if installed.get_origin() != self.trusted_remote():
            raise InstallError("flatpak_origin")
        raw = installed.load_metadata(None)
        raw = raw.get_data() if hasattr(raw, "get_data") else raw
        if not isinstance(raw, bytes) or len(raw) > 65536:
            raise InstallError("unsupported")
        metadata = self.glib.KeyFile()
        metadata.load_from_data(raw.decode("utf-8"), len(raw), self.glib.KeyFileFlags.NONE)
        if not set(permissions(metadata)).issubset(value["permissions"]):
            raise InstallError("flatpak_permissions")
        return installed

    def _resolved_plan(self, tx, value, remote):
        operations = tx.get_operations()
        if not 1 <= len(operations) <= 100:
            raise InstallError("unsupported")
        resolved = []
        app_ref = f"app/{value['id']}/{self.arch}/{value['branch']}"
        app_permissions = None
        for operation in operations:
            ref, commit = operation.get_ref(), operation.get_commit()
            if (not REF.fullmatch(ref) or not COMMIT.fullmatch(commit or "")
                    or operation.get_remote() != remote
                    or operation.get_operation_type() not in {self.fp.TransactionOperationType.INSTALL, self.fp.TransactionOperationType.UPDATE}
                    or (ref.startswith("app/") and ref != app_ref)):
                raise InstallError("changes_required")
            metadata = operation.get_metadata()
            if metadata is None or metadata.has_group("Extra Data"):
                raise InstallError("unsupported")
            data = metadata.to_data()[0]
            if len(data) > 65536:
                raise InstallError("unsupported")
            access = permissions(metadata)
            if ref == app_ref:
                app_permissions = access
                if not set(access).issubset(value["permissions"]):
                    raise InstallError("flatpak_permissions")
            elif access:
                raise InstallError("flatpak_permissions")
            current = None
            if operation.get_operation_type() == self.fp.TransactionOperationType.UPDATE:
                kind, app_id, arch, branch = ref.split("/")
                current = self.installation.get_installed_ref(
                    self.fp.RefKind.APP if kind == "app" else self.fp.RefKind.RUNTIME,
                    app_id, arch, branch, None).get_commit()
                if not COMMIT.fullmatch(current or ""):
                    raise InstallError("unsupported")
            resolved.append({"ref": ref, "remote": remote, "commit": commit, "currentCommit": current,
                             "operation": operation.get_operation_type().value_nick,
                             "metadata": hashlib.sha256(data.encode()).hexdigest(),
                             "downloadBytes": operation.get_download_size()})
        if app_permissions is None:
            raise InstallError("unsupported")
        return {"installed": False, "operations": sorted(resolved, key=lambda item: item["ref"]),
                "packages": sorted(item["ref"] for item in resolved),
                "downloadBytes": sum(item["downloadBytes"] for item in resolved),
                "flatpak": {"remote": remote, "url": FLATHUB_URL, "scope": "user", "ref": app_ref,
                            "runtimeUpdates": [item["ref"] for item in resolved if item["operation"] == "update"],
                            "permissions": app_permissions}}

    def _transaction(self, value, expected=None, progress=None):
        remote = self.trusted_remote()
        self.check_overrides(value)
        tx = self.fp.Transaction.new_for_installation(self.installation, None)
        tx.set_no_interaction(True)
        tx.set_disable_auto_pin(True)
        state = {}
        def deny_rebase(*_args):
            state["error"] = InstallError("unsupported")
            return False
        tx.connect("add-new-remote", lambda *_: False)
        tx.connect("choose-remote-for-ref", lambda _tx, _ref, _reason, candidates: candidates.index(remote) if remote in candidates else -1)
        tx.connect("end-of-lifed-with-rebase", deny_rebase)
        tx.connect("basic-auth-start", lambda *_: False)
        tx.connect("webflow-start", lambda *_: False)
        tx.connect("end-of-lifed", lambda *_: state.update(error=InstallError("unsupported")))
        def ready(transaction):
            try:
                if "error" in state:
                    return False
                if self.trusted_remote() != remote:
                    raise InstallError("plan_changed")
                self.check_overrides(value)
                state["plan"] = self._resolved_plan(transaction, value, remote)
                if expected is not None and state["plan"] != expected:
                    raise InstallError("plan_changed")
                return expected is not None
            except Exception as error:
                state["error"] = error if isinstance(error, InstallError) else InstallError("unsupported")
                return False
        tx.connect("ready", ready)
        tx.connect("operation-error", lambda *_: False)
        if progress:
            def new_operation(_tx, _operation, status):
                seen = state.setdefault("seen", set())
                completed = len(seen)
                seen.add(_operation.get_ref())
                status.set_update_frequency(250)
                def changed(current):
                    total = max(1, len(state.get("plan", {}).get("operations", [])))
                    percent = None if current.get_is_estimating() else int((completed * 100 + current.get_progress()) / total)
                    progress("install", percent)
                status.connect("changed", changed)
            tx.connect("new-operation", new_operation)
        tx.add_install(remote, f"app/{value['id']}/{self.arch}/{value['branch']}", None)
        cancellable = self.gio.Cancellable()
        timeout = threading.Timer(1800 if expected else 90, cancellable.cancel)
        timeout.daemon = True
        timeout.start()
        try:
            tx.run(cancellable)
        except self.glib.Error as error:
            if "error" in state:
                raise state["error"]
            if expected is not None or "plan" not in state:
                raise InstallError(error_category(error)) from None
        finally:
            timeout.cancel()
        if "error" in state:
            raise state["error"]
        if "plan" not in state:
            raise InstallError("failed")
        return state["plan"]

    def prepare(self, value, operation="install"):
        if operation != "install":
            raise InstallError("system_maintenance_required")
        self.check_overrides(value)
        if self.installed(value):
            return {"installed": True}
        return self._transaction(value)

    def perform(self, operation, plan, progress, transaction=None):
        if operation != "install":
            raise InstallError("unsupported")
        ref = plan["flatpak"]["ref"].split("/")[1]
        from flatpak_catalog import recipes
        value = next((value for value in recipes().values() if value["id"] == ref), None)
        if value is None:
            raise InstallError("unsupported")
        self._transaction(value, expected=plan, progress=progress)

    def verify(self, value, operation, plan):
        self.check_overrides(value)
        remote = self.trusted_remote()
        for item in plan["operations"]:
            kind, app_id, arch, branch = item["ref"].split("/")
            installed = self.installation.get_installed_ref(
                self.fp.RefKind.APP if kind == "app" else self.fp.RefKind.RUNTIME,
                app_id, arch, branch, None)
            if installed.get_origin() != remote or installed.get_commit() != item["commit"]:
                return False
        return True
