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

import apport
import apport.hookutils

import attr

import urwid

from subiquitycore.controller import BaseController
from subiquitycore.core import Skip
from subiquitycore.utils import run_command


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
    _file = attr.ib(default=None)

    def add_info(self, _bg_attach_hook, wait=False):
        log.debug("begin adding info for report %s", self.base)

        def _bg_add_info():
            _bg_attach_hook()
            # Add basic info to report.
            self.pr.add_proc_info()
            self.pr.add_os_info()
            self.pr.add_hooks_info(None)
            apport.hookutils.attach_hardware(self.pr)
            # Because apport-cli will in general be run on a different
            # machine, we make some slightly obscure alterations to the report
            # to make this go better.

            # apport-cli gets upset if neither of these are present.
            self.pr['Package'] = 'subiquity ' + os.environ.get(
                "SNAP_REVISION", "SNAP_REVISION")
            self.pr['SourcePackage'] = 'subiquity'

            # If ExecutableTimestamp is present, apport-cli will try to check
            # that ExecutablePath hasn't changed. But it won't be there.
            del self.pr['ExecutableTimestamp']
            # apport-cli gets upset at the probert C extensions it sees in
            # here.  /proc/maps is very unlikely to be interesting for us
            # anyway.
            del self.pr['ProcMaps']
            self.pr.write(self._file)
            if self.kind != ErrorReportKind.UNKNOWN:
                with open(self.kind_path, 'w') as fp:
                    fp.write(self.kind.name+"\n")

        def added_info(fut):
            log.debug("done adding info for report %s", self.base)
            try:
                fut.result()
            except Exception:
                self.construction_state = ErrorReportConstructionState.ERROR
                log.exception("adding info to problem report failed")
            else:
                self.construction_state = ErrorReportConstructionState.DONE
            self._file.close()
            self._file = None
            urwid.emit_signal(self.controller, 'report_changed', self)
        if wait:
            _bg_add_info()
        else:
            self.controller.run_in_bg(_bg_add_info, added_info)

    def load(self, cb):

        def _bg_load():
            log.debug("loading report %s", self.base)
            self.pr.load(self._file)

        def loaded(fut):
            log.debug("done loading report %s", self.base)
            try:
                fut.result()
            except Exception:
                self.construction_state = ErrorReportConstructionState.ERROR
                log.exception("loading problem report failed")
            else:
                self.construction_state = ErrorReportConstructionState.DONE
            self._file.close()
            self._file = None
            urwid.emit_signal(self.controller, 'report_changed', self)
            cb()
        self.controller.run_in_bg(_bg_load, loaded)

    def mark_seen(self):
        with open(self.seen_path, 'w'):
            pass
        urwid.emit_signal(self.controller, 'report_changed', self)

    def mark_for_upload(self):
        with open(self.upload_path, 'w'):
            pass
        urwid.emit_signal(self.controller, 'report_changed', self)

    def _path_with_ext(self, ext):
        return os.path.join(
            self.controller.crash_directory, self.base + '.' + ext)

    @property
    def kind_path(self):
        return self._path_with_ext('kind')

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
    def summary(self):
        return self.pr.get("Title", "???")

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

    def are_reports_persistent(self):
        cp = run_command(['mountpoint', self.crash_directory])
        return cp.returncode == 0

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
        os.makedirs(self.crash_directory, exist_ok=True)
        self.run_in_bg(self._bg_scan_crash_dir, self._scanned)

    def _bg_scan_crash_dir(self):
        reports = []
        for fname in os.listdir(self.crash_directory):
            base, ext = os.path.splitext(fname)
            if ext != '.crash':
                continue
            path = os.path.join(self.crash_directory, fname)
            report = ErrorReport(
                controller=self, base=base, pr=apport.Report(),
                file=open(path, 'rb'),
                construction_state=ErrorReportConstructionState.LOADING)
            try:
                fp = open(report.kind_path)
            except FileNotFoundError:
                pass
            else:
                with fp:
                    report.kind = getattr(
                        ErrorReportKind,
                        fp.read().strip(),
                        ErrorReportKind.UNKNOWN)
            reports.append(report)
        return reports

    def _report_loaded(self):
        for report in self.reports.values():
            if report.construction_state == \
              ErrorReportConstructionState.LOADING:
                report.load(self._report_loaded)
                return

    def _scanned(self, fut):
        try:
            reports = fut.result()
        except Exception:
            logging.exception("scanning for crash reports failed")
            return
        for report in reports:
            if report.base not in self.reports:
                self.reports[report.base] = report
                urwid.emit_signal(self, 'new_report', report)
        self._report_loaded()

    def create_report(self, kind):
        # create a report, send a new_report signal for it
        i = 0
        while 1:
            base = "installer.{}".format(i)
            crash_path = os.path.join(self.crash_directory, base + ".crash")
            try:
                crash_file = open(crash_path, 'xb')
            except FileExistsError:
                i += 1
                continue
            else:
                break
        pr = apport.Report('Bug')

        # Report to the subiquity project on Launchpad.
        crashdb = {
            'impl': 'launchpad',
            'project': 'subiquity',
            }
        if self.app.opts.dry_run:
            crashdb['launchpad_instance'] = 'staging'
        pr['CrashDB'] = repr(crashdb)

        r = self.reports[base] = ErrorReport(
            controller=self, base=base, pr=pr, file=crash_file,
            construction_state=ErrorReportConstructionState.INCOMPLETE,
            kind=kind)
        urwid.emit_signal(self, 'new_report', r)
        return r

    def start_ui(self):
        raise Skip

    def done(self, sender=None):
        self.ui.body.remove_overlay()

    def cancel(self, sender=None):
        self.ui.body.remove_overlay()
