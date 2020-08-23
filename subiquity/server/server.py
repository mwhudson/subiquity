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

import os
import shlex
import sys

from aiohttp import web

from subiquitycore.core import Application
from subiquitycore.prober import Prober
from subiquitycore.snapd import (
    AsyncSnapd,
    FakeSnapdConnection,
    SnapdConnection,
    )

from subiquity.common.api.definition import API
from subiquity.common.api.server import bind
from subiquity.common.errorreport import (
    ErrorReporter,
    )
from subiquity.common.types import (
    ApplicationState,
    ApplicationStatus,
    )
from subiquity.models.subiquity import SubiquityModel


class StateController:

    def __init__(self, app):
        self.app = app
        self.context = app.context.child("State")

    def generic_result(self):
        return {}

    async def get(self):
        return ApplicationState(self.app.status)

    async def wait_early_get(self):
        pass


class SubiquityServer(Application):

    snapd_socket_path = '/run/snapd.socket'

    project = "subiquity"

    from subiquity.server import controllers as controllers_mod

    controllers = [
        "Welcome",
        "Refresh",
        ]

    def make_model(self):
        root = '/'
        if self.opts.dry_run:
            root = os.path.abspath('.subiquity')
        return SubiquityModel(root, self.opts.sources)

    def __init__(self, opts, block_log_dir):
        super().__init__(opts)
        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root)
        self.prober = Prober(opts.machine_config, self.debug_flags)
        self.status = ApplicationStatus.STARTING
        self.autoinstall_config = {}
        self.kernel_cmdline = shlex.split(opts.kernel_cmdline)
        if opts.snaps_from_examples:
            connection = FakeSnapdConnection(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(
                            os.path.dirname(__file__))),
                    "examples", "snaps"),
                self.scale_factor)
        else:
            connection = SnapdConnection(self.root, self.snapd_socket_path)
        self.snapd = AsyncSnapd(connection)

    def note_file_for_apport(self, key, path):
        self.error_reporter.note_file_for_apport(key, path)

    def note_data_for_apport(self, key, value):
        self.error_reporter.note_data_for_apport(key, value)

    def make_apport_report(self, kind, thing, *, wait=False, **kw):
        return self.error_reporter.make_apport_report(
            kind, thing, wait=wait, **kw)

    def interactive(self):
        if not self.autoinstall_config:
            return True
        return bool(self.autoinstall_config.get('interactive-sections'))

    async def startup(self):
        app = web.Application()
        app['app'] = self
        bind(app.router, API.status, StateController(self))
        for controller in self.controllers.instances:
            controller.add_routes(app)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.UnixSite(runner, self.opts.socket)
        await site.start()
        self.status = ApplicationStatus.INTERACTIVE

    def run(self):
        self.aio_loop.create_task(self.startup())
        super().run()

    server_proc = None

    def restart(self):
        cmdline = ['snap', 'run', 'subiquity']
        if self.opts.dry_run:
            cmdline = [
                sys.executable, '-m', 'subiquity.cmd.server',
                ] + sys.argv[1:]
        os.execvp(cmdline[0], cmdline)
