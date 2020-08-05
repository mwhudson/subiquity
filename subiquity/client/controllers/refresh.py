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

import logging


from subiquitycore.tuicontroller import (
    Skip,
    )

from subiquity.client.controller import (
    SubiquityTuiController,
    )
from subiquity.ui.views.refresh import RefreshView


log = logging.getLogger('subiquity.controllers.refresh')


class RefreshController(SubiquityTuiController):

    endpoint = '/refresh'

    def __init__(self, app):
        super().__init__(app)
        self.offered_first_time = False

    async def get_progress(self, change):
        result = await self.app.snapd.get('v2/changes/{}'.format(change))
        return result['result']

    async def _start_ui(self, data, index=1):
        if self.app.updated:
            raise Skip()
        show = False
        self.status = data
        if index == 1:
            if data['check_state'] == 'AVAILABLE':
                show = True
                self.offered_first_time = True
        elif index == 2:
            if not self.offered_first_time:
                if data['check_state'] in ('UNKNOWN', 'AVAILABLE'):
                    show = True
        else:
            raise AssertionError("unexpected index {}".format(index))
        if show:
            await self.app.set_body(RefreshView(self))
        else:
            raise Skip()

    def done(self, sender=None):
        log.debug("RefreshController.done next_screen")
        self.app.next_screen()

    def cancel(self, sender=None):
        self.app.prev_screen()
