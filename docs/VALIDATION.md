# Validation report — 26 October 2026

This report describes checks performed on the local Fresh Fan Manager 2.0.0
checkout. It separates automated results from hardware/session claims.
This report records the checks performed before the v2.0.0 publication.
No package was installed into the host system and `/opt` was not updated.

## Automated regression suite

`make test` runs **39 tests** across release metadata, controller safety, backend
routing, user cleanup, SMC encoding, exclusive ownership, Qt rendering, update
responses, stress cancellation and geometry. The suite was exercised with
`QT_QPA_PLATFORM=offscreen` and Qt scales **100%, 125% and 150%**.

Covered cases include:

- A thermal trip cannot immediately reapply the daemon's manual target.
- Missing temperature restores manual fans; failed writes remain retryable.
- Multiple fans, hidden fan card, failed automatic mode and daemon hysteresis.
- GUI macsmc override, full and absent telemetry, theme/mode/reorder changes.
- CPU/RAM values do not retain stale displayed values after a missing sample.
- PWM mode failures, vendor-specific preset routing and read-only firmware fallback.
- Btrfs/NVMe/mmc root-device parsing and fpe2 RPM round trips.
- Root library trust checks, hwmon traversal rejection, unprivileged cleanup symlinks.
- Release version ordering, draft/prerelease rejection and official URL filtering.
- No network on the default schedule; daily/weekly timing and clock rollback.
- Inactivity timeout and absolute request deadline, HTTP 404/429, malformed JSON, oversized response and normal update response.
- Markdown release notes cannot load local or remote resources.
- Dirty Git checkouts are refused without deleting local files or contacting a remote.
- A real, short two-worker Python fallback workload is stopped as a process group,
  with one completion signal and no surviving CPU-burning children.

Additional checks: Python compilation, **each** shell script and PKGBUILD parsed
separately with `bash -n`, C compiled with `-Wall -Wextra -Werror`, CLI help/version,
Polkit XML parsing and `git diff --check`.

## Exhaustive layout check

```bash
make layouts
```

All **4096 visibility combinations** of the actual 12 Qt cards passed. For each:

- The last visible card ends exactly at the configured bottom padding (4 pixels).
- Fully extended content does not leave a redundant scrollbar.
- Width stays at 360 logical pixels.
- Stop bounds fit work-area heights 768, 900, 1080, 1440 and 2160.
- Empty and one-card layouts retain valid constraints.

The regular suite also checks snapping from both resize edges, Essentials/All,
edit mode, reordering and six themes. These are logical/offscreen checks, not
measurements of drag feel on physical 4K displays or every window manager.

## Network and local telemetry

The repository from local `origin`, `tonythewizard/fresh-fan-manager`, returned
HTTP 200 for repository metadata. The previous FreshLinux repository URL returned
HTTP 404. A real asynchronous Qt request to the current repository's latest-release
endpoint finished with HTTP **404**, handled without a modal error or UI hang.
Release-available behavior is tested with fixtures rather than claiming a published release.

A live **read-only** snapshot detected:

| Metric | Result |
| --- | --- |
| Cooling backend | macsmc |
| CPU temperature | available |
| Fans | one detected |
| Memory | available |
| GPU telemetry object | available; individual fields depend on the driver |
| Network sample | available |
| Battery | absent, handled |
| Disk | unavailable in this session, handled |

No fan RPM, governor, turbo, brightness, volume, sysfs, udev or system cleanup
write was performed on the host during these checks. The short stress cancellation
test ran only its own child processes. Historical handoff claims about a different
mount/session are not substituted for current evidence.

## Packaging and artifacts

Local builds were performed for:

| Artifact | Verification |
| --- | --- |
| Debian amd64 | `make deb`, tar/ar fallback; control architecture and archive contents checked |
| Arch x86_64 | `make arch`, native makepkg build; `.PKGINFO` and payload checked |
| RPM x86_64 | `make rpm` with isolated RPM tools; package architecture and payload checked |
| Python wheel / source | `python -m build`; metadata, license notices and source contents checked |

RPM tooling was downloaded from the distribution's package mirrors and extracted
under `/tmp/ffm-rpm-tools`. No host packages were installed. The isolated wrapper
used `--nodeps` because it has no system RPM dependency database; gcc and the
required tools were present and the actual native compilation/package stages ran.
This is a build check, not an installation test on Fedora/openSUSE.

`dist/` contains rebuilt local artifacts. Older architecture-independent Debian
and Arch artifacts are retained in `dist/previous-builds/` to avoid confusing them
with the new native-architecture packages. The artifacts were not installed on the host; release uploads are handled by GitHub Actions.

## Documentation, screenshots and licensing

`make screenshots` produced ten 2× Qt PNGs from synthetic data: all six themes,
Essentials, edit mode, pinned-widget preview and mini window. The pinned preview
shows the UI, not proof of compositor-level wallpaper pinning.

README, roadmap and handoff match current behavior and the real repository URL.
English GitHub About text and topics are recorded in `docs/GITHUB_ABOUT.md`.
GPL-3.0-or-later metadata, SPDX source markers, package license texts and the
third-party inventory are aligned. Existing copyright attribution is preserved.
The native code's prior provenance is not fully established by the old handoff;
this work does not claim an exhaustive legal/provenance audit.

## Limits of this validation

Physical fan-control writes on ThinkPad, ASUS, Dell, generic PWM, T2/Apple Silicon
and the current Intel SMC were not exercised. Neither were all supported Linux
distributions, ARM builds, graphical sessions or an installed update from a future
GitHub release. GUI/daemon write operations still depend on Polkit authorization;
a headless session without an agent can fail and will log the failure.
The lease is per user, so independent users or external fan daemons must still be
configured to avoid competing hardware control. Raw SMC port I/O is an optional,
driver-specific fallback and cannot share a userspace lock with a kernel driver.

These limitations remain explicit; they are not represented as completed physical
certification. The local implementation, documentation and reproducible checks
requested by the roadmap are complete. Release publication is handled separately by GitHub Actions.
