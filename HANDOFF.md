# Fresh Fan Manager — Development handoff

Updated: **26 October 2026** · version: **2.0.0**
Repository: https://github.com/tonythewizard/fresh-fan-manager

This document supersedes the original handoff, whose full-validation claim was
not supported by the tests available at that time. The local roadmap implementation
has been checked with automated tests, Qt rendering and native package builds.
Physical validation limits are recorded in [docs/VALIDATION.md](docs/VALIDATION.md).
The release workflow builds and publishes v2.0.0 after its checks succeed.

## Architecture

| Component | Responsibility |
| --- | --- |
| `fresh_fan_manager.py` | CLI and GUI startup; `--daemon` runs before Qt imports |
| `core/sensors.py` | psutil/sysfs/SMC telemetry and external-tool fallbacks |
| `core/mbpfan_ctrl.py` | Cooling backend detection and authenticated helper routing |
| `core/macsmc.py` | Driver-specific `/dev/smc` reads |
| `bin/macfan-helper` | Privileged dispatcher; `bin/freshfan-helper` is its checkout symlink |
| `native/smc_port_lib.c` | Optional x86 Intel Apple port fallback, compiled during installation or packaging |
| `core/daemon.py` | Thermal watchdog and explicit AppleSMC preset curve; restores owned controls |
| `core/runtime.py` | Per-user GUI/daemon controller lease |
| `core/updates.py`, `ui/update_controller.py` | Release versions, asynchronous requests, changelog and package links |
| `ui/main_window.py`, `ui/widget_manager.py` | Twelve cards, fixed 360-pixel width, views, resizing and customization |
| `tests/` | Regression suite without privileged hardware writes |
| `tools/check_layouts.py` | Exhaustive card-visibility geometry validation |
| `tools/screenshots.py` | Actual Qt screenshots with synthetic telemetry |

## Main corrections

1. Removed development-directory library loading from the root helper. The
   installed library and its parents must be root-owned and not writable by group
   or other users. Removed a duplicate raw-port fallback that hid failures.
2. Native SMC overrides save the original minimum under `/run`, serialize helper
   calls and propagate errors rather than assuming a universal 1200 RPM minimum.
3. Controller identifiers are validated; user cache directories are not cleaned as root.
4. The macsmc backend is enabled in the UI. Failed return-to-auto commands retain
   the watchdog state and are reported.
5. Thermal monitoring considers hardware-reported manual fans, works without a
   visible fan card, handles multiple fans and stops unsafe stress workloads.
6. The daemon does not immediately reapply a target after a safety trip or cache
   failed writes. Its per-user lease prevents GUI/daemon conflicts.
7. Stress cancellation terminates the entire workload process group.
8. Resize stops use actual card dimensions, including height-for-width behavior,
   avoiding spurious scrollbars and trailing space.
9. Manual/daily/weekly release checks, badge and Markdown notes are implemented;
   automatic network checks are off by default.
10. Packaging declares native architectures and QtNetwork dependencies correctly;
    RPM builds include source staging and native compilation.

## Reproducing validation and builds

```bash
make test
QT_SCALE_FACTOR=1.25 make test
QT_SCALE_FACTOR=1.5 make test
make layouts
make screenshots
make deb
make arch
make rpm
.venv/bin/python -m build
```

The test suite uses the checkout environment rather than `/opt`. Override its
Python interpreter with `PYTHON=...`. Native build targets need their respective
toolchains. Local RPM checks used isolated tools under `/tmp`, without installing
host packages, and skipped dependency-database checks for that isolated toolset.

Artifacts are written to `dist/`, which is excluded from Git. Local builds do not
replace the installation under `/opt`; a checkout frontend can still invoke an
older installed privileged helper. Install the matching package or use the source
installer when deploying the frontend and helper together.

The GitHub release workflow runs the regression matrix, builds Debian, Arch, RPM
and Python artifacts on appropriate runners, generates checksums and publishes
the version's English notes from `docs/releases/`.

## Reference documents

- [Roadmap](roadmap.md): implementation checklist and validation limits.
- [Validation report](docs/VALIDATION.md): evidence and reproducible commands.
- [README](README.md): screenshots, compatibility, installation and usage.
- [GitHub metadata](docs/GITHUB_ABOUT.md): recommended English description and topics.
- [Third-party notices](THIRD_PARTY_NOTICES.md): dependency licenses and provenance limits.
- [Release notes](docs/releases/v2.0.0.md): public v2.0.0 summary.

Live read-only sampling detected macsmc, CPU temperature, one fan, RAM, GPU and
network data. Battery absence and unavailable disk data were handled without a
crash. Results on that system do not certify other vendors or physical control paths.
