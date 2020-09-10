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
import json
import logging
import os
import shlex
import sys
from typing import List, Optional

from aiohttp import web

import jsonschema

from systemd import journal

import yaml

from subiquitycore.core import Application
from subiquitycore.prober import Prober
from subiquitycore.snapd import (
    AsyncSnapd,
    FakeSnapdConnection,
    SnapdConnection,
    )

from subiquity.common.api.server import (
    bind,
    controller_for_request,
    )
from subiquity.common.apidef import API
from subiquity.common.errorreport import (
    ErrorReporter,
    )
from subiquity.common.serialize import Serializer
from subiquity.common.types import (
    ApplicationState,
    ApplicationStatus,
    ErrorReportRef,
    ErrorReportKind,
    )
from subiquity.models.subiquity import SubiquityModel
from subiquity.server.controller import SubiquityController
from subiquity.server.errors import ErrorController


log = logging.getLogger('subiquity.server.server')


class MetaController:

    def __init__(self, app):
        self.app = app
        self.context = app.context.child("Meta")

    async def status_GET(self, cur: Optional[ApplicationStatus] = None) \
            -> ApplicationState:
        if cur == self.app.status:
            await self.app.status_event.wait()
        return ApplicationState(
            status=self.app.status,
            commands_syslog_id=self.app.commands_syslog_id,
            event_syslog_id=self.app.event_syslog_id,
            log_syslog_id=self.app.log_syslog_id)

    async def confirm_POST(self) -> None:
        self.app.base_model.confirm()

    async def restart_POST(self) -> None:
        self.app.restart()

    async def mark_configured_POST(self, endpoint_names: List[str]) -> None:
        endpoints = {getattr(API, en) for en in endpoint_names}
        for controller in self.app.controllers.instances:
            if controller.endpoint in endpoints:
                controller.configured()


class SubiquityServer(Application):

    snapd_socket_path = '/run/snapd.socket'

    project = "subiquity"

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

    controllers = [
        "Early",
        "Reporting",
        "Error",
        "Userdata",
        "Package",
        "Debconf",
        "Welcome",
        "Refresh",
        "Keyboard",
        "Zdev",
        "Network",
        "Proxy",
        "Mirror",
        "Filesystem",
        "Identity",
        "SSH",
        "SnapList",
        "Install",
        "Late",
        "Reboot",
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
        self.status_event = asyncio.Event()
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
        self.event_syslog_id = 'subiquity_event.{}'.format(os.getpid())
        self.log_syslog_id = 'subiquity_log.{}'.format(os.getpid())
        self.commands_syslog_id = 'subiquity_commands.{}'.format(os.getpid())
        self.event_listeners = []

    def update_status(self, status):
        self.status_event.set()
        self.status_event.clear()
        self.status = status

    def note_file_for_apport(self, key, path):
        self.error_reporter.note_file_for_apport(key, path)

    def note_data_for_apport(self, key, value):
        self.error_reporter.note_data_for_apport(key, value)

    def make_apport_report(self, kind, thing, *, wait=False, **kw):
        return self.error_reporter.make_apport_report(
            kind, thing, wait=wait, **kw)

    def add_event_listener(self, listener):
        self.event_listeners.append(listener)

    def _maybe_push_to_journal(self, event_type, context, description):
        if not context.get('is-install-context') and self.interactive():
            controller = context.get('controller')
            if controller is None or controller.interactive():
                return
        indent = context.full_name().count('/') - 2
        if context.get('is-install-context') and self.interactive():
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
            SYSLOG_IDENTIFIER=self.event_syslog_id,
            SUBIQUITY_CONTEXT_NAME=context.full_name(),
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

    async def apply_autoinstall_config(self):
        for controller in self.controllers.instances:
            if not controller.interactive():
                if self.base_model.needs_confirmation:
                    if 'autoinstall' in self.kernel_cmdline:
                        self.base_model.confirm()
                    else:
                        if not self.interactive():
                            journal.send(
                                "", SYSLOG_IDENTIFIER=self.event_syslog_id,
                                SUBIQUITY_CONFIRMATION="yes")
                        await self.base_model.confirmation.wait()
                await controller.apply_autoinstall_config()
                controller.configured()

    def load_autoinstall_config(self, only_early):
        log.debug("load_autoinstall_config only_early %s", only_early)
        if self.opts.autoinstall is None:
            return
        with open(self.opts.autoinstall) as fp:
            self.autoinstall_config = yaml.safe_load(fp)
        if only_early:
            self.controllers.Reporting.setup_autoinstall()
            self.controllers.Reporting.start()
            self.controllers.Error.setup_autoinstall()
            with self.context.child("core_validation", level="INFO"):
                jsonschema.validate(self.autoinstall_config, self.base_schema)
            self.controllers.Early.setup_autoinstall()
        else:
            for controller in self.controllers.instances:
                controller.setup_autoinstall()

    @web.middleware
    async def middleware(self, request, handler):
        controller = await controller_for_request(request)
        if self.updated:
            updated = 'yes'
        else:
            updated = 'no'
        status = 'ok'
        if isinstance(controller, SubiquityController):
            if not controller.interactive():
                return web.Response(
                    status=200,
                    headers={'x-status': 'skip', 'x-updated': updated})
            else:
                bm = self.base_model
                if controller.model_name is not None:
                    if bm.needs_confirmation:
                        if not bm.is_configured(controller.model_name):
                            status = 'confirm'
        resp = await handler(request)
        resp.headers['x-updated'] = updated
        if resp.get('exception'):
            exc = resp['exception']
            log.debug(
                'request to {} crashed'.format(request.raw_path), exc_info=exc)
            s = Serializer()
            report = self.make_apport_report(
                ErrorReportKind.SERVER_REQUEST_FAIL,
                "request to {}".format(request.raw_path),
                exc=exc)
            resp.headers['x-error-report'] = json.dumps(s.serialize(
                ErrorReportRef, report.ref()))
        else:
            resp.headers['x-status'] = status
        return resp

    async def start_api_server(self):
        app = web.Application(middlewares=[self.middleware])
        bind(app.router, API.meta, MetaController(self))
        bind(app.router, API.errors, ErrorController(self))
        if self.opts.dry_run:
            from .dryrun import DryRunController
            bind(app.router, API.dry_run, DryRunController(self))
        for controller in self.controllers.instances:
            controller.add_routes(app)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.UnixSite(runner, self.opts.socket)
        await site.start()

    async def startup(self):
        self.base_model = self.make_model()
        self.controllers.load_all()
        await self.start_api_server()
        self.load_autoinstall_config(only_early=True)
        if self.controllers.Early.cmds:
            self.update_status(ApplicationStatus.EARLY_COMMANDS)
            await self.controllers.Early.run()
        self.load_autoinstall_config(only_early=False)
        self.load_serialized_state()
        self._connect_base_signals()
        self.start_controllers()
        if self.interactive():
            self.update_status(ApplicationStatus.INTERACTIVE)
        else:
            self.update_status(ApplicationStatus.NON_INTERACTIVE)
        await self.apply_autoinstall_config()

    def run(self):
        self.aio_loop.create_task(self.startup())
        try:
            self.aio_loop.run_forever()
        finally:
            self.aio_loop.run_until_complete(
                self.aio_loop.shutdown_asyncgens())
        if self._exc:
            exc, self._exc = self._exc, None
            raise exc

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
