"""Optional system PackageKit binding. No shell, root helper, or password handling."""

import os
import re
import time

from package_provider import detect_native_provider, read_os_release


class InstallError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


PACKAGE_ROLES = {"install": "INSTALL_PACKAGES", "update": "UPDATE_PACKAGES", "remove": "REMOVE_PACKAGES"}
PACKAGE_OPERATIONS = set(PACKAGE_ROLES)
TRANSACTION_ID = re.compile(r"/[0-9]{1,20}_[a-zA-Z0-9_]{1,80}")


def package_identity(package_id):
    """Compare PackageKit name, version and architecture without repository metadata."""
    parts = package_id.split(";")
    if len(parts) != 4 or any(not value for value in parts[:3]):
        raise InstallError("unsupported")
    return tuple(parts[:3])


def error_category(value):
    value = str(value).lower()
    if any(word in value for word in ("network", "download", "fetch")):
        return "network"
    if any(word in value for word in ("auth", "denied", "permission", "cancel")):
        return "authorization"
    if any(word in value for word in ("lock", "busy", "unfinished")):
        return "busy"
    if any(word in value for word in ("not-found", "not found", "no-packages")):
        return "not_found"
    return "failed"


class PackageKitBackend:
    def __init__(self):
        release = read_os_release()
        if release.get("ID") not in ("ubuntu", "linuxmint", "zorin") or detect_native_provider(release) != "apt":
            raise InstallError("unsupported")
        try:
            import gi
            gi.require_version("PackageKitGlib", "1.0")
            from gi.repository import Gio, GLib, PackageKitGlib
            self.gio, self.glib = Gio, GLib
            self.pk = PackageKitGlib
            # Each server worker owns its synchronous client's callback context.
            self.context = GLib.MainContext.new()
            self.context.push_thread_default()
            self.control = self.pk.Control()
            self.control.get_properties(None)
            if self.control.props.backend_name != "apt":
                raise InstallError("unsupported")
            self.client = self.pk.Client()
            self.client.set_interactive(False)
        except InstallError:
            self.close()
            raise
        except (ImportError, ValueError, AttributeError):
            self.close()
            raise InstallError("unavailable") from None
        except Exception:
            self.close()
            raise InstallError("unavailable") from None

    def close(self):
        if getattr(self, "context", None) is not None:
            self.context.pop_thread_default()
            self.context = None

    def _flags(self, *values):
        return sum(1 << int(value) for value in values)

    def _call(self, method, *arguments, progress=None, transaction=None):
        def report(value, kind, unused):
            if transaction is not None:
                transaction(value.get_transaction_id())
            if progress is not None:
                phase = self.pk.status_enum_to_string(value.get_status())
                progress(phase, value.get_percentage())
        try:
            result = method(*arguments, None, report, None)
        except Exception as error:
            raise InstallError(error_category(error)) from None
        failure = result.get_error_code()
        if failure:
            raise InstallError(error_category(self.pk.error_enum_to_string(failure.get_code())))
        if result.get_exit_code() != self.pk.ExitEnum.SUCCESS:
            raise InstallError("failed")
        return result

    def _resolve(self, package):
        filters = self._flags(self.pk.FilterEnum.ARCH, self.pk.FilterEnum.NEWEST)
        result = self._call(self.client.resolve, filters, [package])
        return [item for item in result.get_package_array() if item.get_name() == package]

    def prepare(self, package, operation="install"):
        if operation not in PACKAGE_OPERATIONS:
            raise ValueError("Unknown package operation")
        # A previous launcher may have exited while the system daemon continued.
        # Never replay it or queue another installation behind an unknown action.
        try:
            if self.control.get_transaction_list(None):
                raise InstallError("busy")
        except InstallError:
            raise
        except Exception:
            raise InstallError("unavailable") from None
        packages = self._resolve(package)
        installed = {item.get_id() for item in packages if item.get_info() == self.pk.InfoEnum.INSTALLED}
        if operation == "install":
            if installed:
                return {"installed": True}
            candidates = {item.get_id() for item in packages if item.get_info() == self.pk.InfoEnum.AVAILABLE}
            if not candidates:
                raise InstallError("not_found")
        else:
            if not installed:
                raise InstallError("not_installed")
            if len(installed) != 1:
                raise InstallError("unsupported")
            current = package_identity(next(iter(installed)))
            candidates = installed if operation == "remove" else self._update_candidates(current)
        if len(candidates) != 1:
            raise InstallError("unsupported")
        package_ids = sorted(candidates)
        simulation = self._transaction(operation, package_ids, simulate=True)
        changes = simulation.get_package_array()
        if not changes or len(changes) > 200:
            raise InstallError("changes_required")
        expected = {
            "install": ("INSTALLING", "INSTALL"),
            "update": ("UPDATING", "UPDATE"),
            "remove": ("REMOVING", "REMOVE"),
        }[operation]
        allowed = {value for name in expected if (value := getattr(self.pk.InfoEnum, name, None)) is not None}
        if any(item.get_info() not in allowed for item in changes):
            raise InstallError("changes_required")
        change_ids = sorted(item.get_id() for item in changes)
        planned_identities = [package_identity(value) for value in change_ids]
        target = package_identity(package_ids[0])
        if target not in planned_identities or (operation != "install" and len(planned_identities) != 1):
            raise InstallError("changes_required")
        download_bytes = None
        if operation != "remove":
            details = self._call(self.client.get_details, change_ids).get_details_array()
            if len(details) == len(changes):
                download_bytes = sum(item.get_size() for item in details)
        plan = {
            "packageIds": package_ids,
            "changeIds": change_ids,
            "packages": sorted({item.get_name() for item in changes}),
            "downloadBytes": download_bytes,
        }
        if operation != "install":
            plan["currentVersion"] = current[1]
        if operation == "update":
            plan["targetVersion"] = package_identity(package_ids[0])[1]
        return plan

    def _update_candidates(self, current):
        filters = self._flags(self.pk.FilterEnum.ARCH)
        updates = self._call(self.client.get_updates, filters).get_package_array()
        candidates = set()
        for item in updates:
            if item.get_name() != current[0] or item.get_info() == self.pk.InfoEnum.BLOCKED:
                continue
            identity = package_identity(item.get_id())
            if identity[0] == current[0] and identity[1] != current[1] and identity[2] == current[2]:
                candidates.add(item.get_id())
        if not candidates:
            raise InstallError("no_update")
        return candidates

    def _transaction(self, operation, package_ids, *, simulate=False, progress=None, transaction=None):
        if operation not in PACKAGE_OPERATIONS:
            raise ValueError("Unknown package operation")
        flags = []
        if simulate:
            flags.append(self.pk.TransactionFlagEnum.SIMULATE)
        if operation == "remove":
            # No dependent removals and no autoremove, even at execution time.
            return self._call(self.client.remove_packages, self._flags(*flags), package_ids,
                              False, False, progress=progress, transaction=transaction)
        flags.append(self.pk.TransactionFlagEnum.ONLY_TRUSTED)
        method = self.client.update_packages if operation == "update" else self.client.install_packages
        return self._call(method, self._flags(*flags), package_ids, progress=progress, transaction=transaction)

    def perform(self, operation, plan, progress, transaction=None):
        # Polkit owns the password dialog. Do not use Pk.Task to answer prompts.
        self.client.set_interactive(True)
        self._transaction(operation, plan["packageIds"], progress=progress, transaction=transaction)

    def verify(self, package, operation, plan):
        installed = [item for item in self._resolve(package) if item.get_info() == self.pk.InfoEnum.INSTALLED]
        if operation == "remove":
            return not installed
        if operation == "update":
            expected = package_identity(plan["packageIds"][0])
            return any(package_identity(item.get_id()) == expected for item in installed)
        return bool(installed)


    def recover(self, transaction_id, operation, target, progress):
        """Observe the existing transaction, then verify the exact reviewed outcome."""
        if not TRANSACTION_ID.fullmatch(transaction_id):
            raise InstallError("interrupted")
        role = getattr(self.pk.RoleEnum, PACKAGE_ROLES[operation])
        bus = self.gio.bus_get_sync(self.gio.BusType.SYSTEM, None)
        while (state := self._transaction_properties(bus, transaction_id)) is not None:
            flags = state.get("TransactionFlags")
            if (state.get("Uid") != os.getuid() or state.get("Role") != int(role)
                    or not isinstance(flags, int) or flags & self._flags(self.pk.TransactionFlagEnum.SIMULATE)):
                raise InstallError("interrupted")
            status = state.get("Status")
            if status == int(self.pk.StatusEnum.FINISHED):
                break
            if not isinstance(status, int):
                raise InstallError("interrupted")
            progress(self.pk.status_enum_to_string(self.pk.StatusEnum(status)), state.get("Percentage"))
            time.sleep(1)

        self._verify_history(transaction_id, role)
        installed = [package_identity(item.get_id()) for item in self._resolve(target[0])
                     if item.get_info() == self.pk.InfoEnum.INSTALLED]
        return not installed if operation == "remove" else tuple(target) in installed

    def _transaction_properties(self, bus, transaction_id):
        # Observe read-only properties. Some older libpackagekit builds can
        # leave Client.adopt waiting even after the daemon finishes the job.
        try:
            (properties,) = bus.call_sync(
                "org.freedesktop.PackageKit", transaction_id,
                "org.freedesktop.DBus.Properties", "GetAll",
                self.glib.Variant("(s)", ("org.freedesktop.PackageKit.Transaction",)),
                self.glib.VariantType.new("(a{sv})"),
                self.gio.DBusCallFlags.NO_AUTO_START, 3000, None,
            ).unpack()
        except self.glib.Error:
            return None
        return properties or None

    def _verify_history(self, transaction_id, role):
        try:
            results = self._call(self.client.get_old_transactions, 50)
            match = next((item for item in results.get_transaction_array()
                          if item.get_id() == transaction_id
                          and item.get_uid() == os.getuid()
                          and item.get_role() == role), None)
        except Exception:
            raise InstallError("interrupted") from None
        if match is None:
            raise InstallError("interrupted")
        if not match.get_succeeded():
            raise InstallError("failed")
