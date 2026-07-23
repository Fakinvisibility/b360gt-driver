#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
package_dir="$project_root/packaging/arch"
version="$(sed -n 's/^pkgver=//p' "$package_dir/PKGBUILD")"
archive="$package_dir/b360gt-$version.tar.gz"

tar \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='artifacts' \
  --exclude='captures' \
  --exclude='media-library' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='packaging/arch/b360gt-*.tar.gz' \
  --transform="s,^\.,b360gt-$version," \
  -czf "$archive" \
  -C "$project_root" .

echo "$archive"
