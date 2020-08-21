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

from aiohttp import web

from subiquitycore.context import Context
from subiquitycore.prober import Prober

from subiquity.common.api.definition import API
from subiquity.common.api.server import bind
from subiquity.common.types import (
    ApplicationState,
    ApplicationStatus,
    )


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


class SubiquityServer:

    project = "subiquity-server"

    def __init__(self, opts, block_log_dir):
        self.prober = Prober(opts.machine_config, self.debug_flags)
        self.opts = opts
        self.context = Context.new(self)

    def report_start_event(self, context, description):
        print("{} start: {}".format(context.full_name(), description))

    def report_finish_event(self, context, description, result):
        print("{} finish: {} {}".format(
            context.full_name(), result, description))

    async def startup(self):
        app = web.Application()
        app['app'] = self
        bind(app.router, API.status, StateController(self))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.UnixSite(runner, self.opts.socket)
        await site.start()

    def run(self):
        loop = asyncio.get_event_loop()
        loop.create_task(self.startup())
        loop.run_forever()
