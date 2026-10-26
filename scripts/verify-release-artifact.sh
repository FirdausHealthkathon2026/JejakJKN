#!/usr/bin/env bash
set -euo pipefail

manifest="${1:?usage: verify-release-artifact.sh ARTIFACT.manifest}"
public_key="${RELEASE_SIGNING_PUBLIC_KEY_PATH:-.secrets/release-signing-public.pem}"
openssl dgst -sha256 -verify "$public_key" -signature "$manifest.sig" "$manifest" >/dev/null
artifact="$(dirname "$manifest")/$(sed -n 's/^artifact=//p' "$manifest")"
expected="$(sed -n 's/^sha256=//p' "$manifest")"
actual="$(sha256sum "$artifact" | cut -d' ' -f1)"
test "$actual" = "$expected"
echo "Release signature and artifact digest are valid."
