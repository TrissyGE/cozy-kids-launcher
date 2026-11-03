"""Single, Parent-confirmed catalog package operation with bounded private state."""

import json
from pathlib import Path
import secrets
import threading
import time

from config_store import atomic_write_config
from package_provider import PACKAGE_NAME
from packagekit_backend import InstallError, PACKAGE_OPERATIONS, PackageKitBackend


ACTIVE_STATES = {"checking", "installing"}
ERRORS = {"network", "authorization", "busy", "not_found", "unsupported", "unavailable",
          "changes_required", "plan_changed", "failed", "interrupted", "storage",
          "not_installed", "no_update"}
PHASES = {"waiting-for-auth": "authorization", "download": "downloading", "install": "installing",
          "update": "updating", "remove": "removing", "wait": "waiting",
          "waiting-for-lock": "waiting", "setup": "checking"}


class PackageInstaller:
    def __init__(self, journal, backend_factory=PackageKitBackend, clock=time.monotonic):
        self.journal = Path(journal)
        self.backend_factory = backend_factory
        self.clock = clock
        self.lock = threading.RLock()
        self.job = {"status": "idle"}
        self.plan = None
        self.token = None
        self.worker = None
        try:
            with self.journal.open(encoding="utf-8") as handle:
                previous = json.loads(handle.read(65537))
            if isinstance(previous, dict) and previous.get("status") != "idle":
                # No consent or executable plan survives a process restart.
                self.job = {"status": "interrupted", "error": "interrupted"}
                operation = previous.get("operation")
                if isinstance(operation, str) and operation in PACKAGE_OPERATIONS:
                    self.job["operation"] = operation
        except (OSError, ValueError):
            pass

    def _persist(self):
        self.journal.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_config(str(self.journal), {key: self.job[key] for key in
                            ("jobId", "appId", "operation", "status") if key in self.job})

    def snapshot(self):
        with self.lock:
            result = dict(self.job)
            if result["status"] == "ready":
                result["confirmationToken"] = self.token
            return result

    def _update(self, **values):
        with self.lock:
            self.job.update(values)
            self._persist()

    def prepare(self, app_id, recommendations, operation="install"):
        if not isinstance(app_id, str) or len(app_id) > 100:
            raise ValueError("Invalid app identifier")
        if not isinstance(operation, str) or operation not in PACKAGE_OPERATIONS:
            raise ValueError("Invalid package operation")
        rec = next((item for item in recommendations if item.get("id") == app_id), None)
        if rec is None:
            raise ValueError("Unknown catalog app")
        mappings = rec.get("packages", {})
        if not isinstance(mappings, dict):
            raise ValueError("Invalid native package mapping")
        package = mappings.get("apt", rec.get("package"))
        if not isinstance(package, str) or not PACKAGE_NAME.fullmatch(package):
            raise ValueError("App has no native package")
        with self.lock:
            if self.job["status"] in ACTIVE_STATES:
                raise InstallError("busy")
            self.job = {"jobId": secrets.token_hex(16), "appId": app_id, "operation": operation,
                        "status": "checking", "phase": "checking", "percent": None}
            self.plan = None
            self.token = None
            try:
                self._persist()
            except OSError:
                self.job = {"status": "error", "error": "storage"}
                raise InstallError("storage") from None
            self.package = package
            self.worker = threading.Thread(target=self._run, args=(False,), daemon=True)
            self.worker.start()
            return self.snapshot()

    def start(self, job_id, token, expected_operation=None):
        with self.lock:
            if self.job["status"] == "ready" and self.clock() > self.expires:
                self.token = None
                try:
                    self._update(status="error", error="plan_changed")
                except OSError:
                    self.job.update(status="error", error="storage")
                    raise InstallError("storage") from None
                raise InstallError("plan_changed")
            if (self.job["status"] != "ready" or not isinstance(token, str)
                    or not self.token or not secrets.compare_digest(token, self.token)
                    or job_id != self.job.get("jobId")
                    or (expected_operation and self.job["operation"] != expected_operation)):
                raise InstallError("plan_changed")
            self.token = None
            # Persist intent before any system transaction, so a lost response
            # or process restart cannot turn into an automatic second install.
            try:
                self._update(status="installing", phase="checking", percent=None)
            except OSError:
                self.job.update(status="error", error="storage")
                raise InstallError("storage") from None
            self.worker = threading.Thread(target=self._run, args=(True,), daemon=True)
            self.worker.start()
            return self.snapshot()

    def _progress(self, phase, percentage):
        with self.lock:
            self.job["phase"] = PHASES.get(phase, self.job.get("phase", "installing"))
            self.job["percent"] = percentage if isinstance(percentage, int) and 0 <= percentage <= 100 else None

    def _run(self, confirmed):
        backend = None
        operation = self.job["operation"]
        try:
            backend = self.backend_factory()
            plan = backend.prepare(self.package, operation)
            if plan.get("installed"):
                self._update(status="complete", phase="complete", percent=100)
                return
            if confirmed:
                if plan != self.plan:
                    raise InstallError("plan_changed")
                backend.perform(operation, plan, self._progress)
                if not backend.verify(self.package, operation, plan):
                    raise InstallError("failed")
                self._update(status="complete", phase="complete", percent=100)
            else:
                with self.lock:
                    self.plan = plan
                    self.token = secrets.token_urlsafe(32)
                    self.expires = self.clock() + 600
                    self._update(status="ready", packages=plan["packages"],
                                 downloadBytes=plan["downloadBytes"], percent=None,
                                 **{key: plan[key] for key in ("currentVersion", "targetVersion") if key in plan})
        except Exception as error:
            code = error.code if isinstance(error, InstallError) and error.code in ERRORS else "failed"
            if isinstance(error, OSError):
                code = "storage"
            with self.lock:
                self.token = None
                self.job.update(status="error", error=code, percent=None)
                try:
                    self._persist()
                except OSError:
                    pass
        finally:
            if backend:
                backend.close()
