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

from subiquitycore.controller import BaseController

from subiquity.ui.views import IdentityView

log = logging.getLogger('subiquity.controllers.identity')


class IdentityController(BaseController):

    autoinstall_key = 'identity'

    def __init__(self, app):
        self.model = app.base_model.identity
        super().__init__(app)

    def load_autoinstall(self):
        self.model.add_user(self.autoinstall_data)

    async def apply_autoinstall_config(self):
        self.signal.emit_signal('installprogress:identity-config-done')

    def start_ui(self):
        self.ui.set_body(IdentityView(self.model, self))
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
        self.signal.emit_signal('prev-screen')

    def done(self, user_spec):
        safe_spec = user_spec.copy()
        safe_spec['password'] = '<REDACTED>'
        log.debug(
            "IdentityController.done next-screen user_spec=%s",
            safe_spec)
        self.model.add_user(user_spec)
        self.signal.emit_signal('installprogress:identity-config-done')
        self.signal.emit_signal('next-screen')
