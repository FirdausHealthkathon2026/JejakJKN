#!/usr/bin/env bash
set -euo pipefail

private_key="${RELEASE_SIGNING_PRIVATE_KEY_PATH:-.secrets/release-signing-private.pem}"
output_dir="${1:-releases}"
test -f "$private_key" || { echo "Missing release signing key: $private_key" >&2; exit 1; }
mkdir -p "$output_dir"
version="$(git describe --always --dirty)"
artifact="$output_dir/jejakjkn-$version.tar.gz"
manifest="$artifact.manifest"

git ls-files -z | tar --null -czf "$artifact" --files-from=-
{
  echo "artifact=$(basename "$artifact")"
  echo "sha256=$(sha256sum "$artifact" | cut -d' ' -f1)"
  echo "git_commit=$(git rev-parse HEAD)"
  echo "contracts_sha256=$(find contracts -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
  echo "created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$manifest"
openssl dgst -sha256 -sign "$private_key" -out "$manifest.sig" "$manifest"
echo "Signed release artifact: $artifact"
