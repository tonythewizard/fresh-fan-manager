# Licensing and third-party components

Fresh Fan Manager is distributed under **GPL-3.0-or-later**. The full license
is in `LICENSE`; project metadata and source SPDX identifiers use the same expression.
Copyright notices already present in source files are retained. This maintenance
work does not change the project's license or claim ownership of earlier work.

Runtime dependencies are obtained separately from the distribution or Python
package index; the source repository does not vendor their implementations.

| Component | Upstream terms | Distribution here |
| --- | --- | --- |
| PySide6 / Shiboken6 / Qt | LGPLv3, GPLv3 or commercial terms, depending on component | System dependency or separately installed Python wheels |
| psutil | BSD 3-Clause | System/Python dependency |
| Python | PSF license | System interpreter |
| mbpfan | GPLv3 | Optional external daemon, not bundled |
| stress-ng | GPLv2 or later, with component notices | Optional external executable, not bundled |
| Linux sysfs, ioctl and port I/O interfaces | Kernel interfaces | Accessed by the project's own helper and C library; no kernel binary bundled |

PySide6 is used dynamically. Packages include the project's GPL text and this
notice; source archives include the editable Python/helper/C sources. The installer
may install third-party wheels into a virtual environment: retain the accompanying
license files and notices when redistributing that environment. This repository's
wheel does not include Qt wheels or the native helper library.

The native SMC implementation follows the hardware protocol, but the handoff does
not document the provenance of every earlier implementation detail. No assertion
of a complete third-party source provenance audit is made. Before distributing
modified third-party code, preserve its original copyright and license notices.

Upstream references checked during the roadmap review:

- [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html)
- [psutil license](https://github.com/giampaolo/psutil/blob/master/LICENSE)
- [mbpfan license](https://github.com/linux-on-mac/mbpfan/blob/master/COPYING)
- [stress-ng license notices](https://github.com/ColinIanKing/stress-ng/blob/master/COPYING)

This is an inventory of distribution choices and notices, not a change of license.
