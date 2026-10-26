#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build Fedora / RHEL / openSUSE RPM package using rpmbuild
#
set -e

if ! command -v rpmbuild >/dev/null 2>&1; then
  echo "rpmbuild not found. Install it with: sudo dnf install rpm-build (or zypper in rpm-build)"
  exit 1
fi

HERE="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="2.0.0"
DIST_DIR="$HERE/dist"
RPM_TOPDIR="$(mktemp -d /tmp/rpmbuild-XXXXXX)"

cleanup() {
  rm -rf "$RPM_TOPDIR"
}
trap cleanup EXIT INT TERM

mkdir -p "$DIST_DIR"
mkdir -p "$RPM_TOPDIR"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Create source archive
TARBALL_NAME="fresh-fan-manager-${VERSION}.tar.gz"
tar --exclude="./dist" --exclude="./.git" --exclude="./.venv" --exclude="./build" \
    --exclude="__pycache__" --exclude="*.pyc" --exclude="*.so" \
    --transform="s,^\\.,fresh-fan-manager-${VERSION}," \
    -czf "$RPM_TOPDIR/SOURCES/$TARBALL_NAME" -C "$HERE" .

cp "$HERE/tools/fresh-fan-manager.spec" "$RPM_TOPDIR/SPECS/"

echo "==> Building RPM package"
rpmbuild --define "_topdir $RPM_TOPDIR" -ba "$RPM_TOPDIR/SPECS/fresh-fan-manager.spec"

cp "$RPM_TOPDIR"/RPMS/*/*.rpm "$DIST_DIR/" 2>/dev/null || true
echo "✔ Built RPM package in: $DIST_DIR"
ls -lh "$DIST_DIR"/*.rpm 2>/dev/null || true
