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
import json
import logging
import os
import queue
import threading
import time

import apport
import apport.crashdb
import apport.hookutils

import attr

import bson

import problem_report

import requests

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
    REPORTING = _("REPORTING")
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
    meta = attr.ib(default=attr.Factory(dict))
    construction_state = attr.ib(default=ErrorReportConstructionState.NEW)
    _file = attr.ib(default=None)

    reporting = attr.ib(default=False)
    uploading = attr.ib(default=False)

    @classmethod
    def from_file(cls, controller, fpath):
        base = os.path.splitext(os.path.basename(fpath))[0]
        report = cls(
            controller, base, pr=apport.Report(),
            construction_state=ErrorReportConstructionState.LOADING,
            file=open(fpath, 'rb'))
        try:
            fp = open(report.meta_path, 'r')
        except FileNotFoundError:
            pass
        else:
            with fp:
                report.meta = json.load(fp)
        controller._queue_report_load(report)
        return report

    @classmethod
    def new(cls, controller, kind):
        i = 0
        while 1:
            base = "installer.{}".format(i)
            crash_path = os.path.join(
                controller.crash_directory, base + ".crash")
            try:
                crash_file = open(crash_path, 'xb')
            except FileExistsError:
                i += 1
                continue
            else:
                break
        pr = apport.Report('Bug')
        pr['CrashDB'] = repr(controller.crashdb_spec)

        r = cls(
            controller=controller, base=base, pr=pr, file=crash_file,
            construction_state=ErrorReportConstructionState.INCOMPLETE)
        r.set_meta("kind", kind.name)
        return r

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
        self.set_meta("seen", True)
        urwid.emit_signal(self.controller, 'report_changed', self)

    def report(self):

        self.reporting = True
        self.bytes_sent = 0
        self.bytes_to_send = os.stat(self.path).st_size

        def _cb(data):
            urwid.emit_signal(self.controller, 'reporting_progress', self)

        pipe_w = self.controller.loop.watch_pipe(_cb)

        def _bg_progress(bytes_sent, bytes_to_send):
            self.bytes_sent = bytes_sent
            self.bytes_to_send = bytes_to_send
            os.write(pipe_w, b'x')

        def _bg_report():
            return self.controller.crashdb.upload(self.pr)

        def _reported(fut):
            self.reporting = False
            self.bytes_sent = self.bytes_to_send = None
            self.controller.loop.remove_watch_pipe(pipe_w)
            os.close(pipe_w)
            try:
                ticket = fut.result()
            except Exception:
                logging.exception("reporting bug on Launchpad failed")
                return
            url = self.controller.crashdb.get_comment_url(self.pr, ticket)
            self.set_meta("reported-url", url)
            urwid.emit_signal(self.controller, 'report_changed', self)
            urwid.emit_signal(self.controller, 'reporting_completed', self)

        urwid.emit_signal(self.controller, 'report_changed', self)
        self.controller.run_in_bg(_bg_report, _reported)

    def upload(self):
        log.debug("starting upload for %s", self.base)
        self.uploading = True
        url = "https://daisy.ubuntu.com"
        if self.controller.opts.dry_run:
            url = "https://daisy.staging.ubuntu.com"

        def _bg_upload():
            for_upload = {}
            for k, v in self.pr.items():
                if len(v) < 1024 or k in {"Traceback", "ProcCpuinfoMinimal"}:
                    for_upload[k] = v
                else:
                    log.debug("dropping %s of length %s", k, len(v))
                #logtail = []
                #for line in self.pr["InstallerLog"].splitlines():
                #    logtail.append(line.strip())
                #    while sum(map(len, logtail)) > 2048:
                #        logtail.pop(0)
                #for_upload["InstallerLogTail"] = "\n".join(logtail)
            data = bson.BSON().encode(for_upload)
            return requests.post(url, data=data)

        def uploaded(fut):
            self.uploading = False
            try:
                response = fut.result()
                response.raise_for_status()
            except requests.exceptions.RequestException:
                log.exception("upload for %s failed", self.base)
                return
            log.debug("finished upload for %s, %r", self.base, response.text)
            self.set_meta("oops-id", response.text.split()[0])
            urwid.emit_signal(self.controller, 'report_changed', self)

        urwid.emit_signal(self.controller, 'report_changed', self)
        self.controller.run_in_bg(_bg_upload, uploaded)

    def _path_with_ext(self, ext):
        return os.path.join(
            self.controller.crash_directory, self.base + '.' + ext)

    @property
    def meta_path(self):
        return self._path_with_ext('meta')

    @property
    def path(self):
        return self._path_with_ext('crash')

    @property
    def summary(self):
        return self.pr.get("Title", "???")

    def set_meta(self, key, value):
        self.meta[key] = value
        with open(self.meta_path, 'w') as fp:
            json.dump(self.meta, fp, indent=4)

    @property
    def kind(self):
        k = self.meta.get("kind", "UNKNOWN")
        return getattr(ErrorReportKind, k, ErrorReportKind.UNKNOWN)

    @property
    def reported_url(self):
        return self.meta.get("reported-url")

    @property
    def oops_id(self):
        return self.meta.get("oops-id")

    @property
    def seen(self):
        return self.meta.get("seen")

    @property
    def reporting_state(self):
        if self.reported_url is not None:
            return ErrorReportReportingState.REPORTED
        if self.reporting:
            return ErrorReportReportingState.REPORTING
        if self.oops_id is not None:
            return ErrorReportReportingState.UPLOADED
        if self.uploading:
            return ErrorReportReportingState.UPLOADING
        if self.seen:
            return ErrorReportReportingState.UNREPORTED
        return ErrorReportReportingState.UNVIEWED


class MetaClass(type(ABC), urwid.MetaSignals):
    pass


class ErrorController(BaseController, metaclass=MetaClass):

    signals = [
        'new_report',
        'report_changed',
        'reporting_progress',
        'reporting_completed',
        ]

    def __init__(self, app):
        super().__init__(app)
        self.crash_directory = os.path.join(self.app.root, 'var/crash')
        self.crashdb_spec = {
            'impl': 'launchpad',
            'project': 'subiquity',
            }
        self.crashdb = apport.crashdb.load_crashdb(
            None, self.crashdb_spec)
        if self.app.opts.dry_run:
            self.crashdb_spec['launchpad_instance'] = 'staging'
        self.reports = []  # maps base to ErrorReport
        self._loading_report = None
        self._reports_to_load = []

    def are_reports_persistent(self):
        if self.opts.dry_run:
            return True
        else:
            cp = run_command(['mountpoint', self.crash_directory])
            return cp.returncode == 0

    def register_signals(self):
        # BaseController.register_signals uses the signals class
        # attribute, but that's also used by MetaSignals...
        pass

    def start(self):
        os.makedirs(self.crash_directory, exist_ok=True)
        # scan for pre-existing crash reports and start loading them
        # in the background
        self.scan_crash_dir()

    def _queue_report_load(self, report):
        if self._loading_report is None:
            self._loading_report = report
            self._loading_report.load(self._report_loaded)
        else:
            self._reports_to_load.append(report)

    def _report_loaded(self):
        if self._reports_to_load:
            self._loading_report = self._reports_to_load.pop(0)
            self._loading_report.load(self._report_loaded)
        else:
            self._loading_report = None

    def scan_crash_dir(self):
        filenames = os.listdir(self.crash_directory)
        for filename in filenames:
            base, ext = os.path.splitext(filename)
            if ext != ".crash":
                continue
            path = os.path.join(self.crash_directory, filename)
            self.reports.append(ErrorReport.from_file(self, path))

    def create_report(self, kind):
        r = ErrorReport.new(self, kind)
        self.reports.append(r)
        urwid.emit_signal(self, 'new_report', r)
        return r

    def start_ui(self):
        raise Skip

    def done(self, sender=None):
        self.ui.body.remove_overlay()

    def cancel(self, sender=None):
        self.ui.body.remove_overlay()
