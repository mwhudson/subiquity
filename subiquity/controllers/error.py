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

from urwid import Text

from subiquitycore.controller import BaseController


log = logging.getLogger('subiquity.controllers.errros')


class ErrorReportState(enum.Enum):
    UNSEEN = enum.auto()
    SEEN = enum.auto()
    UPLOADING = enum.auto()
    UPLOADED = enum.auto()


@attr.s
class ErrorReport:
    filepath = attr.ib()

    @property
    def state(self):
        base, extension = os.path.splitext(self.filepath)
        if os.path.exists(base + '.uploaded'):
            return ErrorReport.UPLOADED
        elif os.path.exists(base + '.upload'):
            return ErrorReport.UPLOADING
        elif os.path.exists(base + '.seen'):
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
        self.unseen_reports = 0
        self.report_queue = queue.Queue()

    def network_proxy_set(self):
        # configure proxy for whoopsie
        pass

    def start(self):
        # start watching self.crash_directory
        self.set_button_title()
        self.report_pipe_w = self.app.loop.watch_pipe(self._report_changed)
        t = threading.Thread(target=self._bg_scan_crash_dir)
        t.setDaemon(True)
        t.start()

    def set_button_title(self):
        if self.unseen_reports > 0:
            title = _("{} new error reports").format(self.unseen_reports)
            style = 'info_error'
        elif len(self.reports) > 0:
            title = _("{} error reports").format(len(self.reports))
            style = 'body'
        else:
            self.show_report_btn._w = Text("")
            return
        self.show_report_btn._w = Text((style, title))

    def _report_changed(self, ignored):
        try:
            (act, report) = self.report_queue.get(block=False)
        except queue.Empty:
            return True
        if act == "NEW":
            if report.state == ErrorReport.UNSEEN:
                self.unseen_reports += 1
            self.set_button_title()
        return True

    def _bg_scan_crash_dir(self):
        while True:
            for filename in os.listdir(self.crash_directory):
                if not filename.endswith('.crash'):
                    continue
                path = os.path.join(self.crash_directory, filename)
                if path not in self.reports:
                    log.debug("saw error report %s", path)
                    r = self.reports[path] = ErrorReport(filepath=path)
                    self.report_queue.put(("NEW", r))
                    os.write(self.report_pipe_w, b'x')
            time.sleep(1)

    def start_ui(self):
        self.ui.body.show_stretchy_overlay(ErrorListStretchy(self))

    def done(self, sender=None):
        self.ui.body.remove_overlay()

    def cancel(self, sender=None):
        self.ui.body.remove_overlay()
