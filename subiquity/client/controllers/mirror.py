# Copyright 2018 Canonical, Ltd.
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

from subiquity.client.controller import SubiquityTuiController
from subiquity.ui.views.mirror import MirrorView

log = logging.getLogger('subiquity.controllers.mirror')


class MirrorController(SubiquityTuiController):

    endpoint = '/mirror'

    def __init__(self, app):
        super().__init__(app)
        if 'country-code' in self.answers:
            self.check_state = CheckState.DONE
            self.model.set_country(self.answers['country-code'])

    async def _start_ui(self, status):
        await self.app.set_body(MirrorView(status['mirror'], self))
        if 'mirror' in self.answers:
            self.done(self.answers['mirror'])
        elif 'country-code' in self.answers \
             or 'accept-default' in self.answers:
            self.done(self.model.get_mirror())

    def cancel(self):
        self.app.prev_screen()

    def done(self, mirror):
        log.debug("MirrorController.done next_screen mirror=%s", mirror)
        self.app.next_screen(self.post({'mirror': mirror}))
