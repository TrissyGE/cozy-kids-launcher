# Releasing Cozy Kids Launcher

Releases are built from a version tag by GitHub Actions. The workflow tests the exact tagged commit, creates versioned archives and `SHA256SUMS`, adds a build-provenance attestation, uploads everything to a draft, and only then publishes the release. Branch roles and pull-request targets are defined in [BRANCHING.md](BRANCHING.md).

## Compatibility contract

There are two updater generations in the field:

- Existing v0.3.x installations read `main/VERSION` and download `main.zip`. Because their installed code cannot be changed before that download, **`main` is a stable distribution channel, not a development branch**.
- `main` must equal the commit of the latest published stable release. Before a release is promoted it may be older, but it must never be newer or contain unreleased code. Therefore a legacy updater can only install a version less than or equal to the latest release.
- The current updater first looks for a complete stable GitHub Release containing `cozy-kids-launcher-<version>.tar.gz` and `SHA256SUMS`. Until such a release exists, it automatically falls back to the v0.3.x `main/VERSION` path.
- After one verified release update succeeds, the installation records `update-channel=release`. It then fails closed if release discovery is unavailable instead of silently returning to mutable `main`.
- `--legacy-main` is an explicit emergency override. It never overrides downgrade protection.

This makes the migration gradual: old installations keep updating, new installations gain checksum verification, and no flag day is required. Downgrade prevention in the current updater remains a second safety net; the stable-main invariant prevents a legacy device from receiving unreleased files in the first place.

## One-time repository setup

Before publishing the first release, enable [**immutable releases**](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes) in the repository settings under **Settings → General → Releases**. Once a release is published, its tag and assets are then locked and GitHub produces a release attestation.

The release workflow needs the repository's default GitHub Actions token permissions shown in `.github/workflows/release.yml`: `contents: write`, `id-token: write`, and `attestations: write`. GitHub documents the attestation verification model in [Using artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).

Create `develop` from the current stable `main` and do all ongoing work on `develop`, feature branches, or release branches. Protect `main` against ordinary human pushes and configure its repository rules so the release workflow is allowed to perform its fast-forward promotion. `.github/workflows/stable-main.yml` checks on pushes and daily that `main` is exactly the latest published release tag.

Use a dedicated Ed25519 deploy key for that promotion:

1. Add its public key under **Settings → Deploy keys**, enable **Allow write access**, and give it a release-specific title.
2. Add the private key under **Settings → Secrets and variables → Actions** as the repository secret `RELEASE_DEPLOY_KEY`.
3. In the stable-main branch ruleset, add **Deploy keys** to the bypass list. Do not add repository administrators as a permanent bypass.

The release workflow checks this credential against the repository before it runs tests or publishes anything. Never use a personal SSH key as the Actions secret.

## Prepare a release

1. Start from `develop` or create `release/vX.Y.Z` from `develop`. The release commit must still descend from the current `main`. Never prepare the release directly on `main`.
2. Choose the next semantic version, for example `0.4.0`.
3. Update `VERSION` and turn the relevant Unreleased changelog section into that version with an ISO date, for example `## [0.4.0] - 2026-08-25`. Both local and hosted release gates require it.
4. Run the local release gate:

   ```bash
   bash scripts/deploy.sh
   ```

5. Create and push an annotated tag pointing at that release-branch commit. Push the tag, **not the development branch to `main`**:

   ```bash
   git tag -a v0.4.0 -m "Cozy Kids Launcher 0.4.0"
   git push origin v0.4.0
   ```

The tag starts `.github/workflows/release.yml`. A mismatch between the tag and `VERSION`, a release commit that does not descend from stable `main`, any failing test, a broken isolated install, or a packaging error stops the job before publication.

Only after the release is published does the workflow fast-forward `main` to the exact tagged commit. If publication fails, `main` remains on the previous release. If the final fast-forward is blocked by repository rules, the new release already exists while `main` remains older, which is safe for legacy clients; correct the rule and promote only the exact tag commit.

After a release branch has been used, merge any release-only fixes back into `develop` and delete the branch.

## Verify the result

The published release must contain exactly these updater-facing assets:

```text
cozy-kids-launcher-0.4.0.tar.gz
cozy-kids-launcher-0.4.0.zip
SHA256SUMS
```

Check the workflow summary and verify the downloaded files when doing a manual smoke test:

```bash
sha256sum -c SHA256SUMS
gh attestation verify cozy-kids-launcher-0.4.0.tar.gz \
  --repo TrissyGE/cozy-kids-launcher
```

Finally, test both upgrade paths on disposable profiles:

1. an installed v0.3.x updater using the `main/VERSION` compatibility path;
2. the current updater selecting the new release, verifying its SHA-256 checksum, and writing the release-channel marker.

Also run the **Stable main invariant** workflow and verify that the commit IDs reported for `main` and the latest release tag are identical.

## Fixes and rollback

Never move an existing tag, replace release assets, or reuse a version number. If a published release has a defect, fix it and publish a higher patch version. The updater deliberately refuses downgrades, even with `--force`.

The updater snapshots the installed app, launcher, configuration, autostart entry, and desktop files immediately before installation and restores them automatically if the installer or post-install version check fails. The installer also creates timestamped backups under `~/.local/share/cozy-kids-launcher-backups/`.

Parent settings can restore `config.json` from those timestamped directories. This is deliberately a configuration-only operation: it never rolls program files back, it validates the backup against the installed schema, preserves the active Parent PIN, and creates a private pre-restore snapshot first.

Restoring an older *published* program version remains a deliberate manual recovery operation; user configuration should be backed up first.
