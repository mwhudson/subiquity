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

from subiquitycore.context import with_context

from subiquity.client.controller import SubiquityTuiController
from subiquity.ui.views.installprogress import ProgressView


log = logging.getLogger("subiquity.client.controllers.installprogress")


class ProgressController(SubiquityTuiController):

    def __init__(self, app):
        super().__init__(app)
        self.progress_view = ProgressView(self)

        self.reboot_clicked = asyncio.Event()
        if self.answers.get('reboot', False):
            self.reboot_clicked.set()

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

    @with_context()
    async def _wait_status(self, context):
        status = await self.app.get('/install/wait')
        self.progress_view.title = status['install_state']
        if self.showing:
            self.ui.set_header(self.progress_view.title)

    @with_context()
    async def start_ui(self, context):
        ## if self.install_state in [
        ##         InstallState.NOT_STARTED,
        ##         InstallState.RUNNING,
        ##         ]:
        ##     self.progress_view.title = _("Installing system")
        ## elif self.install_state == InstallState.DONE:
        ##     self.progress_view.title = _("Install complete!")
        ## elif self.install_state == InstallState.ERROR:
        ##     self.progress_view.title = (
        ##         _('An error occurred during installation'))
        await self.app.set_body(self.progress_view)
