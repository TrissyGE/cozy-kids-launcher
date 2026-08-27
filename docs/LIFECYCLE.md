# Launcher lifecycle contract

The launcher records one small, validated state file at
`~/.cache/cozy-kids-launcher/lifecycle.json`. This makes startup and shutdown
behavior observable without exposing process IDs, paths, configuration, or
family data. The cache directory is private to the local user and the state
file is written atomically with mode `0600`.

## States

| State | Meaning | Valid next states |
|---|---|---|
| `starting` | Server and browser are being prepared | `running`, `recovering`, `stopping`, `failed` |
| `running` | The local server and owned launcher browser are ready | `recovering`, `updating`, `stopping`, `failed` |
| `recovering` | An owned failed runtime is being cleaned up before a bounded retry | `starting`, `stopping`, `failed` |
| `updating` | All owned runtime children are stopped and the update trigger is running | `starting`, `stopping`, `failed` |
| `stopping` | Owned server, browser, tile, overlay, and watchdog processes are being closed | `stopped`, `failed` |
| `stopped` | Cleanup completed normally | `starting` |
| `failed` | Recovery was exhausted or startup/update could not complete | `starting` |

Every state has a fixed reason allowlist. Recovery attempts are integers from
1 through 10. Invalid state/reason pairs and invalid transitions are rejected
without replacing the previous valid file.

## Scenario guarantees

- **Startup:** `starting/initial-start` → `running/ready`.
- **Parent exit:** `running/ready` → `stopping/parent-exit` → `stopped/parent-exit`.
- **Logout:** a session `SIGHUP` or `SIGTERM` without another explicit intent
  becomes `stopping/logout` → `stopped/logout`.
- **Shutdown:** the authenticated local shutdown endpoint writes a short-lived
  `shutdown` intent before invoking `systemctl` or `loginctl`. The same session
  termination signal is therefore recorded as `stopped/shutdown`, not logout.
- **Successful update:** `running` → `updating/update-requested` →
  `starting/update-complete` → `running/update-complete`. An update error ends
  as `failed/update-failed` after owned-process cleanup.
- **Server crash:** `running` → `recovering/server-failed` →
  `starting/recovery` → `running/recovered`. The attempt is recorded. Exhausting
  the bounded retry policy ends as `failed/recovery-exhausted`.

The `EXIT` trap owns final cleanup for normal exits, handled session signals,
and command failures. `SIGKILL`, power loss, and kernel failure cannot run a
process cleanup hook; a later launcher run deliberately starts a new lifecycle
and replaces that stale state.

## Diagnostics and tests

Parent diagnostics include only the allowlisted current state, reason, and
bounded recovery attempt. Automated Linux integration tests run real isolated
launcher, server, browser-stub, update, shutdown, logout, and crash-recovery
flows and verify that all owned process records are dead at terminal states.
