# Copyright 2015 Canonical, Ltd.
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
import logging

import aiohttp

from subiquitycore.context import with_context

from subiquity.client.controller import SubiquityTuiController
from subiquity.ui.views.installprogress import ProgressView


log = logging.getLogger("subiquity.client.controllers.progress")


class ProgressController(SubiquityTuiController):

    endpoint_name = 'install'

    def __init__(self, app):
        super().__init__(app)
        self.progress_view = ProgressView(self)

    def event(self, event):
        if event["SUBIQUITY_EVENT_TYPE"] == "start":
            self.progress_view.event_start(
                event["SUBIQUITY_CONTEXT_ID"],
                event.get("SUBIQUITY_CONTEXT_PARENT_ID"),
                event["MESSAGE"])
        elif event["SUBIQUITY_EVENT_TYPE"] == "finish":
            self.progress_view.event_finish(
                event["SUBIQUITY_CONTEXT_ID"])

    def log_line(self, event):
        log_line = event['MESSAGE']
        self.progress_view.add_log_line(log_line)

    def cancel(self):
        pass

    def start(self):
        self.app.aio_loop.create_task(self._wait_status())

    def click_reboot(self):
        self.app.aio_loop.create_task(self.send_reboot_and_wait())

    async def send_reboot_and_wait(self):
        await self.app.client.reboot.post({})
        self.app.exit()

    @with_context()
    async def _wait_status(self, context):
        while True:
            try:
                install_state = await self.endpoint.status.get()
            except aiohttp.ClientError:
                await asyncio.sleep(1)
                continue
            self.progress_view.update_for_status(install_state)
            if self.ui.body is self.progress_view:
                self.ui.set_header(self.progress_view.title)
            if install_state.is_terminal():
                return

    async def start_ui(self):
        await self.app.set_body(self.progress_view)
