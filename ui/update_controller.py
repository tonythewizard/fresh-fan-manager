# SPDX-License-Identifier: GPL-3.0-or-later
"""Asynchronous, opt-in GitHub release checks with explicit update actions."""
from __future__ import annotations

import json
import shutil
import time
from PySide6.QtCore import QObject, QTimer, QUrl, QProcess, QByteArray
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextBrowser, QPushButton, QMessageBox
from core import config, updates
from core.i18n import tr
from core.version import __version__


class ReleaseNotes(QTextBrowser):
    def loadResource(self, resource_type, url):  # noqa: N802
        # Release Markdown is remote input: never read local/remote images.
        return QByteArray()


class UpdateController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.network = QNetworkAccessManager(self)
        self.reply = None
        self.release = None
        self._manual = False
        self._too_large = False
        self._body = bytearray()
        self._dialog = None
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.setInterval(15_000)
        self.deadline.timeout.connect(self._abort_request)
        window.title_bar.update_requested.connect(self.show_release)
        self.timer = QTimer(self)
        self.timer.setInterval(60_000)
        self.timer.timeout.connect(self.check_scheduled)
        self.timer.start()
        QTimer.singleShot(5000, self.check_scheduled)

    def check_scheduled(self):
        s = self.window.settings
        if updates.check_due(s.update_interval_hours, s.update_last_attempt, time.time()):
            self.check()

    def check(self, manual=False):
        if self.reply is not None:
            self._manual = self._manual or manual
            return
        self._manual = manual
        self._too_large = False
        self._body.clear()
        self.window.settings.update_last_attempt = time.time()
        config.save(self.window.settings)
        request = QNetworkRequest(QUrl(updates.API_URL))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", f"Fresh-Fan-Manager/{__version__}".encode())
        request.setTransferTimeout(15_000)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.SameOriginRedirectPolicy)
        self.reply = self.network.get(request)
        self.reply.readyRead.connect(self._read)
        self.reply.finished.connect(self._finished)
        self.deadline.start()

    def _abort_request(self):
        if self.reply is not None:
            self.reply.abort()

    def _read(self):
        self._body.extend(bytes(self.reply.readAll()))
        if len(self._body) > updates.MAX_RESPONSE_BYTES and not self._too_large:
            self._too_large = True
            self.reply.abort()

    def _finished(self):
        self.deadline.stop()
        reply = self.reply
        self._read()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = None
        try:
            if self._too_large:
                raise ValueError(tr("update_bad_response"))
            if status == 404:
                raise ValueError(tr("update_no_release"))
            if status in (403, 429):
                raise ValueError(tr("update_rate_limit"))
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError(tr("update_network_error"))
            self.release = updates.parse_release(json.loads(self._body))
            self.window.title_bar.set_update_version(self.release.tag if self.release.newer else None)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            error = str(exc)
        finally:
            self.reply = None
            reply.deleteLater()
        if self._manual:
            if error:
                QMessageBox.information(self.window, tr("updates"), error)
            elif self.release.newer:
                self.show_release()
            else:
                QMessageBox.information(self.window, tr("updates"), tr("update_current", version=__version__))

    def show_release(self):
        if not self.release:
            self.check(manual=True)
            return
        if self._dialog is not None:
            self._dialog.raise_()
            self._dialog.activateWindow()
            return
        release = self.release
        dlg = QDialog(self.window)
        self._dialog = dlg
        dlg.setWindowTitle(tr("update_available", version=release.tag))
        dlg.resize(580, 520)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(tr("update_versions", current=__version__, latest=release.tag)))
        notes = ReleaseNotes()
        notes.setOpenExternalLinks(False)
        notes.setOpenLinks(False)
        # QTextBrowser never loads remote images from release Markdown.
        notes.setMarkdown(release.notes or tr("update_no_notes"))
        layout.addWidget(notes, 1)
        for name, url in release.assets:
            button = QPushButton(tr("update_download", name=name))
            button.clicked.connect(lambda _=False, target=url: QDesktopServices.openUrl(QUrl(target)))
            layout.addWidget(button)
        checkout = updates.git_checkout()
        if checkout:
            button = QPushButton(tr("update_git"))
            button.clicked.connect(self._update_git)
            layout.addWidget(button)
        link = QPushButton(tr("update_open_release"))
        link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(release.url)))
        layout.addWidget(link)
        close = QPushButton(tr("close"))
        close.clicked.connect(dlg.accept)
        layout.addWidget(close)
        dlg.finished.connect(lambda _: self._clear_dialog())
        dlg.open()

    def _clear_dialog(self):
        self._dialog.deleteLater()
        self._dialog = None

    def _update_git(self):
        root = updates.git_checkout()
        if root is None:
            return
        # Commands are separate argv entries; never interpolate release text into a shell.
        terminals = [
            ("konsole", ["--workdir", str(root), "-e", "bash", "tools/update_checkout.sh"]),
            ("gnome-terminal", ["--working-directory", str(root), "--", "bash", "tools/update_checkout.sh"]),
            ("xterm", ["-e", "bash", str(root / "tools/update_checkout.sh")]),
        ]
        for program, args in terminals:
            if shutil.which(program):
                ok, _ = QProcess.startDetached(program, args, str(root))
                if ok:
                    return
        QMessageBox.information(self.window, tr("updates"), tr("update_terminal", path=str(root)))
