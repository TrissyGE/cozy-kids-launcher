# Local launcher threat model

Cozy Kids Launcher separates a child's launcher UI from Parent controls on
a family device. It assumes a trusted operating system, user account and
installed browser. Someone who can edit that account's files or start
arbitrary programs outside the launcher has the account's ordinary access.
The Parent PIN is an application boundary.

| Boundary | Current controls | Review and release checks |
| --- | --- | --- |
| Parent authentication | Salted PIN hashing, bounded retry attempts, and expiring HttpOnly, SameSite session cookies. Families can choose to leave the PIN unset. | Test retry limits, expiry, and revocation. Test privileged routes with a PIN set and absent. |
| Local HTTP | Bind to loopback, check the request Host against the local listener, reject foreign origins on writes, and require Parent access for private configuration and actions. | Test forged, duplicated and missing Host headers, foreign-origin writes, and the normal installed browser flow. |
| Configuration and media imports | Validate and bound configuration data. Resolve opaque child media IDs against approved local sources. Check PS1 firmware and executable cores before use. | Test traversal, symlinks, oversized imports, changed files and interrupted writes. Child responses should exclude local paths. |
| Updates | Stable main promotion follows publication. Verified updates require the release checksum, and preview selection requires an eligible immutable release. Installer failures can trigger rollback. | Test altered archives, incomplete release metadata, interrupted installs and downgrade protection. Review signing and provenance as a separate release gate. |
| Process launching | Resolve child actions from the active profile and use argument vectors. Keep child process ownership and package confirmation separate from system authentication. | Test hidden or blocked tiles, process replacement and shutdown, changed package plans, and desktop focus. Parent-approved native apps retain their usual OS permissions. |

The launcher's media, ROM and package parsers handle externally supplied
files and metadata. Emulator and player bugs, compromised trusted package
sources, and browser or OS escapes remain relevant risks. The table records
the first-party boundary review. Independent review and native regression
testing remain part of release qualification.
