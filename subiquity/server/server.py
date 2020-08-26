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
import sys

from aiohttp import web

from systemd import journal

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
from subiquity.server.errors import ErrorController


log = logging.getLogger('subiquity.server.server')


class MetaController:

    def __init__(self, app):
        self.app = app
        self.context = app.context.child("Meta")

    def generic_result(self):
        return {'status': 'ok'}

    async def status_GET(self) -> ApplicationState:
        log_id = self.app.controllers.Install._log_syslog_identifier
        return ApplicationState(
            status=self.app.status,
            event_syslog_identifier=self.app.syslog_id,
            log_syslog_identifier=log_id)

    async def status_wait_early_GET(self) -> ApplicationState:
        pass

    async def confirm_POST(self):
        self.app.base_model.confirm()


class SubiquityServer(Application):

    snapd_socket_path = '/run/snapd.socket'

    project = "subiquity"

    from subiquity.server import controllers as controllers_mod

    controllers = [
        "Welcome",
        "Refresh",
        "Keyboard",
        "Proxy",
        "Mirror",
        "Filesystem",
        "Identity",
        "SSH",
        "SnapList",
        "Install",
        ]

    def make_model(self):
        root = '/'
        if self.opts.dry_run:
            root = os.path.abspath('.subiquity')
        return SubiquityModel(root, self.opts.sources)

    def __init__(self, opts, block_log_dir):
        super().__init__(opts)
        self.block_log_dir = block_log_dir
        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root)
        log.debug("debug_flags %s", self.debug_flags)
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
        self.syslog_id = 'subiquity.{}'.format(os.getpid())
        self.event_listeners = []

    def note_file_for_apport(self, key, path):
        self.error_reporter.note_file_for_apport(key, path)

    def note_data_for_apport(self, key, value):
        self.error_reporter.note_data_for_apport(key, value)

    def make_apport_report(self, kind, thing, *, wait=False, **kw):
        return self.error_reporter.make_apport_report(
            kind, thing, wait=wait, **kw)

    def _maybe_push_to_journal(self, event_type, context, description):
        if context.get('hidden', False):
            return
        if not context.get('is-install-context') and self.interactive():
            controller = context.get('controller')
            if controller is None or controller.interactive():
                return
        indent = context.full_name().count('/') - 2
        if context.get('is-install-context'):
            indent -= 1
            msg = context.description
        else:
            msg = context.full_name()
            if description:
                msg += ': ' + description
        msg = '  ' * indent + msg
        if context.parent:
            parent_id = str(context.parent.id)
        else:
            parent_id = ''
        journal.send(
            msg,
            PRIORITY=context.level,
            SYSLOG_IDENTIFIER=self.syslog_id,
            SUBIQUITY_EVENT_TYPE=event_type,
            SUBIQUITY_CONTEXT_ID=str(context.id),
            SUBIQUITY_CONTEXT_PARENT_ID=parent_id)

    def report_start_event(self, context, description):
        for listener in self.event_listeners:
            listener.report_start_event(context, description)
        self._maybe_push_to_journal('start', context, description)

    def report_finish_event(self, context, description, status):
        for listener in self.event_listeners:
            listener.report_finish_event(context, description, status)
        self._maybe_push_to_journal('finish', context, description)

    def interactive(self):
        if not self.autoinstall_config:
            return True
        return bool(self.autoinstall_config.get('interactive-sections'))

    async def startup(self):
        app = web.Application()
        app['app'] = self
        bind(app.router, API.meta, MetaController(self))
        bind(app.router, API.errors, ErrorController(self, self.error_reporter))
        if self.opts.dry_run:
            from .dryrun import DryRunController
            bind(app.router, API.dry_run, DryRunController(self))
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

    def make_autoinstall(self):
        config = {'version': 1}
        for controller in self.controllers.instances:
            controller_conf = controller.make_autoinstall()
            if controller_conf:
                config[controller.autoinstall_key] = controller_conf
        return config
