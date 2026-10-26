#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Universal Installer for Fresh Fan Manager
# Compatible with Arch, CachyOS, Manjaro, Debian, Ubuntu, Parrot, Mint, Fedora, openSUSE.
# Supports direct git execution and piped execution:
#   curl -sSL https://raw.githubusercontent.com/tonythewizard/fresh-fan-manager/main/install.sh | bash
#
set -e

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
  REAL_USER="${SUDO_USER:-root}"
  REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
  [ -z "$REAL_HOME" ] && REAL_HOME="/root"
else
  SUDO="sudo"
  REAL_USER="$USER"
  REAL_HOME="$HOME"
fi

HERE="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo "")"
CLEANUP_TMP=0

# Handle piped curl / wget execution where local repository files are absent
if [ -z "$HERE" ] || [ ! -f "$HERE/fresh_fan_manager.py" ]; then
  echo "==> Piped installation detected. Cloning latest Fresh Fan Manager repository..."
  TMP_CLONE="$(mktemp -d /tmp/fresh-fan-manager-installer-XXXXXX)"
  if command -v git >/dev/null 2>&1; then
    git clone --depth 1 https://github.com/tonythewizard/fresh-fan-manager.git "$TMP_CLONE"
  else
    echo "==> git not found, downloading archive via curl/tar..."
    mkdir -p "$TMP_CLONE"
    curl -fsSL https://github.com/tonythewizard/fresh-fan-manager/archive/refs/heads/main.tar.gz | tar -xz -C "$TMP_CLONE" --strip-components=1
  fi
  HERE="$TMP_CLONE"
  CLEANUP_TMP=1
fi

cleanup() {
  if [ "$CLEANUP_TMP" -eq 1 ] && [ -d "$HERE" ]; then
    rm -rf "$HERE"
  fi
}
trap cleanup EXIT INT TERM

APP_DIR="/opt/fresh-fan-manager"
LAUNCHER="/usr/local/bin/fresh-fan-manager"
HELPER_PRIMARY="/usr/local/bin/freshfan-helper"
HELPER_LEGACY="/usr/local/bin/macfan-helper"
POLICY="/usr/share/polkit-1/actions/org.freshfan.manager.policy"
MENU="/usr/share/applications/fresh-fan-manager.desktop"
AUTOSTART_DIR="$REAL_HOME/.config/autostart"
AUTOSTART="$AUTOSTART_DIR/fresh-fan-manager.desktop"
ICON_PNG_DIR="/usr/share/icons/hicolor/256x256/apps"

echo "==> Installing system dependencies"
if command -v pacman >/dev/null 2>&1; then
  echo "    Detected Arch Linux / CachyOS / Manjaro"
  $SUDO pacman -S --needed --noconfirm git make gcc lm_sensors libnotify polkit python python-psutil pyside6 2>/dev/null || true
  $SUDO pacman -S --needed --noconfirm stress-ng 2>/dev/null || true

elif command -v apt-get >/dev/null 2>&1; then
  echo "    Detected Debian / Ubuntu / Parrot / Mint"
  $SUDO apt-get update -qq
  $SUDO apt-get install -y python3 python3-pip python3-venv lm-sensors libnotify-bin stress-ng git make gcc 2>/dev/null || true
  $SUDO apt-get install -y python3-psutil python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets python3-pyside6.qtnetwork 2>/dev/null || true
  if ! $SUDO apt-get install -y polkitd pkexec 2>/dev/null; then
    $SUDO apt-get install -y policykit-1 2>/dev/null || true
  fi

elif command -v dnf >/dev/null 2>&1; then
  echo "    Detected Fedora / RHEL"
  $SUDO dnf install -y python3 python3-pip python3-pyside6 python3-psutil lm_sensors libnotify polkit stress-ng git make gcc 2>/dev/null || true

elif command -v zypper >/dev/null 2>&1; then
  echo "    Detected openSUSE"
  $SUDO zypper --non-interactive install python3 python3-pip python3-psutil libnotify-tools polkit stress-ng git make gcc 2>/dev/null || true
fi

echo "==> Removing legacy installations (if present)"
$SUDO rm -rf /opt/macfan-monitor 2>/dev/null || true
$SUDO rm -f /usr/local/bin/macfan-monitor
$SUDO rm -f /usr/share/applications/macfan-monitor.desktop
$SUDO rm -f /usr/share/icons/hicolor/256x256/apps/macfan-monitor.png
rm -f "$REAL_HOME/.config/autostart/macfan-monitor.desktop" 2>/dev/null || true
rm -f "$REAL_HOME/.local/share/applications/macfan-monitor.desktop" 2>/dev/null || true
rm -f "$REAL_HOME/.local/share/applications/fresh-fan-manager.desktop" 2>/dev/null || true
$SUDO rm -f /usr/share/polkit-1/actions/org.macfan.monitor.policy

echo "==> Installing files into $APP_DIR"
$SUDO mkdir -p "$APP_DIR/bin"
$SUDO cp -r "$HERE/core" "$HERE/ui" "$HERE/assets" "$HERE/fresh_fan_manager.py" "$APP_DIR/"
$SUDO chmod 755 "$APP_DIR" "$APP_DIR/core" "$APP_DIR/ui" "$APP_DIR/assets" "$APP_DIR/bin"
$SUDO find "$APP_DIR" -type f -exec chmod 644 {} +
$SUDO chmod 755 "$APP_DIR/fresh_fan_manager.py"

echo "==> Configuring Python environment at $APP_DIR/.venv"
$SUDO python3 -m venv --system-site-packages "$APP_DIR/.venv" 2>/dev/null \
    || $SUDO python3 -m venv "$APP_DIR/.venv"

VENV_PY="$APP_DIR/.venv/bin/python"
VENV_PIP="$APP_DIR/.venv/bin/pip"

# Bootstrap pip if missing
if [ ! -x "$VENV_PIP" ]; then
  $SUDO "$VENV_PY" -m ensurepip --upgrade 2>/dev/null || true
fi

# Verify core dependencies in venv
MISSING=()
if ! ${SUDO} "$VENV_PY" -c "import PySide6.QtWidgets, PySide6.QtNetwork" 2>/dev/null; then MISSING+=(PySide6); fi
if ! ${SUDO} "$VENV_PY" -c "import psutil" 2>/dev/null; then MISSING+=(psutil); fi

if [ ${#MISSING[@]} -gt 0 ]; then
  if [ -x "$VENV_PIP" ]; then
    echo "==> Installing missing Python dependencies via pip: ${MISSING[*]}"
    ${SUDO} "$VENV_PIP" install --upgrade pip 2>/dev/null || true
    if [ -f "$HERE/requirements.txt" ]; then
      ${SUDO} "$VENV_PIP" install --cache-dir "$REAL_HOME/.cache/pip" -r "$HERE/requirements.txt"
    else
      $SUDO "$VENV_PIP" install --cache-dir "$REAL_HOME/.cache/pip" PySide6 psutil
    fi
  else
    echo "WARNING: PySide6/psutil not found and pip could not be bootstrapped."
    echo "Install them using your system package manager."
  fi
fi

echo "==> Installing launcher at $LAUNCHER"
$SUDO tee "$LAUNCHER" > /dev/null <<EOF
#!/usr/bin/env bash
if [ -x "$APP_DIR/.venv/bin/python" ]; then
  exec "$APP_DIR/.venv/bin/python" "$APP_DIR/fresh_fan_manager.py" "\$@"
else
  exec python3 "$APP_DIR/fresh_fan_manager.py" "\$@"
fi
EOF
$SUDO chmod 755 "$LAUNCHER"

echo "==> Installing privileged helpers"
NATIVE_BUILD_DIR="$(mktemp -d /tmp/freshfan-native-XXXXXX)"
if [[ "$(uname -m)" == x86_64 || "$(uname -m)" == i?86 ]]; then
  echo "==> Building native Intel SMC port helper library"
  gcc -O2 -Wall -Wextra -fPIC -shared "$HERE/native/smc_port_lib.c" -o "$NATIVE_BUILD_DIR/libsmc_port.so"
fi
$SUDO cp -f "$HERE/bin/macfan-helper" "$HELPER_PRIMARY"
$SUDO chown root:root "$HELPER_PRIMARY"
$SUDO chmod 755 "$HELPER_PRIMARY"
$SUDO ln -sf "$HELPER_PRIMARY" "$HELPER_LEGACY"
$SUDO cp -f "$HERE/bin/macfan-helper" "$APP_DIR/bin/freshfan-helper"
$SUDO chown root:root "$APP_DIR/bin/freshfan-helper"
$SUDO chmod 755 "$APP_DIR/bin/freshfan-helper"
$SUDO ln -sf "$APP_DIR/bin/freshfan-helper" "$APP_DIR/bin/macfan-helper"
if [ -f "$NATIVE_BUILD_DIR/libsmc_port.so" ]; then
  $SUDO install -o root -g root -m 755 "$NATIVE_BUILD_DIR/libsmc_port.so" "$APP_DIR/bin/libsmc_port.so"
else
  $SUDO rm -f "$APP_DIR/bin/libsmc_port.so"
fi
rm -rf "$NATIVE_BUILD_DIR"
$SUDO rm -f /usr/local/bin/libsmc_port.so
$SUDO chown root:root "$APP_DIR" "$APP_DIR/bin"
$SUDO cp "$HERE/LICENSE" "$APP_DIR/LICENSE"
$SUDO cp "$HERE/THIRD_PARTY_NOTICES.md" "$APP_DIR/THIRD_PARTY_NOTICES.md"

echo "==> Installing polkit authorization policy"
$SUDO cp "$HERE/policies/org.freshfan.manager.policy" "$POLICY"
$SUDO chown root:root "$POLICY"
$SUDO chmod 644 "$POLICY"

echo "==> Installing udev rule for Apple SMC (macsmc driver)"
$SUDO tee "/etc/udev/rules.d/99-macsmc.rules" > /dev/null <<'EOF'
# Apple SMC device permissions for Fresh Fan Manager
KERNEL=="smc", SUBSYSTEM=="misc", MODE="0644"
EOF
$SUDO chmod 644 "/etc/udev/rules.d/99-macsmc.rules"
$SUDO udevadm control --reload-rules 2>/dev/null || true
$SUDO udevadm trigger --subsystem-match=misc 2>/dev/null || true
if [ -e /dev/smc ]; then
  $SUDO chmod 644 /dev/smc 2>/dev/null || true
fi

echo "==> Installing application icons"
$SUDO mkdir -p "$ICON_PNG_DIR"
if [ -x "$VENV_PY" ]; then
  for SIZE in 16 22 24 32 40 48 64 96 128 192 256 384 512; do
    SDIR="/usr/share/icons/hicolor/${SIZE}x${SIZE}/apps"
    $SUDO mkdir -p "$SDIR"
    TMP="/tmp/fresh-fan-${SIZE}.png"
    QT_QPA_PLATFORM=offscreen "$VENV_PY" - "$TMP" "$SIZE" <<'PYGEN' 2>/dev/null || true
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import Qt
app = QApplication([])
out, sz = sys.argv[1], int(sys.argv[2])
pm = QPixmap(sz, sz); pm.fill(Qt.GlobalColor.transparent)
p = QPainter(pm)
p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
f = QFont(); f.setPixelSize(int(sz * 0.98)); f.setBold(True); p.setFont(f)
p.setPen(QColor("#7FD7FF"))
p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "❄")
p.end()
pm.save(out, "PNG")
PYGEN
    if [ -f "$TMP" ]; then
      $SUDO cp "$TMP" "$SDIR/fresh-fan-manager.png"
      rm -f "$TMP"
    fi
  done
  $SUDO cp "/usr/share/icons/hicolor/512x512/apps/fresh-fan-manager.png" "$ICON_PNG_DIR/fresh-fan-manager.png" 2>/dev/null || \
  $SUDO cp "$HERE/assets/fresh-fan-manager.png" "$ICON_PNG_DIR/fresh-fan-manager.png"
else
  $SUDO cp "$HERE/assets/fresh-fan-manager.png" "$ICON_PNG_DIR/fresh-fan-manager.png"
fi

echo "==> Installing desktop menu entry"
$SUDO cp "$HERE/autostart/fresh-fan-manager-menu.desktop" "$MENU"

echo "==> Installing autostart entry for current user"
mkdir -p "$AUTOSTART_DIR"
cp "$HERE/autostart/fresh-fan-manager.desktop" "$AUTOSTART"
if [ "$(id -u)" -eq 0 ]; then
  chown "$REAL_USER:$(id -gn "$REAL_USER")" "$AUTOSTART_DIR" "$AUTOSTART"
fi

# Install systemd user service unit for headless daemon mode
if [ -f "$HERE/autostart/fresh-fan-daemon.service" ]; then
  SYSTEMD_USER_DIR="/usr/lib/systemd/user"
  if [ -d "$SYSTEMD_USER_DIR" ]; then
    $SUDO cp "$HERE/autostart/fresh-fan-daemon.service" "$SYSTEMD_USER_DIR/fresh-fan-daemon.service"
    $SUDO chmod 644 "$SYSTEMD_USER_DIR/fresh-fan-daemon.service"
  fi
fi

# Apple SMC check
if [ -f /sys/devices/platform/applesmc.768/fan1_manual ] || [ -f /sys/devices/platform/applesmc/fan1_manual ]; then
  echo "==> Apple SMC detected; enabling mbpfan service"
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now mbpfan 2>/dev/null || true
fi

echo "==> Updating desktop databases and icon caches"
$SUDO update-desktop-database /usr/share/applications 2>/dev/null || true
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  $SUDO gtk-update-icon-cache -t -f /usr/share/icons/hicolor 2>/dev/null || true
fi
if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 --noincremental 2>/dev/null || true
elif command -v kbuildsycoca5 >/dev/null 2>&1; then
  kbuildsycoca5 --noincremental 2>/dev/null || true
fi
rm -f "$REAL_HOME/.cache/ksycoca6_"* "$REAL_HOME/.cache/ksycoca5_"* 2>/dev/null || true
rm -rf "$REAL_HOME/.cache/icon-cache.kcache" 2>/dev/null || true

echo
echo "=========================================================="
echo "  ✔ Fresh Fan Manager installed successfully!"
echo "=========================================================="
echo
echo "Launch graphical interface:  fresh-fan-manager"
echo "Launch as desktop widget:    fresh-fan-manager --widget"
echo "Launch in system tray:       fresh-fan-manager --tray"
echo "Run headless background:     fresh-fan-manager --daemon"
echo
echo "Systemd service (headless):  systemctl --user enable --now fresh-fan-daemon.service"
echo
