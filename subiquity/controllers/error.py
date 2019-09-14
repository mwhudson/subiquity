# Copyright 2019 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from abc import ABC
import enum
import logging
import os
import queue
import threading
import time

import attr

import urwid

from subiquitycore.controller import BaseController


log = logging.getLogger('subiquity.controllers.errros')


class ErrorReportState(enum.Enum):
    NEW = _("NEW")
    SEEN = _("SEEN")
    UPLOADING = _("UPLOADING")
    UPLOADED = _("UPLOADED")


@attr.s(cmp=False)
class ErrorReport:
    controller = attr.ib()
    base = attr.ib()

    def _path_with_ext(self, ext):
        return os.path.join(
            self.controller.crash_directory, self.base + '.' + ext)

    @property
    def path(self):
        return self._path_with_ext('crash')

    @property
    def uploaded_path(self):
        return self._path_with_ext('uploaded')

    @property
    def upload_path(self):
        return self._path_with_ext('upload')

    @property
    def seen_path(self):
        return self._path_with_ext('seen')

    @property
    def state(self):
        if os.path.exists(self.uploaded_path):
            return ErrorReportState.UPLOADED
        elif os.path.exists(self.upload_path):
            return ErrorReportState.UPLOADING
        elif os.path.exists(self.seen_path):
            return ErrorReportState.SEEN
        else:
            return ErrorReportState.NEW


class MetaClass(type(ABC), urwid.MetaSignals):
    pass


class ErrorController(BaseController, metaclass=MetaClass):

    signals = ['new_report', 'report_changed']

    def __init__(self, app):
        super().__init__(app)
        self.crash_directory = os.path.join(self.app.root, 'var/crash')
        self.reports = {}
        self.report_queue = queue.Queue()

    def register_signals(self):
        self.signal.connect_signals(('network-proxy-set', 'network_proxy_set'))

    def network_proxy_set(self):
        # configure proxy for whoopsie
        pass

    def start(self):
        # start watching self.crash_directory
        self._scan_lock = threading.Lock()
        self._seen_files = set()
        self.report_pipe_w = self.app.loop.watch_pipe(
            self._report_pipe_callback)
        t = threading.Thread(target=self._bg_scan_crash_dir)
        t.setDaemon(True)
        t.start()

    def _report_pipe_callback(self, ignored):
        while True:
            try:
                (act, base) = self.report_queue.get(block=False)
            except queue.Empty:
                return True
            self._report_changed(act, base)

    def _report_changed(self, act, base):
        if act == "NEW":
            report = self.reports[base] = ErrorReport(self, base)
            urwid.emit_signal(self, 'new_report', report)
        elif act == "DEL" and base in self.reports:
            del self.reports[base]
        elif act == "CHANGE"  and base in self.reports:
            # Update view of crash report, if showing
            urwid.emit_signal(self, 'report_changed', self.reports[base])

    def _bg_scan_crash_dir(self):
        def _report(act, name):
            self.report_queue.put((act, name))
            os.write(self.report_pipe_w, b'x')
        while True:
            try:
                self._scan_crash_dir(_report)
            except Exception:
                log.exception("_scan_crash_dir failed")
            time.sleep(1)

    def fg_scan_crash_dir(self):
        self._scan_crash_dir(self._report_changed)

    def _scan_crash_dir(self, report_func):
        with self._scan_lock:
            next_files = set()
            exts_bases = [
                os.path.splitext(filename)[::-1] + (filename,)
                for filename in os.listdir(self.crash_directory)
                ]
            for ext, base, filename in sorted(exts_bases):
                next_files.add(filename)
                if filename in self._seen_files:
                    continue
                if ext == '.crash':
                    log.debug("saw error report %s", base)
                    report_func("NEW", base)
                if ext in ['.seen', '.upload', '.uploaded']:
                    report_func("CHANGE", base)
            for filename in self._seen_files - next_files:
                base, ext = os.path.splitext(filename)
                if ext == '.crash':
                    report_func("DEL", base)
            self._seen_files = next_files

    def mark_seen(self, base):
        pass

    def mark_for_upload(self, base):
        pass

    def start_ui(self):
        pass

    def done(self, sender=None):
        self.ui.body.remove_overlay()

    def cancel(self, sender=None):
        self.ui.body.remove_overlay()
