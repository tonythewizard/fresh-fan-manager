# Fresh Fan Manager

Monitor di temperatura, ventola, CPU/GPU/RAM per MacBook su Linux (Parrot OS, KDE/Wayland).
Integrazione completa con `mbpfan` + override manuale + curva personalizzata + stress test.

## Caratteristiche principali

**Monitoraggio live**
- ❄ Icona snowflake che cambia colore in base alla temperatura CPU, sia in taskbar che nel tray
- Temperatura CPU (max core + per-core + package) con sparkline 60s
- RPM ventola con barra min→max e sparkline
- Carico CPU totale + per core, frequenza, governor (cambiabile)
- **Pannello Top processi** (top 5 per CPU%, aggiornato ogni 2.5s)
- **Monitor RAM completo**: usata/totale, swap, disponibile, sparkline
- GPU Intel HD 6000 (frequenza + busy%)
- Batteria: %, tempo rimanente, temperatura, stato carica

**Gestione mbpfan**
- Check auto-install, stato servizio colorato
- 3 preset rapidi: Silent / Balanced / Performance
- **Editor curva ventola personalizzato** (drag&drop su grafico temp/RPM)
- Editor parametri numerici (tweak dialog)
- Riavvio servizio one-click

**Override manuale ventola**
- Spostato nella sezione Ventola, con badge ON/OFF e slider RPM
- **Safety watchdog**: se la CPU supera la soglia configurabile (default 70°C)
  l'app riporta automaticamente in auto e mostra notifica
- Soglia personalizzabile dalle Preferenze

**Stress test integrato**
- Tre durate: 30s / 60s / 90s
- Usa `stress-ng` (se installato), fallback a `stress`, ultima risorsa Python puro
- Barra di progresso in tempo reale + tasto Stop

**Allerta temperatura**
- Soglia personalizzabile dalle Preferenze (default 85°C)
- Toggleable dal pulsante in basso a sinistra

**Server grafico**
- Switch Wayland nativo / XWayland (xcb) dalle Preferenze
- xcb richiesto per la modalità widget pinnata

**UI**
- Frameless + translucida (rotellina mouse o tasto destro → trasparenza)
- Tasti finestra custom: chiudi (→ tray), riduci, ingrandisci, **pin al desktop**
- Modalità widget pinnata in alto a destra sotto la barra Parrot
- System tray sempre attivo, l'unico modo per uscire davvero

**Autostart** al login in modalità widget, gestito via `~/.config/autostart/`.

## Installazione

```bash
chmod +x install.sh
./install.sh
```

Lo script:
1. Installa dipendenze APT (`mbpfan`, `lm-sensors`, `stress-ng`, `polkitd`, `pkexec`, `libnotify-bin`)
2. Rimuove eventuali installazioni precedenti di MacFan Monitor (rename)
3. Crea `/opt/fresh-fan-manager/` con virtualenv dedicato
4. Installa launcher `fresh-fan-manager`, helper privilegiato, policy polkit
5. Registra autostart in modalità widget
6. Registra entry nel menu applicazioni con icona

## Uso

```bash
fresh-fan-manager              # finestra normale
fresh-fan-manager --widget     # widget pinnato (xcb)
fresh-fan-manager --tray       # solo tray
```

## Architettura

```
/opt/fresh-fan-manager/
├── fresh_fan_manager.py
├── core/
│   ├── sensors.py             temp/RPM/CPU/GPU/RAM/top-procs
│   ├── mbpfan_ctrl.py         status, conf, preset, manual on/off
│   ├── governor.py            CPU governor switch
│   ├── stress.py              stress-ng wrapper
│   ├── logger.py              rotating log
│   └── config.py              settings JSON
└── ui/
    ├── main_window.py         finestra principale
    ├── titlebar.py            barra titolo custom
    ├── sparkline.py           grafico mini
    ├── icons.py               snowflake glyph
    ├── tweaks_dialog.py
    ├── curve_editor.py        editor visuale curva
    ├── preferences_dialog.py
    ├── log_dialog.py
    ├── tray.py
    └── styles.py

/usr/local/bin/macfan-helper          dispatcher root via pkexec
/usr/share/polkit-1/actions/...       policy
~/.config/fresh-fan-manager/          settings utente
~/.local/share/fresh-fan-manager/     log rotante
```

## Disinstallazione

```bash
./uninstall.sh
```

## Crediti

- Daemon ventola: [mbpfan](https://github.com/dgraziotin/mbpfan)
  di Daniel Graziotin (GPL-2.0)
- UI framework: [Qt for Python (PySide6)](https://www.qt.io/qt-for-python)
- Sensori sistema: [psutil](https://github.com/giampaolo/psutil)

## Contribuire

Pull request benvenute. Per cambiamenti importanti apri prima una issue
per discutere cosa cambiare. Per i bug usa il template "Bug report",
per nuove feature il template "Feature request".

## Licenza

Questo progetto è distribuito sotto licenza **GNU General Public License v3.0**
(GPL-3.0). Vedi il file [`LICENSE`](LICENSE) per il testo completo.

```
Fresh Fan Manager — Linux fan and temperature control utility
Copyright (C) 2025  Antonio Gullotta

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```
