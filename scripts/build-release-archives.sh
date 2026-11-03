#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: bash scripts/build-release-archives.sh COMMIT OUTPUT_DIRECTORY" >&2
  exit 2
fi

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
commit="$(git -C "$repo" rev-parse --verify --end-of-options "$1^{commit}")"
version="$(git -C "$repo" show "$commit:VERSION" | tr -d '\r\n')"
if [[ ! "$version" =~ ^[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}(-rc\.[1-9][0-9]{0,8})?$ ]]; then
  echo "Unsupported VERSION in $commit" >&2
  exit 1
fi

export LC_ALL=C TZ=UTC
output="$2"
prefix="cozy-kids-launcher-$version"
mkdir -p -- "$output"
staging="$(mktemp -d -- "$output/.release.XXXXXX")"
trap 'rm -rf -- "$staging"' EXIT
git -C "$repo" -c tar.umask=0002 archive --format=tar --prefix="$prefix/" "$commit" \
  | gzip -n -6 > "$staging/$prefix.tar.gz"
git -C "$repo" archive --format=zip -6 --prefix="$prefix/" "$commit" > "$staging/$prefix.zip"
(
  cd "$staging"
  sha256sum "$prefix.tar.gz" "$prefix.zip" > SHA256SUMS
)
mv -- "$staging/$prefix.tar.gz" "$staging/$prefix.zip" "$staging/SHA256SUMS" "$output/"
