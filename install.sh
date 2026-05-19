#!/usr/bin/env bash
#
# Installer for Fresh Fan Manager on Parrot OS / Debian-based systems.
#
set -e

if [ "$(id -u)" -eq 0 ]; then
  echo "Do NOT run install.sh as root. It will sudo where needed."
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="/opt/fresh-fan-manager"
LAUNCHER="/usr/local/bin/fresh-fan-manager"
HELPER="/usr/local/bin/macfan-helper"
POLICY="/usr/share/polkit-1/actions/org.freshfan.manager.policy"
MENU="/usr/share/applications/fresh-fan-manager.desktop"
AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART="$AUTOSTART_DIR/fresh-fan-manager.desktop"
ICON_PNG_DIR="/usr/share/icons/hicolor/256x256/apps"

echo "==> Installing system dependencies"
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv mbpfan lm-sensors libnotify-bin stress-ng
# Try to install PySide6 + psutil from apt (so we don't depend on pip working)
sudo apt-get install -y python3-psutil 2>/dev/null || true
sudo apt-get install -y python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets 2>/dev/null || true
if ! sudo apt-get install -y polkitd pkexec 2>/dev/null; then
  echo "    (polkitd/pkexec not available as separate packages, trying policykit-1)"
  sudo apt-get install -y policykit-1
fi

echo "==> Removing old MacFan Monitor install (if present)"
sudo rm -rf /opt/macfan-monitor 2>/dev/null || true
sudo rm -f /usr/local/bin/macfan-monitor
sudo rm -f /usr/share/applications/macfan-monitor.desktop
sudo rm -f /usr/share/icons/hicolor/256x256/apps/macfan-monitor.png
rm -f "$HOME/.config/autostart/macfan-monitor.desktop"
rm -f "$HOME/.local/share/applications/macfan-monitor.desktop"
rm -f "$HOME/.local/share/applications/fresh-fan-manager.desktop"  # any stale user copy
sudo rm -f /usr/share/polkit-1/actions/org.macfan.monitor.policy

echo "==> Creating $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo cp -r "$HERE/core" "$HERE/ui" "$HERE/assets" "$HERE/fresh_fan_manager.py" "$APP_DIR/"
sudo chmod 755 "$APP_DIR" "$APP_DIR/core" "$APP_DIR/ui" "$APP_DIR/assets"
sudo find "$APP_DIR" -type f -exec chmod 644 {} +
sudo chmod 755 "$APP_DIR/fresh_fan_manager.py"

echo "==> Setting up a Python venv at $APP_DIR/.venv (with system site-packages)"
# Use --system-site-packages so apt-installed deps (PySide6, psutil) are available
# without needing pip at all. Try --upgrade-deps first for a fresh pip if possible.
sudo python3 -m venv --system-site-packages --upgrade-deps "$APP_DIR/.venv" 2>/dev/null \
    || sudo python3 -m venv --system-site-packages "$APP_DIR/.venv" \
    || sudo python3 -m venv "$APP_DIR/.venv"

VENV_PY="$APP_DIR/.venv/bin/python"
VENV_PIP="$APP_DIR/.venv/bin/pip"

# Bootstrap pip if missing in the venv (Debian/Parrot sometimes strips it)
if [ ! -x "$VENV_PIP" ]; then
    echo "==> pip mancante nel venv, bootstrap via ensurepip"
    sudo "$VENV_PY" -m ensurepip --upgrade 2>/dev/null || true
fi
if [ ! -x "$VENV_PIP" ]; then
    echo "==> ensurepip non disponibile, scarico get-pip.py"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
    fi
    [ -f /tmp/get-pip.py ] && sudo "$VENV_PY" /tmp/get-pip.py 2>/dev/null || true
    rm -f /tmp/get-pip.py
fi

# Verify what we have available from the venv (could be from system or pip)
echo "==> Verifying Python dependencies in venv"
MISSING=()
if ! sudo "$VENV_PY" -c "import PySide6.QtWidgets" 2>/dev/null; then MISSING+=(PySide6); fi
if ! sudo "$VENV_PY" -c "import psutil" 2>/dev/null; then MISSING+=(psutil); fi

if [ ${#MISSING[@]} -gt 0 ]; then
    if [ -x "$VENV_PIP" ]; then
        echo "==> Installing missing modules with pip: ${MISSING[*]}"
        sudo "$VENV_PIP" install --upgrade pip 2>/dev/null || true
        sudo "$VENV_PIP" install -r "$HERE/requirements.txt"
    else
        echo "ERRORE: moduli mancanti (${MISSING[*]}) e pip non disponibile."
        echo "Soluzione: sudo apt install --reinstall python3-venv python3-pip"
        echo "  oppure:  sudo apt install python3-pyside6.qtwidgets python3-psutil"
        exit 1
    fi
fi

echo "==> Installing launcher at $LAUNCHER"
sudo tee "$LAUNCHER" > /dev/null <<EOF
#!/usr/bin/env bash
exec "$APP_DIR/.venv/bin/python" "$APP_DIR/fresh_fan_manager.py" "\$@"
EOF
sudo chmod 755 "$LAUNCHER"

echo "==> Installing privileged helper at $HELPER"
sudo cp "$HERE/bin/macfan-helper" "$HELPER"
sudo chown root:root "$HELPER"
sudo chmod 755 "$HELPER"

echo "==> Installing polkit policy"
sudo cp "$HERE/policies/org.freshfan.manager.policy" "$POLICY"
sudo chown root:root "$POLICY"
sudo chmod 644 "$POLICY"

echo "==> Installing application icon"
sudo mkdir -p "$ICON_PNG_DIR"
# Render icon PNGs at every standard hicolor size from scratch (no resize
# scaling artefacts). Each size has the snowflake glyph filling the frame
# at ~98% so the menu/taskbar shows a big crisp fiocco instead of a tiny
# glyph in a padded box.
PYBIN="$(command -v python3)"
if [ -n "$PYBIN" ]; then
  for SIZE in 16 22 24 32 40 48 64 96 128 192 256 384 512; do
    SDIR="/usr/share/icons/hicolor/${SIZE}x${SIZE}/apps"
    sudo mkdir -p "$SDIR"
    TMP="/tmp/fresh-fan-${SIZE}.png"
    QT_QPA_PLATFORM=offscreen "$PYBIN" - "$TMP" "$SIZE" <<'PYGEN' 2>/dev/null || true
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
      sudo cp "$TMP" "$SDIR/fresh-fan-manager.png"
      rm -f "$TMP"
    fi
  done
  # Also copy the largest size as the legacy single-PNG path
  sudo cp "/usr/share/icons/hicolor/512x512/apps/fresh-fan-manager.png" \
          "$ICON_PNG_DIR/fresh-fan-manager.png" 2>/dev/null || \
  sudo cp "$HERE/assets/fresh-fan-manager.png" "$ICON_PNG_DIR/fresh-fan-manager.png"
else
  # Fallback if python3 missing for some reason: just install the asset
  sudo cp "$HERE/assets/fresh-fan-manager.png" "$ICON_PNG_DIR/fresh-fan-manager.png"
fi
# Refresh icon caches so the menu/taskbar pick the new icon immediately
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  sudo gtk-update-icon-cache -t -f /usr/share/icons/hicolor 2>/dev/null || true
fi
rm -rf "$HOME/.cache/icon-cache.kcache" 2>/dev/null || true
# KDE Plasma may cache via kiconcache too
rm -rf "$HOME/.cache/ksycoca6"* 2>/dev/null || true

echo "==> Installing menu entry"
sudo cp "$HERE/autostart/fresh-fan-manager-menu.desktop" "$MENU"

echo "==> Installing autostart entry (current user)"
mkdir -p "$AUTOSTART_DIR"
cp "$HERE/autostart/fresh-fan-manager.desktop" "$AUTOSTART"

echo "==> Ensuring mbpfan service is enabled"
sudo systemctl enable mbpfan 2>/dev/null || true

echo "==> Refreshing desktop and icon caches"
sudo update-desktop-database /usr/share/applications 2>/dev/null || true
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  sudo gtk-update-icon-cache -t -f /usr/share/icons/hicolor 2>/dev/null || true
fi
# KDE-specific menu cache refresh
if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 --noincremental 2>/dev/null || true
elif command -v kbuildsycoca5 >/dev/null 2>&1; then
  kbuildsycoca5 --noincremental 2>/dev/null || true
fi
# Also clear the user-level ksycoca cache (KDE menu cache)
rm -f "$HOME/.cache/ksycoca6_"* "$HOME/.cache/ksycoca5_"* 2>/dev/null || true

echo
echo "✔  Installation complete."
echo
echo "Run now with:   fresh-fan-manager"
echo "Widget mode:    fresh-fan-manager --widget"
echo "Tray only:      fresh-fan-manager --tray"
echo
echo "It will auto-start on next login in widget mode."
