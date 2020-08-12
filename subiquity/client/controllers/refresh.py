# Copyright 2019 Canonical, Ltd.
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

from subiquitycore.tuicontroller import (
    Skip,
    )

from subiquity.client.controller import (
    SubiquityTuiController,
    )
from subiquity.common.api import API, CheckState
from subiquity.ui.views.refresh import RefreshView


log = logging.getLogger('subiquity.controllers.refresh')


class RefreshController(SubiquityTuiController):

    endpoint_cls = API.refresh

    def __init__(self, app):
        super().__init__(app)
        self.offered_first_time = False

    async def get_progress(self, change):
        return await self.endpoint.progress.id.get(id=change)

    async def start_ui(self, index=1):
        status = await self.endpoint.wait.get()
        if self.app.updated:
            raise Skip()
        show = False
        self.status = status
        if index == 1:
            if status.availability == CheckState.AVAILABLE:
                show = True
                self.offered_first_time = True
        elif index == 2:
            if not self.offered_first_time:
                if status.availability in (CheckState.UNKNOWN,
                                           CheckState.AVAILABLE):
                    show = True
        else:
            raise AssertionError("unexpected index {}".format(index))
        if show:
            await self.app.set_body(RefreshView(self))
        else:
            raise Skip()

    async def wait_for_check(self):
        while 1:
            self.status = await self.app.get(self.endpoint)
            if self.status.status != CheckState.UNKNOWN:
                return
            await asyncio.sleep(1)

    async def start_update(self):
        resp = await self.endpoint.post({})
        return resp['change-id']

    def done(self, sender=None):
        log.debug("RefreshController.done next_screen")
        self.app.next_screen()

    def cancel(self, sender=None):
        self.app.prev_screen()
