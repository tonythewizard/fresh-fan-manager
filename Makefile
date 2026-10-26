# Fresh Fan Manager Makefile
.PHONY: help install update uninstall test deb arch rpm all-pkgs clean screenshots layouts

PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

VERSION := 2.0.0

help:
	@echo "Fresh Fan Manager — Build and Installation Targets"
	@echo ""
	@echo "  make install     Install to system via install.sh (sudo will be prompted)"
	@echo "  make uninstall   Uninstall from system via uninstall.sh"
	@echo "  make test        Compile check and offscreen test suite"
	@echo "  make deb         Build Debian/Ubuntu .deb package into dist/"
	@echo "  make arch        Build Arch Linux / CachyOS package via makepkg"
	@echo "  make rpm         Build Fedora/RHEL/openSUSE RPM package into dist/"
	@echo "  make all-pkgs    Build all pre-compiled packages into dist/"
	@echo "  make clean       Remove temporary build artifacts and pycache"
	@echo ""

install:
	./install.sh

uninstall:
	./uninstall.sh

test:
	$(PYTHON) -m py_compile fresh_fan_manager.py bin/macfan-helper core/*.py ui/*.py
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m unittest discover -s tests -v
	for script in install.sh uninstall.sh tools/*.sh PKGBUILD; do bash -n "$$script" || exit; done
	@if [ "$$(uname -m)" = x86_64 ]; then gcc -Wall -Wextra -Werror -fsyntax-only native/smc_port_lib.c; else echo "Native x86 SMC source is not built on this architecture"; fi

update:
	./install.sh

layouts:
	QT_QPA_PLATFORM=offscreen $(PYTHON) tools/check_layouts.py

screenshots:
	QT_QPA_PLATFORM=offscreen $(PYTHON) tools/screenshots.py

deb:
	./tools/build_deb.sh

arch:
	makepkg -df
	mkdir -p dist
	mv -f fresh-fan-manager-*.pkg.tar.zst dist/ 2>/dev/null || true
	rm -rf src pkg

rpm:
	./tools/build_rpm.sh

all-pkgs: deb arch rpm
	@echo ""
	@echo "✔ All pre-compiled packages generated in dist/:"
	@ls -lh dist/

clean:
	rm -rf dist/ build/ *.egg-info src pkg .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
