# Fresh Fan Manager — Roadmap and delivery status

Updated **26 October 2026** for **v2.0.0**. Local implementation is complete;
automated evidence and physical-validation limits are recorded separately.
Release publication is handled by the GitHub Actions release workflow.

## 1. Widget functionality and validation

- [x] CPU/governor rendering with complete and missing samples; available profiles and top-processes dialog.
- [x] Multi-backend cooling, macsmc UI access, manual override and failed-command handling.
- [x] Thermal safety for detected manual fans, missing sensors and multiple fans, with daemon hysteresis and restoration of owned controls.
- [x] Separate privileged system cleanup and unprivileged user cleanup; symlink and command-error regression coverage.
- [x] RAM/swap/zram, GPU, battery absence, power, network, core heatmap, throttling and disk rendering with reproducible telemetry fixtures.
- [x] Btrfs, NVMe and mmc root-device parsing regressions.
- [x] Quick-control and preset routing/error coverage without changing host controls during tests.
- [x] Bounded stress test, thermal/missing-sensor stop and full process-group cancellation.
- [x] Live read-only CPU, macsmc, RAM, GPU and network sampling; absent battery and unavailable disk handled.
- [x] Repeatable `make test` independent of the `/opt` installation, with Python, Qt, shell and C checks.

Historical field-test checkmarks are not evidence for the new changes. No
privileged hardware or system-cleanup writes were performed during automated
validation. Physical multivendor and multidistribution checks require those devices
and environments.

## 2. Release checks and update actions

- [x] Asynchronous GitHub Releases API request with inactivity and absolute deadlines and a response-size limit.
- [x] Numeric stable-version comparison and rejection of drafts, prereleases and foreign download URLs.
- [x] Manual Preferences action and configurable daily/weekly checks; automatic network access initially disabled.
- [x] Offline, timeout, rate-limit, malformed JSON, oversized response and missing-release handling.
- [x] Discreet title-bar badge with the available version in its tooltip.
- [x] Markdown changelog with resource loading blocked; official package and release links.
- [x] Guarded Git update: expected origin, main branch, clean checkout, fast-forward pull and `make update`.
- [x] Browser downloads for package installations, leaving installation explicit.
- [x] Repository URLs aligned with the actual origin, `tonythewizard/fresh-fan-manager`.

The pre-publication live latest-release request returned 404; release-available
behavior was tested with fixtures. Publication makes the version available through
GitHub's release endpoints.

## 3. Vertical resizing and magnetic snap

- [x] Stop positions derived from real card dimensions and height-for-width behavior.
- [x] Removed estimated padding, trailing inter-card space and spurious scrollbars.
- [x] Fourteen-pixel threshold, nearest-stop selection and top/bottom-edge resizing.
- [x] Layout-change updates, fixed 360-pixel width and the window's monitor work area.
- [x] Essentials/All, editing, reordering, density, hidden cards, single-card and empty-layout cases.
- [x] Logical work areas of 768, 900, 1080, 1440 and 2160 pixels; Qt scales of 100%, 125% and 150%.
- [x] All 4096 visibility combinations of twelve cards, with exact final padding and bounds for five heights.

Geometry checks use Qt offscreen. Drag feel and compositor behavior still require
interactive testing; no certification of every display or desktop is claimed.

## 4. Repository presentation

- [x] English About description and topics recorded in `docs/GITHUB_ABOUT.md`.
- [x] Professional English README covering current features, eleven UI languages and six themes.
- [x] Hardware matrix with required interfaces and fallback behavior, without brand-only support promises.
- [x] Distribution, architecture and desktop-session matrices distinguishing build support from validated environments.
- [x] Reproducible 2× screenshots: complete dashboard, Essentials, customization, six themes, widget and mini monitor.
- [x] Synthetic screenshot data, with no personal network identifiers.
- [x] Installation, CLI, headless mode, updates, troubleshooting and removal instructions.
- [x] English handoff, roadmap, issue templates and public release notes.

## 5. License review

- [x] GPLv3 license text checked; existing source headers also permit later versions.
- [x] Retained `GPL-3.0-or-later`, with no change of project license.
- [x] Dependency inventory and upstream references in `THIRD_PARTY_NOTICES.md`.
- [x] Dynamic, separately obtained dependencies and preservation of their notices documented.
- [x] SPDX identifiers added to project sources while preserving existing attribution.
- [x] License and notices included in native packages, wheel and source distribution.
- [x] Limits of prior native-source provenance documented without claiming a complete legal audit.

## Additional delivery corrections

- [x] Removed privileged loading of a shared library from a user directory; verify installed library ownership and parent permissions.
- [x] Restricted raw-port fallback to x86 Apple hardware, with locking, original-minimum preservation and error propagation.
- [x] Changed SMC device rules from 0666 to 0644.
- [x] Validate hwmon names against path traversal.
- [x] Per-user controller lease to prevent GUI/daemon conflicts.
- [x] Correct native package architecture, service launcher resolution and uninstall coverage.
- [x] `make all-pkgs` includes RPM; corrected RPM staging and native compilation.
- [x] Local Debian/Arch/RPM and Python artifact builds verified without installing them on the host.
- [x] Release workflow gates publication on tests and native/Python build jobs, with checksum generation.

See [docs/VALIDATION.md](docs/VALIDATION.md) for commands, evidence and remaining
physical-validation limits.
