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

from subiquitycore.tuicontroller import Skip
from subiquitycore.view import BaseView

from subiquity.client.asyncapp import AsyncTuiApplication
from subiquity.common.api.client import make_client
from subiquity.common.api.definition import API
from subiquity.common.errorreport import (
    ErrorReporter,
    ErrorReportKind,
    )
from subiquity.common.types import ApplicationStatus
from subiquity.journald import journald_listener
from subiquity.ui.frame import SubiquityUI
from subiquity.ui.views.error import ErrorReportStretchy
from subiquity.ui.views.help import HelpMenu
from subiquity.ui.views.installprogress import (
    InstallConfirmation,
    )


log = logging.getLogger('subiquity.client.client')


class Confirm(Exception):
    pass


DEBUG_SHELL_INTRO = _("""\
Installer shell session activated.

This shell session is running inside the installer environment.  You
will be returned to the installer when this shell is exited, for
example by typing Control-D or 'exit'.

Be aware that this is an ephemeral environment.  Changes to this
environment will not survive a reboot. If the install has started, the
installed system will be mounted at /target.""")


class SubiquityClient(AsyncTuiApplication):

    project = "subiquity"

    from subiquity.client import controllers as controllers_mod

    controllers = [
        "Welcome",
        "Refresh",
        "Keyboard",
        "Proxy",
        "Mirror",
        "Refresh",
        "Filesystem",
        "Identity",
        "SSH",
        "SnapList",
        "Progress",
        ]

    def make_model(self, **args):
        return None

    def make_ui(self):
        return SubiquityUI(self, self.help_menu)

    def __init__(self, opts):
        self.help_menu = HelpMenu(self)
        super().__init__(opts)
        self.global_overlays = []
        self.conn = aiohttp.UnixConnector(path=opts.socket)
        self.client = make_client(API, self.make_request)
        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root)

        self.note_data_for_apport("UsingAnswers", str(bool(self.answers)))

    @contextlib.asynccontextmanager
    async def session(self):
        async with aiohttp.ClientSession(
                connector=self.conn, connector_owner=False) as session:
            yield session

    async def make_request(self, method, path, *, params, json):
        async with self.session() as session:
            async with session.request(
                    method, 'http://a' + path, json=json,
                    params=params) as response:
                resp = await response.json()
        if resp['status'] == 'skip':
            raise Skip
        elif resp['status'] == 'confirm':
            raise Confirm
        return resp

    async def connect(self):
        print("connecting...", end='', flush=True)
        while True:
            try:
                state = await self.client.meta.status.GET()
            except aiohttp.ClientError:
                await asyncio.sleep(1)
                print(".", end='', flush=True)
            else:
                print()
                break
        if state.status == ApplicationStatus.STARTING:
            print("server is starting...", end='', flush=True)
            while state.status == ApplicationStatus.STARTING:
                await asyncio.sleep(1)
                print(".", end='', flush=True)
                state = await self.client.meta.status.GET()
            print()
        if state.status == ApplicationStatus.INTERACTIVE:
            fd1, watcher1 = journald_listener(
                [state.event_syslog_identifier],
                self.controllers.Progress.event)
            self.aio_loop.add_reader(fd1, watcher1)
            fd2, watcher2 = journald_listener(
                [state.log_syslog_identifier],
                self.controllers.Progress.log_line)
            self.aio_loop.add_reader(fd2, watcher2)
            self.start_urwid()
            self.select_initial_screen(self.initial_controller_index())
        else:
            print(state.status)
            self.aio_loop.stop()

    async def shutdown(self):
        await self.conn.close()
        await self.aio_loop.shutdown_asyncgens()

    def add_global_overlay(self, overlay):
        self.global_overlays.append(overlay)
        if isinstance(self.ui.body, BaseView):
            self.ui.body.show_stretchy_overlay(overlay)

    def remove_global_overlay(self, overlay):
        self.global_overlays.remove(overlay)
        if isinstance(self.ui.body, BaseView):
            self.ui.body.remove_overlay(overlay)

    def load_serialized_state(self):
        pass

    def select_initial_screen(self, index):
        self.error_reporter.load_reports()
        for report in self.error_reporter.reports:
            if report.kind == ErrorReportKind.UI and not report.seen:
                self.show_error_report(report)
                break
        super().select_initial_screen(index)

    async def select_screen(self, new):
        try:
            await super().select_screen(new)
        except Confirm:
            new.context.exit("(needs confirmation)")
            self.show_confirm_install()
            self.controllers.index = self.controllers.instances.index(
                self.cur_screen)

    def show_confirm_install(self):
        self._cancel_show_progress()
        log.debug("showing InstallConfirmation over %s", self.ui.body)
        self.ui.block_input = False
        self.add_global_overlay(InstallConfirmation(self))

    async def confirm_install(self):
        await self.client.meta.confirm.POST()

    auto_start_urwid = False

    def run(self):
        self.aio_loop.create_task(self.connect())
        try:
            super().run()
        except Exception:
            print("generating crash report")
            try:
                report = self.error_reporter.make_apport_report(
                    ErrorReportKind.UI, "Installer UI", wait=True)
                print("report saved to {path}".format(path=report.path))
            except Exception:
                print("report generation failed")
                traceback.print_exc()
        finally:
            self.aio_loop.run_until_complete(self.shutdown())

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
        if key in ['ctrl e', 'ctrl r']:
            interrupt = key == 'ctrl e'

            async def foo():
                ref = await self.client.dry_run.make_error.POST()
                if interrupt:
                    self.show_error_report(ref)

            self.aio_loop.create_task(foo())
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

    def show_error_report(self, error_ref):
        log.debug("show_error_report %r", error_ref.base)
        if isinstance(self.ui.body, BaseView):
            w = getattr(self.ui.body._w, 'stretchy', None)
            if isinstance(w, ErrorReportStretchy):
                # Don't show an error if already looking at one.
                return
        self.add_global_overlay(ErrorReportStretchy(self, error_ref))

    def restart(self, remove_last_screen=True):
        if remove_last_screen:
            self._remove_last_screen()
        self.urwid_loop.stop()
        cmdline = ['snap', 'run', 'subiquity']
        if self.opts.dry_run:
            if self.server_proc is not None:
                print('killing server {}'.format(self.server_proc.pid))
                self.server_proc.send_signal(2)
                self.server_proc.wait()
            cmdline = [
                sys.executable, '-m', 'subiquity.cmd.tui',
                ] + sys.argv[1:]
        os.execvp(cmdline[0], cmdline)
