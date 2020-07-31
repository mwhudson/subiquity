# Copyright 2020 Canonical, Ltd.
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

import logging
import os
import shlex
import traceback

import jsonschema

import yaml

from subiquitycore.async_helpers import (
    run_in_thread,
    schedule_task,
    )
from subiquitycore.tuicontroller import Skip
from subiquitycore.tui import TuiApplication
from subiquitycore.snapd import (
    AsyncSnapd,
    FakeSnapdConnection,
    SnapdConnection,
    )
from subiquitycore.view import BaseView

from subiquity.common.errorreport import (
    ErrorReporter,
    ErrorReportKind,
    )
from subiquity.models.subiquity import SubiquityModel
from subiquity.ui.views.error import ErrorReportStretchy


log = logging.getLogger('subiquity.core')


DEBUG_SHELL_INTRO = _("""\
Installer shell session activated.

This shell session is running inside the installer environment.  You
will be returned to the installer when this shell is exited, for
example by typing Control-D or 'exit'.

Be aware that this is an ephemeral environment.  Changes to this
environment will not survive a reboot. If the install has started, the
installed system will be mounted at /target.""")


class Subiquity(TuiApplication):

    snapd_socket_path = '/run/snapd.socket'

    base_schema = {
        'type': 'object',
        'properties': {
            'version': {
                'type': 'integer',
                'minimum': 1,
                'maximum': 1,
                },
            },
        'required': ['version'],
        'additionalProperties': True,
        }

    from subiquity.server import controllers as controllers_mod
    project = "subiquity"

    def make_model(self):
        root = '/'
        if self.opts.dry_run:
            root = os.path.abspath('.subiquity')
        return SubiquityModel(root, self.opts.sources)

    controllers = [
        "Early",
        "Reporting",
        "Error",
        "Userdata",
        "Package",
        "Debconf",
        "Locale",
        "Refresh",
        "Keyboard",
        "Zdev",
        "Network",
        "Proxy",
        "Mirror",
        "Refresh",
        "Filesystem",
        "Identity",
        "SSH",
        "SnapList",
        "InstallProgress",
        "Late",
        "Reboot",
    ]

    def __init__(self, opts, block_log_dir):
        super().__init__(opts)
        self.event_listeners = []
        self.block_log_dir = block_log_dir
        self.kernel_cmdline = shlex.split(opts.kernel_cmdline)
        if opts.snaps_from_examples:
            connection = FakeSnapdConnection(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(__file__)),
                    "examples", "snaps"),
                self.scale_factor)
        else:
            connection = SnapdConnection(self.root, self.snapd_socket_path)
        self.snapd = AsyncSnapd(connection)
        self.signal.connect_signals([
            ('network-proxy-set', lambda: schedule_task(self._proxy_set())),
            ('network-change', self._network_change),
            ])

        self.autoinstall_config = {}
        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root)

        self.note_data_for_apport("SnapUpdated", str(self.updated))
        self.note_data_for_apport("UsingAnswers", str(bool(self.answers)))

        self.install_confirmed = False

    def restart(self, remove_last_screen=True):
        XXX

    def load_autoinstall_config(self):
        with open(self.opts.autoinstall) as fp:
            self.autoinstall_config = yaml.safe_load(fp)
        self.controllers.load("Reporting")
        self.controllers.Reporting.start()
        self.controllers.load("Error")
        with self.context.child("core_validation", level="INFO"):
            jsonschema.validate(self.autoinstall_config, self.base_schema)
        self.controllers.load("Early")
        if self.controllers.Early.cmds:
            stamp_file = self.state_path("early-commands")
            if not os.path.exists(stamp_file):
                self.aio_loop.run_until_complete(
                    self.controllers.Early.run())
                self.new_event_loop()
                open(stamp_file, 'w').close()
            with open(self.opts.autoinstall) as fp:
                self.autoinstall_config = yaml.safe_load(fp)
            with self.context.child("core_validation", level="INFO"):
                jsonschema.validate(self.autoinstall_config, self.base_schema)
            for controller in self.controllers.instances:
                controller.setup_autoinstall()

    def run(self):
        try:
            if self.opts.autoinstall is not None:
                self.load_autoinstall_config()
                if not self.interactive() and not self.opts.dry_run:
                    open('/run/casper-no-prompt', 'w').close()
            super().run()
        except Exception:
            print("generating crash report")
            try:
                report = self.make_apport_report(
                    ErrorReportKind.DAEMON, "Installer Daemon", wait=True)
                if report is not None:
                    print("report saved to {path}".format(path=report.path))
            except Exception:
                print("report generation failed")
                traceback.print_exc()
            Error = getattr(self.controllers, "Error", None)
            if Error is not None and Error.cmds:
                self.new_event_loop()
                self.aio_loop.run_until_complete(Error.run())
            self._remove_last_screen()
            raise

    def add_event_listener(self, listener):
        self.event_listeners.append(listener)

    def report_start_event(self, context, description):
        for listener in self.event_listeners:
            listener.report_start_event(context, description)

    def report_finish_event(self, context, description, status):
        for listener in self.event_listeners:
            listener.report_finish_event(context, description, status)

    def confirm_install(self):
        self.install_confirmed = True
        self.controllers.InstallProgress.confirmation.set()

    def _cancel_show_progress(self):
        if self.show_progress_handle is not None:
            self.ui.block_input = False
            self.show_progress_handle.cancel()
            self.show_progress_handle = None

    def next_screen(self):
        can_install = all(e.is_set() for e in self.base_model.install_events)
        if can_install and not self.install_confirmed:
            if self.interactive():
                log.debug("showing InstallConfirmation over %s", self.ui.body)
                from subiquity.ui.views.installprogress import (
                    InstallConfirmation,
                    )
                self._cancel_show_progress()
                self.add_global_overlay(
                    InstallConfirmation(self.ui.body, self))
            else:
                yes = _('yes')
                no = _('no')
                answer = no
                if 'autoinstall' in self.kernel_cmdline:
                    answer = yes
                else:
                    print(_("Confirmation is required to continue."))
                    print(_("Add 'autoinstall' to your kernel command line to"
                            " avoid this"))
                    print()
                prompt = "\n\n{} ({}|{})".format(
                    _("Continue with autoinstall?"), yes, no)
                while answer != yes:
                    print(prompt)
                    answer = input()
                self.confirm_install()
                super().next_screen()
        else:
            super().next_screen()

    def interactive(self):
        if not self.autoinstall_config:
            return True
        return bool(self.autoinstall_config.get('interactive-sections'))

    def add_global_overlay(self, overlay):
        self.global_overlays.append(overlay)
        if isinstance(self.ui.body, BaseView):
            self.ui.body.show_stretchy_overlay(overlay)

    def remove_global_overlay(self, overlay):
        self.global_overlays.remove(overlay)
        if isinstance(self.ui.body, BaseView):
            self.ui.body.remove_overlay(overlay)

    def select_initial_screen(self, index):
        self.error_reporter.start_loading_reports()
        for report in self.error_reporter.reports:
            if report.kind == ErrorReportKind.UI and not report.seen:
                self.show_error_report(report)
                break
        super().select_initial_screen(index)

    def select_screen(self, new):
        if new.interactive():
            self._cancel_show_progress()
            if self.progress_showing:
                shown_for = self.aio_loop.time() - self.progress_shown_time
                remaining = 1.0 - shown_for
                if remaining > 0.0:
                    self.aio_loop.call_later(
                        remaining, self.select_screen, new)
                    return
            self.progress_showing = False
            super().select_screen(new)
        elif self.autoinstall_config and not new.autoinstall_applied:
            if self.interactive() and self.show_progress_handle is None:
                self.ui.block_input = True
                self.show_progress_handle = self.aio_loop.call_later(
                    0.1, self._show_progress)
            schedule_task(self._apply(new))
        else:
            new.configured()
            raise Skip

    async def _apply(self, controller):
        await controller.apply_autoinstall_config()
        controller.autoinstall_applied = True
        controller.configured()
        self.next_screen()

    def _network_change(self):
        self.signal.emit_signal('snapd-network-change')

    async def _proxy_set(self):
        await run_in_thread(
            self.snapd.connection.configure_proxy, self.base_model.proxy)
        self.signal.emit_signal('snapd-network-change')

    def note_file_for_apport(self, key, path):
        self.error_reporter.note_file_for_apport(key, path)

    def note_data_for_apport(self, key, value):
        self.error_reporter.note_data_for_apport(key, value)

    def make_apport_report(self, kind, thing, *, wait=False, **kw):
        return self.error_reporter.make_apport_report(
            kind, thing, wait=wait, **kw)

    def show_error_report(self, report):
        log.debug("show_error_report %r", report.base)
        if isinstance(self.ui.body, BaseView):
            w = getattr(self.ui.body._w, 'stretchy', None)
            if isinstance(w, ErrorReportStretchy):
                # Don't show an error if already looking at one.
                return
        self.add_global_overlay(ErrorReportStretchy(self, report))

    def make_autoinstall(self):
        config = {'version': 1}
        for controller in self.controllers.instances:
            controller_conf = controller.make_autoinstall()
            if controller_conf:
                config[controller.autoinstall_key] = controller_conf
        return config
