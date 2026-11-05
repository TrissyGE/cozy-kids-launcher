"""Single, Parent-confirmed catalog package operation with bounded private state."""

import json
import copy
from pathlib import Path
import re
import secrets
import threading
import time

from config_store import atomic_write_config
from package_provider import PACKAGE_NAME, PROVIDERS, mapped_package
from packagekit_backend import (
    InstallError, PACKAGE_OPERATIONS, PackageKitBackend, TRANSACTION_ID, package_identity,
)


ACTIVE_STATES = {"checking", "installing"}
ERRORS = {"network", "authorization", "busy", "not_found", "unsupported", "unavailable",
          "changes_required", "plan_changed", "failed", "interrupted", "storage",
          "not_installed", "no_update", "system_update_required", "system_maintenance_required"}
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
        self.recovery = None
        try:
            with self.journal.open(encoding="utf-8") as handle:
                previous = json.loads(handle.read(65537))
            if isinstance(previous, dict) and previous.get("status") != "idle":
                self.job = {"status": "interrupted", "error": "interrupted"}
                operation = previous.get("operation")
                if isinstance(operation, str) and operation in PACKAGE_OPERATIONS:
                    self.job["operation"] = operation
                    self._resume(previous)
        except (OSError, ValueError):
            pass

    def _resume(self, previous):
        if previous.get("status") != "installing":
            return
        transaction = previous.get("transactionId")
        target = previous.get("target")
        job_id, app_id = previous.get("jobId"), previous.get("appId")
        if (not isinstance(transaction, str) or not TRANSACTION_ID.fullmatch(transaction)
                or not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id)
                or not isinstance(app_id, str) or not 1 <= len(app_id) <= 100
                or not isinstance(target, list) or len(target) != 3
                or any(not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9.+:~_-]{1,200}", value)
                       for value in target)
                or not PACKAGE_NAME.fullmatch(target[0])):
            return
        provider = previous.get("provider", "apt")
        if not isinstance(provider, str) or provider not in PROVIDERS:
            return
        self.recovery = {"transactionId": transaction, "target": target}
        self.job = {"status": "installing", "operation": previous["operation"], "jobId": job_id,
                    "appId": app_id, "phase": "checking", "percent": None, "recovered": True, "provider": provider}
        self.worker = threading.Thread(target=self._recover, daemon=True)
        self.worker.start()

    def _recover(self):
        backend = None
        try:
            backend = self.backend_factory()
            if backend.provider != self.job["provider"]:
                raise InstallError("interrupted")
            if not backend.recover(self.recovery["transactionId"], self.job["operation"],
                                   self.recovery["target"], self._progress):
                raise InstallError("failed")
            self._update(status="complete", phase="complete", percent=100)
        except Exception as error:
            code = error.code if isinstance(error, InstallError) and error.code in ERRORS else "interrupted"
            with self.lock:
                self.job.update(status="interrupted" if code == "interrupted" else "error",
                                error=code, percent=None)
                try:
                    self._persist()
                except OSError:
                    pass
        finally:
            if backend:
                backend.close()

    def _persist(self):
        self.journal.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        record = {key: self.job[key] for key in
                  ("jobId", "appId", "operation", "status", "provider") if key in self.job}
        if self.job["status"] == "installing" and self.recovery:
            record.update(self.recovery)
        atomic_write_config(str(self.journal), record)

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
        packages = [mapped_package(rec, provider) for provider in PROVIDERS]
        if not any(packages):
            raise ValueError("App has no native package")
        with self.lock:
            if self.job["status"] in ACTIVE_STATES:
                raise InstallError("busy")
            self.job = {"jobId": secrets.token_hex(16), "appId": app_id, "operation": operation,
                        "status": "checking", "phase": "checking", "percent": None}
            self.plan = None
            self.token = None
            self.recovery = None
            try:
                self._persist()
            except OSError:
                self.job = {"status": "error", "error": "storage"}
                raise InstallError("storage") from None
            self.recipe = copy.deepcopy({key: rec[key] for key in ("package", "packages") if key in rec})
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

    def _record_transaction(self, transaction, target):
        if not isinstance(transaction, str) or not TRANSACTION_ID.fullmatch(transaction):
            return
        with self.lock:
            if self.recovery is not None:
                return
            self.recovery = {"transactionId": transaction, "target": list(target)}
            try:
                self._persist()
            except OSError:
                # The daemon already owns the transaction. Keep reporting
                # progress and retry persistence on the next callback.
                self.recovery = None

    def _run(self, confirmed):
        backend = None
        operation = self.job["operation"]
        try:
            backend = self.backend_factory()
            self.package = backend.catalog_package(self.recipe)
            if confirmed and backend.provider != self.job.get("provider"):
                raise InstallError("plan_changed")
            if not confirmed:
                self._update(provider=backend.provider)
            plan = backend.prepare(self.package, operation)
            if plan.get("installed"):
                self._update(status="complete", phase="complete", percent=100)
                return
            if confirmed:
                if plan != self.plan:
                    raise InstallError("plan_changed")
                target = package_identity(plan["packageIds"][0])
                backend.perform(operation, plan, self._progress,
                                transaction=lambda value: self._record_transaction(value, target))
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
