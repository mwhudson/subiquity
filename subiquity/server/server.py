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
import os

from aiohttp import web

from subiquitycore.context import Context
from subiquitycore.core import Application
from subiquitycore.prober import Prober

from subiquity.common.api.definition import API
from subiquity.common.api.server import bind
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
        return ApplicationState(ApplicationStatus.INTERACTIVE)

    async def wait_early_get(self):
        pass


class SubiquityServer(Application):

    project = "subiquity-server"

    from subiquity.server import controllers as controllers_mod
    controllers = [
        "Welcome",
        ]

    def make_model(self):
        root = '/'
        if self.opts.dry_run:
            root = os.path.abspath('.subiquity')
        return SubiquityModel(root, self.opts.sources)

    def __init__(self, opts, block_log_dir):
        super().__init__(opts)
        self.prober = Prober(opts.machine_config, self.debug_flags)
        self.autoinstall_config = {}

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

    def run(self):
        self.aio_loop.create_task(self.startup())
        super().run()
