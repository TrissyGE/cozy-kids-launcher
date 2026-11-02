"""Optional system PackageKit binding. No shell, root helper, or password handling."""

from package_provider import detect_native_provider, read_os_release


class InstallError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


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
            from gi.repository import GLib, PackageKitGlib
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

    def _call(self, method, *arguments, progress=None):
        def report(value, kind, unused):
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

    def prepare(self, package):
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
        if any(item.get_info() == self.pk.InfoEnum.INSTALLED for item in packages):
            return {"installed": True}
        candidates = {item.get_id() for item in packages if item.get_info() == self.pk.InfoEnum.AVAILABLE}
        if not candidates:
            raise InstallError("not_found")
        if len(candidates) != 1:
            raise InstallError("unsupported")
        package_ids = sorted(candidates)
        flags = self._flags(self.pk.TransactionFlagEnum.SIMULATE, self.pk.TransactionFlagEnum.ONLY_TRUSTED)
        simulation = self._call(self.client.install_packages, flags, package_ids)
        changes = simulation.get_package_array()
        if not changes or len(changes) > 200:
            raise InstallError("changes_required")
        # First release deliberately refuses removals, upgrades and downgrades.
        if any(item.get_info() != self.pk.InfoEnum.INSTALLING for item in changes):
            raise InstallError("changes_required")
        details = self._call(self.client.get_details, [item.get_id() for item in changes]).get_details_array()
        download_bytes = sum(item.get_size() for item in details) if len(details) == len(changes) else None
        return {
            "installed": False,
            "packageIds": package_ids,
            "changeIds": sorted(item.get_id() for item in changes),
            "packages": sorted({item.get_name() for item in changes}),
            "downloadBytes": download_bytes,
        }

    def install(self, plan, progress):
        # PackageKit/Polkit request system authorization from the desktop agent.
        # Do not use Pk.Task, which can silently answer additional questions.
        self.client.set_interactive(True)
        flags = self._flags(self.pk.TransactionFlagEnum.ONLY_TRUSTED)
        self._call(self.client.install_packages, flags, plan["packageIds"], progress=progress)

    def installed(self, package):
        return any(item.get_info() == self.pk.InfoEnum.INSTALLED for item in self._resolve(package))
