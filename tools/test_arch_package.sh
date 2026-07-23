#!/usr/bin/env bash
set -euo pipefail

archive=${1:?usage: test_arch_package.sh /path/to/b360gt-live-test.tar.gz}
test_dir=/tmp/b360gt-arch-package-test-20260723

mkdir -p "$test_dir"
tar -xzf "$archive" -C "$test_dir"
cd "$test_dir"

bash packaging/arch/prepare-source.sh
cd packaging/arch
makepkg --cleanbuild --noconfirm

package_file=$(find . -maxdepth 1 -name 'b360gt-*.pkg.tar.zst' -print -quit)
if [[ -z "$package_file" ]]; then
    echo "No package file was produced." >&2
    exit 1
fi

echo "PACKAGE=$package_file"
bsdtar -xOf "$package_file" .PKGINFO
