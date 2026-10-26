# Maintainer: Antonio Gullotta <antonio@freshlinux.org>
pkgname=fresh-fan-manager
pkgver=2.0.0
pkgrel=1
pkgdesc="Universal Linux fan and hardware temperature monitor with adaptive cooling backends"
arch=('x86_64' 'aarch64')
url="https://github.com/tonythewizard/fresh-fan-manager"
license=('GPL-3.0-or-later')
depends=('python' 'python-psutil' 'lm_sensors' 'polkit' 'pyside6')
optdepends=(
    'mbpfan: optional external mbpfan daemon integration'
    'smartmontools: disk SMART metrics reading'
    'stress-ng: CPU stress testing utility'
    'libnotify: desktop notifications'
)
source=()
sha256sums=()

package() {
    cd "${startdir}"

    install -d "${pkgdir}/opt/fresh-fan-manager/bin"
    install -d "${pkgdir}/usr/local/bin"
    if [ "$CARCH" = x86_64 ]; then
        gcc -O2 -fPIC -shared native/smc_port_lib.c -o "${pkgdir}/opt/fresh-fan-manager/bin/libsmc_port.so"
        chmod 755 "${pkgdir}/opt/fresh-fan-manager/bin/libsmc_port.so"
    fi
    install -m 644 LICENSE THIRD_PARTY_NOTICES.md "${pkgdir}/opt/fresh-fan-manager/"
    cp -r core ui assets "${pkgdir}/opt/fresh-fan-manager/"
    install -m 755 fresh_fan_manager.py "${pkgdir}/opt/fresh-fan-manager/"
    install -m 755 bin/freshfan-helper "${pkgdir}/opt/fresh-fan-manager/bin/freshfan-helper"
    ln -sf freshfan-helper "${pkgdir}/opt/fresh-fan-manager/bin/macfan-helper"

    # Clean pycache from pkgdir
    find "${pkgdir}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "${pkgdir}" -type f -name "*.pyc" -delete 2>/dev/null || true

    # System launchers
    install -d "${pkgdir}/usr/bin"
    cat > "${pkgdir}/usr/bin/fresh-fan-manager" <<'EOF'
#!/usr/bin/env bash
if [ -x "/opt/fresh-fan-manager/.venv/bin/python" ]; then
  exec "/opt/fresh-fan-manager/.venv/bin/python" "/opt/fresh-fan-manager/fresh_fan_manager.py" "$@"
else
  exec python3 "/opt/fresh-fan-manager/fresh_fan_manager.py" "$@"
fi
EOF
    chmod 755 "${pkgdir}/usr/bin/fresh-fan-manager"

    # Privileged helpers
    install -d "${pkgdir}/usr/local/bin"
    install -m 755 bin/freshfan-helper "${pkgdir}/usr/local/bin/freshfan-helper"
    ln -sf freshfan-helper "${pkgdir}/usr/local/bin/macfan-helper"

    # Polkit policy
    install -d "${pkgdir}/usr/share/polkit-1/actions"
    install -m 644 policies/org.freshfan.manager.policy "${pkgdir}/usr/share/polkit-1/actions/"

    # Desktop entry & icons
    install -d "${pkgdir}/usr/share/applications"
    install -m 644 autostart/fresh-fan-manager-menu.desktop "${pkgdir}/usr/share/applications/fresh-fan-manager.desktop"

    install -d "${pkgdir}/usr/share/icons/hicolor/256x256/apps"
    install -m 644 assets/fresh-fan-manager.png "${pkgdir}/usr/share/icons/hicolor/256x256/apps/"

    # Systemd user service
    if [ -f autostart/fresh-fan-daemon.service ]; then
        install -d "${pkgdir}/usr/lib/systemd/user"
        install -m 644 autostart/fresh-fan-daemon.service "${pkgdir}/usr/lib/systemd/user/"
    fi

    # Udev rule for macsmc /dev/smc
    install -d "${pkgdir}/usr/lib/udev/rules.d"
    cat > "${pkgdir}/usr/lib/udev/rules.d/99-macsmc.rules" <<'EOF'
# Apple SMC device permissions for Fresh Fan Manager
KERNEL=="smc", SUBSYSTEM=="misc", MODE="0644"
EOF
    chmod 644 "${pkgdir}/usr/lib/udev/rules.d/99-macsmc.rules"
}
