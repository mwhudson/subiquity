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

import asyncio
import contextlib
import logging
import os
import sys
import traceback

import aiohttp

from subiquitycore.async_helpers import (
    schedule_task,
    )
from subiquitycore.tuicontroller import Skip
from subiquitycore.tui import TuiApplication
from subiquitycore.screen import is_linux_tty
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

    project = 'subiquity'

    def make_model(self, **args):
        return None

    controllers = [
        "Welcome",
        "Refresh",
        "Keyboard",
        ## "Zdev",
        ## "Network",
        "Proxy",
        "Mirror",
##        "Refresh",
        ## "Filesystem",
##        "Identity",
##        "SSH",
        ## "SnapList",
        "Progress",
    ]

    def __init__(self, opts, block_log_dir):
        self.conn = aiohttp.UnixConnector(
            path=".subiquity/run/subiquity/socket")

        if is_linux_tty():
            self.input_filter = KeyCodesFilter()
        else:
            self.input_filter = DummyKeycodesFilter()

        self.help_menu = HelpMenu(self)
        super().__init__(opts)
        self.global_overlays = []

        self.confirmation_showing = False

        self.report_to_show = None
        self.show_progress_handle = None
        self.progress_shown_time = self.aio_loop.time()
        self.progress_showing = False
        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root)

        # self.note_data_for_apport("SnapUpdated", str(self.updated))
        self.note_data_for_apport("UsingAnswers", str(bool(self.answers)))
        self.conn = aiohttp.UnixConnector(
            path=".subiquity/run/subiquity/socket")

    @contextlib.asynccontextmanager
    async def session(self):
        async with aiohttp.ClientSession(
                connector=self.conn, connector_owner=False) as session:
            yield session

    async def get(self, path, **kw):
        async with self.session() as session:
            async with session.get('http://a' + path, **kw) as resp:
                return await resp.json()

    async def post(self, path, data):
        async with self.session() as session:
            async with session.post('http://a' + path, json=data) as resp:
                return await resp.json()

    def restart(self, remove_last_screen=True):
        if remove_last_screen:
            self._remove_last_screen()
        self.urwid_loop.screen.stop()
        cmdline = ['snap', 'run', 'subiquity']
        if self.opts.dry_run:
            cmdline = [
                sys.executable, '-m', 'subiquity.client.core',
                ] + sys.argv[1:]
        os.execvp(cmdline[0], cmdline)

    def extra_urwid_loop_args(self):
        return dict(input_filter=self.input_filter.filter)

    async def confirm_install(self):
        await self.post("/confirm", {})

    def show_confirm_install(self):
        self._cancel_show_progress()
        log.debug("showing InstallConfirmation over %s", self.ui.body)
        self.confirmation_showing = True
        from subiquity.ui.views.installprogress import (
            InstallConfirmation,
            )
        self.add_global_overlay(
            InstallConfirmation(self.ui.body, self))

    def _cancel_show_progress(self):
        if self.show_progress_handle is not None:
            self.ui.block_input = False
            self.show_progress_handle.cancel()
            self.show_progress_handle = None

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

    def move_screen(self, increment, coro):
        if self.show_progress_handle is None:
            self.ui.block_input = True
            self.show_progress_handle = self.aio_loop.call_later(
                10.1, self._show_progress)
        old, self.cur_screen = self.cur_screen, None
        if old is not None:
            old.context.exit("completed")
            old.end_ui()
        self.aio_loop.create_task(self._move_screen(increment, coro))

    async def _move_screen(self, increment, coro):
        if coro is not None:
            await coro
        if self.confirmation_showing:
            return
        cur_index = self.controllers.index
        while True:
            self.controllers.index += increment
            if self.controllers.index < 0:
                self.controllers.index = cur_index
                return
            if self.controllers.index >= len(self.controllers.instances):
                self.exit()
                return
            new = self.controllers.cur
            try:
                await self.select_screen(new)
            except Skip:
                log.debug("skipping screen %s", new.name)
                continue
            else:
                return

    def next_screen(self, coro=None):
        self.move_screen(1, coro)

    def prev_screen(self, coro=None):
        self.move_screen(-1, coro)

    async def select_screen(self, new):
        new.context.enter("starting UI")
        if self.opts.screens and new.name not in self.opts.screens:
            raise Skip
        try:
            await new.start_ui()
            self.cur_screen = new
        except Skip:
            new.context.exit("(skipped)")
            raise
        with open(self.state_path('last-screen'), 'w') as fp:
            fp.write(new.name)

    async def set_body(self, view):
        self._cancel_show_progress()
        if self.progress_showing:
            shown_for = self.aio_loop.time() - self.progress_shown_time
            remaining = 1.0 - shown_for
            if remaining > 0.0:
                await asyncio.sleep(remaining)
        self.ui.set_body(view)

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

    async def connect(self):
        print("connecting...", end='', flush=True)
        while True:
            try:
                status = await self.get('/status', timeout=1)
            except aiohttp.ClientError:
                await asyncio.sleep(1)
                print(".", end='', flush=True)
            else:
                print()
                break
        if status['state'] == 'early-commands':
            print("waiting for early-commands")
            await self.get('/wait-early')
            status = await self.get('/status')
        if status['state'] == 'interactive':
            fd1, watcher1 = journald_listener(
                [status["event_syslog_identifier"]],
                self.controllers.Progress.event)
            self.aio_loop.add_reader(fd1, watcher1)
            fd2, watcher2 = journald_listener(
                [status["log_syslog_identifier"]],
                self.controllers.Progress.log_line)
            self.aio_loop.add_reader(fd2, watcher2)
            self.start_urwid()
            self.next_screen()
        else:
            pass

    auto_start_urwid = False

    def run(self):
        self.aio_loop.create_task(self.connect())
        try:
            super().run()
        except Exception:
            log.exception('in run')
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


if __name__ == '__main__':
    from subiquitycore.log import setup_logger
    from subiquity.cmd.tui import parse_options
    setup_logger('.subiquity')
    opts = parse_options(['--dry-run', '--snaps-from-examples'])
    Subiquity(opts, '').run()
