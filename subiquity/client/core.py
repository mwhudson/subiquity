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
import sys
import traceback
import urwid

import aiohttp

from subiquitycore.async_helpers import (
    schedule_task,
    )
from subiquitycore.tuicontroller import Skip
from subiquitycore.tui import TuiApplication
from subiquitycore.screen import is_linux_tty
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
from subiquity.journald import journald_listener
from subiquity.keycodes import (
    DummyKeycodesFilter,
    KeyCodesFilter,
    )
from subiquity.ui.frame import SubiquityUI
from subiquity.ui.views.error import ErrorReportStretchy
from subiquity.ui.views.help import HelpMenu


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

    from subiquity.client import controllers as controllers_mod

    def make_ui(self):
        return SubiquityUI(self, self.help_menu)

    controllers = [
        "Welcome",
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
    ]

    def __init__(self, opts, block_log_dir):
        self.conn = aiohttp.UnixConnector(
            path=".subiquity/run/subiquity/socket")

        if is_linux_tty():
            self.input_filter = KeyCodesFilter()
        else:
            self.input_filter = DummyKeycodesFilter()

        self.journal_fd, self.journal_watcher = journald_listener(
            ["subiquity"], self.subiquity_event, seek=True)
        self.help_menu = HelpMenu(self)
        super().__init__(opts)
        self.global_overlays = []
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

        self.report_to_show = None
        self.show_progress_handle = None
        self.progress_shown_time = self.aio_loop.time()
        self.progress_showing = False
        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root)

        # self.note_data_for_apport("SnapUpdated", str(self.updated))
        self.note_data_for_apport("UsingAnswers", str(bool(self.answers)))

    def subiquity_event(self, event):
        if event["MESSAGE"] == "starting install":
            if event["_PID"] == os.getpid():
                return
            if not self.install_lock_file.is_exclusively_locked():
                return
            from subiquity.ui.views.installprogress import (
                InstallRunning,
                )
            tty = self.install_lock_file.read_content()
            install_running = InstallRunning(self.ui.body, self, tty)
            self.add_global_overlay(install_running)
            schedule_task(self._hide_install_running(install_running))

    async def _hide_install_running(self, install_running):
        # Wait until the install has completed...
        async with self.install_lock_file.shared():
            # And remove the overlay.
            self.remove_global_overlay(install_running)

    def restart(self, remove_last_screen=True):
        if remove_last_screen:
            self._remove_last_screen()
        self.urwid_loop.screen.stop()
        cmdline = ['snap', 'run', 'subiquity']
        if self.opts.dry_run:
            cmdline = [
                sys.executable, '-m', 'subiquity.cmd.tui',
                ] + sys.argv[1:]
        os.execvp(cmdline[0], cmdline)

    def make_screen(self, input=None, output=None):
        if self.interactive():
            return super().make_screen(input, output)
        else:
            r, w = os.pipe()
            s = urwid.raw_display.Screen(
                input=os.fdopen(r), output=open('/dev/null', 'w'))
            s.get_cols_rows = lambda: (80, 24)
            return s

    def new_event_loop(self):
        super().new_event_loop()
        self.aio_loop.add_reader(self.journal_fd, self.journal_watcher)

    def extra_urwid_loop_args(self):
        return dict(input_filter=self.input_filter.filter)

    def run(self):
        try:
            super().run()
        except Exception:
            print("generating crash report")
            try:
                report = self.make_apport_report(
                    ErrorReportKind.UI, "Installer UI", interrupt=False,
                    wait=True)
                if report is not None:
                    print("report saved to {path}".format(path=report.path))
            except Exception:
                print("report generation failed")
                traceback.print_exc()
            self._remove_last_screen()

    def confirm_install(self):
        XXX

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

    def _show_progress(self):
        self.ui.block_input = False
        self.progress_shown_time = self.aio_loop.time()
        self.progress_showing = True
        self.ui.set_body(self.controllers.InstallProgress.progress_view)

    def unhandled_input(self, key):
        if key == 'f1':
            if not self.ui.right_icon.current_help:
                self.ui.right_icon.open_pop_up()
        elif key in ['ctrl z', 'f2']:
            self.debug_shell()
        elif self.opts.dry_run:
            self.unhandled_input_dry_run(key)
        else:
            super().unhandled_input(key)

    def unhandled_input_dry_run(self, key):
        if key == 'ctrl g':
            import asyncio
            from systemd import journal

            async def mock_install():
                async with self.install_lock_file.exclusive():
                    self.install_lock_file.write_content("nowhere")
                    journal.send(
                        "starting install", SYSLOG_IDENTIFIER="subiquity")
                    await asyncio.sleep(5)
            schedule_task(mock_install())
        elif key in ['ctrl e', 'ctrl r']:
            interrupt = key == 'ctrl e'
            try:
                1/0
            except ZeroDivisionError:
                self.make_apport_report(
                    ErrorReportKind.UNKNOWN, "example", interrupt=interrupt)
        elif key == 'ctrl u':
            1/0
        else:
            super().unhandled_input(key)

    def debug_shell(self, after_hook=None):

        def _before():
            os.system("clear")
            print(DEBUG_SHELL_INTRO)

        self.run_command_in_foreground(
            ["bash"], before_hook=_before, after_hook=after_hook, cwd='/')

    def note_file_for_apport(self, key, path):
        self.error_reporter.note_file_for_apport(key, path)

    def note_data_for_apport(self, key, value):
        self.error_reporter.note_data_for_apport(key, value)

    def make_apport_report(self, kind, thing, *, interrupt, wait=False, **kw):
        report = self.error_reporter.make_apport_report(
            kind, thing, wait=wait, **kw)

        if report is not None and interrupt and self.interactive():
            self.show_error_report(report)

        return report

    def show_error_report(self, report):
        log.debug("show_error_report %r", report.base)
        if isinstance(self.ui.body, BaseView):
            w = getattr(self.ui.body._w, 'stretchy', None)
            if isinstance(w, ErrorReportStretchy):
                # Don't show an error if already looking at one.
                return
        self.add_global_overlay(ErrorReportStretchy(self, report))
