# Branching and pull-request flow

Cozy Kids Launcher uses a small release-oriented branch model. The important constraint is that legacy installations download code directly from `main`, so `main` must never contain unreleased development.

## Long-lived branches

| Branch | Responsibility | What may land there |
|---|---|---|
| `main` | Stable distribution channel | Only the exact commit of the latest published release |
| `develop` | Integration branch for the next release | Reviewed features, fixes, documentation, and release preparation |

`main` is not the default development target. It is advanced by the release workflow only after a release has been published successfully. Direct human pushes and ordinary pull requests to `main` should be blocked by the repository ruleset.

`develop` should require the CI checks before merge. Keep it usable and testable; partially implemented work stays on its topic branch.

## Short-lived branches

Create these from `develop`:

| Pattern | Use |
|---|---|
| `feature/<topic>` | New user-facing behavior |
| `fix/<topic>` | Bug fixes for the next release |
| `docs/<topic>` | Documentation-only changes |
| `refactor/<topic>` | Internal changes without intended behavior changes |
| `test/<topic>` | Test infrastructure and coverage |

Use a short lowercase topic separated with hyphens, for example `feature/timer-presets` or `fix/browser-overlay-focus`. Open the pull request against `develop` and delete the branch after merge.

## Release branches

A release branch is optional but recommended once a version is being stabilized:

```text
feature/* ─┐
fix/* ─────┼──► develop ──► release/vX.Y.Z ──► tag vX.Y.Z
docs/* ────┘                                      │
                                                  ▼
                                      GitHub Release ──► main
```

Create `release/vX.Y.Z` from `develop`. During the freeze it accepts only:

- the version and changelog update;
- release documentation;
- fixes for release-blocking defects.

Run the release gate and tag the release commit as described in [RELEASING.md](RELEASING.md). The automation publishes the immutable release first and then fast-forwards `main` to that exact tag. Merge any final release-branch changes back into `develop`, then delete the branch.

Never merge a release branch into `main` manually and never move or reuse a published tag.

## Hotfixes

Use `hotfix/vX.Y.Z` only for an urgent defect in the current stable release:

1. Create the branch from `main`.
2. Make the smallest safe fix and add a regression test.
3. Choose a higher patch version and update `VERSION` and `CHANGELOG.md`.
4. Run `bash scripts/deploy.sh`.
5. Tag the tested hotfix commit and let the normal release workflow publish and promote it.
6. Merge the hotfix changes back into `develop`.

Do not repair a published release by replacing its files or force-moving its tag.

## Pull requests

Every pull request should:

- explain the user-visible problem and the chosen change;
- target `develop`, except for repository-maintenance work that explicitly documents another target;
- include tests or explain why no automated test is practical;
- include updated screenshots when the visible interface changes;
- preserve old configuration formats and the updater compatibility contract;
- pass all required CI checks before merge.

Prefer small, reviewable pull requests. A squash merge is appropriate for most topic branches; release and hotfix history may be kept intact when that makes the tag ancestry clearer.

## Repository rules

Recommended GitHub configuration:

- protect `main` from deletion, force-pushes, and direct human pushes;
- allow only the release deploy key to bypass the `main` promotion restriction;
- require the CI workflow on pull requests to `develop`;
- block force-pushes and branch deletion for both long-lived branches;
- keep immutable releases enabled.

The scheduled **Stable main invariant** workflow is an additional guard: it verifies that `main` and the latest published stable tag point to the same commit.
