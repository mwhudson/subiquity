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

import enum
import logging
import os
import queue
import threading
import time

import attr

from subiquitycore.controller import BaseController


log = logging.getLogger('subiquity.controllers.errros')


class ErrorReportState(enum.Enum):
    UNSEEN = enum.auto()
    SEEN = enum.auto()
    UPLOADING = enum.auto()
    UPLOADED = enum.auto()


@attr.s
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
        return self._path_with_ext('uploaded_path')

    @property
    def upload_path(self):
        return self._path_with_ext('upload')

    @property
    def seen_path(self):
        return self._path_with_ext('seen')

    @property
    def state(self):
        if os.path.exists(self.uploaded_path):
            return ErrorReport.UPLOADED
        elif os.path.exists(self.upload_path):
            return ErrorReport.UPLOADING
        elif os.path.exists(self.seen_path):
            return ErrorReport.SEEN
        else:
            return ErrorReport.UNSEEN


class ErrorController(BaseController):

    signals = [
        ('network-proxy-set', 'network_proxy_set'),
    ]

    def __init__(self, app):
        super().__init__(app)
        self.crash_directory = os.path.join(self.app.root, 'var/log/crash')
        self.show_report_btn = self.app.show_report_btn
        self.reports = {}
        self.report_queue = queue.Queue()

    def network_proxy_set(self):
        # configure proxy for whoopsie
        pass

    def start(self):
        # start watching self.crash_directory
        self.set_button_title()
        self._scan_lock = threading.Lock()
        self._seen_files = set()
        self.report_pipe_w = self.app.loop.watch_pipe(
            self._report_pipe_callback)
        t = threading.Thread(target=self._bg_scan_crash_dir)
        t.setDaemon(True)
        t.start()

    def set_button_title(self):
        unseen_reports = len([
            r for r in self.reports.values()
            if r.state == ErrorReportState.UNSEEN
            ])
        self.show_report_btn.set_title(unseen_reports, len(self.reports))

    def _report_pipe_callback(self, ignored):
        while True:
            try:
                (act, typ, path) = self.report_queue.get(block=False)
            except queue.Empty:
                return True
            self._report_changed(act, typ, path)

    def _report_changed(self, act, base):
        if act == "NEW":
            self.reports[base] = ErrorReport(self, base)
            self.set_button_title()
        elif act == "DEL" and base in self.reports:
            del self.reports[base]
            self.set_button_title()
        elif act == "CHANGE"  and base in self.reports:
            # Update view of crash report, if showing
            pass

    def _bg_scan_crash_dir(self):
        def _report(act, name):
            self.report_queue.put(act, name)
            os.write(self.report_pipe_w, b'x')
        while True:
            self._scan_crash_dir(_report)
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
                if ext == 'crash':
                    log.debug("saw error report %s", base)
                    report_func("NEW", base)
                if ext in ['seen', 'upload', 'uploaded']:
                    report_func("CHANGE", base)
            for filename in self._seen_files - next_files:
                base, ext = os.path.splitext(filename)
                if ext == 'crash':
                    report_func("DEL", base)
            self._seen_files = next_files

    def mark_seen(self, base):
        pass

    def mark_for_upload(self, base):
        pass

    def start_ui(self):
        self.fg_scan_crash_dir()
        self.ui.body.show_stretchy_overlay(ErrorListStretchy(self))

    def show_error(self, base):
        self.start_ui()
        self.ui.body.show_stretchy_overlay(ErrorReportStretchy(self, base))

    def done(self, sender=None):
        self.ui.body.remove_overlay()

    def cancel(self, sender=None):
        self.ui.body.remove_overlay()
