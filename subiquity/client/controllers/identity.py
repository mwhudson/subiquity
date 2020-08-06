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

import logging

from subiquity.client.controller import SubiquityTuiController
from subiquity.ui.views import IdentityView

log = logging.getLogger('subiquity.client.controllers.identity')


class IdentityController(SubiquityTuiController):

    endpoint = '/identity'

    async def _start_ui(self, status):
        await self.app.set_body(IdentityView(status, self))
        if all(elem in self.answers for elem in
               ['realname', 'username', 'password', 'hostname']):
            d = {
                'realname': self.answers['realname'],
                'username': self.answers['username'],
                'hostname': self.answers['hostname'],
                'password': self.answers['password'],
                }
            self.done(d)

    def cancel(self):
        self.app.prev_screen()

    def done(self, user_spec):
        safe_spec = user_spec.copy()
        safe_spec['password'] = '<REDACTED>'
        log.debug(
            "IdentityController.done next_screen user_spec=%s",
            safe_spec)
        self.app.next_screen(self.post(user_spec))
