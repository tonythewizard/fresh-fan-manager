#!/usr/bin/env bash
set -e
if [ "$(id -u)" -eq 0 ]; then
  echo "Do NOT run as root. It will sudo where needed."
  exit 1
fi

echo "==> Removing system files"
sudo rm -rf /opt/fresh-fan-manager
sudo rm -f /usr/local/bin/fresh-fan-manager
sudo rm -f /usr/local/bin/macfan-helper
sudo rm -f /usr/share/polkit-1/actions/org.freshfan.manager.policy
sudo rm -f /usr/share/polkit-1/actions/org.macfan.monitor.policy
sudo rm -f /usr/share/applications/fresh-fan-manager.desktop
sudo rm -f /usr/share/icons/hicolor/256x256/apps/fresh-fan-manager.png

echo "==> Removing user files"
rm -f "$HOME/.config/autostart/fresh-fan-manager.desktop"
rm -f "$HOME/.config/autostart/macfan-monitor.desktop"

read -rp "Rimuovere anche log e settings in ~/.local/share e ~/.config? [y/N] " ans
if [[ "$ans" =~ ^[yY]$ ]]; then
  rm -rf "$HOME/.local/share/macfan-monitor" "$HOME/.local/share/fresh-fan-manager"
  rm -rf "$HOME/.config/macfan-monitor" "$HOME/.config/fresh-fan-manager"
fi

echo "✔  Uninstall complete."
