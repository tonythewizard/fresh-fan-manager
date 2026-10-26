#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build a standalone Debian/Ubuntu/Mint/Parrot .deb package
# Works on any distribution (uses dpkg-deb if present, or standard ar+tar).
#
set -e

HERE="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="2.0.0"
case "$(uname -m)" in
  x86_64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *) echo "Unsupported Debian build architecture: $(uname -m)" >&2; exit 1 ;;
esac
PKG_NAME="fresh-fan-manager"
DEB_NAME="${PKG_NAME}_${VERSION}_${ARCH}.deb"
DIST_DIR="$HERE/dist"
STAGE_DIR="$(mktemp -d /tmp/deb-build-XXXXXX)"

cleanup() {
  rm -rf "$STAGE_DIR"
}
trap cleanup EXIT INT TERM

echo "==> Staging Debian package layout in $STAGE_DIR"
mkdir -p "$STAGE_DIR/DEBIAN"
mkdir -p "$STAGE_DIR/opt/fresh-fan-manager/bin"
mkdir -p "$STAGE_DIR/usr/local/bin"
mkdir -p "$STAGE_DIR/usr/share/applications"
mkdir -p "$STAGE_DIR/usr/share/polkit-1/actions"
mkdir -p "$STAGE_DIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$STAGE_DIR/usr/lib/systemd/user"
mkdir -p "$STAGE_DIR/usr/lib/udev/rules.d"
mkdir -p "$DIST_DIR"

# Copy application files
if [ "$ARCH" = amd64 ]; then
  gcc -O2 -fPIC -shared "$HERE/native/smc_port_lib.c" -o "$STAGE_DIR/opt/fresh-fan-manager/bin/libsmc_port.so"
fi
cp "$HERE/LICENSE" "$HERE/THIRD_PARTY_NOTICES.md" "$STAGE_DIR/opt/fresh-fan-manager/"
cp -r "$HERE/core" "$STAGE_DIR/opt/fresh-fan-manager/"
cp -r "$HERE/ui" "$STAGE_DIR/opt/fresh-fan-manager/"
cp -r "$HERE/assets" "$STAGE_DIR/opt/fresh-fan-manager/"
cp "$HERE/fresh_fan_manager.py" "$STAGE_DIR/opt/fresh-fan-manager/"
cp "$HERE/bin/freshfan-helper" "$STAGE_DIR/opt/fresh-fan-manager/bin/"
ln -sf freshfan-helper "$STAGE_DIR/opt/fresh-fan-manager/bin/macfan-helper"

# Clean any pycache in stage dir
find "$STAGE_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$STAGE_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true

# Helpers and launchers
cp "$HERE/bin/freshfan-helper" "$STAGE_DIR/usr/local/bin/freshfan-helper"
ln -sf freshfan-helper "$STAGE_DIR/usr/local/bin/macfan-helper"

cat > "$STAGE_DIR/usr/local/bin/fresh-fan-manager" <<'EOF'
#!/usr/bin/env bash
if [ -x "/opt/fresh-fan-manager/.venv/bin/python" ]; then
  exec "/opt/fresh-fan-manager/.venv/bin/python" "/opt/fresh-fan-manager/fresh_fan_manager.py" "$@"
else
  exec python3 "/opt/fresh-fan-manager/fresh_fan_manager.py" "$@"
fi
EOF

# Policy, desktop entry, service, and icons
cp "$HERE/policies/org.freshfan.manager.policy" "$STAGE_DIR/usr/share/polkit-1/actions/"
cp "$HERE/autostart/fresh-fan-manager-menu.desktop" "$STAGE_DIR/usr/share/applications/fresh-fan-manager.desktop"
cp "$HERE/assets/fresh-fan-manager.png" "$STAGE_DIR/usr/share/icons/hicolor/256x256/apps/fresh-fan-manager.png"
if [ -f "$HERE/autostart/fresh-fan-daemon.service" ]; then
  cp "$HERE/autostart/fresh-fan-daemon.service" "$STAGE_DIR/usr/lib/systemd/user/"
fi

# Udev rule for macsmc
cat > "$STAGE_DIR/usr/lib/udev/rules.d/99-macsmc.rules" <<'EOF'
# Apple SMC device permissions for Fresh Fan Manager
KERNEL=="smc", SUBSYSTEM=="misc", MODE="0644"
EOF
chmod 644 "$STAGE_DIR/usr/lib/udev/rules.d/99-macsmc.rules"

# Permissions
chmod 755 "$STAGE_DIR/usr/local/bin/fresh-fan-manager"
chmod 755 "$STAGE_DIR/usr/local/bin/freshfan-helper"
chmod 755 "$STAGE_DIR/opt/fresh-fan-manager/fresh_fan_manager.py"
chmod 755 "$STAGE_DIR/opt/fresh-fan-manager/bin/freshfan-helper"
chmod 644 "$STAGE_DIR/usr/share/polkit-1/actions/org.freshfan.manager.policy"

# Control file
cat > "$STAGE_DIR/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: Antonio Gullotta <antonio@freshlinux.org>
Depends: python3 (>= 3.9), python3-psutil, lm-sensors, libnotify-bin, libc6, polkitd | policykit-1, pkexec | policykit-1, python3-pyside6.qtwidgets | python3-pyside6, python3-pyside6.qtnetwork | python3-pyside6
Recommends: smartmontools, stress-ng
Homepage: https://github.com/tonythewizard/fresh-fan-manager
Description: Universal cooling and hardware temperature suite for Linux
 Fresh Fan Manager is a modern hardware telemetry and fan control utility
 supporting Lenovo ThinkPad, ASUS, Dell, Apple Mac, Framework, and generic Linux PWM.
 Includes real-time CPU, GPU, RAM, storage, and battery metrics with desktop widget
 and headless background daemon modes.
EOF

# Post-installation script
cat > "$STAGE_DIR/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -t -f /usr/share/icons/hicolor 2>/dev/null || true
fi
exit 0
EOF
chmod 755 "$STAGE_DIR/DEBIAN/postinst"

echo "==> Packaging .deb"
if command -v dpkg-deb >/dev/null 2>&1; then
  dpkg-deb --build --root-owner-group "$STAGE_DIR" "$DIST_DIR/$DEB_NAME"
else
  # Native fallback using tar + ar
  echo "    (dpkg-deb not present, creating binary archive using tar + ar)"
  ARCHIVE_DIR="$(mktemp -d /tmp/deb-ar-XXXXXX)"
  echo "2.0" > "$ARCHIVE_DIR/debian-binary"
  tar --owner=0 --group=0 -czf "$ARCHIVE_DIR/control.tar.gz" -C "$STAGE_DIR/DEBIAN" .
  tar --owner=0 --group=0 --exclude="./DEBIAN" -cJf "$ARCHIVE_DIR/data.tar.xz" -C "$STAGE_DIR" .
  (cd "$ARCHIVE_DIR" && ar rcs "$DIST_DIR/$DEB_NAME" debian-binary control.tar.gz data.tar.xz)
  rm -rf "$ARCHIVE_DIR"
fi

echo "✔ Built Debian package: $DIST_DIR/$DEB_NAME"
ls -lh "$DIST_DIR/$DEB_NAME"
