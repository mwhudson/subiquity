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

import attr

import urwid

from subiquitycore.controller import BaseController
from subiquitycore.core import Skip


log = logging.getLogger('subiquity.controllers.error')


class ErrorReportReportingState(enum.Enum):
    UNVIEWED = _("UNVIEWED")
    UNREPORTED = _("UNREPORTED")
    UPLOADING = _("UPLOADING")
    UPLOADED = _("UPLOADED")
    REPORTED = _("REPORTED")


class ErrorReportConstructionState(enum.Enum):
    NEW = _("NEW")
    LOADING = _("LOADING")
    INCOMPLETE = _("INCOMPLETE")
    DONE = _("DONE")
    ERROR = _("ERROR")


class ErrorReportKind(enum.Enum):
    FULL_BLOCK_PROBE_FAILED = _("Block device probe failure")
    RESTRICTED_BLOCK_PROBE_FAILED = _("Disk probe failure")
    INSTALL_FAILED = _("Install failure")
    UI_CRASH = _("Installer crash")
    UNKNOWN = _("Unknown error")


@attr.s(cmp=False)
class ErrorReport:
    controller = attr.ib()
    base = attr.ib()
    pr = attr.ib(default=None)
    kind = attr.ib(default=ErrorReportKind.UNKNOWN)
    construction_state = attr.ib(default=ErrorReportConstructionState.NEW)

    def _path_with_ext(self, ext):
        return os.path.join(
            self.controller.crash_directory, self.base + '.' + ext)

    @property
    def path(self):
        return self._path_with_ext('crash')

    @property
    def reported_path(self):
        return self._path_with_ext('uploaded')

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
    def reporting_state(self):
        if os.path.exists(self.reported_path):
            return ErrorReportReportingState.REPORTED
        elif os.path.exists(self.uploaded_path):
            return ErrorReportReportingState.UPLOADED
        elif os.path.exists(self.upload_path):
            return ErrorReportReportingState.UPLOADING
        elif os.path.exists(self.seen_path):
            return ErrorReportReportingState.UNREPORTED
        else:
            return ErrorReportReportingState.UNVIEWED


class MetaClass(type(ABC), urwid.MetaSignals):
    pass


class ErrorController(BaseController, metaclass=MetaClass):

    signals = ['new_report', 'report_changed']

    def __init__(self, app):
        super().__init__(app)
        self.crash_directory = os.path.join(self.app.root, 'var/crash')
        self.reports = {}  # maps base to ErrorReport

    def register_signals(self):
        # BaseController.register_signals uses the signals class
        # attribute, but that's also used by MetaSignals...
        self.signal.connect_signals(
            [('network-proxy-set', 'network_proxy_set')])

    def network_proxy_set(self):
        # configure proxy for whoopsie
        pass

    def start(self):
        # scan for pre-existing crash reports, send new_report signals
        # for them and start loading them in the background
        pass

    def create_report(self, kind):
        # create a report, send a new_report signal for it
        pass

    def start_ui(self):
        raise Skip

    def done(self, sender=None):
        self.ui.body.remove_overlay()

    def cancel(self, sender=None):
        self.ui.body.remove_overlay()
