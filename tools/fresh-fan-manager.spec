Name:           fresh-fan-manager
Version:        2.0.0
Release:        1%{?dist}
Summary:        Universal Linux fan and hardware temperature monitor with adaptive cooling backends
License:        GPL-3.0-or-later
URL:            https://github.com/tonythewizard/fresh-fan-manager
Source0:        %{name}-%{version}.tar.gz
BuildRequires:  gcc
BuildRequires:  make

Requires:       python3 >= 3.9
Requires:       python3-psutil
Requires:       python3-pyside6
Requires:       lm_sensors
Requires:       libnotify
Requires:       polkit

Recommends:     smartmontools
Recommends:     stress-ng

%description
Fresh Fan Manager is a modern hardware telemetry and fan control utility
supporting Lenovo ThinkPad, ASUS, Dell, Apple Mac, Framework, and generic Linux PWM.
Includes real-time CPU, GPU, RAM, storage, and battery metrics with desktop widget
and headless background daemon modes.

%prep
%setup -q

%build
%ifarch x86_64
%{__cc} %{optflags} -Wall -Wextra -fPIC -shared native/smc_port_lib.c -o libsmc_port.so %{?build_ldflags}
%endif

%install
mkdir -p %{buildroot}/opt/%{name}/bin
mkdir -p %{buildroot}%{_bindir}
mkdir -p %{buildroot}/usr/local/bin
mkdir -p %{buildroot}%{_datadir}/applications
mkdir -p %{buildroot}%{_datadir}/polkit-1/actions
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/256x256/apps
mkdir -p %{buildroot}/usr/lib/systemd/user

install -m 644 LICENSE THIRD_PARTY_NOTICES.md %{buildroot}/opt/%{name}/
%ifarch x86_64
install -m 755 libsmc_port.so %{buildroot}/opt/%{name}/bin/
%endif
mkdir -p %{buildroot}/usr/lib/udev/rules.d
printf '%s\n' 'KERNEL=="smc", SUBSYSTEM=="misc", MODE="0644"' > %{buildroot}/usr/lib/udev/rules.d/99-macsmc.rules
cp -r core ui assets %{buildroot}/opt/%{name}/
install -m 755 fresh_fan_manager.py %{buildroot}/opt/%{name}/
install -m 755 bin/freshfan-helper %{buildroot}/opt/%{name}/bin/freshfan-helper
ln -sf freshfan-helper %{buildroot}/opt/%{name}/bin/macfan-helper

# Clean pycache
find %{buildroot} -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find %{buildroot} -type f -name "*.pyc" -delete 2>/dev/null || true

# Launcher script
cat > %{buildroot}%{_bindir}/%{name} << 'EOF'
#!/usr/bin/env bash
if [ -x "/opt/fresh-fan-manager/.venv/bin/python" ]; then
  exec "/opt/fresh-fan-manager/.venv/bin/python" "/opt/fresh-fan-manager/fresh_fan_manager.py" "$@"
else
  exec python3 "/opt/fresh-fan-manager/fresh_fan_manager.py" "$@"
fi
EOF
chmod 755 %{buildroot}%{_bindir}/%{name}

# Privileged helper
install -m 755 bin/freshfan-helper %{buildroot}/usr/local/bin/freshfan-helper
ln -sf freshfan-helper %{buildroot}/usr/local/bin/macfan-helper

# Polkit & Desktop Integration
install -m 644 policies/org.freshfan.manager.policy %{buildroot}%{_datadir}/polkit-1/actions/
install -m 644 autostart/fresh-fan-manager-menu.desktop %{buildroot}%{_datadir}/applications/%{name}.desktop
install -m 644 assets/fresh-fan-manager.png %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/%{name}.png
install -m 644 autostart/fresh-fan-daemon.service %{buildroot}/usr/lib/systemd/user/fresh-fan-daemon.service

%files
/opt/%{name}
/usr/lib/udev/rules.d/99-macsmc.rules
%{_bindir}/%{name}
/usr/local/bin/freshfan-helper
/usr/local/bin/macfan-helper
%{_datadir}/polkit-1/actions/org.freshfan.manager.policy
%{_datadir}/applications/%{name}.desktop
%{_datadir}/icons/hicolor/256x256/apps/%{name}.png
/usr/lib/systemd/user/fresh-fan-daemon.service

%post
/usr/bin/update-desktop-database &> /dev/null || :
/bin/touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :
/usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :

%changelog
* Sun Oct 25 2026 Antonio Gullotta <antonio@freshlinux.org> - 2.0.0-1
- Universal hardware support (ThinkPad, ASUS, Dell, Apple, PWM)
- Headless daemon mode and systemd user service
- Internationalization with English default and Italian support
